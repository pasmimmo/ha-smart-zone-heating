"""Time entities in Controls box for Day and Night schedule hours (dynamically added/removed right below Giorno/Notte)."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DAY_START_TIME, CONF_NIGHT_START_TIME, DOMAIN
from .coordinator import SmartZoneHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Day and Night start time entities dynamically when schedule_enabled is True."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    active_entities: list[TimeEntity] = []
    last_schedule_enabled: bool | None = None

    async def _async_sync_schedule_time_entities() -> None:
        nonlocal last_schedule_enabled
        if coordinator.schedule_enabled == last_schedule_enabled:
            return
        last_schedule_enabled = coordinator.schedule_enabled
        ent_reg = er.async_get(hass)

        if coordinator.schedule_enabled:
            if not active_entities:
                new_entities: list[TimeEntity] = [
                    DayStartTimeEntity(coordinator),
                    NightStartTimeEntity(coordinator),
                ]
                active_entities.extend(new_entities)
                async_add_entities(new_entities)
        else:
            while active_entities:
                ent = active_entities.pop()
                ent_id = ent.entity_id
                await ent.async_remove(force_remove=True)
                if ent_id and ent_reg.async_get(ent_id):
                    ent_reg.async_remove(ent_id)
            for uid in (
                f"{entry.entry_id}_day_start_time",
                f"{entry.entry_id}_night_start_time",
            ):
                if eid := ent_reg.async_get_entity_id("time", DOMAIN, uid):
                    ent_reg.async_remove(eid)

    await _async_sync_schedule_time_entities()

    @callback
    def _on_coordinator_update() -> None:
        if coordinator.schedule_enabled != last_schedule_enabled:
            hass.async_create_task(_async_sync_schedule_time_entities())

    entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))


class DayStartTimeEntity(TimeEntity):
    """Time entity in Controls box right below Giorno/Notte (shown only when schedule_enabled is ON)."""

    _attr_has_entity_name = True
    _attr_name = "Giorno/Notte: Ora Giorno"
    _attr_icon = "mdi:weather-sunny"
    _attr_entity_category = None

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_day_start_time"
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
        if self.hass and self.entity_id:
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
    """Time entity in Controls box right below Giorno/Notte (shown only when schedule_enabled is ON)."""

    _attr_has_entity_name = True
    _attr_name = "Giorno/Notte: Ora Notte"
    _attr_icon = "mdi:weather-night"
    _attr_entity_category = None

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_night_start_time"
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
        if self.hass and self.entity_id:
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
