"""Config-update SSE events keep the internal config record fresh.

The server pushes a ``config`` event (``Key.CONFIG`` / ``SseTopic.CONFIG``)
shaped like ``{"vin": ..., "config": {"fields": {...}, "prefer_typed": bool}}``,
mirroring the REST ``get_config`` response body.  ``TeslemetryStreamVehicle``
registers an internal listener for it at construction (see
``test_config_listener_lifecycle.py`` for why that's safe even outside a
running loop) so ``fields``/``preferTyped`` - and therefore the
``add_field``/``prefer_typed`` no-op checks - reflect current server truth
rather than only what this client has itself requested or observed at
connect.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from teslemetry_stream.const import Key
from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"


class FakeStream:
    """Minimal stand-in for TeslemetryStream that captures the config listener."""

    manual = True
    # Keeps the record "live" (see _record_is_live) so add_field/prefer_typed's
    # no-op check runs - these tests exercise the event-driven merge itself.
    connected = True
    topics = None

    def __init__(self) -> None:
        self.config_listener: Callable[[dict[str, Any]], None] | None = None

    def async_add_listener(
        self,
        callback: Callable[[dict[str, Any]], None],
        filters: dict[str, Any] | None = None,
        internal: bool = False,
    ) -> Callable[[], None]:
        assert filters is not None
        if Key.CONFIG in filters:
            self.config_listener = callback
        return lambda: None


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


def make_vehicle() -> tuple[TeslemetryStreamVehicle, FakeStream]:
    """Build a vehicle that records PATCH payloads instead of sending them."""
    stream = FakeStream()
    vehicle = TeslemetryStreamVehicle(stream, VIN)  # type: ignore[arg-type]
    vehicle.sent = []  # type: ignore[attr-defined]

    async def patch_config(config: dict[str, Any]) -> dict[str, Any]:
        vehicle.sent.append(dict(config))  # type: ignore[attr-defined]
        return {"updated_vehicles": 1}

    vehicle.patch_config = patch_config  # type: ignore[assignment,method-assign]
    return vehicle, stream


async def main() -> None:
    results = []

    # A config event replaces the record with current server truth.
    vehicle, stream = make_vehicle()
    assert stream.config_listener is not None
    stream.config_listener(
        {
            "vin": VIN,
            "config": {
                "fields": {"BatteryLevel": {"interval_seconds": 60}},
                "prefer_typed": True,
            },
        }
    )
    results.append(
        check(
            "a config event updates fields and prefer_typed",
            vehicle.fields == {"BatteryLevel": {"interval_seconds": 60}}
            and vehicle.preferTyped is True,
            f"fields {vehicle.fields}, prefer_typed {vehicle.preferTyped}",
        )
    )

    # A request that now matches the updated record is skipped - no PATCH sent.
    await vehicle.add_field("BatteryLevel", 60)
    results.append(
        check(
            "a request matching the updated record is skipped",
            vehicle.sent == [],
            f"sent {vehicle.sent}",
        )
    )

    # A request that differs from the updated record is still sent.
    await vehicle.add_field("BatteryLevel", 30)
    results.append(
        check(
            "a request differing from the updated record is sent",
            len(vehicle.sent) == 1
            and vehicle.sent[0]["fields"]["BatteryLevel"] == {"interval_seconds": 30},
            f"sent {vehicle.sent}",
        )
    )

    # A malformed/partial config event never corrupts the record.
    handler = CaptureWarnings()
    logger = logging.getLogger("teslemetry_stream")
    logger.addHandler(handler)
    try:
        vehicle, stream = make_vehicle()
        assert stream.config_listener is not None
        stream.config_listener(
            {
                "vin": VIN,
                "config": {
                    "fields": {"BatteryLevel": {}},
                    "prefer_typed": False,
                },
            }
        )
        good_fields, good_typed = dict(vehicle.fields), vehicle.preferTyped

        # A non-dict "config" body is entirely rejected and logged.
        stream.config_listener({"vin": VIN, "config": "not-a-dict"})
        results.append(
            check(
                "a non-dict config event is ignored, logged, and keeps last-good",
                vehicle.fields == good_fields
                and vehicle.preferTyped == good_typed
                and any("malformed" in m.lower() for m in handler.messages),
                f"fields {vehicle.fields}, warnings {handler.messages}",
            )
        )

        # A partially malformed body applies the well-typed piece and keeps
        # the last-good value for the malformed piece.
        handler.messages.clear()
        stream.config_listener(
            {"vin": VIN, "config": {"fields": "not-a-dict", "prefer_typed": True}}
        )
        results.append(
            check(
                "a partial config event applies the good field, keeps the bad one",
                vehicle.fields == good_fields
                and vehicle.preferTyped is True
                and any("malformed" in m.lower() for m in handler.messages),
                f"fields {vehicle.fields}, prefer_typed {vehicle.preferTyped}, "
                f"warnings {handler.messages}",
            )
        )

        # A config event missing a key entirely leaves that piece untouched.
        handler.messages.clear()
        stream.config_listener(
            {"vin": VIN, "config": {"fields": {"CarType": {}}}}
        )
        results.append(
            check(
                "a config event omitting prefer_typed leaves it unchanged",
                vehicle.fields == {"CarType": {}} and vehicle.preferTyped is True,
                f"fields {vehicle.fields}, prefer_typed {vehicle.preferTyped}",
            )
        )

        # A field entry that isn't itself a dict (e.g. null) is malformed
        # shape too, even though the outer "fields" value is a dict - the
        # whole "fields" piece is rejected, not just the bad entry, so it
        # can't leave a null in self.fields that later crashes add_field.
        good_fields = dict(vehicle.fields)
        handler.messages.clear()
        stream.config_listener(
            {
                "vin": VIN,
                "config": {"fields": {"CarType": {}, "BatteryLevel": None}},
            }
        )
        results.append(
            check(
                "a null nested field entry rejects the whole fields piece",
                vehicle.fields == good_fields
                and any("malformed" in m.lower() for m in handler.messages),
                f"fields {vehicle.fields}, warnings {handler.messages}",
            )
        )

        # And, concretely, a later add_field for an unrelated field must not
        # raise trying to .get() off the (rejected, never-stored) null entry.
        try:
            await vehicle.add_field("BatteryLevel", 60)
            add_field_ok = True
        except AttributeError as error:
            add_field_ok = False
            add_field_error = repr(error)
        results.append(
            check(
                "add_field after a rejected null entry does not raise",
                add_field_ok,
                "" if add_field_ok else add_field_error,
            )
        )
    finally:
        logger.removeHandler(handler)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
