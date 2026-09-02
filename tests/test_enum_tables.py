"""Pin TeslemetryEnum value tables in const.py against tesla-protocol 1.4.0.

These tables are hand-maintained, not derived at runtime (see AGENTS.md for
why), so this test is the thing that would catch drift against the proto
enum names on a manual re-check - it is not itself a live comparison.
"""
from __future__ import annotations

from teslemetry_stream import const

# name -> expected TeslemetryEnum.values, verified byte-for-byte against
# tesla_protocol.telemetry.vehicle_data_pb2's enum descriptors (1.4.0).
EXPECTED: dict[str, list[str]] = {
    "DetailedChargeState": [
        "DetailedChargeStateUnknown",
        "DetailedChargeStateDisconnected",
        "DetailedChargeStateNoPower",
        "DetailedChargeStateStarting",
        "DetailedChargeStateCharging",
        "DetailedChargeStateComplete",
        "DetailedChargeStateStopped",
        "DetailedChargeStateCalibrating",
    ],
    "ShiftState": [
        "ShiftStateUnknown",
        "ShiftStateInvalid",
        "ShiftStateP",
        "ShiftStateR",
        "ShiftStateN",
        "ShiftStateD",
        "ShiftStateSNA",
    ],
    "BMSState": [
        "BMSStateUnknown",
        "BMSStateStandby",
        "BMSStateDrive",
        "BMSStateSupport",
        "BMSStateCharge",
        "BMSStateFEIM",
        "BMSStateClearFault",
        "BMSStateFault",
        "BMSStateWeld",
        "BMSStateTest",
        "BMSStateSNA",
    ],
    "CarType": [
        "CarTypeUnknown",
        "CarTypeModelS",
        "CarTypeModelX",
        "CarTypeModel3",
        "CarTypeModelY",
        "CarTypeSemiTruck",
        "CarTypeCybertruck",
    ],
}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}: {label}" + (f" ({detail})" if detail and not ok else ""))
    return ok


def main() -> None:
    results = []
    for name, expected in EXPECTED.items():
        table = getattr(const, name)
        results.append(
            check(
                f"{name}.values matches tesla-protocol 1.4.0",
                table.values == expected,
                f"got {table.values}",
            )
        )

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
