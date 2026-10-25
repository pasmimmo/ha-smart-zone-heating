"""Select entities under Device Configuration to choose zone temperature sensors on the fly."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import SmartZoneHeatingCoordinator, ZoneRuntimeState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up temperature sensor selectors for each zone."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        ZoneTempSensorSelect(coordinator, zone_id)
        for zone_id in coordinator.zones
    ]
    async_add_entities(entities)


class ZoneTempSensorSelect(SelectEntity, RestoreEntity):
    """Select entity in Device Configuration to pick which temperature sensor drives a zone."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:thermometer-check"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator, zone_id: str) -> None:
        self.coordinator = coordinator
        self.zone_id = zone_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone_id}_temp_sensor_select"
        self._attr_name = f"Sensore Temperatura {self.zone.name}"
        self._attr_device_info = coordinator.device_info

    @property
    def zone(self) -> ZoneRuntimeState:
        return self.coordinator.zones[self.zone_id]

    async def async_added_to_hass(self) -> None:
        """Restore previously selected temperature sensor."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state and last_state.state not in ("unknown", "unavailable"):
            await self.coordinator.async_set_zone_temp_sensor(self.zone_id, last_state.state)

        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def options(self) -> list[str]:
        """List all temperature sensors available in Home Assistant."""
        candidates: set[str] = {self.zone.temp_sensor}
        for state in self.hass.states.async_all(["sensor", "input_number"]):
            dev_class = state.attributes.get("device_class")
            unit = state.attributes.get("unit_of_measurement")
            if dev_class == "temperature" or unit in (
                UnitOfTemperature.CELSIUS,
                UnitOfTemperature.FAHRENHEIT,
                "°C",
                "°F",
            ):
                candidates.add(state.entity_id)
        return sorted(candidates)

    @property
    def current_option(self) -> str | None:
        return self.zone.temp_sensor

    async def async_select_option(self, option: str) -> None:
        """Update the zone's active temperature sensor."""
        await self.coordinator.async_set_zone_temp_sensor(self.zone_id, option)
