"""Regression tests for the vehicle config-sync listener's lifecycle.

Two defects flagged in review of the config-consume feature:

- Eagerly registering the internal config listener in
  ``TeslemetryStreamVehicle.__init__`` called ``TeslemetryStream.
  async_add_listener()`` -> ``asyncio.create_task()`` for the very first
  listener, which requires a running event loop. That broke the
  previously-synchronous ``TeslemetryStream(vin=...)``/vehicle
  construction. Registration is now deferred to first use (inside
  ``add_field``/``prefer_typed``/``update_config``, all async).
- The internal listener, once registered, stayed in
  ``TeslemetryStream._listeners`` forever, so the "last listener removed"
  auto-close check (which fires on an empty ``_listeners``) could never
  trigger once every real/public listener was gone - the SSE connection
  leaked open. ``async_add_listener(..., internal=True)`` now excludes it
  from that check.
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


def test_sync_construction_without_a_loop() -> bool:
    """Must run before any event loop exists - constructing a stream+vehicle
    synchronously (the library's documented pre-async-context usage) must not
    require or start one."""
    label = "TeslemetryStream(vin=...) construction outside a running loop does not raise"
    try:
        stream = make_stream(vin=VIN)
        TeslemetryStreamVehicle(stream, VIN)
        return check(label, True)
    except RuntimeError as error:
        return check(label, False, f"raised {error!r}")


async def test_lazy_registration_happens_on_first_use(results: list[bool]) -> None:
    stream = make_stream()
    vehicle = TeslemetryStreamVehicle(stream, VIN)

    results.append(
        check(
            "no listener is registered at construction",
            len(stream._listeners) == 0,
            f"listeners {len(stream._listeners)}",
        )
    )

    async def patch_config(config: dict[str, Any]) -> dict[str, Any]:
        return {"updated_vehicles": 1}

    vehicle.patch_config = patch_config  # type: ignore[assignment,method-assign]
    await vehicle.add_field("BatteryLevel")

    results.append(
        check(
            "the internal config listener is registered by the first add_field call",
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
    vehicle = TeslemetryStreamVehicle(stream, VIN)

    async def patch_config(config: dict[str, Any]) -> dict[str, Any]:
        return {"updated_vehicles": 1}

    vehicle.patch_config = patch_config  # type: ignore[assignment,method-assign]
    # Registers the internal (excluded) listener.
    await vehicle.add_field("BatteryLevel")

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


async def main(pre_loop_results: list[bool]) -> None:
    results: list[bool] = list(pre_loop_results)
    await test_lazy_registration_happens_on_first_use(results)
    await test_auto_close_after_last_public_listener_removed(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    # Must run before asyncio.run() starts a loop - that's the entire point.
    pre_loop_results = [test_sync_construction_without_a_loop()]
    asyncio.run(main(pre_loop_results))
