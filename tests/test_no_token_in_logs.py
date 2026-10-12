"""Regression tests: the access token must never reach the log.

aiohttp.ClientResponseError's repr embeds its RequestInfo, and with it the
request headers - including "Authorization: Bearer <token>". Logging
repr(error) on a stream error (e.g. a 5xx from the SSE endpoint) wrote the
token into every Home Assistant log that shipped it anywhere. These tests
fail any log record that contains the token, on the retry path (5xx), the
auth-failure path (401) and the listen-task path.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import aiohttp
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from teslemetry_stream.exception import TeslemetryStreamAuthenticationError
from teslemetry_stream.stream import LOGGER, TeslemetryStream

TOKEN = "s3cr3t-access-token-value"
REQUEST_INFO = aiohttp.RequestInfo(
    url=URL("https://fake.teslemetry.com/sse"),
    method="GET",
    headers=CIMultiDictProxy(CIMultiDict({"Authorization": f"Bearer {TOKEN}"})),
    real_url=URL("https://fake.teslemetry.com/sse"),
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
    def __init__(self) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200
        self.content = FakeContent()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    """Each `get()` raises or returns the next queued result."""

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
        access_token=TOKEN,
        server="api.teslemetry.com",
        manual=True,
    )


def response_error(status: int, message: str) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(
        request_info=REQUEST_INFO, history=(), status=status, message=message
    )


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def leaked(records: list[logging.LogRecord]) -> list[str]:
    return [r.getMessage() for r in records if TOKEN in r.getMessage()]


async def drain_cancelled(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_fixture_would_leak_through_repr(results: list[bool]) -> None:
    """Guard: the fixture really carries the token in its repr, so the
    other tests would catch a regression back to repr(error)."""
    results.append(
        check(
            "repr(ClientResponseError) contains the token",
            TOKEN in repr(response_error(500, "x")),
        )
    )


async def test_server_error_does_not_log_token(results: list[bool]) -> None:
    session = FakeSession([FakeResponse(), FakeResponse()])
    stream = make_stream(session)

    with CaptureLogs() as records:
        task = asyncio.create_task(stream.listen())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        session.responses[0].content.fail(response_error(502, "Bad Gateway"))
        # retries starts at 0, so the first backoff delay is 2**0 == 1 second.
        await asyncio.sleep(1.2)

    warnings = [r for r in records if "Client error" in r.getMessage()]
    results.append(
        check("a 502 logs a Client error warning", len(warnings) == 1, f"got {warnings}")
    )
    results.append(
        check(
            "the warning keeps the status and message",
            bool(warnings) and "502" in warnings[0].getMessage()
            and "Bad Gateway" in warnings[0].getMessage(),
        )
    )
    results.append(check("no log record contains the token (502)", not leaked(records)))

    stream.close()
    await drain_cancelled(task)


async def test_auth_failure_does_not_log_token(results: list[bool]) -> None:
    session = FakeSession([response_error(401, "Unauthorized")])
    stream = make_stream(session)

    with CaptureLogs() as records, contextlib.suppress(TeslemetryStreamAuthenticationError):
        await stream.listen()

    results.append(
        check(
            "a 401 logs the authentication failure",
            any("Authentication failed" in r.getMessage() for r in records),
        )
    )
    results.append(check("no log record contains the token (401)", not leaked(records)))


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
    await test_fixture_would_leak_through_repr(results)
    await test_server_error_does_not_log_token(results)
    await test_auth_failure_does_not_log_token(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
