"""Regression test: per-door listeners tolerate a null or partial DoorState.

BLE broadcast ingest can emit DoorState as null or with only some doors. The
per-door listeners called .get on the raw value, so a null DoorState raised
AttributeError instead of delivering None.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from teslemetry_stream.const import Signal
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"

DOORS = {
    "listen_FrontDriverDoor": "DriverFront",
    "listen_RearDriverDoor": "DriverRear",
    "listen_FrontPassengerDoor": "PassengerFront",
    "listen_RearPassengerDoor": "PassengerRear",
    "listen_TrunkFront": "TrunkFront",
    "listen_TrunkRear": "TrunkRear",
}


class FakeStream:
    """Minimal stand-in for TeslemetryStream that captures listeners."""

    manual = True

    def __init__(self) -> None:
        self.captured: dict[str, Any] = {}

    def async_add_listener(
        self,
        callback: Callable[[dict[str, Any]], None],
        filters: dict[str, Any] | None = None,
        internal: bool = False,
    ) -> Callable[[], None]:
        assert filters is not None
        if "data" in filters:
            self.captured[next(iter(filters["data"]))] = callback
        return lambda: None

    def async_add_connection_listener(
        self, callback: Callable[[bool], None]
    ) -> Callable[[], None]:
        return lambda: None


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def deliver(name: str, raw: Any) -> Any:
    stream = FakeStream()
    vehicle = TeslemetryStreamVehicle(stream, VIN)  # type: ignore[arg-type]
    vehicle.fields = {Signal.DOOR_STATE.value: {}}
    vehicle._populated = True
    delivered: list[Any] = []
    getattr(vehicle, name)(delivered.append)
    stream.captured[Signal.DOOR_STATE.value](
        {"vin": VIN, "data": {Signal.DOOR_STATE.value: raw}}
    )
    return delivered[0]


async def main() -> None:
    results: list[bool] = []
    for name, key in DOORS.items():
        got = deliver(name, {key: True, "Other": False})
        results.append(check(f"{name} delivers the door value", got is True, f"got {got!r}"))
        got = deliver(name, {"Unrelated": True})
        results.append(
            check(f"{name} delivers None for partial DoorState", got is None, f"got {got!r}")
        )
        got = deliver(name, None)
        results.append(
            check(f"{name} delivers None for null DoorState", got is None, f"got {got!r}")
        )

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
