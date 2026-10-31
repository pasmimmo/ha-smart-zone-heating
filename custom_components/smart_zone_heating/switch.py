"""Master, Away, and Day/Night Schedule switches for Smart Zone Heating (in Controls box)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_SCHEDULE_ENABLED, DOMAIN
from .coordinator import SmartZoneHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches in the Controls section."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Remove legacy ExclusiveControlSwitch entity if present (now managed via OptionsFlow gear menu)
    ent_reg = er.async_get(hass)
    if old_excl_id := ent_reg.async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_exclusive_control"
    ):
        ent_reg.async_remove(old_excl_id)

    async_add_entities(
        [
            MasterHeatingSwitch(coordinator),
            GlobalAwaySwitch(coordinator),
            ScheduleEnabledSwitch(coordinator),
        ]
    )


class MasterHeatingSwitch(SwitchEntity):
    """Master switch to enable/disable all zone thermostats (HEAT / OFF)."""

    _attr_has_entity_name = True
    _attr_name = "Attiva Termostati"
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_master_enabled"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        ent_reg = er.async_get(self.hass)
        if self.entity_id and ent_reg.async_get(self.entity_id):
            ent_reg.async_update_entity(
                self.entity_id,
                entity_category=None,
                original_name=self._attr_name,
            )
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
        await self.coordinator.async_set_master_enabled(
            True, entity_id=self.entity_id, context=self._context
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_master_enabled(
            False, entity_id=self.entity_id, context=self._context
        )


class GlobalAwaySwitch(SwitchEntity, RestoreEntity):
    """Switch to set all zones to Fuori Casa (Away) mode at once."""

    _attr_has_entity_name = True
    _attr_name = "Fuori Casa"
    _attr_icon = "mdi:home-export-outline"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_global_away"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        ent_reg = er.async_get(self.hass)
        if self.entity_id and ent_reg.async_get(self.entity_id):
            ent_reg.async_update_entity(
                self.entity_id,
                entity_category=None,
                original_name=self._attr_name,
            )
        last_state = await self.async_get_last_state()
        if last_state and last_state.state == "on":
            self.coordinator.global_away_mode = True

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
        await self.coordinator.async_set_global_away(
            True, entity_id=self.entity_id, context=self._context
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_global_away(
            False, entity_id=self.entity_id, context=self._context
        )


class ScheduleEnabledSwitch(SwitchEntity):
    """Switch in Controls box to enable/disable automatic Day/Night hourly schedule."""

    _attr_has_entity_name = True
    _attr_name = "Giorno/Notte"
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = None

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_schedule_enabled"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        ent_reg = er.async_get(self.hass)
        if self.entity_id and ent_reg.async_get(self.entity_id):
            ent_reg.async_update_entity(
                self.entity_id,
                entity_category=None,
                original_name=self._attr_name,
            )
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
        self.coordinator.persist_config_option(CONF_SCHEDULE_ENABLED, True)
        self.coordinator._last_scheduled_period = None
        self.coordinator._last_trigger_context = self._context
        self.coordinator._notify_listeners()
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc="-> on, ciclo automatico Giorno/Notte attivo",
            context=self._context,
        )
        await self.coordinator.async_evaluate()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.schedule_enabled = False
        self.coordinator.persist_config_option(CONF_SCHEDULE_ENABLED, False)
        self.coordinator._last_trigger_context = self._context
        self.coordinator._notify_listeners()
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc="-> off, ciclo automatico Giorno/Notte disattivato",
            context=self._context,
        )
        await self.coordinator.async_evaluate()
