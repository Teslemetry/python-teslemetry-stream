"""Regression tests for the SSE stream lifecycle hardening: an owned listen
task, serialized connect(), and close() as a real stop rather than a
response-close-only operation.

Scenarios mirror the leak audit's proven defects:
- no listener/connect single-flight (concurrent connects overwrite the one
  `_response` slot, orphaning the first response);
- last-listener removal only flipped `active`, leaving the response open;
- `close()` didn't stop a running listener or survive task cancellation.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import aiohttp

from teslemetry_stream.stream import TeslemetryStream


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
    """Captures every `get()` call; optionally gates them on an event."""

    def __init__(self) -> None:
        self.calls = 0
        self.responses: list[FakeResponse] = []
        self.gate: asyncio.Event | None = None

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        response = FakeResponse()
        self.responses.append(response)
        return response


def make_stream(session: FakeSession, manual: bool = False) -> TeslemetryStream:
    return TeslemetryStream(
        session=session,  # type: ignore[arg-type]
        access_token="test-token",
        server="api.teslemetry.com",
        manual=manual,
    )


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


async def drain_cancelled(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_add_remove_readd_before_loop_runs(results: list[bool]) -> None:
    session = FakeSession()
    stream = make_stream(session)

    remove1 = stream.async_add_listener(lambda event: None)
    task1 = stream._listen_task
    remove1()
    remove2 = stream.async_add_listener(lambda event: None)
    task2 = stream._listen_task

    results.append(
        check(
            "re-add before the loop runs schedules a distinct owned task",
            task2 is not None and task2 is not task1,
        )
    )

    # Let the event loop actually run the (cancelled) first task and the
    # (live) second one.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    results.append(
        check(
            "exactly one connect happens despite add/remove/re-add racing the task",
            session.calls == 1,
            f"got {session.calls}",
        )
    )
    results.append(check("the stream ends up connected", stream.connected))

    stream.close()
    await asyncio.sleep(0)
    remove2()

    results.append(
        check(
            "close leaves no open response behind",
            bool(session.responses) and all(r.closed for r in session.responses),
        )
    )


async def test_two_explicit_listen_calls(results: list[bool]) -> None:
    session = FakeSession()
    stream = make_stream(session, manual=True)

    task_a = asyncio.create_task(stream.listen())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    results.append(
        check("the first listen() call connects", session.calls == 1, f"got {session.calls}")
    )

    task_b = asyncio.create_task(stream.listen())
    await asyncio.sleep(0)
    results.append(
        check(
            "a second concurrent listen() call joins rather than reconnecting",
            session.calls == 1,
            f"got {session.calls}",
        )
    )
    results.append(
        check("the owned task stays the first caller's", stream._listen_task is task_a)
    )

    stream.close()
    await drain_cancelled(task_a)
    await drain_cancelled(task_b)

    results.append(
        check("both callers finish once the owner is closed", task_a.done() and task_b.done())
    )
    results.append(
        check(
            "close leaves no open response behind",
            bool(session.responses) and all(r.closed for r in session.responses),
        )
    )


async def test_cancel_while_blocked_reading(results: list[bool]) -> None:
    session = FakeSession()
    stream = make_stream(session, manual=True)

    task = asyncio.create_task(stream.listen())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    results.append(check("connected before cancellation", stream.connected and session.calls == 1))

    # Cancel the task directly - not via stream.close() - to prove listen()'s
    # own finally, not an explicit stop call, is what closes the response.
    task.cancel()
    await drain_cancelled(task)

    results.append(
        check(
            "cancellation while blocked in content still closes the response",
            bool(session.responses) and session.responses[0].closed,
        )
    )
    results.append(check("the response reference is cleared", stream._response is None))
    results.append(check("the owned task reference is cleared", stream._listen_task is None))


async def test_close_during_connect(results: list[bool]) -> None:
    session = FakeSession()
    session.gate = asyncio.Event()
    stream = make_stream(session, manual=True)

    task = asyncio.create_task(stream.connect())
    await asyncio.sleep(0)  # let connect() reach the gated session.get()

    stream.close()  # active=False while the GET is still in flight
    session.gate.set()  # now let the late response arrive
    await task

    results.append(
        check("a response arriving after close is not published", stream._response is None)
    )
    results.append(
        check(
            "a response arriving after close is closed, not leaked",
            len(session.responses) == 1 and session.responses[0].closed,
        )
    )


async def test_close_prevents_reconnect_after_backoff(results: list[bool]) -> None:
    session = FakeSession()
    stream = make_stream(session, manual=True)

    task = asyncio.create_task(stream.listen())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    results.append(check("initial connect happened", session.calls == 1))

    session.responses[0].content.fail(aiohttp.ClientError("boom"))
    await asyncio.sleep(0)  # let __anext__ observe the error and enter the backoff sleep

    results.append(
        check("the failed response was closed before backoff", session.responses[0].closed)
    )

    stream.close()  # cancel mid-backoff
    await drain_cancelled(task)

    results.append(
        check(
            "no reconnect attempt happens once closed during backoff",
            session.calls == 1,
            f"got {session.calls}",
        )
    )


async def test_restart_after_public_readd_with_internal_listener_present(
    results: list[bool],
) -> None:
    """An internal (bookkeeping-only) listener surviving auto-close must not
    block a later public listener from restarting the owned task."""
    session = FakeSession()
    stream = make_stream(session)

    # An internal listener alone must not itself start the task - only
    # public listeners drive connect/disconnect.
    remove_internal = stream.async_add_listener(lambda event: None, internal=True)
    results.append(
        check(
            "an internal-only listener does not start the owned task",
            stream._listen_task is None,
        )
    )

    remove_public = stream.async_add_listener(lambda event: None)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    results.append(
        check(
            "adding the first public listener connects",
            session.calls == 1,
            f"got {session.calls}",
        )
    )

    # Removing the last public listener auto-closes even though the
    # internal listener remains registered.
    remove_public()
    await asyncio.sleep(0)
    results.append(
        check(
            "removing the last public listener auto-closes despite the internal listener",
            not stream.active,
        )
    )

    # A later public listener, added while only the internal one remains
    # registered, must still restart the owned task - this is the bug: the
    # registry was non-empty (internal listener) so the old whole-registry
    # emptiness check never saw a zero-to-one transition.
    remove_public2 = stream.async_add_listener(lambda event: None)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    results.append(
        check(
            "re-adding a public listener afterwards reconnects",
            session.calls == 2,
            f"got {session.calls}",
        )
    )

    remove_public2()
    remove_internal()
    stream.close()
    await asyncio.sleep(0)


async def main() -> None:
    results: list[bool] = []
    await test_add_remove_readd_before_loop_runs(results)
    await test_two_explicit_listen_calls(results)
    await test_cancel_while_blocked_reading(results)
    await test_close_during_connect(results)
    await test_close_prevents_reconnect_after_backoff(results)
    await test_restart_after_public_readd_with_internal_listener_present(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
