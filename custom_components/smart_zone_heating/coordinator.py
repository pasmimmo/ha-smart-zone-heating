"""Core Coordinator for Smart Zone Heating orchestrating zones, schedule, safety, and switches."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COOLDOWN_ENABLED,
    CONF_COOLDOWN_MINUTES,
    CONF_COOLDOWN_ZONE_ID,
    CONF_DAY_START_TIME,
    CONF_EXCLUSIVE_CONTROL,
    CONF_HEATER_ENTITY,
    CONF_MANUAL_SAFETY_ENABLED,
    CONF_MANUAL_SAFETY_ZONE_ID,
    CONF_MASTER_ENABLED,
    CONF_NIGHT_START_TIME,
    CONF_NOTIFY_LEVEL,
    CONF_NOTIFY_SERVICE,
    CONF_POWER_GRACE_SECONDS,
    CONF_POWER_SENSOR,
    CONF_POWER_THRESHOLD_WATT,
    CONF_SCHEDULE_ENABLED,
    CONF_SYSTEM_NAME,
    CONF_TEMP_SENSOR,
    CONF_USE_POWER_SENSOR,
    CONF_USE_SEPARATE_MANUAL_ZONE,
    CONF_ZONE_ID,
    CONF_ZONES,
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_DAY_START_TIME,
    DEFAULT_HYSTERESIS,
    DEFAULT_NIGHT_START_TIME,
    DEFAULT_NOTIFY_LEVEL,
    DEFAULT_POWER_GRACE_SECONDS,
    DEFAULT_POWER_THRESHOLD_WATT,
    DOMAIN,
    PRESET_AWAY,
    PRESET_DAY,
    PRESET_NIGHT,
    STATE_DISABLED,
    STATE_IDLE,
)
from .models import (
    CONF_HYSTERESIS,
    LOGBOOK_NAME,
    NOTIFY_PREFIX,
    ZoneRuntimeState,
    fmt_temp,
    parse_time,
)
from .notifier import CoordinatorNotificationMixin
from .safety_manager import CoordinatorSafetyMixin
from .switch_controller import CoordinatorSwitchMixin

__all__ = [
    "CONF_HYSTERESIS",
    "LOGBOOK_NAME",
    "NOTIFY_PREFIX",
    "SmartZoneHeatingCoordinator",
    "ZoneRuntimeState",
]


class SmartZoneHeatingCoordinator(
    CoordinatorNotificationMixin,
    CoordinatorSwitchMixin,
    CoordinatorSafetyMixin,
):
    """Manages multi-zone valves, presets/schedule, heater switch, power/timer cooldown, and SZH logbook/debug."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._updating_from_entity: bool = False
        data = {**entry.data, **entry.options}

        self.system_name: str = data.get(CONF_SYSTEM_NAME, "Riscaldamento")
        self.heater_entity: str = data[CONF_HEATER_ENTITY]
        self.master_enabled: bool = bool(data.get(CONF_MASTER_ENABLED, True))
        self.exclusive_control: bool = bool(data.get(CONF_EXCLUSIVE_CONTROL, False))
        self.hysteresis: float = float(data.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS))
        self.system_state: str = STATE_IDLE

        # Schedule settings (Day / Night / Away)
        self.schedule_enabled: bool = bool(data.get(CONF_SCHEDULE_ENABLED, True))
        self.day_start_time: time = parse_time(
            data.get(CONF_DAY_START_TIME), DEFAULT_DAY_START_TIME
        )
        self.night_start_time: time = parse_time(
            data.get(CONF_NIGHT_START_TIME), DEFAULT_NIGHT_START_TIME
        )
        self.global_away_mode: bool = False
        self._last_scheduled_period: str | None = None

        self.zones: dict[str, ZoneRuntimeState] = {}
        for z_cfg in data.get(CONF_ZONES, []):
            z = ZoneRuntimeState(z_cfg, initial_enabled=self.master_enabled)
            self.zones[z.zone_id] = z

        first_zone_id = next(iter(self.zones), None)

        # Cooldown / heat dissipation settings (Power primary + Timer fallback)
        self.cooldown_enabled: bool = bool(data.get(CONF_COOLDOWN_ENABLED, True))
        self.cooldown_minutes: int = int(
            data.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
        )
        self.cooldown_zone_id: str | None = (
            data.get(CONF_COOLDOWN_ZONE_ID) or first_zone_id
        )
        self.in_cooldown: bool = False
        self.cooldown_started_at: datetime | None = None
        self.cooldown_until: datetime | None = None
        self._was_heating: bool = False
        self._cooldown_fallback_warned: bool = False

        # Power consumption / manual ignition safety settings
        self.power_sensor: str | None = data.get(CONF_POWER_SENSOR) or None
        self.use_power_sensor: bool = bool(
            data.get(CONF_USE_POWER_SENSOR, bool(self.power_sensor))
        )
        self.power_threshold_watt: float = float(
            data.get(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT)
        )
        self.power_grace_seconds: int = int(
            data.get(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS)
        )
        self.manual_safety_enabled: bool = bool(
            data.get(CONF_MANUAL_SAFETY_ENABLED, bool(self.power_sensor))
        )
        self.use_separate_manual_zone: bool = bool(
            data.get(CONF_USE_SEPARATE_MANUAL_ZONE, False)
        )
        if self.use_separate_manual_zone:
            self.manual_safety_zone_id: str | None = (
                data.get(CONF_MANUAL_SAFETY_ZONE_ID)
                or self.cooldown_zone_id
                or first_zone_id
            )
        else:
            self.manual_safety_zone_id = self.cooldown_zone_id or first_zone_id

        self.current_power_watt: float | None = None
        self.manual_safety_active: bool = False
        self._was_manual_safety_active: bool = False

        # Notification settings
        self.notify_service: str | None = data.get(CONF_NOTIFY_SERVICE) or None
        if self.notify_service == "none":
            self.notify_service = None
        self.notify_level: str = data.get(CONF_NOTIFY_LEVEL, DEFAULT_NOTIFY_LEVEL)

        # Problem / unavailability tracking
        self.unavailable_entities: list[str] = []
        self.problem_detected: bool = False
        self._prev_unavailable_set: set[str] = set()
        self._unavail_first_seen: dict[str, datetime] = {}
        self._unavail_cause_contexts: dict[str, Context] = {}
        self.problem_binary_sensor_entity_id: str | None = None
        self._startup_grace_until: datetime | None = dt_util.utcnow() + timedelta(
            seconds=45
        )
        self._is_stopping: bool = False

        # Switch command tracking
        self._last_desired_switch_state: dict[str, bool] = {}
        self._pending_switch_cmd: dict[str, tuple[bool, datetime]] = {}

        # Context tracking for Home Assistant Logbook attribution
        self._last_trigger_context: Context | None = None
        self._last_trigger_entity_id: str | None = None
        self.current_eval_context: Context | None = None

        self._listeners: list[Callable[[], None]] = []
        self._unsub_state_listener: Callable[[], None] | None = None
        self._unsub_cooldown_timer: Callable[[], None] | None = None
        self._unsub_grace_timer: Callable[[], None] | None = None
        self._unsub_startup_grace: Callable[[], None] | None = None
        self._unsub_unavail_confirm: Callable[[], None] | None = None
        self._unsub_periodic_tick: Callable[[], None] | None = None
        self._evaluating: bool = False
        self._eval_pending: bool = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return DeviceInfo so all entities are grouped under a single Device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.system_name,
            manufacturer="Smart Zone Heating",
            model="Multi-Zone Heating Controller",
            sw_version="1.0.1",
        )

    @callback
    def persist_config_option(self, key: str, value: Any) -> None:
        """Persist a configuration option into entry.data / entry.options without triggering a full reload."""
        self._updating_from_entity = True
        try:
            new_data = {**self.entry.data, key: value}
            new_options = {**self.entry.options}
            if key in new_options:
                new_options[key] = value
            self.hass.config_entries.async_update_entry(
                self.entry, data=new_data, options=new_options
            )
        finally:
            self._updating_from_entity = False

    async def async_set_master_enabled(
        self, enabled: bool, entity_id: str | None = None, context: Context | None = None
    ) -> None:
        """Turn all zone thermostats ON (HEAT) or OFF via the master switch."""
        self.master_enabled = enabled
        self.persist_config_option(CONF_MASTER_ENABLED, enabled)
        self._last_trigger_context = context
        for zone in self.zones.values():
            zone.hvac_mode_enabled = enabled
        self.current_eval_context = context
        self._notify_listeners()
        self.current_eval_context = None

        state_str = "on" if enabled else "off"
        hvac_str = "heat" if enabled else "off"
        await self.async_record_action(
            entity_id=entity_id,
            action_desc=f"-> {state_str}, tutti i termostati -> {hvac_str}",
            context=context,
        )
        await self.async_evaluate()

    def get_current_schedule_preset(self) -> str:
        """Return PRESET_DAY or PRESET_NIGHT based on current local time."""
        now_time = dt_util.now().time()
        if self.day_start_time <= self.night_start_time:
            is_day = self.day_start_time <= now_time < self.night_start_time
        else:
            is_day = (
                now_time >= self.day_start_time or now_time < self.night_start_time
            )
        return PRESET_DAY if is_day else PRESET_NIGHT

    def get_zone_id_by_name(self, zone_name: str) -> str | None:
        """Find a zone_id from its friendly name."""
        for z_id, zone in self.zones.items():
            if zone.name == zone_name:
                return z_id
        return None

    def get_zone_name(self, zone_id: str | None) -> str | None:
        """Return friendly name for a zone_id."""
        if zone_id and zone_id in self.zones:
            return self.zones[zone_id].name
        return None

    def async_add_listener(
        self, update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Register an entity callback to be notified on updates."""
        self._listeners.append(update_callback)

        def _remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _remove

    @callback
    def _notify_listeners(self) -> None:
        for listener in self._listeners.copy():
            listener()

    @callback
    def start_post_boot_grace(self, seconds: int = 30) -> None:
        """Start or refresh the post-boot grace timer so slow integrations can finish initializing."""
        if self._unsub_startup_grace:
            self._unsub_startup_grace()
            self._unsub_startup_grace = None
        if self._startup_grace_until is None:
            return
        self._startup_grace_until = dt_util.utcnow() + timedelta(seconds=seconds)

        @callback
        def _on_startup_grace_expired(_now: datetime) -> None:
            self._unsub_startup_grace = None
            self._startup_grace_until = None
            self.hass.async_create_task(self.async_evaluate())

        self._unsub_startup_grace = async_call_later(
            self.hass, seconds, _on_startup_grace_expired
        )

    async def async_start(self) -> None:
        """Start tracking entities, apply exclusive control visibility, and evaluate initial state."""
        self.apply_exclusive_control_visibility()
        self._resubscribe_listeners()
        self.start_post_boot_grace(30)
        self._unsub_periodic_tick = async_track_time_interval(
            self.hass,
            self._async_periodic_tick,
            timedelta(seconds=30),
        )
        await self.async_evaluate()

    @callback
    def _resubscribe_listeners(self) -> None:
        """Subscribe to state changes of configured temperature sensors, power sensor, and switches."""
        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None

        tracked_entities: set[str] = {self.heater_entity}
        if self.power_sensor:
            tracked_entities.add(self.power_sensor)
        for zone in self.zones.values():
            tracked_entities.add(zone.valve_entity)
            if zone.temp_sensor:
                tracked_entities.add(zone.temp_sensor)

        self._unsub_state_listener = async_track_state_change_event(
            self.hass,
            tracked_entities,
            self._async_on_state_change,
        )

    async def async_stop(self) -> None:  # NOSONAR
        """Clean up listeners on unload or Home Assistant stop."""
        self._is_stopping = True
        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None
        if self._unsub_cooldown_timer:
            self._unsub_cooldown_timer()
            self._unsub_cooldown_timer = None
        if self._unsub_grace_timer:
            self._unsub_grace_timer()
            self._unsub_grace_timer = None
        if self._unsub_startup_grace:
            self._unsub_startup_grace()
            self._unsub_startup_grace = None
        if self._unsub_unavail_confirm:
            self._unsub_unavail_confirm()
            self._unsub_unavail_confirm = None
        if self._unsub_periodic_tick:
            self._unsub_periodic_tick()
            self._unsub_periodic_tick = None

    def _read_sensor_float(self, entity_id: str | None) -> tuple[float | None, bool]:
        """Read float value from sensor/input_number. Returns (value, is_available)."""
        if not entity_id:
            return None, True
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None, False
        try:
            return float(state.state), True
        except (ValueError, TypeError):
            return None, False

    def _is_entity_available(self, entity_id: str | None) -> bool:
        """Check if a switch/sensor entity exists and is not unavailable."""
        if not entity_id:
            return True
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )

    @callback
    def _async_on_state_change(self, event: Event) -> None:
        """Handle state changes of tracked sensors or switches."""
        if self._is_stopping or self.hass.is_stopping:
            return
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if (
            old_state is not None
            and new_state is not None
            and old_state.state == new_state.state
        ):
            return

        entity_id = event.data.get("entity_id")
        managed_switches = {self.heater_entity} | {
            z.valve_entity for z in self.zones.values()
        }

        if entity_id in managed_switches and not self.exclusive_control:
            was_avail = old_state is not None and old_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            )
            now_avail = new_state is not None and new_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            )
            if was_avail == now_avail:
                return

        self._last_trigger_context = event.context
        self._last_trigger_entity_id = entity_id
        self.hass.async_create_task(self.async_evaluate())

    @callback
    def _async_periodic_tick(self, _now: datetime) -> None:
        """Periodic check to update Day/Night schedule transitions and cooldown timer."""
        if self._is_stopping or self.hass.is_stopping:
            return
        self.hass.async_create_task(self.async_evaluate())

    async def async_set_zone_temp_sensor(
        self,
        zone_id: str,
        sensor_entity_id: str,
        select_entity_id: str | None = None,
        context: Context | None = None,
    ) -> None:
        """Change the active temperature sensor for a zone on the fly."""
        zone = self.zones.get(zone_id)
        if not zone:
            return
        old_sensor = zone.temp_sensor
        zone.temp_sensor = sensor_entity_id
        zones_cfg = [dict(z) for z in self.entry.data.get(CONF_ZONES, [])]
        for z_dict in zones_cfg:
            if z_dict.get(CONF_ZONE_ID) == zone_id:
                z_dict[CONF_TEMP_SENSOR] = sensor_entity_id
        self.persist_config_option(CONF_ZONES, zones_cfg)
        self._last_trigger_context = context
        self._resubscribe_listeners()
        self.current_eval_context = context
        self._notify_listeners()
        self.current_eval_context = None
        await self.async_record_action(
            entity_id=select_entity_id,
            action_desc=f"-> {sensor_entity_id} (zona {zone.name}, prec: {old_sensor})",
            context=context,
        )
        await self.async_evaluate()

    async def async_set_global_away(
        self, away: bool, entity_id: str | None = None, context: Context | None = None
    ) -> None:
        """Set or clear Away mode across all zones."""
        self.global_away_mode = away
        self._last_trigger_context = context
        target_preset = PRESET_AWAY if away else self.get_current_schedule_preset()
        for zone in self.zones.values():
            zone.apply_preset(target_preset)
        self.current_eval_context = context
        self._notify_listeners()
        self.current_eval_context = None
        state_str = "on" if away else "off"
        await self.async_record_action(
            entity_id=entity_id,
            action_desc=f"-> {state_str}, preset tutte le zone -> {target_preset}",
            context=context,
        )
        await self.async_evaluate()

    async def async_evaluate(self) -> None:
        """Evaluate schedule, zones, power-driven cooldown + timer fallback, safety, and notifications."""
        if self._is_stopping or self.hass.is_stopping:
            return
        if self._evaluating:
            self._eval_pending = True
            return
        self._evaluating = True
        try:
            await self._async_evaluate_inner()
            while self._eval_pending and not self._is_stopping and not self.hass.is_stopping:
                self._eval_pending = False
                await self._async_evaluate_inner()
        finally:
            self._evaluating = False

    def _sync_master_and_away_flags(self) -> None:
        """Synchronize master_enabled, global_away_mode, and manual_safety_zone_id."""
        if self.zones:
            self.master_enabled = any(z.hvac_mode_enabled for z in self.zones.values())
            if all(z.preset_mode == PRESET_AWAY for z in self.zones.values()):
                self.global_away_mode = True
            elif any(z.preset_mode != PRESET_AWAY for z in self.zones.values()):
                self.global_away_mode = False

        if not self.use_separate_manual_zone:
            self.manual_safety_zone_id = self.cooldown_zone_id

    async def _async_check_schedule_transition(self, eval_ctx: Context) -> None:
        """Apply Day/Night preset transition when schedule_enabled is active."""
        current_period = self.get_current_schedule_preset()
        if not self.schedule_enabled or current_period == self._last_scheduled_period:
            return
        prev_period = self._last_scheduled_period
        self._last_scheduled_period = current_period
        for zone in self.zones.values():
            if zone.preset_mode != PRESET_AWAY and not self.global_away_mode:
                zone.apply_preset(current_period)
        if prev_period is not None:
            self.current_eval_context = eval_ctx
            self._notify_listeners()
            self.current_eval_context = None
            await self.async_record_action(
                entity_id=None,
                action_desc=f"fascia oraria -> {current_period}",
                context=eval_ctx,
            )

    def _check_heater_and_power(self, unavailable: list[str]) -> tuple[bool, bool]:
        """Check heater switch and optional power sensor availability."""
        if not self._is_entity_available(self.heater_entity):
            unavailable.append(self.heater_entity)

        power_sensor_configured = bool(self.power_sensor)
        if not power_sensor_configured:
            self.current_power_watt = None
            return False, False

        power_val, power_ok = self._read_sensor_float(self.power_sensor)
        self.current_power_watt = power_val
        if not power_ok and self.power_sensor:
            unavailable.append(self.power_sensor)
        return True, power_ok

    def _evaluate_zone_heat_requests(self, unavailable: list[str]) -> bool:
        """Update current_temp and hysteresis heat request for all zones."""
        any_heating = False
        for zone in self.zones.values():
            if not self._is_entity_available(zone.valve_entity):
                unavailable.append(zone.valve_entity)

            temp_val, temp_ok = self._read_sensor_float(zone.temp_sensor)
            zone.current_temp = temp_val
            if not temp_ok:
                unavailable.append(zone.temp_sensor)

            zone.forced_open_reason = None
            self._update_single_zone_request(zone)
            if zone.requesting_heat:
                any_heating = True
        return any_heating

    def _update_single_zone_request(self, zone: ZoneRuntimeState) -> None:
        """Apply hysteresis threshold to a single zone's heat request."""
        if not zone.hvac_mode_enabled or zone.current_temp is None:
            zone.requesting_heat = False
            return
        if zone.requesting_heat:
            if zone.current_temp >= zone.target_temp + self.hysteresis:
                zone.requesting_heat = False
        elif zone.current_temp <= zone.target_temp - self.hysteresis:
            zone.requesting_heat = True

    @callback
    def _schedule_unavail_confirm(self, delay: float = 5.5) -> None:
        """Schedule a re-evaluation after the unavailability confirmation window."""
        if self._unsub_unavail_confirm or self._is_stopping or self.hass.is_stopping:
            return

        @callback
        def _on_confirm(_now: datetime) -> None:
            self._unsub_unavail_confirm = None
            if not self._is_stopping and not self.hass.is_stopping:
                self.hass.async_create_task(self.async_evaluate())

        self._unsub_unavail_confirm = async_call_later(self.hass, delay, _on_confirm)

    def _record_first_seen_unavailable(
        self, current_unavail_set: set[str], now: datetime
    ) -> None:
        """Track first-seen timestamp and original Context for unavailable entities."""
        for eid in list(self._unavail_first_seen):
            if eid not in current_unavail_set:
                self._unavail_first_seen.pop(eid, None)
                self._unavail_cause_contexts.pop(eid, None)
        for eid in current_unavail_set:
            if eid not in self._unavail_first_seen:
                self._unavail_first_seen[eid] = now
                if st := self.hass.states.get(eid):
                    self._unavail_cause_contexts[eid] = st.context

    def _filter_confirmed_unavailable(
        self, current_unavail_set: set[str], now: datetime
    ) -> set[str]:
        """Return entities unavailable for at least 5s so shutdown/reboot teardown does not trigger false alerts."""
        self._record_first_seen_unavailable(current_unavail_set, now)
        confirmed = {
            eid
            for eid in current_unavail_set
            if eid in self._prev_unavailable_set
            or (now - self._unavail_first_seen[eid]) >= timedelta(seconds=5)
        }
        if len(confirmed) < len(current_unavail_set):
            self._schedule_unavail_confirm(5.5)
        return confirmed

    def _resolve_problem_cause_context(
        self, newly_unavailable: list[str], newly_restored: list[str]
    ) -> Context | None:
        """Return the Context of the entity that caused the problem state transition."""
        if newly_unavailable:
            eid = newly_unavailable[0]
            if ctx := self._unavail_cause_contexts.get(eid):
                return ctx
            st = self.hass.states.get(eid)
            return st.context if st else None
        if newly_restored:
            st = self.hass.states.get(newly_restored[0])
            return st.context if st else None
        return None

    def _update_unavailability_tracking(
        self, unavailable: list[str], now: datetime
    ) -> tuple[list[str], list[str], Context | None]:
        """Track newly unavailable/restored entities respecting startup grace and shutdown suppression."""
        if self._is_stopping or self.hass.is_stopping:
            return [], [], None

        current_unavail_set = set(unavailable)
        if not current_unavail_set and self._startup_grace_until is not None:
            self._startup_grace_until = None
            if self._unsub_startup_grace:
                self._unsub_startup_grace()
                self._unsub_startup_grace = None

        in_startup_grace = not self.hass.is_running or (
            self._startup_grace_until is not None and now < self._startup_grace_until
        )
        if in_startup_grace:
            self.unavailable_entities = []
            self.problem_detected = False
            return [], [], None

        confirmed_unavail_set = self._filter_confirmed_unavailable(
            current_unavail_set, now
        )
        newly_unavailable = sorted(confirmed_unavail_set - self._prev_unavailable_set)
        newly_restored = sorted(self._prev_unavailable_set - current_unavail_set)
        self._prev_unavailable_set = confirmed_unavail_set
        self.unavailable_entities = sorted(confirmed_unavail_set)
        self.problem_detected = len(self.unavailable_entities) > 0

        return (
            newly_unavailable,
            newly_restored,
            self._resolve_problem_cause_context(newly_unavailable, newly_restored),
        )

    def _format_cooldown_state(self, cooldown_mode: str) -> str:
        """Format Stato Sistema string for power or timer cooldown."""
        cd_zone = self.get_zone_name(self.cooldown_zone_id) or ""
        if cooldown_mode == "power":
            detail = (
                f"{self.current_power_watt:.0f}W"
                if self.current_power_watt is not None
                else "attesa W"
            )
        else:
            detail = f"{self.cooldown_remaining_minutes} min"
        return f"Smaltimento: {cd_zone} ({detail})"

    def _compute_system_state_string(
        self, any_heating: bool, cooldown_mode: str | None
    ) -> str:
        """Build expressive Stato Sistema text including active zone or problem names."""
        prob_labels = ", ".join(
            self.friendly_entity_label(eid) for eid in self.unavailable_entities
        )
        if any_heating:
            heating_names = ", ".join(
                z.name for z in self.zones.values() if z.requesting_heat
            )
            state_str = f"Riscaldamento: {heating_names}"
            if self.problem_detected:
                state_str = f"{state_str} (⚠️ Problema: {prob_labels})"
        elif cooldown_mode in ("power", "timer"):
            state_str = self._format_cooldown_state(cooldown_mode)
        elif self.manual_safety_active:
            saf_zone = self.get_zone_name(self.manual_safety_zone_id) or ""
            w_val = (
                f"{self.current_power_watt:.0f}W"
                if self.current_power_watt is not None
                else ""
            )
            state_str = f"Accensione manuale: {saf_zone} ({w_val})"
        elif not self.master_enabled:
            state_str = STATE_DISABLED
        elif self.problem_detected:
            state_str = f"Problema: {prob_labels}"
        else:
            state_str = (
                "Inattivo (Fuori Casa)" if self.global_away_mode else STATE_IDLE
            )

        return state_str[:247] + "..." if len(state_str) > 250 else state_str

    def _build_zone_valve_commands(
        self, cooldown_mode: str | None
    ) -> list[tuple[ZoneRuntimeState, bool, str]]:
        """Determine target valve state and reason for each zone."""
        valve_commands: list[tuple[ZoneRuntimeState, bool, str]] = []
        for zone in self.zones.values():
            should_open, reason = self._resolve_single_zone_valve(zone, cooldown_mode)
            valve_commands.append((zone, should_open, reason))
        return valve_commands

    def _resolve_single_zone_valve(
        self, zone: ZoneRuntimeState, cooldown_mode: str | None
    ) -> tuple[bool, str]:
        """Compute (should_open_valve, valve_reason) and update zone.forced_open_reason."""
        t_curr = fmt_temp(zone.current_temp)
        t_targ = fmt_temp(zone.target_temp)

        if zone.requesting_heat:
            return True, f"Termostato {zone.name} {t_curr}<{t_targ}"

        if cooldown_mode is not None and zone.zone_id == self.cooldown_zone_id:
            if cooldown_mode == "power":
                w_str = (
                    f"{self.current_power_watt:.0f}W>={self.power_threshold_watt:g}W"
                    if self.current_power_watt is not None
                    else "attesa potenza"
                )
                zone.forced_open_reason = f"smaltimento calore ({w_str})"
            else:
                zone.forced_open_reason = (
                    f"smaltimento timer ({self.cooldown_remaining_minutes}m)"
                )
            return True, zone.forced_open_reason

        if self.manual_safety_active and zone.zone_id == self.manual_safety_zone_id:
            zone.forced_open_reason = f"sicurezza accensione manuale ({self.current_power_watt:.0f}W>={self.power_threshold_watt:g}W)"
            return True, zone.forced_open_reason

        if not zone.hvac_mode_enabled:
            return False, f"Termostato {zone.name} off"
        if zone.current_temp is None:
            return False, f"sensore {zone.temp_sensor} indisponibile"
        return False, f"nessuna richiesta ({t_curr}>={t_targ})"

    def _resolve_zone_context(
        self,
        zone: ZoneRuntimeState,
        trigger_ctx: Context | None,
        eval_ctx: Context,
    ) -> Context:
        """Return the best causal Context for a zone valve command."""
        if trigger_ctx is not None:
            return trigger_ctx
        if zone.climate_entity_id and (
            clim_st := self.hass.states.get(zone.climate_entity_id)
        ):
            return clim_st.context
        if zone.temp_sensor and (temp_st := self.hass.states.get(zone.temp_sensor)):
            return temp_st.context
        return eval_ctx

    def _resolve_heater_context(
        self, trigger_ctx: Context | None, eval_ctx: Context
    ) -> Context:
        """Return the best causal Context for the main heater switch command."""
        if trigger_ctx is not None:
            return trigger_ctx
        for z in self.zones.values():
            if (
                z.requesting_heat
                and z.climate_entity_id
                and (clim_st := self.hass.states.get(z.climate_entity_id))
            ):
                return clim_st.context
        return eval_ctx

    async def _async_evaluate_inner(self) -> None:
        """Inner evaluation routine protected against re-entrancy."""
        unavailable: list[str] = []
        trigger_ctx = self._last_trigger_context
        self._last_trigger_context = None
        eval_ctx = trigger_ctx if trigger_ctx is not None else Context()

        self._sync_master_and_away_flags()
        await self._async_check_schedule_transition(eval_ctx)
        self._sync_master_and_away_flags()

        power_sensor_configured, power_sensor_available = self._check_heater_and_power(
            unavailable
        )
        any_heating = self._evaluate_zone_heat_requests(unavailable)

        now = dt_util.utcnow()
        use_watt_for_cooldown = self.use_power_sensor and power_sensor_configured
        cooldown_mode = await self._async_evaluate_cooldown(
            any_heating, use_watt_for_cooldown, power_sensor_available, now, trigger_ctx
        )

        await self._async_evaluate_manual_safety(
            any_heating,
            cooldown_mode,
            power_sensor_configured,
            power_sensor_available,
            trigger_ctx,
        )

        newly_unavailable, newly_restored, problem_cause_ctx = (
            self._update_unavailability_tracking(unavailable, now)
        )
        if problem_cause_ctx is not None:
            eval_ctx = problem_cause_ctx

        self.system_state = self._compute_system_state_string(
            any_heating, cooldown_mode
        )
        valve_commands = self._build_zone_valve_commands(cooldown_mode)

        self.current_eval_context = eval_ctx
        self._notify_listeners()
        self.current_eval_context = None

        await self._async_emit_problem_logbook_entries(
            newly_unavailable, newly_restored, eval_ctx
        )

        for zone, should_open_valve, valve_reason in valve_commands:
            await self._async_command_switch(
                entity_id=zone.valve_entity,
                turn_on=should_open_valve,
                reason=valve_reason,
                trigger_context=self._resolve_zone_context(zone, trigger_ctx, eval_ctx),
            )

        if any_heating:
            active_zones_str = ", ".join(
                f"{z.name} {fmt_temp(z.current_temp)}<{fmt_temp(z.target_temp)}"
                for z in self.zones.values()
                if z.requesting_heat
            )
            heater_reason = f"richiesta calore ({active_zones_str})"
        else:
            heater_reason = "nessuna richiesta"

        await self._async_command_switch(
            entity_id=self.heater_entity,
            turn_on=any_heating,
            reason=heater_reason,
            trigger_context=self._resolve_heater_context(trigger_ctx, eval_ctx),
        )
