"""Config flow for Smart Zone Heating integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_HEATER_ENTITY,
    CONF_SYSTEM_NAME,
    CONF_TARGET_TEMP,
    CONF_TEMP_SENSOR,
    CONF_VALVE_ENTITY,
    CONF_ZONE_COUNT,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_TARGET_TEMP,
    DOMAIN,
)


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
        """Step 1: System name, main heater switch, and number of zones."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data[CONF_SYSTEM_NAME] = user_input[CONF_SYSTEM_NAME]
            self._data[CONF_HEATER_ENTITY] = user_input[CONF_HEATER_ENTITY]
            self._zone_count = int(user_input[CONF_ZONE_COUNT])
            self._zones = []
            self._current_zone_idx = 0
            return await self.async_step_zone()

        schema = vol.Schema(
            {
                vol.Required(CONF_SYSTEM_NAME, default="Riscaldamento Casa"): selector.TextSelector(),
                vol.Required(CONF_HEATER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Required(CONF_ZONE_COUNT, default=2): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=10, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
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
        """Step 2 (repeated for each zone): Zone name, valve switch, and temp sensor."""
        errors: dict[str, str] = {}
        zone_num = self._current_zone_idx + 1

        if user_input is not None:
            zone_name = user_input[CONF_ZONE_NAME]
            zone_id = f"zone_{zone_num}_{slugify(zone_name)}"
            self._zones.append(
                {
                    CONF_ZONE_ID: zone_id,
                    CONF_ZONE_NAME: zone_name,
                    CONF_VALVE_ENTITY: user_input[CONF_VALVE_ENTITY],
                    CONF_TEMP_SENSOR: user_input[CONF_TEMP_SENSOR],
                    CONF_TARGET_TEMP: float(user_input.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP)),
                }
            )
            self._current_zone_idx += 1

            if self._current_zone_idx < self._zone_count:
                return await self.async_step_zone()

            self._data[CONF_ZONES] = self._zones
            return self.async_create_entry(
                title=self._data[CONF_SYSTEM_NAME],
                data=self._data,
            )

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
                vol.Required(CONF_TARGET_TEMP, default=DEFAULT_TARGET_TEMP): selector.NumberSelector(
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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SmartZoneHeatingOptionsFlow(config_entry)


class SmartZoneHeatingOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow to change heater or zone valves/sensors."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage main heater entity option."""
        data = {**self._entry.data, **self._entry.options}

        if user_input is not None:
            new_options = dict(self._entry.options)
            new_options[CONF_HEATER_ENTITY] = user_input[CONF_HEATER_ENTITY]
            return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HEATER_ENTITY,
                    default=data.get(CONF_HEATER_ENTITY),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
