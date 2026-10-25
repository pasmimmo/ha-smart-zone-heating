"""Coordinator for Smart Zone Heating (Step 1: Base Multi-Zone + Heater)."""
from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_HEATER_ENTITY,
    CONF_SYSTEM_NAME,
    CONF_TARGET_TEMP,
    CONF_TEMP_SENSOR,
    CONF_VALVE_ENTITY,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_HYSTERESIS,
    DEFAULT_TARGET_TEMP,
    DOMAIN,
    STATE_DISABLED,
    STATE_HEATING,
    STATE_IDLE,
)

_LOGGER = logging.getLogger(__name__)


class ZoneRuntimeState:
    """Holds runtime state for a single heating zone."""

    def __init__(self, zone_cfg: dict[str, Any]) -> None:
        self.zone_id: str = zone_cfg[CONF_ZONE_ID]
        self.name: str = zone_cfg[CONF_ZONE_NAME]
        self.valve_entity: str = zone_cfg[CONF_VALVE_ENTITY]
        self.temp_sensor: str = zone_cfg[CONF_TEMP_SENSOR]
        self.target_temp: float = float(zone_cfg.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP))
        self.hvac_mode_enabled: bool = True
        self.current_temp: float | None = None
        self.requesting_heat: bool = False


class SmartZoneHeatingCoordinator:
    """Manages the logic for multi-zone valves and the main heater."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        data = {**entry.data, **entry.options}

        self.system_name: str = data.get(CONF_SYSTEM_NAME, "Riscaldamento")
        self.heater_entity: str = data[CONF_HEATER_ENTITY]
        self.master_enabled: bool = True
        self.hysteresis: float = DEFAULT_HYSTERESIS
        self.system_state: str = STATE_IDLE

        self.zones: dict[str, ZoneRuntimeState] = {}
        for z_cfg in data.get(CONF_ZONES, []):
            z = ZoneRuntimeState(z_cfg)
            self.zones[z.zone_id] = z

        self._listeners: list[Callable[[], None]] = []
        self._unsub_state_listener: Callable[[], None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return DeviceInfo so all entities are grouped under a single Device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.system_name,
            manufacturer="Smart Zone Heating",
            model="Multi-Zone Heating Controller (Step 1)",
            sw_version="0.1.0",
        )

    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register an entity callback to be notified on updates."""
        self._listeners.append(update_callback)

        def _remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _remove

    @callback
    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def async_start(self) -> None:
        """Start tracking entities and evaluate initial state."""
        self._resubscribe_listeners()
        for zone in self.zones.values():
            self._read_zone_temp(zone)
        await self.async_evaluate()

    @callback
    def _resubscribe_listeners(self) -> None:
        """Subscribe to state changes of configured temperature sensors and switches."""
        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None

        tracked_entities: set[str] = {self.heater_entity}
        for zone in self.zones.values():
            tracked_entities.add(zone.valve_entity)
            if zone.temp_sensor:
                tracked_entities.add(zone.temp_sensor)

        self._unsub_state_listener = async_track_state_change_event(
            self.hass,
            list(tracked_entities),
            self._async_on_state_change,
        )

    async def async_stop(self) -> None:
        """Clean up listeners on unload."""
        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None

    def _read_zone_temp(self, zone: ZoneRuntimeState) -> None:
        """Read current temperature from the zone's active temperature sensor."""
        state = self.hass.states.get(zone.temp_sensor)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            zone.current_temp = None
            return
        try:
            zone.current_temp = float(state.state)
        except (ValueError, TypeError):
            zone.current_temp = None

    @callback
    def _async_on_state_change(self, event: Event) -> None:
        """Handle state changes of tracked sensors or switches."""
        for zone in self.zones.values():
            self._read_zone_temp(zone)
        self.hass.async_create_task(self.async_evaluate())

    async def async_set_zone_temp_sensor(self, zone_id: str, sensor_entity_id: str) -> None:
        """Change the active temperature sensor for a zone on the fly."""
        zone = self.zones.get(zone_id)
        if not zone:
            return
        zone.temp_sensor = sensor_entity_id
        self._resubscribe_listeners()
        self._read_zone_temp(zone)
        await self.async_evaluate()

    async def async_evaluate(self) -> None:
        """Evaluate all zones and control zone valves + main heater switch."""
        any_heating = False

        for zone in self.zones.values():
            self._read_zone_temp(zone)

            if not self.master_enabled or not zone.hvac_mode_enabled:
                zone.requesting_heat = False
            elif zone.current_temp is None:
                # Safety: if sensor is unavailable, stop requesting heat for that zone
                zone.requesting_heat = False
            else:
                if zone.requesting_heat:
                    # Keep heating until target + hysteresis is reached
                    if zone.current_temp >= zone.target_temp + self.hysteresis:
                        zone.requesting_heat = False
                else:
                    # Start heating when temp drops to or below target - hysteresis
                    if zone.current_temp <= zone.target_temp - self.hysteresis:
                        zone.requesting_heat = True

            if zone.requesting_heat:
                any_heating = True

            # Control the zone valve switch
            await self._async_set_switch(zone.valve_entity, zone.requesting_heat)

        # Control main heater switch
        await self._async_set_switch(self.heater_entity, any_heating)

        if not self.master_enabled:
            self.system_state = STATE_DISABLED
        elif any_heating:
            self.system_state = STATE_HEATING
        else:
            self.system_state = STATE_IDLE

        self._notify_listeners()

    async def _async_set_switch(self, entity_id: str, turn_on: bool) -> None:
        """Turn a switch or input_boolean on/off only if its current state differs."""
        state_obj = self.hass.states.get(entity_id)
        if state_obj is None:
            return
        is_currently_on = state_obj.state == STATE_ON
        if is_currently_on == turn_on:
            return

        domain = entity_id.split(".")[0]
        if domain not in ("switch", "input_boolean", "homeassistant"):
            domain = "homeassistant"
        service = SERVICE_TURN_ON if turn_on else SERVICE_TURN_OFF
        await self.hass.services.async_call(
            domain,
            service,
            {ATTR_ENTITY_ID: entity_id},
            blocking=False,
        )
