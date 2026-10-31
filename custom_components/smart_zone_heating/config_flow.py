"""Config flow for Smart Zone Heating integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

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
    CONF_ZONE_COUNT,
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
)
from .coordinator import CONF_HYSTERESIS


class SmartZoneHeatingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial setup wizard for Smart Zone Heating."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._zone_count: int = 2
        self._zones: list[dict[str, Any]] = []
        self._current_zone_idx: int = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1: System name, number of zones/floors, hysteresis, and schedule toggle."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data[CONF_SYSTEM_NAME] = user_input[CONF_SYSTEM_NAME]
            self._zone_count = int(user_input[CONF_ZONE_COUNT])
            self._data[CONF_ZONE_COUNT] = self._zone_count
            self._data[CONF_HYSTERESIS] = float(
                user_input.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
            )
            schedule_on = bool(user_input.get(CONF_SCHEDULE_ENABLED, True))
            self._data[CONF_SCHEDULE_ENABLED] = schedule_on
            self._zones = []
            self._current_zone_idx = 0

            if schedule_on:
                return await self.async_step_schedule_hours()

            self._data[CONF_DAY_START_TIME] = DEFAULT_DAY_START_TIME
            self._data[CONF_NIGHT_START_TIME] = DEFAULT_NIGHT_START_TIME
            return await self.async_step_zone()

        schema = vol.Schema(
            {
                vol.Required(CONF_SYSTEM_NAME, default="Riscaldamento Casa"): selector.TextSelector(),
                vol.Required(CONF_ZONE_COUNT, default=2): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=10, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required(CONF_HYSTERESIS, default=DEFAULT_HYSTERESIS): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=2.0,
                        step=0.1,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_SCHEDULE_ENABLED, default=True): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_schedule_hours(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1b (only if schedule_enabled is True): Day and Night start hours."""
        if user_input is not None:
            self._data[CONF_DAY_START_TIME] = user_input.get(
                CONF_DAY_START_TIME, DEFAULT_DAY_START_TIME
            )
            self._data[CONF_NIGHT_START_TIME] = user_input.get(
                CONF_NIGHT_START_TIME, DEFAULT_NIGHT_START_TIME
            )
            return await self.async_step_zone()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DAY_START_TIME, default=DEFAULT_DAY_START_TIME
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_NIGHT_START_TIME, default=DEFAULT_NIGHT_START_TIME
                ): selector.TimeSelector(),
            }
        )
        return self.async_show_form(step_id="schedule_hours", data_schema=schema)

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 2 (repeated for each zone/floor): Thermostat name, valve, sensor, and Day/Night/Away temps."""
        errors: dict[str, str] = {}
        zone_num = self._current_zone_idx + 1

        if user_input is not None:
            zone_name = user_input[CONF_ZONE_NAME]
            zone_id = f"zone_{zone_num}_{slugify(zone_name)}"
            temp_day = float(user_input.get(CONF_TEMP_DAY, DEFAULT_TEMP_DAY))
            temp_night = float(user_input.get(CONF_TEMP_NIGHT, DEFAULT_TEMP_NIGHT))
            temp_away = float(user_input.get(CONF_TEMP_AWAY, DEFAULT_TEMP_AWAY))

            self._zones.append(
                {
                    CONF_ZONE_ID: zone_id,
                    CONF_ZONE_NAME: zone_name,
                    CONF_VALVE_ENTITY: user_input[CONF_VALVE_ENTITY],
                    CONF_TEMP_SENSOR: user_input[CONF_TEMP_SENSOR],
                    CONF_TEMP_DAY: temp_day,
                    CONF_TEMP_NIGHT: temp_night,
                    CONF_TEMP_AWAY: temp_away,
                    CONF_TARGET_TEMP: temp_day,
                }
            )
            self._current_zone_idx += 1

            if self._current_zone_idx < self._zone_count:
                return await self.async_step_zone()

            self._data[CONF_ZONES] = self._zones
            self._data[CONF_MASTER_ENABLED] = True
            return await self.async_step_heater_and_safety()

        default_name = f"Piano {zone_num}" if self._zone_count <= 3 else f"Zona {zone_num}"

        schema = vol.Schema(
            {
                vol.Required(CONF_ZONE_NAME, default=default_name): selector.TextSelector(),
                vol.Required(CONF_VALVE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "input_number"])
                ),
                vol.Required(CONF_TEMP_DAY, default=DEFAULT_TEMP_DAY): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5.0,
                        max=30.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_TEMP_NIGHT, default=DEFAULT_TEMP_NIGHT): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5.0,
                        max=30.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_TEMP_AWAY, default=DEFAULT_TEMP_AWAY): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5.0,
                        max=30.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="zone",
            data_schema=schema,
            description_placeholders={
                "zone_num": str(zone_num),
                "zone_total": str(self._zone_count),
            },
            errors=errors,
        )

    async def async_step_heater_and_safety(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 3: Main Heater switch, Exclusive Control, and Cooldown enable toggle."""
        default_zone_id = self._zones[0][CONF_ZONE_ID] if self._zones else ""

        if user_input is not None:
            self._data[CONF_HEATER_ENTITY] = user_input[CONF_HEATER_ENTITY]
            self._data[CONF_EXCLUSIVE_CONTROL] = bool(
                user_input.get(CONF_EXCLUSIVE_CONTROL, False)
            )
            cooldown_enabled = bool(user_input.get(CONF_COOLDOWN_ENABLED, True))
            self._data[CONF_COOLDOWN_ENABLED] = cooldown_enabled

            # Defaults
            self._data.setdefault(CONF_COOLDOWN_ZONE_ID, default_zone_id)
            self._data.setdefault(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
            self._data.setdefault(CONF_USE_POWER_SENSOR, False)
            self._data.setdefault(CONF_POWER_SENSOR, None)
            self._data.setdefault(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT)
            self._data.setdefault(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS)
            self._data.setdefault(CONF_MANUAL_SAFETY_ENABLED, False)
            self._data.setdefault(CONF_USE_SEPARATE_MANUAL_ZONE, False)
            self._data.setdefault(CONF_MANUAL_SAFETY_ZONE_ID, default_zone_id)
            self._data.setdefault(CONF_NOTIFY_SERVICE, None)
            self._data.setdefault(CONF_NOTIFY_LEVEL, DEFAULT_NOTIFY_LEVEL)

            if cooldown_enabled:
                return await self.async_step_cooldown()

            # Cooldown is OFF -> no Watt sensor configured -> finish directly
            self._data[CONF_USE_POWER_SENSOR] = False
            self._data[CONF_POWER_SENSOR] = None
            self._data[CONF_MANUAL_SAFETY_ENABLED] = False
            return self.async_create_entry(
                title=self._data[CONF_SYSTEM_NAME],
                data=self._data,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_HEATER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Required(CONF_EXCLUSIVE_CONTROL, default=False): selector.BooleanSelector(),
                vol.Required(CONF_COOLDOWN_ENABLED, default=True): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="heater_and_safety", data_schema=schema)

    async def async_step_cooldown(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 3.1: Cooldown valve, Watt monitoring toggle, and fallback timer."""
        zone_options = [
            selector.SelectOptionDict(value=z[CONF_ZONE_ID], label=z[CONF_ZONE_NAME])
            for z in self._zones
        ]
        default_zone_id = self._zones[0][CONF_ZONE_ID] if self._zones else ""

        if user_input is not None:
            cooldown_zone_id = user_input.get(CONF_COOLDOWN_ZONE_ID, default_zone_id)
            self._data[CONF_COOLDOWN_ZONE_ID] = cooldown_zone_id
            self._data[CONF_MANUAL_SAFETY_ZONE_ID] = cooldown_zone_id
            use_power = bool(user_input.get(CONF_USE_POWER_SENSOR, True))
            self._data[CONF_USE_POWER_SENSOR] = use_power
            self._data[CONF_COOLDOWN_MINUTES] = int(
                user_input.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
            )

            if use_power:
                return await self.async_step_power_sensor()

            # Watt monitoring is OFF -> no Watt sensor configured -> finish directly
            self._data[CONF_POWER_SENSOR] = None
            self._data[CONF_MANUAL_SAFETY_ENABLED] = False
            return self.async_create_entry(
                title=self._data[CONF_SYSTEM_NAME],
                data=self._data,
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_COOLDOWN_ZONE_ID, default=default_zone_id
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=zone_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_USE_POWER_SENSOR, default=True): selector.BooleanSelector(),
                vol.Required(
                    CONF_COOLDOWN_MINUTES, default=DEFAULT_COOLDOWN_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=240,
                        step=5,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="cooldown", data_schema=schema)

    async def async_step_power_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 3.1.2: Power sensor, threshold Watt, and grace seconds."""
        if user_input is not None:
            self._data[CONF_POWER_SENSOR] = user_input.get(CONF_POWER_SENSOR) or None
            self._data[CONF_POWER_THRESHOLD_WATT] = float(
                user_input.get(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT)
            )
            self._data[CONF_POWER_GRACE_SECONDS] = int(
                user_input.get(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS)
            )
            return await self.async_step_manual_safety()

        schema = vol.Schema(
            {
                vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "input_number"])
                ),
                vol.Required(
                    CONF_POWER_THRESHOLD_WATT, default=DEFAULT_POWER_THRESHOLD_WATT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0,
                        max=1000.0,
                        step=1.0,
                        unit_of_measurement="W",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_POWER_GRACE_SECONDS, default=DEFAULT_POWER_GRACE_SECONDS
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=600,
                        step=5,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="power_sensor", data_schema=schema)

    async def async_step_manual_safety(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 3.2: Manual ignition detection (only reached when a Watt sensor has been set)."""
        if user_input is not None:
            manual_enabled = bool(user_input.get(CONF_MANUAL_SAFETY_ENABLED, True))
            use_separate = bool(user_input.get(CONF_USE_SEPARATE_MANUAL_ZONE, False))
            self._data[CONF_MANUAL_SAFETY_ENABLED] = manual_enabled
            self._data[CONF_USE_SEPARATE_MANUAL_ZONE] = use_separate

            if manual_enabled and use_separate:
                return await self.async_step_manual_zone()

            return self.async_create_entry(
                title=self._data[CONF_SYSTEM_NAME],
                data=self._data,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_MANUAL_SAFETY_ENABLED, default=True): selector.BooleanSelector(),
                vol.Required(CONF_USE_SEPARATE_MANUAL_ZONE, default=False): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="manual_safety", data_schema=schema)

    async def async_step_manual_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 3.3: Select separate zone valve for manual ignition safety."""
        if user_input is not None:
            self._data[CONF_MANUAL_SAFETY_ZONE_ID] = user_input[CONF_MANUAL_SAFETY_ZONE_ID]
            return self.async_create_entry(
                title=self._data[CONF_SYSTEM_NAME],
                data=self._data,
            )

        zone_options = [
            selector.SelectOptionDict(value=z[CONF_ZONE_ID], label=z[CONF_ZONE_NAME])
            for z in self._zones
        ]
        default_zone_id = self._data.get(CONF_COOLDOWN_ZONE_ID) or (
            self._zones[0][CONF_ZONE_ID] if self._zones else ""
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MANUAL_SAFETY_ZONE_ID, default=default_zone_id
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=zone_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="manual_zone",
            data_schema=schema,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SmartZoneHeatingOptionsFlow(config_entry)


class SmartZoneHeatingOptionsFlow(config_entries.OptionsFlow):
    """Multi-page Advanced Settings (Impostazioni Avanzate) flow opened via the gear icon."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry
        self._pending_options: dict[str, Any] = dict(config_entry.options)

    def _current_data(self) -> dict[str, Any]:
        """Merge entry data, existing options, and pending step options."""
        return {**self._entry.data, **self._entry.options, **self._pending_options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Page 1: Common Heat Generator, Exclusive Control, and Heat Dissipation toggle."""
        data = self._current_data()

        if user_input is not None:
            self._pending_options[CONF_HEATER_ENTITY] = user_input[CONF_HEATER_ENTITY]
            self._pending_options[CONF_EXCLUSIVE_CONTROL] = bool(
                user_input.get(CONF_EXCLUSIVE_CONTROL, False)
            )
            cooldown_enabled = bool(user_input.get(CONF_COOLDOWN_ENABLED, True))
            self._pending_options[CONF_COOLDOWN_ENABLED] = cooldown_enabled

            if cooldown_enabled:
                return await self.async_step_cooldown()

            # Cooldown disabled -> no Watt sensor configured -> manual ignition safety not available, save directly
            self._pending_options[CONF_USE_POWER_SENSOR] = False
            self._pending_options[CONF_POWER_SENSOR] = None
            self._pending_options[CONF_MANUAL_SAFETY_ENABLED] = False
            return self._save_options()

        default_cooldown_enabled = bool(data.get(CONF_COOLDOWN_ENABLED, True))

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HEATER_ENTITY,
                    default=data.get(CONF_HEATER_ENTITY),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Required(
                    CONF_EXCLUSIVE_CONTROL,
                    default=bool(data.get(CONF_EXCLUSIVE_CONTROL, False)),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_COOLDOWN_ENABLED,
                    default=default_cooldown_enabled,
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_cooldown(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Page 2 (if cooldown_enabled is Yes): Cooldown valve, Watt monitoring toggle, and fallback timer."""
        data = self._current_data()
        zones = data.get(CONF_ZONES, [])
        zone_options = [
            selector.SelectOptionDict(value=z[CONF_ZONE_ID], label=z[CONF_ZONE_NAME])
            for z in zones
        ]
        default_zone_id = zones[0][CONF_ZONE_ID] if zones else ""

        if user_input is not None:
            cooldown_zone_id = user_input.get(CONF_COOLDOWN_ZONE_ID, default_zone_id)
            self._pending_options[CONF_COOLDOWN_ZONE_ID] = cooldown_zone_id
            use_power = bool(user_input.get(CONF_USE_POWER_SENSOR, False))
            self._pending_options[CONF_USE_POWER_SENSOR] = use_power
            self._pending_options[CONF_COOLDOWN_MINUTES] = int(
                user_input.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
            )

            if use_power:
                return await self.async_step_power_sensor()

            # Watt monitoring disabled -> no Watt sensor configured -> manual ignition safety not available, save directly
            self._pending_options[CONF_POWER_SENSOR] = None
            self._pending_options[CONF_MANUAL_SAFETY_ENABLED] = False
            return self._save_options()

        default_use_power = bool(
            data.get(CONF_USE_POWER_SENSOR, bool(data.get(CONF_POWER_SENSOR)))
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_COOLDOWN_ZONE_ID,
                    default=data.get(CONF_COOLDOWN_ZONE_ID, default_zone_id),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=zone_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_USE_POWER_SENSOR,
                    default=default_use_power,
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_COOLDOWN_MINUTES,
                    default=int(data.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=240,
                        step=5,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="cooldown", data_schema=schema)

    async def async_step_power_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Page 2.1 (if use_power_sensor is Yes): Power sensor selector, Watt threshold, and grace seconds."""
        data = self._current_data()

        if user_input is not None:
            self._pending_options[CONF_POWER_SENSOR] = user_input.get(CONF_POWER_SENSOR) or None
            self._pending_options[CONF_POWER_THRESHOLD_WATT] = float(
                user_input.get(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT)
            )
            self._pending_options[CONF_POWER_GRACE_SECONDS] = int(
                user_input.get(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS)
            )
            return await self.async_step_manual_safety()

        current_power_sensor = (
            self._entry.options.get(CONF_POWER_SENSOR)
            or self._entry.data.get(CONF_POWER_SENSOR)
        )
        power_key = (
            vol.Required(CONF_POWER_SENSOR, default=current_power_sensor)
            if current_power_sensor
            else vol.Required(CONF_POWER_SENSOR)
        )

        schema = vol.Schema(
            {
                power_key: selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "input_number"])
                ),
                vol.Required(
                    CONF_POWER_THRESHOLD_WATT,
                    default=float(
                        data.get(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0,
                        max=1000.0,
                        step=1.0,
                        unit_of_measurement="W",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_POWER_GRACE_SECONDS,
                    default=int(
                        data.get(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=600,
                        step=5,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="power_sensor", data_schema=schema)

    async def async_step_manual_safety(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Page 3 (only reached when a Watt sensor is configured): Manual ignition detection."""
        data = self._current_data()

        if user_input is not None:
            manual_enabled = bool(user_input.get(CONF_MANUAL_SAFETY_ENABLED, True))
            use_separate = bool(user_input.get(CONF_USE_SEPARATE_MANUAL_ZONE, False))
            self._pending_options[CONF_MANUAL_SAFETY_ENABLED] = manual_enabled
            self._pending_options[CONF_USE_SEPARATE_MANUAL_ZONE] = use_separate

            if manual_enabled and use_separate:
                return await self.async_step_manual_zone()

            self._pending_options[CONF_MANUAL_SAFETY_ZONE_ID] = data.get(CONF_COOLDOWN_ZONE_ID)
            return self._save_options()

        default_manual_enabled = bool(
            data.get(CONF_MANUAL_SAFETY_ENABLED, True)
        )
        default_use_separate = bool(data.get(CONF_USE_SEPARATE_MANUAL_ZONE, False))

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MANUAL_SAFETY_ENABLED,
                    default=default_manual_enabled,
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_USE_SEPARATE_MANUAL_ZONE,
                    default=default_use_separate,
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="manual_safety", data_schema=schema)

    async def async_step_manual_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Page 3.1: Select separate zone valve for manual ignition safety."""
        data = self._current_data()
        zones = data.get(CONF_ZONES, [])

        if user_input is not None:
            self._pending_options[CONF_MANUAL_SAFETY_ZONE_ID] = user_input[
                CONF_MANUAL_SAFETY_ZONE_ID
            ]
            return self._save_options()

        zone_options = [
            selector.SelectOptionDict(value=z[CONF_ZONE_ID], label=z[CONF_ZONE_NAME])
            for z in zones
        ]
        default_zone_id = (
            data.get(CONF_MANUAL_SAFETY_ZONE_ID)
            or data.get(CONF_COOLDOWN_ZONE_ID)
            or (zones[0][CONF_ZONE_ID] if zones else "")
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MANUAL_SAFETY_ZONE_ID, default=default_zone_id
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=zone_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="manual_zone", data_schema=schema)

    def _save_options(self) -> config_entries.FlowResult:
        """Persist updated options into entry.data as well so restarts always keep the latest settings."""
        merged_data = {**self._entry.data, **self._pending_options}
        self.hass.config_entries.async_update_entry(self._entry, data=merged_data)
        return self.async_create_entry(title="", data=self._pending_options)
