"""Time entities in Controls box for Day and Night schedule hours."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DAY_START_TIME, CONF_NIGHT_START_TIME, DOMAIN
from .coordinator import SmartZoneHeatingCoordinator
from .entity import SmartZoneBaseEntity


async def async_setup_entry(  # NOSONAR
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Day and Night start time entities (visibility managed via EntityRegistry)."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            DayStartTimeEntity(coordinator),
            NightStartTimeEntity(coordinator),
        ]
    )
    coordinator.apply_dynamic_config_visibility()


class DayStartTimeEntity(SmartZoneBaseEntity, TimeEntity):
    """Time entity in Controls box right below Giorno/Notte."""

    _attr_name = "[SZH] Giorno/Notte: Ora Giorno"
    _attr_icon = "mdi:weather-sunny"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_day_start_time"

    @property
    def native_value(self) -> time:
        return self.coordinator.day_start_time

    async def async_set_value(self, value: time) -> None:
        old_val = self.coordinator.day_start_time.strftime("%H:%M")
        self.coordinator.day_start_time = value
        self.coordinator.persist_config_option(CONF_DAY_START_TIME, value.isoformat())
        self.coordinator._last_scheduled_period = None
        self.coordinator._last_trigger_context = self._context
        self.async_write_ha_state()
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {value.strftime('%H:%M')}, modifica ora giorno ({old_val} -> {value.strftime('%H:%M')})",
            context=self._context,
        )
        await self.coordinator.async_evaluate()


class NightStartTimeEntity(SmartZoneBaseEntity, TimeEntity):
    """Time entity in Controls box right below Giorno/Notte."""

    _attr_name = "[SZH] Giorno/Notte: Ora Notte"
    _attr_icon = "mdi:weather-night"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_night_start_time"

    @property
    def native_value(self) -> time:
        return self.coordinator.night_start_time

    async def async_set_value(self, value: time) -> None:
        old_val = self.coordinator.night_start_time.strftime("%H:%M")
        self.coordinator.night_start_time = value
        self.coordinator.persist_config_option(
            CONF_NIGHT_START_TIME, value.isoformat()
        )
        self.coordinator._last_scheduled_period = None
        self.coordinator._last_trigger_context = self._context
        self.async_write_ha_state()
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {value.strftime('%H:%M')}, modifica ora notte ({old_val} -> {value.strftime('%H:%M')})",
            context=self._context,
        )
        await self.coordinator.async_evaluate()
