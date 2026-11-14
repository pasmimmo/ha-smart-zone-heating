"""Tests for Generator Lifecycle Estimation (Watt & Timer fallback) and Manual Ignition Safety."""
from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.smart_zone_heating.const import (
    CONF_MANUAL_SAFETY_ZONE_ID,
    CONF_USE_SEPARATE_MANUAL_ZONE,
    DOMAIN,
    GeneratorPhase,
)

from conftest import (
    HEATER_SWITCH,
    TEMP_ZONE_1,
    VALVE_ZONE_1,
    VALVE_ZONE_2,
    ZONE_2_ID,
    MockHardwareTracker,
    build_default_entry_data,
)


async def test_generator_lifecycle_watt_cooldown_and_completion(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test full lifecycle: Heating (Running) -> Cooldown (Watt >= threshold) -> Off (Watt < threshold)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_lifecycle_watt",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.zones["zone_1_piano_1"].target_temp = 20.5
    assert coordinator.generator_phase == GeneratorPhase.OFF

    # 1. Start heating: temp drops to 19.5°C, stove power rises to 120W
    mock_hardware.set_temp(TEMP_ZONE_1, 19.5)
    mock_hardware.set_power(120.0)
    await hass.async_block_till_done()

    assert hass.states.get(HEATER_SWITCH).state == STATE_ON
    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON
    assert coordinator.generator_phase == GeneratorPhase.RUNNING

    # 2. Target reached (21.0°C): Heater turns OFF, but stove still draws 85W (>= 10W)
    # Cooldown valve (Zone 1) MUST stay OPEN to dissipate residual heat
    mock_hardware.set_temp(TEMP_ZONE_1, 21.0)
    mock_hardware.set_power(85.0)
    await hass.async_block_till_done()

    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF
    assert coordinator.in_cooldown is True
    assert coordinator.generator_phase == GeneratorPhase.STOPPING_COOLDOWN
    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON

    # 3. Advance time past initial grace period (20 seconds), stove still at 60W -> stays in cooldown
    future = dt_util.utcnow() + timedelta(seconds=20)
    freezer.move_to(future)
    async_fire_time_changed(hass, future)
    mock_hardware.set_power(60.0)
    await hass.async_block_till_done()

    assert coordinator.in_cooldown is True
    assert coordinator.generator_phase == GeneratorPhase.STOPPING_COOLDOWN
    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON

    # 4. Stove finishes shutdown cycle: power drops to 3W (< 10W threshold)
    # Cooldown ends immediately and Valve 1 closes
    mock_hardware.set_power(3.0)
    await hass.async_block_till_done()

    assert coordinator.in_cooldown is False
    assert coordinator.generator_phase == GeneratorPhase.OFF
    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF


async def test_cooldown_falls_back_to_timer_when_power_sensor_unavailable(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test fallback to timer when the Watt sensor goes unavailable during cooldown."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_lifecycle_fallback",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.zones["zone_1_piano_1"].target_temp = 20.5

    # Heat then stop heating to enter cooldown
    mock_hardware.set_temp(TEMP_ZONE_1, 19.5)
    mock_hardware.set_power(100.0)
    await hass.async_block_till_done()

    mock_hardware.set_temp(TEMP_ZONE_1, 21.0)
    await hass.async_block_till_done()
    assert coordinator.in_cooldown is True

    # Power sensor goes offline during cooldown -> fallback timer keeps Valve 1 open
    mock_hardware.set_power(STATE_UNAVAILABLE)
    future_grace = dt_util.utcnow() + timedelta(seconds=20)
    freezer.move_to(future_grace)
    async_fire_time_changed(hass, future_grace)
    await coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert coordinator.in_cooldown is True
    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON

    # Advance past the 30-minute fallback timer -> cooldown finishes and Valve 1 closes
    future_end = dt_util.utcnow() + timedelta(minutes=31)
    freezer.move_to(future_end)
    async_fire_time_changed(hass, future_end)
    await coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert coordinator.in_cooldown is False
    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF


async def test_manual_ignition_detection_and_dedicated_valve(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Test manual ignition detection when thermostats are idle but Watt >= threshold."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(
            **{
                CONF_USE_SEPARATE_MANUAL_ZONE: True,
                CONF_MANUAL_SAFETY_ZONE_ID: ZONE_2_ID,
            }
        ),
        entry_id="test_manual_ignition",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]

    # All zones are warm (21.0°C >= 20.5°C), heater switch is OFF
    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF
    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF
    assert hass.states.get(VALVE_ZONE_2).state == STATE_OFF

    # Someone turns on the stove manually from the physical panel -> power jumps to 140W
    mock_hardware.set_power(140.0)
    await hass.async_block_till_done()

    assert coordinator.manual_safety_active is True
    assert coordinator.generator_phase == GeneratorPhase.MANUAL_OVERRIDE
    # Dedicated manual safety valve (Zone 2) opens automatically
    assert hass.states.get(VALVE_ZONE_2).state == STATE_ON
    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF

    # Manual fire turns off -> power drops to 0W -> Zone 2 valve closes
    mock_hardware.set_power(0.0)
    await hass.async_block_till_done()

    assert coordinator.manual_safety_active is False
    assert coordinator.generator_phase == GeneratorPhase.OFF
    assert hass.states.get(VALVE_ZONE_2).state == STATE_OFF


async def test_manual_ignition_seamless_transition_when_thermostat_requests_heat(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Scenario 8c: Stove is manually ignited (MANUAL_OVERRIDE), then Floor 1 requests heat -> transitions to RUNNING."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_manual_to_auto",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.zones["zone_1_piano_1"].target_temp = 20.5

    # 1. Stove turned on manually at 150W while thermostats are idle
    mock_hardware.set_power(150.0)
    await hass.async_block_till_done()
    assert coordinator.manual_safety_active is True
    assert coordinator.generator_phase == GeneratorPhase.MANUAL_OVERRIDE
    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON
    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF

    # 2. Floor 1 temperature drops to 19.5°C -> Thermostat requests heat
    # System seamlessly transitions from MANUAL_OVERRIDE to RUNNING
    mock_hardware.set_temp(TEMP_ZONE_1, 19.5)
    await hass.async_block_till_done()

    assert coordinator.manual_safety_active is False
    assert coordinator.generator_phase == GeneratorPhase.RUNNING
    assert hass.states.get(HEATER_SWITCH).state == STATE_ON
    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON
