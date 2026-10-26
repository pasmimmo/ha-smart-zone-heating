"""Master, Away, and Schedule switches for Smart Zone Heating."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import SmartZoneHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for Smart Zone Heating."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            MasterHeatingSwitch(coordinator),
            GlobalAwaySwitch(coordinator),
            ScheduleEnabledSwitch(coordinator),
        ]
    )


class MasterHeatingSwitch(SwitchEntity, RestoreEntity):
    """Master switch to enable/disable the entire heating system."""

    _attr_has_entity_name = True
    _attr_name = "Impianto Abilitato"
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_master_enabled"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in ("on", "off"):
            self.coordinator.master_enabled = last_state.state == "on"

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self.coordinator.master_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.master_enabled = True
        await self.coordinator.async_evaluate()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.master_enabled = False
        await self.coordinator.async_evaluate()


class GlobalAwaySwitch(SwitchEntity, RestoreEntity):
    """Switch to set all zones to Fuori Casa (Away) mode at once."""

    _attr_has_entity_name = True
    _attr_name = "Modalità Fuori Casa"
    _attr_icon = "mdi:home-export-outline"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_global_away"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state == "on":
            await self.coordinator.async_set_global_away(True)

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self.coordinator.global_away_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_global_away(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_global_away(False)


class ScheduleEnabledSwitch(SwitchEntity, RestoreEntity):
    """Switch under Configuration to enable/disable automatic Day/Night hourly schedule."""

    _attr_has_entity_name = True
    _attr_name = "Cambio Orario Giorno/Notte"
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_schedule_enabled"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in ("on", "off"):
            self.coordinator.schedule_enabled = last_state.state == "on"

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self.coordinator.schedule_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.schedule_enabled = True
        self.coordinator._last_scheduled_period = None
        await self.coordinator.async_evaluate()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.schedule_enabled = False
        await self.coordinator.async_evaluate()

