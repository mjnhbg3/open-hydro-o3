import asyncio
from unittest.mock import AsyncMock

import pytest

from app.actuators import ActuatorController


@pytest.mark.asyncio
async def test_execute_pump_dose_success(monkeypatch):
    controller = ActuatorController(mock=True)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    result = await controller._execute_pump_dose("pump_a", 5.0)
    assert result is True
    assert controller.states["pumps"]["pump_a"] is False


@pytest.mark.asyncio
async def test_execute_pump_dose_error(monkeypatch):
    controller = ActuatorController(mock=True)

    async def boom(_):
        raise RuntimeError("fail")

    monkeypatch.setattr(asyncio, "sleep", boom)
    result = await controller._execute_pump_dose("pump_a", 5.0)
    assert result is False
    assert controller.states["pumps"]["pump_a"] is False


def test_check_dosing_safety_limits():
    controller = ActuatorController(mock=True)
    unsafe = controller._check_dosing_safety("pump_a", 100)
    assert not unsafe["safe"]
    controller.daily_doses["pump_a"] = 195
    over_daily = controller._check_dosing_safety("pump_a", 10)
    assert not over_daily["safe"]
    safe = controller._check_dosing_safety("pump_a", 5)
    assert safe["safe"]


@pytest.mark.asyncio
async def test_dose_nutrients_skips_invalid_and_limits(monkeypatch):
    controller = ActuatorController(mock=True)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    controller.daily_doses["pump_a"] = 195
    cmds = {
        "pump_a": {"ml": 10, "reason": "test"},
        "badpump": {"ml": 5},
    }
    res = await controller.dose_nutrients(cmds)
    assert "pump_a" in res["skipped"]  # daily limit
    assert "badpump" not in res["executed"]


@pytest.mark.asyncio
async def test_emergency_stop_sets_states(monkeypatch):
    controller = ActuatorController(mock=True)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    await controller._execute_pump_dose("pump_a", 2)
    await controller.control_fan(50)
    await controller.control_led(80)
    status_before = await controller.get_status()
    assert status_before["states"]["fan_speed"] == 50
    await controller.emergency_stop()
    status_after = await controller.get_status()
    assert all(not v for v in status_after["states"]["pumps"].values())
    assert status_after["states"]["fan_speed"] == 0
    assert status_after["states"]["led_power"] == 0


@pytest.mark.asyncio
async def test_fan_and_led_controls(monkeypatch):
    controller = ActuatorController(mock=True)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    res = await controller.control_fan(80, duration_minutes=0.01)
    assert res["fan_speed"] == 80
    await controller.control_led(70)
    status = await controller.get_status()
    assert status["states"]["fan_speed"] == 80
    assert status["states"]["led_power"] == 70
    # auto shutoff triggers sleep
    await controller._auto_fan_shutoff(0)
    assert controller.states["fan_speed"] == 0


def test_reset_daily_doses():
    controller = ActuatorController(mock=True)
    controller.daily_doses["pump_a"] = 10
    controller.last_dose_reset = controller.last_dose_reset.replace(
        day=controller.last_dose_reset.day - 1
    )
    controller._reset_daily_doses_if_needed()
    assert controller.daily_doses == {}
