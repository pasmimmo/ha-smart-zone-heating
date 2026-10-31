"""Time entities under Device Configuration for Day and Night schedule hours."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DAY_START_TIME, CONF_NIGHT_START_TIME, DOMAIN
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


class DayStartTimeEntity(TimeEntity):
    """Time entity for when Day mode starts (shown only when schedule_enabled is ON)."""

    _attr_has_entity_name = True
    _attr_name = "Termostati: Orario Inizio Giorno"
    _attr_icon = "mdi:weather-sunny"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_day_start_time"
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
    def native_value(self) -> time:
        return self.coordinator.day_start_time

    async def async_set_value(self, value: time) -> None:
        old_val = self.coordinator.day_start_time.strftime("%H:%M")
        self.coordinator.day_start_time = value
        self.coordinator.persist_config_option(CONF_DAY_START_TIME, value.isoformat())
        self.coordinator._last_scheduled_period = None
        self.coordinator._last_trigger_context = self._context
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {value.strftime('%H:%M')} (prec: {old_val})",
            context=self._context,
        )
        await self.coordinator.async_evaluate()


class NightStartTimeEntity(TimeEntity):
    """Time entity for when Night mode starts (shown only when schedule_enabled is ON)."""

    _attr_has_entity_name = True
    _attr_name = "Termostati: Orario Inizio Notte"
    _attr_icon = "mdi:weather-night"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_night_start_time"
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
    def native_value(self) -> time:
        return self.coordinator.night_start_time

    async def async_set_value(self, value: time) -> None:
        old_val = self.coordinator.night_start_time.strftime("%H:%M")
        self.coordinator.night_start_time = value
        self.coordinator.persist_config_option(CONF_NIGHT_START_TIME, value.isoformat())
        self.coordinator._last_scheduled_period = None
        self.coordinator._last_trigger_context = self._context
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {value.strftime('%H:%M')} (prec: {old_val})",
            context=self._context,
        )
        await self.coordinator.async_evaluate()
