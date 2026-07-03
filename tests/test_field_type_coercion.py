"""End-to-end typing checks for the field-type fixes in v0.9.1.

Exercises the real public ``listen_*`` methods on ``TeslemetryStreamVehicle``
exactly as a library consumer would, then pushes representative *real-world*
streamed values (as sampled from the Teslemetry na_cache NATS KV store, per the
PR description) through the registered listener and asserts the value and the
Python type delivered to the consumer callback.
"""
from __future__ import annotations

import asyncio
from typing import Any

from teslemetry_stream.const import Signal
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"


class FakeStream:
    """Minimal stand-in for TeslemetryStream that just captures listeners."""

    manual = True

    def __init__(self) -> None:
        # maps Signal value -> wrapped listener callback
        self.captured: dict[str, Any] = {}

    def async_add_listener(self, callback, filters=None):
        # filters carries {"vin": ..., "data": {Signal: None}} — grab the field
        signal = next(iter(filters["data"]))
        self.captured[signal] = callback
        return lambda: None


def build_vehicle() -> tuple[TeslemetryStreamVehicle, FakeStream]:
    stream = FakeStream()
    vehicle = TeslemetryStreamVehicle(stream, VIN)  # type: ignore[arg-type]
    # Pre-populate config so _enable_field/add_field short-circuits without HTTP.
    vehicle.fields = {s.value: {} for s in Signal}
    return vehicle, stream


def deliver(stream: FakeStream, signal: Signal, raw: Any) -> Any:
    """Feed a raw streamed value through the captured listener, return delivered."""
    box: dict[str, Any] = {}
    # The captured callback was registered by listen_* with the consumer callback
    # already baked in; re-register a fresh consumer to capture the delivered value.
    event = {"vin": VIN, "data": {signal.value: raw}}
    stream.captured[signal.value](event)
    return box  # unused; delivered value captured by the consumer closure


async def main() -> None:
    results: list[tuple[str, Any, str, Any, str, bool]] = []

    def check(label, signal, register, raw, expected, expected_type):
        vehicle, stream = build_vehicle()
        delivered: dict[str, Any] = {}
        register(vehicle, lambda v: delivered.__setitem__("v", v))
        stream.captured[signal.value]({"vin": VIN, "data": {signal.value: raw}})
        got = delivered.get("v")
        ok = got == expected and type(got) is expected_type
        results.append(
            (label, raw, type(raw).__name__, got, type(got).__name__, ok)
        )

    # --- BATCH 1: seat cooling, previously passed raw str through (wrong) ---
    check(
        "ClimateSeatCoolingFrontLeft",
        Signal.CLIMATE_SEAT_COOLING_FRONT_LEFT,
        lambda v, cb: v.listen_ClimateSeatCoolingFrontLeft(cb),
        "3", 3, int,
    )
    check(
        "ClimateSeatCoolingFrontRight",
        Signal.CLIMATE_SEAT_COOLING_FRONT_RIGHT,
        lambda v, cb: v.listen_ClimateSeatCoolingFrontRight(cb),
        "0", 0, int,
    )

    # --- BATCH 2a: CurrentLimitMph streams fractional values; make_int used to
    #     truncate 74.4367 -> 74. Now make_float preserves the fraction. ---
    check(
        "CurrentLimitMph",
        Signal.CURRENT_LIMIT_MPH,
        lambda v, cb: v.listen_CurrentLimitMph(cb),
        "74.4367", 74.4367, float,
    )
    check(
        "CurrentLimitMph",
        Signal.CURRENT_LIMIT_MPH,
        lambda v, cb: v.listen_CurrentLimitMph(cb),
        "80.6504", 80.6504, float,
    )

    # --- BATCH 2b: SoftwareUpdateScheduledStartTime streams an int epoch as str;
    #     previously delivered raw str, now coerced to int. ---
    check(
        "SoftwareUpdateScheduledStartTime",
        Signal.SOFTWARE_UPDATE_SCHEDULED_START_TIME,
        lambda v, cb: v.listen_SoftwareUpdateScheduledStartTime(cb),
        "1783072740", 1783072740, int,
    )

    # --- Deliberate int divergence (kept as int despite fields.json "real") ---
    check(
        "CruiseSetSpeed (kept int)",
        Signal.CRUISE_SET_SPEED,
        lambda v, cb: v.listen_CruiseSetSpeed(cb),
        "65", 65, int,
    )
    check(
        "DiTorquemotor (kept int)",
        Signal.DI_TORQUEMOTOR,
        lambda v, cb: v.listen_DiTorquemotor(cb),
        "120", 120, int,
    )
    check(
        "ExpectedEnergyPercentAtTripArrival (kept int)",
        Signal.EXPECTED_ENERGY_PERCENT_AT_TRIP_ARRIVAL,
        lambda v, cb: v.listen_ExpectedEnergyPercentAtTripArrival(cb),
        "82", 82, int,
    )

    print(f"{'field':<42} {'raw (stream)':<16} {'delivered':<14} {'type':<7} ok")
    print("-" * 88)
    all_ok = True
    for label, raw, raw_t, got, got_t, ok in results:
        all_ok = all_ok and ok
        print(
            f"{label:<42} {repr(raw):<16} {repr(got):<14} {got_t:<7} "
            f"{'PASS' if ok else 'FAIL'}"
        )
    print("-" * 88)
    print("ALL PASS" if all_ok else "FAILURES PRESENT")
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
