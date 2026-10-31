"""Select entities under Device Configuration: Zone input sensors and Notifications."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_NOTIFY_LEVEL,
    CONF_NOTIFY_SERVICE,
    DOMAIN,
    NOTIFY_LEVELS,
)
from .coordinator import SmartZoneHeatingCoordinator, ZoneRuntimeState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zone temperature sensor selectors and notification selectors in Configuration."""
    coordinator: SmartZoneHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Remove legacy safety valve select entities (now configured via OptionsFlow gear menu)
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
    async_add_entities(entities)

    # Dynamically add/remove NotifyLevelSelect right below Notifiche when a notify service is active
    active_level_entities: list[SelectEntity] = []
    last_has_notify: bool | None = None

    async def _async_sync_notify_level_entity() -> None:
        nonlocal last_has_notify
        has_notify = bool(coordinator.notify_service)
        if has_notify == last_has_notify:
            return
        last_has_notify = has_notify

        if has_notify:
            if not active_level_entities:
                lvl_ent = NotifyLevelSelect(coordinator)
                active_level_entities.append(lvl_ent)
                async_add_entities([lvl_ent])
        else:
            while active_level_entities:
                ent = active_level_entities.pop()
                ent_id = ent.entity_id
                await ent.async_remove(force_remove=True)
                if ent_id and ent_reg.async_get(ent_id):
                    ent_reg.async_remove(ent_id)
            uid = f"{entry.entry_id}_notify_level_select"
            if eid := ent_reg.async_get_entity_id("select", DOMAIN, uid):
                ent_reg.async_remove(eid)

    await _async_sync_notify_level_entity()

    @callback
    def _on_coordinator_update() -> None:
        if bool(coordinator.notify_service) != last_has_notify:
            hass.async_create_task(_async_sync_notify_level_entity())

    entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))


class ZoneTempSensorSelect(SelectEntity):
    """Select entity in Device Configuration to pick which temperature sensor drives a zone."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:thermometer-check"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator, zone_id: str) -> None:
        self.coordinator = coordinator
        self.zone_id = zone_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone_id}_temp_sensor_select"
        # Leading non-breaking space sorts Sensore right after Isteresi and before Notifiche
        self._attr_name = f"\u00a0Sensore {self.zone.name}"
        self._attr_device_info = coordinator.device_info

    @property
    def zone(self) -> ZoneRuntimeState:
        return self.coordinator.zones[self.zone_id]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        ent_reg = er.async_get(self.hass)
        if self.entity_id and ent_reg.async_get(self.entity_id):
            ent_reg.async_update_entity(
                self.entity_id,
                entity_category=EntityCategory.CONFIG,
                original_name=self._attr_name,
            )
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


class NotifyServiceSelect(SelectEntity):
    """Select entity in Configuration box to pick the notification service (notify.*)."""

    _attr_has_entity_name = True
    _attr_name = "Notifiche"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:cellphone-message"

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_notify_service_select"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        ent_reg = er.async_get(self.hass)
        if self.entity_id and ent_reg.async_get(self.entity_id):
            ent_reg.async_update_entity(
                self.entity_id,
                entity_category=EntityCategory.CONFIG,
                original_name=self._attr_name,
            )
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
        self.coordinator._notify_listeners()
        await self.coordinator.async_record_action(
            entity_id=self.entity_id,
            action_desc=f"-> {option} (prec: {old_svc})",
            context=self._context,
        )


class NotifyLevelSelect(SelectEntity):
    """Select entity in Configuration box right below Notifiche (shown only when a notify service is active)."""

    _attr_has_entity_name = True
    _attr_name = "Notifiche: Livello"
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
        ent_reg = er.async_get(self.hass)
        if self.entity_id and ent_reg.async_get(self.entity_id):
            ent_reg.async_update_entity(
                self.entity_id,
                entity_category=EntityCategory.CONFIG,
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
