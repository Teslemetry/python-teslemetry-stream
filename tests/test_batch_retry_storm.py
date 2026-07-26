"""Regression test for the config-write retry storm.

At integration setup, every streaming listener schedules its own
``add_field`` task. Before the single-flight fix, a deterministic upstream
rejection left the merged pending config in place, so every already-scheduled
listener task replayed the identical PATCH serially - one full write per
listener. This asserts the batch collapses to exactly one upstream call, and
that a later explicit trigger (not the same batch) still gets to retry.
"""
from __future__ import annotations

import asyncio
from typing import Any

from teslemetry_stream.vehicle import TeslemetryStreamVehicle

VIN = "TESTVIN0000000001"

ACCEPTED: dict[str, Any] = {"updated_vehicles": 1}
FAILED: dict[str, Any] = {"response": None, "error": "upstream internal error"}


class FakeStream:
    """Minimal stand-in for TeslemetryStream."""

    manual = True


def make_vehicle(vin: str, responses: list[Any]) -> TeslemetryStreamVehicle:
    """Build a vehicle that records payloads and replays canned responses."""
    vehicle = TeslemetryStreamVehicle(FakeStream(), vin)  # type: ignore[arg-type]
    vehicle.sent = []  # type: ignore[attr-defined]

    async def patch_config(config: dict[str, Any]) -> dict[str, Any]:
        vehicle.sent.append(dict(config))  # type: ignore[attr-defined]
        return responses.pop(0) if responses else ACCEPTED

    vehicle.patch_config = patch_config  # type: ignore[assignment,method-assign]
    return vehicle


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<68} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


async def main() -> None:
    results = []

    # 80 listener tasks race to add distinct fields at setup time, exactly as
    # HA's async_setup_stream fans out one add_field task per streaming
    # entity. Upstream deterministically rejects every write for this VIN
    # (Tesla's per-VIN write latch), so a canned response is queued for each
    # possible replay to prove the fix - not just the buggy code's first one.
    responses: list[Any] = [FAILED] * 100
    vehicle = make_vehicle(VIN, responses)
    fields = [f"Field{i}" for i in range(80)]
    await asyncio.wait_for(
        asyncio.gather(*(vehicle.add_field(f) for f in fields)), timeout=5
    )

    results.append(
        check(
            "a failed batch produces exactly one upstream PATCH",
            len(vehicle.sent) == 1,  # type: ignore[attr-defined]
            f"sent {len(vehicle.sent)} PATCH(es)",  # type: ignore[attr-defined]
        )
    )
    results.append(
        check(
            "the single PATCH carries every listener's requested field",
            set(vehicle.sent[0]["fields"]) == set(fields),  # type: ignore[attr-defined]
            f"fields sent {sorted(vehicle.sent[0]['fields'])}",  # type: ignore[attr-defined]
        )
    )
    results.append(
        check(
            "no field is recorded as configured after a terminal failure",
            vehicle.fields == {},
            f"fields {sorted(vehicle.fields)}",
        )
    )
    results.append(
        check(
            "desired state survives the terminal failure for a later retry",
            set(vehicle._config.get("fields", {})) == set(fields),
            f"pending {sorted(vehicle._config.get('fields', {}))}",
        )
    )

    # A later explicit trigger (e.g. a new listener) gets its own single
    # attempt carrying the still-pending fields, not a fresh replay storm.
    # Upstream has since recovered.
    responses.clear()
    responses.append(ACCEPTED)
    await vehicle.add_field("LaterField")

    results.append(
        check(
            "a later explicit trigger performs exactly one more PATCH",
            len(vehicle.sent) == 2,  # type: ignore[attr-defined]
            f"sent {len(vehicle.sent)} PATCH(es) total",  # type: ignore[attr-defined]
        )
    )
    results.append(
        check(
            "the later PATCH carries the still-pending fields plus the new one",
            set(vehicle.sent[1]["fields"])  # type: ignore[attr-defined]
            == set(fields) | {"LaterField"},
            f"fields sent {sorted(vehicle.sent[1]['fields'])}",  # type: ignore[attr-defined]
        )
    )
    results.append(
        check(
            "recovery is recorded once upstream accepts the retry",
            all(f in vehicle.fields for f in fields) and "LaterField" in vehicle.fields,
            f"fields {sorted(vehicle.fields)}",
        )
    )

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
