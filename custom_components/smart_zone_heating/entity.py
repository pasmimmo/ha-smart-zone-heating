"""Shared base entity classes for Smart Zone Heating."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

if TYPE_CHECKING:
    from .coordinator import SmartZoneHeatingCoordinator
    from .models import ZoneRuntimeState


class SmartZoneBaseEntity(Entity):
    """Base entity subscribed to SmartZoneHeatingCoordinator updates with causal Context propagation."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartZoneHeatingCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates when added to Home Assistant."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write state to Home Assistant preserving the evaluation Context when present."""
        if not self.hass or not self.entity_id:
            return
        if self.coordinator.current_eval_context is not None:
            self.async_set_context(self.coordinator.current_eval_context)
        self.async_write_ha_state()


class SmartZoneEntity(SmartZoneBaseEntity):
    """Base entity bound to a specific heating zone."""

    def __init__(self, coordinator: SmartZoneHeatingCoordinator, zone_id: str) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id

    @property
    def zone(self) -> ZoneRuntimeState:
        """Return runtime state for this entity's zone."""
        return self.coordinator.zones[self.zone_id]
