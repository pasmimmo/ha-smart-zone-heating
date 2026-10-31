"""Select entities under Device Configuration to choose zone sensors, safety valves, and notification settings."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_COOLDOWN_ZONE_ID,
    CONF_MANUAL_SAFETY_ZONE_ID,
    CONF_NOTIFY_LEVEL,
    CONF_NOTIFY_SERVICE,
    CONF_USE_SEPARATE_MANUAL_ZONE,
    DOMAIN,
    NOTIFY_LEVELS,
)
from .coordinator import SmartZoneHeatingCoordinator, ZoneRuntimeState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up temperature sensor selectors, safety valve selectors, and notification selectors."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = [
        ZoneTempSensorSelect(coordinator, zone_id)
        for zone_id in coordinator.zones
    ]
    entities.extend(
        [
            CooldownZoneSelect(coordinator),
            ManualSafetyZoneSelect(coordinator),
            NotifyServiceSelect(coordinator),
            NotifyLevelSelect(coordinator),
        ]
    )
    async_add_entities(entities)


class ZoneTempSensorSelect(SelectEntity):
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
        await super().async_added_to_hass()
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
        await self.coordinator.async_set_zone_temp_sensor(
            self.zone_id,
            option,
            select_entity_id=self.entity_id,
            context=self._context,
        )


class CooldownZoneSelect(SelectEntity):
    """Select which zone valve stays open during heat dissipation (cooldown)."""

    _attr_has_entity_name = True
    _attr_name = "Valvola Smaltimento Calore"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:valve-open"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cooldown_zone_select"
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
    def options(self) -> list[str]:
        return [z.name for z in self.coordinator.zones.values()]

    @property
    def current_option(self) -> str | None:
        return self.coordinator.get_zone_name(self.coordinator.cooldown_zone_id)

    async def async_select_option(self, option: str) -> None:
        z_id = self.coordinator.get_zone_id_by_name(option)
        if z_id:
            old_name = self.current_option or "?"
            self.coordinator.cooldown_zone_id = z_id
            self.coordinator.persist_config_option(CONF_COOLDOWN_ZONE_ID, z_id)
            self.coordinator._last_trigger_context = self._context
            await self.coordinator.async_record_action(
                entity_id=self.entity_id,
                action_desc=f"-> {option} (prec: {old_name})",
                context=self._context,
            )
            await self.coordinator.async_evaluate()


class ManualSafetyZoneSelect(SelectEntity):
    """Select which zone valve opens when manual ignition / power consumption > threshold W is detected."""

    _attr_has_entity_name = True
    _attr_name = "Valvola Sicurezza Accensione Manuale"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:shield-alert-outline"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_manual_safety_zone_select"
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
    def options(self) -> list[str]:
        return [z.name for z in self.coordinator.zones.values()]

    @property
    def current_option(self) -> str | None:
        return self.coordinator.get_zone_name(self.coordinator.manual_safety_zone_id)

    async def async_select_option(self, option: str) -> None:
        z_id = self.coordinator.get_zone_id_by_name(option)
        if z_id:
            old_name = self.current_option or "?"
            self.coordinator.manual_safety_zone_id = z_id
            self.coordinator.use_separate_manual_zone = (
                z_id != self.coordinator.cooldown_zone_id
            )
            self.coordinator.persist_config_option(CONF_MANUAL_SAFETY_ZONE_ID, z_id)
            self.coordinator.persist_config_option(
                CONF_USE_SEPARATE_MANUAL_ZONE, self.coordinator.use_separate_manual_zone
            )
            self.coordinator._last_trigger_context = self._context
            await self.coordinator.async_record_action(
                entity_id=self.entity_id,
                action_desc=f"-> {option} (prec: {old_name})",
                context=self._context,
            )
            await self.coordinator.async_evaluate()


class NotifyServiceSelect(SelectEntity):
    """Select entity to pick the notification service (notify.*) on the Device Page."""

    _attr_has_entity_name = True
    _attr_name = "Servizio di Notifica"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:cellphone-message"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_notify_service_select"
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
        self._handle_coordinator_update()
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {option} (prec: {old_svc})",
            context=self._context,
        )


class NotifyLevelSelect(SelectEntity):
    """Select entity to configure notification verbosity (off / error / warning / debug)."""

    _attr_has_entity_name = True
    _attr_name = "Livello Notifiche"
    _attr_translation_key = "notify_level"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bell-cog-outline"
    _attr_options = NOTIFY_LEVELS

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_notify_level_select"
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
                action_desc=f"-> {option} (prec: {old_lvl})",
                context=self._context,
            )
