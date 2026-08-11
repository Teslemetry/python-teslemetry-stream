"""Checks ``update_config`` against the shapes the config API really returns.

Success is reported flat as ``{"updated_vehicles": n}``, optionally with an
``ignoredFields`` list naming fields the API dropped, and errors arrive as
``{"response": null, "error": ...}``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN_A = "TESTVIN0000000001"
VIN_B = "TESTVIN0000000002"

# Response bodies as observed against the live API
ACCEPTED: dict[str, Any] = {"updated_vehicles": 1}
IGNORED: dict[str, Any] = {"updated_vehicles": 1, "ignoredFields": ["RouteLastUpdated"]}
ALL_IGNORED: dict[str, Any] = {
    "updated_vehicles": 0,
    "ignoredFields": ["LifetimeEnergyUsedDrive", "RouteLastUpdated"],
}
FAILED: dict[str, Any] = {"response": None, "error": "upstream internal error"}


class FakeStream:
    """Minimal stand-in for TeslemetryStream."""

    manual = True

    def async_add_listener(
        self, callback: Any, filters: dict[str, Any] | None = None
    ) -> Any:
        return lambda: None


def make_vehicle(vin: str, responses: list[Any]) -> TeslemetryStreamVehicle:
    """Build a vehicle that records payloads and replays canned responses."""
    vehicle = TeslemetryStreamVehicle(FakeStream(), vin)  # type: ignore[arg-type]
    vehicle.sent = []  # type: ignore[attr-defined]

    async def patch_config(config: dict[str, Any]) -> dict[str, Any]:
        vehicle.sent.append(dict(config))  # type: ignore[attr-defined]
        return responses.pop(0) if responses else ACCEPTED

    vehicle.patch_config = patch_config  # type: ignore[assignment,method-assign]
    return vehicle


class CaptureWarnings(logging.Handler):
    """Collect formatted WARNING records emitted by the library."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<56} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


async def main() -> None:
    results = []

    # A confirmed update records its fields and leaves nothing pending.
    vehicle = make_vehicle(VIN_A, [ACCEPTED])
    await vehicle.update_config({"fields": {"BatteryLevel": {"interval_seconds": 60}}})
    results.append(
        check(
            "a confirmed update records its fields",
            "BatteryLevel" in vehicle.fields and vehicle._config == {},
            f"fields {sorted(vehicle.fields)}, pending {vehicle._config}",
        )
    )

    # Ignored fields are named in a warning.
    handler = CaptureWarnings()
    logger = logging.getLogger("teslemetry_stream")
    logger.addHandler(handler)
    try:
        vehicle = make_vehicle(VIN_A, [IGNORED])
        await vehicle.update_config(
            {"fields": {"BatteryLevel": None, "RouteLastUpdated": None}}
        )
        results.append(
            check(
                "ignored fields are named in a warning",
                any("RouteLastUpdated" in m for m in handler.messages),
                f"warnings {handler.messages}",
            )
        )

        handler.messages.clear()
        vehicle = make_vehicle(VIN_A, [ALL_IGNORED])
        await vehicle.update_config({"fields": {"RouteLastUpdated": None}})
        results.append(
            check(
                "every ignored field is named",
                any(
                    "RouteLastUpdated" in m and "LifetimeEnergyUsedDrive" in m
                    for m in handler.messages
                ),
                f"warnings {handler.messages}",
            )
        )

        handler.messages.clear()
        vehicle = make_vehicle(VIN_A, [ACCEPTED])
        await vehicle.update_config({"fields": {"BatteryLevel": None}})
        results.append(
            check(
                "no warning when nothing was ignored",
                not handler.messages,
                f"warnings {handler.messages}",
            )
        )
    finally:
        logger.removeHandler(handler)

    # Ignored fields were dropped by the API, so they are not configured - and
    # must not short-circuit a later add_field into reporting them as enabled.
    vehicle = make_vehicle(VIN_A, [IGNORED])
    await vehicle.update_config(
        {"fields": {"BatteryLevel": None, "RouteLastUpdated": None}}
    )
    results.append(
        check(
            "an ignored field is not recorded as configured",
            "RouteLastUpdated" not in vehicle.fields and "BatteryLevel" in vehicle.fields,
            f"fields {sorted(vehicle.fields)}",
        )
    )
    before = len(vehicle.sent)  # type: ignore[attr-defined]
    await vehicle.add_field("RouteLastUpdated")
    results.append(
        check(
            "an ignored field is requested again, not short-circuited",
            len(vehicle.sent) == before + 1,  # type: ignore[attr-defined]
            f"{len(vehicle.sent) - before} further request(s)",  # type: ignore[attr-defined]
        )
    )

    # A default add_field stores an options mapping, so a second listener on the
    # same signal does not call .get on None.
    vehicle = make_vehicle(VIN_A, [ACCEPTED, ACCEPTED])
    await vehicle.add_field("BatteryLevel")
    results.append(
        check(
            "a default add_field records an empty mapping",
            vehicle.fields.get("BatteryLevel") == {},
            f"stored {vehicle.fields.get('BatteryLevel')!r}",
        )
    )
    try:
        await vehicle.add_field("BatteryLevel")
        second_ok = True
    except AttributeError:
        second_ok = False
    results.append(check("a second listener on the same signal does not raise", second_ok))
    results.append(
        check(
            "a later add_field with an interval still goes through",
            (await vehicle.add_field("BatteryLevel", 60)) is None
            and vehicle.sent[-1]["fields"]["BatteryLevel"]  # type: ignore[attr-defined]
            == {"interval_seconds": 60},
            f"sent {vehicle.sent[-1]}",  # type: ignore[attr-defined]
        )
    )

    # A failed update does not record its fields as configured.
    vehicle = make_vehicle(VIN_A, [FAILED])
    await vehicle.update_config({"fields": {"BatteryLevel": None}})
    results.append(
        check(
            "a failed update records no fields",
            vehicle.fields == {},
            f"fields {sorted(vehicle.fields)}",
        )
    )

    # prefer_typed=False must be recorded as False, not coerced to True.
    vehicle = make_vehicle(VIN_A, [ACCEPTED])
    await vehicle.prefer_typed(False)
    results.append(
        check(
            "prefer_typed(False) recorded as False",
            vehicle.preferTyped is False,
            f"got {vehicle.preferTyped!r}",
        )
    )

    # Pending config must not be shared between vehicles.
    first = make_vehicle(VIN_A, [FAILED])
    second = make_vehicle(VIN_B, [ACCEPTED])
    await first.update_config({"fields": {"RouteLastUpdated": None}})
    await second.update_config({"fields": {"BatteryLevel": None}})
    sent = second.sent[0]["fields"]  # type: ignore[attr-defined]
    results.append(
        check(
            "one vehicle's pending config does not leak to another",
            "RouteLastUpdated" not in sent,
            f"sent {sorted(sent)}",
        )
    )
    results.append(
        check(
            "one vehicle's recorded fields do not leak to another",
            "BatteryLevel" not in first.fields,
            f"first {sorted(first.fields)}, second {sorted(second.fields)}",
        )
    )

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
