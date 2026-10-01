"""Tests for the listen_ActiveRoute* composite listeners.

After navigation ends Minutes to Arrival goes null, but the car keeps
reporting the last trip's destination, arrival energy and traffic delay. The
composites pair each route field with Minutes to Arrival. Scenarios mirror the
Home Assistant Teslemetry tests the helper was ported from.
"""
from __future__ import annotations

import asyncio
from typing import Any

from teslemetry_stream.const import Signal, TeslaLocation
from teslemetry_stream.stream import TeslemetryStream
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"
MINUTES = Signal.MINUTES_TO_ARRIVAL
DELAY = Signal.ROUTE_TRAFFIC_MINUTES_DELAY
ENERGY = Signal.EXPECTED_ENERGY_PERCENT_AT_TRIP_ARRIVAL
DESTINATION = Signal.DESTINATION_LOCATION
LOCATION = {"latitude": -27.824252, "longitude": 153.328079}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def make_vehicle() -> tuple[TeslemetryStream, TeslemetryStreamVehicle]:
    stream = TeslemetryStream(None, "token", manual=True)  # type: ignore[arg-type]
    vehicle = TeslemetryStreamVehicle(stream, VIN)
    vehicle.fields = {s.value: {} for s in (MINUTES, DELAY, ENERGY, DESTINATION)}
    vehicle._populated = True
    return stream, vehicle


def run(listener: str, messages: list[dict[Signal, Any]]) -> list[Any]:
    """Return every value the callback received, in order."""
    stream, vehicle = make_vehicle()
    values: list[Any] = []
    unsub = getattr(vehicle, listener)(values.append)
    for message in messages:
        stream.ingest({k.value: v for k, v in message.items()}, vin=VIN)
    unsub()
    return values


SEQUENCES: list[tuple[str, str, list[dict[Signal, Any]], list[Any]]] = [
    (
        "route_ends_delay",
        "listen_ActiveRouteTrafficMinutesDelay",
        [
            {MINUTES: 12.5, DELAY: 3, ENERGY: 62},
            {MINUTES: None, DELAY: 0, ENERGY: 62},
        ],
        [3, None],
    ),
    (
        "route_ends_energy",
        "listen_ActiveRouteExpectedEnergyPercentAtTripArrival",
        [
            {MINUTES: 12.5, DELAY: 3, ENERGY: 62},
            {MINUTES: None, DELAY: 0, ENERGY: 62},
        ],
        [62, None],
    ),
    (
        "route_restarts",
        "listen_ActiveRouteTrafficMinutesDelay",
        [
            {MINUTES: 12.5, DELAY: 3},
            {MINUTES: None, DELAY: 0},
            {MINUTES: 30.0, DELAY: 5},
        ],
        [3, None, 5],
    ),
    (
        "route_restarts_with_unchanged_value",
        "listen_ActiveRouteTrafficMinutesDelay",
        [{MINUTES: 12.5, DELAY: 3}, {MINUTES: None}, {MINUTES: 20.0}],
        [3, None, 3],
    ),
    (
        "waits_for_minutes_to_arrival",
        "listen_ActiveRouteTrafficMinutesDelay",
        [{DELAY: 3}, {MINUTES: 12.5}],
        [3],
    ),
    (
        "energy_never_reported",
        "listen_ActiveRouteExpectedEnergyPercentAtTripArrival",
        [{MINUTES: 12.5, DELAY: 3}, {MINUTES: None, DELAY: 0}, {MINUTES: 30.0}],
        [None],
    ),
    (
        "destination_route_ends",
        "listen_ActiveRouteDestinationLocation",
        [
            {DESTINATION: LOCATION, MINUTES: 12.5},
            {DESTINATION: LOCATION, MINUTES: None},
        ],
        [TeslaLocation(**LOCATION), None],
    ),
    (
        "unrelated_event_ignored",
        "listen_ActiveRouteTrafficMinutesDelay",
        [{MINUTES: 12.5, DELAY: 3}, {Signal.VEHICLE_SPEED: 40}],
        [3],
    ),
]


async def main() -> None:
    results: list[bool] = []
    for name, listener, messages, expected in SEQUENCES:
        got = run(listener, messages)
        results.append(check(f"sequence {name}", got == expected, f"got {got!r}"))

    stream, vehicle = make_vehicle()
    before = len(stream._listeners)
    unsub = vehicle.listen_ActiveRouteDestinationLocation(lambda v: None)
    added = len(stream._listeners) - before
    unsub()
    results.append(
        check(
            "one unsubscribe removes all three listeners",
            added == 3 and len(stream._listeners) == before,
            f"added {added}, left {len(stream._listeners) - before}",
        )
    )
    await asyncio.sleep(0)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
