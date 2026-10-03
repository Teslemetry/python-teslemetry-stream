"""Tests for Teslemetry for Business API keys (`sk_...`).

A business key may not call /api/metadata or open the account-wide /sse
stream (403 business_route_not_allowed), so the stream must find the region
host of its one product in GET /api/business/products, fail clearly when it
cannot, and reconnect when the server ends a business stream after its
fixed 5-minute lifetime. Consumer tokens must behave exactly as before.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from teslemetry_stream import TeslemetryStreamBusinessKeyError
from teslemetry_stream.stream import LOGGER, TeslemetryStream, is_business_key

VIN = "5YJ3E1EA1JF000001"
BUSINESS_KEY = "sk_live_test"
PRODUCTS = {
    "response": [
        {
            "product_type": "vehicle",
            "product_id": "5YJ3E1EA1JF000009",
            "region": "NA",
            "customer": {"id": "a", "ref": None},
            "granted_at": "2026-10-01T00:00:00.000Z",
        },
        {
            "product_type": "vehicle",
            "product_id": VIN,
            "region": "EU",
            "customer": {"id": "b", "ref": None},
            "granted_at": "2026-10-01T00:00:00.000Z",
        },
    ]
}


class FakeContent:
    """Async-iterable SSE body that blocks until ended cleanly."""

    def __init__(self) -> None:
        self._blocker: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def __aiter__(self) -> FakeContent:
        return self

    async def __anext__(self) -> bytes:
        await self._blocker
        raise StopAsyncIteration

    def end(self) -> None:
        if not self._blocker.done():
            self._blocker.set_result(None)


class FakeResponse:
    def __init__(self, url: str, body: Any = None) -> None:
        self.url = url
        self.status = 200
        self.ok = True
        self.body = body
        self.content = FakeContent()
        self.closed = False

    async def json(self) -> Any:
        return self.body

    def close(self) -> None:
        self.closed = True


class FakeSession:
    """Answers the JSON routes and records every GET url."""

    def __init__(self, products: Any = PRODUCTS) -> None:
        self.urls: list[str] = []
        self.sse: list[FakeResponse] = []
        self.products = products

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.urls.append(url)
        if url.endswith("/api/metadata"):
            return FakeResponse(url, {"region": "NA"})
        if url.endswith("/api/business/products"):
            return FakeResponse(url, self.products)
        if "/api/config/" in url:
            return FakeResponse(url, {"response": {"fields": {}}})
        response = FakeResponse(url)
        self.sse.append(response)
        return response


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<72} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def drain(task: asyncio.Task[Any]) -> BaseException | None:
    with contextlib.suppress(asyncio.CancelledError):
        try:
            await task
        except Exception as error:
            return error
    return None


async def test_detection(results: list[bool]) -> None:
    results.append(check("sk_ prefix is a business key", is_business_key("sk_abc")))
    results.append(check("a consumer token is not", not is_business_key("abc.def")))
    results.append(check("None is not", not is_business_key(None)))


async def test_consumer_unchanged(results: list[bool]) -> None:
    session = FakeSession()
    stream = TeslemetryStream(session, "consumer-token", server="", vin=VIN, manual=True)  # type: ignore[arg-type]
    await stream.find_server()
    results.append(
        check("consumer token still uses /api/metadata", session.urls[-1].endswith("/api/metadata"))
    )
    results.append(check("consumer server from metadata", stream.server == "na.teslemetry.com"))

    session = FakeSession()
    stream = TeslemetryStream(session, "consumer-token", vin=VIN, manual=True)  # type: ignore[arg-type]
    await stream.connect()
    results.append(
        check(
            "consumer token on the default host makes no listing call",
            session.urls == [f"https://api.teslemetry.com/sse/{VIN}"],
            f"got {session.urls}",
        )
    )
    stream.close()


async def test_business_find_server(results: list[bool]) -> None:
    session = FakeSession()
    stream = TeslemetryStream(session, BUSINESS_KEY, server="", vin=VIN, manual=True)  # type: ignore[arg-type]
    await stream.connect()
    results.append(
        check(
            "business key never calls /api/metadata",
            not any(u.endswith("/api/metadata") for u in session.urls),
            f"got {session.urls}",
        )
    )
    results.append(
        check("business server is the VIN's region", stream.server == "eu.teslemetry.com")
    )
    results.append(
        check(
            "business stream opens /sse/<vin> on the region host",
            session.urls[-1] == f"https://eu.teslemetry.com/sse/{VIN}",
            f"got {session.urls[-1]}",
        )
    )
    stream.close()


async def test_business_default_host_and_lifetime(results: list[bool]) -> None:
    session = FakeSession()

    async def token() -> str:
        return BUSINESS_KEY

    stream = TeslemetryStream(session, token, vin=VIN, manual=True)  # type: ignore[arg-type]
    states: list[bool] = []
    stream.async_add_connection_listener(states.append)
    with CaptureLogs() as records:
        task = asyncio.create_task(stream.listen())
        await settle()
        results.append(
            check(
                "callable business key on the default host goes to the region host",
                session.urls[-1] == f"https://eu.teslemetry.com/sse/{VIN}",
                f"got {session.urls}",
            )
        )
        # The server ends a business stream after its 5-minute lifetime.
        session.sse[0].content.end()
        await settle()

    sse_urls = [u for u in session.urls if "/sse/" in u]
    results.append(
        check(
            "a lifetime end reconnects to the same product",
            sse_urls == [f"https://eu.teslemetry.com/sse/{VIN}"] * 2,
            f"got {sse_urls}",
        )
    )
    results.append(
        check(
            "the product listing is read once, not on every reconnect",
            sum(u.endswith("/api/business/products") for u in session.urls) == 1,
        )
    )
    results.append(check("the stream is still active", stream.active))
    results.append(
        check("listeners saw down then up", states == [True, False, True], f"got {states}")
    )
    results.append(
        check(
            "a lifetime end does not log at INFO or above",
            not [r for r in records if r.levelno >= logging.INFO],
            f"got {[r.getMessage() for r in records if r.levelno >= logging.INFO]}",
        )
    )
    stream.close()
    await drain(task)


async def test_business_not_shared(results: list[bool]) -> None:
    session = FakeSession(products={"response": []})
    stream = TeslemetryStream(session, BUSINESS_KEY, vin=VIN, manual=True)  # type: ignore[arg-type]
    states: list[bool] = []
    stream.async_add_connection_listener(states.append)
    task = asyncio.create_task(stream.listen())
    await settle()
    error = await asyncio.wait_for(drain(task), 1)
    results.append(
        check(
            "an unshared VIN raises TeslemetryStreamBusinessKeyError",
            isinstance(error, TeslemetryStreamBusinessKeyError) and VIN in str(error),
            f"got {error!r}",
        )
    )
    results.append(
        check("and stops instead of retrying", not stream.active and len(session.urls) == 1)
    )
    results.append(check("and reports the connection down", states == [False], f"got {states}"))


async def test_business_without_vin(results: list[bool]) -> None:
    try:
        TeslemetryStream(FakeSession(), BUSINESS_KEY)  # type: ignore[arg-type]
        raised = False
    except ValueError:
        raised = True
    results.append(check("a str business key without vin is rejected at construction", raised))

    async def token() -> str:
        return BUSINESS_KEY

    session = FakeSession()
    stream = TeslemetryStream(session, token, server="", manual=True)  # type: ignore[arg-type]
    try:
        await stream.find_server()
        error: BaseException | None = None
    except TeslemetryStreamBusinessKeyError as e:
        error = e
    results.append(
        check(
            "a callable business key without vin fails clearly in find_server",
            error is not None and session.urls == [],
            f"got {error!r} {session.urls}",
        )
    )


class CaptureLogs:
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
    await test_detection(results)
    await test_consumer_unchanged(results)
    await test_business_find_server(results)
    await test_business_default_host_and_lifetime(results)
    await test_business_not_shared(results)
    await test_business_without_vin(results)

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
