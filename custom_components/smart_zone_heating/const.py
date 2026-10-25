"""Constants for Smart Zone Heating integration."""

DOMAIN = "smart_zone_heating"

CONF_SYSTEM_NAME = "system_name"
CONF_HEATER_ENTITY = "heater_entity"
CONF_ZONE_COUNT = "zone_count"
CONF_ZONES = "zones"

CONF_ZONE_ID = "zone_id"
CONF_ZONE_NAME = "zone_name"
CONF_VALVE_ENTITY = "valve_entity"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_TARGET_TEMP = "target_temp"

DEFAULT_HYSTERESIS = 0.3
DEFAULT_TARGET_TEMP = 20.0

STATE_IDLE = "Inattivo"
STATE_HEATING = "Riscaldamento in corso"
STATE_DISABLED = "Impianto disabilitato"
