"""Coordinator for Smart Zone Heating (Exclusive Control + Dynamic Visibility + Unified SZH Logbook/Debug)."""
from __future__ import annotations

from datetime import datetime, time, timedelta
import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
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
    CONF_TARGET_TEMP,
    CONF_TEMP_AWAY,
    CONF_TEMP_DAY,
    CONF_TEMP_NIGHT,
    CONF_TEMP_SENSOR,
    CONF_USE_POWER_SENSOR,
    CONF_USE_SEPARATE_MANUAL_ZONE,
    CONF_VALVE_ENTITY,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_DAY_START_TIME,
    DEFAULT_HYSTERESIS,
    DEFAULT_NIGHT_START_TIME,
    DEFAULT_NOTIFY_LEVEL,
    DEFAULT_POWER_GRACE_SECONDS,
    DEFAULT_POWER_THRESHOLD_WATT,
    DEFAULT_TEMP_AWAY,
    DEFAULT_TEMP_DAY,
    DEFAULT_TEMP_NIGHT,
    DOMAIN,
    NOTIFY_LEVEL_DEBUG,
    NOTIFY_LEVEL_ERROR,
    NOTIFY_LEVEL_OFF,
    NOTIFY_LEVEL_WARNING,
    PRESET_AWAY,
    PRESET_DAY,
    PRESET_NIGHT,
    STATE_COOLDOWN_POWER,
    STATE_COOLDOWN_TIMER,
    STATE_DISABLED,
    STATE_HEATING,
    STATE_IDLE,
    STATE_MANUAL_SAFETY,
    STATE_PROBLEM,
)

_LOGGER = logging.getLogger(__name__)

LOGBOOK_NAME = "SZH Integration"
NOTIFY_PREFIX = "[SZH Integration]"

_LEVEL_PRIORITY = {
    NOTIFY_LEVEL_OFF: 0,
    NOTIFY_LEVEL_ERROR: 3,
    NOTIFY_LEVEL_WARNING: 2,
    NOTIFY_LEVEL_DEBUG: 1,
}

CONF_HYSTERESIS = "hysteresis"


def _parse_time(val: str | time | None, default_str: str) -> time:
    """Parse a time string HH:MM or HH:MM:SS into a datetime.time object."""
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        parsed = dt_util.parse_time(val)
        if parsed is not None:
            return parsed
    return dt_util.parse_time(default_str) or time(7, 0)


def _fmt_temp(val: float | None) -> str:
    """Format temperature cleanly (e.g. 18.5 or 22)."""
    if val is None:
        return "?"
    return f"{val:g}"


class ZoneRuntimeState:
    """Holds runtime state for a single heating zone."""

    def __init__(self, zone_cfg: dict[str, Any], initial_enabled: bool = True) -> None:
        self.zone_id: str = zone_cfg[CONF_ZONE_ID]
        self.name: str = zone_cfg[CONF_ZONE_NAME]
        self.valve_entity: str = zone_cfg[CONF_VALVE_ENTITY]
        self.temp_sensor: str = zone_cfg[CONF_TEMP_SENSOR]
        self.temp_day: float = float(
            zone_cfg.get(CONF_TEMP_DAY, zone_cfg.get(CONF_TARGET_TEMP, DEFAULT_TEMP_DAY))
        )
        self.temp_night: float = float(zone_cfg.get(CONF_TEMP_NIGHT, DEFAULT_TEMP_NIGHT))
        self.temp_away: float = float(zone_cfg.get(CONF_TEMP_AWAY, DEFAULT_TEMP_AWAY))
        self.preset_mode: str = PRESET_DAY
        self.target_temp: float = self.temp_day
        self.hvac_mode_enabled: bool = initial_enabled
        self.current_temp: float | None = None
        self.requesting_heat: bool = False
        self.forced_open_reason: str | None = None
        self.climate_entity_id: str | None = None

    def apply_preset(self, preset: str) -> None:
        """Apply preset mode and update target_temp accordingly."""
        self.preset_mode = preset
        if preset == PRESET_DAY:
            self.target_temp = self.temp_day
        elif preset == PRESET_NIGHT:
            self.target_temp = self.temp_night
        elif preset == PRESET_AWAY:
            self.target_temp = self.temp_away


class SmartZoneHeatingCoordinator:
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
        self.day_start_time: time = _parse_time(
            data.get(CONF_DAY_START_TIME), DEFAULT_DAY_START_TIME
        )
        self.night_start_time: time = _parse_time(
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
        self.cooldown_enabled: bool = bool(
            data.get(CONF_COOLDOWN_ENABLED, True)
        )
        self.cooldown_minutes: int = int(
            data.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
        )
        self.cooldown_zone_id: str | None = data.get(CONF_COOLDOWN_ZONE_ID) or first_zone_id
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
                data.get(CONF_MANUAL_SAFETY_ZONE_ID) or self.cooldown_zone_id or first_zone_id
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
        self.problem_binary_sensor_entity_id: str | None = None
        # Startup grace period so slow integrations (Tapo Wi-Fi, Zigbee, etc.) don't trigger false boot problems
        self._startup_grace_until: datetime | None = dt_util.utcnow() + timedelta(seconds=45)

        # Track last desired switch state for non-exclusive (edge-triggered) mode
        self._last_desired_switch_state: dict[str, bool] = {}
        # Track in-flight switch commands (entity_id -> (target_turn_on, sent_at_utc)) to avoid false Exclusive Control reverts on slow Wi-Fi switches
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
            sw_version="1.0.0",
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

    @callback
    def _set_entity_hidden_by_unique_id(self, unique_id: str, should_hide: bool) -> None:
        """Hide or unhide one of our own config entities by its unique_id."""
        ent_reg = er.async_get(self.hass)
        entity_id = ent_reg.async_get_entity_id("time", DOMAIN, unique_id) or ent_reg.async_get_entity_id(
            "select", DOMAIN, unique_id
        ) or ent_reg.async_get_entity_id("number", DOMAIN, unique_id)
        if not entity_id:
            return
        reg_entry = ent_reg.async_get(entity_id)
        if reg_entry is None:
            return
        if should_hide:
            if reg_entry.hidden_by is None:
                ent_reg.async_update_entity(
                    entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
                )
        else:
            if reg_entry.hidden_by == er.RegistryEntryHider.INTEGRATION:
                ent_reg.async_update_entity(entity_id, hidden_by=None)

    @callback
    def apply_dynamic_config_visibility(self) -> None:
        """Dynamically show/hide child configuration entities based on parent toggle states."""
        # 1. Day/Night start time entities: visible only when schedule_enabled is True
        hide_schedule_times = not self.schedule_enabled
        self._set_entity_hidden_by_unique_id(
            f"{self.entry.entry_id}_day_start_time", hide_schedule_times
        )
        self._set_entity_hidden_by_unique_id(
            f"{self.entry.entry_id}_night_start_time", hide_schedule_times
        )

        # 2. Notify Level selector: visible only when notify_service is selected (not None)
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
            if should_hide:
                if reg_entry.hidden_by is None:
                    ent_reg.async_update_entity(
                        entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
                    )
            else:
                if reg_entry.hidden_by == er.RegistryEntryHider.INTEGRATION:
                    ent_reg.async_update_entity(entity_id, hidden_by=None)

    def _fire_logbook_entry(
        self,
        entity_id: str | None,
        message: str,
        context: Context | None = None,
    ) -> Context:
        """Fire a Home Assistant logbook_entry event sharing the exact trigger Context so 'Cosa è successo' links the cause."""
        action_context = context if context is not None else Context()
        # Always include 'SZH Integration:' in message because HA hides 'name' when viewing a single entity's history
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
        detail = "switch fisici nascosti e bloccati" if enabled else "switch fisici visibili e sbloccati"
        await self.async_record_action(
            entity_id=entity_id,
            action_desc=f"-> {state_str}, {detail}",
            context=context,
        )
        await self.async_evaluate()

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
            is_day = now_time >= self.day_start_time or now_time < self.night_start_time
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

    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
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
        """Clean up listeners on unload."""
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
        return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    @callback
    def _async_on_state_change(self, event: Event) -> None:
        """Handle state changes of tracked sensors or switches."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if old_state is not None and new_state is not None and old_state.state == new_state.state:
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
    def _async_periodic_tick(self, now: datetime) -> None:
        """Periodic check to update Day/Night schedule transitions and cooldown timer."""
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

    async def async_evaluate(self) -> None:
        """Evaluate schedule, zones, power-driven cooldown + timer fallback, safety, and notifications."""
        if self._evaluating:
            self._eval_pending = True
            return
        self._evaluating = True
        try:
            await self._async_evaluate_inner()
            while self._eval_pending:
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
        if use_watt_for_cooldown and not power_sensor_available and not self._cooldown_fallback_warned:
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
        elif not self.manual_safety_active and self._was_manual_safety_active and not any_heating:
            await self.async_record_action(
                entity_id=self.power_sensor,
                action_desc=f"fine sicurezza accensione manuale ({_fmt_temp(self.current_power_watt)}W < {self.power_threshold_watt:g}W)",
                context=trigger_ctx,
            )
        self._was_manual_safety_active = self.manual_safety_active

    def _update_unavailability_tracking(
        self, unavailable: list[str], now: datetime
    ) -> tuple[list[str], list[str], Context | None]:
        """Track newly unavailable/restored entities respecting the post-boot startup grace."""
        current_unavail_set = set(unavailable)
        if not current_unavail_set and self._startup_grace_until is not None:
            self._startup_grace_until = None
            if self._unsub_startup_grace:
                self._unsub_startup_grace()
                self._unsub_startup_grace = None

        in_startup_grace = (
            not self.hass.is_running
            or (self._startup_grace_until is not None and now < self._startup_grace_until)
        )
        if in_startup_grace:
            self.unavailable_entities = []
            self.problem_detected = False
            return [], [], None

        newly_unavailable = sorted(current_unavail_set - self._prev_unavailable_set)
        newly_restored = sorted(self._prev_unavailable_set - current_unavail_set)
        self._prev_unavailable_set = current_unavail_set
        self.unavailable_entities = sorted(current_unavail_set)
        self.problem_detected = len(self.unavailable_entities) > 0

        cause_entity: str | None = None
        if newly_unavailable:
            cause_entity = newly_unavailable[0]
        elif newly_restored:
            cause_entity = newly_restored[0]
        cause_st = self.hass.states.get(cause_entity) if cause_entity else None
        return newly_unavailable, newly_restored, (cause_st.context if cause_st else None)

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
            w_val = f"{self.current_power_watt:.0f}W" if self.current_power_watt is not None else ""
            state_str = f"Accensione manuale: {saf_zone} ({w_val})"
        elif not self.master_enabled:
            state_str = STATE_DISABLED
        elif self.problem_detected:
            state_str = f"Problema: {prob_labels}"
        else:
            state_str = "Inattivo (Fuori Casa)" if self.global_away_mode else STATE_IDLE

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
        t_curr = _fmt_temp(zone.current_temp)
        t_targ = _fmt_temp(zone.target_temp)

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
                zone.forced_open_reason = f"smaltimento timer ({self.cooldown_remaining_minutes}m)"
            return True, zone.forced_open_reason

        if self.manual_safety_active and zone.zone_id == self.manual_safety_zone_id:
            zone.forced_open_reason = (
                f"sicurezza accensione manuale ({self.current_power_watt:.0f}W>={self.power_threshold_watt:g}W)"
            )
            return True, zone.forced_open_reason

        if not zone.hvac_mode_enabled:
            return False, f"Termostato {zone.name} off"
        if zone.current_temp is None:
            return False, f"sensore {zone.temp_sensor} indisponibile"
        return False, f"nessuna richiesta ({t_curr}>={t_targ})"

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

    def _resolve_zone_context(
        self,
        zone: ZoneRuntimeState,
        trigger_ctx: Context | None,
        eval_ctx: Context,
    ) -> Context:
        """Return the best causal Context for a zone valve command."""
        if trigger_ctx is not None:
            return trigger_ctx
        if zone.climate_entity_id and (clim_st := self.hass.states.get(zone.climate_entity_id)):
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
            if z.requesting_heat and z.climate_entity_id and (clim_st := self.hass.states.get(z.climate_entity_id)):
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

        self.system_state = self._compute_system_state_string(any_heating, cooldown_mode)
        valve_commands = self._build_zone_valve_commands(cooldown_mode)

        # Write Thermostat / System State / Problem BinarySensor entity rows with eval_ctx BEFORE firing logbook entries
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
                f"{z.name} {_fmt_temp(z.current_temp)}<{_fmt_temp(z.target_temp)}"
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
