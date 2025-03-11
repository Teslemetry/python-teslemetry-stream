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

- `__init__(self, session: aiohttp.ClientSession, access_token: str, server: str | None = None, vin: str | None = None, parse_timestamp: bool = False)`
- `get_vehicle(self, vin: str) -> TeslemetryStreamVehicle`
- `connected(self) -> bool`
- `get_config(self, vin: str | None = None) -> None`
- `find_server(self) -> None`
- `update_fields(self, fields: dict, vin: str) -> dict`
- `replace_fields(self, fields: dict, vin: str) -> dict`
- `config(self) -> dict`
- `connect(self) -> None`
- `close(self) -> None`
- `async_add_listener(self, callback: Callable, filters: dict | None = None) -> Callable[[], None]`
- `listen(self)`
- `listen_Credits(self, callback: Callable[[dict[str, str | int]], None]) -> Callable[[], None]`
- `listen_Balance(self, callback: Callable[[int], None]) -> Callable[[], None]`

## Public Methods in TeslemetryStreamVehicle Class

- `__init__(self, stream: TeslemetryStream, vin: str)`
- `config(self) -> dict`
- `get_config(self) -> None`
- `update_config(self, config: dict) -> None`
- `patch_config(self, config: dict) -> dict[str, str|dict]`
- `post_config(self, config: dict) -> dict[str, str|dict]`
- `add_field(self, field: Signal | str, interval: int | None = None) -> None`
- `prefer_typed(self, prefer_typed: bool) -> None`
- `listen_ACChargingEnergyIn(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_ACChargingPower(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_AutoSeatClimateLeft(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_AutoSeatClimateRight(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_AutomaticBlindSpotCamera(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_AutomaticEmergencyBrakingOff(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_BMSState(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_BatteryHeaterOn(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_BatteryLevel(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_BlindSpotCollisionWarningChime(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_BmsFullchargecomplete(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_BrakePedal(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_BrakePedalPos(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_BrickVoltageMax(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_BrickVoltageMin(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_CabinOverheatProtectionMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_CabinOverheatProtectionTemperatureLimit(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_CarType(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_CenterDisplay(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ChargeAmps(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_ChargeCurrentRequest(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_ChargeCurrentRequestMax(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_ChargeEnableRequest(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_ChargeLimitSoc(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_ChargePort(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ChargePortColdWeatherMode(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_ChargePortDoorOpen(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_ChargePortLatch(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ChargeState(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ChargerPhases(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_ChargingCableType(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ClimateKeeperMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ClimateSeatCoolingFrontLeft(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ClimateSeatCoolingFrontRight(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_CruiseFollowDistance(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_CruiseSetSpeed(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_CurrentLimitMph(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_DCChargingEnergyIn(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DCChargingPower(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DCDCEnable(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_DefrostForPreconditioning(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_DefrostMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_DestinationLocation(self, callback: Callable[[TeslaLocation | None], None]) -> Callable[[],None]`
- `listen_DestinationName(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_DetailedChargeState(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_DiAxleSpeedF(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiAxleSpeedR(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiAxleSpeedREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiAxleSpeedRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiHeatsinkTF(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiHeatsinkTR(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiHeatsinkTREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiHeatsinkTRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiInverterTF(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiInverterTR(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiInverterTREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiInverterTRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiMotorCurrentF(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiMotorCurrentR(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiMotorCurrentREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiMotorCurrentRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiSlaveTorqueCmd(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiStateF(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_DiStateR(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_DiStateREL(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_DiStateRER(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_DiStatorTempF(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiStatorTempR(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiStatorTempREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiStatorTempRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiTorqueActualF(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiTorqueActualR(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiTorqueActualREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiTorqueActualRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiTorquemotor(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_DiVBatF(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiVBatR(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiVBatREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DiVBatRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_DoorState(self, callback: Callable[[dict | None], None]) -> Callable[[],None]`
- `listen_FrontDriverDoor(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_RearDriverDoor(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_FrontPassengerDoor(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_RearPassengerDoor(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_TrunkFront(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_TrunkRear(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_DriveRail(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_DriverSeatBelt(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_DriverSeatOccupied(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_EfficiencyPackage(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_EmergencyLaneDepartureAvoidance(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_EnergyRemaining(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_EstBatteryRange(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_EstimatedHoursToChargeTermination(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_EuropeVehicle(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_ExpectedEnergyPercentAtTripArrival(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_ExteriorColor(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_FastChargerPresent(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_FastChargerType(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_FrontDriverWindow(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ForwardCollisionWarning(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_FrontPassengerWindow(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_Gear(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_GpsHeading(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_GpsState(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_GuestModeEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_GuestModeMobileAccessState(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_HomelinkDeviceCount(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_HomelinkNearby(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_HvacACEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_HvacAutoMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_HvacFanSpeed(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_HvacFanStatus(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_HvacLeftTemperatureRequest(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_HvacPower(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_HvacRightTemperatureRequest(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_HvacSteeringWheelHeatAuto(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_HvacSteeringWheelHeatLevel(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_Hvil(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_IdealBatteryRange(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_InsideTemp(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_IsolationResistance(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_LaneDepartureAvoidance(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_LateralAcceleration(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_LifetimeEnergyUsed(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_LifetimeEnergyUsedDrive(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_LocatedAtFavorite(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_LocatedAtHome(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_LocatedAtWork(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_Location(self, callback: Callable[[TeslaLocation | None], None]) -> Callable[[],None]`
- `listen_Locked(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_LongitudinalAcceleration(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_MilesToArrival(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_MinutesToArrival(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_ModuleTempMax(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_ModuleTempMin(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_NotEnoughPowerToHeat(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_NumBrickVoltageMax(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_NumBrickVoltageMin(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_NumModuleTempMax(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_NumModuleTempMin(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_Odometer(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_OffroadLightbarPresent(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_OriginLocation(self, callback: Callable[[TeslaLocation | None], None]) -> Callable[[],None]`
- `listen_OutsideTemp(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_PackCurrent(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_PackVoltage(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_PairedPhoneKeyAndKeyFobQty(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_PassengerSeatBelt(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_PedalPosition(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_PinToDriveEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_PowershareHoursLeft(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_PowershareInstantaneousPowerKW(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_PowershareStatus(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_PowershareStopReason(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_PowershareType(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_PreconditioningEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_RatedRange(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_RearDriverWindow(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_RearDisplayHvacEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_RearSeatHeaters(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_RemoteStartEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_RightHandDrive(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_RoofColor(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_RouteLastUpdated(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_RouteTrafficMinutesDelay(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_RearPassengerWindow(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ScheduledChargingMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ScheduledChargingPending(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_ScheduledChargingStartTime(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ScheduledDepartureTime(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_SeatHeaterLeft(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_SeatHeaterRearCenter(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_SeatHeaterRearLeft(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_SeatHeaterRearRight(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_SeatHeaterRight(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_SentryMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ServiceMode(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_Setting24HourTime(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_SettingChargeUnit(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_SettingDistanceUnit(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_SettingTemperatureUnit(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_SettingTirePressureUnit(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_Soc(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_SoftwareUpdateDownloadPercentComplete(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_SoftwareUpdateExpectedDurationMinutes(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_SoftwareUpdateInstallationPercentComplete(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_SoftwareUpdateScheduledStartTime(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_SoftwareUpdateVersion(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_SpeedLimitMode(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_SpeedLimitWarning(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_SuperchargerSessionTripPlanner(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_TimeToFullCharge(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_TonneauOpenPercent(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_TonneauPosition(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_TonneauTentMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_TpmsHardWarnings(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_TpmsLastSeenPressureTimeFl(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_TpmsLastSeenPressureTimeFr(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_TpmsLastSeenPressureTimeRl(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_TpmsLastSeenPressureTimeRr(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_TpmsPressureFl(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_TpmsPressureFr(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_TpmsPressureRl(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_TpmsPressureRr(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_TpmsSoftWarnings(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_Trim(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_ValetModeEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_VehicleName(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_VehicleSpeed(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_Version(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_WheelType(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_WiperHeatEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_LightsHazardsActive(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_LightsTurnSignal(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_LightsHighBeams(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_MediaPlaybackStatus(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_MediaPlaybackSource(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_MediaAudioVolume(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_MediaNowPlayingDuration(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_MediaNowPlayingElapsed(self, callback: Callable[[int | None], None]) -> Callable[[],None]`
- `listen_MediaNowPlayingArtist(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_MediaNowPlayingTitle(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_MediaNowPlayingAlbum(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_MediaNowPlayingStation(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_MediaAudioVolumeIncrement(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_MediaAudioVolumeMax(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
- `listen_SunroofInstalled(self, callback: Callable[[str | None], None]) -> Callable[[],None]`
- `listen_SeatVentEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_RearDefrostEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]`
- `listen_ChargeRateMilePerHour(self, callback: Callable[[float | None], None]) -> Callable[[],None]`
