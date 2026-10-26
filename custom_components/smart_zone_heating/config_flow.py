"""Config flow for Smart Zone Heating integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

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
    CONF_ZONE_COUNT,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_DAY_START_TIME,
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


def _get_notify_service_options(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """Build list of available notify.* services in Home Assistant."""
    options = [selector.SelectOptionDict(value="none", label="Nessuno (Disabilitato)")]
    notify_services = hass.services.async_services().get("notify", {})
    for svc_name in sorted(notify_services.keys()):
        full_name = f"notify.{svc_name}"
        options.append(selector.SelectOptionDict(value=full_name, label=full_name))
    return options


def _get_notify_level_options() -> list[selector.SelectOptionDict]:
    """Build list of notification levels."""
    return [
        selector.SelectOptionDict(value=NOTIFY_LEVEL_OFF, label="Disabilitate (Off)"),
        selector.SelectOptionDict(
            value=NOTIFY_LEVEL_ERROR,
            label="Error (Solo errori critici / sensori indisponibili)",
        ),
        selector.SelectOptionDict(
            value=NOTIFY_LEVEL_WARNING,
            label="Warning (Errori + accensione manuale / fallback timer)",
        ),
        selector.SelectOptionDict(
            value=NOTIFY_LEVEL_DEBUG,
            label="Debug (Tutti gli eventi: aperture valvole, stufa, cambio orario)",
        ),
    ]


class SmartZoneHeatingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Zone Heating."""

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
        """Step 1: System name, number of zones/floors, and Day/Night schedule hours."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data[CONF_SYSTEM_NAME] = user_input[CONF_SYSTEM_NAME]
            self._zone_count = int(user_input[CONF_ZONE_COUNT])
            self._data[CONF_ZONE_COUNT] = self._zone_count
            self._data[CONF_SCHEDULE_ENABLED] = bool(
                user_input.get(CONF_SCHEDULE_ENABLED, True)
            )
            self._data[CONF_DAY_START_TIME] = user_input.get(
                CONF_DAY_START_TIME, DEFAULT_DAY_START_TIME
            )
            self._data[CONF_NIGHT_START_TIME] = user_input.get(
                CONF_NIGHT_START_TIME, DEFAULT_NIGHT_START_TIME
            )
            self._zones = []
            self._current_zone_idx = 0
            return await self.async_step_zone()

        schema = vol.Schema(
            {
                vol.Required(CONF_SYSTEM_NAME, default="Riscaldamento Casa"): selector.TextSelector(),
                vol.Required(CONF_ZONE_COUNT, default=2): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=10, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required(CONF_SCHEDULE_ENABLED, default=True): selector.BooleanSelector(),
                vol.Required(
                    CONF_DAY_START_TIME, default=DEFAULT_DAY_START_TIME
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_NIGHT_START_TIME, default=DEFAULT_NIGHT_START_TIME
                ): selector.TimeSelector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

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
        """Step 3: Main Heater switch, Power/Cooldown safety, and optional Notifier."""
        if user_input is not None:
            self._data[CONF_HEATER_ENTITY] = user_input[CONF_HEATER_ENTITY]
            self._data[CONF_MASTER_ENABLED] = bool(user_input.get(CONF_MASTER_ENABLED, True))
            self._data[CONF_COOLDOWN_MINUTES] = int(
                user_input.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
            )
            cooldown_zone_id = user_input.get(CONF_COOLDOWN_ZONE_ID)
            self._data[CONF_COOLDOWN_ZONE_ID] = cooldown_zone_id
            self._data[CONF_POWER_SENSOR] = user_input.get(CONF_POWER_SENSOR) or None
            self._data[CONF_POWER_THRESHOLD_WATT] = float(
                user_input.get(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT)
            )
            self._data[CONF_POWER_GRACE_SECONDS] = int(
                user_input.get(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS)
            )
            notify_svc = user_input.get(CONF_NOTIFY_SERVICE)
            self._data[CONF_NOTIFY_SERVICE] = (
                None if not notify_svc or notify_svc == "none" else notify_svc
            )
            self._data[CONF_NOTIFY_LEVEL] = user_input.get(
                CONF_NOTIFY_LEVEL, DEFAULT_NOTIFY_LEVEL
            )
            use_separate = bool(user_input.get(CONF_USE_SEPARATE_MANUAL_ZONE, False))
            self._data[CONF_USE_SEPARATE_MANUAL_ZONE] = use_separate

            if use_separate:
                return await self.async_step_manual_zone()

            # Default: use the exact same zone valve for manual ignition safety as for cooldown
            self._data[CONF_MANUAL_SAFETY_ZONE_ID] = cooldown_zone_id
            return self.async_create_entry(
                title=self._data[CONF_SYSTEM_NAME],
                data=self._data,
            )

        zone_options = [
            selector.SelectOptionDict(value=z[CONF_ZONE_ID], label=z[CONF_ZONE_NAME])
            for z in self._zones
        ]
        default_zone_id = self._zones[0][CONF_ZONE_ID] if self._zones else ""
        notify_options = _get_notify_service_options(self.hass)
        level_options = _get_notify_level_options()

        schema = vol.Schema(
            {
                vol.Required(CONF_HEATER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Required(CONF_MASTER_ENABLED, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_POWER_SENSOR): selector.EntitySelector(
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
                vol.Required(
                    CONF_COOLDOWN_MINUTES, default=DEFAULT_COOLDOWN_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=240,
                        step=5,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_COOLDOWN_ZONE_ID, default=default_zone_id
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=zone_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_USE_SEPARATE_MANUAL_ZONE, default=False
                ): selector.BooleanSelector(),
                vol.Required(CONF_NOTIFY_SERVICE, default="none"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=notify_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Required(
                    CONF_NOTIFY_LEVEL, default=DEFAULT_NOTIFY_LEVEL
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=level_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="heater_and_safety",
            data_schema=schema,
        )

    async def async_step_manual_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 4 (only if use_separate_manual_zone is True): Pick separate valve for manual ignition."""
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
    """Handle options flow to change heater, schedule, cooldown, power sensor, and notifications."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry
        self._pending_options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage heater, schedule, cooldown, power consumption, and notifier options."""
        data = {**self._entry.data, **self._entry.options}
        zones = data.get(CONF_ZONES, [])

        if user_input is not None:
            new_options = dict(self._entry.options)
            new_options[CONF_HEATER_ENTITY] = user_input[CONF_HEATER_ENTITY]
            new_options[CONF_MASTER_ENABLED] = bool(user_input.get(CONF_MASTER_ENABLED, True))
            new_options[CONF_SCHEDULE_ENABLED] = bool(
                user_input.get(CONF_SCHEDULE_ENABLED, True)
            )
            new_options[CONF_DAY_START_TIME] = user_input.get(
                CONF_DAY_START_TIME, DEFAULT_DAY_START_TIME
            )
            new_options[CONF_NIGHT_START_TIME] = user_input.get(
                CONF_NIGHT_START_TIME, DEFAULT_NIGHT_START_TIME
            )
            new_options[CONF_COOLDOWN_MINUTES] = int(
                user_input.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
            )
            cooldown_zone_id = user_input.get(CONF_COOLDOWN_ZONE_ID)
            new_options[CONF_COOLDOWN_ZONE_ID] = cooldown_zone_id
            new_options[CONF_POWER_SENSOR] = user_input.get(CONF_POWER_SENSOR) or None
            new_options[CONF_POWER_THRESHOLD_WATT] = float(
                user_input.get(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT)
            )
            new_options[CONF_POWER_GRACE_SECONDS] = int(
                user_input.get(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS)
            )
            notify_svc = user_input.get(CONF_NOTIFY_SERVICE)
            new_options[CONF_NOTIFY_SERVICE] = (
                None if not notify_svc or notify_svc == "none" else notify_svc
            )
            new_options[CONF_NOTIFY_LEVEL] = user_input.get(
                CONF_NOTIFY_LEVEL, DEFAULT_NOTIFY_LEVEL
            )
            use_separate = bool(user_input.get(CONF_USE_SEPARATE_MANUAL_ZONE, False))
            new_options[CONF_USE_SEPARATE_MANUAL_ZONE] = use_separate

            if use_separate:
                self._pending_options = new_options
                return await self.async_step_manual_zone()

            new_options[CONF_MANUAL_SAFETY_ZONE_ID] = cooldown_zone_id
            return self.async_create_entry(title="", data=new_options)

        zone_options = [
            selector.SelectOptionDict(value=z[CONF_ZONE_ID], label=z[CONF_ZONE_NAME])
            for z in zones
        ]
        default_zone_id = zones[0][CONF_ZONE_ID] if zones else ""
        notify_options = _get_notify_service_options(self.hass)
        level_options = _get_notify_level_options()
        current_notify = data.get(CONF_NOTIFY_SERVICE) or "none"

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_HEATER_ENTITY,
                default=data.get(CONF_HEATER_ENTITY),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
            ),
            vol.Required(
                CONF_MASTER_ENABLED,
                default=data.get(CONF_MASTER_ENABLED, True),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_SCHEDULE_ENABLED,
                default=data.get(CONF_SCHEDULE_ENABLED, True),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_DAY_START_TIME,
                default=data.get(CONF_DAY_START_TIME, DEFAULT_DAY_START_TIME),
            ): selector.TimeSelector(),
            vol.Required(
                CONF_NIGHT_START_TIME,
                default=data.get(CONF_NIGHT_START_TIME, DEFAULT_NIGHT_START_TIME),
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_POWER_SENSOR,
                description={"suggested_value": data.get(CONF_POWER_SENSOR)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_number"])
            ),
            vol.Required(
                CONF_POWER_THRESHOLD_WATT,
                default=data.get(CONF_POWER_THRESHOLD_WATT, DEFAULT_POWER_THRESHOLD_WATT),
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
                default=data.get(CONF_POWER_GRACE_SECONDS, DEFAULT_POWER_GRACE_SECONDS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=600,
                    step=5,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_COOLDOWN_MINUTES,
                default=data.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=240,
                    step=5,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
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
                CONF_USE_SEPARATE_MANUAL_ZONE,
                default=data.get(CONF_USE_SEPARATE_MANUAL_ZONE, False),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_NOTIFY_SERVICE,
                default=current_notify,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Required(
                CONF_NOTIFY_LEVEL,
                default=data.get(CONF_NOTIFY_LEVEL, DEFAULT_NOTIFY_LEVEL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=level_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema_dict))

    async def async_step_manual_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Select separate zone valve for manual ignition in Options Flow."""
        data = {**self._entry.data, **self._entry.options}
        zones = data.get(CONF_ZONES, [])

        if user_input is not None:
            self._pending_options[CONF_MANUAL_SAFETY_ZONE_ID] = user_input[
                CONF_MANUAL_SAFETY_ZONE_ID
            ]
            return self.async_create_entry(title="", data=self._pending_options)

        zone_options = [
            selector.SelectOptionDict(value=z[CONF_ZONE_ID], label=z[CONF_ZONE_NAME])
            for z in zones
        ]
        default_zone_id = data.get(CONF_MANUAL_SAFETY_ZONE_ID) or (
            zones[0][CONF_ZONE_ID] if zones else ""
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

