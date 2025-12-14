#!/usr/bin/env python3
"""
Advanced example demonstrating comprehensive field operations with teslemetry_stream.

This example shows:
1. Adding multiple fields with different intervals
2. Using both Signal enum and string field names
3. Updating existing field configurations
4. Creating custom data processors and field enrichment
5. Managing field subscriptions dynamically
6. Error handling and reconnection strategies
"""

import asyncio
import aiohttp
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from teslemetry_stream import TeslemetryStream, Signal

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
ACCESS_TOKEN = "your_access_token_here"
VIN = "your_vin_here"
SERVER = "api.teslemetry.com"


class TelemetryProcessor:
    """Advanced telemetry data processor with field enrichment capabilities."""

    def __init__(self):
        self.data_history = {}
        self.custom_metrics = {}
        self.alert_thresholds = {"battery_low": 15, "speed_high": 80, "temp_high": 100}

    def add_custom_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add custom computed fields to telemetry data."""
        enriched_data = data.copy()

        # Add timestamp fields
        now = datetime.now()
        enriched_data["processed_at"] = now.isoformat()
        enriched_data["processing_delay_ms"] = (
            0  # Would calculate actual delay in production
        )

        # Battery-related custom fields
        if "BatteryLevel" in data:
            battery_level = data["BatteryLevel"]
            enriched_data["battery_category"] = self._categorize_battery_level(
                battery_level
            )
            enriched_data["battery_alert"] = (
                battery_level < self.alert_thresholds["battery_low"]
            )

            # Track battery change rate if we have history
            if "BatteryLevel" in self.data_history:
                last_battery = self.data_history["BatteryLevel"]["value"]
                last_time = self.data_history["BatteryLevel"]["timestamp"]
                time_diff = (now - last_time).total_seconds() / 3600  # hours

                if time_diff > 0:
                    battery_change_rate = (battery_level - last_battery) / time_diff
                    enriched_data["battery_change_rate_per_hour"] = round(
                        battery_change_rate, 2
                    )

            # Update history
            self.data_history["BatteryLevel"] = {
                "value": battery_level,
                "timestamp": now,
            }

        # Speed-related custom fields
        if "VehicleSpeed" in data:
            speed = data["VehicleSpeed"]
            enriched_data["speed_category"] = self._categorize_speed(speed)
            enriched_data["speeding_alert"] = (
                speed > self.alert_thresholds["speed_high"]
            )

            # Update history
            self.data_history["VehicleSpeed"] = {"value": speed, "timestamp": now}

        # Location-based custom fields
        if "Location" in data and isinstance(data["Location"], dict):
            location = data["Location"]
            if "latitude" in location and "longitude" in location:
                enriched_data["location_zone"] = self._determine_location_zone(
                    location["latitude"], location["longitude"]
                )

        # Climate-related custom fields
        if "InsideTemp" in data and "OutsideTemp" in data:
            temp_diff = data["InsideTemp"] - data["OutsideTemp"]
            enriched_data["cabin_temp_differential"] = round(temp_diff, 1)
            enriched_data["climate_efficiency"] = self._assess_climate_efficiency(
                temp_diff
            )

        # Charging-related custom fields
        if "ChargeState" in data and "BatteryLevel" in data:
            enriched_data["charging_recommendation"] = (
                self._get_charging_recommendation(
                    data["ChargeState"], data["BatteryLevel"]
                )
            )

        # Multi-field derived metrics
        if "VehicleSpeed" in data and "BatteryLevel" in data:
            enriched_data["energy_efficiency_category"] = (
                self._assess_energy_efficiency(
                    data["VehicleSpeed"], data["BatteryLevel"]
                )
            )

        return enriched_data

    def _categorize_battery_level(self, level: float) -> str:
        """Categorize battery level."""
        if level >= 80:
            return "high"
        elif level >= 50:
            return "medium"
        elif level >= 20:
            return "low"
        else:
            return "critical"

    def _categorize_speed(self, speed: float) -> str:
        """Categorize vehicle speed."""
        if speed == 0:
            return "stopped"
        elif speed <= 25:
            return "city"
        elif speed <= 55:
            return "suburban"
        else:
            return "highway"

    def _determine_location_zone(self, lat: float, lon: float) -> str:
        """Determine location zone (simplified example)."""
        # This is a simplified example - in practice, you'd use geofencing
        # or reverse geocoding services
        return "unknown_zone"

    def _assess_climate_efficiency(self, temp_diff: float) -> str:
        """Assess climate control efficiency."""
        abs_diff = abs(temp_diff)
        if abs_diff < 5:
            return "efficient"
        elif abs_diff < 15:
            return "moderate"
        else:
            return "inefficient"

    def _get_charging_recommendation(
        self, charge_state: str, battery_level: float
    ) -> str:
        """Provide charging recommendation."""
        if charge_state == "Charging":
            return "currently_charging"
        elif battery_level < 20:
            return "charge_immediately"
        elif battery_level < 50:
            return "charge_soon"
        else:
            return "no_charging_needed"

    def _assess_energy_efficiency(self, speed: float, battery_level: float) -> str:
        """Assess energy efficiency based on speed and battery usage."""
        # Simplified efficiency assessment
        if speed == 0:
            return "idle"
        elif speed <= 45:
            return "efficient"
        elif speed <= 65:
            return "moderate"
        else:
            return "consuming"


async def advanced_field_management_example():
    """Comprehensive example of advanced field management."""

    processor = TelemetryProcessor()

    async with aiohttp.ClientSession() as session:
        stream = TeslemetryStream(
            session=session,
            access_token=ACCESS_TOKEN,
            vin=VIN,
            server=SERVER,
            parse_timestamp=True,
        )

        try:
            vehicle = stream.get_vehicle(VIN)

            # Phase 1: Add initial field set with different intervals
            logger.info("Phase 1: Adding initial telemetry fields...")

            initial_fields = [
                (Signal.BATTERY_LEVEL, 30),
                (Signal.VEHICLE_SPEED, 5),
                (Signal.CHARGE_STATE, 60),
                (Signal.LOCATION, 15),
                (Signal.INSIDE_TEMP, 45),
                (Signal.OUTSIDE_TEMP, 45),
                (Signal.HVAC_POWER, 30),
            ]

            for field, interval in initial_fields:
                await vehicle.add_field(field, interval=interval)
                await asyncio.sleep(0.1)  # Small delay between additions

            logger.info(f"Added {len(initial_fields)} initial fields")

            # Phase 2: Set up event handlers
            logger.info("Phase 2: Setting up event handlers...")

            events_received = 0
            processed_events = []

            def handle_enriched_data(event):
                """Handle telemetry data with enrichment."""
                nonlocal events_received
                events_received += 1

                if "data" in event:
                    # Process and enrich the data
                    enriched_data = processor.add_custom_fields(event["data"])

                    # Store processed event
                    processed_event = {
                        "original": event["data"],
                        "enriched": enriched_data,
                        "event_id": events_received,
                        "received_at": datetime.now().isoformat(),
                    }
                    processed_events.append(processed_event)

                    # Log interesting enriched data
                    custom_fields = {
                        k: v for k, v in enriched_data.items() if k not in event["data"]
                    }
                    if custom_fields:
                        logger.info(
                            f"Event #{events_received} - Custom fields: {custom_fields}"
                        )

                    # Handle alerts
                    alerts = []
                    if enriched_data.get("battery_alert"):
                        alerts.append("LOW_BATTERY")
                    if enriched_data.get("speeding_alert"):
                        alerts.append("SPEEDING")

                    if alerts:
                        logger.warning(
                            f"ALERTS for event #{events_received}: {', '.join(alerts)}"
                        )

            # Register the enriched data handler
            remove_main_listener = stream.async_add_listener(handle_enriched_data)

            # Phase 3: Dynamic field management during runtime
            logger.info("Phase 3: Starting stream with dynamic field management...")

            async with stream:
                # Run for 30 seconds with initial configuration
                logger.info(
                    "Running with initial field configuration for 30 seconds..."
                )
                await asyncio.sleep(30)

                # Add more fields dynamically
                logger.info("Adding additional fields dynamically...")
                additional_fields = [
                    (Signal.CHARGE_AMPS, 30),
                    (Signal.CHARGER_VOLTAGE, 30),
                    (Signal.ODOMETER, 120),  # Less frequent updates for odometer
                ]

                for field, interval in additional_fields:
                    await vehicle.add_field(field, interval=interval)
                    logger.info(f"Added field: {field.value} with {interval}s interval")
                    await asyncio.sleep(0.1)

                # Run for another 30 seconds with expanded configuration
                logger.info(
                    "Running with expanded field configuration for 30 seconds..."
                )
                await asyncio.sleep(30)

                # Update existing field intervals
                logger.info("Updating field intervals...")
                await vehicle.add_field(
                    Signal.BATTERY_LEVEL, interval=10
                )  # More frequent
                await vehicle.add_field(Signal.LOCATION, interval=5)  # More frequent
                logger.info("Updated BATTERY_LEVEL to 10s and LOCATION to 5s intervals")

                # Final run with updated intervals
                logger.info("Running with updated intervals for 20 seconds...")
                await asyncio.sleep(20)

        except Exception as e:
            logger.error(f"Error during advanced field management: {e}")
            raise

        finally:
            # Cleanup
            if "remove_main_listener" in locals():
                remove_main_listener()

            # Report final statistics
            logger.info("=== Final Statistics ===")
            logger.info(f"Total events received: {events_received}")
            logger.info(f"Events with custom fields: {len(processed_events)}")

            if processed_events:
                # Show sample of enriched data
                logger.info("Sample enriched event:")
                sample_event = processed_events[-1]  # Last event
                logger.info(json.dumps(sample_event, indent=2, default=str))


async def field_configuration_demo():
    """Demonstrate various field configuration patterns."""

    async with aiohttp.ClientSession() as session:
        stream = TeslemetryStream(session=session, access_token=ACCESS_TOKEN, vin=VIN)

        vehicle = stream.get_vehicle(VIN)

        # Demo 1: Adding fields with Signal enum
        logger.info("Demo 1: Adding fields using Signal enum...")
        await vehicle.add_field(Signal.BATTERY_LEVEL, interval=30)
        await vehicle.add_field(Signal.VEHICLE_SPEED, interval=10)

        # Demo 2: Adding fields with string names (if supported)
        logger.info("Demo 2: Adding fields using string names...")
        await vehicle.add_field("ChargeState", interval=60)
        await vehicle.add_field("Location", interval=20)

        # Demo 3: Adding fields without specific intervals (uses default)
        logger.info("Demo 3: Adding fields with default intervals...")
        await vehicle.add_field(Signal.INSIDE_TEMP)
        await vehicle.add_field(Signal.OUTSIDE_TEMP)

        # Demo 4: Show current configuration
        logger.info("Current field configuration:")
        for field_name, config in vehicle.fields.items():
            interval = (
                config.get("interval_seconds", "default") if config else "default"
            )
            logger.info(f"  {field_name}: {interval}s")


if __name__ == "__main__":
    print("=== Advanced Teslemetry Stream Field Management Example ===")
    print()
    print("This comprehensive example demonstrates:")
    print("1. Adding multiple fields with custom intervals")
    print("2. Dynamic field management during runtime")
    print("3. Custom data processing and field enrichment")
    print("4. Alert generation from telemetry data")
    print("5. Event statistics and monitoring")
    print()
    print("Before running:")
    print("- Update ACCESS_TOKEN with your Teslemetry token")
    print("- Update VIN with your vehicle's VIN")
    print("- Ensure you have network connectivity")
    print()

    try:
        # Run the field configuration demo first
        print("Running field configuration demo...")
        asyncio.run(field_configuration_demo())

        print("\nRunning advanced field management example...")
        asyncio.run(advanced_field_management_example())

    except KeyboardInterrupt:
        print("\nExample interrupted by user")
    except Exception as e:
        print(f"\nExample failed with error: {e}")
        raise
