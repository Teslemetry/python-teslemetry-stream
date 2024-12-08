from enum import Enum


class IntEnum(int, Enum):
    """Integer Enum"""


class StrEnum(str, Enum):
    """String Enum"""


class Signal(StrEnum):
    """Signals available in Fleet Telemetry streams"""

    AC_CHARGING_ENERGY_IN = "ACChargingEnergyIn"
    AC_CHARGING_POWER = "ACChargingPower"
    AUTO_SEAT_CLIMATE_LEFT = "AutoSeatClimateLeft"
    AUTO_SEAT_CLIMATE_RIGHT = "AutoSeatClimateRight"
    AUTOMATIC_BLIND_SPOT_CAMERA = "AutomaticBlindSpotCamera"
    AUTOMATIC_EMERGENCY_BRAKING_OFF = "AutomaticEmergencyBrakingOff"
    BATTERY_HEATER_ON = "BatteryHeaterOn"
    BATTERY_LEVEL = "BatteryLevel"
    BLIND_SPOT_COLLISION_WARNING_CHIME = "BlindSpotCollisionWarningChime"
    BMS_FULL_CHARGE_COMPLETE = "BmsFullchargecomplete"
    BMS_STATE = "BMSState"
    BRAKE_PEDAL = "BrakePedal"
    BRAKE_PEDAL_POS = "BrakePedalPos"
    BRICK_VOLTAGE_MAX = "BrickVoltageMax"
    BRICK_VOLTAGE_MIN = "BrickVoltageMin"
    CABIN_OVERHEAT_PROTECTION_MODE = "CabinOverheatProtectionMode"
    CABIN_OVERHEAT_PROTECTION_TEMPERATURE_LIMIT = "CabinOverheatProtectionTemperatureLimit"
    CAR_TYPE = "CarType"
    CENTER_DISPLAY = "CenterDisplay"
    CHARGE_AMPS = "ChargeAmps"
    CHARGE_CURRENT_REQUEST = "ChargeCurrentRequest"
    CHARGE_CURRENT_REQUEST_MAX = "ChargeCurrentRequestMax"
    CHARGE_ENABLE_REQUEST = "ChargeEnableRequest"
    CHARGE_LIMIT_SOC = "ChargeLimitSoc"
    CHARGE_PORT = "ChargePort"
    CHARGE_PORT_COLD_WEATHER_MODE = "ChargePortColdWeatherMode"
    CHARGE_PORT_DOOR_OPEN = "ChargePortDoorOpen"
    CHARGE_PORT_LATCH = "ChargePortLatch"
    CHARGE_STATE = "ChargeState"
    CHARGER_PHASES = "ChargerPhases"
    CHARGING_CABLE_TYPE = "ChargingCableType"
    CLIMATE_KEEPER_MODE = "ClimateKeeperMode"
    CRUISE_FOLLOW_DISTANCE = "CruiseFollowDistance"
    CRUISE_SET_SPEED = "CruiseSetSpeed"
    CRUISE_STATE = "CruiseState"
    CURRENT_LIMIT_MPH = "CurrentLimitMph"
    DC_CHARGING_ENERGY_IN = "DCChargingEnergyIn"
    DC_CHARGING_POWER = "DCChargingPower"
    DC_DC_ENABLE = "DCDCEnable"
    DEFROST_FOR_PRECONDITIONING = "DefrostForPreconditioning"
    DEFROST_MODE = "DefrostMode"
    DESTINATION_LOCATION = "DestinationLocation"
    DETAILED_CHARGE_STATE = "DetailedChargeState"
    DI_AXLE_SPEED_F = "DiAxleSpeedF"
    DI_AXLE_SPEED_R = "DiAxleSpeedR"
    DI_AXLE_SPEED_REL = "DiAxleSpeedREL"
    DI_AXLE_SPEED_RER = "DiAxleSpeedRER"
    DI_HEATSINK_TF = "DiHeatsinkTF"
    DI_HEATSINK_TR = "DiHeatsinkTR"
    DI_HEATSINK_TREL = "DiHeatsinkTREL"
    DI_HEATSINK_TRER = "DiHeatsinkTRER"
    DI_MOTOR_CURRENT_F = "DiMotorCurrentF"
    DI_MOTOR_CURRENT_R = "DiMotorCurrentR"
    DI_MOTOR_CURRENT_REL = "DiMotorCurrentREL"
    DI_MOTOR_CURRENT_RER = "DiMotorCurrentRER"
    DI_SLAVE_TORQUE_CMD = "DiSlaveTorqueCmd"
    DI_STATE_F = "DiStateF"
    DI_STATE_R = "DiStateR"
    DI_STATE_REL = "DiStateREL"
    DI_STATE_RER = "DiStateRER"
    DI_STATOR_TEMP_F = "DiStatorTempF"
    DI_STATOR_TEMP_R = "DiStatorTempR"
    DI_STATOR_TEMP_REL = "DiStatorTempREL"
    DI_STATOR_TEMP_RER = "DiStatorTempRER"
    DI_TORQUE_ACTUAL_F = "DiTorqueActualF"
    DI_TORQUE_ACTUAL_R = "DiTorqueActualR"
    DI_TORQUE_ACTUAL_REL = "DiTorqueActualREL"
    DI_TORQUE_ACTUAL_RER = "DiTorqueActualRER"
    DI_TORQUEMOTOR = "DiTorquemotor"
    DI_V_BAT_F = "DiVBatF"
    DI_V_BAT_R = "DiVBatR"
    DI_V_BAT_REL = "DiVBatREL"
    DI_V_BAT_RER = "DiVBatRER"
    DOOR_STATE = "DoorState"
    DRIVE_RAIL = "DriveRail"
    DRIVER_SEAT_BELT = "DriverSeatBelt"
    DRIVER_SEAT_OCCUPIED = "DriverSeatOccupied"
    EFFICIENCY_PACKAGE = "EfficiencyPackage"
    EMERGENCY_LANE_DEPARTURE_AVOIDANCE = "EmergencyLaneDepartureAvoidance"
    ENERGY_REMAINING = "EnergyRemaining"
    EST_BATTERY_RANGE = "EstBatteryRange"
    ESTIMATED_HOURS_TO_CHARGE_TERMINATION = "EstimatedHoursToChargeTermination"
    EUROPE_VEHICLE = "EuropeVehicle"
    EXPECTED_ENERGY_PERCENT_AT_TRIP_ARRIVAL = "ExpectedEnergyPercentAtTripArrival"
    EXPERIMENTAL_1 = "Experimental_1"
    EXPERIMENTAL_2 = "Experimental_2"
    EXPERIMENTAL_3 = "Experimental_3"
    EXPERIMENTAL_4 = "Experimental_4"
    EXTERIOR_COLOR = "ExteriorColor"
    FAST_CHARGER_PRESENT = "FastChargerPresent"
    FAST_CHARGER_TYPE = "FastChargerType"
    FD_WINDOW = "FdWindow"
    FORWARD_COLLISION_WARNING = "ForwardCollisionWarning"
    FP_WINDOW = "FpWindow"
    GEAR = "Gear"
    GPS_HEADING = "GpsHeading"
    GPS_STATE = "GpsState"
    GUEST_MODE_ENABLED = "GuestModeEnabled"
    GUEST_MODE_MOBILE_ACCESS_STATE = "GuestModeMobileAccessState"
    HOMELINK_DEVICE_COUNT = "HomelinkDeviceCount"
    HOMELINK_NEARBY = "HomelinkNearby"
    HVAC_AC_ENABLED = "HvacACEnabled"
    HVAC_AUTO_MODE = "HvacAutoMode"
    HVAC_FAN_SPEED = "HvacFanSpeed"
    HVAC_FAN_STATUS = "HvacFanStatus"
    HVAC_LEFT_TEMPERATURE_REQUEST = "HvacLeftTemperatureRequest"
    HVAC_POWER = "HvacPower"
    HVAC_RIGHT_TEMPERATURE_REQUEST = "HvacRightTemperatureRequest"
    HVAC_STEERING_WHEEL_HEAT_AUTO = "HvacSteeringWheelHeatAuto"
    HVAC_STEERING_WHEEL_HEAT_LEVEL = "HvacSteeringWheelHeatLevel"
    HVIL = "Hvil"
    IDEAL_BATTERY_RANGE = "IdealBatteryRange"
    INSIDE_TEMP = "InsideTemp"
    ISOLATION_RESISTANCE = "IsolationResistance"
    LANE_DEPARTURE_AVOIDANCE = "LaneDepartureAvoidance"
    LATERAL_ACCELERATION = "LateralAcceleration"
    LIFETIME_ENERGY_GAINED_REGEN = "LifetimeEnergyGainedRegen"
    LIFETIME_ENERGY_USED = "LifetimeEnergyUsed"
    LIFETIME_ENERGY_USED_DRIVE = "LifetimeEnergyUsedDrive"
    LOCATION = "Location"
    LOCKED = "Locked"
    LONGITUDINAL_ACCELERATION = "LongitudinalAcceleration"
    MILES_TO_ARRIVAL = "MilesToArrival"
    MINUTES_TO_ARRIVAL = "MinutesToArrival"
    MODULE_TEMP_MAX = "ModuleTempMax"
    MODULE_TEMP_MIN = "ModuleTempMin"
    NOT_ENOUGH_POWER_TO_HEAT = "NotEnoughPowerToHeat"
    NUM_BRICK_VOLTAGE_MAX = "NumBrickVoltageMax"
    NUM_BRICK_VOLTAGE_MIN = "NumBrickVoltageMin"
    NUM_MODULE_TEMP_MAX = "NumModuleTempMax"
    NUM_MODULE_TEMP_MIN = "NumModuleTempMin"
    ODOMETER = "Odometer"
    OFFROAD_LIGHTBAR_PRESENT = "OffroadLightbarPresent"
    ORIGIN_LOCATION = "OriginLocation"
    OUTSIDE_TEMP = "OutsideTemp"
    PACK_CURRENT = "PackCurrent"
    PACK_VOLTAGE = "PackVoltage"
    PAIRED_PHONE_KEY_AND_KEY_FOB_QTY = "PairedPhoneKeyAndKeyFobQty"
    PASSENGER_SEAT_BELT = "PassengerSeatBelt"
    PEDAL_POSITION = "PedalPosition"
    PIN_TO_DRIVE_ENABLED = "PinToDriveEnabled"
    POWERSHARE_HOURS_LEFT = "PowershareHoursLeft"
    POWERSHARE_INSTANTANEOUS_POWER_KW = "PowershareInstantaneousPowerKW"
    POWERSHARE_STATUS = "PowershareStatus"
    POWERSHARE_STOP_REASON = "PowershareStopReason"
    POWERSHARE_TYPE = "PowershareType"
    PRECONDITIONING_ENABLED = "PreconditioningEnabled"
    RATED_RANGE = "RatedRange"
    RD_WINDOW = "RdWindow"
    REAR_DISPLAY_HVAC_ENABLED = "RearDisplayHvacEnabled"
    REAR_SEAT_HEATERS = "RearSeatHeaters"
    REMOTE_START_ENABLED = "RemoteStartEnabled"
    RIGHT_HAND_DRIVE = "RightHandDrive"
    ROOF_COLOR = "RoofColor"
    ROUTE_LAST_UPDATED = "RouteLastUpdated"
    ROUTE_LINE = "RouteLine"
    ROUTE_TRAFFIC_MINUTES_DELAY = "RouteTrafficMinutesDelay"
    RP_WINDOW = "RpWindow"
    SCHEDULED_CHARGING_MODE = "ScheduledChargingMode"
    SCHEDULED_CHARGING_PENDING = "ScheduledChargingPending"
    SCHEDULED_CHARGING_START_TIME = "ScheduledChargingStartTime"
    SCHEDULED_DEPARTURE_TIME = "ScheduledDepartureTime"
    SEAT_HEATER_LEFT = "SeatHeaterLeft"
    SEAT_HEATER_REAR_CENTER = "SeatHeaterRearCenter"
    SEAT_HEATER_REAR_LEFT = "SeatHeaterRearLeft"
    SEAT_HEATER_REAR_RIGHT = "SeatHeaterRearRight"
    SEAT_HEATER_RIGHT = "SeatHeaterRight"
    SENTRY_MODE = "SentryMode"
    SERVICE_MODE = "ServiceMode"
    SOC = "Soc"
    SOFTWARE_UPDATE_DOWNLOAD_PERCENT_COMPLETE = "SoftwareUpdateDownloadPercentComplete"
    SOFTWARE_UPDATE_EXPECTED_DURATION_MINUTES = "SoftwareUpdateExpectedDurationMinutes"
    SOFTWARE_UPDATE_INSTALLATION_PERCENT_COMPLETE = "SoftwareUpdateInstallationPercentComplete"
    SOFTWARE_UPDATE_SCHEDULED_START_TIME = "SoftwareUpdateScheduledStartTime"
    SOFTWARE_UPDATE_VERSION = "SoftwareUpdateVersion"
    SPEED_LIMIT_MODE = "SpeedLimitMode"
    SPEED_LIMIT_WARNING = "SpeedLimitWarning"
    SUPERCHARGER_SESSION_TRIP_PLANNER = "SuperchargerSessionTripPlanner"
    TIME_TO_FULL_CHARGE = "TimeToFullCharge"
    TONNEAU_OPEN_PERCENT = "TonneauOpenPercent"
    TONNEAU_POSITION = "TonneauPosition"
    TONNEAU_TENT_MODE = "TonneauTentMode"
    TPMS_HARD_WARNINGS = "TpmsHardWarnings"
    TPMS_LAST_SEEN_PRESSURE_TIME_FL = "TpmsLastSeenPressureTimeFl"
    TPMS_LAST_SEEN_PRESSURE_TIME_FR = "TpmsLastSeenPressureTimeFr"
    TPMS_LAST_SEEN_PRESSURE_TIME_RL = "TpmsLastSeenPressureTimeRl"
    TPMS_LAST_SEEN_PRESSURE_TIME_RR = "TpmsLastSeenPressureTimeRr"
    TPMS_PRESSURE_FL = "TpmsPressureFl"
    TPMS_PRESSURE_FR = "TpmsPressureFr"
    TPMS_PRESSURE_RL = "TpmsPressureRl"
    TPMS_PRESSURE_RR = "TpmsPressureRr"
    TPMS_SOFT_WARNINGS = "TpmsSoftWarnings"
    TRIM = "Trim"
    VALET_MODE_ENABLED = "ValetModeEnabled"
    VEHICLE_NAME = "VehicleName"
    VEHICLE_SPEED = "VehicleSpeed"
    VERSION = "Version"
    WHEEL_TYPE = "WheelType"
    WIPER_HEAT_ENABLED = "WiperHeatEnabled"


class Alert(StrEnum):
    """Alerts available in Fleet Telemetry streams"""

    CUSTOMER = "Customer"
    SERVICE = "Service"
    SERVICE_FIX = "ServiceFix"
