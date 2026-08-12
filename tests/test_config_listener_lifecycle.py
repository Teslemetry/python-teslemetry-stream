"""Regression tests for the vehicle config-sync listener's lifecycle.

Defects flagged across review of the config-consume feature:

- A first attempt eagerly registered the internal config listener in
  ``TeslemetryStreamVehicle.__init__``, which risked ``TeslemetryStream.
  async_add_listener()`` -> ``asyncio.create_task()`` needing a running
  event loop. That was worked around by deferring registration to first
  use (inside ``add_field``/``update_config``) - but lazy registration
  left a gap: a stream that was already connected
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
- ``add_field`` no longer gates its no-op skip on connection/topic state
  (``_record_is_live()``, since removed). Instead it gates on whether the
  record has ever been ``_populated`` - by a push event or by a REST
  fetch. An unpopulated record is fetched over REST before the no-op
  decision is made; a populated one is trusted without hitting the
  network at all.
"""
from __future__ import annotations

import asyncio
from typing import Any

from teslemetry_stream.const import Key
from teslemetry_stream.stream import TeslemetryStream
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"


class RefusingSession:
    """A session whose get() is never expected to be called in these tests."""

    async def get(self, url: str, **kwargs: Any) -> Any:
        raise AssertionError(f"unexpected session.get({url!r}) - these tests must not connect")


class FakeConfigResponse:
    """Minimal stand-in for the aiohttp response get_config() awaits."""

    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self._body = body

    async def json(self) -> dict[str, Any]:
        return self._body


class FetchingSession:
    """A session that serves a canned config GET and counts calls."""

    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.calls = 0
        self.status = status
        self.body = body

    async def get(self, url: str, **kwargs: Any) -> FakeConfigResponse:
        self.calls += 1
        return FakeConfigResponse(self.status, self.body)


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def make_stream(session: Any, **kwargs: Any) -> TeslemetryStream:
    # manual=True: these tests exercise listener bookkeeping, not the real
    # connect/listen loop.
    kwargs.setdefault("manual", True)
    return TeslemetryStream(
        session=session,
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
        stream = make_stream(RefusingSession(), vin=VIN)
    except RuntimeError as error:
        return check(label, False, f"raised {error!r}")
    ok = check(label, True)
    ok = (
        check(
            "the config listener is registered by the time construction returns",
            len(stream._listeners) == 1,
            f"listeners {len(stream._listeners)}",
        )
        and ok
    )
    return (
        check(
            "the connection listener is registered by the time construction returns",
            len(stream._connection_listeners) == 1,
            f"connection listeners {len(stream._connection_listeners)}",
        )
        and ok
    )


async def test_registration_happens_at_construction(results: list[bool]) -> None:
    stream = make_stream(RefusingSession())
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
    results.append(
        check(
            "the connection listener is registered by construction",
            len(stream._connection_listeners) == 1,
            f"connection listeners {len(stream._connection_listeners)}",
        )
    )


async def test_auto_close_after_last_public_listener_removed(results: list[bool]) -> None:
    stream = make_stream(RefusingSession())
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


async def test_unpopulated_add_field_fetches_before_deciding(results: list[bool]) -> None:
    """A vehicle that has never received a config event or a REST fetch must
    not trust its unset defaults - add_field awaits get_config() first, then
    decides the no-op skip against the answer it got back."""
    session = FetchingSession(
        200, {"fields": {"BatteryLevel": {"interval_seconds": 60}}}
    )
    stream = make_stream(session)
    vehicle, sent = make_vehicle_with_capture(stream)

    results.append(check("the vehicle starts unpopulated", not vehicle._populated))

    # Matches what the fetch will reveal - should fetch, then skip.
    await vehicle.add_field("BatteryLevel", 60)
    results.append(check("get_config was fetched exactly once", session.calls == 1))
    results.append(
        check(
            "add_field skips the PATCH once the fetched record matches",
            sent == [],
            f"sent {sent}",
        )
    )
    results.append(check("the vehicle is now populated", vehicle._populated))

    # A second call for a field the fetch didn't mention must not re-fetch,
    # and must send since it doesn't match.
    await vehicle.add_field("ChargeState")
    results.append(
        check("a later call does not re-fetch once populated", session.calls == 1)
    )
    results.append(
        check(
            "a later call sends when the (now-trusted) record doesn't match",
            len(sent) == 1 and "ChargeState" in sent[0]["fields"],
            f"sent {sent}",
        )
    )


async def test_populated_add_field_skips_without_fetching(results: list[bool]) -> None:
    """Once a config event has populated the record, add_field trusts it
    outright - no REST fetch, matching the pre-feature status quo for the
    push-driven path."""
    stream = make_stream(RefusingSession())
    vehicle, sent = make_vehicle_with_capture(stream)

    vehicle._on_config_event(
        {
            Key.VIN: VIN,
            Key.CONFIG: {"fields": {"BatteryLevel": {"interval_seconds": 60}}},
        }
    )
    results.append(check("the config event populated the vehicle", vehicle._populated))

    await vehicle.add_field("BatteryLevel", 60)
    results.append(
        check(
            "add_field skips the PATCH without ever calling session.get",
            sent == [],
            f"sent {sent}",
        )
    )


async def test_authoritative_404_clears_stale_fields(results: list[bool]) -> None:
    """A vehicle carrying fields from before a disconnect must not trust them
    forever if the config was deleted server-side while it was offline - a
    404 on the reconnect-window fetch is authoritative (no config exists),
    so it must clear `fields`, not just mark the record populated."""
    session = FetchingSession(404, {})
    stream = make_stream(session)
    vehicle, sent = make_vehicle_with_capture(stream)

    # Simulate a stale record surviving a disconnect: previously populated
    # with a field the server no longer has, then unpopulated as a real
    # disconnect would leave it.
    vehicle.fields = {"BatteryLevel": {"interval_seconds": 60}}
    vehicle._populated = False

    await vehicle.get_config()
    results.append(
        check(
            "an authoritative 404 clears stale fields, not just marks populated",
            vehicle.fields == {},
            f"fields {vehicle.fields}",
        )
    )

    # With the stale record cleared, a later add_field for that same field
    # must send - not skip on a match that no longer exists - and without
    # re-fetching, since the (now correctly empty) record is populated.
    await vehicle.add_field("BatteryLevel", 60)
    results.append(
        check(
            "add_field sends the PATCH instead of no-op'ing against the stale record",
            session.calls == 1 and len(sent) == 1 and "BatteryLevel" in sent[0]["fields"],
            f"calls {session.calls}, sent {sent}",
        )
    )


async def main(pre_loop_results: list[bool]) -> None:
    results: list[bool] = list(pre_loop_results)
    await test_registration_happens_at_construction(results)
    await test_auto_close_after_last_public_listener_removed(results)
    await test_unpopulated_add_field_fetches_before_deciding(results)
    await test_populated_add_field_skips_without_fetching(results)
    await test_authoritative_404_clears_stale_fields(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    # Must run before asyncio.run() starts a loop - that's the entire point.
    pre_loop_results = [test_sync_construction_without_a_loop()]
    asyncio.run(main(pre_loop_results))
