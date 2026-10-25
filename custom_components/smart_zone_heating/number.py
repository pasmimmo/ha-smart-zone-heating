"""Number entities under Device Configuration."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_HYSTERESIS, DOMAIN
from .coordinator import SmartZoneHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up configuration number entities."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HysteresisNumber(coordinator)])


class HysteresisNumber(NumberEntity, RestoreEntity):
    """Number entity to configure thermostat hysteresis."""

    _attr_has_entity_name = True
    _attr_name = "Isteresi Termostati"
    _attr_icon = "mdi:thermometer-lines"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0.1
    _attr_native_max_value = 2.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_hysteresis"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            try:
                self.coordinator.hysteresis = float(last_state.state)
            except (ValueError, TypeError):
                self.coordinator.hysteresis = DEFAULT_HYSTERESIS

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return self.coordinator.hysteresis

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.hysteresis = float(value)
        await self.coordinator.async_evaluate()
