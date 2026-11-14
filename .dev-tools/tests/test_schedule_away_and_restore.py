"""Tests for schedule, away mode, RestoreEntity persistence, and no-reload option updates."""
from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    HVACMode,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE as NUMBER_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.smart_zone_heating.const import (
    CONF_EXCLUSIVE_CONTROL,
    CONF_NOTIFY_LEVEL,
    CONF_NOTIFY_SERVICE,
    DOMAIN,
    NOTIFY_LEVEL_ERROR,
    NOTIFY_LEVEL_WARNING,
    PRESET_AWAY,
    PRESET_NIGHT,
)

from conftest import (
    HEATER_SWITCH,
    TEMP_ZONE_1,
    VALVE_ZONE_1,
    VALVE_ZONE_2,
    ZONE_1_ID,
    ZONE_2_ID,
    MockHardwareTracker,
    build_default_entry_data,
)


async def test_entity_config_updates_do_not_reload_integration(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Verify changing Hysteresis or Master switch does not trigger a full ConfigEntry reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_no_reload",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator_before = hass.data[DOMAIN][entry.entry_id]
    ent_reg = er.async_get(hass)
    hyst_eid = ent_reg.async_get_entity_id(
        NUMBER_DOMAIN, DOMAIN, f"{entry.entry_id}_hysteresis"
    )
    assert hyst_eid is not None

    await hass.services.async_call(
        NUMBER_DOMAIN,
        NUMBER_SET_VALUE,
        {ATTR_ENTITY_ID: hyst_eid, ATTR_VALUE: 0.6},
        blocking=True,
    )
    await hass.async_block_till_done()

    coordinator_after = hass.data[DOMAIN][entry.entry_id]
    assert coordinator_after is coordinator_before
    assert coordinator_after.hysteresis == 0.6


async def test_thermostat_preset_and_temperature_persistence(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Verify changing preset and target temperature updates zone state and persists."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_climate_persist",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    ent_reg = er.async_get(hass)
    clim_eid = ent_reg.async_get_entity_id(
        CLIMATE_DOMAIN, DOMAIN, f"{entry.entry_id}_{ZONE_1_ID}_climate"
    )
    assert clim_eid is not None

    # Set preset to AWAY and customize away temperature to 17.0°C
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: clim_eid, ATTR_PRESET_MODE: PRESET_AWAY},
        blocking=True,
    )
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: clim_eid, ATTR_TEMPERATURE: 17.0},
        blocking=True,
    )
    await hass.async_block_till_done()

    zone = coordinator.zones[ZONE_1_ID]
    assert zone.preset_mode == PRESET_AWAY
    assert zone.target_temp == 17.0
    assert zone.temp_away == 17.0

    # Turn thermostat OFF
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: clim_eid, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert zone.hvac_mode_enabled is False


async def test_exclusive_control_and_unavailability_debounce(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test exclusive control switch restoration and 5-second unavailability debounce."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(**{CONF_EXCLUSIVE_CONTROL: True}),
        entry_id="test_excl_unavail",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Clear startup grace period to test runtime unavailability
    coordinator._startup_grace_until = None

    # 1. Exclusive control: manually turning ON Valve 1 while idle reverts it back to OFF
    mock_hardware.set_switch_state(VALVE_ZONE_1, STATE_ON)
    await hass.async_block_till_done()
    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF

    # 2. Unavailability debounce: sensor goes unavailable -> not flagged before 5s
    mock_hardware.set_temp(TEMP_ZONE_1, "unavailable")
    await hass.async_block_till_done()
    assert coordinator.problem_detected is False

    # Advance 6 seconds -> confirmed unavailable
    future = dt_util.utcnow() + timedelta(seconds=6)
    freezer.move_to(future)
    async_fire_time_changed(hass, future)
    await coordinator.async_evaluate()
    await hass.async_block_till_done()
    assert coordinator.problem_detected is True
    assert TEMP_ZONE_1 in coordinator.unavailable_entities

    # Restore sensor -> problem cleared immediately
    mock_hardware.set_temp(TEMP_ZONE_1, 20.5)
    await hass.async_block_till_done()
    assert coordinator.problem_detected is False


async def test_configuration_restored_after_restart(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Scenario 2: Verify thermostat HVAC mode, preset, and custom temperatures survive a Home Assistant restart."""
    mock_restore_cache(
        hass,
        [
            State(
                "climate.riscaldamento_test_szh_termostato_piano_1",
                HVACMode.HEAT,
                {
                    ATTR_PRESET_MODE: PRESET_NIGHT,
                    ATTR_TEMPERATURE: 18.5,
                    "temp_day": 21.5,
                    "temp_night": 18.5,
                    "temp_away": 15.5,
                },
            ),
            State(
                "climate.riscaldamento_test_szh_termostato_piano_2",
                HVACMode.OFF,
                {
                    ATTR_PRESET_MODE: PRESET_AWAY,
                    ATTR_TEMPERATURE: 15.0,
                    "temp_day": 20.0,
                    "temp_night": 18.0,
                    "temp_away": 15.0,
                },
            ),
        ],
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_restart_restore",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    z1 = coordinator.zones[ZONE_1_ID]
    z2 = coordinator.zones[ZONE_2_ID]

    assert z1.hvac_mode_enabled is True
    assert z1.preset_mode == PRESET_NIGHT
    assert z1.target_temp == 18.5
    assert z1.temp_day == 21.5

    assert z2.hvac_mode_enabled is False
    assert z2.preset_mode == PRESET_AWAY
    assert z2.target_temp == 15.0


async def test_notifications_error_recovery_and_warning_levels(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Scenario 3 & 7: Test notifications on device unavailability, recovery, and manual ignition warning."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(
            **{
                CONF_NOTIFY_SERVICE: "notify.mobile_app_test",
                CONF_NOTIFY_LEVEL: NOTIFY_LEVEL_WARNING,
            }
        ),
        entry_id="test_notifications",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator._startup_grace_until = None
    mock_hardware.clear_log()

    # 1. Floor 1 sensor becomes unavailable while heating -> after 6s fires ERROR notification & stops heating
    coordinator.zones[ZONE_1_ID].target_temp = 20.5
    mock_hardware.set_temp(TEMP_ZONE_1, 19.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER_SWITCH).state == STATE_ON

    mock_hardware.clear_log()
    mock_hardware.set_temp(TEMP_ZONE_1, "unavailable")
    await hass.async_block_till_done()
    future = dt_util.utcnow() + timedelta(seconds=6)
    freezer.move_to(future)
    async_fire_time_changed(hass, future)
    await coordinator.async_evaluate()
    await hass.async_block_till_done()

    # Heater turns off because Floor 1 sensor is unavailable; ERROR notification is sent
    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF
    assert any("🚨[SZH] -" in n["title"] for n in mock_hardware.notifications)
    assert any("[ERROR] Status:" in n["message"] and "[ERROR] Reason:" in n["message"] for n in mock_hardware.notifications)

    # 2. Sensor comes back online -> sends "✅[SZH] -" recovery notification
    mock_hardware.clear_log()
    mock_hardware.set_temp(TEMP_ZONE_1, 21.0)
    await hass.async_block_till_done()
    assert any("✅[SZH] -" in n["title"] for n in mock_hardware.notifications)
    assert any("[OK] Status:" in n["message"] for n in mock_hardware.notifications)

    # Finish cooldown first (advance past grace period with 0W) so stove is completely idle
    future_cool = dt_util.utcnow() + timedelta(seconds=20)
    freezer.move_to(future_cool)
    async_fire_time_changed(hass, future_cool)
    mock_hardware.set_power(0.0)
    await coordinator.async_evaluate()
    await hass.async_block_till_done()
    assert coordinator.in_cooldown is False

    # 3. Manual ignition while idle -> sends "⚠️[SZH] -" notification with Status/Reason/Value
    mock_hardware.clear_log()
    mock_hardware.set_power(140.0)
    await hass.async_block_till_done()
    assert any("⚠️[SZH] -" in n["title"] for n in mock_hardware.notifications)
    assert any("[WARN] Value: 140W >= 10W" in n["message"] for n in mock_hardware.notifications)

    # 4. If level is set to ERROR, WARNING events are filtered out
    coordinator.notify_level = NOTIFY_LEVEL_ERROR
    mock_hardware.set_power(0.0)
    await hass.async_block_till_done()
    mock_hardware.clear_log()
    mock_hardware.set_power(140.0)
    await hass.async_block_till_done()
    assert not any("⚠️[SZH] -" in n["title"] for n in mock_hardware.notifications)
    assert hass.states.get(VALVE_ZONE_2).state == STATE_OFF
