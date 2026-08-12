"""Regression test for a reconnect-window gap in the config no-op skip.

``TeslemetryStream.connect()`` sets ``self._response`` and notifies
connection listeners (``stream.connected`` becomes True) before ``listen()``
has read a single SSE line - in particular, before the server's post-connect
config snapshot has been dispatched to the vehicle's internal config
listener. ``TeslemetryStreamVehicle`` unpopulates itself on disconnect (see
its ``_on_connection_event``), so a field-config call landing in that window
finds itself unpopulated and awaits a fresh REST fetch rather than trusting
the stale pre-disconnect record.
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
    """A session whose get() hands back a connected-but-empty response, or
    (once armed) serves the vehicle's config GET."""

    def __init__(self) -> None:
        self.config_calls = 0
        self.config_body: dict[str, Any] | None = None

    async def get(self, url: str, **kwargs: Any) -> Any:
        if "/api/config/" in url:
            self.config_calls += 1
            assert self.config_body is not None, "get_config() called before armed"
            return FakeConfigResponse(self.config_body)
        return FakeResponse()


class FakeConfigResponse:
    status = 200

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    async def json(self) -> dict[str, Any]:
        return self._body


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


async def test_reconnect_window_add_field_refetches_instead_of_trusting_stale_record(
    results: list[bool],
) -> None:
    stream = make_stream()
    vehicle, sent = make_vehicle_with_capture(stream)

    # An initial connection, so a later _close_response() has something to
    # actually tear down (and thus something to notify listeners about).
    await stream.connect()

    # Pre-disconnect state: server had BatteryLevel @ 60s, learned via a
    # push event (so the vehicle is populated).
    vehicle._on_config_event(
        {Key.VIN: VIN, Key.CONFIG: {"fields": {"BatteryLevel": {"interval_seconds": 60}}}}
    )
    results.append(check("the vehicle is populated before disconnect", vehicle._populated))

    # Disconnect: the connection listener unpopulates the record.
    stream._close_response()
    results.append(
        check("disconnect unpopulates the vehicle", not vehicle._populated)
    )

    # Server-side truth changed while disconnected (unbeknownst to this
    # client yet) - the reconnect's config snapshot will reveal 30s.
    stream._session.config_body = {  # type: ignore[attr-defined]
        "fields": {"BatteryLevel": {"interval_seconds": 30}},
        "prefer_typed": False,
    }

    # A connection listener reacting to reconnect - e.g. an HA integration
    # re-asserting its desired fields - the exact scenario under test.
    scheduled: list[asyncio.Task[None]] = []

    def on_connect(connected: bool) -> None:
        if connected:
            scheduled.append(asyncio.ensure_future(vehicle.add_field("BatteryLevel", 60)))

    stream.async_add_connection_listener(on_connect)

    # Reconnect: this flips `connected` True and fires `on_connect`
    # synchronously, scheduling (not yet running) the add_field task - well
    # before the server's config snapshot for this connection arrives.
    await stream.connect()
    results.append(
        check("stream reports connected immediately after connect()", stream.connected)
    )

    await asyncio.gather(*scheduled)

    results.append(
        check(
            "add_field fetched fresh config instead of trusting the stale pre-disconnect record",
            stream._session.config_calls == 1,  # type: ignore[attr-defined]
            f"config GETs {stream._session.config_calls}",  # type: ignore[attr-defined]
        )
    )
    results.append(
        check(
            "add_field sends a PATCH since the fresh 30s answer doesn't match the desired 60s",
            len(sent) == 1 and sent[0]["fields"]["BatteryLevel"] == {"interval_seconds": 60},
            f"sent {sent}",
        )
    )
    results.append(
        check(
            "the desired 60s interval is the vehicle's final state",
            vehicle.fields.get("BatteryLevel") == {"interval_seconds": 60},
            f"fields {vehicle.fields}",
        )
    )


async def main() -> None:
    results: list[bool] = []
    await test_reconnect_window_add_field_refetches_instead_of_trusting_stale_record(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
