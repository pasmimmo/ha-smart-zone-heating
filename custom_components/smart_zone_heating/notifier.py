"""Logbook event recording and notification dispatching mixin for Smart Zone Heating."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    NOTIFY_LEVEL_DEBUG,
    NOTIFY_LEVEL_ERROR,
    NOTIFY_LEVEL_OFF,
    NOTIFY_LEVEL_WARNING,
)
from .models import LOGBOOK_NAME, NOTIFY_PREFIX

_LOGGER = logging.getLogger(__name__)

_LEVEL_PRIORITY = {
    NOTIFY_LEVEL_OFF: 0,
    NOTIFY_LEVEL_ERROR: 3,
    NOTIFY_LEVEL_WARNING: 2,
    NOTIFY_LEVEL_DEBUG: 1,
}


class CoordinatorNotificationMixin:
    """Mixin handling Home Assistant Logbook attribution and notify.* service calls."""

    hass: HomeAssistant
    notify_service: str | None
    notify_level: str
    problem_binary_sensor_entity_id: str | None

    def friendly_entity_label(self, entity_id: str) -> str:
        """Return a human-friendly name for an entity_id (falling back to entity_id)."""
        if state := self.hass.states.get(entity_id):
            if state.name and state.name != entity_id:
                return state.name
        ent_reg = er.async_get(self.hass)
        if reg_entry := ent_reg.async_get(entity_id):
            if reg_entry.name:
                return reg_entry.name
            if reg_entry.original_name:
                return reg_entry.original_name
        return entity_id

    def _fire_logbook_entry(
        self,
        entity_id: str | None,
        message: str,
        context: Context | None = None,
    ) -> Context:
        """Fire a Home Assistant logbook_entry event sharing the exact trigger Context so 'Cosa è successo' links the cause."""
        action_context = context if context is not None else Context()
        prefixed_msg = (
            message
            if message.startswith(LOGBOOK_NAME)
            else f"{LOGBOOK_NAME}: {message}"
        )
        log_data: dict[str, Any] = {
            "name": LOGBOOK_NAME,
            "message": prefixed_msg,
            "domain": DOMAIN,
        }
        if entity_id:
            log_data["entity_id"] = entity_id
        self.hass.bus.async_fire("logbook_entry", log_data, context=action_context)
        return action_context

    def _should_notify(self, event_level: str) -> bool:
        """Return True if the configured notify_level includes event_level."""
        if not self.notify_service or self.notify_level == NOTIFY_LEVEL_OFF:
            return False
        configured_prio = _LEVEL_PRIORITY.get(self.notify_level, 0)
        event_prio = _LEVEL_PRIORITY.get(event_level, 99)
        if configured_prio == 0:
            return False
        return event_prio >= configured_prio

    async def _async_notify(self, event_level: str, message: str) -> None:
        """Send notification via configured notify.* service if level matches."""
        full_msg = (
            message
            if message.startswith(NOTIFY_PREFIX)
            else f"{NOTIFY_PREFIX} {message}"
        )
        _LOGGER.debug("%s [%s]", full_msg, event_level.upper())
        if not self._should_notify(event_level):
            return

        prefix = {
            NOTIFY_LEVEL_ERROR: "🚨 [ERROR]",
            NOTIFY_LEVEL_WARNING: "⚠️ [WARN]",
            NOTIFY_LEVEL_DEBUG: "ℹ️ [DEBUG]",
        }.get(event_level, "")
        title = f"{prefix} {LOGBOOK_NAME}".strip()

        svc = self.notify_service
        if not svc:
            return
        domain, _, service_name = svc.partition(".")
        if not service_name:
            domain = "notify"
            service_name = svc

        try:
            if domain == "notify" and service_name == "persistent_notification":
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {"title": title, "message": full_msg},
                    blocking=False,
                )
            else:
                await self.hass.services.async_call(
                    domain,
                    service_name,
                    {"title": title, "message": full_msg},
                    blocking=False,
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Impossibile inviare notifica su %s: %s", svc, err)

    async def async_record_action(
        self,
        entity_id: str | None,
        action_desc: str,
        context: Context | None = None,
        level: str = NOTIFY_LEVEL_DEBUG,
    ) -> Context:
        """Record a unified action in both Home Assistant Logbook and Debug Notifications."""
        ctx = self._fire_logbook_entry(
            entity_id=entity_id,
            message=action_desc,
            context=context,
        )
        target_prefix = f"{entity_id} " if entity_id else ""
        await self._async_notify(level, f"{NOTIFY_PREFIX} {target_prefix}{action_desc}")
        return ctx

    async def _async_emit_problem_logbook_entries(
        self,
        newly_unavailable: list[str],
        newly_restored: list[str],
        eval_ctx: Context,
    ) -> None:
        """Record Logbook and notification entries when entities become unavailable or restored."""
        if newly_unavailable:
            unavail_desc = ", ".join(
                f"{self.friendly_entity_label(eid)} ({eid})" for eid in newly_unavailable
            )
            await self.async_record_action(
                entity_id=self.problem_binary_sensor_entity_id,
                action_desc=f"rilevato problema -> indisponibile: {unavail_desc}",
                context=eval_ctx,
                level=NOTIFY_LEVEL_ERROR,
            )
            for eid in newly_unavailable:
                st = self.hass.states.get(eid)
                self._fire_logbook_entry(
                    entity_id=eid,
                    message=f"entità indisponibile ({self.friendly_entity_label(eid)})",
                    context=st.context if st is not None else eval_ctx,
                )

        if newly_restored:
            restored_desc = ", ".join(
                f"{self.friendly_entity_label(eid)} ({eid})" for eid in newly_restored
            )
            await self.async_record_action(
                entity_id=self.problem_binary_sensor_entity_id,
                action_desc=f"problema risolto -> ripristinato: {restored_desc}",
                context=eval_ctx,
                level=NOTIFY_LEVEL_ERROR,
            )
            for eid in newly_restored:
                st = self.hass.states.get(eid)
                self._fire_logbook_entry(
                    entity_id=eid,
                    message=f"entità ripristinata ({self.friendly_entity_label(eid)})",
                    context=st.context if st is not None else eval_ctx,
                )
