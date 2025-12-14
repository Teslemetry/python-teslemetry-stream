#!/usr/bin/env python3
"""
Example script demonstrating how to use teslemetry_stream and add fields.

This script shows how to:
1. Connect to the Teslemetry Stream service
2. Add specific telemetry fields to monitor
3. Listen to the streaming data
4. Handle the received telemetry events

Make sure you have:
- A Teslemetry access token from https://teslemetry.com/console
- Your vehicle's VIN
- The teslemetry-stream package installed: pip install teslemetry-stream
"""

import asyncio
import aiohttp
import logging
from datetime import datetime
from teslemetry_stream import TeslemetryStream, Signal

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Replace these with your actual values
ACCESS_TOKEN = "your_teslemetry_access_token_here"
VIN = "your_vehicle_vin_here"
SERVER = "api.teslemetry.com"  # or "na.teslemetry.com" or "eu.teslemetry.com"


async def main():
    """Main example function demonstrating field addition and streaming."""

    async with aiohttp.ClientSession() as session:
        # Create TeslemetryStream instance
        stream = TeslemetryStream(
            session=session,
            access_token=ACCESS_TOKEN,
            vin=VIN,
            server=SERVER,
            parse_timestamp=True,  # Enable timestamp parsing for easier handling
        )

        try:
            # Get vehicle instance
            vehicle = stream.get_vehicle(VIN)

            # Example 1: Add individual fields with different intervals
            logger.info("Adding telemetry fields...")

            # Add battery level monitoring (every 30 seconds)
            await vehicle.add_field(Signal.BATTERY_LEVEL, interval=30)

            # Add vehicle speed monitoring (every 5 seconds for more frequent updates)
            await vehicle.add_field(Signal.VEHICLE_SPEED, interval=5)

            # Add charge state monitoring (every 60 seconds)
            await vehicle.add_field(Signal.CHARGE_STATE, interval=60)

            # Add location data (every 10 seconds)
            await vehicle.add_field(Signal.LOCATION, interval=10)

            # Add door state monitoring (every 15 seconds)
            await vehicle.add_field(Signal.DOOR_STATE, interval=15)

            # Add HVAC power state (every 20 seconds)
            await vehicle.add_field(Signal.HVAC_POWER, interval=20)

            logger.info("Fields added successfully! Current vehicle config:")
            logger.info(f"Fields: {list(vehicle.fields.keys())}")

            # Example 2: Set up event handlers for specific data
            def handle_battery_level(battery_level):
                """Handle battery level updates."""
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"[{timestamp}] Battery Level: {battery_level}%")

                # Add custom logic here (e.g., alert if battery is low)
                if battery_level < 20:
                    logger.warning(f"LOW BATTERY WARNING: {battery_level}%")

            def handle_vehicle_speed(speed):
                """Handle vehicle speed updates."""
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if speed > 0:
                    logger.info(f"[{timestamp}] Vehicle Speed: {speed} mph")

            def handle_charge_state(charge_state):
                """Handle charge state updates."""
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"[{timestamp}] Charge State: {charge_state}")

            def handle_location(location):
                """Handle location updates."""
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if (
                    isinstance(location, dict)
                    and "latitude" in location
                    and "longitude" in location
                ):
                    lat, lon = location["latitude"], location["longitude"]
                    logger.info(f"[{timestamp}] Location: {lat:.6f}, {lon:.6f}")

            # Example 3: Generic event handler for all data
            def handle_all_telemetry(event):
                """Handle all telemetry events with custom processing."""
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if "data" in event:
                    data = event["data"]

                    # Add custom field: calculate a derived metric
                    # For example, add a "data_freshness" field based on timestamp
                    if "createdAt" in event:
                        created_at = event["createdAt"]
                        data["custom_data_age_seconds"] = (
                            datetime.now()
                            - datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        ).total_seconds()

                    # Add custom field: combine multiple signals
                    if "BatteryLevel" in data and "ChargeState" in data:
                        if (
                            data["ChargeState"] == "Charging"
                            and data["BatteryLevel"] < 80
                        ):
                            data["custom_charging_needed"] = True
                        else:
                            data["custom_charging_needed"] = False

                    # Log interesting combinations
                    interesting_fields = [
                        "BatteryLevel",
                        "VehicleSpeed",
                        "ChargeState",
                        "Location",
                    ]
                    present_fields = [
                        field for field in interesting_fields if field in data
                    ]

                    if present_fields:
                        field_values = {field: data[field] for field in present_fields}
                        logger.info(f"[{timestamp}] Multi-field update: {field_values}")

                        # Log any custom fields we added
                        custom_fields = {
                            k: v for k, v in data.items() if k.startswith("custom_")
                        }
                        if custom_fields:
                            logger.info(f"[{timestamp}] Custom fields: {custom_fields}")

            # Register listeners using typed methods
            logger.info("Setting up event listeners...")
            remove_battery_listener = vehicle.listen_BatteryLevel(handle_battery_level)
            remove_speed_listener = vehicle.listen_VehicleSpeed(handle_vehicle_speed)
            remove_charge_listener = vehicle.listen_ChargeState(handle_charge_state)
            remove_location_listener = vehicle.listen_Location(handle_location)

            # Register generic listener for all events
            remove_all_listener = stream.async_add_listener(handle_all_telemetry)

            # Example 4: Connect and listen for a specified duration
            logger.info("Starting telemetry stream... (will run for 60 seconds)")

            async with stream:  # This connects automatically
                # Let it run for 60 seconds to collect data
                await asyncio.sleep(60)

            # Clean up listeners
            logger.info("Cleaning up listeners...")
            remove_battery_listener()
            remove_speed_listener()
            remove_charge_listener()
            remove_location_listener()
            remove_all_listener()

        except Exception as e:
            logger.error(f"Error in telemetry streaming: {e}")
            raise

        finally:
            logger.info("Example completed!")


if __name__ == "__main__":
    print("=== Teslemetry Stream Field Addition Example ===")
    print()
    print("This example demonstrates:")
    print("1. Adding specific telemetry fields with custom intervals")
    print("2. Setting up typed listeners for different data types")
    print("3. Creating custom derived fields from streaming data")
    print("4. Handling telemetry events with custom logic")
    print()
    print("Make sure to update ACCESS_TOKEN and VIN before running!")
    print()

    # Run the example
    asyncio.run(main())
