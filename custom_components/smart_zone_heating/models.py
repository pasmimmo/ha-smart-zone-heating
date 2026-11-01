"""Data models and formatting helpers for Smart Zone Heating."""
from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant.util import dt as dt_util

from .const import (
    CONF_TARGET_TEMP,
    CONF_TEMP_AWAY,
    CONF_TEMP_DAY,
    CONF_TEMP_NIGHT,
    CONF_TEMP_SENSOR,
    CONF_VALVE_ENTITY,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    DEFAULT_TEMP_AWAY,
    DEFAULT_TEMP_DAY,
    DEFAULT_TEMP_NIGHT,
    PRESET_AWAY,
    PRESET_DAY,
    PRESET_NIGHT,
)

LOGBOOK_NAME = "SZH Integration"
NOTIFY_PREFIX = "[SZH Integration]"
CONF_HYSTERESIS = "hysteresis"


def parse_time(val: str | time | None, default_str: str) -> time:
    """Parse a time string HH:MM or HH:MM:SS into a datetime.time object."""
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        parsed = dt_util.parse_time(val)
        if parsed is not None:
            return parsed
    return dt_util.parse_time(default_str) or time(7, 0)


def fmt_temp(val: float | None) -> str:
    """Format temperature cleanly (e.g. 18.5 or 22)."""
    if val is None:
        return "?"
    return f"{val:g}"


class ZoneRuntimeState:
    """Holds runtime state for a single heating zone."""

    def __init__(self, zone_cfg: dict[str, Any], initial_enabled: bool = True) -> None:
        self.zone_id: str = zone_cfg[CONF_ZONE_ID]
        self.name: str = zone_cfg[CONF_ZONE_NAME]
        self.valve_entity: str = zone_cfg[CONF_VALVE_ENTITY]
        self.temp_sensor: str = zone_cfg[CONF_TEMP_SENSOR]
        self.temp_day: float = float(
            zone_cfg.get(CONF_TEMP_DAY, zone_cfg.get(CONF_TARGET_TEMP, DEFAULT_TEMP_DAY))
        )
        self.temp_night: float = float(zone_cfg.get(CONF_TEMP_NIGHT, DEFAULT_TEMP_NIGHT))
        self.temp_away: float = float(zone_cfg.get(CONF_TEMP_AWAY, DEFAULT_TEMP_AWAY))
        self.preset_mode: str = PRESET_DAY
        self.target_temp: float = self.temp_day
        self.hvac_mode_enabled: bool = initial_enabled
        self.current_temp: float | None = None
        self.requesting_heat: bool = False
        self.forced_open_reason: str | None = None
        self.climate_entity_id: str | None = None

    def apply_preset(self, preset: str) -> None:
        """Apply preset mode and update target_temp accordingly."""
        self.preset_mode = preset
        if preset == PRESET_DAY:
            self.target_temp = self.temp_day
        elif preset == PRESET_NIGHT:
            self.target_temp = self.temp_night
        elif preset == PRESET_AWAY:
            self.target_temp = self.temp_away
