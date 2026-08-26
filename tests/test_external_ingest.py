"""Tests for `TeslemetryStream.ingest`, the externally sourced event surface.

An observation the library did not pull off its own SSE connection (a
Bluetooth broadcast, today) is handed in as a stream-shaped dict and reaches
the same listeners a native event does. What is asserted here:

- native SSE events are delivered exactly as before, with nothing added;
- a BLE-shaped event and a native event for the same field are
  indistinguishable to a consumer apart from their metadata - the field
  names and value types the two sources emit are the same;
- every event is dispatched in arrival order with no deduplication and no
  source ranking, so two sources reporting one field produce two dispatches.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from teslemetry_stream.const import Metadata, Signal
from teslemetry_stream.stream import TeslemetryStream

VIN = "TESTVIN0000000001"

# Both sources report these three fields with the same names and the same
# value types - the payload-compatibility claim this file exists to pin.
NATIVE_LINES = [
    b'data: {"vin": "TESTVIN0000000001", "createdAt": "2026-08-26T03:40:26.399Z",'
    b' "data": {"Locked": true}}\n',
    b'data: {"vin": "TESTVIN0000000001", "createdAt": "2026-08-26T03:40:36.399Z",'
    b' "data": {"ChargePortDoorOpen": false}}\n',
    b'data: {"vin": "TESTVIN0000000001", "createdAt": "2026-08-26T03:40:46.399Z",'
    b' "data": {"DoorState": {"TrunkFront": true}}}\n',
]

NATIVE_EVENTS: list[dict[str, Any]] = [
    json.loads(line.decode().partition(": ")[2]) for line in NATIVE_LINES
]


class FakeEventContent:
    """Async-iterable response body yielding canned SSE lines, then blocking."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)
        self._blocker: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def __aiter__(self) -> FakeEventContent:
        return self

    async def __anext__(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        await self._blocker
        raise AssertionError("unreachable - blocker only resolves via cancellation")


class FakeResponse:
    """Minimal stand-in for the aiohttp response `connect()` awaits."""

    def __init__(self, content: Any) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200
        self.content = content
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    """Counts `get()` calls and serves canned SSE content."""

    def __init__(self, lines: list[bytes] | None = None) -> None:
        self.calls = 0
        self.lines = lines or []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls += 1
        return FakeResponse(FakeEventContent(self.lines))


def make_stream(
    session: FakeSession,
    manual: bool = True,
    vin: str | None = None,
    parse_timestamp: bool = False,
) -> TeslemetryStream:
    return TeslemetryStream(
        session=session,  # type: ignore[arg-type]
        access_token="test-token",
        server="api.teslemetry.com",
        manual=manual,
        vin=vin,
        parse_timestamp=parse_timestamp,
    )


def make_vehicle(stream: TeslemetryStream) -> Any:
    """A vehicle whose config is already known, so listen_* issues no REST."""
    vehicle = stream.get_vehicle(VIN)
    vehicle.fields = {s.value: {} for s in Signal}
    vehicle._populated = True
    return vehicle


def dispatch_native(stream: TeslemetryStream, event: dict[str, Any]) -> None:
    """Deliver an event the way the SSE reader does.

    `test_native_events_are_delivered_unchanged` is what proves `listen()`
    still goes through here.
    """
    stream._dispatch(event)


async def wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Poll until `predicate` holds or the timeout expires."""
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


async def test_native_events_are_delivered_unchanged(results: list[bool]) -> None:
    """The regression that would matter most: adding an ingestion point must
    not touch what the SSE connection itself delivers."""
    session = FakeSession(NATIVE_LINES)
    stream = make_stream(session, manual=False)
    delivered: list[dict[str, Any]] = []
    stream.async_add_listener(delivered.append)
    await wait_for(lambda: len(delivered) == len(NATIVE_EVENTS))
    stream.close()

    results.append(
        check(
            "native SSE events arrive exactly as sent",
            delivered == NATIVE_EVENTS,
            f"got {delivered}",
        )
    )
    results.append(
        check(
            "native SSE events gain no metadata key",
            all("metadata" not in event for event in delivered),
            f"got {[sorted(e) for e in delivered]}",
        )
    )

    # parse_timestamp still derives its epoch milliseconds from createdAt.
    session = FakeSession(NATIVE_LINES[:1])
    stream = make_stream(session, manual=False, parse_timestamp=True)
    stamped: list[dict[str, Any]] = []
    stream.async_add_listener(stamped.append)
    await wait_for(lambda: len(stamped) == 1)
    stream.close()
    results.append(
        check(
            "native parse_timestamp is unchanged",
            bool(stamped) and stamped[0]["timestamp"] == 1787715626399,
            f"got {stamped}",
        )
    )


async def test_ingested_and_native_events_are_indistinguishable(
    results: list[bool],
) -> None:
    """A BLE-shaped event and a stream-shaped event for the same field must
    look the same to a consumer once through the funnel, apart from metadata."""
    stream = make_stream(FakeSession())
    vehicle = make_vehicle(stream)

    locked: list[Any] = []
    charge_port: list[Any] = []
    trunk: list[Any] = []
    vehicle.listen_Locked(locked.append)
    vehicle.listen_ChargePortDoorOpen(charge_port.append)
    vehicle.listen_TrunkFront(trunk.append)

    raw: list[dict[str, Any]] = []
    stream.async_add_listener(raw.append, {"vin": VIN})

    for event in NATIVE_EVENTS:
        dispatch_native(stream, event)

    ingested = [
        vehicle.ingest(
            {Signal.LOCKED: True},
            {Metadata.SOURCE: "bluetooth", Metadata.RAW: "VEHICLELOCKSTATE_LOCKED"},
        ),
        vehicle.ingest(
            {Signal.CHARGE_PORT_DOOR_OPEN: False},
            {Metadata.SOURCE: "bluetooth", Metadata.RAW: "CLOSURESTATE_CLOSED"},
        ),
        vehicle.ingest(
            {Signal.DOOR_STATE: {"TrunkFront": True}},
            {Metadata.SOURCE: "bluetooth", Metadata.RAW: "CLOSURESTATE_OPEN"},
        ),
    ]

    results.append(
        check(
            "typed listeners deliver the same values from both sources",
            locked == [True, True]
            and charge_port == [False, False]
            and trunk == [True, True],
            f"got {locked} {charge_port} {trunk}",
        )
    )
    results.append(
        check(
            "and the same Python types",
            all(type(a) is type(b) for a, b in (locked, charge_port, trunk)),
            f"got {[type(v).__name__ for v in locked + charge_port + trunk]}",
        )
    )

    def comparable(event: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in event.items() if k not in ("metadata", "createdAt")}

    results.append(
        check(
            "ingested events match native ones apart from metadata",
            [comparable(e) for e in ingested] == [comparable(e) for e in NATIVE_EVENTS],
            f"got {[comparable(e) for e in ingested]}",
        )
    )
    results.append(
        check(
            "an ingested event carries the documented wire keys",
            all(
                sorted(e) == ["createdAt", "data", "metadata", "vin"] for e in ingested
            ),
            f"got {[sorted(e) for e in ingested]}",
        )
    )
    results.append(
        check(
            "an ingested event's keys are plain strings, as decoded JSON gives",
            all(type(key) is str for event in ingested for key in event),
            f"got {[[type(k).__name__ for k in e] for e in ingested]}",
        )
    )
    results.append(
        check(
            "a plain listener sees both sources on one subscription",
            len(raw) == 6,
            f"got {len(raw)}",
        )
    )


async def test_both_sources_reporting_one_field(results: list[bool]) -> None:
    """No deduplication and no reordering: every event is dispatched as it
    arrives, whichever source it came from."""
    stream = make_stream(FakeSession())
    vehicle = make_vehicle(stream)

    locked: list[Any] = []
    vehicle.listen_Locked(locked.append)
    sources: list[Any] = []
    stream.async_add_listener(
        lambda e: sources.append(e.get("metadata", {}).get("source")), {"vin": VIN}
    )

    # Bluetooth reports the change first, the stream repeats it a beat later,
    # then Bluetooth reports the next change.
    vehicle.ingest({Signal.LOCKED: False}, {Metadata.SOURCE: "bluetooth"})
    dispatch_native(stream, {"vin": VIN, "data": {Signal.LOCKED: False}})
    vehicle.ingest({Signal.LOCKED: True}, {Metadata.SOURCE: "bluetooth"})

    results.append(
        check(
            "both sources' events are delivered, in arrival order",
            locked == [False, False, True],
            f"got {locked}",
        )
    )
    results.append(
        check(
            "the repeated value is not deduplicated away",
            sources == ["bluetooth", None, "bluetooth"],
            f"got {sources}",
        )
    )

    # The same sequence with the sources swapped behaves identically - the
    # stream holds no preference between them.
    stream = make_stream(FakeSession())
    vehicle = make_vehicle(stream)
    swapped: list[Any] = []
    vehicle.listen_Locked(swapped.append)
    vehicle.ingest({Signal.LOCKED: False}, {Metadata.SOURCE: "stream"})
    vehicle.ingest({Signal.LOCKED: False}, {Metadata.SOURCE: "bluetooth"})
    vehicle.ingest({Signal.LOCKED: True}, {Metadata.SOURCE: "stream"})
    results.append(
        check(
            "no source outranks another",
            swapped == locked,
            f"got {swapped}",
        )
    )

    # An older observation arriving late is still delivered: the stream keeps
    # no per-field value to compare it against.
    late: list[Any] = []
    stream = make_stream(FakeSession())
    vehicle = make_vehicle(stream)
    vehicle.listen_Locked(late.append)
    vehicle.ingest({Signal.LOCKED: True}, created_at="2026-08-26T03:40:46.000Z")
    vehicle.ingest({Signal.LOCKED: False}, created_at="2026-08-26T03:40:26.000Z")
    results.append(
        check(
            "an out-of-order observation is delivered, not dropped",
            late == [True, False],
            f"got {late}",
        )
    )


async def test_metadata_is_carried_and_never_acted_on(results: list[bool]) -> None:
    stream = make_stream(FakeSession())
    vehicle = make_vehicle(stream)
    seen: list[dict[str, Any]] = []
    stream.async_add_listener(seen.append, {"vin": VIN})

    payload = {Signal.LOCKED: False}
    metadata = {
        Metadata.SOURCE: "bluetooth",
        Metadata.RAW: "VEHICLELOCKSTATE_SELECTIVE_UNLOCKED",
        "rssi": -67,
    }
    event = vehicle.ingest(payload, metadata)
    results.append(
        check(
            "metadata is carried verbatim, extra keys included",
            event["metadata"] == metadata and seen[0]["metadata"] == metadata,
            f"got {event['metadata']}",
        )
    )

    # The caller's own dicts are its own; mutating them after the fact must
    # not rewrite an event already delivered.
    payload[Signal.LOCKED] = True
    metadata["rssi"] = -20
    results.append(
        check(
            "the dispatched event is unaffected by later caller mutation",
            event["data"] == {Signal.LOCKED: False} and event["metadata"]["rssi"] == -67,
            f"got {event}",
        )
    )

    plain = vehicle.ingest({Signal.LOCKED: True})
    results.append(
        check(
            "omitted metadata is an empty dict, not a missing key",
            plain["metadata"] == {},
            f"got {plain}",
        )
    )


async def test_ingest_needs_no_connection(results: list[bool]) -> None:
    """Bluetooth keeps reporting while the SSE connection is down, so
    ingesting must neither require nor start one."""
    session = FakeSession()
    stream = make_stream(session)
    vehicle = make_vehicle(stream)
    locked: list[Any] = []
    vehicle.listen_Locked(locked.append)

    vehicle.ingest({Signal.LOCKED: True}, {Metadata.SOURCE: "bluetooth"})

    results.append(
        check(
            "an ingested event is delivered while disconnected",
            locked == [True] and not stream.connected,
            f"got {locked}, connected={stream.connected}",
        )
    )
    results.append(
        check(
            "ingesting opens no connection",
            session.calls == 0 and not stream.active,
            f"got calls={session.calls}, active={stream.active}",
        )
    )


async def test_ingest_rejects_malformed_input(results: list[bool]) -> None:
    stream = make_stream(FakeSession(), vin=VIN)

    def raises(exc: type[BaseException], call: Callable[[], Any]) -> bool:
        try:
            call()
        except exc:
            return True
        except BaseException:
            return False
        return False

    results.append(
        check(
            "a non-dict payload raises TypeError",
            raises(TypeError, lambda: stream.ingest(["Locked"])),  # type: ignore[arg-type]
        )
    )
    results.append(
        check(
            "non-dict metadata raises TypeError",
            raises(
                TypeError,
                lambda: stream.ingest({Signal.LOCKED: True}, metadata="bluetooth"),  # type: ignore[arg-type]
            ),
        )
    )
    results.append(
        check(
            "the stream's own vin is used when none is given",
            stream.ingest({Signal.LOCKED: True})["vin"] == VIN,
        )
    )
    results.append(
        check(
            "a missing vin raises ValueError",
            raises(
                ValueError, lambda: make_stream(FakeSession()).ingest({Signal.LOCKED: True})
            ),
        )
    )


async def test_ingest_shares_the_native_dispatch_guarantees(
    results: list[bool],
) -> None:
    """Same dispatch, same protections: a raising listener is contained, and
    internal (bookkeeping) listeners still run before public ones."""
    stream = make_stream(FakeSession())
    vehicle = make_vehicle(stream)

    order: list[str] = []
    stream.async_add_listener(lambda e: order.append("public"), {"vin": VIN})
    stream.async_add_listener(
        lambda e: order.append("internal"), {"vin": VIN}, internal=True
    )

    def boom(event: dict[str, Any]) -> None:
        raise RuntimeError("listener blew up")

    stream.async_add_listener(boom, {"vin": VIN})
    delivered: list[Any] = []
    vehicle.listen_Locked(delivered.append)

    vehicle.ingest({Signal.LOCKED: True}, {Metadata.SOURCE: "bluetooth"})

    results.append(
        check(
            "internal listeners run before public ones",
            order == ["internal", "public"],
            f"got {order}",
        )
    )
    results.append(
        check(
            "a raising listener does not stop the rest",
            delivered == [True],
            f"got {delivered}",
        )
    )


async def main() -> None:
    results: list[bool] = []
    await test_native_events_are_delivered_unchanged(results)
    await test_ingested_and_native_events_are_indistinguishable(results)
    await test_both_sources_reporting_one_field(results)
    await test_metadata_is_carried_and_never_acted_on(results)
    await test_ingest_needs_no_connection(results)
    await test_ingest_rejects_malformed_input(results)
    await test_ingest_shares_the_native_dispatch_guarantees(results)
    # Let the fire-and-forget field-config tasks listen_* schedules finish.
    await asyncio.sleep(0)

    print("-" * 82)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
