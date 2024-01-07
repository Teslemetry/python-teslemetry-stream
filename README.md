# Teslemetry Stream Library
This is an asynchronous python library that connects to the Teslemetry Stream server and provides Tesla Fleet Telemetry over server side events.

## Installation

`pip install teslemetry-stream`

## Usage

The TeslemetryStream class requires:

- session: an aiohttp.ClientSession
- access_token: an access token from the (Teslemetry console)[https://teslemetry.com/console]
- vin: your Tesla's Vehicle Identification Number

The TeslemetryStream instance can then be configured with:
- `add_field(field, interval)`
- `remove_field(field)`
- `add_alert(alert)`
- `remove_alert(alert)`

The full list of possible values are provided in `TeslemetryStream.Fields` and `TeslemetryStream.Alerts`

To connect, either use `async with` on the instance, call `connect()`, or register an async callback on `listen()`, which will connect automatically.

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

        async def callback(event):
            print(event)

        asyncio.create_task(stream.listen(callback))

        await asyncio.sleep(20)
        await stream.close()
```