from collections.abc import Callable
import aiohttp
import asyncio
import json
import logging
from datetime import datetime, timezone
from .const import TelemetryFields, TelemetryAlerts


LOGGER = logging.getLogger(__package__)


class TeslemetryStreamError(Exception):
    """Teslemetry Stream Error"""

    message = "An error occurred with the Teslemetry Stream."

    def __init__(self) -> None:
        super().__init__(self.message)


class TeslemetryStreamConnectionError(TeslemetryStreamError):
    """Teslemetry Stream Connection Error"""

    message = "An error occurred with the Teslemetry Stream connection."


class TeslemetryStreamVehicleNotConfigured(TeslemetryStreamError):
    """Teslemetry Stream Not Active Error"""

    message = "This vehicle is not configured to connect to Teslemetry."


class TeslemetryStream:
    """Teslemetry Stream Client"""

    fields: dict[TelemetryFields, dict[str, int]]
    alerts: list[TelemetryAlerts]
    _update_lock = asyncio.Lock()
    _response: aiohttp.ClientResponse | None = None
    _listeners: dict[Callable, Callable] = {}
    connected = False
    active = False

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        server: str | None = None,
        vin: str | None = None,
        parse_timestamp: bool = False,
    ):
        if not server and not vin:
            raise ValueError("Either server or VIN is required")

        if server and not server.endswith(".teslemetry.com"):
            raise ValueError("Server must be a teslemetry.com domain")

        self.vin = vin
        self.server = server
        self._session = session
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self.parse_timestamp = parse_timestamp

    async def get_config(self, vin: str | None = None) -> None:
        """Get the current stream config."""

        vin = vin or self.vin

        if not vin:
            raise ValueError("VIN is required")

        LOGGER.debug("Getting fleet telemetry config from %s", vin)
        req = await self._session.get(
            f"https://api.teslemetry.com/api/1/vehicles/{vin}/fleet_telemetry_config",
            headers=self._headers,
            raise_for_status=True,
        )
        response = (await req.json()).get("response")

        if (
            response and (config := response.get("config"))
            # and config["hostname"].endswith(".teslemetry.com")
        ):
            self.server = config["hostname"]
            self.fields = config["fields"]
            self.alerts = config["alert_types"]
        else:
            raise TeslemetryStreamVehicleNotConfigured()
        if not response.get("synced"):
            LOGGER.warning("Vehicle configuration not active")

    async def add_field(
        self, field: TelemetryFields, interval: int, update: bool = True
    ) -> None:
        """Add field to telemetry stream."""
        if not self.fields.get(field, {}).get("interval_seconds") == interval:
            self.fields[field] = {"interval_seconds": interval}
            if update:
                await self.update()

    async def remove_field(self, field: TelemetryFields, update: bool = True) -> None:
        """Remove field from telemetry stream."""
        if field in self.fields:
            del self.fields[field]
            if update:
                await self.update()

    async def add_alert(self, alert: TelemetryAlerts, update: bool = True) -> None:
        """Add alert to telemetry stream."""
        if alert not in self.alerts:
            self.alerts.append(alert)
            if update:
                await self.update()

    async def remove_alert(self, alert: TelemetryAlerts, update: bool = True) -> None:
        """Remove alert from telemetry stream."""
        if alert in self.alerts:
            self.alerts.remove(alert)
            if update:
                await self.update()

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return {
            "hostname": self.server,
            "fields": self.fields,
            "alerts": self.alerts,
        }

    async def update(self, wait: int = 1) -> None:
        """Update the telemetry stream."""
        if self._update_lock.locked():
            return
        with self._update_lock:
            await asyncio.sleep(wait)
            await self._session.post(
                f"https://api.teslemetry.com/api/telemetry/{self.vin}",
                headers=self._headers,
                json=self.config,
            )

    async def connect(self) -> None:
        """Connect to the telemetry stream."""
        if not self.server:
            await self.get_config()

        LOGGER.debug("Connecting to %s", self.server)
        self._response = await self._session.get(
            f"https://{self.server}/sse/{self.vin or ''}",
            headers=self._headers,
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(connect=5, sock_read=30, total=None),
        )
        self.connected = True
        LOGGER.debug(
            "Connected to %s with status %s", self._response.url, self._response.status
        )

    def close(self) -> None:
        """Close connection."""
        if self._response is not None:
            LOGGER.debug("Disconnecting from %s", self.server)
            self._response.close()
            self._response = None
            self.connected = False

    async def __aenter__(self) -> "TeslemetryStream":
        """Connect and listen Server-Sent Event."""
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        """Close connection."""
        self.close()

    def __aiter__(self):
        """Return"""
        return self

    async def __anext__(self) -> dict:
        """Return next event."""
        self.active = True
        if not self._response:
            await self.connect()
        try:
            async for line_in_bytes in self._response.content:
                line = line_in_bytes.decode("utf8")
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    if self.parse_timestamp:
                        main, _, ns = data["createdAt"].partition(".")
                        data["timestamp"] = int(
                            datetime.strptime(main, "%Y-%m-%dT%H:%M:%S")
                            .replace(tzinfo=timezone.utc)
                            .timestamp()
                        ) * 1000 + int(ns[:3])
                    LOGGER.debug("event %s", json.dumps(data))
                    return data
                continue
        except aiohttp.ClientConnectionError as error:
            raise StopAsyncIteration from error
        finally:
            self.active = False

    def async_add_listener(self, callback: Callable) -> Callable[[], None]:
        """Listen for data updates."""
        schedule_refresh = not self._listeners

        def remove_listener() -> None:
            """Remove update listener."""
            self._listeners.pop(remove_listener)
            if not self._listeners:
                self.close()

        self._listeners[remove_listener] = callback

        # This is the first listener, set up task.
        if schedule_refresh:
            asyncio.create_task(self.listen())

        return remove_listener

    async def listen(self):
        """Listen to the telemetry stream."""
        async for event in self:
            if event:
                for listener in self._listeners.values():
                    listener(event)
