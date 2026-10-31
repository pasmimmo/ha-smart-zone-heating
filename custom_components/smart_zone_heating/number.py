"""Number entities under Device Configuration."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_COOLDOWN_MINUTES, CONF_POWER_THRESHOLD_WATT, DOMAIN
from .coordinator import CONF_HYSTERESIS, SmartZoneHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up configuration number entities."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HysteresisNumber(coordinator),
            CooldownMinutesNumber(coordinator),
            PowerThresholdNumber(coordinator),
        ]
    )


class HysteresisNumber(NumberEntity):
    """Number entity to configure thermostat hysteresis."""

    _attr_has_entity_name = True
    _attr_name = "Termostati: Isteresi"
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
        old_val = self.coordinator.hysteresis
        self.coordinator.hysteresis = float(value)
        self.coordinator.persist_config_option(CONF_HYSTERESIS, self.coordinator.hysteresis)
        self.coordinator._last_trigger_context = self._context
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {self.coordinator.hysteresis:g}°C (prec: {old_val:g}°C)",
            context=self._context,
        )
        await self.coordinator.async_evaluate()


class CooldownMinutesNumber(NumberEntity):
    """Number entity to configure heat dissipation duration in minutes."""

    _attr_has_entity_name = True
    _attr_name = "Sicurezza: Durata Smaltimento Calore"
    _attr_icon = "mdi:timer-sand"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 240
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cooldown_minutes"
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
    def native_value(self) -> float:
        return float(self.coordinator.cooldown_minutes)

    async def async_set_native_value(self, value: float) -> None:
        old_val = self.coordinator.cooldown_minutes
        self.coordinator.cooldown_minutes = int(value)
        self.coordinator.persist_config_option(
            CONF_COOLDOWN_MINUTES, self.coordinator.cooldown_minutes
        )
        self.coordinator._last_trigger_context = self._context
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {self.coordinator.cooldown_minutes} min (prec: {old_val} min)",
            context=self._context,
        )
        await self.coordinator.async_evaluate()


class PowerThresholdNumber(NumberEntity):
    """Number entity to configure minimum power threshold in Watts for manual ignition safety."""

    _attr_has_entity_name = True
    _attr_name = "Sicurezza: Soglia Consumo"
    _attr_icon = "mdi:flash-alert"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 1.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_power_threshold_watt"
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
    def native_value(self) -> float:
        return self.coordinator.power_threshold_watt

    async def async_set_native_value(self, value: float) -> None:
        old_val = self.coordinator.power_threshold_watt
        self.coordinator.power_threshold_watt = float(value)
        self.coordinator.persist_config_option(
            CONF_POWER_THRESHOLD_WATT, self.coordinator.power_threshold_watt
        )
        self.coordinator._last_trigger_context = self._context
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {self.coordinator.power_threshold_watt:g}W (prec: {old_val:g}W)",
            context=self._context,
        )
        await self.coordinator.async_evaluate()
