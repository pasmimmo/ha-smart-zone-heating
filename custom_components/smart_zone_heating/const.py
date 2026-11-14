"""Constants for Smart Zone Heating integration."""
from __future__ import annotations

from enum import StrEnum

DOMAIN = "smart_zone_heating"

CONF_SYSTEM_NAME = "system_name"
CONF_HEATER_ENTITY = "heater_entity"
CONF_MASTER_ENABLED = "master_enabled"
CONF_EXCLUSIVE_CONTROL = "exclusive_control"
CONF_ZONE_COUNT = "zone_count"
CONF_ZONES = "zones"

CONF_ZONE_ID = "zone_id"
CONF_ZONE_NAME = "zone_name"
CONF_VALVE_ENTITY = "valve_entity"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_TARGET_TEMP = "target_temp"
CONF_TEMP_DAY = "temp_day"
CONF_TEMP_NIGHT = "temp_night"
CONF_TEMP_AWAY = "temp_away"

# Schedule settings (Day / Night hours)
CONF_SCHEDULE_ENABLED = "schedule_enabled"
CONF_DAY_START_TIME = "day_start_time"
CONF_NIGHT_START_TIME = "night_start_time"

# Cooldown / Heat dissipation settings
CONF_COOLDOWN_ENABLED = "cooldown_enabled"
CONF_COOLDOWN_MINUTES = "cooldown_minutes"
CONF_COOLDOWN_ZONE_ID = "cooldown_zone_id"
CONF_USE_POWER_SENSOR = "use_power_sensor"

# Generator lifecycle estimation (Watt) & Manual ignition settings
CONF_POWER_SENSOR = "power_sensor"
CONF_POWER_THRESHOLD_WATT = "power_threshold_watt"
CONF_POWER_GRACE_SECONDS = "power_grace_seconds"
CONF_MANUAL_SAFETY_ENABLED = "manual_safety_enabled"
CONF_USE_SEPARATE_MANUAL_ZONE = "use_separate_manual_zone"
CONF_MANUAL_SAFETY_ZONE_ID = "manual_safety_zone_id"

# Notification settings
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_LEVEL = "notify_level"

NOTIFY_LEVEL_OFF = "off"
NOTIFY_LEVEL_ERROR = "error"
NOTIFY_LEVEL_WARNING = "warning"
NOTIFY_LEVEL_DEBUG = "debug"
NOTIFY_LEVELS = [
    NOTIFY_LEVEL_OFF,
    NOTIFY_LEVEL_ERROR,
    NOTIFY_LEVEL_WARNING,
    NOTIFY_LEVEL_DEBUG,
]

# Preset modes for thermostats
PRESET_DAY = "day"
PRESET_NIGHT = "night"
PRESET_AWAY = "away"

DEFAULT_HYSTERESIS = 0.3
DEFAULT_TEMP_DAY = 20.5
DEFAULT_TEMP_NIGHT = 18.0
DEFAULT_TEMP_AWAY = 16.0
DEFAULT_DAY_START_TIME = "07:00:00"
DEFAULT_NIGHT_START_TIME = "22:00:00"

DEFAULT_COOLDOWN_MINUTES = 60
DEFAULT_POWER_THRESHOLD_WATT = 10.0
DEFAULT_POWER_GRACE_SECONDS = 15
DEFAULT_NOTIFY_LEVEL = NOTIFY_LEVEL_WARNING

STATE_IDLE = "Inattivo"
STATE_DISABLED = "Impianto disabilitato"


class GeneratorPhase(StrEnum):
    """Estimated lifecycle phase of the heat generator."""

    OFF = "off"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING_COOLDOWN = "stopping_cooldown"
    MANUAL_OVERRIDE = "manual_override"


GENERATOR_PHASE_LABELS: dict[GeneratorPhase, str] = {
    GeneratorPhase.OFF: "Spento",
    GeneratorPhase.STARTING: "In avvio",
    GeneratorPhase.RUNNING: "In funzione",
    GeneratorPhase.STOPPING_COOLDOWN: "Smaltimento calore",
    GeneratorPhase.MANUAL_OVERRIDE: "Acceso manualmente",
}
