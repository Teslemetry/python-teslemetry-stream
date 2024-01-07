import aiohttp
import asyncio
import json
from .const import TelemetryFields, TelemetryAlerts

SERVER = "http://192.168.1.3:4443"


class TeslemetryStream:
    """Teslemetry Stream Client"""

    fields: dict[TelemetryFields, dict[str, int]]
    alerts: list[TelemetryAlerts]
    _update_lock: bool = False
    _response: aiohttp.ClientResponse | None = None

    def __init__(self, session: aiohttp.ClientSession, vin: str, access_token: str):
        self._session = session
        self.vin = vin
        self._headers = {"Authorization": f"Bearer {access_token}"}

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
        return {"fields": self.fields, "alerts": self.alerts}

    async def update(self, wait: int = 1) -> None:
        """Update the telemetry stream."""
        if self._update_lock:
            return
        self._update_lock = True
        await asyncio.sleep(wait)
        await self._session.patch(
            f"{SERVER}/{self.vin}",
            headers=self._headers,
            json=self.config,
        )
        self._update_lock = False

    async def connect(self) -> None:
        """Connect to the telemetry stream."""

        self._response = await self._session.post(
            f"{SERVER}/{self.vin}",
            headers=self._headers,
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(connect=5, sock_read=30, total=None),
        )

    async def listen(self, callback):
        """Listen to the telemetry stream."""
        async for event in self:
            callback(event)

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
                print(line)
                if line.startswith("data:"):
                    return json.loads(line[5:])
                continue
        except aiohttp.ClientConnectionError as error:
            raise StopAsyncIteration from error
