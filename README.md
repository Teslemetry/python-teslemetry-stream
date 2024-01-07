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

        async def callback(event):
            print(event)

        asyncio.create_task(self.listen(callback))

        await asyncio.sleep(20)
        await stream.close()
```