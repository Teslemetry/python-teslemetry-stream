"""Energy site class for handling streaming live_status and site_info updates."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable

from .const import EnergyHistoryTotals, Key, ProductType, RefreshTopic

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

    def __init__(self, stream: TeslemetryStream, site_id: str):
        self.stream = stream
        self.site_id = str(site_id)

    def listen_LiveStatus(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Listen for energy site live status.

        The callback receives the full live_status document. On connect (and
        whenever a snapshot exists), an initial event is delivered with
        `isCache` set, matching the same snapshot-then-live semantics as
        vehicle state.
        """
        return self.stream.async_add_listener(
            lambda x: callback(x[Key.LIVE_STATUS]),
            {Key.SITE_ID: self.site_id, Key.LIVE_STATUS: None},
        )

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
        return self.stream.async_add_listener(
            lambda x: callback(x[Key.SITE_INFO]),
            {Key.SITE_ID: self.site_id, Key.SITE_INFO: None},
        )

    def listen_TariffContentV2(
        self, callback: Callable[[dict[str, Any] | None], None]
    ) -> Callable[[], None]:
        """Listen for the site's V2 tariff document.

        The callback receives the `tariff_content_v2` document verbatim, or
        `None` when the server sends an explicit removal signal (the
        site's V2 tariff was cleared). Published only when it changes -
        silence means no change, never staleness, matching `listen_SiteInfo`.
        """
        return self.stream.async_add_listener(
            lambda x: callback(x[Key.TARIFF_CONTENT_V2]),
            {Key.SITE_ID: self.site_id, Key.TARIFF_CONTENT_V2: None},
        )

    def listen_ComposedSiteInfo(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Listen for a view composing the two streamed site_info pieces.

        Merges the latest slim `site_info` with the last known
        `tariff_content_v2` piece under a `tariff_content_v2` key, so
        consumers don't have to hand-assemble the two separate listeners
        themselves. This only ever carries what the stream itself carries -
        slim `site_info` plus the V2 tariff - never the legacy V1
        `tariff_content`, which has no SSE topic and stays REST-only by
        design; a consumer needing V1 must fetch the REST site_info
        endpoint directly. Fires whenever either half updates; nothing is
        emitted until the first `site_info` document has arrived.
        `tariff_content_v2` is `None` until a value has been received, and
        again after an explicit removal.
        """
        state: dict[str, Any] = {"site_info": None, "tariff_content_v2": None}

        def emit() -> None:
            if state["site_info"] is None:
                return
            callback({**state["site_info"], Key.TARIFF_CONTENT_V2: state["tariff_content_v2"]})

        def on_site_info(site_info: dict[str, Any]) -> None:
            state["site_info"] = site_info
            emit()

        def on_tariff(tariff_content_v2: dict[str, Any] | None) -> None:
            state["tariff_content_v2"] = tariff_content_v2
            emit()

        remove_site_info = self.listen_SiteInfo(on_site_info)
        remove_tariff = self.listen_TariffContentV2(on_tariff)

        def remove_listener() -> None:
            remove_site_info()
            remove_tariff()

        return remove_listener

    def listen_EnergyTotals(
        self, callback: Callable[[EnergyHistoryTotals], None]
    ) -> Callable[[], None]:
        """Listen for energy_totals refresh notifications.

        Unlike live_status/site_info, this event carries no full document -
        just cumulative totals and the event fires only when the server's
        5-minute poll actually detects a change. Silence means no change,
        never staleness; there is no snapshot-on-connect delivery. A
        consumer wanting the full time series must GET the event's `url`
        via their own REST client - this listener only exposes the totals.
        """
        return self.stream.async_add_listener(
            lambda x: callback(EnergyHistoryTotals.from_dict(x[Key.TOTALS])),
            {
                Key.ID: self.site_id,
                Key.PRODUCT_TYPE: ProductType.ENERGY_SITE,
                Key.TOPIC: RefreshTopic.ENERGY_TOTALS,
            },
        )
