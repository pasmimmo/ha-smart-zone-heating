"""Problem binary sensor for Smart Zone Heating."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SmartZoneHeatingCoordinator
from .entity import SmartZoneBaseEntity


async def async_setup_entry(  # NOSONAR
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up problem diagnostic binary sensor."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SystemProblemBinarySensor(coordinator)])


class SystemProblemBinarySensor(SmartZoneBaseEntity, BinarySensorEntity):
    """Binary sensor that turns ON (Problem) when any configured sensor or switch is unavailable."""

    _attr_name = "\u00a0[SZH] Problema Sensori"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_problem"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.problem_binary_sensor_entity_id = self.entity_id

    @property
    def is_on(self) -> bool:
        return self.coordinator.problem_detected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "unavailable_entities": self.coordinator.unavailable_entities,
            "dettaglio_problemi": [
                f"{self.coordinator.friendly_entity_label(eid)} ({eid})"
                for eid in self.coordinator.unavailable_entities
            ],
            "power_sensor": self.coordinator.power_sensor,
            "heater_entity": self.coordinator.heater_entity,
        }
