"""Physical switch control, Exclusive Control enforcement, and Registry visibility mixin."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import CONF_EXCLUSIVE_CONTROL, DOMAIN, NOTIFY_LEVEL_DEBUG
from .models import ZoneRuntimeState


class CoordinatorSwitchMixin:
    """Mixin managing switch service calls, Wi-Fi latency grace, and entity registry visibility."""

    hass: HomeAssistant
    entry: ConfigEntry
    heater_entity: str
    zones: dict[str, ZoneRuntimeState]
    exclusive_control: bool
    schedule_enabled: bool
    notify_service: str | None
    _last_desired_switch_state: dict[str, bool]
    _pending_switch_cmd: dict[str, tuple[bool, datetime]]
    _last_trigger_context: Context | None
    _is_stopping: bool

    def persist_config_option(self, key: str, value: Any) -> None:
        """Implemented by Coordinator."""
        raise NotImplementedError

    async def async_record_action(
        self,
        entity_id: str | None,
        action_desc: str,
        context: Context | None = None,
        level: str = NOTIFY_LEVEL_DEBUG,
    ) -> Context:
        """Implemented by CoordinatorNotificationMixin."""
        raise NotImplementedError

    async def async_evaluate(self) -> None:
        """Implemented by Coordinator."""
        raise NotImplementedError

    @callback
    def _set_entity_hidden_by_unique_id(self, unique_id: str, should_hide: bool) -> None:
        """Hide or unhide one of our own config entities by its unique_id."""
        ent_reg = er.async_get(self.hass)
        entity_id = (
            ent_reg.async_get_entity_id("time", DOMAIN, unique_id)
            or ent_reg.async_get_entity_id("select", DOMAIN, unique_id)
            or ent_reg.async_get_entity_id("number", DOMAIN, unique_id)
        )
        if not entity_id:
            return
        reg_entry = ent_reg.async_get(entity_id)
        if reg_entry is None:
            return
        if should_hide and reg_entry.hidden_by is None:
            ent_reg.async_update_entity(
                entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
            )
        elif not should_hide and reg_entry.hidden_by == er.RegistryEntryHider.INTEGRATION:
            ent_reg.async_update_entity(entity_id, hidden_by=None)

    @callback
    def apply_dynamic_config_visibility(self) -> None:
        """Dynamically show/hide child configuration entities based on parent toggle states."""
        hide_schedule_times = not self.schedule_enabled
        self._set_entity_hidden_by_unique_id(
            f"{self.entry.entry_id}_day_start_time", hide_schedule_times
        )
        self._set_entity_hidden_by_unique_id(
            f"{self.entry.entry_id}_night_start_time", hide_schedule_times
        )
        hide_notify_level = not bool(self.notify_service)
        self._set_entity_hidden_by_unique_id(
            f"{self.entry.entry_id}_notify_level_select", hide_notify_level
        )

    @callback
    def apply_exclusive_control_visibility(self, force_unhide: bool = False) -> None:
        """Hide or unhide managed physical switch entities in Entity Registry based on exclusive_control."""
        ent_reg = er.async_get(self.hass)
        managed_switches = {self.heater_entity} | {
            z.valve_entity for z in self.zones.values()
        }
        should_hide = self.exclusive_control and not force_unhide

        for entity_id in managed_switches:
            reg_entry = ent_reg.async_get(entity_id)
            if reg_entry is None:
                continue
            if should_hide and reg_entry.hidden_by is None:
                ent_reg.async_update_entity(
                    entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
                )
            elif not should_hide and reg_entry.hidden_by == er.RegistryEntryHider.INTEGRATION:
                ent_reg.async_update_entity(entity_id, hidden_by=None)

    async def async_set_exclusive_control(
        self, enabled: bool, entity_id: str | None = None, context: Context | None = None
    ) -> None:
        """Toggle exclusive control mode, update switch visibility, and evaluate."""
        self.exclusive_control = enabled
        self.persist_config_option(CONF_EXCLUSIVE_CONTROL, enabled)
        self._last_trigger_context = context
        self.apply_exclusive_control_visibility()
        if enabled:
            self._last_desired_switch_state.clear()

        state_str = "on" if enabled else "off"
        detail = (
            "switch fisici nascosti e bloccati"
            if enabled
            else "switch fisici visibili e sbloccati"
        )
        await self.async_record_action(
            entity_id=entity_id,
            action_desc=f"-> {state_str}, {detail}",
            context=context,
        )
        await self.async_evaluate()

    def _is_switch_command_in_flight(
        self, entity_id: str, turn_on: bool, now: datetime
    ) -> bool:
        """Return True if an identical command was sent to entity_id within the last 15 seconds."""
        pending = self._pending_switch_cmd.get(entity_id)
        if pending is None:
            return False
        pend_target, pend_sent_at = pending
        return pend_target == turn_on and (now - pend_sent_at).total_seconds() < 15.0

    def _handle_offline_switch(self, entity_id: str) -> None:
        """Reset switch tracking when a switch entity is unavailable."""
        if self.exclusive_control:
            self._last_desired_switch_state.pop(entity_id, None)
        self._pending_switch_cmd.pop(entity_id, None)

    def _build_switch_log_and_cause(
        self,
        turn_on: bool,
        desired_changed: bool,
        reason: str,
        state_context: Context,
        trigger_context: Context | None,
    ) -> tuple[str, Context | None]:
        """Build logbook message and select causal Context for a switch command."""
        target_str = "on" if turn_on else "off"
        if self.exclusive_control and not desired_changed:
            return (
                f"ripristino stato -> {target_str}, {reason} (controllo esclusivo)",
                state_context,
            )
        return f"-> {target_str}, {reason}", trigger_context

    async def _async_command_switch(
        self,
        entity_id: str,
        turn_on: bool,
        reason: str,
        trigger_context: Context | None = None,
    ) -> bool:
        """Command a switch respecting Exclusive Control, Wi-Fi switch latency, and Logbook cause attribution."""
        if getattr(self, "_is_stopping", False) or self.hass.is_stopping:
            return False
        state_obj = self.hass.states.get(entity_id)
        if state_obj is None or state_obj.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._handle_offline_switch(entity_id)
            return False

        prev_desired = self._last_desired_switch_state.get(entity_id)
        desired_changed = prev_desired is None or prev_desired != turn_on
        self._last_desired_switch_state[entity_id] = turn_on

        if (state_obj.state == STATE_ON) == turn_on:
            self._pending_switch_cmd.pop(entity_id, None)
            return False

        if not self.exclusive_control and not desired_changed:
            return False

        now = dt_util.utcnow()
        if not desired_changed and self._is_switch_command_in_flight(entity_id, turn_on, now):
            return False

        self._pending_switch_cmd[entity_id] = (turn_on, now)
        log_msg, cause_ctx = self._build_switch_log_and_cause(
            turn_on, desired_changed, reason, state_obj.context, trigger_context
        )

        action_context = await self.async_record_action(
            entity_id=entity_id,
            action_desc=log_msg,
            context=cause_ctx,
            level=NOTIFY_LEVEL_DEBUG,
        )

        domain = entity_id.split(".")[0]
        if domain not in ("switch", "input_boolean", "homeassistant"):
            domain = "homeassistant"
        await self.hass.services.async_call(
            domain,
            SERVICE_TURN_ON if turn_on else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
            context=action_context,
        )
        return True

