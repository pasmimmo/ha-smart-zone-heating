"""Shared pytest fixtures for Smart Zone Heating integration tests."""
from __future__ import annotations

from typing import Any

import pytest
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, ServiceCall
from pytest_homeassistant.common import MockConfigEntry

from custom_components.smart_zone_heating.const import (
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
    DOMAIN,
    NOTIFY_LEVEL_DEBUG,
)
from custom_components.smart_zone_heating.models import CONF_HYSTERESIS

HEATER_SWITCH = "input_boolean.stufa_relais"
VALVE_ZONE_1 = "input_boolean.valvola_zona_1"
VALVE_ZONE_2 = "input_boolean.valvola_zona_2"
TEMP_ZONE_1 = "sensor.temp_zona_1"
TEMP_ZONE_2 = "sensor.temp_zona_2"
POWER_SENSOR = "sensor.potenza_stufa"

ZONE_1_ID = "zone_1_piano_1"
ZONE_2_ID = "zone_2_piano_2"


@pytest.fixture(autouse=True)
async def auto_enable_custom_integrations(
    hass: HomeAssistant, enable_custom_integrations: Any
) -> Any:
    """Enable loading custom integrations and cleanly unload entries on teardown."""
    yield
    for entry in list(hass.config_entries.async_entries(DOMAIN)):
        if entry.state.recoverable:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


class MockHardwareTracker:
    """Tracks mock physical switch calls, notifications, and states in chronological order."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.call_log: list[tuple[str, str]] = []
        self.notifications: list[dict[str, str]] = []
        self.failing_entities: set[str] = set()

    def clear_log(self) -> None:
        self.call_log.clear()
        self.notifications.clear()

    def set_temp(self, entity_id: str, value: float | str) -> None:
        self.hass.states.async_set(
            entity_id,
            str(value),
            {
                ATTR_DEVICE_CLASS: "temperature",
                ATTR_UNIT_OF_MEASUREMENT: UnitOfTemperature.CELSIUS,
            },
        )

    def set_power(self, value: float | str) -> None:
        self.hass.states.async_set(
            POWER_SENSOR,
            str(value),
            {
                ATTR_DEVICE_CLASS: "power",
                ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            },
        )

    def set_switch_state(self, entity_id: str, state: str) -> None:
        self.hass.states.async_set(entity_id, state)


@pytest.fixture
async def mock_hardware(hass: HomeAssistant) -> MockHardwareTracker:
    """Set up simulated physical switches and sensors in Home Assistant."""
    tracker = MockHardwareTracker(hass)

    tracker.set_switch_state(HEATER_SWITCH, STATE_OFF)
    tracker.set_switch_state(VALVE_ZONE_1, STATE_OFF)
    tracker.set_switch_state(VALVE_ZONE_2, STATE_OFF)
    tracker.set_temp(TEMP_ZONE_1, 21.0)
    tracker.set_temp(TEMP_ZONE_2, 21.0)
    tracker.set_power(0.0)

    from homeassistant.exceptions import HomeAssistantError

    async def _handle_turn_on(call: ServiceCall) -> None:
        eids = call.data.get(ATTR_ENTITY_ID)
        if isinstance(eids, str):
            eids = [eids]
        for eid in eids or []:
            tracker.call_log.append((SERVICE_TURN_ON, eid))
            if eid in tracker.failing_entities:
                raise HomeAssistantError(f"Simulated hardware failure on {eid}")
            hass.states.async_set(eid, STATE_ON)

    async def _handle_turn_off(call: ServiceCall) -> None:
        eids = call.data.get(ATTR_ENTITY_ID)
        if isinstance(eids, str):
            eids = [eids]
        for eid in eids or []:
            tracker.call_log.append((SERVICE_TURN_OFF, eid))
            if eid in tracker.failing_entities:
                raise HomeAssistantError(f"Simulated hardware failure on {eid}")
            hass.states.async_set(eid, STATE_OFF)

    async def _handle_notify(call: ServiceCall) -> None:
        tracker.notifications.append(
            {
                "service": f"{call.domain}.{call.service}",
                "title": str(call.data.get("title", "")),
                "message": str(call.data.get("message", "")),
            }
        )

    hass.services.async_register("input_boolean", SERVICE_TURN_ON, _handle_turn_on)
    hass.services.async_register("input_boolean", SERVICE_TURN_OFF, _handle_turn_off)
    hass.services.async_register("homeassistant", SERVICE_TURN_ON, _handle_turn_on)
    hass.services.async_register("homeassistant", SERVICE_TURN_OFF, _handle_turn_off)
    hass.services.async_register("notify", "mobile_app_test", _handle_notify)
    hass.services.async_register("persistent_notification", "create", _handle_notify)

    return tracker


def build_default_entry_data(**overrides: Any) -> dict[str, Any]:
    """Return a complete 2-zone Smart Zone Heating configuration dictionary."""
    data: dict[str, Any] = {
        CONF_SYSTEM_NAME: "Riscaldamento Test",
        CONF_HEATER_ENTITY: HEATER_SWITCH,
        CONF_MASTER_ENABLED: True,
        CONF_EXCLUSIVE_CONTROL: False,
        CONF_HYSTERESIS: 0.3,
        CONF_SCHEDULE_ENABLED: True,
        CONF_DAY_START_TIME: "07:00:00",
        CONF_NIGHT_START_TIME: "22:00:00",
        CONF_ZONE_COUNT: 2,
        CONF_ZONES: [
            {
                CONF_ZONE_ID: ZONE_1_ID,
                CONF_ZONE_NAME: "Piano 1",
                CONF_VALVE_ENTITY: VALVE_ZONE_1,
                CONF_TEMP_SENSOR: TEMP_ZONE_1,
                CONF_TEMP_DAY: 20.5,
                CONF_TEMP_NIGHT: 18.0,
                CONF_TEMP_AWAY: 16.0,
                CONF_TARGET_TEMP: 20.5,
            },
            {
                CONF_ZONE_ID: ZONE_2_ID,
                CONF_ZONE_NAME: "Piano 2",
                CONF_VALVE_ENTITY: VALVE_ZONE_2,
                CONF_TEMP_SENSOR: TEMP_ZONE_2,
                CONF_TEMP_DAY: 20.0,
                CONF_TEMP_NIGHT: 18.0,
                CONF_TEMP_AWAY: 16.0,
                CONF_TARGET_TEMP: 20.0,
            },
        ],
        CONF_COOLDOWN_ENABLED: True,
        CONF_COOLDOWN_MINUTES: 30,
        CONF_COOLDOWN_ZONE_ID: ZONE_1_ID,
        CONF_USE_POWER_SENSOR: True,
        CONF_POWER_SENSOR: POWER_SENSOR,
        CONF_POWER_THRESHOLD_WATT: 10.0,
        CONF_POWER_GRACE_SECONDS: 15,
        CONF_MANUAL_SAFETY_ENABLED: True,
        CONF_USE_SEPARATE_MANUAL_ZONE: False,
        CONF_MANUAL_SAFETY_ZONE_ID: ZONE_1_ID,
        CONF_NOTIFY_SERVICE: None,
        CONF_NOTIFY_LEVEL: NOTIFY_LEVEL_DEBUG,
    }
    data.update(overrides)
    return data


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a MockConfigEntry for Smart Zone Heating."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Riscaldamento Test",
        data=build_default_entry_data(),
        entry_id="test_szh_entry_1",
    )
