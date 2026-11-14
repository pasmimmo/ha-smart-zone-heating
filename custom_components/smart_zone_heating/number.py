"""Hysteresis number entity under Device Configuration."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CONF_HYSTERESIS, SmartZoneHeatingCoordinator
from .entity import SmartZoneBaseEntity


async def async_setup_entry(  # NOSONAR
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hysteresis number entity and remove legacy safety number entities."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]

    ent_reg = er.async_get(hass)
    for legacy_uid in (
        f"{entry.entry_id}_cooldown_minutes",
        f"{entry.entry_id}_power_threshold_watt",
    ):
        if old_id := ent_reg.async_get_entity_id("number", DOMAIN, legacy_uid):
            ent_reg.async_remove(old_id)

    async_add_entities([HysteresisNumber(coordinator)])


class HysteresisNumber(SmartZoneBaseEntity, NumberEntity):
    """Number entity to configure thermostat hysteresis."""

    _attr_name = "\u00a0[SZH] Isteresi"
    _attr_icon = "mdi:thermometer-lines"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0.1
    _attr_native_max_value = 2.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_hysteresis"

    @property
    def native_value(self) -> float:
        return self.coordinator.hysteresis

    async def async_set_native_value(self, value: float) -> None:
        old_val = self.coordinator.hysteresis
        self.coordinator.hysteresis = float(value)
        self.coordinator.persist_config_option(
            CONF_HYSTERESIS, self.coordinator.hysteresis
        )
        self.coordinator._last_trigger_context = self._context
        self.async_write_ha_state()
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {self.coordinator.hysteresis:g}°C, modifica isteresi ({old_val:g}°C -> {self.coordinator.hysteresis:g}°C)",
            context=self._context,
        )
        await self.coordinator.async_evaluate()
