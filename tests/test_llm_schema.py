"""
Tests for LLM schema validation and decision making
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm_agent import LLMAgent
from app.utils import validate_json_schema, load_json_schema


@pytest.fixture
def llm_agent(mock_openai):
    """Create LLM agent with mocked OpenAI"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        agent = LLMAgent()
        agent.client = mock_openai
        return agent


class TestLLMSchemaValidation:
    """Test LLM response schema validation"""

    def test_dose_schema_validation(self):
        """Test dosing command schema validation"""
        # Load the dosing schema
        try:
            schema = load_json_schema("schemas/actuator_dose.json")
        except Exception:
            # If schema file doesn't exist, create basic schema for testing
            schema = {
                "type": "object",
                "properties": {
                    "timestamp": {"type": "string"},
                    "pump_a": {
                        "type": "object",
                        "properties": {
                            "ml": {"type": "number", "minimum": 0, "maximum": 50},
                            "reason": {"type": "string"},
                        },
                        "required": ["ml", "reason"],
                    },
                },
                "required": ["timestamp"],
            }

        # Valid dosing command
        valid_dose = {
            "timestamp": "2023-01-01T12:00:00Z",
            "pump_a": {"ml": 5.0, "reason": "pH adjustment needed"},
        }

        # Should validate successfully
        assert validate_json_schema(valid_dose, schema)

        # Invalid dosing command (negative ml)
        invalid_dose = {
            "timestamp": "2023-01-01T12:00:00Z",
            "pump_a": {
                "ml": -5.0,  # Invalid negative amount
                "reason": "pH adjustment needed",
            },
        }

        # Should raise validation error
        with pytest.raises(ValueError):
            validate_json_schema(invalid_dose, schema)

    def test_fan_schema_validation(self):
        """Test fan control schema validation"""
        schema = {
            "type": "object",
            "properties": {
                "timestamp": {"type": "string"},
                "fan_speed": {"type": "number", "minimum": 0, "maximum": 100},
                "duration_minutes": {"type": "number", "minimum": 1, "maximum": 1440},
                "reason": {"type": "string"},
            },
            "required": ["timestamp", "fan_speed", "duration_minutes", "reason"],
        }

        # Valid fan command
        valid_fan = {
            "timestamp": "2023-01-01T12:00:00Z",
            "fan_speed": 75,
            "duration_minutes": 30,
            "reason": "Temperature control",
        }

        assert validate_json_schema(valid_fan, schema)

        # Invalid fan command (speed > 100)
        invalid_fan = {
            "timestamp": "2023-01-01T12:00:00Z",
            "fan_speed": 150,  # Invalid speed
            "duration_minutes": 30,
            "reason": "Temperature control",
        }

        with pytest.raises(ValueError):
            validate_json_schema(invalid_fan, schema)

    def test_led_schema_validation(self):
        """Test LED control schema validation"""
        schema = {
            "type": "object",
            "properties": {
                "timestamp": {"type": "string"},
                "led_power": {"type": "number", "minimum": 0, "maximum": 100},
                "reason": {"type": "string"},
            },
            "required": ["timestamp", "led_power", "reason"],
        }

        # Valid LED command
        valid_led = {
            "timestamp": "2023-01-01T12:00:00Z",
            "led_power": 80,
            "reason": "Light schedule adjustment",
        }

        assert validate_json_schema(valid_led, schema)


class TestLLMAgent:
    """Test LLM agent functionality"""

    @pytest.mark.asyncio
    async def test_llm_decision_making(self, llm_agent, mock_sensor_data, mock_config):
        """Test LLM decision making process"""
        # Mock vector memory
        llm_agent.vector_memory = MagicMock()
        llm_agent.vector_memory.search = AsyncMock(return_value=[])

        # Mock KPI calculator
        llm_agent.kpi_calc = MagicMock()
        llm_agent.kpi_calc.calculate_current_kpis = AsyncMock(
            return_value={"health_score": 0.8, "ph_in_spec": 0.9, "ec_in_spec": 0.85}
        )

        result = await llm_agent.make_decision(mock_sensor_data, mock_config)

        assert result is not None
        assert "decisions" in result
        assert "reasoning" in result
        assert "confidence" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_llm_response_validation(self, llm_agent):
        """Test LLM response validation"""
        # Mock valid response
        valid_response = {
            "decisions": {
                "dose": {
                    "pump_a": {"ml": 2.5, "reason": "EC adjustment"},
                    "ph_pump": {"ml": 1.0, "reason": "pH correction"},
                }
            },
            "reasoning": "Making minor adjustments based on sensor trends",
            "confidence": 0.8,
        }

        # Mock schema loading (simplified)
        llm_agent.schemas = {
            "actuator_dose": {
                "type": "object",
                "properties": {
                    "pump_a": {
                        "type": "object",
                        "properties": {
                            "ml": {"type": "number", "minimum": 0, "maximum": 50},
                            "reason": {"type": "string"},
                        },
                    }
                },
            }
        }

        validated = await llm_agent._validate_response(valid_response)

        assert validated is not None
        assert "decisions" in validated
        assert "dose" in validated["decisions"]

    @pytest.mark.asyncio
    async def test_llm_error_handling(self, llm_agent, mock_sensor_data, mock_config):
        """Test LLM error handling"""
        # Mock API failure
        llm_agent.client.chat.completions.create.side_effect = Exception("API Error")

        # Mock other components
        llm_agent.vector_memory = MagicMock()
        llm_agent.vector_memory.search = AsyncMock(return_value=[])
        llm_agent.kpi_calc = MagicMock()
        llm_agent.kpi_calc.calculate_current_kpis = AsyncMock(
            return_value={"health_score": 0.8}
        )

        result = await llm_agent.make_decision(mock_sensor_data, mock_config)

        assert result is not None
        assert "error" in result
        assert result["fallback"]

    def test_system_prompt_generation(self, llm_agent):
        """Test system prompt generation"""
        config = {
            "grow_phase": "flowering",
            "targets": {
                "ph_min": 5.5,
                "ph_max": 6.5,
                "ec_min": 1.2,
                "ec_max": 2.0,
                "temp_min": 18,
                "temp_max": 26,
            },
        }

        memory_context = "Previous similar conditions resulted in good growth"
        kpis = {"days_since_reservoir_change": 5}

        prompt = llm_agent._prepare_system_prompt(config, memory_context, kpis)

        assert "flowering" in prompt
        assert "5.5-6.5" in prompt  # pH range
        assert "1.2-2.0" in prompt  # EC range
        assert "stable-unless-better" in prompt.lower()
        assert memory_context in prompt

    def test_user_message_generation(self, llm_agent, mock_sensor_data):
        """Test user message generation"""
        kpis = {"health_score": 0.85, "ph_in_spec": 0.9}
        recent_actions = [{"action": "test", "timestamp": "2023-01-01T12:00:00Z"}]

        message = llm_agent._prepare_user_message(
            mock_sensor_data, kpis, recent_actions
        )

        assert "CURRENT SENSOR READINGS" in message
        assert "CURRENT KPIs" in message
        assert "RECENT ACTIONS" in message
        assert json.dumps(mock_sensor_data, indent=2) in message

    def test_decision_summary_creation(self, llm_agent):
        """Test decision summary creation for vector storage"""
        sensor_data = {
            "water": {"ph": 6.2, "ec": 1.8},
            "air": {"temperature": 24, "humidity": 65},
        }

        decision = {
            "decisions": {
                "dose": {
                    "pump_a": {"ml": 3.0, "reason": "EC adjustment"},
                    "ph_pump": {"ml": 1.5, "reason": "pH correction"},
                },
                "fan": {"fan_speed": 60},
            }
        }

        summary = llm_agent._create_decision_summary(sensor_data, decision)

        assert "pH 6.2" in summary
        assert "EC 1.8" in summary
        assert "temp 24" in summary
        assert "pump_a 3.0ml" in summary
        assert "fan 60%" in summary


class TestLLMIntegration:
    """Integration tests for LLM agent with other components"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_llm_with_vector_memory(self, mock_chromadb):
        """Test LLM agent integration with vector memory"""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("app.llm_agent.VectorMemory") as mock_vector_class:
                mock_vector_instance = MagicMock()
                mock_vector_instance.search = AsyncMock(
                    return_value=[
                        {"summary": "Similar pH conditions", "outcome": "successful"}
                    ]
                )
                mock_vector_instance.store = AsyncMock(return_value="memory_id")
                mock_vector_class.return_value = mock_vector_instance

                agent = LLMAgent()
                agent.client = MagicMock()
                agent.client.chat.completions.create.return_value.choices[
                    0
                ].message.content = json.dumps(
                    {
                        "decisions": {
                            "dose": {"pump_a": {"ml": 2.0, "reason": "test"}}
                        },
                        "reasoning": "test reasoning",
                        "confidence": 0.8,
                    }
                )

                # Mock KPI calculator
                agent.kpi_calc = MagicMock()
                agent.kpi_calc.calculate_current_kpis = AsyncMock(
                    return_value={"health_score": 0.8}
                )

                sensor_data = {
                    "water": {"ph": 6.0, "ec": 1.6},
                    "air": {"temperature": 24.0},
                }
                config = {"targets": {"ph_target": 6.0}}

                result = await agent.make_decision(sensor_data, config)

                assert result is not None
                # Verify memory was searched and stored
                mock_vector_instance.search.assert_called_once()
                mock_vector_instance.store.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_llm_decision_consistency(
        self, llm_agent, mock_sensor_data, mock_config
    ):
        """Test that LLM decisions are consistent for similar inputs"""
        # Mock dependencies
        llm_agent.vector_memory = MagicMock()
        llm_agent.vector_memory.search = AsyncMock(return_value=[])
        llm_agent.kpi_calc = MagicMock()
        llm_agent.kpi_calc.calculate_current_kpis = AsyncMock(
            return_value={"health_score": 0.8}
        )

        # Make multiple decisions with same input
        results = []
        for _ in range(3):
            result = await llm_agent.make_decision(mock_sensor_data, mock_config)
            results.append(result)

        # All results should have similar structure
        for result in results:
            assert "decisions" in result
            assert "reasoning" in result
            assert "confidence" in result
