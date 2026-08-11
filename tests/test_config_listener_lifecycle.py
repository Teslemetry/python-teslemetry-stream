"""Regression tests for the vehicle config-sync listener's lifecycle.

Defects flagged across review of the config-consume feature:

- A first attempt eagerly registered the internal config listener in
  ``TeslemetryStreamVehicle.__init__``, which risked ``TeslemetryStream.
  async_add_listener()`` -> ``asyncio.create_task()`` needing a running
  event loop. That was worked around by deferring registration to first
  use (inside ``add_field``/``prefer_typed``/``update_config``) - but
  lazy registration left a gap: a stream that was already connected
  before the listener existed could have dispatched a config event that
  was simply never seen.
- The actual fix for the loop hazard was structural, not timing:
  ``async_add_listener(..., internal=True)`` makes its
  ``schedule_refresh`` (the gate on the ``asyncio.create_task()`` call)
  unconditionally false for an internal-only registration - so
  registering the config listener eagerly in ``__init__`` is safe outside
  a running loop, and the lazy-registration gap is gone: the listener
  exists from construction, so no connection can ever predate it.
- The same ``internal=True`` flag also excludes it from the "last
  listener removed" auto-close check (and its counterpart "first listener
  starts the task" check) - otherwise a permanently-registered internal
  listener would keep ``_listeners`` non-empty forever, and a later public
  listener's own zero-to-one transition couldn't restart a closed stream.
- The config-sync listener can only observe a server-side change while
  connected AND the ``config`` topic isn't filtered out via
  ``TeslemetryStream(topics=...)``. A separate attempt at handling *that*
  forced a REST refresh before the no-op check whenever disconnected -
  reverted, since it added a failure path and could storm the API with
  GETs for a batch of callers. The no-op *skip* is purely an optimization
  (a redundant PATCH is harmless), so it's gated on the record actually
  being live-maintained (``_record_is_live()``) rather than
  force-freshened; otherwise add_field/prefer_typed just send
  unconditionally, exactly the pre-feature status quo.
"""
from __future__ import annotations

import asyncio
from typing import Any

from teslemetry_stream.stream import TeslemetryStream
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"


class FakeSession:
    """A session whose get() is never expected to be called in these tests."""

    async def get(self, url: str, **kwargs: Any) -> Any:
        raise AssertionError(f"unexpected session.get({url!r}) - these tests must not connect")


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def make_stream(**kwargs: Any) -> TeslemetryStream:
    # manual=True: these tests exercise listener bookkeeping, not the real
    # connect/listen loop - FakeSession.get() intentionally isn't a working
    # SSE endpoint.
    kwargs.setdefault("manual", True)
    return TeslemetryStream(
        session=FakeSession(),  # type: ignore[arg-type]
        access_token="test-token",
        server="api.teslemetry.com",
        **kwargs,
    )


def make_vehicle_with_capture(
    stream: TeslemetryStream,
) -> tuple[TeslemetryStreamVehicle, list[dict[str, Any]]]:
    vehicle = TeslemetryStreamVehicle(stream, VIN)
    sent: list[dict[str, Any]] = []

    async def patch_config(config: dict[str, Any]) -> dict[str, Any]:
        sent.append(dict(config))
        return {"updated_vehicles": 1}

    vehicle.patch_config = patch_config  # type: ignore[assignment,method-assign]
    return vehicle, sent


def test_sync_construction_without_a_loop() -> bool:
    """Must run before any event loop exists - constructing a stream+vehicle
    synchronously (the library's documented pre-async-context usage) must not
    require or start one, and the config listener must already be registered
    by the time construction returns (internal=True never reaches the
    asyncio.create_task() call that would need a loop)."""
    label = "TeslemetryStream(vin=...) construction outside a running loop does not raise"
    try:
        # TeslemetryStream(vin=...) constructs its own TeslemetryStreamVehicle
        # internally (get_vehicle), which is exactly the construction path
        # that must stay loop-free.
        stream = make_stream(vin=VIN)
    except RuntimeError as error:
        return check(label, False, f"raised {error!r}")
    ok = check(label, True)
    return check(
        "the config listener is registered by the time construction returns",
        len(stream._listeners) == 1,
        f"listeners {len(stream._listeners)}",
    ) and ok


async def test_registration_happens_at_construction(results: list[bool]) -> None:
    stream = make_stream()
    _vehicle, _sent = make_vehicle_with_capture(stream)

    results.append(
        check(
            "the internal config listener is registered by construction, before any call",
            len(stream._listeners) == 1,
            f"listeners {len(stream._listeners)}",
        )
    )
    results.append(
        check(
            "the registered listener is marked internal",
            all(is_internal for _, _, is_internal in stream._listeners.values()),
        )
    )


async def test_auto_close_after_last_public_listener_removed(results: list[bool]) -> None:
    stream = make_stream()
    # The internal listener registers at construction; no call needed to set it up.
    _vehicle, _sent = make_vehicle_with_capture(stream)

    # A real/public listener on top of the internal one.
    remove_public = stream.async_add_listener(lambda event: None)

    results.append(
        check(
            "two listeners are registered: one internal, one public",
            len(stream._listeners) == 2,
            f"listeners {len(stream._listeners)}",
        )
    )

    stream.active = True  # simulate a live connection to observe close() flip it back
    remove_public()

    results.append(
        check(
            "removing the last public listener still auto-closes the stream",
            stream.active is False,
        )
    )
    results.append(
        check(
            "the internal listener remains registered after auto-close",
            len(stream._listeners) == 1,
            f"listeners {len(stream._listeners)}",
        )
    )


async def test_cold_stream_add_field_sends_patch_unconditionally(results: list[bool]) -> None:
    """A never-connected (or disconnected) stream can't have observed a
    server-side change, so the no-op skip must not apply - send the PATCH
    unconditionally rather than trying to force the record fresh."""
    stream = make_stream()
    vehicle, sent = make_vehicle_with_capture(stream)
    vehicle.fields = {"BatteryLevel": {"interval_seconds": 60}}  # matches the request below

    results.append(check("the stream starts disconnected", not stream.connected))

    await vehicle.add_field("BatteryLevel", 60)

    results.append(
        check(
            "add_field sends the PATCH even though the record already matches",
            len(sent) == 1 and sent[0]["fields"]["BatteryLevel"] == {"interval_seconds": 60},
            f"sent {sent}",
        )
    )


async def test_filtered_config_topic_sends_patch_unconditionally(results: list[bool]) -> None:
    """Even while connected, if `topics=` filters out the config topic the
    config-sync listener never receives anything - the record can't be
    trusted, so the no-op skip must not apply."""
    stream = make_stream(topics=["state"])
    vehicle, sent = make_vehicle_with_capture(stream)
    vehicle.fields = {"BatteryLevel": {"interval_seconds": 60}}

    stream._response = object()  # type: ignore[assignment]  # simulate a live connection
    results.append(check("the stream is connected", stream.connected))

    await vehicle.add_field("BatteryLevel", 60)

    results.append(
        check(
            "add_field sends the PATCH when the config topic is filtered out",
            len(sent) == 1 and sent[0]["fields"]["BatteryLevel"] == {"interval_seconds": 60},
            f"sent {sent}",
        )
    )


async def test_connected_and_subscribed_record_match_skips(results: list[bool]) -> None:
    """The no-op skip only applies once both conditions hold: connected, and
    the config topic isn't filtered out (default `topics=None` subscribes
    to everything)."""
    stream = make_stream()
    vehicle, sent = make_vehicle_with_capture(stream)
    vehicle.fields = {"BatteryLevel": {"interval_seconds": 60}}

    stream._response = object()  # type: ignore[assignment]  # simulate a live connection
    results.append(
        check(
            "the stream is connected and subscribed to every topic",
            stream.connected and stream.topics is None,
        )
    )

    await vehicle.add_field("BatteryLevel", 60)

    results.append(
        check(
            "add_field skips the PATCH when the record is live-maintained and matches",
            sent == [],
            f"sent {sent}",
        )
    )


async def main(pre_loop_results: list[bool]) -> None:
    results: list[bool] = list(pre_loop_results)
    await test_registration_happens_at_construction(results)
    await test_auto_close_after_last_public_listener_removed(results)
    await test_cold_stream_add_field_sends_patch_unconditionally(results)
    await test_filtered_config_topic_sends_patch_unconditionally(results)
    await test_connected_and_subscribed_record_match_skips(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    # Must run before asyncio.run() starts a loop - that's the entire point.
    pre_loop_results = [test_sync_construction_without_a_loop()]
    asyncio.run(main(pre_loop_results))
