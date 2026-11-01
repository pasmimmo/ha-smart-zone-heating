"""Heat dissipation (Cooldown) and Manual Ignition Safety mixin for Smart Zone Heating."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import NOTIFY_LEVEL_DEBUG, NOTIFY_LEVEL_WARNING
from .models import ZoneRuntimeState, fmt_temp


class CoordinatorSafetyMixin:
    """Mixin managing Watt/timer heat dissipation and Manual Ignition Safety."""

    hass: HomeAssistant
    zones: dict[str, ZoneRuntimeState]
    cooldown_enabled: bool
    cooldown_minutes: int
    cooldown_zone_id: str | None
    in_cooldown: bool
    cooldown_started_at: datetime | None
    cooldown_until: datetime | None
    _was_heating: bool
    _cooldown_fallback_warned: bool
    power_sensor: str | None
    use_power_sensor: bool
    power_threshold_watt: float
    power_grace_seconds: int
    current_power_watt: float | None
    manual_safety_enabled: bool
    manual_safety_zone_id: str | None
    manual_safety_active: bool
    _was_manual_safety_active: bool
    _unsub_cooldown_timer: Callable[[], None] | None
    _unsub_grace_timer: Callable[[], None] | None

    def get_zone_name(self, zone_id: str | None) -> str | None:
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

    @property
    def cooldown_remaining_minutes(self) -> int:
        """Return remaining minutes of fallback cooldown timer when active."""
        if not self.in_cooldown or not self.cooldown_until:
            return 0
        now = dt_util.utcnow()
        if now >= self.cooldown_until:
            return 0
        delta = self.cooldown_until - now
        return max(1, int((delta.total_seconds() + 59) // 60))

    def _start_cooldown(self) -> None:
        """Start heat dissipation phase (power-monitored primary + timer fallback)."""
        self._cancel_cooldown()
        now = dt_util.utcnow()
        self.in_cooldown = True
        self.cooldown_started_at = now
        self._cooldown_fallback_warned = False

        if self.cooldown_minutes > 0:
            self.cooldown_until = now + timedelta(minutes=self.cooldown_minutes)

            @callback
            def _on_cooldown_timer_expired(_now: datetime) -> None:
                self._unsub_cooldown_timer = None
                self.hass.async_create_task(self.async_evaluate())

            self._unsub_cooldown_timer = async_call_later(
                self.hass,
                self.cooldown_minutes * 60,
                _on_cooldown_timer_expired,
            )

        grace = max(5, self.power_grace_seconds)

        @callback
        def _on_grace_expired(_now: datetime) -> None:
            self._unsub_grace_timer = None
            self.hass.async_create_task(self.async_evaluate())

        self._unsub_grace_timer = async_call_later(self.hass, grace, _on_grace_expired)

    def _cancel_cooldown(self) -> None:
        """Cancel active cooldown phase and timers."""
        if self._unsub_cooldown_timer:
            self._unsub_cooldown_timer()
            self._unsub_cooldown_timer = None
        if self._unsub_grace_timer:
            self._unsub_grace_timer()
            self._unsub_grace_timer = None
        self.in_cooldown = False
        self.cooldown_started_at = None
        self.cooldown_until = None
        self._cooldown_fallback_warned = False

    async def _async_evaluate_cooldown(
        self,
        any_heating: bool,
        use_watt_for_cooldown: bool,
        power_sensor_available: bool,
        now: datetime,
        trigger_ctx: Context | None,
    ) -> str | None:
        """Manage heat dissipation phase (Watt-driven primary, timer fallback)."""
        if not self.cooldown_enabled or any_heating:
            self._was_heating = any_heating
            if self.in_cooldown:
                self._cancel_cooldown()
            return None

        if self._was_heating:
            self._was_heating = False
            self._start_cooldown()
            cooldown_zone_name = self.get_zone_name(self.cooldown_zone_id) or ""
            await self.async_record_action(
                entity_id=None,
                action_desc=f"avvio smaltimento calore su {cooldown_zone_name}",
                context=trigger_ctx,
            )

        if not self.in_cooldown or self.cooldown_zone_id not in self.zones:
            return None

        if use_watt_for_cooldown and power_sensor_available:
            return await self._async_check_power_cooldown(now, trigger_ctx)
        return await self._async_check_timer_cooldown(
            use_watt_for_cooldown, power_sensor_available, now, trigger_ctx
        )

    async def _async_check_power_cooldown(
        self, now: datetime, trigger_ctx: Context | None
    ) -> str | None:
        """Evaluate Watt-driven cooldown completion."""
        in_initial_grace = (
            self.cooldown_started_at is not None
            and (now - self.cooldown_started_at).total_seconds()
            < max(5, self.power_grace_seconds)
        )
        above_threshold = (
            self.current_power_watt is not None
            and self.current_power_watt >= self.power_threshold_watt
        )
        if above_threshold or in_initial_grace:
            return "power"

        self._cancel_cooldown()
        await self.async_record_action(
            entity_id=None,
            action_desc=f"fine smaltimento calore, potenza {self.current_power_watt:.0f}W < {self.power_threshold_watt:.0f}W",
            context=trigger_ctx,
        )
        return None

    async def _async_check_timer_cooldown(
        self,
        use_watt_for_cooldown: bool,
        power_sensor_available: bool,
        now: datetime,
        trigger_ctx: Context | None,
    ) -> str | None:
        """Evaluate timer-based cooldown (or fallback when power sensor is offline)."""
        if (
            use_watt_for_cooldown
            and not power_sensor_available
            and not self._cooldown_fallback_warned
        ):
            self._cooldown_fallback_warned = True
            await self.async_record_action(
                entity_id=self.power_sensor,
                action_desc=f"indisponibile in smaltimento -> attivo timer fallback ({self.cooldown_minutes} min)",
                context=trigger_ctx,
                level=NOTIFY_LEVEL_WARNING,
            )

        if self.cooldown_until is not None and now < self.cooldown_until:
            return "timer"

        self._cancel_cooldown()
        await self.async_record_action(
            entity_id=None,
            action_desc="fine smaltimento calore (scaduto timer fallback)",
            context=trigger_ctx,
        )
        return None

    async def _async_evaluate_manual_safety(
        self,
        any_heating: bool,
        cooldown_mode: str | None,
        power_sensor_configured: bool,
        power_sensor_available: bool,
        trigger_ctx: Context | None,
    ) -> None:
        """Evaluate Manual Ignition Safety (> threshold W while thermostats are idle)."""
        power_above_threshold = (
            self.manual_safety_enabled
            and power_sensor_configured
            and power_sensor_available
            and self.current_power_watt is not None
            and self.current_power_watt >= self.power_threshold_watt
        )
        self.manual_safety_active = (
            not any_heating
            and cooldown_mode is None
            and power_above_threshold
            and self.manual_safety_zone_id in self.zones
        )

        if self.manual_safety_active and not self._was_manual_safety_active:
            safety_zone_name = self.get_zone_name(self.manual_safety_zone_id) or ""
            await self.async_record_action(
                entity_id=self.power_sensor,
                action_desc=f"accensione manuale rilevata ({self.current_power_watt:.0f}W >= {self.power_threshold_watt:.0f}W) -> apertura sicurezza {safety_zone_name}",
                context=trigger_ctx,
                level=NOTIFY_LEVEL_WARNING,
            )
        elif (
            not self.manual_safety_active
            and self._was_manual_safety_active
            and not any_heating
        ):
            await self.async_record_action(
                entity_id=self.power_sensor,
                action_desc=f"fine sicurezza accensione manuale ({fmt_temp(self.current_power_watt)}W < {self.power_threshold_watt:g}W)",
                context=trigger_ctx,
            )
        self._was_manual_safety_active = self.manual_safety_active
