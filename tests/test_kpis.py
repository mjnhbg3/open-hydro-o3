import pytest
from unittest.mock import AsyncMock, MagicMock

from app.memory.kpis import KPICalculator


@pytest.mark.asyncio
async def test_is_in_range_and_trend():
    calc = KPICalculator()
    assert calc._is_in_range(6.0, 5.5, 6.5) == 1.0
    assert calc._is_in_range(7.0, 5.5, 6.5) < 1.0
    assert calc._calculate_trend([1, 2, 3]) == "increasing"
    assert calc._calculate_trend([3, 2, 1]) == "decreasing"
    assert calc._calculate_trend([1, 1, 1]) == "stable"


@pytest.mark.asyncio
async def test_calculate_current_kpis(monkeypatch, mock_sensor_data):
    calc = KPICalculator()
    monkeypatch.setattr(
        calc,
        "_get_recent_dosing_totals",
        AsyncMock(
            return_value={
                "total_24h": 5,
                "pump_a_24h": 2,
                "pump_b_24h": 2,
                "ph_pump_24h": 1,
            }
        ),
    )
    monkeypatch.setattr(
        calc, "_get_days_since_reservoir_change", AsyncMock(return_value=3)
    )
    kpis = await calc.calculate_current_kpis(mock_sensor_data)
    assert kpis["health_score"] > 0
    assert kpis["ml_total_24h"] == 5
    assert kpis["days_since_reservoir_change"] == 3


@pytest.mark.asyncio
async def test_calculate_period_kpis(monkeypatch):
    db_mock = MagicMock()
    db_mock.get_recent_sensor_data = AsyncMock(
        return_value=[
            {"ph": 6.0, "ec": 1.6, "air_temp": 22, "humidity": 60, "co2": 800}
            for _ in range(3)
        ]
    )
    db_mock.get_recent_actions = AsyncMock(return_value=[{"pump_a_ml": 2.0}])
    calc = KPICalculator(db_mock)
    result = await calc.calculate_period_kpis(period_hours=1)
    assert result["reading_count"] == 3
    assert result["ph_avg"] == 6.0
    assert result["ml_total"] == 2.0


@pytest.mark.asyncio
async def test_calculate_period_kpis_no_data(monkeypatch):
    db_mock = MagicMock()
    db_mock.get_recent_sensor_data = AsyncMock(return_value=[])
    calc = KPICalculator(db_mock)
    res = await calc.calculate_period_kpis(period_hours=1)
    assert "error" in res


@pytest.mark.asyncio
async def test_dosing_totals_and_trends():
    calc = KPICalculator()
    actions = [
        {"pump_a_ml": 1.0, "pump_b_ml": 2.0, "ph_pump_ml": 0.5, "success": True},
        {"pump_a_ml": 1.0, "pump_b_ml": 1.0, "ph_pump_ml": 0.5, "success": True},
    ]
    totals = calc._calculate_dosing_totals(actions)
    assert totals["ml_total"] == 6.0
    trend = calc._calculate_trend([1, 1.5, 2])
    assert trend == "increasing"
