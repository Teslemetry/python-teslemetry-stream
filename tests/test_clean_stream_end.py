"""Regression tests for how __anext__ logs the end of the SSE response body.

A deploy on the Teslemetry API ends every open SSE stream cleanly (the
response body just finishes, no exception). That is routine and must log at
INFO, not WARNING - a WARNING per connection on every deploy reads as an
error in every streaming Home Assistant install's log. An abrupt end (a
transport-level aiohttp.ClientError) is a real problem and must keep its
WARNING.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import aiohttp

from teslemetry_stream.stream import LOGGER, TeslemetryStream


class FakeContent:
    """Async-iterable response body that either ends cleanly or fails."""

    def __init__(self) -> None:
        self._blocker: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._ended = False

    def __aiter__(self) -> FakeContent:
        return self

    async def __anext__(self) -> bytes:
        if self._ended:
            raise StopAsyncIteration
        await self._blocker
        raise AssertionError("unreachable - blocker only resolves via an exception")

    def end(self) -> None:
        """Simulate a clean end of the body (server closed it normally)."""
        self._ended = True
        if not self._blocker.done():
            self._blocker.set_exception(StopAsyncIteration())

    def fail(self, exc: BaseException) -> None:
        if not self._blocker.done():
            self._blocker.set_exception(exc)


class FakeResponse:
    def __init__(self) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200
        self.content = FakeContent()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.calls = 0
        self._responses = list(responses)
        self.responses: list[FakeResponse] = []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls += 1
        response = self._responses.pop(0)
        self.responses.append(response)
        return response


def make_stream(session: FakeSession) -> TeslemetryStream:
    return TeslemetryStream(
        session=session,  # type: ignore[arg-type]
        access_token="test-token",
        server="api.teslemetry.com",
        manual=True,
    )


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


async def drain_cancelled(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_clean_end_logs_info_and_reconnects(results: list[bool]) -> None:
    session = FakeSession([FakeResponse(), FakeResponse()])
    stream = make_stream(session)

    with CaptureLogs() as records:
        task = asyncio.create_task(stream.listen())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        results.append(
            check("initial connect happened", session.calls == 1, f"got {session.calls}")
        )

        session.responses[0].content.end()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    results.append(
        check(
            "reconnected immediately on a clean end",
            session.calls == 2,
            f"got {session.calls}",
        )
    )
    results.append(check("the stream is still active after a clean end", stream.active))

    info_records = [
        r for r in records if r.levelno == logging.INFO and "Stream ended" in r.getMessage()
    ]
    warning_records = [
        r for r in records if r.levelno == logging.WARNING and "Stream ended" in r.getMessage()
    ]
    results.append(
        check("a clean end logs at INFO", len(info_records) == 1, f"got {info_records}")
    )
    results.append(
        check(
            "a clean end does not log at WARNING",
            len(warning_records) == 0,
            f"got {warning_records}",
        )
    )

    stream.close()
    await drain_cancelled(task)


async def test_abrupt_end_still_warns(results: list[bool]) -> None:
    session = FakeSession([FakeResponse(), FakeResponse()])
    stream = make_stream(session)

    with CaptureLogs() as records:
        task = asyncio.create_task(stream.listen())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        session.responses[0].content.fail(aiohttp.ClientError("boom"))
        # retries starts at 0, so the first backoff delay is 2**0 == 1 second.
        await asyncio.sleep(1.2)

    results.append(
        check(
            "reconnected after an abrupt end",
            session.calls == 2,
            f"got {session.calls}",
        )
    )

    warning_records = [
        r for r in records if r.levelno == logging.WARNING and "Client error" in r.getMessage()
    ]
    results.append(
        check(
            "an abrupt end still logs at WARNING",
            len(warning_records) == 1,
            f"got {warning_records}",
        )
    )

    stream.close()
    await drain_cancelled(task)


class CaptureLogs:
    """Minimal stand-in for pytest's caplog fixture, scoped to LOGGER."""

    def __enter__(self) -> list[logging.LogRecord]:
        self._records: list[logging.LogRecord] = []
        self._handler = _ListHandler(self._records)
        self._prev_level = LOGGER.level
        LOGGER.addHandler(self._handler)
        LOGGER.setLevel(logging.DEBUG)
        return self._records

    def __exit__(self, *exc_info: Any) -> None:
        LOGGER.removeHandler(self._handler)
        LOGGER.setLevel(self._prev_level)


class _ListHandler(logging.Handler):
    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self._records = records

    def emit(self, record: logging.LogRecord) -> None:
        self._records.append(record)


async def main() -> None:
    results: list[bool] = []
    await test_clean_end_logs_info_and_reconnects(results)
    await test_abrupt_end_still_warns(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
