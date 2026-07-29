"""Checks the api PR 318/319 SSE protocol additions: the `topics` allowlist
query parameter, the `tariff_content_v2` topic (including null-as-removal),
and the composed site_info+tariff helper.

Fixtures mirror the authoritative schemas in Teslemetry/api:
- `src/lib/sseTopics.ts` for the exact wire topic names and `topics` being
  an additive, omission-preserves-legacy-behavior query parameter.
- `src/routes/sse/tariffContentV2Schema.ts` for the tariff_content_v2 event
  shape (`createdAt`/`site_id`/`isCache?`/`tariff_content_v2`, the last
  nullable to signal removal).
- `src/routes/sse/siteInfoSchema.ts` for the now-slim `site_info` event
  (never carries `tariff_content`/`tariff_content_v2`).
"""
from __future__ import annotations

import asyncio
from typing import Any

from teslemetry_stream.const import SseTopic
from teslemetry_stream.stream import TeslemetryStream, recursive_match

SITE_A = "12345"

SITE_INFO_SNAPSHOT: dict[str, Any] = {
    "createdAt": "2026-07-29T10:15:30.000Z",
    "site_id": SITE_A,
    "isCache": True,
    "site_info": {
        "site_name": "Home",
        "backup_reserve_percent": 20,
        "default_real_mode": "self_consumption",
    },
}

SITE_INFO_UPDATE: dict[str, Any] = {
    "createdAt": "2026-07-29T10:16:00.000Z",
    "site_id": SITE_A,
    "site_info": {
        "site_name": "Home",
        "backup_reserve_percent": 25,
        "default_real_mode": "self_consumption",
    },
}

TARIFF_SNAPSHOT: dict[str, Any] = {
    "createdAt": "2026-07-29T10:15:30.000Z",
    "site_id": SITE_A,
    "isCache": True,
    "tariff_content_v2": {"code": "PLAN-1", "utility": "Acme Power"},
}

TARIFF_REMOVED: dict[str, Any] = {
    "createdAt": "2026-07-29T10:17:00.000Z",
    "site_id": SITE_A,
    "tariff_content_v2": None,
}


class FakeResponse:
    """Minimal stand-in for the aiohttp response `connect()` awaits."""

    def __init__(self) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200


class FakeSession:
    """Captures the kwargs `connect()` passes to `session.get`."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeResponse()


def make_stream(topics: Any = None) -> tuple[TeslemetryStream, FakeSession]:
    session = FakeSession()
    stream = TeslemetryStream(
        session=session,  # type: ignore[arg-type]
        access_token="test-token",
        server="api.teslemetry.com",
        manual=True,
        topics=topics,
    )
    return stream, session


def dispatch(stream: TeslemetryStream, event: dict[str, Any]) -> None:
    """Replicate stream.listen()'s per-event dispatch without a live connection."""
    for listener, filters in list(stream._listeners.values()):
        if recursive_match(filters, event):
            listener(event)


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<64} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def main() -> None:
    results = []

    # Omitting topics preserves legacy behavior: no topics param sent at all.
    stream, session = make_stream(topics=None)
    asyncio.run(stream.connect())
    results.append(
        check(
            "omitted topics sends no topics query param",
            session.calls[0]["params"] is None,
            f"got {session.calls[0]['params']}",
        )
    )

    # Passing topics builds the exact comma-separated allowlist param.
    stream, session = make_stream(topics=[SseTopic.LIVE_STATUS, SseTopic.SITE_INFO])
    asyncio.run(stream.connect())
    results.append(
        check(
            "topics builds a comma-separated params entry",
            session.calls[0]["params"] == {"topics": "live_status,site_info"},
            f"got {session.calls[0]['params']}",
        )
    )

    # Plain strings work too, not just SseTopic members.
    stream, session = make_stream(topics=["state", "config"])
    asyncio.run(stream.connect())
    results.append(
        check(
            "plain string topics are accepted",
            session.calls[0]["params"] == {"topics": "state,config"},
            f"got {session.calls[0]['params']}",
        )
    )

    # An explicitly empty topics iterable is rejected, not treated as legacy-all.
    raised = False
    try:
        make_stream(topics=[])
    except ValueError:
        raised = True
    results.append(
        check(
            "an empty topics iterable raises ValueError instead of silently enabling legacy-all",
            raised,
        )
    )

    # listen_TariffContentV2 receives the tariff document verbatim.
    stream, _ = make_stream()
    site = stream.get_energysite(SITE_A)
    received: list[dict[str, Any] | None] = []
    site.listen_TariffContentV2(received.append)
    dispatch(stream, TARIFF_SNAPSHOT)
    results.append(
        check(
            "listen_TariffContentV2 receives the tariff document",
            received == [TARIFF_SNAPSHOT["tariff_content_v2"]],
            f"got {received}",
        )
    )

    # A null tariff_content_v2 body is delivered as None - the removal signal.
    stream, _ = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_TariffContentV2(received.append)
    dispatch(stream, TARIFF_SNAPSHOT)
    dispatch(stream, TARIFF_REMOVED)
    results.append(
        check(
            "a null tariff_content_v2 body surfaces as None (removal)",
            received == [TARIFF_SNAPSHOT["tariff_content_v2"], None],
            f"got {received}",
        )
    )

    # listen_SiteInfo keeps working against the slim shape and ignores tariff events.
    stream, _ = make_stream()
    site = stream.get_energysite(SITE_A)
    received = []
    site.listen_SiteInfo(received.append)
    dispatch(stream, SITE_INFO_SNAPSHOT)
    dispatch(stream, TARIFF_SNAPSHOT)
    results.append(
        check(
            "listen_SiteInfo ignores tariff_content_v2 events",
            received == [SITE_INFO_SNAPSHOT["site_info"]],
            f"got {received}",
        )
    )

    # listen_ComposedSiteInfo merges the latest site_info with the last tariff piece.
    stream, _ = make_stream()
    site = stream.get_energysite(SITE_A)
    composed: list[dict[str, Any]] = []
    site.listen_ComposedSiteInfo(composed.append)
    dispatch(stream, SITE_INFO_SNAPSHOT)
    results.append(
        check(
            "composed view emits site_info alone with tariff_content_v2=None first",
            composed == [{**SITE_INFO_SNAPSHOT["site_info"], "tariff_content_v2": None}],
            f"got {composed}",
        )
    )

    dispatch(stream, TARIFF_SNAPSHOT)
    results.append(
        check(
            "composed view merges in the tariff once it arrives",
            composed[-1]
            == {**SITE_INFO_SNAPSHOT["site_info"], "tariff_content_v2": TARIFF_SNAPSHOT["tariff_content_v2"]},
            f"got {composed[-1]}",
        )
    )

    dispatch(stream, SITE_INFO_UPDATE)
    results.append(
        check(
            "composed view keeps the last tariff when only site_info updates",
            composed[-1]
            == {**SITE_INFO_UPDATE["site_info"], "tariff_content_v2": TARIFF_SNAPSHOT["tariff_content_v2"]},
            f"got {composed[-1]}",
        )
    )

    dispatch(stream, TARIFF_REMOVED)
    results.append(
        check(
            "composed view reflects an explicit tariff removal as None",
            composed[-1] == {**SITE_INFO_UPDATE["site_info"], "tariff_content_v2": None},
            f"got {composed[-1]}",
        )
    )

    # Nothing is emitted before the first site_info document arrives.
    stream, _ = make_stream()
    site = stream.get_energysite(SITE_A)
    composed = []
    site.listen_ComposedSiteInfo(composed.append)
    dispatch(stream, TARIFF_SNAPSHOT)
    results.append(
        check(
            "composed view withholds emission until site_info has arrived",
            composed == [],
            f"got {composed}",
        )
    )

    # Removing the composed listener removes both underlying listeners.
    stream, _ = make_stream()
    site = stream.get_energysite(SITE_A)
    composed = []
    remove = site.listen_ComposedSiteInfo(composed.append)
    dispatch(stream, SITE_INFO_SNAPSHOT)
    remove()
    dispatch(stream, TARIFF_SNAPSHOT)
    dispatch(stream, SITE_INFO_UPDATE)
    results.append(
        check(
            "removing the composed listener stops delivery from either half",
            len(composed) == 1,
            f"got {composed}",
        )
    )

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
