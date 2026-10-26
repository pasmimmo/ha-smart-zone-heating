"""Coordinator for Smart Zone Heating (Power-driven Cooldown + Timer Fallback + Notifications)."""
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
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COOLDOWN_MINUTES,
    CONF_COOLDOWN_ZONE_ID,
    CONF_DAY_START_TIME,
    CONF_HEATER_ENTITY,
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

_LEVEL_PRIORITY = {
    NOTIFY_LEVEL_OFF: 0,
    NOTIFY_LEVEL_ERROR: 3,
    NOTIFY_LEVEL_WARNING: 2,
    NOTIFY_LEVEL_DEBUG: 1,
}


def _parse_time(val: str | time | None, default_str: str) -> time:
    """Parse a time string HH:MM or HH:MM:SS into a datetime.time object."""
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        parsed = dt_util.parse_time(val)
        if parsed is not None:
            return parsed
    return dt_util.parse_time(default_str) or time(7, 0)


class ZoneRuntimeState:
    """Holds runtime state for a single heating zone."""

    def __init__(self, zone_cfg: dict[str, Any]) -> None:
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
        self.hvac_mode_enabled: bool = True
        self.current_temp: float | None = None
        self.requesting_heat: bool = False
        self.forced_open_reason: str | None = None

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
    """Manages multi-zone valves, presets/schedule, heater switch, power/timer cooldown, and notifications."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        data = {**entry.data, **entry.options}

        self.system_name: str = data.get(CONF_SYSTEM_NAME, "Riscaldamento")
        self.heater_entity: str = data[CONF_HEATER_ENTITY]
        self.master_enabled: bool = bool(data.get(CONF_MASTER_ENABLED, True))
        self.hysteresis: float = DEFAULT_HYSTERESIS
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
            z = ZoneRuntimeState(z_cfg)
            self.zones[z.zone_id] = z

        first_zone_id = next(iter(self.zones), None)

        # Cooldown / heat dissipation settings (Power primary + Timer fallback)
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
        self.power_threshold_watt: float = float(
            data.get(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT)
        )
        self.power_grace_seconds: int = int(
            data.get(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS)
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

        self._listeners: list[Callable[[], None]] = []
        self._unsub_state_listener: Callable[[], None] | None = None
        self._unsub_cooldown_timer: Callable[[], None] | None = None
        self._unsub_grace_timer: Callable[[], None] | None = None
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
            sw_version="0.9.0",
        )

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
        _LOGGER.debug("[%s][%s] %s", self.system_name, event_level.upper(), message)
        if not self._should_notify(event_level):
            return

        prefix = {
            NOTIFY_LEVEL_ERROR: "🚨 [ERRORE]",
            NOTIFY_LEVEL_WARNING: "⚠️ [WARNING]",
            NOTIFY_LEVEL_DEBUG: "ℹ️ [DEBUG]",
        }.get(event_level, "")
        title = f"{prefix} {self.system_name}".strip()

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
                    {"title": title, "message": message},
                    blocking=False,
                )
            else:
                await self.hass.services.async_call(
                    domain,
                    service_name,
                    {"title": title, "message": message},
                    blocking=False,
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Impossibile inviare notifica su %s: %s", svc, err)

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
        for listener in list(self._listeners):
            listener()

    async def async_start(self) -> None:
        """Start tracking entities and evaluate initial state."""
        self._resubscribe_listeners()
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
            list(tracked_entities),
            self._async_on_state_change,
        )

    async def async_stop(self) -> None:
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
        if self._evaluating:
            return
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if old_state is not None and new_state is not None and old_state.state == new_state.state:
            return
        self.hass.async_create_task(self.async_evaluate())

    @callback
    def _async_periodic_tick(self, now: datetime) -> None:
        """Periodic check to update Day/Night schedule transitions and cooldown timer."""
        self.hass.async_create_task(self.async_evaluate())

    async def async_set_zone_temp_sensor(self, zone_id: str, sensor_entity_id: str) -> None:
        """Change the active temperature sensor for a zone on the fly."""
        zone = self.zones.get(zone_id)
        if not zone:
            return
        zone.temp_sensor = sensor_entity_id
        self._resubscribe_listeners()
        await self.async_evaluate()

    async def async_set_global_away(self, away: bool) -> None:
        """Set or clear Away mode across all zones."""
        self.global_away_mode = away
        target_preset = PRESET_AWAY if away else self.get_current_schedule_preset()
        for zone in self.zones.values():
            zone.apply_preset(target_preset)
        await self._async_notify(
            NOTIFY_LEVEL_DEBUG,
            f"Modalità Fuori Casa {'attivata' if away else 'disattivata'} su tutte le zone.",
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

        # Also schedule an evaluation after power_grace_seconds
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

    async def _async_evaluate_inner(self) -> None:
        """Inner evaluation routine protected against re-entrancy."""
        unavailable: list[str] = []

        # 0. Check Day / Night time transition if schedule_enabled is True
        current_period = self.get_current_schedule_preset()
        if self.schedule_enabled and current_period != self._last_scheduled_period:
            prev_period = self._last_scheduled_period
            self._last_scheduled_period = current_period
            for zone in self.zones.values():
                if zone.preset_mode != PRESET_AWAY and not self.global_away_mode:
                    zone.apply_preset(current_period)
            if prev_period is not None:
                label = "Giorno" if current_period == PRESET_DAY else "Notte"
                await self._async_notify(
                    NOTIFY_LEVEL_DEBUG,
                    f"Cambio fascia oraria automatico: attivata modalità {label}.",
                )

        # Keep global_away_mode synced with zones
        if all(z.preset_mode == PRESET_AWAY for z in self.zones.values()) and self.zones:
            self.global_away_mode = True
        elif any(z.preset_mode != PRESET_AWAY for z in self.zones.values()):
            self.global_away_mode = False

        # Keep manual_safety_zone_id synced with cooldown_zone_id when use_separate_manual_zone is False
        if not self.use_separate_manual_zone:
            self.manual_safety_zone_id = self.cooldown_zone_id

        # 1. Check Heater switch availability
        if not self._is_entity_available(self.heater_entity):
            unavailable.append(self.heater_entity)

        # 2. Check Power sensor if configured
        power_sensor_configured = bool(self.power_sensor)
        power_sensor_available = False
        if power_sensor_configured:
            power_val, power_ok = self._read_sensor_float(self.power_sensor)
            self.current_power_watt = power_val
            power_sensor_available = power_ok
            if not power_ok:
                unavailable.append(self.power_sensor)  # type: ignore[arg-type]
        else:
            self.current_power_watt = None

        # 3. Evaluate each zone's heat request
        any_heating = False
        for zone in self.zones.values():
            if not self._is_entity_available(zone.valve_entity):
                unavailable.append(zone.valve_entity)

            temp_val, temp_ok = self._read_sensor_float(zone.temp_sensor)
            zone.current_temp = temp_val
            if not temp_ok:
                unavailable.append(zone.temp_sensor)

            zone.forced_open_reason = None

            if not self.master_enabled or not zone.hvac_mode_enabled:
                zone.requesting_heat = False
            elif zone.current_temp is None:
                # Fail-safe: stop requesting heat if temperature sensor is unavailable
                zone.requesting_heat = False
            else:
                if zone.requesting_heat:
                    if zone.current_temp >= zone.target_temp + self.hysteresis:
                        zone.requesting_heat = False
                else:
                    if zone.current_temp <= zone.target_temp - self.hysteresis:
                        zone.requesting_heat = True

            if zone.requesting_heat:
                any_heating = True

        # 4. Manage Cooldown (Smaltimento calore: Watt-driven primary, Timer fallback)
        now = dt_util.utcnow()
        cooldown_mode: str | None = None

        if any_heating:
            if not self._was_heating:
                active_names = ", ".join(
                    z.name for z in self.zones.values() if z.requesting_heat
                )
                await self._async_notify(
                    NOTIFY_LEVEL_DEBUG,
                    f"Richiesta calore da [{active_names}]: accensione generatore ({self.heater_entity}).",
                )
            self._was_heating = True
            if self.in_cooldown:
                self._cancel_cooldown()
        else:
            if self._was_heating:
                self._was_heating = False
                self._start_cooldown()
                cooldown_zone_name = self.get_zone_name(self.cooldown_zone_id) or ""
                await self._async_notify(
                    NOTIFY_LEVEL_DEBUG,
                    f"Tutte le zone in temperatura: spegnimento generatore e avvio smaltimento calore su {cooldown_zone_name}.",
                )

            if self.in_cooldown and self.cooldown_zone_id in self.zones:
                if power_sensor_configured and power_sensor_available:
                    # Primary mode: Power sensor (Watts) decides when cooldown ends!
                    in_initial_grace = (
                        self.cooldown_started_at is not None
                        and (now - self.cooldown_started_at).total_seconds()
                        < max(5, self.power_grace_seconds)
                    )
                    if (
                        self.current_power_watt is not None
                        and self.current_power_watt >= self.power_threshold_watt
                    ) or in_initial_grace:
                        cooldown_mode = "power"
                    else:
                        # Power dropped below threshold -> cooldown finished!
                        self._cancel_cooldown()
                        await self._async_notify(
                            NOTIFY_LEVEL_DEBUG,
                            f"Smaltimento calore completato: consumo sceso sotto soglia ({self.current_power_watt:.0f}W < {self.power_threshold_watt:.0f}W). Chiusura valvola.",
                        )
                else:
                    # Fallback mode: Power sensor not configured OR unavailable -> use Timer!
                    if (
                        power_sensor_configured
                        and not power_sensor_available
                        and not self._cooldown_fallback_warned
                    ):
                        self._cooldown_fallback_warned = True
                        await self._async_notify(
                            NOTIFY_LEVEL_WARNING,
                            f"Sensore consumi ({self.power_sensor}) indisponibile durante lo smaltimento calore: attivato timer di fallback ({self.cooldown_minutes} min).",
                        )

                    if self.cooldown_until is not None and now < self.cooldown_until:
                        cooldown_mode = "timer"
                    else:
                        self._cancel_cooldown()
                        await self._async_notify(
                            NOTIFY_LEVEL_DEBUG,
                            "Smaltimento calore completato (fine timer di fallback). Chiusura valvola.",
                        )

        # 5. Evaluate Manual Ignition Safety (> threshold W when not heating and not in cooldown)
        power_above_threshold = (
            power_sensor_available
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
            await self._async_notify(
                NOTIFY_LEVEL_WARNING,
                f"Rilevato assorbimento ({self.current_power_watt:.0f}W >= {self.power_threshold_watt:.0f}W) a impianto spento (accensione manuale): aperta valvola di sicurezza {safety_zone_name}.",
            )
        elif not self.manual_safety_active and self._was_manual_safety_active and not any_heating:
            await self._async_notify(
                NOTIFY_LEVEL_DEBUG,
                "Fine sicurezza accensione manuale: consumo tornato sotto soglia.",
            )
        self._was_manual_safety_active = self.manual_safety_active

        # 6. Determine final valve state for each zone (Heat Request OR Cooldown OR Manual Safety)
        for zone in self.zones.values():
            should_open_valve = zone.requesting_heat

            if not should_open_valve and cooldown_mode is not None and zone.zone_id == self.cooldown_zone_id:
                should_open_valve = True
                if cooldown_mode == "power":
                    w_str = f"{self.current_power_watt:.0f}W" if self.current_power_watt is not None else ""
                    zone.forced_open_reason = f"Smaltimento calore da consumo ({w_str})"
                else:
                    zone.forced_open_reason = (
                        f"Smaltimento calore timer fallback ({self.cooldown_remaining_minutes} min)"
                    )

            if (
                not should_open_valve
                and self.manual_safety_active
                and zone.zone_id == self.manual_safety_zone_id
            ):
                should_open_valve = True
                zone.forced_open_reason = (
                    f"Sicurezza accensione manuale ({self.current_power_watt:.0f}W >= {self.power_threshold_watt:.0f}W)"
                )

            changed = await self._async_set_switch(zone.valve_entity, should_open_valve)
            if changed:
                state_label = "APERTA" if should_open_valve else "CHIUSA"
                reason_suffix = f" ({zone.forced_open_reason})" if zone.forced_open_reason else ""
                await self._async_notify(
                    NOTIFY_LEVEL_DEBUG,
                    f"Valvola {zone.name} ({zone.valve_entity}): {state_label}{reason_suffix}.",
                )

        # 7. Control main Heater switch (ON only when at least one zone requests heat)
        await self._async_set_switch(self.heater_entity, any_heating)

        # 8. Update Problem detection, send ERROR notifications on unavailability changes, & set System State
        current_unavail_set = set(unavailable)
        newly_unavailable = sorted(current_unavail_set - self._prev_unavailable_set)
        newly_restored = sorted(self._prev_unavailable_set - current_unavail_set)
        self._prev_unavailable_set = current_unavail_set

        if newly_unavailable:
            await self._async_notify(
                NOTIFY_LEVEL_ERROR,
                f"Entità diventate INDISPONIBILI: {', '.join(newly_unavailable)}.",
            )
        if newly_restored:
            await self._async_notify(
                NOTIFY_LEVEL_ERROR,
                f"Entità tornate DISPONIBILI: {', '.join(newly_restored)}.",
            )

        self.unavailable_entities = sorted(current_unavail_set)
        self.problem_detected = len(self.unavailable_entities) > 0

        if any_heating:
            self.system_state = STATE_HEATING
        elif cooldown_mode == "power":
            w_val = f"{self.current_power_watt:.0f}W" if self.current_power_watt is not None else ""
            self.system_state = f"{STATE_COOLDOWN_POWER} ({w_val})"
        elif cooldown_mode == "timer":
            rem = self.cooldown_remaining_minutes
            self.system_state = f"{STATE_COOLDOWN_TIMER} ({rem} min)"
        elif self.manual_safety_active:
            self.system_state = STATE_MANUAL_SAFETY
        elif not self.master_enabled:
            self.system_state = STATE_DISABLED
        elif self.problem_detected:
            self.system_state = STATE_PROBLEM
        else:
            self.system_state = STATE_IDLE

        self._notify_listeners()

    async def _async_set_switch(self, entity_id: str, turn_on: bool) -> bool:
        """Turn a switch or input_boolean on/off only if its current state differs. Returns True if changed."""
        state_obj = self.hass.states.get(entity_id)
        if state_obj is None or state_obj.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        is_currently_on = state_obj.state == STATE_ON
        if is_currently_on == turn_on:
            return False

        domain = entity_id.split(".")[0]
        if domain not in ("switch", "input_boolean", "homeassistant"):
            domain = "homeassistant"
        service = SERVICE_TURN_ON if turn_on else SERVICE_TURN_OFF
        await self.hass.services.async_call(
            domain,
            service,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        return True
