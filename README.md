# Teslemetry Stream Library

```
async def main():
    async with aiohttp.ClientSession() as session:
        stream = TeslemetryStream(
            token="<token>",
            vin="<vin>",
            session=session,
        )
        await stream.connect()
        print("Connected")

        async def listen(stream):
            async for event in stream:
                print(event)

        asyncio.create_task(listen(stream))

        await asyncio.sleep(20)
        await stream.close()
```