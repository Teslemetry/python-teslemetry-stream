# Teslemetry Stream Library
This is an asynchronous Python 3 library that connects to the Teslemetry Stream server and provides Tesla Fleet Telemetry using server side events.

## Installation

`pip install teslemetry-stream`

## Usage

The TeslemetryStream class requires:

- session: an aiohttp.ClientSession
- access_token: an access token from the [Teslemetry console](https://teslemetry.com/console)
- One or both:
  - vin: your Tesla's Vehicle Identification Number
  - server: The Teslemetry server to connect to

The full list of possible values are provided in `TeslemetryStream.Fields` and `TeslemetryStream.Alerts`

To connect, either use `async with` on the instance, call `connect()`, or register an callback with `async_add_listener`, which will connect when added and disconnect when removed.

Using `connect()` or `listen()` will require you to close the session manually using `close()`.

## Example
The following example puts the listening loop in the background, then stopping after 20 seconds.
```
async def main():
    async with aiohttp.ClientSession() as session:
        stream = TeslemetryStream(
            access_token="<token>",
            vin="<vin>",
            session=session,
        )
        await stream.connect()

        def callback(event):
            print(event["data"])

        remove = stream.async_add_listener(callback)

        print("Running")
        await asyncio.sleep(60)
        remove()
```