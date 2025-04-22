# Teslemetry Stream Library
This is an asynchronous Python 3 library that connects to the Teslemetry Stream service and provides Tesla Fleet Telemetry using server sent events. The library allows you to listen to various telemetry signals from Tesla vehicles, and provides a convenient way to handle these signals using typed listen methods.

## Capabilities
- Connect to the Teslemetry Stream service
- Listen to various telemetry signals from Tesla vehicles
- Handle signals using typed listen methods
- Write custom listeners for multiple signals

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

To connect, either use `async with` on the instance, call `connect()`, or register an callback with `async_add_listener`, which will connect when added and disconnect when removed.

Using `connect()` or `listen()` will require you to close the session manually using `close()`.

## Example
The following example puts the listening loop in the background, then stopping after 20 seconds.
```
async def main():
    async with aiohttp.ClientSession() as session:
        async with TeslemetryStream(
            access_token="<token>",
            vin="<vin>", # for single vehicles
            server="na.teslemetry.com" # or "eu.teslemetry.com"
            session=session,
        ) as stream:

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
        async with TeslemetryStream(
            access_token="<token>",
            vin="<vin>", # for single vehicles
            session=session,
        ) as stream:

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

## Public Methods in TeslemetryStream Class

### `__init__(session: aiohttp.ClientSession, access_token: str, server: str | None = None, vin: str | None = None, parse_timestamp: bool = False)`
Initialize the TeslemetryStream client.

### `get_vehicle(vin: str) -> TeslemetryStreamVehicle`
Create a vehicle object to manage config and create listeners.

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

### `listen_Credits(callback: Callable[[dict[str, str | int]], None]) -> Callable[[], None]`
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
