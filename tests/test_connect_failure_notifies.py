"""Regression tests for connection listeners when the stream cannot connect.

A connect that fails before the stream has ever connected leaves no response
to close, so the reconnect path used to say nothing to connection listeners.
A consumer that marks its entities unavailable on `False` then kept showing
setup-time values as live for as long as the outage lasted. Every failed
attempt must report `False`, while a stream that is already connected must
still report exactly one `False` when it drops.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import aiohttp

from teslemetry_stream.exception import TeslemetryStreamAuthenticationError
from teslemetry_stream.stream import TeslemetryStream

REQUEST_INFO = aiohttp.RequestInfo(
    url="https://fake.teslemetry.com/sse",
    method="GET",
    headers={},  # type: ignore[arg-type]
    real_url="https://fake.teslemetry.com/sse",  # type: ignore[arg-type]
)


class FakeContent:
    """Async-iterable response body that blocks until failed."""

    def __init__(self) -> None:
        self._blocker: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def __aiter__(self) -> FakeContent:
        return self

    async def __anext__(self) -> bytes:
        await self._blocker
        raise AssertionError("unreachable - blocker only resolves via an exception")

    def fail(self, exc: BaseException) -> None:
        self._blocker.set_exception(exc)


class FakeResponse:
    def __init__(self) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200
        self.content = FakeContent()

    def close(self) -> None:
        pass


class FakeSession:
    """Each `get()` raises or returns the next queued result; once they run
    out, `exhausted` resolves and the call blocks, so a test observes the
    first retry instead of spinning through backoff."""

    def __init__(self, get_results: list[Any]) -> None:
        self._get_results = list(get_results)
        self.exhausted: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def get(self, url: str, **kwargs: Any) -> Any:
        if not self._get_results:
            self.exhausted.set_result(None)
            await asyncio.Future()
        result = self._get_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def make_stream(session: FakeSession) -> TeslemetryStream:
    return TeslemetryStream(
        session=session,  # type: ignore[arg-type]
        access_token="token",
        server="api.teslemetry.com",
        manual=True,
    )


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


async def next_connection_event(
    stream: TeslemetryStream, session: FakeSession, events: list[bool], count: int
) -> asyncio.Task[Any]:
    """Run `__anext__` until `count` connection events have arrived or the
    stream starts a retry the session has no answer for, then return the
    still-pending task."""
    reached = asyncio.get_running_loop().create_future()

    def record(value: bool) -> None:
        events.append(value)
        if len(events) >= count and not reached.done():
            reached.set_result(None)

    stream.async_add_connection_listener(record)
    stream.active = True
    task = asyncio.create_task(stream.__anext__())
    await asyncio.wait(
        {reached, session.exhausted, task}, return_when=asyncio.FIRST_COMPLETED
    )
    return task


async def drain(task: asyncio.Task[Any]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


async def test_failed_first_connect_reports_down(results: list[bool]) -> None:
    session = FakeSession([aiohttp.ClientConnectionError("refused")])
    stream = make_stream(session)
    events: list[bool] = []

    task = await next_connection_event(stream, session, events, 1)

    results.append(
        check(
            "a failed first connect notifies connection listeners with False",
            events == [False],
            f"got {events}",
        )
    )
    results.append(check("the stream is still retrying", not task.done() and stream.active))
    await drain(task)


async def test_unexpected_first_connect_error_reports_down(results: list[bool]) -> None:
    session = FakeSession([RuntimeError("boom")])
    stream = make_stream(session)
    events: list[bool] = []

    task = await next_connection_event(stream, session, events, 1)

    results.append(
        check(
            "an unexpected error on first connect notifies False",
            events == [False],
            f"got {events}",
        )
    )
    await drain(task)


async def test_auth_failure_on_first_connect_reports_down(results: list[bool]) -> None:
    error = aiohttp.ClientResponseError(
        request_info=REQUEST_INFO, history=(), status=401, message="Unauthorized"
    )
    stream = make_stream(FakeSession([error]))
    events: list[bool] = []
    stream.async_add_connection_listener(events.append)
    stream.active = True

    raised = False
    try:
        await stream.__anext__()
    except TeslemetryStreamAuthenticationError:
        raised = True

    results.append(check("a 401 on first connect still raises", raised))
    results.append(
        check("a 401 on first connect notifies False", events == [False], f"got {events}")
    )


async def test_drop_after_connect_reports_one_down(results: list[bool]) -> None:
    response = FakeResponse()
    session = FakeSession([response])
    stream = make_stream(session)
    events: list[bool] = []

    task = await next_connection_event(stream, session, events, 1)
    response.content.fail(aiohttp.ClientPayloadError("reset"))
    reached = asyncio.get_running_loop().create_future()
    stream.async_add_connection_listener(
        lambda value: reached.done() or reached.set_result(None)
    )
    await asyncio.wait(
        {reached, session.exhausted, task}, return_when=asyncio.FIRST_COMPLETED
    )

    results.append(
        check(
            "a connected stream that drops reports True then a single False",
            events == [True, False],
            f"got {events}",
        )
    )
    await drain(task)


async def main() -> None:
    results: list[bool] = []
    await test_failed_first_connect_reports_down(results)
    await test_unexpected_first_connect_error_reports_down(results)
    await test_auth_failure_on_first_connect_reports_down(results)
    await test_drop_after_connect_reports_one_down(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
