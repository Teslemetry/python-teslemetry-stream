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
- server: The Teslemetry server to connect to, otherwise use `find_server`
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
            server="na.teslemetry.com" # or "eu.teslemetry.com"
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

        await stream.disconnect()
```

## Public Methods in TeslemetryStream Class

### `__init__(self, session: aiohttp.ClientSession, access_token: str, server: str | None = None, vin: str | None = None, parse_timestamp: bool = False)`
Initialize the TeslemetryStream client.

### `get_vehicle(self, vin: str) -> TeslemetryStreamVehicle`
Create a vehicle stream.

### `connected(self) -> bool`
Return if connected.

### `get_config(self, vin: str | None = None) -> None`
Get the current stream config.

### `find_server(self) -> None`
Find the server using metadata.

### `update_fields(self, fields: dict, vin: str) -> dict`
Modify the Fleet Telemetry configuration.

### `replace_fields(self, fields: dict, vin: str) -> dict`
Replace the Fleet Telemetry configuration.

### `config(self) -> dict`
Return current configuration.

### `connect(self) -> None`
Connect to the telemetry stream.

### `close(self) -> None`
Close connection.

### `async_add_listener(self, callback: Callable, filters: dict | None = None) -> Callable[[], None]`
Add listener for data updates.

### `listen(self)`
Listen to the telemetry stream.

### `listen_Credits(self, callback: Callable[[dict[str, str | int]], None]) -> Callable[[], None]`
Add listener for credit events.

### `listen_Balance(self, callback: Callable[[int], None]) -> Callable[[], None]`
Add listener for credit balance.

## Public Methods in TeslemetryStreamVehicle Class

### `__init__(self, stream: TeslemetryStream, vin: str)`
Initialize the TeslemetryStreamVehicle instance.

### `get_config(self) -> None`
Get the current vehicle config.

### `update_fields(self, fields: dict) -> dict`
Update Fleet Telemetry configuration for the vehicle.

### `replace_fields(self, fields: dict) -> dict`
Replace Fleet Telemetry configuration for the vehicle.

### `config(self) -> dict`
Return current configuration for the vehicle.

### `listen_*` Methods
The `TeslemetryStreamVehicle` class contains several `listen_*` methods for various telemetry signals. These methods allow you to listen to specific signals and handle their data in a type-safe manner. The available `listen_*` methods and their callback types are:

- `listen_BatteryLevel(callback: Callable[[int], None])`
- `listen_VehicleSpeed(callback: Callable[[int], None])`
- `listen_Location(callback: Callable[[dict], None])`
- `listen_ChargeState(callback: Callable[[str], None])`
- `listen_DoorState(callback: Callable[[dict], None])`
- `listen_HvacPower(callback: Callable[[str], None])`
- `listen_ClimateKeeperMode(callback: Callable[[str], None])`
- `listen_CabinOverheatProtectionMode(callback: Callable[[str], None])`
- `listen_DefrostMode(callback: Callable[[str], None])`
- `listen_SeatHeaterLeft(callback: Callable[[int], None])`
- `listen_SeatHeaterRight(callback: Callable[[int], None])`
- `listen_SeatHeaterRearLeft(callback: Callable[[int], None])`
- `listen_SeatHeaterRearRight(callback: Callable[[int], None])`
- `listen_SeatHeaterRearCenter(callback: Callable[[int], None])`
- `listen_SentryMode(callback: Callable[[bool], None])`
- `listen_ScheduledChargingMode(callback: Callable[[str], None])`
- `listen_ScheduledChargingPending(callback: Callable[[bool], None])`
- `listen_ScheduledChargingStartTime(callback: Callable[[str], None])`
- `listen_ScheduledDepartureTime(callback: Callable[[str], None])`
- `listen_SoftwareUpdateVersion(callback: Callable[[str], None])`
- `listen_SoftwareUpdateDownloadPercentComplete(callback: Callable[[int], None])`
- `listen_SoftwareUpdateExpectedDurationMinutes(callback: Callable[[int], None])`
- `listen_SoftwareUpdateInstallationPercentComplete(callback: Callable[[int], None])`
- `listen_SoftwareUpdateScheduledStartTime(callback: Callable[[str], None])`
- `listen_ChargingCableType(callback: Callable[[str], None])`
- `listen_FastChargerType(callback: Callable[[str], None])`
- `listen_ChargePort(callback: Callable[[str], None])`
- `listen_ChargePortLatch(callback: Callable[[str], None])`
- `listen_ChargePortDoorOpen(callback: Callable[[bool], None])`
- `listen_ChargeEnableRequest(callback: Callable[[bool], None])`
- `listen_ChargeCurrentRequest(callback: Callable[[int], None])`
- `listen_ChargeCurrentRequestMax(callback: Callable[[int], None])`
- `listen_ChargeAmps(callback: Callable[[int], None])`
- `listen_ChargerPhases(callback: Callable[[int], None])`
- `listen_ChargeLimitSoc(callback: Callable[[int], None])`
- `listen_ChargeState(callback: Callable[[str], None])`
- `listen_ChargingCableType(callback: Callable[[str], None])`
- `listen_FastChargerType(callback: Callable[[str], None])`
- `listen_ChargePort(callback: Callable[[str], None])`
- `listen_ChargePortLatch(callback: Callable[[str], None])`
- `listen_ChargePortDoorOpen(callback: Callable[[bool], None])`
- `listen_ChargeEnableRequest(callback: Callable[[bool], None])`
- `listen_ChargeCurrentRequest(callback: Callable[[int], None])`
- `listen_ChargeCurrentRequestMax(callback: Callable[[int], None])`
- `listen_ChargeAmps(callback: Callable[[int], None])`
- `listen_ChargerPhases(callback: Callable[[int], None])`
- `listen_ChargeLimitSoc(callback: Callable[[int], None])`
