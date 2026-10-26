"""Problem binary sensor for Smart Zone Heating."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up problem diagnostic binary sensor."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SystemProblemBinarySensor(coordinator)])


class SystemProblemBinarySensor(BinarySensorEntity):
    """Binary sensor that turns ON (Problem) when any configured sensor or switch is unavailable."""

    _attr_has_entity_name = True
    _attr_name = "Problema Impianto / Sensori"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_problem"
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
    def is_on(self) -> bool:
        return self.coordinator.problem_detected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "unavailable_entities": self.coordinator.unavailable_entities,
            "power_sensor": self.coordinator.power_sensor,
            "heater_entity": self.coordinator.heater_entity,
        }

