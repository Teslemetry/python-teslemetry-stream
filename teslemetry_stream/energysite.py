"""Energy site class for handling streaming live_status and site_info updates."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .const import EnergyTotalsEvent, Key

if TYPE_CHECKING:
    from .stream import TeslemetryStream
else:
    TeslemetryStream = None


class TeslemetryStreamEnergySite:
    """Handle streaming energy site updates.

    Unlike vehicle signals, energy `live_status` and `site_info` events are
    full documents rather than field deltas, and there is no per-field
    config to enable - the server auto-polls subscribed sites - so listeners
    here just filter and unwrap the matching topic.
    """

    def __init__(self, stream: TeslemetryStream, site_id: int):
        self.stream = stream
        self.site_id = site_id

    def listen_LiveStatus(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Listen for energy site live status.

        The callback receives the full live_status document. On connect (and
        whenever a snapshot exists), an initial event is delivered with
        `isCache` set, matching the same snapshot-then-live semantics as
        vehicle state.
        """
        def _handler(x: dict[str, Any]) -> None:
            if int(x[Key.SITE_ID]) == self.site_id:
                callback(x[Key.LIVE_STATUS])

        return self.stream.async_add_listener(_handler, {Key.LIVE_STATUS: None})

    def listen_SiteInfo(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Listen for energy site info.

        The callback receives the site_info document. This document no
        longer carries `tariff_content`/`tariff_content_v2` - subscribe to
        `listen_TariffContentV2` for the V2 tariff, or use the REST
        site_info endpoint for the full Tesla-shaped document including
        both tariffs. On connect (and whenever a snapshot exists), an
        initial event is delivered with `isCache` set, matching the same
        snapshot-then-live semantics as vehicle state.
        """
        def _handler(x: dict[str, Any]) -> None:
            if int(x[Key.SITE_ID]) == self.site_id:
                callback(x[Key.SITE_INFO])

        return self.stream.async_add_listener(_handler, {Key.SITE_INFO: None})

    def listen_TariffContentV2(
        self, callback: Callable[[dict[str, Any] | None], None]
    ) -> Callable[[], None]:
        """Listen for the site's V2 tariff document.

        The callback receives the `tariff_content_v2` document verbatim, or
        `None` when the server sends an explicit removal signal (the
        site's V2 tariff was cleared). Published only when it changes -
        silence means no change, never staleness, matching `listen_SiteInfo`.
        """
        def _handler(x: dict[str, Any]) -> None:
            if int(x[Key.SITE_ID]) == self.site_id:
                callback(x[Key.TARIFF_CONTENT_V2])

        return self.stream.async_add_listener(_handler, {Key.TARIFF_CONTENT_V2: None})

    def listen_EnergyTotals(
        self, callback: Callable[[EnergyTotalsEvent], None]
    ) -> Callable[[], None]:
        """Listen for energy_totals refresh notifications.

        Unlike live_status/site_info, this event carries no full document -
        just cumulative totals. The server delivers a connect-time snapshot
        (`is_cache: True`) and otherwise fires only when its periodic poll
        detects a change; silence between events means no change, never
        staleness. The callback receives an `EnergyTotalsEvent` carrying
        `date` (the site-local day the totals belong to, verbatim),
        `created_at`, `is_cache` and the `totals` themselves - a caller
        deriving Home Assistant's `last_reset` needs `date`, not its own
        clock, since the server finalises a day's rollover after local
        midnight.

        Breaking change: previously delivered the bare `EnergyHistoryTotals`
        as the callback argument; now delivers an `EnergyTotalsEvent`
        wrapping it under `.totals`.
        """
        def _handler(x: dict[str, Any]) -> None:
            if int(x[Key.ID]) == self.site_id:
                callback(EnergyTotalsEvent.from_dict(x))

        return self.stream.async_add_listener(_handler, {Key.TOTALS: None})
