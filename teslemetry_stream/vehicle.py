from typing import TYPE_CHECKING
import asyncio
import logging

from .const import Signal

if TYPE_CHECKING:
    from .stream import TeslemetryStream
else:
    TeslemetryStream = None

LOGGER = logging.getLogger(__package__)

class TeslemetryStreamVehicle:
    """Handle streaming field updates."""

    fields: dict[Signal, dict[str, int]] = {}
    preferTyped: bool | None = None
    _config: dict = {}

    def __init__(self, stream: TeslemetryStream, vin: str):
        # A dictionary of TelemetryField keys and null values
        self.stream = stream
        self.vin: str = vin
        self.lock = asyncio.Lock()

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return {
            "fields": self.fields,
            "prefer_typed": self.preferTyped,
        }

    async def get_config(self) -> None:
        """Get the current configuration for the vehicle."""

        req = await self.stream._session.get(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=self.stream._headers,
            raise_for_status=True,
        )
        response = await req.json()

        self.fields = response.get("fields")
        self.preferTyped = response.get("prefer_typed",False)

    async def update_config(self, config: dict) -> None:
        """Update the configuration for the vehicle."""

        # Lock so that we dont change the config while making the API call
        async with self.lock:
            self._config = merge(config, self._config)

        await asyncio.sleep(1)

        async with self.lock:
            if not self._config:
                return

            data = await self.patch_config(self._config)
            if error := data.get("error"):
                LOGGER.error("Error updating streaming config for %s: %s", self.vin, error)
                return
            elif data.get("response",{}).get("updated_vehicles"):
                LOGGER.info("Updated vehicle streaming config for %s", self.vin)
                if fields := self._config.get("fields"):
                    LOGGER.debug("Configured streaming fields %s", ", ".join(fields.keys()))
                    self.fields = {**self.fields, **fields}
                if prefer_typed := self._config.get("prefer_typed") in [True, False]:
                    LOGGER.debug("Configured streaming typed to %s", prefer_typed)
                    self.preferTyped = prefer_typed
                self._config.clear()


    async def patch_config(self, config: dict) -> dict[str, str|dict]:
        """Modify the configuration for the vehicle."""
        resp = await self.stream._session.patch(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=self.stream._headers,
            json=config,
            raise_for_status=False,
        )
        return await resp.json()

    async def post_config(self, config: dict) -> dict[str, str|dict]:
        """Overwrite the configuration for the vehicle."""
        resp = await self.stream._session.post(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=self.stream._headers,
            json=config,
            raise_for_status=False,
        )
        return await resp.json()

    async def add_field(self, field: Signal | str, interval: int | None = None) -> None:
        """Handle vehicle data from the stream."""
        if isinstance(field, Signal):
            field = field.value

        if field in self.fields and (interval is None or self.fields[field].get("interval_seconds") == interval):
            LOGGER.debug("Streaming field %s already enabled @ %ss", field, self.fields[field].get('interval_seconds'))
            return

        value = {"interval_seconds": interval} if interval else None
        await self.update_config({"fields": {field: value}})

    async def prefer_typed(self, prefer_typed: bool) -> None:
        """Set prefer typed."""
        if self.preferTyped == prefer_typed:
            LOGGER.debug("Streaming typed already set to %s", prefer_typed)
            return
        await self.update_config({"prefer_typed": prefer_typed})

def merge(source, destination):
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            merge(value, node)
        else:
            destination[key] = value

    return destination
