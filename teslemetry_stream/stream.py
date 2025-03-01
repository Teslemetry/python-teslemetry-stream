from collections.abc import Callable
import aiohttp
import asyncio
import json
import logging
from datetime import datetime, timezone

from .vehicle import TeslemetryStreamVehicle
from .exception import TeslemetryStreamEnded

DELAY = 1
LOGGER = logging.getLogger(__package__)

class TeslemetryStream:
    """Teslemetry Stream Client"""

    _response: aiohttp.ClientResponse | None = None
    _listeners: dict[Callable, Callable]
    delay: int
    active = None
    vehicle: TeslemetryStreamVehicle
    vehicles: dict[str, TeslemetryStreamVehicle] = {}

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        server: str | None = None,
        vin: str | None = None,
        parse_timestamp: bool = False,
    ):
        if server and not server.endswith(".teslemetry.com"):
            raise ValueError("Server must be on the teslemetry.com domain")

        self.server = server
        self.vin = vin
        self._listeners = {}
        self._session = session
        self._headers = {"Authorization": f"Bearer {access_token}", "X-Library": "python teslemetry-stream"}
        self.parse_timestamp = parse_timestamp
        self.delay = DELAY

        if(self.vin):
            self.vehicle = self.get_vehicle(self.vin)

    def get_vehicle(self, vin: str) -> TeslemetryStreamVehicle:
        """Create a vehicle stream."""
        if self.vin is not None and self.vin != vin:
            raise AttributeError("Stream started in single vehicle mode")
        if vin not in self.vehicles:
            self.vehicles[vin] = TeslemetryStreamVehicle(self, vin)
        return self.vehicles[vin]

    @property
    def connected(self) -> bool:
        """Return if connected."""
        return self._response is not None

    async def get_config(self, vin: str | None = None) -> None:
        """Get the current stream config."""
        if not self.server:
            await self.find_server()
        if hasattr(self, 'vehicle'):
            await self.vehicle.get_config()

    async def find_server(self) -> None:
        """Find the server using metadata."""

        req = await self._session.get(
            "https://api.teslemetry.com/api/metadata",
            headers=self._headers,
            raise_for_status=True,
        )
        response = await req.json()
        self.server = f"{response["region"].lower()}.teslemetry.com"



    async def update_fields(self, fields: dict, vin: str) -> dict:
        """Update Fleet Telemetry configuration"""
        resp = await self._session.patch(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=self._headers,
            json={"fields": fields},
            raise_for_status=False,
        )
        if resp.ok:
            self.fields = {**self.fields, **fields}
        return await resp.json()

    async def replace_fields(self, fields: dict, vin: str) -> dict:
        """Replace Fleet Telemetry configuration"""
        resp = await self._session.post(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=self._headers,
            json={"fields": fields},
            raise_for_status=False,
        )
        if resp.ok:
            self.fields = fields
        return await resp.json()

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return {
            "hostname": self.server,
        }

    async def connect(self) -> None:
        """Connect to the telemetry stream."""
        self.active = True
        if not self.server:
            await self.get_config()

        LOGGER.debug("Connecting to %s", self.server)
        self._response = await self._session.get(
            f"https://{self.server}/sse/{self.vin or ''}",
            headers=self._headers,
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(
                connect=5, sock_connect=5, sock_read=30, total=None
            ),
        )
        LOGGER.debug(
            "Connected to %s with status %s", self._response.url, self._response.status
        )

    def close(self) -> None:
        """Close connection."""
        if self._response is not None:
            LOGGER.debug("Disconnecting from %s", self.server)
            self._response.close()
            self._response = None

    def __aiter__(self):
        """Return"""
        return self

    async def __anext__(self) -> dict:
        """Return next event."""
        try:
            if self.active is False:
                # Stop the stream and loop
                self.close()
                raise StopAsyncIteration
            if not self._response:
                # Connect to the stream
                await self.connect()
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
                    # LOGGER.debug("event %s", json.dumps(data))
                    self.delay = DELAY
                    return data
            raise TeslemetryStreamEnded()
        except (TeslemetryStreamEnded, aiohttp.ClientError) as error:
            LOGGER.warning("Connection error: %s", error)
            self.close()
            LOGGER.debug("Reconnecting in %s seconds", self.delay)
            await asyncio.sleep(self.delay)
            self.delay += self.delay

    def async_add_listener(
        self, callback: Callable, filters: dict | None = None
    ) -> Callable[[], None]:
        """Listen for data updates."""
        schedule_refresh = not self._listeners

        def remove_listener() -> None:
            """Remove update listener."""
            self._listeners.pop(remove_listener)
            if not self._listeners:
                self.active = False

        self._listeners[remove_listener] = (callback, filters)

        # This is the first listener, set up task.
        if schedule_refresh:
            asyncio.create_task(self.listen())

        return remove_listener

    async def listen(self):
        """Listen to the telemetry stream."""

        async for event in self:
            if event:
                for listener, filters in self._listeners.values():
                    if recursive_match(filters, event):
                        try:
                            listener(event)
                        except Exception as error:
                            LOGGER.error("Uncaught error in listener: %s", error)
        LOGGER.debug("Listen has finished")

    def listen_Credits(self, callback: Callable[[dict[str, str | int]], None]) -> Callable[[], None]:
        """Listen for credits update."""

        return self.async_add_listener(
            lambda x: callback(x["credits"]),
            {"credits": None}
        )

    def listen_Balance(self, callback: Callable[[int], None]) -> Callable[[], None]:
        """Listen for credits balance."""

        return self.async_add_listener(
            lambda x: callback(x["credits"]["balance"]),
            {"credits": {"balance": None}}
        )

def recursive_match(dict1, dict2):
    """Recursively match dict1 with dict2."""
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
            elif value1 is not None:
                # Check the value matches
                if value1 != value2:
                    return False
    # No differences found
    return True
