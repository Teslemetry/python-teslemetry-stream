"""Regression tests for the silence watchdog in `__anext__`: a connection
that stops delivering any bytes - not even an SSE keepalive comment - for
longer than the silence window is closed and reconnected by the existing
loop, instead of hanging forever like the customer incident that motivated
this (a Home Assistant instance whose stream connection went dead for 2.5+
days with no reconnect attempt).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Callable

import teslemetry_stream.stream as stream_module
from teslemetry_stream.stream import LOGGER, TeslemetryStream


class QueueContent:
    """Async-iterable response body fed lines on the test's own timeline."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    def __aiter__(self) -> QueueContent:
        return self

    async def __anext__(self) -> bytes:
        return await self._queue.get()

    def push(self, line: bytes) -> None:
        self._queue.put_nowait(line)


class FakeResponse:
    def __init__(self) -> None:
        self.url = "https://fake.teslemetry.com/sse"
        self.status = 200
        self.content = QueueContent()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self) -> None:
        self.calls = 0
        self.responses: list[FakeResponse] = []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls += 1
        response = FakeResponse()
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


def with_silence_window(window: float) -> Callable[[], None]:
    """Patch the module-level silence window; returns a restore function."""
    original = stream_module._SILENCE_WINDOW
    stream_module._SILENCE_WINDOW = window

    def restore() -> None:
        stream_module._SILENCE_WINDOW = original

    return restore


async def test_silence_past_window_triggers_reconnect(results: list[bool]) -> None:
    session = FakeSession()
    stream = make_stream(session)
    restore = with_silence_window(0.1)

    with CaptureLogs() as records:
        task = asyncio.create_task(stream.listen())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        results.append(
            check("initial connect happened", session.calls == 1, f"got {session.calls}")
        )

        await asyncio.sleep(0.15)  # past the (patched) silence window, before a second one

        results.append(
            check(
                "a reconnect attempt was made after silence",
                session.calls == 2,
                f"got {session.calls}",
            )
        )
        results.append(check("the silent response was closed", session.responses[0].closed))

    warning_records = [
        r for r in records if r.levelno == logging.WARNING and "No data received" in r.getMessage()
    ]
    results.append(
        check(
            "the first silence-triggered reconnect logs at WARNING",
            len(warning_records) == 1,
            f"got {warning_records}",
        )
    )

    restore()
    stream.close()
    await drain_cancelled(task)


async def test_repeated_silence_logs_debug_after_first_warning(results: list[bool]) -> None:
    session = FakeSession()
    stream = make_stream(session)
    restore = with_silence_window(0.1)

    with CaptureLogs() as records:
        task = asyncio.create_task(stream.listen())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # Two consecutive silence windows with no successful read in between.
        await asyncio.sleep(0.15)
        await asyncio.sleep(0.1)

        results.append(
            check(
                "a second reconnect attempt was made",
                session.calls == 3,
                f"got {session.calls}",
            )
        )

    warning_records = [
        r for r in records if r.levelno == logging.WARNING and "No data received" in r.getMessage()
    ]
    debug_records = [
        r for r in records if r.levelno == logging.DEBUG and "No data received" in r.getMessage()
    ]
    results.append(
        check(
            "only the first silence-triggered reconnect logs at WARNING",
            len(warning_records) == 1,
            f"got {warning_records}",
        )
    )
    results.append(
        check(
            "the repeat silence-triggered reconnect logs at DEBUG",
            len(debug_records) == 1,
            f"got {debug_records}",
        )
    )

    restore()
    stream.close()
    await drain_cancelled(task)


async def test_keepalive_within_window_does_not_reconnect(results: list[bool]) -> None:
    session = FakeSession()
    stream = make_stream(session)
    restore = with_silence_window(0.2)

    task = asyncio.create_task(stream.listen())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    results.append(
        check("initial connect happened", session.calls == 1, f"got {session.calls}")
    )

    # A keepalive comment line, well inside the window, should reset it.
    await asyncio.sleep(0.1)
    session.responses[0].content.push(b": keepalive\n")
    await asyncio.sleep(0)

    # Elapsed since connect (0.1 + 0.1 = 0.2) would exceed the window if it
    # hadn't been reset by the keepalive above.
    await asyncio.sleep(0.1)

    results.append(
        check(
            "no reconnect happens while keepalives arrive inside the window",
            session.calls == 1,
            f"got {session.calls}",
        )
    )
    results.append(
        check("the connection stays open", not session.responses[0].closed)
    )

    restore()
    stream.close()
    await drain_cancelled(task)


async def main() -> None:
    results: list[bool] = []
    await test_silence_past_window_triggers_reconnect(results)
    await test_repeated_silence_logs_debug_after_first_warning(results)
    await test_keepalive_within_window_does_not_reconnect(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
