"""Regression tests for listen() dying before its first successful connect.

A listen task that fails before ever reaching a connect must not vanish
quietly: it is the failure mode behind the incident that motivated this -
a listen task that never logged a single connect attempt for 2.5+ days,
discoverable only by an absence in server-side logs. Any death before the
first connect must say so loudly, at ERROR, in the caller's own logs, and
must not swallow the underlying exception.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import aiohttp

from teslemetry_stream.exception import TeslemetryStreamAuthenticationError
from teslemetry_stream.stream import LOGGER, TeslemetryStream

REQUEST_INFO = aiohttp.RequestInfo(
    url="https://fake.teslemetry.com/sse",
    method="GET",
    headers={},  # type: ignore[arg-type]
    real_url="https://fake.teslemetry.com/sse",  # type: ignore[arg-type]
)


class BlockingSession:
    """A session whose GET never returns until the caller is cancelled -
    the shape of a connect() that is stuck (DNS, TCP handshake, proxy)."""

    def __init__(self) -> None:
        self.calls = 0

    async def get(self, url: str, **kwargs: Any) -> Any:
        self.calls += 1
        await asyncio.Future()  # blocks until this awaiter is cancelled


class FakeSession:
    """A session whose single `get()` raises the given exception, mirroring
    a 401/403 raising straight out of the connect GET."""

    def __init__(self, exc: BaseException) -> None:
        self.calls = 0
        self._exc = exc

    async def get(self, url: str, **kwargs: Any) -> Any:
        self.calls += 1
        raise self._exc


def make_stream(session: Any) -> TeslemetryStream:
    return TeslemetryStream(
        session=session,
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


def early_exit_errors(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [
        r
        for r in records
        if r.levelno == logging.ERROR and "before its first connect" in r.getMessage()
    ]


async def test_cancelled_before_first_connect_logs_error(results: list[bool]) -> None:
    """A stuck connect that is cancelled before it ever succeeds must log
    ERROR and re-raise the CancelledError - never vanish silently."""
    session = BlockingSession()
    stream = make_stream(session)

    with CaptureLogs() as records:
        task = asyncio.create_task(stream.listen())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task.cancel()
        await drain_cancelled(task)

    results.append(
        check(
            "cancellation before first connect logs at ERROR",
            len(early_exit_errors(records)) == 1,
            f"got {early_exit_errors(records)}",
        )
    )
    results.append(check("the task ended up cancelled, not swallowed", task.cancelled()))


async def test_auth_failure_before_first_connect_logs_error(results: list[bool]) -> None:
    """A 401 on the very first connect attempt both surfaces its usual
    TeslemetryStreamAuthenticationError and, since it happened before any
    connect ever succeeded, is loudly flagged as an early exit."""
    error = aiohttp.ClientResponseError(
        request_info=REQUEST_INFO, history=(), status=401, message="Unauthorized"
    )
    session = FakeSession(error)
    stream = make_stream(session)

    with CaptureLogs() as records:
        task = asyncio.create_task(stream.listen())

        raised: BaseException | None = None
        try:
            await task
        except TeslemetryStreamAuthenticationError as exc:
            raised = exc

    results.append(
        check(
            "the auth error is still re-raised, not swallowed",
            isinstance(raised, TeslemetryStreamAuthenticationError),
            f"got {raised!r}",
        )
    )
    results.append(
        check(
            "the failure before first connect logs at ERROR",
            len(early_exit_errors(records)) == 1,
            f"got {early_exit_errors(records)}",
        )
    )


async def main() -> None:
    results: list[bool] = []
    await test_cancelled_before_first_connect_logs_error(results)
    await test_auth_failure_before_first_connect_logs_error(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
