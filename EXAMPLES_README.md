# Teslemetry Stream Examples

This directory contains example scripts demonstrating how to use the `teslemetry-stream` library to connect to Tesla telemetry data and add custom fields for monitoring.

## Prerequisites

1. **Teslemetry Account**: Sign up at [teslemetry.com](https://teslemetry.com)
2. **Access Token**: Get your access token from the [Teslemetry Console](https://teslemetry.com/console)
3. **Vehicle VIN**: Your Tesla vehicle's VIN number
4. **Python Dependencies**: Install the required packages:
   ```bash
   pip install teslemetry-stream aiohttp
   ```

## Example Scripts

### 1. `simple_field_example.py` - Basic Field Addition

**Purpose**: Demonstrates the fundamental pattern for adding telemetry fields and listening to data.

**What it shows**:
- Connecting to the Teslemetry Stream service
- Adding basic telemetry fields (battery level, speed, charge state)
- Setting up a simple event handler
- Adding custom fields to incoming data

**Usage**:
```bash
# Edit the file to add your ACCESS_TOKEN and VIN
python simple_field_example.py
```

**Key concepts**:
- Using `vehicle.add_field()` to subscribe to specific telemetry signals
- Setting custom intervals for different fields
- Processing incoming telemetry events
- Adding computed fields to the data stream

### 2. `example_add_field.py` - Comprehensive Field Management

**Purpose**: Shows a complete implementation with multiple field types, event handlers, and custom processing.

**What it shows**:
- Adding multiple fields with different monitoring intervals
- Using typed listener methods for specific signals
- Creating custom event handlers for different data types
- Implementing custom field derivation and alerts
- Proper resource cleanup and error handling

**Features demonstrated**:
- Battery level monitoring with low battery alerts
- Vehicle speed tracking
- Location monitoring
- Charge state management
- Custom field generation (data freshness, charging recommendations)

**Usage**:
```bash
# Update configuration section with your credentials
python example_add_field.py
```

### 3. `advanced_field_example.py` - Advanced Data Processing

**Purpose**: Demonstrates sophisticated telemetry processing with dynamic field management and data enrichment.

**What it shows**:
- Dynamic field addition and interval updates during runtime
- Advanced data processing with the `TelemetryProcessor` class
- Historical data tracking and trend analysis
- Alert generation based on multiple conditions
- Event statistics and monitoring
- Field configuration management

**Advanced features**:
- Battery change rate calculation
- Location zone determination
- Climate efficiency assessment
- Energy efficiency categorization
- Multi-field derived metrics
- Real-time alert system

**Usage**:
```bash
# Configure ACCESS_TOKEN and VIN in the script
python advanced_field_example.py
```

## Configuration

Before running any example, update these variables in the scripts:

```python
ACCESS_TOKEN = "your_teslemetry_access_token_here"
VIN = "your_vehicle_vin_here"
SERVER = "api.teslemetry.com"  # or your regional server
```

### Regional Servers

Choose the appropriate server based on your location:
- `api.teslemetry.com` - Global (recommended)
- `na.teslemetry.com` - North America
- `eu.teslemetry.com` - Europe

## Available Telemetry Fields

The library supports numerous telemetry fields defined in the `Signal` enum. Common fields include:

### Battery & Charging
- `BATTERY_LEVEL` - Battery percentage
- `CHARGE_STATE` - Charging status
- `CHARGE_AMPS` - Charging current
- `CHARGER_VOLTAGE` - Charger voltage
- `TIME_TO_FULL_CHARGE` - Estimated time to full charge

### Vehicle Movement
- `VEHICLE_SPEED` - Current speed
- `LOCATION` - GPS coordinates
- `ODOMETER` - Total distance traveled
- `GEAR` - Current gear selection

### Climate Control
- `INSIDE_TEMP` - Cabin temperature
- `OUTSIDE_TEMP` - Ambient temperature
- `HVAC_POWER` - Climate system status
- `HVAC_FAN_SPEED` - Fan speed setting

### Vehicle State
- `DOOR_STATE` - Door open/closed status
- `LOCKED` - Vehicle lock state
- `SENTRY_MODE` - Sentry mode status
- `CENTER_DISPLAY` - Display state

### Complete Field List

For a complete list of available fields, see:
- The `Signal` enum in `teslemetry_stream/const.py`
- [Teslemetry Fields API](https://api.teslemetry.com/fields.json)

## Field Management Patterns

### Adding Fields with Intervals

```python
# Add field with 30-second updates
await vehicle.add_field(Signal.BATTERY_LEVEL, interval=30)

# Add field with default interval
await vehicle.add_field(Signal.CHARGE_STATE)
```

### Using Typed Listeners

```python
# Set up typed listeners for specific fields
def battery_handler(battery_level):
    print(f"Battery: {battery_level}%")

remove_listener = vehicle.listen_BatteryLevel(battery_handler)
```

### Generic Event Handling

```python
# Handle all telemetry events
def handle_all_data(event):
    if "data" in event:
        data = event["data"]
        # Process any fields present in the data
        
remove_listener = stream.async_add_listener(handle_all_data)
```

## Custom Field Addition

All examples demonstrate adding custom fields to the telemetry data:

### Simple Custom Fields
```python
# Add computed status field
if "BatteryLevel" in data:
    if data["BatteryLevel"] > 80:
        data["battery_status"] = "high"
    elif data["BatteryLevel"] > 20:
        data["battery_status"] = "medium"
    else:
        data["battery_status"] = "low"
```

### Advanced Custom Fields
```python
# Add time-based fields
data["processed_at"] = datetime.now().isoformat()

# Add multi-field derivatives
if "BatteryLevel" in data and "ChargeState" in data:
    data["needs_charging"] = (
        data["ChargeState"] != "Charging" and data["BatteryLevel"] < 30
    )
```

## Error Handling

The examples include proper error handling patterns:

```python
try:
    async with stream:  # Auto-connect and cleanup
        # Your telemetry processing code
        await asyncio.sleep(duration)
except Exception as e:
    logger.error(f"Telemetry error: {e}")
finally:
    # Cleanup listeners
    remove_listener()
```

## Best Practices

1. **Use appropriate intervals**: Don't request data more frequently than needed
2. **Handle reconnections**: The library handles reconnections automatically
3. **Clean up listeners**: Always remove listeners when done
4. **Process data efficiently**: Avoid blocking operations in event handlers
5. **Monitor rate limits**: Be aware of API rate limiting
6. **Use typed listeners**: Prefer typed listeners for better error handling
7. **Log appropriately**: Use structured logging for debugging and monitoring

## Troubleshooting

### Common Issues

1. **Authentication Error**: Verify your access token is correct and active
2. **VIN Not Found**: Ensure the VIN is correct and associated with your account
3. **Connection Timeout**: Check network connectivity and server selection
4. **No Data Received**: Verify the vehicle is online and telemetry is enabled

### Debug Logging

Enable debug logging to see detailed connection information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Rate Limiting

If you encounter rate limiting:
- Increase field intervals
- Reduce the number of concurrent fields
- Contact Teslemetry support for higher limits

## Next Steps

After running these examples:

1. **Customize field selection**: Choose only the fields you need for your application
2. **Implement data persistence**: Store telemetry data in a database
3. **Create dashboards**: Visualize the telemetry data
4. **Set up alerts**: Create automated alerts for important conditions
5. **Integrate with other services**: Send data to cloud services or home automation systems

## Support

- **Library Documentation**: See the main README.md
- **Teslemetry Documentation**: [docs.teslemetry.com](https://docs.teslemetry.com)
- **API Reference**: [api.teslemetry.com](https://api.teslemetry.com)
- **Community Support**: Join the Teslemetry community forums

## License

These examples are provided under the same license as the main library.