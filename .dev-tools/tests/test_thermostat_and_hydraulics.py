"""Tests for zone thermostat hysteresis, valve actuation, and hydraulic safety ordering."""
from __future__ import annotations

from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.smart_zone_heating.const import CONF_COOLDOWN_ENABLED, DOMAIN

from conftest import (
    HEATER_SWITCH,
    TEMP_ZONE_1,
    TEMP_ZONE_2,
    VALVE_ZONE_1,
    VALVE_ZONE_2,
    MockHardwareTracker,
    build_default_entry_data,
)


async def test_hysteresis_heating_cycle_and_hydraulic_order(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Test hysteresis band, valve-before-heater turn-on, and heater-before-valve turn-off."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(**{CONF_COOLDOWN_ENABLED: False}),
        entry_id="test_hydraulics",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Ensure zone 1 target is 20.5°C, hysteresis 0.3°C
    coordinator.zones["zone_1_piano_1"].target_temp = 20.5
    coordinator.zones["zone_2_piano_2"].target_temp = 20.0
    await coordinator.async_evaluate()
    await hass.async_block_till_done()

    # 1. Temp at 20.3°C (above 20.5 - 0.3 = 20.2°C) -> No heating
    mock_hardware.clear_log()
    mock_hardware.set_temp(TEMP_ZONE_1, 20.3)
    await hass.async_block_till_done()
    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF
    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF

    # 2. Temp drops to 20.2°C (<= 20.2°C) -> Zone 1 requests heat
    # Hydraulic rule: Valve 1 MUST open BEFORE Heater turns ON
    mock_hardware.clear_log()
    mock_hardware.set_temp(TEMP_ZONE_1, 20.2)
    await hass.async_block_till_done()

    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON
    assert hass.states.get(VALVE_ZONE_2).state == STATE_OFF
    assert hass.states.get(HEATER_SWITCH).state == STATE_ON
    assert mock_hardware.call_log == [
        (SERVICE_TURN_ON, VALVE_ZONE_1),
        (SERVICE_TURN_ON, HEATER_SWITCH),
    ]

    # 3. Temp rises to 20.6°C (< 20.5 + 0.3 = 20.8°C) -> Still heating (hysteresis hold)
    mock_hardware.clear_log()
    mock_hardware.set_temp(TEMP_ZONE_1, 20.6)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER_SWITCH).state == STATE_ON

    # 4. Temp reaches 20.8°C (>= 20.8°C) -> Heating stops
    # Hydraulic rule (when cooldown is off): Heater MUST turn OFF BEFORE Valve 1 closes
    mock_hardware.clear_log()
    mock_hardware.set_temp(TEMP_ZONE_1, 20.8)
    await hass.async_block_till_done()

    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF
    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF
    assert mock_hardware.call_log == [
        (SERVICE_TURN_OFF, HEATER_SWITCH),
        (SERVICE_TURN_OFF, VALVE_ZONE_1),
    ]


async def test_heater_does_not_turn_on_if_only_requesting_valve_is_unavailable(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Prevent firing the boiler against a closed collector when the requesting zone's valve is offline."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(**{CONF_COOLDOWN_ENABLED: False}),
        entry_id="test_offline_valve",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.zones["zone_1_piano_1"].target_temp = 20.5

    # Valve 1 goes unavailable while Zone 1 needs heat
    mock_hardware.set_switch_state(VALVE_ZONE_1, STATE_UNAVAILABLE)
    mock_hardware.set_temp(TEMP_ZONE_1, 19.0)
    await hass.async_block_till_done()

    # Since Valve 1 is unavailable and Zone 2 is not requesting heat, Heater MUST stay OFF
    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF


async def test_valve_service_exception_does_not_prevent_heater_shutoff(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Ensure a HomeAssistantError on a zone valve does not abort heater shutoff."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(**{CONF_COOLDOWN_ENABLED: False}),
        entry_id="test_valve_exception",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.zones["zone_1_piano_1"].target_temp = 20.5

    # Start heating normally
    mock_hardware.set_temp(TEMP_ZONE_1, 19.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER_SWITCH).state == STATE_ON

    # Simulate hardware communication error on Valve 1 when trying to shut down
    mock_hardware.failing_entities.add(VALVE_ZONE_1)
    mock_hardware.set_temp(TEMP_ZONE_1, 21.5)
    await hass.async_block_till_done()

    # Heater MUST still be turned OFF safely despite Valve 1 raising HomeAssistantError
    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF


async def test_second_floor_only_heating_and_cooldown_routing(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Scenario 5: Only Floor 2 requests heat; on completion, cooldown opens Floor 1 valve and closes Floor 2."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),  # Cooldown enabled on Zone 1 (Piano 1)
        entry_id="test_floor_2_only",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.zones["zone_1_piano_1"].target_temp = 20.5
    coordinator.zones["zone_2_piano_2"].target_temp = 20.0

    # Floor 1 is warm (21.0°C), Floor 2 drops to 19.0°C (<= 20.0 - 0.3 = 19.7°C)
    mock_hardware.clear_log()
    mock_hardware.set_temp(TEMP_ZONE_2, 19.0)
    mock_hardware.set_power(110.0)
    await hass.async_block_till_done()

    # Only Valve 2 opens (before Heater), Valve 1 stays OFF
    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF
    assert hass.states.get(VALVE_ZONE_2).state == STATE_ON
    assert hass.states.get(HEATER_SWITCH).state == STATE_ON
    assert mock_hardware.call_log == [
        (SERVICE_TURN_ON, VALVE_ZONE_2),
        (SERVICE_TURN_ON, HEATER_SWITCH),
    ]

    # Floor 2 reaches target (20.5°C >= 20.3°C) while stove is still at 80W
    # Cooldown activates on configured Cooldown Zone (Piano 1 -> VALVE_ZONE_1 opens, VALVE_ZONE_2 closes)
    mock_hardware.set_temp(TEMP_ZONE_2, 20.5)
    mock_hardware.set_power(80.0)
    await hass.async_block_till_done()

    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF
    assert coordinator.in_cooldown is True
    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON
    assert hass.states.get(VALVE_ZONE_2).state == STATE_OFF


async def test_both_floors_simultaneous_and_handover_without_stopping_heater(
    hass: HomeAssistant,
    mock_hardware: MockHardwareTracker,
) -> None:
    """Scenario 6: Both floors heat together; Floor 1 finishes first -> Valve 1 closes while Heater & Valve 2 keep running."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_both_floors",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.zones["zone_1_piano_1"].target_temp = 20.5
    coordinator.zones["zone_2_piano_2"].target_temp = 20.5

    # 1. Both floors drop to 19.0°C -> Both valves open and Heater turns ON
    mock_hardware.set_temp(TEMP_ZONE_1, 19.0)
    mock_hardware.set_temp(TEMP_ZONE_2, 19.0)
    mock_hardware.set_power(130.0)
    await hass.async_block_till_done()

    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON
    assert hass.states.get(VALVE_ZONE_2).state == STATE_ON
    assert hass.states.get(HEATER_SWITCH).state == STATE_ON

    # 2. Floor 1 reaches 21.0°C (satisfied), but Floor 2 is still at 19.8°C (needs heat)
    # Valve 1 closes, Valve 2 stays OPEN, Heater stays ON without entering cooldown!
    mock_hardware.set_temp(TEMP_ZONE_1, 21.0)
    await hass.async_block_till_done()

    assert hass.states.get(VALVE_ZONE_1).state == STATE_OFF
    assert hass.states.get(VALVE_ZONE_2).state == STATE_ON
    assert hass.states.get(HEATER_SWITCH).state == STATE_ON
    assert coordinator.in_cooldown is False

    # 3. Finally Floor 2 also reaches 21.0°C -> Heater turns OFF and Cooldown begins
    mock_hardware.set_temp(TEMP_ZONE_2, 21.0)
    mock_hardware.set_power(90.0)
    await hass.async_block_till_done()

    assert hass.states.get(HEATER_SWITCH).state == STATE_OFF
    assert coordinator.in_cooldown is True
    assert hass.states.get(VALVE_ZONE_1).state == STATE_ON
    assert hass.states.get(VALVE_ZONE_2).state == STATE_OFF
