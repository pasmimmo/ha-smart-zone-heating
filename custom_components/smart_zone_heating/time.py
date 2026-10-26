"""Time entities under Device Configuration for Day and Night schedule hours."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import SmartZoneHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Day and Night start time entities."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            DayStartTimeEntity(coordinator),
            NightStartTimeEntity(coordinator),
        ]
    )


class DayStartTimeEntity(TimeEntity, RestoreEntity):
    """Time entity for when Day mode starts."""

    _attr_has_entity_name = True
    _attr_name = "Orario Inizio Giorno"
    _attr_icon = "mdi:weather-sunny"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_day_start_time"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            parsed = dt_util.parse_time(last_state.state)
            if parsed is not None:
                self.coordinator.day_start_time = parsed

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> time:
        return self.coordinator.day_start_time

    async def async_set_value(self, value: time) -> None:
        self.coordinator.day_start_time = value
        self.coordinator._last_scheduled_period = None
        await self.coordinator.async_evaluate()


class NightStartTimeEntity(TimeEntity, RestoreEntity):
    """Time entity for when Night mode starts."""

    _attr_has_entity_name = True
    _attr_name = "Orario Inizio Notte"
    _attr_icon = "mdi:weather-night"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_night_start_time"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            parsed = dt_util.parse_time(last_state.state)
            if parsed is not None:
                self.coordinator.night_start_time = parsed

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> time:
        return self.coordinator.night_start_time

    async def async_set_value(self, value: time) -> None:
        self.coordinator.night_start_time = value
        self.coordinator._last_scheduled_period = None
        await self.coordinator.async_evaluate()

