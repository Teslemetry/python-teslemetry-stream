"""Regression tests for __anext__'s auth-failure handling: a 401/403
aiohttp.ClientResponseError is a subtype of aiohttp.ClientError, so without
special-casing it, an invalid token is swallowed and retried exactly like a
transient network blip - the caller sees no events and no error. These tests
cover the fix (auth failure surfaces as TeslemetryStreamAuthenticationError
and is not retried) and its safety rail (a genuine transient ClientError
still retries and reconnects, unchanged).
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
    """Async-iterable response body that blocks until failed or cancelled."""

    def __init__(self) -> None:
        self._blocker: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def __aiter__(self) -> FakeContent:
        return self

    async def __anext__(self) -> bytes:
        await self._blocker
        raise AssertionError("unreachable - blocker only resolves via an exception")

    def fail(self, exc: BaseException) -> None:
        if not self._blocker.done():
            self._blocker.set_exception(exc)


class FakeResponse:
    """Minimal stand-in for the aiohttp response `connect()` awaits."""

    def __init__(self) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200
        self.content = FakeContent()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    """Captures every `get()` call; a queue of `get_results` (each either an
    exception to raise or a FakeResponse to return) drives each call in
    order, mirroring how a real 401 raises straight out of the connect GET
    when `raise_for_status=True`."""

    def __init__(self, get_results: list[Any]) -> None:
        self.calls = 0
        self._get_results = list(get_results)
        self.responses: list[FakeResponse] = []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls += 1
        result = self._get_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        self.responses.append(result)
        return result


def make_stream(session: FakeSession) -> TeslemetryStream:
    return TeslemetryStream(
        session=session,  # type: ignore[arg-type]
        access_token="bad-token",
        server="api.teslemetry.com",
        manual=True,
    )


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


async def drain_cancelled(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_401_surfaces_and_does_not_retry(results: list[bool]) -> None:
    error = aiohttp.ClientResponseError(
        request_info=REQUEST_INFO, history=(), status=401, message="Unauthorized"
    )
    session = FakeSession([error])
    stream = make_stream(session)

    task = asyncio.create_task(stream.listen())

    raised: Exception | None = None
    try:
        await task
    except TeslemetryStreamAuthenticationError as exc:
        raised = exc

    results.append(
        check("a 401 surfaces as TeslemetryStreamAuthenticationError", raised is not None)
    )
    results.append(
        check(
            "the original 401 is chained as the cause",
            raised is not None and raised.__cause__ is error,
        )
    )
    results.append(
        check("no retry is attempted after a 401", session.calls == 1, f"got {session.calls}")
    )
    results.append(check("the stream stops rather than looping forever", not stream.active))


async def test_403_surfaces_and_does_not_retry(results: list[bool]) -> None:
    error = aiohttp.ClientResponseError(
        request_info=REQUEST_INFO, history=(), status=403, message="Forbidden"
    )
    session = FakeSession([error])
    stream = make_stream(session)

    task = asyncio.create_task(stream.listen())

    raised: Exception | None = None
    try:
        await task
    except TeslemetryStreamAuthenticationError as exc:
        raised = exc

    results.append(
        check("a 403 surfaces as TeslemetryStreamAuthenticationError", raised is not None)
    )
    results.append(
        check("no retry is attempted after a 403", session.calls == 1, f"got {session.calls}")
    )


async def test_transient_client_error_still_retries_and_reconnects(results: list[bool]) -> None:
    """A genuine transient failure (connection reset mid-stream, not a 401/403
    response) must keep retrying and reconnecting exactly as before - the
    auth-failure special-case must not touch this path."""
    session = FakeSession([FakeResponse(), FakeResponse()])
    stream = make_stream(session)

    task = asyncio.create_task(stream.listen())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    results.append(check("initial connect happened", session.calls == 1, f"got {session.calls}"))

    session.responses[0].content.fail(aiohttp.ClientError("boom"))
    # retries starts at 0, so the first backoff delay is 2**0 == 1 second.
    await asyncio.sleep(1.2)

    results.append(check("the stream is still active after a transient error", stream.active))
    results.append(
        check(
            "the stream reconnected instead of surfacing an error",
            session.calls == 2,
            f"got {session.calls}",
        )
    )
    results.append(check("the listen task is still running", not task.done()))

    stream.close()
    await drain_cancelled(task)


async def main() -> None:
    results: list[bool] = []
    await test_401_surfaces_and_does_not_retry(results)
    await test_403_surfaces_and_does_not_retry(results)
    await test_transient_client_error_still_retries_and_reconnects(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
