"""Tests for Smart Zone Heating ConfigFlow and OptionsFlow."""
from __future__ import annotations

from conftest import (
    HEATER_SWITCH,
    POWER_SENSOR,
    TEMP_ZONE_1,
    VALVE_ZONE_1,
    ZONE_1_ID,
    MockHardwareTracker,
    build_default_entry_data,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.smart_zone_heating.const import (
    CONF_COOLDOWN_ENABLED,
    CONF_COOLDOWN_MINUTES,
    CONF_COOLDOWN_ZONE_ID,
    CONF_DAY_START_TIME,
    CONF_EXCLUSIVE_CONTROL,
    CONF_HEATER_ENTITY,
    CONF_MANUAL_SAFETY_ENABLED,
    CONF_NIGHT_START_TIME,
    CONF_POWER_GRACE_SECONDS,
    CONF_POWER_SENSOR,
    CONF_POWER_THRESHOLD_WATT,
    CONF_SCHEDULE_ENABLED,
    CONF_SYSTEM_NAME,
    CONF_TEMP_AWAY,
    CONF_TEMP_DAY,
    CONF_TEMP_NIGHT,
    CONF_TEMP_SENSOR,
    CONF_USE_POWER_SENSOR,
    CONF_USE_SEPARATE_MANUAL_ZONE,
    CONF_VALVE_ENTITY,
    CONF_ZONE_COUNT,
    CONF_ZONE_NAME,
    DOMAIN,
)
from custom_components.smart_zone_heating.models import CONF_HYSTERESIS


async def test_full_config_flow_wizard(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Test the complete multi-step ConfigFlow wizard."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Step 1: User settings (1 zone, schedule enabled)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SYSTEM_NAME: "Casa Test",
            CONF_ZONE_COUNT: 1,
            CONF_HYSTERESIS: 0.3,
            CONF_SCHEDULE_ENABLED: True,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "schedule_hours"

    # Step 1b: Schedule hours
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DAY_START_TIME: "06:30:00",
            CONF_NIGHT_START_TIME: "22:30:00",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zone"

    # Step 2: Zone 1
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ZONE_NAME: "Piano 1",
            CONF_VALVE_ENTITY: VALVE_ZONE_1,
            CONF_TEMP_SENSOR: TEMP_ZONE_1,
            CONF_TEMP_DAY: 20.5,
            CONF_TEMP_NIGHT: 18.0,
            CONF_TEMP_AWAY: 16.0,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "heater_and_safety"

    # Step 3: Heater & Cooldown enabled
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HEATER_ENTITY: HEATER_SWITCH,
            CONF_EXCLUSIVE_CONTROL: True,
            CONF_COOLDOWN_ENABLED: True,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cooldown"

    # Step 3.1: Cooldown settings with Watt sensor
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COOLDOWN_ZONE_ID: ZONE_1_ID,
            CONF_USE_POWER_SENSOR: True,
            CONF_COOLDOWN_MINUTES: 45,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "power_sensor"

    # Step 3.1.2: Power sensor settings
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_POWER_SENSOR: POWER_SENSOR,
            CONF_POWER_THRESHOLD_WATT: 12.0,
            CONF_POWER_GRACE_SECONDS: 20,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual_safety"

    # Step 3.2: Manual safety (shared valve) -> Create Entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MANUAL_SAFETY_ENABLED: True,
            CONF_USE_SEPARATE_MANUAL_ZONE: False,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Casa Test"
    assert result["data"][CONF_POWER_THRESHOLD_WATT] == 12.0


async def test_options_flow_updates_settings(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Test updating settings via OptionsFlow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_opt_flow",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_HEATER_ENTITY: HEATER_SWITCH,
            CONF_EXCLUSIVE_CONTROL: True,
            CONF_COOLDOWN_ENABLED: False,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.exclusive_control is True
    assert coordinator.cooldown_enabled is False
