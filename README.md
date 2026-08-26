# Teslemetry Stream Library
This is an asynchronous Python 3 library that connects to the Teslemetry Stream service and provides Tesla Fleet Telemetry using server sent events. The library allows you to listen to various telemetry signals from Tesla vehicles, and provides a convenient way to handle these signals using typed listen methods.

## Capabilities
- Connect to the Teslemetry Stream service
- Listen to various telemetry signals from Tesla vehicles
- Handle signals using typed listen methods
- Write custom listeners for multiple signals
- Ingest observations from other sources into the same listeners

## Installation

`pip install teslemetry-stream`

## Usage

The TeslemetryStream class requires:

- session: an aiohttp.ClientSession
- access_token: an access token from the [Teslemetry console](https://teslemetry.com/console)
- vin: If you only want to use a single vehicle, otherwise use `create_vehicle`
- server: Override the Teslemetry server to connect to:
  - api.teslemetry.com (recommended and default)
  - na.teslemetry.com
  - eu.teslemetry.com

The full list of possible values are provided in `TelemetryFields` and `TelemetryAlerts`

The simplest way to connect is to register a callback with `async_add_listener`: it connects automatically when the first listener is added, and disconnects when the last one is removed - no explicit `connect()`/`close()` call needed.

If you want to manage the connection yourself instead, call `connect()` and drive the stream with `listen()`; in that case you are responsible for calling `close()` when done.

## Example
The following example puts the listening loop in the background, then stopping after 20 seconds.
```
async def main():
    async with aiohttp.ClientSession() as session:
        stream = TeslemetryStream(
            access_token="<token>",
            vin="<vin>", # for single vehicles
            server="na.teslemetry.com" # or "eu.teslemetry.com"
            session=session,
        )

        def callback(event):
            print(event["data"])

        remove = stream.async_add_listener(callback)

        print("Running")
        await asyncio.sleep(60)
        remove()
```

## Using Typed Listen Methods

The library provides typed listen methods for various telemetry signals. These methods allow you to listen to specific signals and handle their data in a type-safe manner. Here is an example of using the typed listen methods:

```python
async def main():
    async with aiohttp.ClientSession() as session:
        stream = TeslemetryStream(
            access_token="<token>",
            vin="<vin>", # for single vehicles
            session=session,
        )

        vehicle = stream.get_vehicle("<vin>")

        def battery_level_callback(battery_level):
            print(f"Battery Level: {battery_level}")

        def vehicle_speed_callback(vehicle_speed):
            print(f"Vehicle Speed: {vehicle_speed}")

        remove_battery_level_listener = vehicle.listen_BatteryLevel(battery_level_callback)
        remove_vehicle_speed_listener = vehicle.listen_VehicleSpeed(vehicle_speed_callback)

        print("Running")
        await asyncio.sleep(60)
        remove_battery_level_listener()
        remove_vehicle_speed_listener()
```

## Writing Your Own Listener with Multiple Signals

You can also write your own listener that listens to multiple signals. Here is an example of writing a custom listener:

```python
async def main():
    async with aiohttp.ClientSession() as session:
        stream = TeslemetryStream(
            access_token="<token>",
            vin="<vin>", # for single vehicles
            server="na.teslemetry.com" # or "eu.teslemetry.com"
            session=session,
        )

        await stream.connect()

        vehicle = stream.get_vehicle("<vin>")

        def custom_listener(event):
            if "BatteryLevel" in event["data"]:
                print(f"Battery Level: {event['data']['BatteryLevel']}")
            if "VehicleSpeed" in event["data"]:
                print(f"Vehicle Speed: {event['data']['VehicleSpeed']}")

        remove_custom_listener = stream.async_add_listener(custom_listener, {"vin": "<vin>", "data": {"BatteryLevel": None, "VehicleSpeed": None}})

        print("Running")
        await asyncio.sleep(60)
        remove_custom_listener()

        await stream.close()
```

## Energy Site Streaming

Energy sites stream two events, `live_status` and `site_info`. Unlike vehicle
signals these are delivered as full documents rather than field deltas, and
there is nothing to enable - subscribed sites are polled automatically. On
connect you get an initial snapshot event for each, the same way vehicle
`State` is delivered on connect.

```python
async def main():
    async with aiohttp.ClientSession() as session:
        stream = TeslemetryStream(
            access_token="<token>",
            session=session,
        )

        site = stream.get_energysite("<site_id>")

        def live_status_callback(live_status):
            print(f"Battery Power: {live_status.get('battery_power')}")

        def site_info_callback(site_info):
            print(f"Site Name: {site_info.get('site_name')}")

        remove_live_status_listener = site.listen_LiveStatus(live_status_callback)
        remove_site_info_listener = site.listen_SiteInfo(site_info_callback)

        print("Running")
        await asyncio.sleep(60)
        remove_live_status_listener()
        remove_site_info_listener()
        stream.close()
```

> **Note:** Energy site streaming ships flag-gated behind [Teslemetry/api#310](https://github.com/Teslemetry/api/pull/310).
> Until that server feature is enabled, `listen_LiveStatus`/`listen_SiteInfo` will simply never fire.

`site_info` never carries `tariff_content`/`tariff_content_v2` - the site's V2
tariff is its own `tariff_content_v2` event, published only when it changes.
Like `site_info`, event silence means no change, never staleness; freshness
always lives in a REST call, never in event cadence. A `None` body is an
explicit removal signal (the site's V2 tariff was cleared), not "no data yet".

```python
        def tariff_callback(tariff_content_v2):
            if tariff_content_v2 is None:
                print("V2 tariff removed")
            else:
                print(f"Tariff code: {tariff_content_v2.get('code')}")

        remove_tariff_listener = site.listen_TariffContentV2(tariff_callback)
```

A third event, `energy_totals`, fires when the server's periodic
`calendar_history` poll detects the day's history actually changed. It never
carries the full time series - just cumulative per-type totals and a `url`
to re-fetch the full document via your own REST client. Silence means no
change, never a stale value.

```python
        def energy_totals_callback(totals):
            print(f"Total home usage: {totals.total_home_usage}")

        remove_energy_totals_listener = site.listen_EnergyTotals(energy_totals_callback)
```

## SSE Topic Selection

By default a connection receives every applicable event (legacy-all
behavior, unchanged forever). Pass `topics` to `TeslemetryStream` to
subscribe to only the SSE wire events you need - an exact allowlist,
comma-joined onto the connection's `topics` query parameter:

```python
from teslemetry_stream import TeslemetryStream, SseTopic, SSE_ENERGY_TOPICS

stream = TeslemetryStream(
    access_token="<token>",
    session=session,
    topics=[SseTopic.LIVE_STATUS, SseTopic.SITE_INFO],
)

# Or use a preset that expands client-side to every topic in a group:
stream = TeslemetryStream(
    access_token="<token>",
    session=session,
    topics=SSE_ENERGY_TOPICS,
)
```

`SseTopic` is the closed set of exact wire names the server recognizes;
`SSE_VEHICLE_TOPICS`, `SSE_ENERGY_TOPICS`, and `SSE_ALL_TOPICS` are
convenience presets that expand to those exact names client-side.

## Ingesting Externally Sourced Events

Some observations arrive from somewhere other than the SSE connection - a
Bluetooth broadcast read locally, for instance. `ingest` accepts one and
delivers it to the listeners you already registered, in the same wire format
the connection itself sends, so no consumer needs a second subscription or a
translation step:

```python
from teslemetry_stream import Metadata, Signal

vehicle = stream.get_vehicle("<vin>")
vehicle.listen_Locked(print)

vehicle.ingest(
    {Signal.LOCKED: False},
    {
        Metadata.SOURCE: "bluetooth",
        Metadata.RAW: "VEHICLELOCKSTATE_SELECTIVE_UNLOCKED",
    },
)
```

`metadata` records where the observation came from and what its untranslated
wire value was. It is carried on the event and never acted on: `source` keeps
provenance visible for debugging or for a decision the consumer makes, and
`raw` keeps the fidelity a translation discards (any unlocked state reads as
unlocked, but which one is still worth having). It is a plain dict, so a
source can add keys of its own without a format break; `Metadata` names the
two every source is expected to speak.

Ingesting holds no client and opens no connection, so an observation is
delivered whether or not the stream is connected.

**Ordering and deduplication.** Every event - native or ingested - is
dispatched in arrival order, exactly as given. The stream keeps no per-field
value and compares nothing against what came before, so if two sources report
the same field, listeners are called twice: once per report, later report
last, neither dropped. There is deliberately no source ranking, precedence,
or preferred source. Which report to believe is the consumer's decision, and
`metadata` is what it decides on.

## Public Methods in TeslemetryStream Class

### `__init__(session: aiohttp.ClientSession, access_token: str, server: str | None = None, vin: str | None = None, parse_timestamp: bool = False, manual: bool = False, topics: str | Iterable[str] | None = None)`
Initialize the TeslemetryStream client. `topics` is an optional exact SSE wire event allowlist (see `SseTopic`) - a single topic or an iterable of them; omitting it preserves legacy-all behavior.

### `get_vehicle(vin: str) -> TeslemetryStreamVehicle`
Create a vehicle object to manage config and create listeners.

### `get_energysite(site_id: str | int) -> TeslemetryStreamEnergySite`
Create an energy site object to create listeners for `live_status` and `site_info`.

### `connected -> bool`
Return if connected.

### `get_config(vin: str | None = None) -> None`
Get the current stream config.

### `find_server(self) -> None`
Find the server using metadata.

### `update_fields(fields: dict, vin: str) -> dict`
Modify the Fleet Telemetry configuration.

### `replace_fields(fields: dict, vin: str) -> dict`
Replace the Fleet Telemetry configuration.

### `config(self) -> dict`
Return current configuration.

### `connect(self) -> None`
Connect to the telemetry stream.

### `close(self) -> None`
Close connection.

### `async_add_listener(callback: Callable, filters: dict | None = None) -> Callable[[], None]`
Add listener for data updates.

### `listen(self)`
Listen to the telemetry stream.

### `ingest(data: dict, vin: str | None = None, metadata: dict | None = None, created_at: str | None = None) -> dict`
Deliver an externally sourced observation to this stream's listeners, in the same wire format the connection sends. `vin` defaults to the stream's own. Returns the event as dispatched. See [Ingesting Externally Sourced Events](#ingesting-externally-sourced-events).

### `listen_Credits(callback: Callable[[CreditsEvent], None]) -> Callable[[], None]`
Add listener for credit events.

### `listen_Balance(callback: Callable[[int], None]) -> Callable[[], None]`
Add listener for credit balance.

## Public Methods in TeslemetryStreamVehicle Class

### `__init__(stream: TeslemetryStream, vin: str)`
Initialize the TeslemetryStreamVehicle instance.

### `get_config(self) -> None`
Get the current vehicle config.

### `update_fields(fields: dict) -> dict`
Update Fleet Telemetry configuration for the vehicle.

### `replace_fields(fields: dict) -> dict`
Replace Fleet Telemetry configuration for the vehicle.

### `config(self) -> dict`
Return current configuration for the vehicle.

### `ingest(data: dict, metadata: dict | None = None, created_at: str | None = None) -> dict`
Ingest an externally sourced observation for this vehicle - `TeslemetryStream.ingest` with the VIN filled in.

### `listen_State(callback: Callable[[bool], None]) -> Callable[[],None]`
Listen for vehicle online state polling. The callback receives a boolean value representing whether the vehicle is online.

### `listen_VehicleData(callback: Callable[[dict], None]) -> Callable[[],None]`
Listen for vehicle data polling events. The callback receives a dictionary containing the complete vehicle data.

### `listen_Cellular(callback: Callable[[bool], None]) -> Callable[[],None]`
Listen for cellular connectivity events. The callback receives a boolean value indicating whether the cellular connection is established.

### `listen_Wifi(callback: Callable[[bool], None]) -> Callable[[],None]`
Listen for WiFi connectivity events. The callback receives a boolean value indicating whether the WiFi connection is established.

### `listen_Alerts(callback: Callable[[list[dict]], None]) -> Callable[[],None]`
Listen for vehicle alert events. The callback receives a list of dictionaries containing alert information.

### `listen_Errors(callback: Callable[[list[dict]], None]) -> Callable[[],None]`
Listen for vehicle error events. The callback receives a list of dictionaries containing error information.

### `listen_*` Methods
The `TeslemetryStreamVehicle` class contains a `listen_*` methods for each telemetry signal.
These methods allow you to listen to specific signals and handle their data in a type-safe manner.
A full list of fields and metadata can be found at [api.teslemetry.com/fields.json](https://api.teslemetry.com/fields.json)

## Public Methods in TeslemetryStreamEnergySite Class

### `__init__(stream: TeslemetryStream, site_id: str)`
Initialize the TeslemetryStreamEnergySite instance.

### `listen_LiveStatus(callback: Callable[[dict], None]) -> Callable[[],None]`
Listen for energy site live status events. The callback receives the full `live_status` document.

### `listen_SiteInfo(callback: Callable[[dict], None]) -> Callable[[],None]`
Listen for energy site info events. The callback receives the `site_info` document. This document never carries `tariff_content`/`tariff_content_v2` - use `listen_TariffContentV2` for the V2 tariff.

### `listen_TariffContentV2(callback: Callable[[dict | None], None]) -> Callable[[],None]`
Listen for the site's V2 tariff document. The callback receives the `tariff_content_v2` document verbatim, or `None` when the server sends an explicit removal signal. Published only when it changes.

### `listen_EnergyTotals(callback: Callable[[EnergyHistoryTotals], None]) -> Callable[[],None]`
Listen for `energy_totals` refresh notifications. The callback receives an `EnergyHistoryTotals` dataclass of cumulative per-type totals - never the full time series. Fires only when the server's periodic history poll detects a change; a consumer wanting the full series should GET the underlying event's `url` via their own REST client.
