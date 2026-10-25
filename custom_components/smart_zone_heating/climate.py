"""Climate entities for Smart Zone Heating zones."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import SmartZoneHeatingCoordinator, ZoneRuntimeState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zone thermostats from config entry."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        SmartZoneThermostat(coordinator, zone_id)
        for zone_id in coordinator.zones
    ]
    async_add_entities(entities)


class SmartZoneThermostat(ClimateEntity, RestoreEntity):
    """Virtual Thermostat for a single heating zone."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: SmartZoneHeatingCoordinator, zone_id: str) -> None:
        self.coordinator = coordinator
        self.zone_id = zone_id
        zone = self.zone
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone_id}_climate"
        self._attr_name = f"Termostato {zone.name}"
        self._attr_device_info = coordinator.device_info

    @property
    def zone(self) -> ZoneRuntimeState:
        return self.coordinator.zones[self.zone_id]

    async def async_added_to_hass(self) -> None:
        """Restore previous target temperature and HVAC mode on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            if last_state.state in (HVACMode.HEAT, HVACMode.OFF):
                self.zone.hvac_mode_enabled = last_state.state == HVACMode.HEAT
            restored_temp = last_state.attributes.get(ATTR_TEMPERATURE)
            if restored_temp is not None:
                try:
                    self.zone.target_temp = float(restored_temp)
                except (ValueError, TypeError):
                    pass

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def current_temperature(self) -> float | None:
        return self.zone.current_temp

    @property
    def target_temperature(self) -> float | None:
        return self.zone.target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self.zone.hvac_mode_enabled else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if not self.zone.hvac_mode_enabled or not self.coordinator.master_enabled:
            return HVACAction.OFF
        return HVACAction.HEATING if self.zone.requesting_heat else HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "valve_entity": self.zone.valve_entity,
            "temp_sensor": self.zone.temp_sensor,
            "requesting_heat": self.zone.requesting_heat,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self.zone.target_temp = float(temp)
            await self.coordinator.async_evaluate()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        self.zone.hvac_mode_enabled = hvac_mode == HVACMode.HEAT
        await self.coordinator.async_evaluate()
