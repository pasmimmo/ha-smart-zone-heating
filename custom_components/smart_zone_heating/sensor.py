"""Diagnostic and live monitored-entity sensors for Smart Zone Heating."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SmartZoneHeatingCoordinator, ZoneRuntimeState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up diagnostic status, cooldown, and selected hardware/sensor mirror entities."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    ent_reg = er.async_get(hass)

    entities: list[SensorEntity] = [
        SystemStateSensor(coordinator),
        HeaterDiagnosticSensor(coordinator),
    ]

    if coordinator.cooldown_enabled:
        entities.append(CooldownRemainingSensor(coordinator))
    else:
        if old_cd := ent_reg.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_cooldown_remaining"
        ):
            ent_reg.async_remove(old_cd)

    if coordinator.use_power_sensor and coordinator.power_sensor:
        entities.append(GeneratorPowerDiagnosticSensor(coordinator))
    else:
        if old_pwr := ent_reg.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_diag_generator_power"
        ):
            ent_reg.async_remove(old_pwr)

    for zone_id in coordinator.zones:
        entities.append(ZoneTempDiagnosticSensor(coordinator, zone_id))
        entities.append(ZoneValveDiagnosticSensor(coordinator, zone_id))

    async_add_entities(entities)


class _BaseDiagnosticSensor(SensorEntity):
    """Base diagnostic sensor listening to coordinator updates."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        ent_reg = er.async_get(self.hass)
        if self.entity_id and ent_reg.async_get(self.entity_id):
            ent_reg.async_update_entity(
                self.entity_id,
                entity_category=EntityCategory.DIAGNOSTIC,
                original_name=self._attr_name,
            )
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class SystemStateSensor(_BaseDiagnosticSensor):
    """Sensor showing the current operating state of the heating system (1st in Diagnostics)."""

    _attr_name = "\u00a0Stato Sistema"
    _attr_icon = "mdi:fire-circle"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_system_state"

    @property
    def native_value(self) -> str:
        return self.coordinator.system_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "heater_entity": self.coordinator.heater_entity,
            "power_sensor": self.coordinator.power_sensor,
            "current_power_watt": self.coordinator.current_power_watt,
            "active_zones": [
                z.name for z in self.coordinator.zones.values() if z.requesting_heat
            ],
            "forced_open_valves": {
                z.name: z.forced_open_reason
                for z in self.coordinator.zones.values()
                if z.forced_open_reason
            },
        }


class CooldownRemainingSensor(_BaseDiagnosticSensor):
    """Sensor showing remaining minutes of heat dissipation after heater turns off."""

    _attr_name = "\u00a0Timer Smaltimento"
    _attr_icon = "mdi:timer-outline"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cooldown_remaining"

    @property
    def native_value(self) -> int:
        return self.coordinator.cooldown_remaining_minutes


class HeaterDiagnosticSensor(_BaseDiagnosticSensor):
    """Diagnostic sensor showing live state of the selected Heat Generator switch."""

    _attr_name = "Generatore"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_diag_heater_state"

    @property
    def icon(self) -> str:
        st = self.coordinator.hass.states.get(self.coordinator.heater_entity)
        if st and st.state == STATE_ON:
            return "mdi:fire"
        return "mdi:fire-off"

    @property
    def native_value(self) -> str:
        st = self.coordinator.hass.states.get(self.coordinator.heater_entity)
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return "Indisponibile"
        return "ON" if st.state == STATE_ON else "OFF"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source_entity": self.coordinator.heater_entity,
        }


class GeneratorPowerDiagnosticSensor(_BaseDiagnosticSensor):
    """Diagnostic sensor showing live power consumption (Watt) from the selected power sensor."""

    _attr_name = "Consumo Generatore"
    _attr_icon = "mdi:flash"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_diag_generator_power"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.current_power_watt

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source_entity": self.coordinator.power_sensor,
            "threshold_watt": self.coordinator.power_threshold_watt,
        }


class ZoneTempDiagnosticSensor(_BaseDiagnosticSensor):
    """Diagnostic sensor showing live temperature of the currently selected zone sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator, zone_id: str) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        zone = self.zone
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone_id}_diag_temp"
        self._attr_name = f"Temperatura {zone.name}"

    @property
    def zone(self) -> ZoneRuntimeState:
        return self.coordinator.zones[self.zone_id]

    @property
    def native_value(self) -> float | None:
        return self.zone.current_temp

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source_entity": self.zone.temp_sensor,
            "target_temp": self.zone.target_temp,
            "requesting_heat": self.zone.requesting_heat,
        }


class ZoneValveDiagnosticSensor(_BaseDiagnosticSensor):
    """Diagnostic sensor showing live state of the selected zone valve switch."""

    def __init__(self, coordinator: SmartZoneHeatingCoordinator, zone_id: str) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        zone = self.zone
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone_id}_diag_valve"
        self._attr_name = f"Valvola {zone.name}"

    @property
    def zone(self) -> ZoneRuntimeState:
        return self.coordinator.zones[self.zone_id]

    @property
    def icon(self) -> str:
        st = self.coordinator.hass.states.get(self.zone.valve_entity)
        if st and st.state == STATE_ON:
            return "mdi:valve-open"
        return "mdi:valve-closed"

    @property
    def native_value(self) -> str:
        st = self.coordinator.hass.states.get(self.zone.valve_entity)
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return "Indisponibile"
        return "ON" if st.state == STATE_ON else "OFF"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source_entity": self.zone.valve_entity,
            "requesting_heat": self.zone.requesting_heat,
            "forced_open_reason": self.zone.forced_open_reason,
        }
