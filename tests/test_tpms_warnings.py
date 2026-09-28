"""Regression tests for the TPMS soft/hard warning listeners.

Both fields stream as a per-tire object of booleans, never a number. They
were typed and parsed as ints, so a consumer trusting the annotation treated
the object as a scalar and rendered its repr as a sensor state.
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from teslemetry_stream.const import Signal
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"

# The real wire shape, as streamed by a Model 3 on 2026.26.6.
WARNINGS = {
    "frontLeft": False,
    "frontRight": True,
    "rearLeft": False,
    "rearRight": False,
    "semiMiddleAxleLeft2": False,
    "semiMiddleAxleRight2": False,
    "semiRearAxleLeft": False,
    "semiRearAxleLeft2": False,
    "semiRearAxleRight": False,
    "semiRearAxleRight2": False,
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


def deliver(name: str, signal: Signal, raw: Any) -> Any:
    stream = FakeStream()
    vehicle = TeslemetryStreamVehicle(stream, VIN)  # type: ignore[arg-type]
    vehicle.fields = {signal.value: {}}
    vehicle._populated = True
    delivered: list[Any] = []
    getattr(vehicle, name)(delivered.append)
    stream.captured[signal.value]({"vin": VIN, "data": {signal.value: raw}})
    return delivered[0]


async def main() -> None:
    results: list[bool] = []
    for name, signal in (
        ("listen_TpmsSoftWarnings", Signal.TPMS_SOFT_WARNINGS),
        ("listen_TpmsHardWarnings", Signal.TPMS_HARD_WARNINGS),
    ):
        annotation = inspect.signature(
            getattr(TeslemetryStreamVehicle, name)
        ).parameters["callback"].annotation
        results.append(
            check(
                f"{name} callback is typed as a dict",
                annotation == "Callable[[dict[str, Any] | None], None]",
                f"got {annotation}",
            )
        )
        got = deliver(name, signal, WARNINGS)
        results.append(
            check(f"{name} delivers the per-tire object", got == WARNINGS, f"got {got!r}")
        )
        got = deliver(name, signal, None)
        results.append(check(f"{name} delivers None for null", got is None, f"got {got!r}"))

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
