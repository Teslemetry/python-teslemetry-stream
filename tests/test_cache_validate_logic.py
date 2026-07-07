"""Offline unit tests for the pure logic in scripts/tesla_cache_validate.py.

These exercise field extraction, envelope unwrapping, sanitization, presence-
shape inference, and key discovery against synthetic records shaped like the
real na_cache/eu_cache corpus (see
data/chargeport-null-validate-v4/raw/ for the originals this is modeled on).
Nothing here touches NATS - safe to run anywhere, including CI.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tesla_cache_validate as tcv  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name: str, got: object, expected: object) -> None:
    ok = got == expected
    results.append((name, ok))
    if not ok:
        print(f"FAIL {name}: expected {expected!r}, got {got!r}")


def test_extract_dotted() -> None:
    record = {
        "charge_state": {
            "charge_port_door_open": False,
            "charge_port_latch": "Engaged",
            "user_charge_enable_request": None,
        }
    }
    check(
        "extract_dotted explicit false",
        tcv.extract_dotted(record, "charge_state.charge_port_door_open"),
        (tcv.Presence.EXPLICIT_VALUE, False),
    )
    check(
        "extract_dotted present null",
        tcv.extract_dotted(record, "charge_state.user_charge_enable_request"),
        (tcv.Presence.PRESENT_NULL, None),
    )
    check(
        "extract_dotted key absent (leaf missing)",
        tcv.extract_dotted(record, "charge_state.nonexistent_field"),
        (tcv.Presence.KEY_ABSENT, None),
    )
    check(
        "extract_dotted parent absent (no drive_state at all)",
        tcv.extract_dotted(record, "drive_state.latitude"),
        (tcv.Presence.PARENT_ABSENT, None),
    )


def test_unwrap_energy_envelope() -> None:
    wrapped = {"statusCode": 200, "json": {"response": {"grid_status": "Active"}}}
    check(
        "unwrap_energy_envelope unwraps",
        tcv.unwrap_energy_envelope(wrapped),
        {"grid_status": "Active"},
    )
    unwrapped_shape = {"grid_status": "Active"}
    check(
        "unwrap_energy_envelope falls back on unrecognized shape",
        tcv.unwrap_energy_envelope(unwrapped_shape),
        unwrapped_shape,
    )


def test_sanitize_record() -> None:
    record = {
        "vin": "5YJ3E1EA0KF495312",
        "battery_level": 40,
        "wall_connectors": [{"vin": "5YJ3E1EA0KF495312", "din": "abc", "wall_connector_power": 0}],
    }
    check(
        "sanitize_record passthrough for preferred identifier",
        tcv.sanitize_record(record, preferred=True),
        record,
    )
    sanitized = tcv.sanitize_record(record, preferred=False)
    check("sanitize_record redacts top-level vin", sanitized["vin"], "REDACTED")
    check("sanitize_record keeps non-sensitive numeric field", sanitized["battery_level"], 40)
    check(
        "sanitize_record redacts nested vin/din but keeps numeric shape",
        (sanitized["wall_connectors"][0]["vin"], sanitized["wall_connectors"][0]["din"],
         sanitized["wall_connectors"][0]["wall_connector_power"]),
        ("REDACTED", "REDACTED", 0),
    )


def test_infer_presence_shape() -> None:
    always = Counter({tcv.Presence.EXPLICIT_VALUE: 720, tcv.Presence.KEY_ABSENT: 0})
    check("infer_presence_shape ALWAYS", tcv.infer_presence_shape(always, Counter({"0": 720}))[0], "ALWAYS")

    nullable = Counter({tcv.Presence.EXPLICIT_VALUE: 710, tcv.Presence.PRESENT_NULL: 13})
    check("infer_presence_shape NULLABLE", tcv.infer_presence_shape(nullable, Counter({"False": 431, "True": 279}))[0], "NULLABLE")

    true_or_absent = Counter({tcv.Presence.EXPLICIT_VALUE: 40, tcv.Presence.KEY_ABSENT: 3448})
    check(
        "infer_presence_shape TRUE_OR_ABSENT",
        tcv.infer_presence_shape(true_or_absent, Counter({"True": 40}))[0],
        "TRUE_OR_ABSENT",
    )

    conditional = Counter({tcv.Presence.EXPLICIT_VALUE: 23, tcv.Presence.KEY_ABSENT: 5})
    check(
        "infer_presence_shape CONDITIONALLY_PRESENT",
        tcv.infer_presence_shape(conditional, Counter({"Active": 22, "Unknown": 1}))[0],
        "CONDITIONALLY_PRESENT",
    )

    empty: Counter[str] = Counter()
    check("infer_presence_shape INSUFFICIENT_DATA", tcv.infer_presence_shape(empty, Counter())[0], "INSUFFICIENT_DATA")

    always_absent = Counter({tcv.Presence.KEY_ABSENT: 10})
    check("infer_presence_shape ALWAYS_ABSENT", tcv.infer_presence_shape(always_absent, Counter())[0], "ALWAYS_ABSENT")


def test_discover_records() -> None:
    keys = [
        "5YJ3E1EA0KF495312.vehicle_data",
        "5YJ3E1EA0KF495312.data.ChargePortDoorOpen",
        "5YJ3E1EA0KF495312.state",
        "5YJ3E1EA0KF495312.alerts",
        "5YJ3E1EA0KF495312.connectivity.wifi",
        "energy_sites.2533979794926773.live_status",
        "energy_sites.2533979794926773.site_info",
        "energy_sites.2533979794926773.calendar_history.energy.day",
    ]

    vd_refs = tcv.discover_records(tcv.RecordKind.VEHICLE_DATA, "na_cache", "unused", keys)
    check("discover_records vehicle_data finds exactly one", [r.key for r in vd_refs], ["5YJ3E1EA0KF495312.vehicle_data"])

    sig_refs = tcv.discover_records(tcv.RecordKind.SIGNAL, "na_cache", "ChargePortDoorOpen", keys)
    check("discover_records signal matches exact signal name", [r.key for r in sig_refs], ["5YJ3E1EA0KF495312.data.ChargePortDoorOpen"])

    live_refs = tcv.discover_records(tcv.RecordKind.ENERGY_LIVE_STATUS, "na_cache", "unused", keys)
    check("discover_records energy_live_status", [r.identifier for r in live_refs], ["2533979794926773"])

    site_refs = tcv.discover_records(tcv.RecordKind.ENERGY_SITE_INFO, "na_cache", "unused", keys)
    check("discover_records energy_site_info", [r.identifier for r in site_refs], ["2533979794926773"])

    universe = tcv.discover_signal_universe("na_cache", keys)
    check("discover_signal_universe only counts .state keys", universe, ["5YJ3E1EA0KF495312"])


def main() -> None:
    test_extract_dotted()
    test_unwrap_energy_envelope()
    test_sanitize_record()
    test_infer_presence_shape()
    test_discover_records()

    print(f"{'test':<70} result")
    print("-" * 80)
    all_ok = True
    for name, ok in results:
        all_ok = all_ok and ok
        print(f"{name:<70} {'PASS' if ok else 'FAIL'}")
    print("-" * 80)
    print("ALL PASS" if all_ok else "FAILURES PRESENT")
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
