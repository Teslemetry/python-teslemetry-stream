"""Checks energy site listener filtering against PR 310/316's SSE event shapes.

Fixtures mirror the `liveStatusSchema`/`siteInfoSchema` from Teslemetry/api
PR 310: a flat envelope of `createdAt`, `site_id`, optional `isCache`, and
the full document under `live_status`/`site_info` (opaque, not a delta).
`energy_totals` fixtures mirror the api's `energyTotalsNotification` shape:
`id`/`date`/`createdAt`/`totals`, with `isCache` present only when true - no
`site_id`, `product_type`, `topic`, or `url` keys.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from teslemetry_stream.const import EnergyHistoryTotals, EnergyTotalsEvent
from teslemetry_stream.stream import TeslemetryStream, recursive_match

SITE_A = "12345"
SITE_B = "67890"

LIVE_STATUS_SNAPSHOT: dict[str, Any] = {
    "createdAt": "2026-07-28T10:15:30.000Z",
    "site_id": SITE_A,
    "isCache": True,
    "live_status": {
        "battery_power": 1200,
        "load_power": 900,
        "grid_power": -300,
        "solar_power": 2400,
        "percentage_charged": 82.5,
    },
}

LIVE_STATUS_LIVE: dict[str, Any] = {
    "createdAt": "2026-07-28T10:16:00.000Z",
    "site_id": SITE_A,
    "live_status": {
        "battery_power": 1100,
        "load_power": 950,
        "grid_power": -150,
        "solar_power": 2200,
        "percentage_charged": 82.6,
    },
}

SITE_INFO_SNAPSHOT: dict[str, Any] = {
    "createdAt": "2026-07-28T10:15:30.000Z",
    "site_id": SITE_A,
    "isCache": True,
    "site_info": {
        "site_name": "Home",
        "backup_reserve_percent": 20,
        "default_real_mode": "self_consumption",
    },
}

LIVE_STATUS_NUMERIC_ID: dict[str, Any] = {
    **LIVE_STATUS_LIVE,
    "site_id": int(SITE_A),
}

SITE_INFO_NUMERIC_ID: dict[str, Any] = {
    **SITE_INFO_SNAPSHOT,
    "site_id": int(SITE_A),
}

TARIFF_CONTENT_V2_EVENT: dict[str, Any] = {
    "createdAt": "2026-07-28T10:16:00.000Z",
    "site_id": SITE_A,
    "tariff_content_v2": {"code": "TOU-1"},
}

TARIFF_CONTENT_V2_NUMERIC_ID: dict[str, Any] = {
    **TARIFF_CONTENT_V2_EVENT,
    "site_id": int(SITE_A),
}

OTHER_SITE_LIVE_STATUS: dict[str, Any] = {
    "createdAt": "2026-07-28T10:16:00.000Z",
    "site_id": SITE_B,
    "live_status": {"battery_power": 0},
}

ENERGY_TOTALS_FIXTURE: dict[str, float | None] = {
    "solar_energy_exported": 12.3,
    "generator_energy_exported": None,
    "grid_energy_imported": 4.5,
    "grid_services_energy_imported": None,
    "grid_services_energy_exported": None,
    "grid_energy_exported_from_solar": None,
    "grid_energy_exported_from_generator": None,
    "grid_energy_exported_from_battery": None,
    "battery_energy_exported": 1.1,
    "battery_energy_imported_from_grid": None,
    "battery_energy_imported_from_solar": None,
    "battery_energy_imported_from_generator": None,
    "consumer_energy_imported_from_grid": None,
    "consumer_energy_imported_from_solar": None,
    "consumer_energy_imported_from_battery": None,
    "consumer_energy_imported_from_generator": None,
    "total_home_usage": 20.0,
    "total_battery_charge": None,
    "total_battery_discharge": None,
    "total_solar_generation": 12.3,
    "total_grid_energy_exported": None,
}

ENERGY_TOTALS_EVENT: dict[str, Any] = {
    "id": SITE_A,
    "date": "2026-07-29",
    "createdAt": "2026-07-29T10:16:00.000Z",
    "totals": ENERGY_TOTALS_FIXTURE,
}

ENERGY_TOTALS_SNAPSHOT: dict[str, Any] = {
    **ENERGY_TOTALS_EVENT,
    "isCache": True,
}

OTHER_SITE_ENERGY_TOTALS: dict[str, Any] = {
    **ENERGY_TOTALS_EVENT,
    "id": SITE_B,
}

ENERGY_TOTALS_NUMERIC_ID: dict[str, Any] = {
    **ENERGY_TOTALS_EVENT,
    "id": int(SITE_A),
}

CREDITS_EVENT: dict[str, Any] = {
    "credits": {"type": "snapshot", "cost": 0, "name": "snapshot", "balance": 5, "quota": {}},
    "createdAt": "2026-07-28T10:16:00.000Z",
    "isCache": True,
}


def make_stream() -> TeslemetryStream:
    """Build a stream that never actually connects."""
    return TeslemetryStream(session=None, access_token="test-token", manual=True)  # type: ignore[arg-type]


def dispatch(stream: TeslemetryStream, event: dict[str, Any]) -> None:
    """Replicate stream.listen()'s per-event dispatch without a live connection."""
    for listener, filters, _internal in list(stream._listeners.values()):
        if recursive_match(filters, event):
            listener(event)


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<64} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def main() -> None:
    results = []

    # listen_LiveStatus receives the unwrapped live_status document, snapshot and live alike.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received: list[dict[str, Any]] = []
    site.listen_LiveStatus(received.append)
    dispatch(stream, LIVE_STATUS_SNAPSHOT)
    dispatch(stream, LIVE_STATUS_LIVE)
    results.append(
        check(
            "listen_LiveStatus unwraps the live_status document",
            received == [LIVE_STATUS_SNAPSHOT["live_status"], LIVE_STATUS_LIVE["live_status"]],
            f"got {received}",
        )
    )

    # listen_SiteInfo receives the unwrapped site_info document.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_SiteInfo(received.append)
    dispatch(stream, SITE_INFO_SNAPSHOT)
    results.append(
        check(
            "listen_SiteInfo unwraps the site_info document",
            received == [SITE_INFO_SNAPSHOT["site_info"]],
            f"got {received}",
        )
    )

    # A live_status event for another site is not delivered.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_LiveStatus(received.append)
    dispatch(stream, OTHER_SITE_LIVE_STATUS)
    results.append(
        check(
            "a different site's live_status is filtered out",
            received == [],
            f"got {received}",
        )
    )

    # A site_info listener does not receive live_status events for the same site.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_SiteInfo(received.append)
    dispatch(stream, LIVE_STATUS_SNAPSHOT)
    results.append(
        check(
            "listen_SiteInfo ignores live_status events",
            received == [],
            f"got {received}",
        )
    )

    # listen_EnergyTotals receives date, created_at and is_cache alongside the totals.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    totals_received: list[EnergyTotalsEvent] = []
    site.listen_EnergyTotals(totals_received.append)
    dispatch(stream, ENERGY_TOTALS_EVENT)
    results.append(
        check(
            "listen_EnergyTotals parses the totals dict",
            totals_received
            == [
                EnergyTotalsEvent(
                    date="2026-07-29",
                    created_at=datetime(2026, 7, 29, 10, 16, 0, tzinfo=timezone.utc),
                    is_cache=False,
                    totals=EnergyHistoryTotals(**ENERGY_TOTALS_FIXTURE),
                )
            ],
            f"got {totals_received}",
        )
    )

    # A connect-time snapshot carries is_cache=True; date is passed through unchanged.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    totals_received = []
    site.listen_EnergyTotals(totals_received.append)
    dispatch(stream, ENERGY_TOTALS_SNAPSHOT)
    results.append(
        check(
            "listen_EnergyTotals marks a connect-time snapshot with is_cache",
            len(totals_received) == 1
            and totals_received[0].is_cache is True
            and totals_received[0].date == "2026-07-29",
            f"got {totals_received}",
        )
    )

    # An energy_totals event for another site is not delivered.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    totals_received = []
    site.listen_EnergyTotals(totals_received.append)
    dispatch(stream, OTHER_SITE_ENERGY_TOTALS)
    results.append(
        check(
            "a different site's energy_totals is filtered out",
            totals_received == [],
            f"got {totals_received}",
        )
    )

    # listen_LiveStatus does not receive energy_totals events.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_LiveStatus(received.append)
    dispatch(stream, ENERGY_TOTALS_EVENT)
    results.append(
        check(
            "listen_LiveStatus ignores energy_totals events",
            received == [],
            f"got {received}",
        )
    )

    # Unrelated account-wide events (e.g. credits) are not delivered to energy listeners.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    live_received: list[dict[str, Any]] = []
    info_received: list[dict[str, Any]] = []
    site.listen_LiveStatus(live_received.append)
    site.listen_SiteInfo(info_received.append)
    dispatch(stream, CREDITS_EVENT)
    results.append(
        check(
            "credits events are not delivered to energy site listeners",
            live_received == [] and info_received == [],
            f"live={live_received} info={info_received}",
        )
    )

    # Removing a listener stops further delivery.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    remove = site.listen_LiveStatus(received.append)
    dispatch(stream, LIVE_STATUS_SNAPSHOT)
    remove()
    dispatch(stream, LIVE_STATUS_LIVE)
    results.append(
        check(
            "removing a listener stops further delivery",
            received == [LIVE_STATUS_SNAPSHOT["live_status"]],
            f"got {received}",
        )
    )

    # A numeric site_id (e.g. from a command-patch event) still matches str-typed listeners.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_LiveStatus(received.append)
    dispatch(stream, LIVE_STATUS_NUMERIC_ID)
    results.append(
        check(
            "listen_LiveStatus matches a numeric site_id",
            received == [LIVE_STATUS_NUMERIC_ID["live_status"]],
            f"got {received}",
        )
    )

    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_SiteInfo(received.append)
    dispatch(stream, SITE_INFO_NUMERIC_ID)
    results.append(
        check(
            "listen_SiteInfo matches a numeric site_id",
            received == [SITE_INFO_NUMERIC_ID["site_info"]],
            f"got {received}",
        )
    )

    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    tariff_received: list[dict[str, Any] | None] = []
    site.listen_TariffContentV2(tariff_received.append)
    dispatch(stream, TARIFF_CONTENT_V2_NUMERIC_ID)
    results.append(
        check(
            "listen_TariffContentV2 matches a numeric site_id",
            tariff_received == [TARIFF_CONTENT_V2_NUMERIC_ID["tariff_content_v2"]],
            f"got {tariff_received}",
        )
    )

    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    totals_received = []
    site.listen_EnergyTotals(totals_received.append)
    dispatch(stream, ENERGY_TOTALS_NUMERIC_ID)
    results.append(
        check(
            "listen_EnergyTotals matches a numeric id",
            totals_received
            == [
                EnergyTotalsEvent(
                    date="2026-07-29",
                    created_at=datetime(2026, 7, 29, 10, 16, 0, tzinfo=timezone.utc),
                    is_cache=False,
                    totals=EnergyHistoryTotals(**ENERGY_TOTALS_FIXTURE),
                )
            ],
            f"got {totals_received}",
        )
    )

    # A mismatched id (numeric or not) is still filtered out.
    stream = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_LiveStatus(received.append)
    dispatch(stream, {**LIVE_STATUS_NUMERIC_ID, "site_id": int(SITE_B)})
    results.append(
        check(
            "listen_LiveStatus still filters a mismatched numeric site_id",
            received == [],
            f"got {received}",
        )
    )

    # get_energysite is idempotent per id, mirroring get_vehicle.
    stream = make_stream()
    results.append(
        check(
            "get_energysite returns the same instance for the same id",
            stream.get_energysite(SITE_A) is stream.get_energysite(SITE_A),
        )
    )
    results.append(
        check(
            "get_energysite normalizes int and str ids to the same instance",
            stream.get_energysite(12345) is stream.get_energysite("12345"),
        )
    )

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
