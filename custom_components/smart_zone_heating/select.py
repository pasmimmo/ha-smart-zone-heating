"""Select entities under Device Configuration: Zone input sensors and Notifications."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_NOTIFY_LEVEL,
    CONF_NOTIFY_SERVICE,
    DOMAIN,
    NOTIFY_LEVELS,
)
from .coordinator import SmartZoneHeatingCoordinator
from .entity import SmartZoneBaseEntity, SmartZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zone temperature sensor selectors and notification selectors in Configuration."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]

    ent_reg = er.async_get(hass)
    for legacy_uid in (
        f"{entry.entry_id}_cooldown_zone_select",
        f"{entry.entry_id}_manual_safety_zone_select",
    ):
        if old_id := ent_reg.async_get_entity_id("select", DOMAIN, legacy_uid):
            ent_reg.async_remove(old_id)

    entities: list[SelectEntity] = [
        ZoneTempSensorSelect(coordinator, zone_id)
        for zone_id in coordinator.zones
    ]
    entities.append(NotifyServiceSelect(coordinator))
    entities.append(NotifyLevelSelect(coordinator))
    async_add_entities(entities)
    coordinator.apply_dynamic_config_visibility()


class ZoneTempSensorSelect(SmartZoneEntity, SelectEntity):
    """Select entity in Device Configuration to pick which temperature sensor drives a zone."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:thermometer-check"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator, zone_id: str) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{zone_id}_temp_sensor_select"
        )
        self._attr_name = f"\u00a0[SZH] Sensore {self.zone.name}"

    @property
    def options(self) -> list[str]:
        """List all external temperature sensors available in Home Assistant (excluding SZH's own mirror sensors)."""
        ent_reg = er.async_get(self.hass)
        candidates: set[str] = {self.zone.temp_sensor}
        for state in self.hass.states.async_all(["sensor", "input_number"]):
            reg_entry = ent_reg.async_get(state.entity_id)
            if reg_entry and reg_entry.platform == DOMAIN:
                continue
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
        await self.coordinator.async_set_zone_temp_sensor(
            self.zone_id,
            option,
            select_entity_id=self.entity_id,
            context=self._context,
        )


class NotifyServiceSelect(SmartZoneBaseEntity, SelectEntity):
    """Select entity in Configuration box to pick the notification service (notify.*)."""

    _attr_name = "[SZH] Notifiche"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:cellphone-message"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_notify_service_select"

    @property
    def options(self) -> list[str]:
        candidates: set[str] = {"none"}
        if self.coordinator.notify_service:
            candidates.add(self.coordinator.notify_service)
        notify_services = self.hass.services.async_services().get("notify", {})
        for svc_name in notify_services:
            candidates.add(f"notify.{svc_name}")
        return ["none"] + sorted(c for c in candidates if c != "none")

    @property
    def current_option(self) -> str:
        return self.coordinator.notify_service or "none"

    async def async_select_option(self, option: str) -> None:
        old_svc = self.current_option
        self.coordinator.notify_service = None if option == "none" else option
        self.coordinator.persist_config_option(CONF_NOTIFY_SERVICE, option)
        self.coordinator.apply_dynamic_config_visibility()
        self.coordinator._notify_listeners()
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {option}, modifica servizio notifiche ({old_svc} -> {option})",
            context=self._context,
        )


class NotifyLevelSelect(SmartZoneBaseEntity, SelectEntity):
    """Select entity in Configuration box right below Notifiche."""

    _attr_name = "[SZH] Notifiche: Livello"
    _attr_translation_key = "notify_level"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bell-cog-outline"
    _attr_options = NOTIFY_LEVELS

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_notify_level_select"

    @property
    def current_option(self) -> str:
        return self.coordinator.notify_level

    async def async_select_option(self, option: str) -> None:
        if option in NOTIFY_LEVELS:
            old_lvl = self.coordinator.notify_level
            self.coordinator.notify_level = option
            self.coordinator.persist_config_option(CONF_NOTIFY_LEVEL, option)
            self._handle_coordinator_update()
            await self.coordinator.async_record_action(
                entity_id=self.entity_id,
                action_desc=f"-> {option}, modifica livello notifiche ({old_lvl} -> {option})",
                context=self._context,
            )
