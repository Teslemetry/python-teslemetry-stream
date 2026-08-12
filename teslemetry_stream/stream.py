from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
from typing import Any, cast

import aiohttp

from .energysite import TeslemetryStreamEnergySite
from .exception import TeslemetryStreamEnded
from .vehicle import TeslemetryStreamVehicle

LOGGER = logging.getLogger(__package__)


class TeslemetryStream:
    """Teslemetry Stream Client"""

    _response: aiohttp.ClientResponse | None = None
    # Bumped each time connect() installs a new response - lets a vehicle
    # tell "this connection's config snapshot has been applied" apart from
    # "some past connection's was".
    _connection_id: int = 0

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str | Callable[[], Awaitable[str | None]],
        server: str = "api.teslemetry.com",
        vin: str | None = None,
        parse_timestamp: bool = False,
        manual: bool = False,
        topics: str | Iterable[str] | None = None,
    ):
        """
        Initialize the TeslemetryStream client.

        :param session: An aiohttp ClientSession.
        :param access_token: Access token for authentication.
        :param server: Teslemetry server to connect to.
        :param vin: Vehicle Identification Number.
        :param parse_timestamp: Whether to parse timestamps.
        :param manual: Whether to start listening manually.
        :param topics: Exact SSE wire event names (see `SseTopic` and its
            presets in `const.py`) to subscribe to - a single topic or an
            iterable of them. Omitting this (`None`) preserves legacy-all
            behavior: every applicable event is delivered unfiltered,
            forever. An explicitly empty iterable is rejected - it means
            "no topics", not "all topics", mirroring the server's own 400
            on an empty `topics` value.
        """
        if server and not server.endswith(".teslemetry.com"):
            raise ValueError("Server must be on the teslemetry.com domain")

        self.active: bool = False
        self.server = server
        self.vin = vin
        self.topics: list[str] | None
        if topics is not None:
            # A bare str (or SseTopic, itself a str) is iterable character-by-character -
            # wrap it as a single topic rather than silently splitting it into letters.
            self.topics = [topics] if isinstance(topics, str) else list(topics)
            if not self.topics:
                raise ValueError(
                    "topics must not be empty - omit it (None) for legacy-all behavior"
                )
        else:
            self.topics = None
        self._listeners: dict[
            Callable[..., Any],
            tuple[Callable[[dict[str, Any]], None], dict[str, Any] | None, bool],
        ] = {}
        self._connection_listeners: dict[Callable[..., Any], Callable[[bool], None]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        # Created lazily in connect() - asyncio.Lock() requires a running
        # loop on Python 3.9, and streams are commonly built before one.
        self._connect_lock: asyncio.Lock | None = None
        self._session = session
        self.access_token = access_token
        self.parse_timestamp = parse_timestamp
        self.manual = manual
        self.retries: int = 0
        self.vehicles: dict[str, TeslemetryStreamVehicle] = {}
        self.energysites: dict[str, TeslemetryStreamEnergySite] = {}
        self.fields: dict[str, Any] = {}

        if self.vin:
            self.vehicle: TeslemetryStreamVehicle = self.get_vehicle(self.vin)
            self.vehicles[self.vin] = self.vehicle

    async def headers(self) -> dict[str, str]:
        if callable(self.access_token):
            access_token = await self.access_token()
        else:
            access_token = self.access_token
        return {
            "Authorization": f"Bearer {access_token}",
            "X-Library": "python teslemetry-stream",
        }

    def get_vehicle(self, vin: str) -> TeslemetryStreamVehicle:
        """
        Create a vehicle stream.

        :param vin: Vehicle Identification Number.
        :return: TeslemetryStreamVehicle instance.
        """
        if vin not in self.vehicles:
            self.vehicles[vin] = TeslemetryStreamVehicle(self, vin)
        return self.vehicles[vin]

    def get_energysite(self, site_id: str | int) -> TeslemetryStreamEnergySite:
        """
        Create an energy site stream.

        :param site_id: Numeric energy site ID.
        :return: TeslemetryStreamEnergySite instance.
        """
        site_id = str(site_id)
        if site_id not in self.energysites:
            self.energysites[site_id] = TeslemetryStreamEnergySite(self, site_id)
        return self.energysites[site_id]

    @property
    def connected(self) -> bool:
        """
        Return if connected.

        :return: True if connected, False otherwise.
        """
        return self._response is not None

    async def get_config(self, vin: str | None = None) -> None:
        """
        Get the current stream config.

        :param vin: Vehicle Identification Number.
        """
        if not self.server:
            await self.find_server()
        if hasattr(self, "vehicle"):
            await self.vehicle.get_config()

    async def find_server(self) -> None:
        """
        Find the server using metadata.
        """
        headers = await self.headers()
        req = await self._session.get(
            "https://api.teslemetry.com/api/metadata",
            headers=headers,
            raise_for_status=True,
        )
        response = await req.json()
        self.server = f"{response['region'].lower()}.teslemetry.com"

    async def update_fields(self, fields: dict[str, Any], vin: str) -> dict[str, Any]:
        """
        Update Fleet Telemetry configuration.

        :param fields: Dictionary of fields to update.
        :param vin: Vehicle Identification Number.
        :return: Response JSON as a dictionary.
        """
        headers = await self.headers()
        resp = await self._session.patch(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=headers,
            json={"fields": fields},
            raise_for_status=False,
        )
        if resp.ok:
            self.fields = {**self.fields, **fields}
        return cast(dict[str, Any], await resp.json())

    async def replace_fields(self, fields: dict[str, Any], vin: str) -> dict[str, Any]:
        """
        Replace Fleet Telemetry configuration.

        :param fields: Dictionary of fields to replace.
        :param vin: Vehicle Identification Number.
        :return: Response JSON as a dictionary.
        """
        headers = await self.headers()
        resp = await self._session.post(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=headers,
            json={"fields": fields},
            raise_for_status=False,
        )
        if resp.ok:
            self.fields = fields
        return cast(dict[str, Any], await resp.json())

    @property
    def config(self) -> dict[str, Any]:
        """
        Return current configuration.

        :return: Configuration dictionary.
        """
        return {
            "hostname": self.server,
        }

    def async_add_connection_listener(
        self, callback: Callable[[bool], None]
    ) -> Callable[[], None]:
        """
        Listen for connection state changes.

        :param callback: Callback function to handle connection state changes.
        :return: Function to remove the listener.
        """

        def remove_listener() -> None:
            """
            Remove connection listener.
            """
            self._connection_listeners.pop(remove_listener)

        self._connection_listeners[remove_listener] = callback

        return remove_listener

    def _update_connection_listeners(self, value: bool | None = None) -> None:
        """Update all connection listeners with retry count"""
        for listener in self._connection_listeners.values():
            listener(self.connected if value is None else value)

    async def connect(self) -> None:
        """
        Connect to the telemetry stream.
        """
        self.active = True
        if not self.server:
            await self.get_config()

        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()
        async with self._connect_lock:
            if not self.active:
                # Stopped while waiting for the lock; a concurrent caller may
                # already be connected, or a stop was requested outright.
                return

            LOGGER.debug("Connecting to %s", self.server)
            url = f"https://{self.server}/sse"
            if self.vin:
                url += f"/{self.vin}"
            headers = await self.headers()
            params = {"topics": ",".join(self.topics)} if self.topics else None
            response = await self._session.get(
                url,
                headers=headers,
                params=params,
                raise_for_status=True,
                timeout=aiohttp.ClientTimeout(
                    connect=5, sock_connect=5, sock_read=30, total=None
                ),
                chunked=True,
            )
            if not self.active:
                # Stopped while the request was in flight - discard it rather
                # than publish a response nobody will ever close.
                response.close()
                return
            if self._response is not None:
                self._response.close()
            self._response = response
            self._connection_id += 1
            LOGGER.debug(
                "Connected to %s with status %s", self._response.url, self._response.status
            )
            self.retries = 0
            self._update_connection_listeners(True)

    def disconnect(self) -> None:
        """
        Disconnect from the telemetry stream.
        """
        self.close()

    def _close_response(self) -> None:
        """
        Close the current response, if any, without changing whether the
        stream is meant to keep running - used by reconnect paths and by
        listen()'s cleanup, as opposed to close()'s full stop.
        """
        if self._response is not None:
            LOGGER.debug("Disconnecting from %s", self.server)
            self._response.close()
            self._response = None
            self._update_connection_listeners(False)

    def close(self) -> None:
        """
        Stop the stream: closes the response and cancels the owned listen
        task so a running listener does not immediately reconnect.
        """
        self.active = False
        task, self._listen_task = self._listen_task, None
        if task is not None and not task.done():
            task.cancel()
        self._close_response()

    def __aiter__(self) -> TeslemetryStream:
        """
        Return an asynchronous iterator.

        :return: Asynchronous iterator.
        """

        self.active = True
        return self

    async def __anext__(self) -> dict[str, Any]:
        """
        Return next event.

        :return: Next event as a dictionary.
        :raises StopAsyncIteration: If the stream is stopped.
        :raises TeslemetryStreamEnded: If the stream is ended by the server.
        """
        while self.active:
            try:
                if not self._response:
                    # Connect to the stream
                    await self.connect()
                assert self._response
                async for line_in_bytes in self._response.content:
                    field, _, value = line_in_bytes.decode("utf8").partition(": ")
                    if field == "data":
                        data = json.loads(value)
                        if self.parse_timestamp:
                            main, _, ns = data["createdAt"].partition(".")
                            data["timestamp"] = int(
                                datetime.strptime(main, "%Y-%m-%dT%H:%M:%S")
                                .replace(tzinfo=timezone.utc)
                                .timestamp()
                            ) * 1000 + int(ns[:3])
                        return cast(dict[str, Any], data)
                raise TeslemetryStreamEnded()
            except StopAsyncIteration as e:
                # Re-raise explicitly so it isn't caught by the generic Exception handler below
                self.disconnect()
                raise e
            except TeslemetryStreamEnded:
                LOGGER.warning("Stream ended by server")
                self._close_response()
            except aiohttp.ClientError as error:
                LOGGER.warning("Client error: %s", repr(error))
                self._close_response()
                delay = min(2**self.retries, 600)
                LOGGER.debug("Reconnecting in %s seconds", delay)
                await asyncio.sleep(delay)
                self.retries += 1
            except Exception as error:
                LOGGER.error("Unexpected error: %s", repr(error))
                self._close_response()
                LOGGER.debug("Reconnecting in %s seconds", 1)
                await asyncio.sleep(1)

        raise StopAsyncIteration

    def async_add_listener(
        self,
        callback: Callable[[dict[str, Any]], None],
        filters: dict[str, Any] | None = None,
        internal: bool = False,
    ) -> Callable[[], None]:
        """
        Listen for data updates.

        :param callback: Callback function to handle updates.
        :param filters: Filters to apply to the updates.
        :param internal: True for a listener that keeps the client's own
            state fresh (e.g. a vehicle's config-sync listener) rather than
            serving a consumer callback. Excluded from both the "first
            listener" start check and the "last listener removed" auto-close
            check - on either side of the registry, only public listeners
            count - so a bookkeeping-only listener can neither pin the
            connection open forever nor, by itself, block a later public
            listener from restarting a closed one.
        :return: Function to remove the listener.
        """

        def has_public_listener() -> bool:
            return any(not is_internal for _, _, is_internal in self._listeners.values())

        # A transition from zero to one *public* listeners, not merely a
        # non-empty registry - an internal listener surviving a prior
        # auto-close must not block a later public listener from restarting
        # the owned task.
        schedule_refresh = not internal and not has_public_listener()

        def remove_listener() -> None:
            """
            Remove update listener.
            """
            self._listeners.pop(remove_listener)
            if not has_public_listener():
                LOGGER.info("Shutting down stream as there are no more listeners")
                self.close()

        self._listeners[remove_listener] = (callback, filters, internal)

        # This is the first public listener - start the owned listen task,
        # unless one is already running or manual mode delegates that to the
        # caller.
        if (
            schedule_refresh
            and not self.manual
            and (self._listen_task is None or self._listen_task.done())
        ):
            self._listen_task = asyncio.create_task(self.listen())

        return remove_listener

    async def listen(self) -> None:
        """
        Listen to the telemetry stream.

        A second concurrent call joins the already-running owned task
        instead of starting a competing reader on the same connection.
        """
        current_task = asyncio.current_task()
        existing_task = self._listen_task
        if (
            existing_task is not None
            and not existing_task.done()
            and existing_task is not current_task
        ):
            await existing_task
            return

        self._listen_task = current_task
        try:
            async for event in self:
                if event:
                    # A snapshot, not a live view - a callback that creates a
                    # vehicle (get_vehicle) or otherwise adds a listener
                    # mid-dispatch must not mutate _listeners while this is
                    # iterating it, which would raise RuntimeError and kill
                    # the loop. Internal (bookkeeping) listeners go first, so
                    # one can cache from the pristine event before any public
                    # callback gets a chance to mutate it in place.
                    ordered = sorted(self._listeners.values(), key=lambda item: not item[2])
                    for listener, filters, _internal in ordered:
                        if recursive_match(filters, event):
                            try:
                                listener(event)
                            except Exception as error:
                                LOGGER.error("Uncaught error in listener: %s", error)
        finally:
            self._close_response()
            if self._listen_task is current_task:
                self._listen_task = None
        LOGGER.debug("Listen has finished")

    def listen_Credits(
        self, callback: Callable[[dict[str, str | int]], None]
    ) -> Callable[[], None]:
        """
        Listen for credits update.

        :param callback: Callback function to handle credits update.
        :return: Function to remove the listener.
        """
        return self.async_add_listener(
            lambda x: callback(x["credits"]), {"credits": None}
        )

    def listen_Balance(self, callback: Callable[[int], None]) -> Callable[[], None]:
        """
        Listen for credits balance.

        :param callback: Callback function to handle credits balance.
        :return: Function to remove the listener.
        """
        return self.async_add_listener(
            lambda x: callback(x["credits"]["balance"]), {"credits": {"balance": None}}
        )


def recursive_match(dict1: dict[str, Any] | None, dict2: dict[str, Any]) -> bool:
    """
    Recursively match dict1 with dict2.

    :param dict1: First dictionary.
    :param dict2: Second dictionary.
    :return: True if dict1 matches dict2, False otherwise.
    """
    if dict1 is not None:
        for key, value1 in dict1.items():
            if key not in dict2:
                # A required key isn't present
                return False
            value2 = dict2[key]
            if isinstance(value1, dict):
                # Check the next level of the dict
                if not recursive_match(value1, value2):
                    return False
            elif isinstance(value1, list):
                # Check each dict in the list
                if not all(
                    any(recursive_match(item1, item2) for item2 in value2)
                    for item1 in value1
                ):
                    return False
            elif value1 is not None and value1 != value2:
                # Check the value matches
                return False
    # No differences found
    return True
