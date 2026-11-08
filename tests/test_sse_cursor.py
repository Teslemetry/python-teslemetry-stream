"""Checks the SSE `cursor` resume: the stream keeps the last `cursor` an event
carried and sends it back on a reconnect asking for the same vehicles and
topics, so the connect snapshot starts after it. A first connect, or one
whose vehicles or topics changed, omits it and takes a full snapshot.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any


from teslemetry_stream.stream import TeslemetryStream

VIN = "LRW3F7EK4NC000001"


def line(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event)}\n".encode()


def event(cursor: int | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "vin": VIN,
        "createdAt": "2026-11-07T10:00:00.000Z",
        "data": {"Odometer": 1},
    }
    if cursor is not None:
        ev["cursor"] = cursor
    return ev


class FakeContent:
    """Response body that yields its lines once, then ends cleanly."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    def __aiter__(self) -> FakeContent:
        return self

    async def __anext__(self) -> bytes:
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class FakeResponse:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200
        self.content = FakeContent([line(e) for e in events])

    def close(self) -> None:
        pass


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_stream(session: FakeSession, **kwargs: Any) -> TeslemetryStream:
    return TeslemetryStream(
        session=session,  # type: ignore[arg-type]
        access_token="test-token",
        server="api.teslemetry.com",
        manual=True,
        **kwargs,
    )


def sent_cursor(session: FakeSession, index: int) -> str | None:
    return session.calls[index]["params"].get("cursor")


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


async def test_resume(results: list[bool]) -> None:
    session = FakeSession(
        [
            FakeResponse([event(5), event()]),
            FakeResponse([event(9)]),
            FakeResponse([event()]),
        ]
    )
    stream = make_stream(session, topics=["data"])
    stream.active = True

    await stream.__anext__()
    results.append(
        check("first connect omits cursor", sent_cursor(session, 0) is None)
    )
    results.append(check("cursor tracked from an event", stream._cursor == 5))

    await stream.__anext__()
    results.append(
        check("an event without cursor keeps the last value", stream._cursor == 5)
    )

    await stream.__anext__()  # body ends, reconnects
    results.append(
        check(
            "reconnect sends the last cursor",
            sent_cursor(session, 1) == "5",
            f"got {sent_cursor(session, 1)!r}",
        )
    )
    results.append(
        check(
            "cursor sent next to cache=true",
            session.calls[1]["params"].get("cache") == "true",
        )
    )


async def main() -> int:
    results: list[bool] = []
    await test_resume(results)
    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
