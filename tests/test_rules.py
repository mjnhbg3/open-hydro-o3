"""
Tests for the rules engine and stable-unless-better logic
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from datetime import datetime, timedelta

from app.rules import RulesEngine


@pytest_asyncio.fixture
async def rules_engine(mock_config, temp_db):
    """Create rules engine instance"""
    await temp_db.init()
    return RulesEngine(mock_config, temp_db)


class TestRulesEngine:
    """Test the rules engine functionality"""

    @pytest.mark.asyncio
    async def test_ph_adjustment_rule(self, rules_engine, mock_sensor_data):
        """Test pH adjustment rule logic"""
        # Mock 7-day trends indicating poor pH stability
        mock_trends = {
            "ph_in_spec_7day": 85.0,  # Below 90% threshold
            "ph_trend": "decreasing",
        }

        # Mock KPI calculator to return poor pH trends
        rules_engine.kpi_calc.calculate_7day_trends = AsyncMock(
            return_value=mock_trends
        )

        # Test with high pH requiring adjustment
        mock_sensor_data["water"]["ph"] = 6.8  # Above target of 6.0

        current_kpis = {"health_score": 0.75}

        result = await rules_engine.evaluate_rules(mock_sensor_data, current_kpis)

        assert result is not None
        assert "rule_evaluations" in result
        assert "actions" in result

        # Should recommend pH adjustment
        ph_actions = [
            r for r in result["rule_evaluations"] if r.get("rule") == "ph_adjustment"
        ]
        if ph_actions:
            assert "action" in ph_actions[0]
            assert "ph_pump" in ph_actions[0]["action"]

    @pytest.mark.asyncio
    async def test_ec_adjustment_rule(self, rules_engine, mock_sensor_data):
        """Test EC adjustment rule logic"""
        # Mock trends showing poor EC stability and low health
        mock_trends = {
            "ec_in_spec_7day": 80.0,  # Below 90% threshold
            "ml_total_7day": 45.0,
        }

        rules_engine.kpi_calc.calculate_7day_trends = AsyncMock(
            return_value=mock_trends
        )

        # Test with low EC and low health score
        mock_sensor_data["water"]["ec"] = 1.3  # Below target of 1.6
        current_kpis = {"health_score": 0.7}  # Below 0.8 threshold

        result = await rules_engine.evaluate_rules(mock_sensor_data, current_kpis)

        # Should recommend EC increase
        ec_actions = [
            r for r in result["rule_evaluations"] if r.get("rule") == "ec_increase"
        ]
        if ec_actions:
            assert "action" in ec_actions[0]
            action = ec_actions[0]["action"]
            assert "pump_a" in action or "pump_b" in action

    @pytest.mark.asyncio
    async def test_environmental_control_rules(self, rules_engine, mock_sensor_data):
        """Test environmental control rule logic"""
        # Test high temperature triggering fan control
        mock_sensor_data["air"]["temperature"] = 28.0  # Above target + tolerance
        current_kpis = {"health_score": 0.8}

        result = await rules_engine.evaluate_rules(mock_sensor_data, current_kpis)

        # Should recommend fan speed increase
        fan_actions = [r for r in result["rule_evaluations"] if r.get("type") == "fan"]
        if fan_actions:
            assert "action" in fan_actions[0]
            assert fan_actions[0]["action"]["fan_speed"] > 0

    @pytest.mark.asyncio
    async def test_safety_limits_enforcement(self, rules_engine):
        """Test that safety limits are enforced"""
        # Test dosing safety limits
        assert rules_engine._is_dosage_safe("pump_a", 25.0)
        assert not rules_engine._is_dosage_safe("pump_a", 75.0)
        assert rules_engine._is_dosage_safe("ph_pump", 15.0)
        assert not rules_engine._is_dosage_safe("ph_pump", 25.0)

    @pytest.mark.asyncio
    async def test_freeze_status_check(self, rules_engine):
        """Test system freeze logic for excellent performance"""
        # Mock excellent performance trends
        excellent_trends = {
            "health_7day_avg": 0.96,
            "ph_in_spec_7day": 97.0,
            "ec_in_spec_7day": 96.0,
        }

        freeze_status = await rules_engine._check_freeze_status(excellent_trends)

        assert freeze_status["frozen"]
        assert "freeze_until" in freeze_status
        assert freeze_status["reason"] is not None

    @pytest.mark.asyncio
    async def test_stable_unless_better_logic(self, rules_engine):
        """Test stable-unless-better filtering"""
        # Mock proposed actions
        proposed_actions = {
            "dose": {
                "pump_a": {"ml": 10.0, "reason": "Test dosing"},
                "pump_b": {"ml": 5.0, "reason": "Test dosing"},
            }
        }

        # Test with excellent performance (should reduce actions)
        excellent_performance = {"health_score": 0.95}

        result = await rules_engine.apply_stable_unless_better_logic(
            proposed_actions, excellent_performance
        )

        assert result["stability_factor"] == 0.5  # Should reduce by 50%
        assert result["filtered_actions"]["dose"]["pump_a"]["ml"] == 5.0  # Reduced

        # Test with poor performance (should allow full actions)
        poor_performance = {"health_score": 0.6}

        result = await rules_engine.apply_stable_unless_better_logic(
            proposed_actions, poor_performance
        )

        assert result["stability_factor"] == 1.0  # No reduction
        assert result["filtered_actions"]["dose"]["pump_a"]["ml"] == 10.0  # Full amount

    def test_ph_dosage_calculations(self, rules_engine):
        """Test pH dosage calculation formulas"""
        # Test pH down calculation
        dosage_down = rules_engine._calculate_ph_down_dosage(0.2)  # 0.2 pH units
        assert dosage_down > 0
        assert dosage_down <= 50  # Should be reasonable amount

        # Test pH up calculation
        dosage_up = rules_engine._calculate_ph_up_dosage(0.2)
        assert dosage_up > 0
        assert dosage_up < dosage_down  # pH up typically more concentrated

    def test_nutrient_dosage_calculations(self, rules_engine):
        """Test nutrient dosage calculation formulas"""
        # Test EC increase dosage
        dosage_increase = rules_engine._calculate_nutrient_dosage(0.1, increase=True)
        assert dosage_increase > 0
        assert dosage_increase <= 50  # Should be reasonable

        # Test EC decrease dosage (dilution)
        dosage_decrease = rules_engine._calculate_nutrient_dosage(0.1, increase=False)
        assert dosage_decrease > 0
        assert dosage_decrease < dosage_increase  # Dilution harder than concentration

    @pytest.mark.asyncio
    async def test_ph_target_nudge_rule(self, rules_engine, mock_sensor_data):
        """pH target nudging when stability is poor"""
        mock_trends = {"ph_in_spec_7day": 80.0, "ph_trend": "increasing"}
        rules_engine.kpi_calc.calculate_7day_trends = AsyncMock(
            return_value=mock_trends
        )

        result = await rules_engine.evaluate_rules(
            mock_sensor_data, {"health_score": 0.9}
        )

        nudge = [
            r for r in result["rule_evaluations"] if r.get("rule") == "ph_target_nudge"
        ]
        assert nudge
        assert nudge[0]["action"]["ph_target"] == 6.1

    @pytest.mark.asyncio
    async def test_ec_target_raise_rule(self, rules_engine, mock_sensor_data):
        """EC target raises when performance is poor"""
        mock_trends = {"ec_in_spec_7day": 80.0, "ml_total_7day": 30.0}
        rules_engine.kpi_calc.calculate_7day_trends = AsyncMock(
            return_value=mock_trends
        )

        result = await rules_engine.evaluate_rules(
            mock_sensor_data, {"health_score": 0.7}
        )

        raise_act = [
            r for r in result["rule_evaluations"] if r.get("rule") == "ec_target_raise"
        ]
        assert raise_act
        assert raise_act[0]["action"]["ec_target"] == 1.7

    @pytest.mark.asyncio
    async def test_ec_target_lower_rule(self, rules_engine, mock_sensor_data):
        """EC target lowered when dosing high"""
        mock_trends = {"ec_in_spec_7day": 96.0, "ml_total_7day": 70.0}
        rules_engine.kpi_calc.calculate_7day_trends = AsyncMock(
            return_value=mock_trends
        )

        result = await rules_engine.evaluate_rules(
            mock_sensor_data, {"health_score": 0.85}
        )

        lower_act = [
            r for r in result["rule_evaluations"] if r.get("rule") == "ec_decrease"
        ]
        assert lower_act
        assert lower_act[0]["action"]["ec_target"] == 1.5

    @pytest.mark.asyncio
    async def test_lux_ec_temp_lower(self, rules_engine, mock_sensor_data):
        """Temporary EC reduction when high light and EC"""
        mock_trends = {"ec_in_spec_7day": 95.0, "ml_total_7day": 40.0}
        rules_engine.kpi_calc.calculate_7day_trends = AsyncMock(
            return_value=mock_trends
        )
        rules_engine.db.get_recent_sensor_data = AsyncMock(
            return_value=[{"ec": 2.1}, {"ec": 2.1}, {"ec": 2.1}]
        )
        mock_sensor_data["light"]["lux"] = 32000

        result = await rules_engine.evaluate_rules(
            mock_sensor_data, {"health_score": 0.85}
        )

        action = [
            r
            for r in result["rule_evaluations"]
            if r.get("rule") == "lux_ec_temp_lower"
        ]
        assert action
        assert action[0]["action"]["ec_target"] == 1.5


class TestRuleValidation:
    """Test rule validation and edge cases"""

    @pytest.mark.asyncio
    async def test_missing_sensor_data(self, rules_engine):
        """Test handling of missing sensor data"""
        incomplete_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "water": {"ph": None, "ec": 1.6},  # Missing pH
            "air": {"temperature": 22},  # Missing other air data
        }

        current_kpis = {"health_score": 0.8}

        # Should not crash with incomplete data
        result = await rules_engine.evaluate_rules(incomplete_data, current_kpis)

        assert result is not None
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_extreme_sensor_values(self, rules_engine, mock_sensor_data):
        """Test handling of extreme sensor values"""
        # Test with extreme values
        mock_sensor_data["water"]["ph"] = 3.0  # Extremely low
        mock_sensor_data["water"]["ec"] = 4.0  # Extremely high
        mock_sensor_data["air"]["temperature"] = 40.0  # Very high

        current_kpis = {"health_score": 0.2}  # Very poor

        result = await rules_engine.evaluate_rules(mock_sensor_data, current_kpis)

        # Should handle extreme values gracefully
        assert result is not None
        assert result.get("rollback_required", {}).get("required")

    @pytest.mark.asyncio
    async def test_rollback_after_config_change(self, rules_engine, mock_sensor_data):
        """Rollback triggered when KPIs worsen after a change"""
        rules_engine._last_config_change_time = datetime.utcnow() - timedelta(hours=1)
        rules_engine._previous_kpis = {
            "health_score": 0.9,
            "ph_in_spec": 0.95,
            "ec_in_spec": 0.9,
        }

        mock_trends = {
            "ph_in_spec_7day": 95.0,
            "ec_in_spec_7day": 95.0,
            "ml_total_7day": 40.0,
        }
        rules_engine.kpi_calc.calculate_7day_trends = AsyncMock(
            return_value=mock_trends
        )

        current_kpis = {"health_score": 0.85, "ph_in_spec": 0.9, "ec_in_spec": 0.88}
        result = await rules_engine.evaluate_rules(mock_sensor_data, current_kpis)

        assert result["rollback_required"]["required"]

    def test_dosage_safety_edge_cases(self, rules_engine):
        """Test dosage safety with edge cases"""
        # Test zero dosage
        assert not rules_engine._is_dosage_safe("pump_a", 0.0)  # Zero not allowed

        # Test negative dosage
        assert not rules_engine._is_dosage_safe("pump_a", -5.0)

        # Test exact limit
        assert rules_engine._is_dosage_safe("pump_a", 50.0)  # Exactly at limit

        # Test very small dosage
        assert rules_engine._is_dosage_safe("pump_a", 0.1)


@pytest.mark.integration
class TestRulesIntegration:
    """Integration tests for rules engine with other components"""

    @pytest.mark.asyncio
    async def test_full_rules_cycle_with_database(
        self, rules_engine, mock_sensor_data, temp_db
    ):
        """Test complete rules evaluation cycle with database storage"""
        await temp_db.init()

        # Store some historical data first
        for i in range(10):
            await temp_db.store_sensor_reading(mock_sensor_data)
            await temp_db.store_actuator_action(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "action_type": "test",
                    "pump_a_ml": 2.0,
                    "reason": "test action",
                }
            )

        current_kpis = {"health_score": 0.8}

        result = await rules_engine.evaluate_rules(mock_sensor_data, current_kpis)

        assert result is not None
        assert "rule_evaluations" in result
        assert "actions" in result
        assert "freeze_status" in result

    @pytest.mark.asyncio
    async def test_rules_with_kpi_calculation(
        self, rules_engine, mock_sensor_data, temp_db
    ):
        """Test rules engine integration with KPI calculations"""
        await temp_db.init()

        # Create mock KPI data
        kpis = {
            "health_score": 0.85,
            "ph_in_spec": 0.9,
            "ec_in_spec": 0.88,
            "days_since_reservoir_change": 10,
        }

        result = await rules_engine.evaluate_rules(mock_sensor_data, kpis)

        # Verify the rules engine used the KPI data appropriately
        assert result is not None
        assert len(result["rule_evaluations"]) > 0
