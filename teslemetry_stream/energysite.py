"""Energy site class for handling streaming live_status and site_info updates."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable

from .const import Key

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

        The callback receives the full site_info document. On connect (and
        whenever a snapshot exists), an initial event is delivered with
        `isCache` set, matching the same snapshot-then-live semantics as
        vehicle state.
        """
        return self.stream.async_add_listener(
            lambda x: callback(x[Key.SITE_INFO]),
            {Key.SITE_ID: self.site_id, Key.SITE_INFO: None},
        )
