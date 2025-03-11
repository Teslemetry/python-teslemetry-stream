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
        async with TeslemetryStream(
            access_token="<token>",
            vin="<vin>", # for single vehicles
            server="na.teslemetry.com" # or "eu.teslemetry.com"
            session=session,
        ) as stream:

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
```
