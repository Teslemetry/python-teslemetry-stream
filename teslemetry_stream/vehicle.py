"""Vehicle class for handling streaming field updates."""

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from .const import (
    BMSState,
    #BuckleStatus,
    CabinOverheatProtectionModeState,
    CableType,
    CarType,
    ChargePort,
    ChargePortLatch,
    ChargeState,
    ChargeUnitPreference,
    #ChargeUnitPreference,
    ClimateKeeperModeState,
    ClimateOverheatProtectionTempLimit,
    DefrostModeState,
    DetailedChargeState,
    DisplayState,
    DistanceUnit,
    #DistanceUnit,
    DriveInverterState,
    FastCharger,
    FollowDistance,
    ForwardCollisionSensitivity,
    GuestModeMobileAccess,
    HvacAutoModeState,
    HvacPowerState,
    HvilStatus,
    LaneAssistLevel,
    PowershareState,
    PowershareStopReasonStatus,
    PowershareTypeStatus,
    PressureUnit,
    #PressureUnit,
    ScheduledChargingMode,
    #SeatFoldPosition,
    SentryModeState,
    ShiftState,
    Signal,
    TemperatureUnit,
    #SpeedAssistLevel,
    #TemperatureUnit,
    TeslaLocation,
    #TonneauPositionState,
    #TonneauTentModeState,
    #TractorAirStatus,
    #TrailerAirStatus,
    WindowState,
)

if TYPE_CHECKING:
    from .stream import TeslemetryStream
else:
    TeslemetryStream = None

LOGGER = logging.getLogger(__package__)

class TeslemetryStreamVehicle:
    """Handle streaming field updates."""

    fields: dict[Signal, dict[str, int]] = {}
    preferTyped: bool | None = None
    _config: dict = {}

    def __init__(self, stream: TeslemetryStream, vin: str):
        # A dictionary of TelemetryField keys and null values
        self.stream = stream
        self.vin: str = vin
        self.lock = asyncio.Lock()

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return {
            "fields": self.fields,
            "prefer_typed": self.preferTyped,
        }

    async def get_config(self) -> None:
        """Get the current configuration for the vehicle."""

        req = await self.stream._session.get(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=self.stream._headers,
            raise_for_status=True,
        )
        response = await req.json()

        self.fields = response.get("fields")
        self.preferTyped = response.get("prefer_typed",False)

    async def update_config(self, config: dict) -> None:
        """Update the configuration for the vehicle."""

        # Lock so that we dont change the config while making the API call
        async with self.lock:
            self._config = merge(config, self._config)

        await asyncio.sleep(1)

        async with self.lock:
            if not self._config:
                return

            data = await self.patch_config(self._config)
            if error := data.get("error"):
                LOGGER.error("Error updating streaming config for %s: %s", self.vin, error)
                return
            elif data.get("response",{}).get("updated_vehicles"):
                LOGGER.info("Updated vehicle streaming config for %s", self.vin)
                if fields := self._config.get("fields"):
                    LOGGER.debug("Configured streaming fields %s", ", ".join(fields.keys()))
                    self.fields = {**self.fields, **fields}
                if prefer_typed := self._config.get("prefer_typed") in [True, False]:
                    LOGGER.debug("Configured streaming typed to %s", prefer_typed)
                    self.preferTyped = prefer_typed
                self._config.clear()


    async def patch_config(self, config: dict) -> dict[str, str|dict]:
        """Modify the configuration for the vehicle."""
        resp = await self.stream._session.patch(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=self.stream._headers,
            json=config,
            raise_for_status=False,
        )
        return await resp.json()

    async def post_config(self, config: dict) -> dict[str, str|dict]:
        """Overwrite the configuration for the vehicle."""
        resp = await self.stream._session.post(
            f"https://api.teslemetry.com/api/config/{self.vin}",
            headers=self.stream._headers,
            json=config,
            raise_for_status=False,
        )
        return await resp.json()

    async def add_field(self, field: Signal | str, interval: int | None = None) -> None:
        """Handle vehicle data from the stream."""
        if isinstance(field, Signal):
            field = field.value

        if field in self.fields and (interval is None or self.fields[field].get("interval_seconds") == interval):
            LOGGER.debug("Streaming field %s already enabled @ %ss", field, self.fields[field].get('interval_seconds'))
            return

        value = {"interval_seconds": interval} if interval else None
        await self.update_config({"fields": {field: value}})

    async def prefer_typed(self, prefer_typed: bool) -> None:
        """Set prefer typed."""
        if self.preferTyped == prefer_typed:
            LOGGER.debug("Streaming typed already set to %s", prefer_typed)
            return
        await self.update_config({"prefer_typed": prefer_typed})

    # Add listeners for each signal

    def listen_ACChargingEnergyIn(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for AC Charging Energy In."""
        return self.stream.async_add_listener(
            make_float(Signal.AC_CHARGING_ENERGY_IN, callback),
            {"vin":self.vin, "data": {Signal.AC_CHARGING_ENERGY_IN: None}}
        )

    def listen_ACChargingPower(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for AC Charging Power."""
        return self.stream.async_add_listener(
            make_float(Signal.AC_CHARGING_POWER, callback),
            {"vin":self.vin, "data": {Signal.AC_CHARGING_POWER: None}}
        )

    def listen_AutoSeatClimateLeft(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Auto Seat Climate Left."""
        return self.stream.async_add_listener(
            make_bool(Signal.AUTO_SEAT_CLIMATE_LEFT, callback),
            {"vin":self.vin, "data": {Signal.AUTO_SEAT_CLIMATE_LEFT: None}}
        )

    def listen_AutoSeatClimateRight(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Auto Seat Climate Right."""
        return self.stream.async_add_listener(
            make_bool(Signal.AUTO_SEAT_CLIMATE_RIGHT, callback),
            {"vin":self.vin, "data": {Signal.AUTO_SEAT_CLIMATE_RIGHT: None}}
        )

    def listen_AutomaticBlindSpotCamera(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Automatic Blind Spot Camera."""
        return self.stream.async_add_listener(
            make_bool(Signal.AUTOMATIC_BLIND_SPOT_CAMERA, callback),
            {"vin":self.vin, "data": {Signal.AUTOMATIC_BLIND_SPOT_CAMERA: None}}
        )

    def listen_AutomaticEmergencyBrakingOff(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Automatic Emergency Braking Off."""
        return self.stream.async_add_listener(
            make_bool(Signal.AUTOMATIC_EMERGENCY_BRAKING_OFF, callback),
            {"vin":self.vin, "data": {Signal.AUTOMATIC_EMERGENCY_BRAKING_OFF: None}}
        )

    def listen_BMSState(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for BMS State."""
        return self.stream.async_add_listener(
            lambda x: callback(BMSState.get(x['data'][Signal.BMS_STATE])),
            {"vin":self.vin, "data": {Signal.BMS_STATE: None}}
        )

    def listen_BatteryHeaterOn(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Battery Heater On."""
        return self.stream.async_add_listener(
            make_bool(Signal.BATTERY_HEATER_ON, callback), #Unsure about this
            {"vin":self.vin, "data": {Signal.BATTERY_HEATER_ON: None}}
        )

    def listen_BatteryLevel(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Battery Level."""
        return self.stream.async_add_listener(
            make_float(Signal.BATTERY_LEVEL, callback),
            {"vin":self.vin, "data": {Signal.BATTERY_LEVEL: None}}
        )

    def listen_BlindSpotCollisionWarningChime(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Blind Spot Collision Warning Chime."""
        return self.stream.async_add_listener(
            make_bool(Signal.BLIND_SPOT_COLLISION_WARNING_CHIME, callback),
            {"vin":self.vin, "data": {Signal.BLIND_SPOT_COLLISION_WARNING_CHIME: None}}
        )

    def listen_BmsFullchargecomplete(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for BMS Full Charge Complete."""
        return self.stream.async_add_listener(
            make_bool(Signal.BMS_FULL_CHARGE_COMPLETE, callback),
            {"vin":self.vin, "data": {Signal.BMS_FULL_CHARGE_COMPLETE: None}}
        )

    def listen_BrakePedal(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Brake Pedal."""
        return self.stream.async_add_listener(
            make_bool(Signal.BRAKE_PEDAL, callback),
            {"vin":self.vin, "data": {Signal.BRAKE_PEDAL: None}}
        )

    def listen_BrakePedalPos(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Brake Pedal Position."""
        return self.stream.async_add_listener(
            make_float(Signal.BRAKE_PEDAL_POS, callback),
            {"vin":self.vin, "data": {Signal.BRAKE_PEDAL_POS: None}}
        )

    def listen_BrickVoltageMax(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Brick Voltage Maximum."""
        return self.stream.async_add_listener(
            make_float(Signal.BRICK_VOLTAGE_MAX, callback),
            {"vin":self.vin, "data": {Signal.BRICK_VOLTAGE_MAX: None}}
        )

    def listen_BrickVoltageMin(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Brick Voltage Minimum."""
        return self.stream.async_add_listener(
            make_float(Signal.BRICK_VOLTAGE_MIN, callback),
            {"vin":self.vin, "data": {Signal.BRICK_VOLTAGE_MIN: None}}
        )

    def listen_CabinOverheatProtectionMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Cabin Overheat Protection Mode."""
        return self.stream.async_add_listener(
            lambda x: callback(CabinOverheatProtectionModeState.get(x['data'][Signal.CABIN_OVERHEAT_PROTECTION_MODE])),
            {"vin":self.vin, "data": {Signal.CABIN_OVERHEAT_PROTECTION_MODE: None}}
        )

    def listen_CabinOverheatProtectionTemperatureLimit(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Cabin Overheat Protection Temperature Limit."""
        return self.stream.async_add_listener(
            lambda x: callback(ClimateOverheatProtectionTempLimit.get(x['data'][Signal.CABIN_OVERHEAT_PROTECTION_TEMPERATURE_LIMIT])),
            {"vin":self.vin, "data": {Signal.CABIN_OVERHEAT_PROTECTION_TEMPERATURE_LIMIT: None}}
        )

    def listen_CarType(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Car Type."""
        return self.stream.async_add_listener(
            lambda x: callback(CarType.get(x['data'][Signal.CAR_TYPE])),
            {"vin":self.vin, "data": {Signal.CAR_TYPE: None}}
        )

    def listen_CenterDisplay(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Center Display."""
        return self.stream.async_add_listener(
            lambda x: callback(DisplayState.get(x['data'][Signal.CENTER_DISPLAY])),
            {"vin":self.vin, "data": {Signal.CENTER_DISPLAY: None}}
        )

    def listen_ChargeAmps(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Charge Amps."""
        return self.stream.async_add_listener(
            make_float(Signal.CHARGE_AMPS, callback),
            {"vin":self.vin, "data": {Signal.CHARGE_AMPS: None}}
        )

    def listen_ChargeCurrentRequest(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Charge Current Request."""
        return self.stream.async_add_listener(
            make_int(Signal.CHARGE_CURRENT_REQUEST, callback),
            {"vin":self.vin, "data": {Signal.CHARGE_CURRENT_REQUEST: None}}
        )

    def listen_ChargeCurrentRequestMax(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Charge Current Request Max."""
        return self.stream.async_add_listener(
            make_int(Signal.CHARGE_CURRENT_REQUEST_MAX, callback),
            {"vin":self.vin, "data": {Signal.CHARGE_CURRENT_REQUEST_MAX: None}}
        )

    def listen_ChargeEnableRequest(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Charge Enable Request."""
        return self.stream.async_add_listener(
            make_bool(Signal.CHARGE_ENABLE_REQUEST, callback),
            {"vin":self.vin, "data": {Signal.CHARGE_ENABLE_REQUEST: None}}
        )

    def listen_ChargeLimitSoc(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Charge Limit State of Charge."""
        return self.stream.async_add_listener(
            make_int(Signal.CHARGE_LIMIT_SOC, callback),
            {"vin":self.vin, "data": {Signal.CHARGE_LIMIT_SOC: None}}
        )

    def listen_ChargePort(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Charge Port."""
        return self.stream.async_add_listener(
            lambda x: callback(ChargePort.get(x['data'][Signal.CHARGE_PORT])),
            {"vin":self.vin, "data": {Signal.CHARGE_PORT: None}}
        )

    def listen_ChargePortColdWeatherMode(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Charge Port Cold Weather Mode."""
        return self.stream.async_add_listener(
            make_bool(Signal.CHARGE_PORT_COLD_WEATHER_MODE, callback),
            {"vin":self.vin, "data": {Signal.CHARGE_PORT_COLD_WEATHER_MODE: None}}
        )

    def listen_ChargePortDoorOpen(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Charge Port Door Open."""
        return self.stream.async_add_listener(
            make_bool(Signal.CHARGE_PORT_DOOR_OPEN, callback),
            {"vin":self.vin, "data": {Signal.CHARGE_PORT_DOOR_OPEN: None}}
        )

    def listen_ChargePortLatch(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Charge Port Latch."""
        return self.stream.async_add_listener(
            lambda x: callback(ChargePortLatch.get(x['data'][Signal.CHARGE_PORT_LATCH])),
            {"vin":self.vin, "data": {Signal.CHARGE_PORT_LATCH: None}}
        )

    def listen_ChargeState(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Charge State."""
        return self.stream.async_add_listener(
            lambda x: callback(ChargeState.get(x['data'][Signal.CHARGE_STATE])),
            {"vin":self.vin, "data": {Signal.CHARGE_STATE: None}}
        )

    def listen_ChargerPhases(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Charger Phases."""
        return self.stream.async_add_listener(
            make_int(Signal.CHARGER_PHASES, callback),
            {"vin":self.vin, "data": {Signal.CHARGER_PHASES: None}}
        )

    def listen_ChargingCableType(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Charging Cable Type."""
        return self.stream.async_add_listener(
            lambda x: callback(CableType.get(x['data'][Signal.CHARGING_CABLE_TYPE])),
            {"vin":self.vin, "data": {Signal.CHARGING_CABLE_TYPE: None}}
        )

    def listen_ClimateKeeperMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Climate Keeper Mode."""
        return self.stream.async_add_listener(
            lambda x: callback(ClimateKeeperModeState.get(x['data'][Signal.CLIMATE_KEEPER_MODE])),
            {"vin":self.vin, "data": {Signal.CLIMATE_KEEPER_MODE: None}}
        )

    def listen_ClimateSeatCoolingFrontLeft(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Climate Seat Cooling Front Left."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.CLIMATE_SEAT_COOLING_FRONT_LEFT]), # This should enum but I dont know what
            {"vin":self.vin, "data": {Signal.CLIMATE_SEAT_COOLING_FRONT_LEFT: None}}
        )

    def listen_ClimateSeatCoolingFrontRight(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Climate Seat Cooling Front Right."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.CLIMATE_SEAT_COOLING_FRONT_RIGHT]),
            {"vin":self.vin, "data": {Signal.CLIMATE_SEAT_COOLING_FRONT_RIGHT: None}}
        )

    def listen_CruiseFollowDistance(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Cruise Follow Distance."""
        return self.stream.async_add_listener(
            lambda x: callback(FollowDistance.get(x['data'][Signal.CRUISE_FOLLOW_DISTANCE])),
            {"vin":self.vin, "data": {Signal.CRUISE_FOLLOW_DISTANCE: None}}
        )

    def listen_CruiseSetSpeed(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Cruise Set Speed."""
        return self.stream.async_add_listener(
            make_int(Signal.CRUISE_SET_SPEED, callback),
            {"vin":self.vin, "data": {Signal.CRUISE_SET_SPEED: None}}
        )

    def listen_CurrentLimitMph(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Current Limit MPH."""
        return self.stream.async_add_listener(
            make_int(Signal.CURRENT_LIMIT_MPH, callback),
            {"vin":self.vin, "data": {Signal.CURRENT_LIMIT_MPH: None}}
        )

    def listen_DCChargingEnergyIn(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for DC Charging Energy In."""
        return self.stream.async_add_listener(
            make_float(Signal.DC_CHARGING_ENERGY_IN, callback),
            {"vin":self.vin, "data": {Signal.DC_CHARGING_ENERGY_IN: None}}
        )

    def listen_DCChargingPower(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for DC Charging Power."""
        return self.stream.async_add_listener(
            make_float(Signal.DC_CHARGING_POWER, callback),
            {"vin":self.vin, "data": {Signal.DC_CHARGING_POWER: None}}
        )

    def listen_DCDCEnable(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for DC DC Enable."""
        return self.stream.async_add_listener(
            make_bool(Signal.DCDC_ENABLE, callback),
            {"vin":self.vin, "data": {Signal.DCDC_ENABLE: None}}
        )

    def listen_DefrostForPreconditioning(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Defrost For Preconditioning."""
        return self.stream.async_add_listener(
            make_bool(Signal.DEFROST_FOR_PRECONDITIONING, callback),
            {"vin":self.vin, "data": {Signal.DEFROST_FOR_PRECONDITIONING: None}}
        )

    def listen_DefrostMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Defrost Mode."""
        return self.stream.async_add_listener(
            lambda x: callback(DefrostModeState.get(x['data'][Signal.DEFROST_MODE])),
            {"vin":self.vin, "data": {Signal.DEFROST_MODE: None}}
        )

    def listen_DestinationLocation(self, callback: Callable[[dict | None], None]) -> Callable[[],None]:
        """Listen for Destination Location."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.DESTINATION_LOCATION]),
            {"vin":self.vin, "data": {Signal.DESTINATION_LOCATION: None}}
        )

    def listen_DestinationName(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Destination Name."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.DESTINATION_NAME]),
            {"vin":self.vin, "data": {Signal.DESTINATION_NAME: None}}
        )

    def listen_DetailedChargeState(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Detailed Charge State."""
        return self.stream.async_add_listener(
            lambda x: callback(DetailedChargeState.get(x['data'][Signal.DETAILED_CHARGE_STATE])),
            {"vin":self.vin, "data": {Signal.DETAILED_CHARGE_STATE: None}}
        )

    def listen_DiAxleSpeedF(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Axle Speed Front."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_AXLE_SPEED_F, callback),
            {"vin":self.vin, "data": {Signal.DI_AXLE_SPEED_F: None}}
        )

    def listen_DiAxleSpeedR(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Axle Speed Rear."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_AXLE_SPEED_R, callback),
            {"vin":self.vin, "data": {Signal.DI_AXLE_SPEED_R: None}}
        )

    def listen_DiAxleSpeedREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Axle Speed Rear Left."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_AXLE_SPEED_REL, callback),
            {"vin":self.vin, "data": {Signal.DI_AXLE_SPEED_REL: None}}
        )

    def listen_DiAxleSpeedRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Axle Speed Rear Right."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_AXLE_SPEED_RER, callback),
            {"vin":self.vin, "data": {Signal.DI_AXLE_SPEED_RER: None}}
        )

    def listen_DiHeatsinkTF(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Heatsink Temperature Front."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_HEATSINK_T_F, callback),
            {"vin":self.vin, "data": {Signal.DI_HEATSINK_T_F: None}}
        )

    def listen_DiHeatsinkTR(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Heatsink Temperature Rear."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_HEATSINK_T_R, callback),
            {"vin":self.vin, "data": {Signal.DI_HEATSINK_T_R: None}}
        )

    def listen_DiHeatsinkTREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Heatsink Temperature Rear Left."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_HEATSINK_T_REL, callback),
            {"vin":self.vin, "data": {Signal.DI_HEATSINK_T_REL: None}}
        )

    def listen_DiHeatsinkTRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Heatsink Temperature Rear Right."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_HEATSINK_T_RER, callback),
            {"vin":self.vin, "data": {Signal.DI_HEATSINK_T_RER: None}}
        )

    def listen_DiInverterTF(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Temperature Front."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_INVERTER_T_F, callback),
            {"vin":self.vin, "data": {Signal.DI_INVERTER_T_F: None}}
        )

    def listen_DiInverterTR(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Temperature Rear."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_INVERTER_T_R, callback),
            {"vin":self.vin, "data": {Signal.DI_INVERTER_T_R: None}}
        )

    def listen_DiInverterTREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Temperature Rear Left."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_INVERTER_T_REL, callback),
            {"vin":self.vin, "data": {Signal.DI_INVERTER_T_REL: None}}
        )

    def listen_DiInverterTRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Temperature Rear Right."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_INVERTER_T_RER, callback),
            {"vin":self.vin, "data": {Signal.DI_INVERTER_T_RER: None}}
        )

    def listen_DiMotorCurrentF(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Motor Current Front."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_MOTOR_CURRENT_F, callback),
            {"vin":self.vin, "data": {Signal.DI_MOTOR_CURRENT_F: None}}
        )

    def listen_DiMotorCurrentR(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Motor Current Rear."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_MOTOR_CURRENT_R, callback),
            {"vin":self.vin, "data": {Signal.DI_MOTOR_CURRENT_R: None}}
        )

    def listen_DiMotorCurrentREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Motor Current Rear Left."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_MOTOR_CURRENT_REL, callback),
            {"vin":self.vin, "data": {Signal.DI_MOTOR_CURRENT_REL: None}}
        )

    def listen_DiMotorCurrentRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Motor Current Rear Right."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_MOTOR_CURRENT_RER, callback),
            {"vin":self.vin, "data": {Signal.DI_MOTOR_CURRENT_RER: None}}
        )

    def listen_DiSlaveTorqueCmd(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Slave Torque Command."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_SLAVE_TORQUE_CMD, callback),
            {"vin":self.vin, "data": {Signal.DI_SLAVE_TORQUE_CMD: None}}
        )

    def listen_DiStateF(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter State Front."""
        return self.stream.async_add_listener(
            lambda x: callback(DriveInverterState.get(x['data'][Signal.DI_STATE_F])),
            {"vin":self.vin, "data": {Signal.DI_STATE_F: None}}
        )

    def listen_DiStateR(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter State Rear."""
        return self.stream.async_add_listener(
            lambda x: callback(DriveInverterState.get(x['data'][Signal.DI_STATE_R])),
            {"vin":self.vin, "data": {Signal.DI_STATE_R: None}}
        )

    def listen_DiStateREL(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter State Rear Left."""
        return self.stream.async_add_listener(
            lambda x: callback(DriveInverterState.get(x['data'][Signal.DI_STATE_REL])),
            {"vin":self.vin, "data": {Signal.DI_STATE_REL: None}}
        )

    def listen_DiStateRER(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter State Rear Right."""
        return self.stream.async_add_listener(
            lambda x: callback(DriveInverterState.get(x['data'][Signal.DI_STATE_RER])),
            {"vin":self.vin, "data": {Signal.DI_STATE_RER: None}}
        )

    def listen_DiStatorTempF(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Stator Temperature Front."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_STATOR_TEMP_F, callback),
            {"vin":self.vin, "data": {Signal.DI_STATOR_TEMP_F: None}}
        )

    def listen_DiStatorTempR(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Stator Temperature Rear."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_STATOR_TEMP_R, callback),
            {"vin":self.vin, "data": {Signal.DI_STATOR_TEMP_R: None}}
        )

    def listen_DiStatorTempREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Stator Temperature Rear Left."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_STATOR_TEMP_REL, callback),
            {"vin":self.vin, "data": {Signal.DI_STATOR_TEMP_REL: None}}
        )

    def listen_DiStatorTempRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Stator Temperature Rear Right."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_STATOR_TEMP_RER, callback),
            {"vin":self.vin, "data": {Signal.DI_STATOR_TEMP_RER: None}}
        )

    def listen_DiTorqueActualF(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Torque Actual Front."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_TORQUE_ACTUAL_F, callback),
            {"vin":self.vin, "data": {Signal.DI_TORQUE_ACTUAL_F: None}}
        )

    def listen_DiTorqueActualR(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
            """Listen for Drive Inverter Torque Actual Rear."""
            return self.stream.async_add_listener(
                make_float(Signal.DI_TORQUE_ACTUAL_R, callback),
                {"vin":self.vin, "data": {Signal.DI_TORQUE_ACTUAL_R: None}}
            )

    def listen_DiTorqueActualREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Torque Actual Rear Left."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_TORQUE_ACTUAL_REL, callback),
            {"vin":self.vin, "data": {Signal.DI_TORQUE_ACTUAL_REL: None}}
        )

    def listen_DiTorqueActualRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Torque Actual Rear Right."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_TORQUE_ACTUAL_RER, callback),
            {"vin":self.vin, "data": {Signal.DI_TORQUE_ACTUAL_RER: None}}
        )

    def listen_DiTorquemotor(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Torque Motor."""
        return self.stream.async_add_listener(
            make_int(Signal.DI_TORQUEMOTOR, callback),
            {"vin":self.vin, "data": {Signal.DI_TORQUEMOTOR: None}}
        )

    def listen_DiVBatF(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Battery Voltage Front."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_V_BAT_F, callback),
            {"vin":self.vin, "data": {Signal.DI_V_BAT_F: None}}
        )

    def listen_DiVBatR(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Battery Voltage Rear."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_V_BAT_R, callback),
            {"vin":self.vin, "data": {Signal.DI_V_BAT_R: None}}
        )

    def listen_DiVBatREL(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Battery Voltage Rear Left."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_V_BAT_REL, callback),
            {"vin":self.vin, "data": {Signal.DI_V_BAT_REL: None}}
        )

    def listen_DiVBatRER(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Drive Inverter Battery Voltage Rear Right."""
        return self.stream.async_add_listener(
            make_float(Signal.DI_V_BAT_RER, callback),
            {"vin":self.vin, "data": {Signal.DI_V_BAT_RER: None}}
        )

    def listen_DoorState(self, callback: Callable[[dict | None], None]) -> Callable[[],None]:
        """Listen for Door State."""
        return self.stream.async_add_listener(
            make_dict(Signal.DOOR_STATE, callback),
            {"vin":self.vin, "data": {Signal.DOOR_STATE: None}}
        )

    def listen_FrontDriverDoor(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Front Driver Door State."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.DOOR_STATE].get("DriverFront")),
            {"vin":self.vin, "data": {Signal.DOOR_STATE: None}}
        )

    def listen_RearDriverDoor(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Rear Driver Door State."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.DOOR_STATE].get("DriverRear")),
            {"vin":self.vin, "data": {Signal.DOOR_STATE: None}}
        )

    def listen_FrontPassengerDoor(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Front Passenger Door State."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.DOOR_STATE].get("PassengerFront")),
            {"vin":self.vin, "data": {Signal.DOOR_STATE: None}}
        )

    def listen_RearPassengerDoor(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Rear Passenger Door State."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.DOOR_STATE].get("PassengerRear")),
            {"vin":self.vin, "data": {Signal.DOOR_STATE: None}}
        )

    def listen_TrunkFront(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Front Trunk Door State."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.DOOR_STATE].get("TrunkFront")),
            {"vin":self.vin, "data": {Signal.DOOR_STATE: None}}
        )

    def listen_TrunkRear(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Rear Trunk Door State."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.DOOR_STATE].get("TrunkRear")),
            {"vin":self.vin, "data": {Signal.DOOR_STATE: None}}
        )

    def listen_DriveRail(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Drive Rail."""
        return self.stream.async_add_listener(
            make_bool(Signal.DRIVE_RAIL, callback),
            {"vin":self.vin, "data": {Signal.DRIVE_RAIL: None}}
        )

    def listen_DriverSeatBelt(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Driver Seat Belt."""
        return self.stream.async_add_listener(
            make_bool(Signal.DRIVER_SEAT_BELT, callback), #BuckleStatus?
            {"vin":self.vin, "data": {Signal.DRIVER_SEAT_BELT: None}}
        )

    def listen_DriverSeatOccupied(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Driver Seat Occupied."""
        return self.stream.async_add_listener(
            make_bool(Signal.DRIVER_SEAT_OCCUPIED, callback),
            {"vin":self.vin, "data": {Signal.DRIVER_SEAT_OCCUPIED: None}}
        )

    def listen_EfficiencyPackage(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Efficiency Package."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.EFFICIENCY_PACKAGE]),
            {"vin":self.vin, "data": {Signal.EFFICIENCY_PACKAGE: None}}
        )

    def listen_EmergencyLaneDepartureAvoidance(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Emergency Lane Departure Avoidance."""
        return self.stream.async_add_listener(
            make_bool(Signal.EMERGENCY_LANE_DEPARTURE_AVOIDANCE, callback),
            {"vin":self.vin, "data": {Signal.EMERGENCY_LANE_DEPARTURE_AVOIDANCE: None}}
        )

    def listen_EnergyRemaining(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Energy Remaining."""
        return self.stream.async_add_listener(
            make_float(Signal.ENERGY_REMAINING, callback),
            {"vin":self.vin, "data": {Signal.ENERGY_REMAINING: None}}
        )

    def listen_EstBatteryRange(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Estimated Battery Range."""
        return self.stream.async_add_listener(
            make_float(Signal.EST_BATTERY_RANGE, callback),
            {"vin":self.vin, "data": {Signal.EST_BATTERY_RANGE: None}}
        )

    def listen_EstimatedHoursToChargeTermination(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Estimated Hours to Charge Termination."""
        return self.stream.async_add_listener(
            make_float(Signal.ESTIMATED_HOURS_TO_CHARGE_TERMINATION, callback),
            {"vin":self.vin, "data": {Signal.ESTIMATED_HOURS_TO_CHARGE_TERMINATION: None}}
        )

    def listen_EuropeVehicle(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Europe Vehicle."""
        return self.stream.async_add_listener(
            make_bool(Signal.EUROPE_VEHICLE, callback),
            {"vin":self.vin, "data": {Signal.EUROPE_VEHICLE: None}}
        )

    def listen_ExpectedEnergyPercentAtTripArrival(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Expected Energy Percent at Trip Arrival."""
        return self.stream.async_add_listener(
            make_int(Signal.EXPECTED_ENERGY_PERCENT_AT_TRIP_ARRIVAL, callback),
            {"vin":self.vin, "data": {Signal.EXPECTED_ENERGY_PERCENT_AT_TRIP_ARRIVAL: None}}
        )

    def listen_ExteriorColor(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Exterior Color."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.EXTERIOR_COLOR]),
            {"vin":self.vin, "data": {Signal.EXTERIOR_COLOR: None}}
        )

    def listen_FastChargerPresent(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Fast Charger Present."""
        return self.stream.async_add_listener(
            make_bool(x['data'][Signal.FAST_CHARGER_PRESENT], callback),
            {"vin":self.vin, "data": {Signal.FAST_CHARGER_PRESENT: None}}
        )

    def listen_FastChargerType(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Fast Charger Type."""
        return self.stream.async_add_listener(
            lambda x: callback(FastCharger.get(x['data'][Signal.FAST_CHARGER_TYPE])),
            {"vin":self.vin, "data": {Signal.FAST_CHARGER_TYPE: None}}
        )

    def listen_FrontDriverWindow(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Front Driver Window State."""
        return self.stream.async_add_listener(
            lambda x: callback(WindowState.get(x['data'][Signal.FD_WINDOW])),
            {"vin":self.vin, "data": {Signal.FD_WINDOW: None}}
        )

    def listen_ForwardCollisionWarning(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Forward Collision Warning."""
        return self.stream.async_add_listener(
            lambda x: callback(ForwardCollisionSensitivity.get(x['data'][Signal.FORWARD_COLLISION_WARNING])),
            {"vin":self.vin, "data": {Signal.FORWARD_COLLISION_WARNING: None}}
        )

    def listen_FrontPassengerWindow(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Front Passenger Window State."""
        return self.stream.async_add_listener(
            lambda x: callback(WindowState.get(x['data'][Signal.FP_WINDOW])),
            {"vin":self.vin, "data": {Signal.FP_WINDOW: None}}
        )

    def listen_Gear(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Gear State."""
        return self.stream.async_add_listener(
            lambda x: callback(ShiftState.get(x['data'][Signal.GEAR])),
            {"vin":self.vin, "data": {Signal.GEAR: None}}
        )

    def listen_GpsHeading(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for GPS Heading."""
        return self.stream.async_add_listener(
            make_float(Signal.GPS_HEADING, callback),
            {"vin":self.vin, "data": {Signal.GPS_HEADING: None}}
        )

    def listen_GpsState(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for GPS State."""
        return self.stream.async_add_listener(
            make_bool(Signal.GPS_STATE, callback),
            {"vin":self.vin, "data": {Signal.GPS_STATE: None}}
        )

    def listen_GuestModeEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Guest Mode Enabled."""
        return self.stream.async_add_listener(
            make_bool(Signal.GUEST_MODE_ENABLED, callback),
            {"vin":self.vin, "data": {Signal.GUEST_MODE_ENABLED: None}}
        )

    def listen_GuestModeMobileAccessState(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Guest Mode Mobile Access State."""
        return self.stream.async_add_listener(
            lambda x: callback(GuestModeMobileAccess.get(x['data'][Signal.GUEST_MODE_MOBILE_ACCESS_STATE])),
            {"vin":self.vin, "data": {Signal.GUEST_MODE_MOBILE_ACCESS_STATE: None}}
        )

    def listen_HomelinkDeviceCount(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Homelink Device Count."""
        return self.stream.async_add_listener(
            make_int(Signal.HOMELINK_DEVICE_COUNT, callback),
            {"vin":self.vin, "data": {Signal.HOMELINK_DEVICE_COUNT: None}}
        )

    def listen_HomelinkNearby(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Homelink Nearby."""
        return self.stream.async_add_listener(
            make_bool(Signal.HOMELINK_NEARBY, callback),
            {"vin":self.vin, "data": {Signal.HOMELINK_NEARBY: None}}
        )

    def listen_HvacACEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for HVAC AC Enabled."""
        return self.stream.async_add_listener(
            make_bool(Signal.HVAC_AC_ENABLED, callback),
            {"vin":self.vin, "data": {Signal.HVAC_AC_ENABLED: None}}
        )

    def listen_HvacAutoMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for HVAC Auto Mode."""
        return self.stream.async_add_listener(
            lambda x: callback(HvacAutoModeState.get(x['data'][Signal.HVAC_AUTO_MODE])),
            {"vin":self.vin, "data": {Signal.HVAC_AUTO_MODE: None}}
        )

    def listen_HvacFanSpeed(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for HVAC Fan Speed."""
        return self.stream.async_add_listener(
            make_int(Signal.HVAC_FAN_SPEED, callback),
            {"vin":self.vin, "data": {Signal.HVAC_FAN_SPEED: None}}
        )

    def listen_HvacFanStatus(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for HVAC Fan Status."""
        return self.stream.async_add_listener(
            make_int(Signal.HVAC_FAN_STATUS, callback),
            {"vin":self.vin, "data": {Signal.HVAC_FAN_STATUS: None}}
        )

    def listen_HvacLeftTemperatureRequest(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for HVAC Left Temperature Request."""
        return self.stream.async_add_listener(
            make_float(Signal.HVAC_LEFT_TEMPERATURE_REQUEST, callback),
            {"vin":self.vin, "data": {Signal.HVAC_LEFT_TEMPERATURE_REQUEST: None}}
        )

    def listen_HvacPower(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for HVAC Power."""
        return self.stream.async_add_listener(
            lambda x: callback(HvacPowerState.get(x['data'][Signal.HVAC_POWER])),
            {"vin":self.vin, "data": {Signal.HVAC_POWER: None}}
        )

    def listen_HvacRightTemperatureRequest(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for HVAC Right Temperature Request."""
        return self.stream.async_add_listener(
            make_float(Signal.HVAC_RIGHT_TEMPERATURE_REQUEST, callback),
            {"vin":self.vin, "data": {Signal.HVAC_RIGHT_TEMPERATURE_REQUEST: None}}
        )

    def listen_HvacSteeringWheelHeatAuto(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for HVAC Steering Wheel Heat Auto."""
        return self.stream.async_add_listener(
            make_bool(Signal.HVAC_STEERING_WHEEL_HEAT_AUTO, callback),
            {"vin":self.vin, "data": {Signal.HVAC_STEERING_WHEEL_HEAT_AUTO: None}}
        )

    def listen_HvacSteeringWheelHeatLevel(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for HVAC Steering Wheel Heat Level."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.HVAC_STEERING_WHEEL_HEAT_LEVEL]),
            {"vin":self.vin, "data": {Signal.HVAC_STEERING_WHEEL_HEAT_LEVEL: None}}
        )

    def listen_Hvil(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for HVIL."""
        return self.stream.async_add_listener(
            lambda x: callback(HvilStatus.get(x['data'][Signal.HVIL])),
            {"vin":self.vin, "data": {Signal.HVIL: None}}
        )

    def listen_IdealBatteryRange(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Ideal Battery Range."""
        return self.stream.async_add_listener(
            make_float(Signal.IDEAL_BATTERY_RANGE, callback),
            {"vin":self.vin, "data": {Signal.IDEAL_BATTERY_RANGE: None}}
        )

    def listen_InsideTemp(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Inside Temperature."""
        return self.stream.async_add_listener(
            make_float(Signal.INSIDE_TEMP, callback),
            {"vin":self.vin, "data": {Signal.INSIDE_TEMP: None}}
        )

    def listen_IsolationResistance(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Isolation Resistance."""
        return self.stream.async_add_listener(
            make_float(Signal.ISOLATION_RESISTANCE, callback),
            {"vin":self.vin, "data": {Signal.ISOLATION_RESISTANCE: None}}
        )

    def listen_LaneDepartureAvoidance(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Lane Departure Avoidance."""
        return self.stream.async_add_listener(
            lambda x: callback(LaneAssistLevel.get(x['data'][Signal.LANE_DEPARTURE_AVOIDANCE])),
            {"vin":self.vin, "data": {Signal.LANE_DEPARTURE_AVOIDANCE: None}}
        )

    def listen_LateralAcceleration(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Lateral Acceleration."""
        return self.stream.async_add_listener(
            make_float(Signal.LATERAL_ACCELERATION, callback),
            {"vin":self.vin, "data": {Signal.LATERAL_ACCELERATION: None}}
        )

    def listen_LifetimeEnergyUsed(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Lifetime Energy Used."""
        return self.stream.async_add_listener(
            make_float(Signal.LIFETIME_ENERGY_USED, callback),
            {"vin":self.vin, "data": {Signal.LIFETIME_ENERGY_USED: None}}
        )

    def listen_LifetimeEnergyUsedDrive(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Lifetime Energy Used Drive."""
        return self.stream.async_add_listener(
            make_float(Signal.LIFETIME_ENERGY_USED_DRIVE, callback),
            {"vin":self.vin, "data": {Signal.LIFETIME_ENERGY_USED_DRIVE: None}}
        )

    def listen_LocatedAtFavorite(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Located At Favorite."""
        return self.stream.async_add_listener(
            make_bool(Signal.LOCATED_AT_FAVORITE, callback),
            {"vin":self.vin, "data": {Signal.LOCATED_AT_FAVORITE: None}}
        )

    def listen_LocatedAtHome(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Located At Home."""
        return self.stream.async_add_listener(
            make_bool(Signal.LOCATED_AT_HOME, callback),
            {"vin":self.vin, "data": {Signal.LOCATED_AT_HOME: None}}
        )

    def listen_LocatedAtWork(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Located At Work."""
        return self.stream.async_add_listener(
            make_bool(Signal.LOCATED_AT_WORK, callback),
            {"vin":self.vin, "data": {Signal.LOCATED_AT_WORK: None}}
        )

    def listen_Location(self, callback: Callable[[TeslaLocation | None], None]) -> Callable[[],None]:
        """Listen for Location."""
        return self.stream.async_add_listener(
            make_location(Signal.LOCATION, callback),
            {"vin":self.vin, "data": {Signal.LOCATION: None}}
        )

    def listen_Locked(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Locked."""
        return self.stream.async_add_listener(
            make_bool(Signal.LOCKED, callback),
            {"vin":self.vin, "data": {Signal.LOCKED: None}}
        )

    def listen_LongitudinalAcceleration(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Longitudinal Acceleration."""
        return self.stream.async_add_listener(
            make_float(Signal.LONGITUDINAL_ACCELERATION, callback),
            {"vin":self.vin, "data": {Signal.LONGITUDINAL_ACCELERATION: None}}
        )

    def listen_MilesToArrival(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Miles to Arrival."""
        return self.stream.async_add_listener(
            make_float(Signal.MILES_TO_ARRIVAL, callback),
            {"vin":self.vin, "data": {Signal.MILES_TO_ARRIVAL: None}}
        )

    def listen_MinutesToArrival(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Minutes to Arrival."""
        return self.stream.async_add_listener(
            make_float(Signal.MINUTES_TO_ARRIVAL, callback),
            {"vin":self.vin, "data": {Signal.MINUTES_TO_ARRIVAL: None}}
        )

    def listen_ModuleTempMax(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Module Temperature Maximum."""
        return self.stream.async_add_listener(
            make_float(Signal.MODULE_TEMP_MAX, callback),
            {"vin":self.vin, "data": {Signal.MODULE_TEMP_MAX: None}}
        )

    def listen_ModuleTempMin(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Module Temperature Minimum."""
        return self.stream.async_add_listener(
            make_float(Signal.MODULE_TEMP_MIN, callback),
            {"vin":self.vin, "data": {Signal.MODULE_TEMP_MIN: None}}
        )

    def listen_NotEnoughPowerToHeat(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Not Enough Power to Heat."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.NOT_ENOUGH_POWER_TO_HEAT]),
            {"vin":self.vin, "data": {Signal.NOT_ENOUGH_POWER_TO_HEAT: None}}
        )

    def listen_NumBrickVoltageMax(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Number of Brick Voltage Maximum."""
        return self.stream.async_add_listener(
            make_int(Signal.NUM_BRICK_VOLTAGE_MAX, callback),
            {"vin":self.vin, "data": {Signal.NUM_BRICK_VOLTAGE_MAX: None}}
        )

    def listen_NumBrickVoltageMin(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Number of Brick Voltage Minimum."""
        return self.stream.async_add_listener(
            make_int(Signal.NUM_BRICK_VOLTAGE_MIN, callback),
            {"vin":self.vin, "data": {Signal.NUM_BRICK_VOLTAGE_MIN: None}}
        )

    def listen_NumModuleTempMax(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Number of Module Temperature Maximum."""
        return self.stream.async_add_listener(
            make_int(Signal.NUM_MODULE_TEMP_MAX, callback),
            {"vin":self.vin, "data": {Signal.NUM_MODULE_TEMP_MAX: None}}
        )

    def listen_NumModuleTempMin(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Number of Module Temperature Minimum."""
        return self.stream.async_add_listener(
            make_int(Signal.NUM_MODULE_TEMP_MIN, callback),
            {"vin":self.vin, "data": {Signal.NUM_MODULE_TEMP_MIN: None}}
        )

    def listen_Odometer(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Odometer."""
        return self.stream.async_add_listener(
            make_float(Signal.ODOMETER, callback),
            {"vin":self.vin, "data": {Signal.ODOMETER: None}}
        )

    def listen_OffroadLightbarPresent(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Offroad Lightbar Present."""
        return self.stream.async_add_listener(
            make_bool(Signal.OFFROAD_LIGHTBAR_PRESENT, callback),
            {"vin":self.vin, "data": {Signal.OFFROAD_LIGHTBAR_PRESENT: None}}
        )

    def listen_OriginLocation(self, callback: Callable[[TeslaLocation | None], None]) -> Callable[[],None]:
        """Listen for Origin Location."""
        return self.stream.async_add_listener(
            make_location(Signal.ORIGIN_LOCATION, callback),
            {"vin":self.vin, "data": {Signal.ORIGIN_LOCATION: None}}
        )

    def listen_OutsideTemp(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Outside Temperature."""
        return self.stream.async_add_listener(
            make_float(Signal.OUTSIDE_TEMP, callback),
            {"vin":self.vin, "data": {Signal.OUTSIDE_TEMP: None}}
        )

    def listen_PackCurrent(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Pack Current."""
        return self.stream.async_add_listener(
            make_float(Signal.PACK_CURRENT, callback),
            {"vin":self.vin, "data": {Signal.PACK_CURRENT: None}}
        )

    def listen_PackVoltage(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Pack Voltage."""
        return self.stream.async_add_listener(
            make_float(Signal.PACK_VOLTAGE, callback),
            {"vin":self.vin, "data": {Signal.PACK_VOLTAGE: None}}
        )

    def listen_PairedPhoneKeyAndKeyFobQty(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Paired Phone Key and Key Fob Quantity."""
        return self.stream.async_add_listener(
            make_int(Signal.PAIRED_PHONE_KEY_AND_KEY_FOB_QTY, callback),
            {"vin":self.vin, "data": {Signal.PAIRED_PHONE_KEY_AND_KEY_FOB_QTY: None}}
        )

    def listen_PassengerSeatBelt(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Passenger Seat Belt."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.PASSENGER_SEAT_BELT]),
            {"vin":self.vin, "data": {Signal.PASSENGER_SEAT_BELT: None}}
        )

    def listen_PedalPosition(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Pedal Position."""
        return self.stream.async_add_listener(
            make_float(Signal.PEDAL_POSITION, callback),
            {"vin":self.vin, "data": {Signal.PEDAL_POSITION: None}}
        )

    def listen_PinToDriveEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Pin to Drive Enabled."""
        return self.stream.async_add_listener(
            make_bool(Signal.PIN_TO_DRIVE_ENABLED, callback),
            {"vin":self.vin, "data": {Signal.PIN_TO_DRIVE_ENABLED: None}}
        )

    def listen_PowershareHoursLeft(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Powershare Hours Left."""
        return self.stream.async_add_listener(
            make_float(Signal.POWERSHARE_HOURS_LEFT, callback),
            {"vin":self.vin, "data": {Signal.POWERSHARE_HOURS_LEFT: None}}
        )

    def listen_PowershareInstantaneousPowerKW(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Powershare Instantaneous Power kW."""
        return self.stream.async_add_listener(
            make_float(Signal.POWERSHARE_INSTANTANEOUS_POWER_KW, callback),
            {"vin":self.vin, "data": {Signal.POWERSHARE_INSTANTANEOUS_POWER_KW: None}}
        )

    def listen_PowershareStatus(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Powershare Status."""
        return self.stream.async_add_listener(
            lambda x: callback(PowershareState.get(x['data'][Signal.POWERSHARE_STATUS])),
            {"vin":self.vin, "data": {Signal.POWERSHARE_STATUS: None}}
        )

    def listen_PowershareStopReason(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Powershare Stop Reason."""
        return self.stream.async_add_listener(
            lambda x: callback(PowershareStopReasonStatus.get(x['data'][Signal.POWERSHARE_STOP_REASON])),
            {"vin":self.vin, "data": {Signal.POWERSHARE_STOP_REASON: None}}
        )

    def listen_PowershareType(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Powershare Type."""
        return self.stream.async_add_listener(
            lambda x: callback(PowershareTypeStatus.get(x['data'][Signal.POWERSHARE_TYPE])),
            {"vin":self.vin, "data": {Signal.POWERSHARE_TYPE: None}}
        )

    def listen_PreconditioningEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Preconditioning Enabled."""
        return self.stream.async_add_listener(
            make_bool(Signal.PRECONDITIONING_ENABLED, callback),
            {"vin":self.vin, "data": {Signal.PRECONDITIONING_ENABLED: None}}
        )

    def listen_RatedRange(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Rated Range."""
        return self.stream.async_add_listener(
            make_float(Signal.RATED_RANGE, callback),
            {"vin":self.vin, "data": {Signal.RATED_RANGE: None}}
        )

    def listen_RearDriverWindow(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Rear Driver Window State."""
        return self.stream.async_add_listener(
            lambda x: callback(WindowState.get(x['data'][Signal.RD_WINDOW])),
            {"vin":self.vin, "data": {Signal.RD_WINDOW: None}}
        )

    def listen_RearDisplayHvacEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Rear Display HVAC Enabled."""
        return self.stream.async_add_listener(
            make_bool(Signal.REAR_DISPLAY_HVAC_ENABLED, callback),
            {"vin":self.vin, "data": {Signal.REAR_DISPLAY_HVAC_ENABLED: None}}
        )

    def listen_RearSeatHeaters(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Rear Seat Heaters."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.REAR_SEAT_HEATERS]),
            {"vin":self.vin, "data": {Signal.REAR_SEAT_HEATERS: None}}
        )

    def listen_RemoteStartEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Remote Start Enabled."""
        return self.stream.async_add_listener(
            make_bool(Signal.REMOTE_START_ENABLED, callback),
            {"vin":self.vin, "data": {Signal.REMOTE_START_ENABLED: None}}
        )

    def listen_RightHandDrive(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Right Hand Drive."""
        return self.stream.async_add_listener(
            make_bool(Signal.RIGHT_HAND_DRIVE, callback),
            {"vin":self.vin, "data": {Signal.RIGHT_HAND_DRIVE: None}}
        )

    def listen_RoofColor(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Roof Color."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.ROOF_COLOR]),
            {"vin":self.vin, "data": {Signal.ROOF_COLOR: None}}
        )

    def listen_RouteLastUpdated(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Route Last Updated."""
        return self.stream.async_add_listener(
            make_int(Signal.ROUTE_LAST_UPDATED, callback),
            {"vin":self.vin, "data": {Signal.ROUTE_LAST_UPDATED: None}}
        )

    def listen_RouteTrafficMinutesDelay(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Route Traffic Minutes Delay."""
        return self.stream.async_add_listener(
            make_int(Signal.ROUTE_TRAFFIC_MINUTES_DELAY, callback),
            {"vin":self.vin, "data": {Signal.ROUTE_TRAFFIC_MINUTES_DELAY: None}}
        )

    def listen_RearPassengerWindow(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Rear Passenger Window State."""
        return self.stream.async_add_listener(
            lambda x: callback(WindowState.get(x['data'][Signal.RP_WINDOW])),
            {"vin":self.vin, "data": {Signal.RP_WINDOW: None}}
        )

    def listen_ScheduledChargingMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Scheduled Charging Mode."""
        return self.stream.async_add_listener(
            lambda x: callback(ScheduledChargingMode.get(x['data'][Signal.SCHEDULED_CHARGING_MODE])),
            {"vin":self.vin, "data": {Signal.SCHEDULED_CHARGING_MODE: None}}
        )

    def listen_ScheduledChargingPending(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Scheduled Charging Pending."""
        return self.stream.async_add_listener(
            make_bool(Signal.SCHEDULED_CHARGING_PENDING, callback),
            {"vin":self.vin, "data": {Signal.SCHEDULED_CHARGING_PENDING: None}}
        )

    def listen_ScheduledChargingStartTime(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Scheduled Charging Start Time."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SCHEDULED_CHARGING_START_TIME]),
            {"vin":self.vin, "data": {Signal.SCHEDULED_CHARGING_START_TIME: None}}
        )

    def listen_ScheduledDepartureTime(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Scheduled Departure Time."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SCHEDULED_DEPARTURE_TIME]),
            {"vin":self.vin, "data": {Signal.SCHEDULED_DEPARTURE_TIME: None}}
        )

    def listen_SeatHeaterLeft(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Seat Heater Left."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SEAT_HEATER_LEFT]),
            {"vin":self.vin, "data": {Signal.SEAT_HEATER_LEFT: None}}
        )

    def listen_SeatHeaterRearCenter(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Seat Heater Rear Center."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SEAT_HEATER_REAR_CENTER]),
            {"vin":self.vin, "data": {Signal.SEAT_HEATER_REAR_CENTER: None}}
        )

    def listen_SeatHeaterRearLeft(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Seat Heater Rear Left."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SEAT_HEATER_REAR_LEFT]),
            {"vin":self.vin, "data": {Signal.SEAT_HEATER_REAR_LEFT: None}}
        )

    def listen_SeatHeaterRearRight(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Seat Heater Rear Right."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SEAT_HEATER_REAR_RIGHT]),
            {"vin":self.vin, "data": {Signal.SEAT_HEATER_REAR_RIGHT: None}}
        )

    def listen_SeatHeaterRight(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Seat Heater Right."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SEAT_HEATER_RIGHT]),
            {"vin":self.vin, "data": {Signal.SEAT_HEATER_RIGHT: None}}
        )

    def listen_SentryMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Sentry Mode."""
        return self.stream.async_add_listener(
            lambda x: callback(SentryModeState.get(x['data'][Signal.SENTRY_MODE])),
            {"vin":self.vin, "data": {Signal.SENTRY_MODE: None}}
        )

    def listen_ServiceMode(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Service Mode."""
        return self.stream.async_add_listener(
            make_bool(Signal.SERVICE_MODE, callback),
            {"vin":self.vin, "data": {Signal.SERVICE_MODE: None}}
        )

    def listen_Setting24HourTime(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for 24 Hour Time Setting."""
        return self.stream.async_add_listener(
            make_bool(Signal.SETTING_24_HOUR_TIME, callback),
            {"vin":self.vin, "data": {Signal.SETTING_24_HOUR_TIME: None}}
        )

    def listen_SettingChargeUnit(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Charge Unit Setting."""
        return self.stream.async_add_listener(
            lambda x: callback(ChargeUnitPreference.get(x['data'][Signal.SETTING_CHARGE_UNIT])),
            {"vin":self.vin, "data": {Signal.SETTING_CHARGE_UNIT: None}}
        )

    def listen_SettingDistanceUnit(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Distance Unit Setting."""
        return self.stream.async_add_listener(
            lambda x: callback(DistanceUnit.get(x['data'][Signal.SETTING_DISTANCE_UNIT])),
            {"vin":self.vin, "data": {Signal.SETTING_DISTANCE_UNIT: None}}
        )

    def listen_SettingTemperatureUnit(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Temperature Unit Setting."""
        return self.stream.async_add_listener(
            lambda x: callback(TemperatureUnit.get(x['data'][Signal.SETTING_TEMPERATURE_UNIT])),
            {"vin":self.vin, "data": {Signal.SETTING_TEMPERATURE_UNIT: None}}
        )

    def listen_SettingTirePressureUnit(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Tire Pressure Unit Setting."""
        return self.stream.async_add_listener(
            lambda x: callback(PressureUnit.get(x['data'][Signal.SETTING_TIRE_PRESSURE_UNIT])),
            {"vin":self.vin, "data": {Signal.SETTING_TIRE_PRESSURE_UNIT: None}}
        )

    def listen_Soc(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for State of Charge."""
        return self.stream.async_add_listener(
            make_float(Signal.SOC, callback),
            {"vin":self.vin, "data": {Signal.SOC: None}}
        )

    def listen_SoftwareUpdateDownloadPercentComplete(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Software Update Download Percent Complete."""
        return self.stream.async_add_listener(
            make_int(Signal.SOFTWARE_UPDATE_DOWNLOAD_PERCENT_COMPLETE, callback),
            {"vin":self.vin, "data": {Signal.SOFTWARE_UPDATE_DOWNLOAD_PERCENT_COMPLETE: None}}
        )

    def listen_SoftwareUpdateExpectedDurationMinutes(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Software Update Expected Duration Minutes."""
        return self.stream.async_add_listener(
            make_int(Signal.SOFTWARE_UPDATE_EXPECTED_DURATION_MINUTES, callback),
            {"vin":self.vin, "data": {Signal.SOFTWARE_UPDATE_EXPECTED_DURATION_MINUTES: None}}
        )

    def listen_SoftwareUpdateInstallationPercentComplete(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for Software Update Installation Percent Complete."""
        return self.stream.async_add_listener(
            make_int(Signal.SOFTWARE_UPDATE_INSTALLATION_PERCENT_COMPLETE, callback),
            {"vin":self.vin, "data": {Signal.SOFTWARE_UPDATE_INSTALLATION_PERCENT_COMPLETE: None}}
        )

    def listen_SoftwareUpdateScheduledStartTime(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Software Update Scheduled Start Time."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SOFTWARE_UPDATE_SCHEDULED_START_TIME]),
            {"vin":self.vin, "data": {Signal.SOFTWARE_UPDATE_SCHEDULED_START_TIME: None}}
        )

    def listen_SoftwareUpdateVersion(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Software Update Version."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SOFTWARE_UPDATE_VERSION]),
            {"vin":self.vin, "data": {Signal.SOFTWARE_UPDATE_VERSION: None}}
        )

    def listen_SpeedLimitMode(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Speed Limit Mode."""
        return self.stream.async_add_listener(
            make_bool(Signal.SPEED_LIMIT_MODE, callback),
            {"vin":self.vin, "data": {Signal.SPEED_LIMIT_MODE: None}}
        )

    def listen_SpeedLimitWarning(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Speed Limit Warning."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.SPEED_LIMIT_WARNING]),
            {"vin":self.vin, "data": {Signal.SPEED_LIMIT_WARNING: None}}
        )

    def listen_SuperchargerSessionTripPlanner(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Supercharger Session Trip Planner."""
        return self.stream.async_add_listener(
            make_bool(Signal.SUPERCHARGER_SESSION_TRIP_PLANNER, callback),
            {"vin":self.vin, "data": {Signal.SUPERCHARGER_SESSION_TRIP_PLANNER: None}}
        )

    def listen_TimeToFullCharge(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Time to Full Charge."""
        return self.stream.async_add_listener(
            make_float(Signal.TIME_TO_FULL_CHARGE, callback),
            {"vin":self.vin, "data": {Signal.TIME_TO_FULL_CHARGE: None}}
        )

    def listen_TonneauOpenPercent(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Tonneau Open Percent."""
        return self.stream.async_add_listener(
            make_float(Signal.TONNEAU_OPEN_PERCENT, callback),
            {"vin":self.vin, "data": {Signal.TONNEAU_OPEN_PERCENT: None}}
        )

    def listen_TonneauPosition(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Tonneau Position."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.TONNEAU_POSITION]),
            {"vin":self.vin, "data": {Signal.TONNEAU_POSITION: None}}
        )

    def listen_TonneauTentMode(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Tonneau Tent Mode."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.TONNEAU_TENT_MODE]),
            {"vin":self.vin, "data": {Signal.TONNEAU_TENT_MODE: None}}
        )

    def listen_TpmsHardWarnings(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for TPMS Hard Warnings."""
        return self.stream.async_add_listener(
            make_int(Signal.TPMS_HARD_WARNINGS, callback),
            {"vin":self.vin, "data": {Signal.TPMS_HARD_WARNINGS: None}}
        )

    def listen_TpmsLastSeenPressureTimeFl(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for TPMS Last Seen Pressure Time Front Left."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.TPMS_LAST_SEEN_PRESSURE_TIME_FL]),
            {"vin":self.vin, "data": {Signal.TPMS_LAST_SEEN_PRESSURE_TIME_FL: None}}
        )

    def listen_TpmsLastSeenPressureTimeFr(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for TPMS Last Seen Pressure Time Front Right."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.TPMS_LAST_SEEN_PRESSURE_TIME_FR]),
            {"vin":self.vin, "data": {Signal.TPMS_LAST_SEEN_PRESSURE_TIME_FR: None}}
        )

    def listen_TpmsLastSeenPressureTimeRl(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for TPMS Last Seen Pressure Time Rear Left."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.TPMS_LAST_SEEN_PRESSURE_TIME_RL]),
            {"vin":self.vin, "data": {Signal.TPMS_LAST_SEEN_PRESSURE_TIME_RL: None}}
        )

    def listen_TpmsLastSeenPressureTimeRr(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for TPMS Last Seen Pressure Time Rear Right."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.TPMS_LAST_SEEN_PRESSURE_TIME_RR]),
            {"vin":self.vin, "data": {Signal.TPMS_LAST_SEEN_PRESSURE_TIME_RR: None}}
        )

    def listen_TpmsPressureFl(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for TPMS Pressure Front Left."""
        return self.stream.async_add_listener(
            make_float(Signal.TPMS_PRESSURE_FL, callback),
            {"vin":self.vin, "data": {Signal.TPMS_PRESSURE_FL: None}}
        )

    def listen_TpmsPressureFr(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for TPMS Pressure Front Right."""
        return self.stream.async_add_listener(
            make_float(Signal.TPMS_PRESSURE_FR, callback),
            {"vin":self.vin, "data": {Signal.TPMS_PRESSURE_FR: None}}
        )

    def listen_TpmsPressureRl(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for TPMS Pressure Rear Left."""
        return self.stream.async_add_listener(
            make_float(Signal.TPMS_PRESSURE_RL, callback),
            {"vin":self.vin, "data": {Signal.TPMS_PRESSURE_RL: None}}
        )

    def listen_TpmsPressureRr(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for TPMS Pressure Rear Right."""
        return self.stream.async_add_listener(
            make_float(Signal.TPMS_PRESSURE_RR, callback),
            {"vin":self.vin, "data": {Signal.TPMS_PRESSURE_RR: None}}
        )

    def listen_TpmsSoftWarnings(self, callback: Callable[[int | None], None]) -> Callable[[],None]:
        """Listen for TPMS Soft Warnings."""
        return self.stream.async_add_listener(
            make_int(Signal.TPMS_SOFT_WARNINGS, callback),
            {"vin":self.vin, "data": {Signal.TPMS_SOFT_WARNINGS: None}}
        )

    def listen_Trim(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Trim."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.TRIM]),
            {"vin":self.vin, "data": {Signal.TRIM: None}}
        )

    def listen_ValetModeEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Valet Mode Enabled."""
        return self.stream.async_add_listener(
            make_bool(Signal.VALET_MODE_ENABLED, callback),
            {"vin":self.vin, "data": {Signal.VALET_MODE_ENABLED: None}}
        )

    def listen_VehicleName(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Vehicle Name."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.VEHICLE_NAME]),
            {"vin":self.vin, "data": {Signal.VEHICLE_NAME: None}}
        )

    def listen_VehicleSpeed(self, callback: Callable[[float | None], None]) -> Callable[[],None]:
        """Listen for Vehicle Speed."""
        return self.stream.async_add_listener(
            make_float(Signal.VEHICLE_SPEED, callback),
            {"vin":self.vin, "data": {Signal.VEHICLE_SPEED: None}}
        )

    def listen_Version(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Version."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.VERSION]),
            {"vin":self.vin, "data": {Signal.VERSION: None}}
        )

    def listen_WheelType(self, callback: Callable[[str | None], None]) -> Callable[[],None]:
        """Listen for Wheel Type."""
        return self.stream.async_add_listener(
            lambda x: callback(x['data'][Signal.WHEEL_TYPE]),
            {"vin":self.vin, "data": {Signal.WHEEL_TYPE: None}}
        )

    def listen_WiperHeatEnabled(self, callback: Callable[[bool | None], None]) -> Callable[[],None]:
        """Listen for Wiper Heat Enabled."""
        return self.stream.async_add_listener(
            make_bool(Signal.WIPER_HEAT_ENABLED, callback),
            {"vin":self.vin, "data": {Signal.WIPER_HEAT_ENABLED: None}}
        )


def make_int(signal: Signal, callback: Callable[[int | None], None]) -> Callable[[dict], None]:
    """Listener factory"""
    def typer(event: dict):
        data = event["data"][signal]
        if isinstance(data, str):
            #Handle invalid and None?
            data = int(data)
        callback(data)
    return typer

def make_float(signal: Signal, callback: Callable[[float | None], None]) -> Callable[[dict], None]:
    """Listener factory"""
    def typer(event: dict):
        data = event["data"][signal]
        if isinstance(data, str):
            #Handle invalid and None?
            data = float(data)
        callback(data)
    return typer

def make_bool(signal: Signal, callback: Callable[[bool | None], None]) -> Callable[[dict], None]:
    """Listener factory"""
    def typer(event: dict):
        data = event["data"][signal]
        if isinstance(data, str):
            #Handle invalid and None?
            data = data == "true"
        callback(data)
    return typer

def make_dict(signal: Signal, callback: Callable[[dict | None], None]) -> Callable[[dict], None]:
    """Listener factory"""
    def typer(event: dict):
        data = event["data"][signal]
        if not isinstance(data, dict):
            data = None
        callback(data)
    return typer

def make_location(signal: Signal, callback: Callable[[TeslaLocation | None], None]) -> Callable[[dict], None]:
    """Listener factory"""
    def typer(event: dict):
        data = event["data"][signal]
        if isinstance(data, dict) and "longitude" in data and "latitude" in data:
            callback(TeslaLocation(latitude=data["latitude"], longitude=data["longitude"]))
        else:
            callback(None)
    return typer

def merge(source, destination):
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            merge(value, node)
        else:
            destination[key] = value

    return destination
