"""Regression test for a reconnect-window gap in the config no-op skip.

``TeslemetryStream.connect()`` sets ``self._response`` and notifies
connection listeners (``stream.connected`` becomes True) before ``listen()``
has read a single SSE line - in particular, before the server's post-connect
config snapshot has been dispatched to the vehicle's internal config
listener. ``add_field``/``prefer_typed``'s no-op skip is gated on
``_record_is_live()``, which only checks "connected and not topic-filtered" -
not "has this connection's snapshot actually been applied yet". A connection
listener that calls ``add_field()`` in that window can match against the
stale pre-disconnect record and skip its PATCH, and nothing retries it once
the snapshot later reveals the mismatch.
"""
from __future__ import annotations

import asyncio
from typing import Any

from teslemetry_stream.const import Key
from teslemetry_stream.stream import TeslemetryStream
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"


class FakeResponse:
    """A response whose content is never actually iterated in this test."""

    status = 200
    url = "https://api.teslemetry.com/sse"

    def close(self) -> None:
        pass


class FakeSession:
    """A session whose get() hands back a connected-but-empty response."""

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return FakeResponse()


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def make_stream(**kwargs: Any) -> TeslemetryStream:
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


async def test_reconnect_window_add_field_matches_stale_record(
    results: list[bool],
) -> None:
    stream = make_stream()
    vehicle, sent = make_vehicle_with_capture(stream)

    # Pre-disconnect state: server had BatteryLevel @ 60s.
    vehicle.fields = {"BatteryLevel": {"interval_seconds": 60}}
    results.append(check("stream starts disconnected", not stream.connected))

    # A connection listener reacting to reconnect - e.g. an HA integration
    # re-asserting its desired fields - the exact scenario `_record_is_live`
    # exists to protect against a stale match.
    scheduled: list[asyncio.Task[None]] = []

    def on_connect(connected: bool) -> None:
        if connected:
            scheduled.append(asyncio.ensure_future(vehicle.add_field("BatteryLevel", 60)))

    stream.async_add_connection_listener(on_connect)

    # Reconnect: this flips `connected` True and fires `on_connect`
    # synchronously, scheduling (not yet running) the add_field task.
    await stream.connect()
    results.append(check("stream reports connected immediately after connect()", stream.connected))

    # Let the scheduled add_field task run its no-op check BEFORE the
    # server's config snapshot for this connection has arrived - the window
    # under test. Server-side truth (unbeknownst to this client yet) is
    # actually 30s, not the stale 60s the record still holds.
    await asyncio.sleep(0)

    # Now the snapshot for the new connection arrives.
    vehicle._on_config_event(
        {Key.VIN: VIN, Key.CONFIG: {"fields": {"BatteryLevel": {"interval_seconds": 30}}}}
    )

    await asyncio.gather(*scheduled)

    results.append(
        check(
            "add_field sends a PATCH instead of matching the pre-reconnect stale record",
            len(sent) == 1 and sent[0]["fields"]["BatteryLevel"] == {"interval_seconds": 60},
            f"sent {sent}",
        )
    )
    results.append(
        check(
            "the desired 60s interval is the vehicle's final state, not the stale 30s snapshot",
            vehicle.fields.get("BatteryLevel") == {"interval_seconds": 60},
            f"fields {vehicle.fields}",
        )
    )


async def main() -> None:
    results: list[bool] = []
    await test_reconnect_window_add_field_matches_stale_record(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
