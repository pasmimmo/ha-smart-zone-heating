"""Diagnostic and state sensors for Smart Zone Heating."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SmartZoneHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up status sensor."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SystemStateSensor(coordinator)])


class SystemStateSensor(SensorEntity):
    """Sensor showing the current operating state of the heating system."""

    _attr_has_entity_name = True
    _attr_name = "Stato Sistema"
    _attr_icon = "mdi:fire-circle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_system_state"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        return self.coordinator.system_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "heater_entity": self.coordinator.heater_entity,
            "active_zones": [
                z.name for z in self.coordinator.zones.values() if z.requesting_heat
            ],
        }
