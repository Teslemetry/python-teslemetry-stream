import aiohttp
import asyncio
import json
import logging
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

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        server: str | None = None,
        vin: str | None = None,
    ):
        if not server and not vin:
            raise ValueError("Either server or VIN is required")

        if server and not server.endswith(".teslemetry.com"):
            raise ValueError("Server must be a teslemetry.com domain")

        self.vin = vin
        self.server = server
        self._session = session
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def get_config(self) -> None:
        """Get the current stream config."""

        req = await self._session.get(
            f"https://api.teslemetry.com/api/1/vehicles/{self.vin}/fleet_telemetry_config",
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
            LOGGER.debug("No server, getting config")
            await self.get_config()

        LOGGER.debug("Connecting to %s", self.server)
        self._response = await self._session.get(
            f"https://{self.server}/sse/{self.vin or ''}",
            headers=self._headers,
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(connect=5, sock_read=30, total=None),
        )
        LOGGER.debug(
            "Connected to %s with status %s", self._response.url, self._response.status
        )

    async def listen(self, callback):
        """Listen to the telemetry stream."""
        async for event in self:
            await callback(event)

    async def close(self) -> None:
        """Close connection."""
        if self._response is not None:
            self._response.close()
            self._response = None

    async def __aenter__(self) -> "TeslemetryStream":
        """Connect and listen Server-Sent Event."""
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        """Close connection."""
        await self.close()

    def __aiter__(self):
        """Return"""
        return self

    async def __anext__(self) -> dict:
        """Return next event."""
        if not self._response:
            await self.connect()
        try:
            async for line_in_bytes in self._response.content:
                line = line_in_bytes.decode("utf8")
                if line.startswith("data:"):
                    LOGGER.debug("Received: %s", line[5:])
                    return json.loads(line[5:])
                continue
        except aiohttp.ClientConnectionError as error:
            raise StopAsyncIteration from error
