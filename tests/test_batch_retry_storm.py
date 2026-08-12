"""Regression test for the config-write retry storm.

At integration setup, every streaming listener schedules its own
``add_field`` task. Before the single-flight fix, a deterministic upstream
rejection left the merged pending config in place, so every already-scheduled
listener task replayed the identical PATCH serially - one full write per
listener. This asserts the batch collapses to exactly one upstream call, and
that a later explicit trigger (not the same batch) still gets to retry.

It also covers a follow-on defect in the single-flight fix itself: a waiter
is joined to the shared flush with a plain ``await``, so cancelling (or
timing out) one caller propagates into the shared task and cancels the
flush out from under every other waiter, leaving the coalesced config
unapplied. Waiters must join the flush shielded from their own cancellation.
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

    def async_add_listener(
        self, callback: Any, filters: dict[str, Any] | None = None, internal: bool = False
    ) -> Any:
        return lambda: None

    def async_add_connection_listener(self, callback: Any) -> Any:
        return lambda: None


def make_vehicle(vin: str, responses: list[Any]) -> TeslemetryStreamVehicle:
    """Build a vehicle that records payloads and replays canned responses."""
    vehicle = TeslemetryStreamVehicle(FakeStream(), vin)  # type: ignore[arg-type]
    # These tests exercise the write path, not the lazy-populate fetch (the
    # fake stream has no REST session to serve one) - mark it populated like
    # a real connection's config snapshot already would have.
    vehicle._populated = True
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

    # A batch of concurrent callers joins one shared flush. Cancelling one of
    # them mid-flight (here, during the debounce sleep, before the PATCH is
    # even sent) must not cancel the flush out from under the others.
    vehicle = make_vehicle(VIN, [ACCEPTED])
    cancel_fields = [f"CancelField{i}" for i in range(5)]
    tasks = [asyncio.ensure_future(vehicle.add_field(f)) for f in cancel_fields]
    await asyncio.sleep(0.05)  # let every caller merge in and join the flush
    cancelled_task = tasks[2]
    cancelled_task.cancel()

    cancelled_raised = False
    try:
        await cancelled_task
    except asyncio.CancelledError:
        cancelled_raised = True

    remaining = [t for t in tasks if t is not cancelled_task]
    await asyncio.wait_for(asyncio.gather(*remaining), timeout=5)

    results.append(
        check(
            "the cancelled caller itself observes CancelledError",
            cancelled_raised,
        )
    )
    results.append(
        check(
            "cancelling one waiter does not abort the shared flush",
            len(vehicle.sent) == 1,  # type: ignore[attr-defined]
            f"sent {len(vehicle.sent)} PATCH(es)",  # type: ignore[attr-defined]
        )
    )
    results.append(
        check(
            "the other concurrent callers still complete with the applied config",
            all(f in vehicle.fields for f in cancel_fields),
            f"fields {sorted(vehicle.fields)}",
        )
    )

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
