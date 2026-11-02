"""Checks ``update_config`` against the shapes the config API really returns.

Success is reported flat as ``{"updated_vehicles": n}``, optionally with an
``ignoredFields`` list naming fields the API dropped, and errors arrive as
``{"response": null, "error": ...}``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from teslemetry_stream.vehicle import LOGGER, TeslemetryStreamVehicle

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
        self, callback: Any, filters: dict[str, Any] | None = None, internal: bool = False
    ) -> Any:
        return lambda: None

    def async_add_connection_listener(self, callback: Any) -> Any:
        return lambda: None


def make_vehicle(vin: str, responses: list[Any]) -> TeslemetryStreamVehicle:
    """Build a vehicle that records payloads and replays canned responses."""
    vehicle = TeslemetryStreamVehicle(FakeStream(), vin)  # type: ignore[arg-type]
    # These tests exercise the no-op check itself, not the lazy-populate
    # fetch (the fake stream has no REST session to serve one) - mark it
    # populated like a real connection's config snapshot already would have.
    vehicle._populated = True
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


class CaptureErrors(logging.Handler):
    """Collect formatted ERROR records emitted by the library."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
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

    # A streaming allowance refusal logs the description and drops the batch.
    over = {
        "response": None,
        "error": "streaming_allowance_exceeded",
        "error_description": "This streaming configuration uses 120% of your allowance",
    }
    vehicle = make_vehicle(VIN_A, [over])
    captured = CaptureErrors()
    LOGGER.addHandler(captured)
    try:
        await vehicle.update_config({"fields": {"BatteryLevel": None}})
    finally:
        LOGGER.removeHandler(captured)
    results.append(
        check(
            "allowance refusal logs the error description",
            any("120% of your allowance" in m for m in captured.messages)
            and not any("streaming_allowance_exceeded" in m for m in captured.messages),
            f"logged {captured.messages}",
        )
    )
    results.append(
        check(
            "allowance refusal clears the pending config",
            vehicle._config == {} and vehicle.fields == {},
            f"pending {vehicle._config}, fields {sorted(vehicle.fields)}",
        )
    )

    # The config-refused listener gets (error, description) once; a removed
    # listener is not called; a raising listener does not block the others.
    vehicle = make_vehicle(VIN_A, [over, FAILED, over])
    calls: list[tuple[str, str | None]] = []
    later: list[tuple[str, str | None]] = []

    def boom(error: str, description: str | None) -> None:
        raise RuntimeError("listener bug")

    vehicle.listen_config_refused(boom)
    vehicle.listen_config_refused(lambda e, d: calls.append((e, d)))
    remove_later = vehicle.listen_config_refused(lambda e, d: later.append((e, d)))
    await vehicle.update_config({"fields": {"BatteryLevel": None}})
    results.append(
        check(
            "config-refused listener called once with error and description",
            calls == [(over["error"], over["error_description"])]
            and later == calls,
            f"calls {calls}",
        )
    )
    remove_later()
    await vehicle.update_config({"fields": {"BatteryLevel": None}})
    results.append(
        check(
            "removed listener not called; other errors reach listeners",
            len(later) == 1 and calls[-1] == ("upstream internal error", None),
            f"calls {calls}, later {later}",
        )
    )
    vehicle = make_vehicle(VIN_A, [ACCEPTED])
    seen: list[Any] = []
    vehicle.listen_config_refused(lambda e, d: seen.append(e))
    await vehicle.update_config({"fields": {"BatteryLevel": None}})
    results.append(check("success does not call the listener", seen == []))

    # The same callback registered twice has independent, idempotent removers.
    vehicle = make_vehicle(VIN_A, [over, over])
    twice: list[str] = []

    def same(error: str, description: str | None) -> None:
        twice.append(error)

    remove_first = vehicle.listen_config_refused(same)
    vehicle.listen_config_refused(same)
    remove_first()
    remove_first()
    await vehicle.update_config({"fields": {"BatteryLevel": None}})
    results.append(
        check(
            "repeated remove only removes its own registration",
            len(twice) == 1,
            f"calls {twice}",
        )
    )

    # Any other error keeps the pending config for the next explicit trigger.
    vehicle = make_vehicle(VIN_A, [FAILED])
    await vehicle.update_config({"fields": {"BatteryLevel": None}})
    results.append(
        check(
            "other errors keep the pending config",
            vehicle._config == {"fields": {"BatteryLevel": None}},
            f"pending {vehicle._config}",
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
