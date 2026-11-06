"""Tests for the per-vehicle alert tracker (`alerts`, `listen_AlertChanges`).

Each alerts event carries the vehicle's window of recent alerts, newest first,
ended ones included, and the same window is resent unchanged - including as
the snapshot replayed with ``isCache`` on every (re)connect. What is asserted:

- the first batch seeds `alerts` without calling back;
- a later batch calls back "started" for an alert not seen before and "ended"
  for a known active alert that now carries ``endedAt``, and nothing for a
  resent batch;
- a reconnect's replayed snapshot produces no duplicates, but reports what
  started or ended while disconnected;
- a stale copy of an ended alert (no ``endedAt``) never revives it;
- `alerts` is the latest batch, so an alert the vehicle drops off its window
  leaves it, ended or not;
- an unseen alert behind one already seen is kept as history, not
  reported as a start, and newness follows batch position even when the
  vehicle's clock has skewed ``startedAt``.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from teslemetry_stream.stream import TeslemetryStream

VIN = "TESTVIN0000000001"


def alert(name: str, started: str, ended: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": name,
        "audiences": ["Customer"],
        "startedAt": f"2026-11-06T{started}.000Z",
    }
    if ended:
        value["endedAt"] = f"2026-11-06T{ended}.000Z"
    return value


def batch(*alerts: dict[str, Any], cache: bool = False) -> dict[str, Any]:
    event: dict[str, Any] = {
        "vin": VIN,
        "createdAt": "2026-11-06T12:00:00.000Z",
        "alerts": list(alerts),
    }
    if cache:
        event["isCache"] = True
    return event


DOOR = alert("UI_a002_DoorOpen", "10:00:00", "10:00:05")
CABLE = alert("VCFRONT_a186_noDriveChgCableCon", "09:00:00")
CABLE_ENDED = alert("VCFRONT_a186_noDriveChgCableCon", "09:00:00", "11:00:00")
KEY = alert("VCSEC_a260_prsntPhoneKeyDisconnected", "11:30:00")
USB = alert("UI_a112_badUSBDevice", "11:40:00", "11:40:01")
# Seen on the wire: after a clock correction an alert can carry a startedAt
# later than its own endedAt, and later than an alert the vehicle sends after it.
WASHER = alert("VCFRONT_a361_washerFluidLowMomentary", "11:50:00", "11:48:00")
DASHCAM = alert("UI_a266_DashcamRecentBufferDurationReduced", "11:49:00")


class FakeEventContent:
    """Async-iterable response body yielding canned SSE lines, then ending
    (so the stream reconnects) or blocking forever."""

    def __init__(self, lines: list[bytes], end: bool) -> None:
        self._lines = list(lines)
        self._end = end
        self._blocker: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def __aiter__(self) -> FakeEventContent:
        return self

    async def __anext__(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        if self._end:
            raise StopAsyncIteration
        await self._blocker
        raise AssertionError("unreachable - blocker only resolves via cancellation")


class FakeResponse:
    def __init__(self, content: Any) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200
        self.content = content
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    """Serves one canned list of events per connection; all but the last end."""

    def __init__(self, connections: list[list[dict[str, Any]]]) -> None:
        self.connections = connections
        self.calls = 0

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        events = self.connections[min(self.calls, len(self.connections) - 1)]
        self.calls += 1
        lines = [f"data: {json.dumps(event)}\n".encode() for event in events]
        return FakeResponse(FakeEventContent(lines, end=self.calls < len(self.connections)))


def make_stream(session: Any = None, manual: bool = True) -> TeslemetryStream:
    return TeslemetryStream(
        session=session,
        access_token="test-token",
        server="api.teslemetry.com",
        manual=manual,
    )


def track(stream: TeslemetryStream) -> tuple[Any, list[tuple[str, str]]]:
    vehicle = stream.get_vehicle(VIN)
    changes: list[tuple[str, str]] = []
    vehicle.listen_AlertChanges(lambda change, a: changes.append((change, a["name"])))
    return vehicle, changes


async def wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0)
    return predicate()


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def test_first_batch_seeds_silently(results: list[bool]) -> None:
    stream = make_stream()
    vehicle, changes = track(stream)
    stream._dispatch(batch(DOOR, CABLE, cache=True))
    results.append(check("first batch calls back nothing", changes == [], f"got {changes}"))
    results.append(
        check(
            "first batch seeds alerts newest first",
            vehicle.alerts == [DOOR, CABLE],
            f"got {vehicle.alerts}",
        )
    )


def test_live_transitions(results: list[bool]) -> None:
    stream = make_stream()
    vehicle, changes = track(stream)
    stream._dispatch(batch(DOOR, CABLE, cache=True))

    stream._dispatch(batch(KEY, DOOR, CABLE))
    results.append(
        check("a new alert is started", changes == [("started", KEY["name"])], f"got {changes}")
    )

    changes.clear()
    stream._dispatch(batch(KEY, DOOR, CABLE))
    results.append(check("a resent batch calls back nothing", changes == [], f"got {changes}"))

    stream._dispatch(batch(KEY, DOOR, CABLE_ENDED))
    results.append(
        check(
            "a known active alert with endedAt is ended",
            changes == [("ended", CABLE["name"])],
            f"got {changes}",
        )
    )
    results.append(
        check(
            "the ended alert keeps its endedAt in alerts",
            vehicle.alerts == [KEY, DOOR, CABLE_ENDED],
            f"got {vehicle.alerts}",
        )
    )

    changes.clear()
    stream._dispatch(batch(USB, KEY, DOOR, CABLE_ENDED))
    results.append(
        check(
            "an alert started and ended between batches is both",
            changes == [("started", USB["name"]), ("ended", USB["name"])],
            f"got {changes}",
        )
    )


def test_stale_ended_alert_never_revives(results: list[bool]) -> None:
    stream = make_stream()
    vehicle, changes = track(stream)
    stream._dispatch(batch(DOOR, CABLE, cache=True))
    stream._dispatch(batch(DOOR, CABLE_ENDED))
    changes.clear()

    # e.g. a replayed snapshot older than what was already seen live
    stream._dispatch(batch(DOOR, CABLE, cache=True))
    results.append(check("a stale copy calls back nothing", changes == [], f"got {changes}"))
    results.append(
        check(
            "a stale copy leaves the alert ended",
            vehicle.alerts == [DOOR, CABLE_ENDED],
            f"got {vehicle.alerts}",
        )
    )


def test_unseen_history_is_not_a_start(results: list[bool]) -> None:
    stream = make_stream()
    vehicle, changes = track(stream)
    stream._dispatch(batch(KEY, cache=True))
    stream._dispatch(batch(KEY, DOOR, CABLE))
    results.append(
        check(
            "unseen alerts behind a seen one call back nothing", changes == [], f"got {changes}"
        )
    )
    results.append(
        check(
            "unseen older alerts are kept",
            vehicle.alerts == [KEY, DOOR, CABLE],
            f"got {vehicle.alerts}",
        )
    )


def test_skewed_clock(results: list[bool]) -> None:
    stream = make_stream()
    vehicle, changes = track(stream)
    stream._dispatch(batch(WASHER, KEY, cache=True))
    stream._dispatch(batch(DASHCAM, WASHER, KEY))
    results.append(
        check(
            "an alert ahead of a seen one starts despite an earlier startedAt",
            changes == [("started", DASHCAM["name"])],
            f"got {changes}",
        )
    )
    results.append(
        check(
            "alerts keeps the vehicle's order",
            vehicle.alerts == [DASHCAM, WASHER, KEY],
            f"got {vehicle.alerts}",
        )
    )


def test_alerts_follow_the_latest_batch(results: list[bool]) -> None:
    """The vehicle drops old alerts off its window, active ones included, with
    no endedAt; `alerts` follows it rather than holding them active forever."""
    stream = make_stream()
    vehicle, changes = track(stream)
    stream._dispatch(batch(KEY, DOOR, CABLE, cache=True))
    stream._dispatch(batch(KEY, DOOR))
    results.append(
        check("an alert dropped off the window calls back nothing", changes == [], f"got {changes}")
    )
    results.append(
        check(
            "an alert dropped off the window leaves alerts",
            vehicle.alerts == [KEY, DOOR],
            f"got {vehicle.alerts}",
        )
    )


def test_callers_get_copies(results: list[bool]) -> None:
    stream = make_stream()
    vehicle = stream.get_vehicle(VIN)
    received: list[dict[str, Any]] = []
    vehicle.listen_AlertChanges(lambda change, a: received.append(a))
    stream._dispatch(batch(DOOR, cache=True))
    stream._dispatch(batch(KEY, DOOR))
    received[0]["endedAt"] = "mutated"
    vehicle.alerts[0]["endedAt"] = "mutated"
    results.append(
        check(
            "callers get copies, not the tracked alerts",
            vehicle.alerts == [KEY, DOOR],
            f"got {vehicle.alerts}",
        )
    )


async def test_reconnect_replay(results: list[bool]) -> None:
    """Through the real SSE reader: the first connection's snapshot seeds and
    a live batch starts KEY; the stream then ends and reconnects, and the new
    connection's snapshot is the latest batch plus what changed meanwhile."""
    session = FakeSession(
        [
            [batch(DOOR, CABLE, cache=True), batch(KEY, DOOR, CABLE)],
            [batch(USB, KEY, DOOR, CABLE_ENDED, cache=True)],
        ]
    )
    stream = make_stream(session, manual=False)
    _, changes = track(stream)
    await wait_for(lambda: session.calls == 2 and len(changes) >= 4)
    await asyncio.sleep(0)
    stream.close()

    results.append(check("the stream reconnected", session.calls == 2, f"calls {session.calls}"))
    results.append(
        check(
            "the replayed snapshot reports only what changed",
            changes
            == [
                ("started", KEY["name"]),
                ("ended", CABLE["name"]),
                ("started", USB["name"]),
                ("ended", USB["name"]),
            ],
            f"got {changes}",
        )
    )


async def main() -> None:
    results: list[bool] = []
    test_first_batch_seeds_silently(results)
    test_live_transitions(results)
    test_stale_ended_alert_never_revives(results)
    test_unseen_history_is_not_a_start(results)
    test_skewed_clock(results)
    test_alerts_follow_the_latest_batch(results)
    test_callers_get_copies(results)
    await test_reconnect_replay(results)
    print(f"\n{sum(results)}/{len(results)} passed")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
