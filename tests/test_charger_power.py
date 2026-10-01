"""Tests for the listen_ChargerPower composite listener.

Charger power streams as two fields, AC and DC Charging Power, and neither is
reliably reset when a session ends. The composite combines them, gated by
Detailed Charge State. Scenarios mirror the Home Assistant Teslemetry sensor
tests the aggregator was ported from; "restored" is the consumer's value
before any callback, which only a callback replaces.
"""
from __future__ import annotations

import asyncio
from typing import Any

from teslemetry_stream.const import Signal
from teslemetry_stream.stream import TeslemetryStream
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"
STATE = Signal.DETAILED_CHARGE_STATE
AC = Signal.AC_CHARGING_POWER
DC = Signal.DC_CHARGING_POWER
UNSET = object()


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def run(messages: list[dict[Signal, Any]], restored: Any = UNSET) -> Any:
    """Return the consumer's value after every message has been dispatched."""
    stream = TeslemetryStream(None, "token", manual=True)  # type: ignore[arg-type]
    vehicle = TeslemetryStreamVehicle(stream, VIN)
    vehicle.fields = {STATE.value: {}, AC.value: {}, DC.value: {}}
    vehicle._populated = True
    value = [restored]
    unsub = vehicle.listen_ChargerPower(lambda v: value.__setitem__(0, v))
    for message in messages:
        stream.ingest({k.value: v for k, v in message.items()}, vin=VIN)
    unsub()
    return value[0]


def charging(**extra: Any) -> dict[Signal, Any]:
    return {STATE: "DetailedChargeStateCharging", **extra}


SEQUENCES: list[tuple[str, list[dict[Signal, Any]], Any]] = [
    ("dc_charging", [{STATE: "DetailedChargeStateCharging", AC: 0, DC: 148.2}], 148.2),
    ("dc_then_ac", [charging(**{AC: 0, DC: 148.2}), {AC: 7, DC: 0}], 7),
    ("ac_charging", [charging(**{AC: 7, DC: 0})], 7),
    (
        "dc_charging_ended",
        [charging(**{AC: 0, DC: 148.2}), {STATE: "DetailedChargeStateDisconnected"}],
        0,
    ),
    (
        "lingering_dc_ignored_after_end",
        [
            charging(**{AC: 0, DC: 148.2}),
            {STATE: "DetailedChargeStateDisconnected"},
            {DC: 148.2},
        ],
        0,
    ),
    (
        "ac_after_dc_ended",
        [
            charging(**{AC: 0, DC: 148.2}),
            {STATE: "DetailedChargeStateDisconnected"},
            {DC: 148.2},
            charging(**{AC: 7}),
        ],
        7,
    ),
    (
        "dc_power_with_charging_start",
        [{STATE: "DetailedChargeStateDisconnected"}, charging(**{DC: 150})],
        150,
    ),
    ("dc_power_zero_without_ac", [charging(**{DC: 150}), {DC: 0}], 0),
    (
        "charging_ended_without_ac",
        [charging(**{DC: 150}), {STATE: "DetailedChargeStateComplete"}],
        0,
    ),
    ("dc_power_before_any_charge_state", [{DC: 150}], 150),
    (
        "dc_power_while_starting",
        [
            {STATE: "DetailedChargeStateDisconnected"},
            {STATE: "DetailedChargeStateStarting", DC: 20},
        ],
        20,
    ),
    (
        "ac_charging_ended",
        [charging(**{AC: 0.6, DC: 0}), {STATE: "DetailedChargeStateDisconnected"}],
        0,
    ),
    (
        "dc_charging_ended_after_ac_session",
        [
            charging(**{AC: 0.6, DC: 0}),
            {STATE: "DetailedChargeStateDisconnected"},
            charging(**{DC: 150}),
            {STATE: "DetailedChargeStateComplete"},
        ],
        0,
    ),
    (
        "ac_charging_after_dc_session",
        [
            charging(**{DC: 150}),
            {STATE: "DetailedChargeStateComplete"},
            charging(**{AC: 7}),
        ],
        7,
    ),
    ("no_power_from_either_source", [charging(**{AC: 0, DC: 0})], 0),
    (
        "late_ac_power_while_not_charging",
        [charging(), {STATE: "DetailedChargeStateDisconnected"}, {AC: 0.6}],
        0,
    ),
    (
        "charging_stopped",
        [charging(**{AC: 7}), {STATE: "DetailedChargeStateStopped"}],
        0,
    ),
    (
        "charging_lost_power",
        [charging(**{AC: 7}), {STATE: "DetailedChargeStateNoPower"}],
        0,
    ),
    *[
        (
            f"late_ac_power_after_{name}_charge_state",
            [
                charging(),
                {STATE: "DetailedChargeStateDisconnected"},
                {STATE: state},
                {AC: 0.6},
            ],
            0,
        )
        for name, state in (
            ("null", None),
            ("unknown", "DetailedChargeStateUnknown"),
            ("calibrating", "DetailedChargeStateCalibrating"),
        )
    ],
    ("dc_power_preferred_over_ac", [charging(**{AC: 11, DC: 3})], 3),
    (
        "null_power_kept_while_not_charging",
        [
            charging(**{AC: 7}),
            {STATE: "DetailedChargeStateDisconnected"},
            {AC: None, DC: None},
            {STATE: "DetailedChargeStateComplete"},
        ],
        None,
    ),
    (
        "null_ac_power_after_charging_ended",
        [charging(**{AC: 7}), {STATE: "DetailedChargeStateDisconnected"}, {AC: None}],
        0,
    ),
    (
        "late_power_from_both_sources_while_not_charging",
        [
            charging(**{AC: 7}),
            {STATE: "DetailedChargeStateDisconnected"},
            {AC: 0.6, DC: 148.2},
        ],
        0,
    ),
    (
        "dc_power_zero_after_ac_session",
        [
            charging(**{AC: 0.6}),
            {STATE: "DetailedChargeStateDisconnected"},
            charging(),
            {DC: 0},
        ],
        0,
    ),
    ("ac_power_zero_before_any_charge_state", [{AC: 0}], 0),
]

RESTORED: list[tuple[str, float, list[dict[Signal, Any]], Any]] = [
    (
        "charging_ended_before_any_charge_state",
        148.2,
        [{STATE: "DetailedChargeStateDisconnected"}],
        0,
    ),
    (
        "charging_ended_after_charging_state",
        148.2,
        [charging(), {STATE: "DetailedChargeStateDisconnected"}],
        0,
    ),
    ("ac_power_zero_while_dc_charging", 148.2, [charging(**{AC: 0})], 148.2),
    (
        "held_ac_power_zero_released_when_charging_ends",
        148.2,
        [charging(**{AC: 0}), {STATE: "DetailedChargeStateComplete"}],
        0,
    ),
    (
        "held_ac_power_zero_superseded_by_dc_power",
        148.2,
        [charging(**{AC: 0}), {DC: 150}],
        150,
    ),
    ("dc_power_zero_while_ac_charging", 7.2, [charging(**{DC: 0})], 7.2),
    ("ac_power_null_while_dc_charging", 148.2, [charging(**{AC: None})], 148.2),
    ("no_power_from_either_source", 148.2, [charging(**{AC: 0, DC: None})], 0),
    ("ac_power_zero_before_any_charge_state", 7.2, [{AC: 0}], 0),
    ("dc_power_zero_before_any_charge_state", 148.2, [{DC: 0}], 0),
    (
        "ac_power_zero_with_unknown_charge_state",
        7.2,
        [{STATE: "DetailedChargeStateUnknown", AC: 0}],
        0,
    ),
]


async def main() -> None:
    results: list[bool] = []
    for name, messages, expected in SEQUENCES:
        got = run(messages)
        results.append(check(f"sequence {name}", got == expected, f"got {got!r}"))
    for name, restored, messages, expected in RESTORED:
        got = run(messages, restored)
        results.append(check(f"restored {name}", got == expected, f"got {got!r}"))
    for name, state in (
        ("null", None),
        ("unknown", "DetailedChargeStateUnknown"),
        ("calibrating", "DetailedChargeStateCalibrating"),
    ):
        steps = [charging(**{AC: 7}), {STATE: state}]
        ok = run(steps) == 7 and run([*steps, {AC: 8}]) == 8
        results.append(check(f"uninformative {name} charge state keeps updating", ok))

    stream = TeslemetryStream(None, "token", manual=True)  # type: ignore[arg-type]
    vehicle = TeslemetryStreamVehicle(stream, VIN)
    vehicle.fields = {STATE.value: {}, AC.value: {}, DC.value: {}}
    vehicle._populated = True
    before = len(stream._listeners)
    unsub = vehicle.listen_ChargerPower(lambda v: None)
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
