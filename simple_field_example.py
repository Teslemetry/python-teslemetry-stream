#!/usr/bin/env python3
"""
Simple example showing how to add fields to teslemetry_stream.

This example demonstrates the basic pattern for:
1. Connecting to Teslemetry Stream
2. Adding specific telemetry fields
3. Listening to the data stream
"""

import asyncio
import aiohttp
import logging
from teslemetry_stream import TeslemetryStream, Signal

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration - Replace with your actual values
ACCESS_TOKEN = "your_access_token_here"
VIN = "your_vin_here"


async def simple_field_example():
    """Simple example of adding fields and listening to telemetry data."""

    async with aiohttp.ClientSession() as session:
        # Create stream instance
        stream = TeslemetryStream(
            session=session,
            access_token=ACCESS_TOKEN,
            vin=VIN,
        )

        # Get vehicle instance for field management
        vehicle = stream.get_vehicle(VIN)

        # Add fields we want to monitor
        logger.info("Adding telemetry fields...")
        await vehicle.add_field(Signal.BATTERY_LEVEL, interval=30)
        await vehicle.add_field(Signal.VEHICLE_SPEED, interval=10)
        await vehicle.add_field(Signal.CHARGE_STATE, interval=60)

        # Set up event handler
        def handle_telemetry_data(event):
            """Process incoming telemetry data."""
            if "data" in event:
                data = event["data"]

                # Add custom field based on existing data
                if "BatteryLevel" in data:
                    # Add a custom field indicating battery status
                    if data["BatteryLevel"] > 80:
                        data["battery_status"] = "high"
                    elif data["BatteryLevel"] > 20:
                        data["battery_status"] = "medium"
                    else:
                        data["battery_status"] = "low"

                # Log the received data with our custom field
                logger.info(f"Received data: {data}")

        # Start listening
        remove_listener = stream.async_add_listener(handle_telemetry_data)

        try:
            async with stream:  # Auto-connect
                logger.info("Listening for telemetry data for 30 seconds...")
                await asyncio.sleep(30)
        finally:
            remove_listener()
            logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(simple_field_example())
