"""
Pytest configuration and fixtures for hydroponic controller tests
"""

import asyncio
import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

# Mock hardware imports
import sys

sys.modules["RPi"] = MagicMock()
sys.modules["RPi.GPIO"] = MagicMock()
sys.modules["board"] = MagicMock()
sys.modules["busio"] = MagicMock()
sys.modules["adafruit_ads1x15"] = MagicMock()
sys.modules["adafruit_ads1x15.ads1115"] = MagicMock()
sys.modules["adafruit_ads1x15.analog_in"] = MagicMock()
sys.modules["adafruit_bme280"] = MagicMock()
sys.modules["adafruit_dht"] = MagicMock()
sys.modules["serial"] = MagicMock()
sys.modules["w1thermsensor"] = MagicMock()
sys.modules["chromadb"] = MagicMock()

# Set test environment
os.environ["MOCK_HARDWARE"] = "true"
os.environ["USE_LLM"] = "false"


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_sensor_data():
    """Sample sensor data for testing"""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "water": {
            "ph": 6.0,
            "ec": 1.6,
            "temperature": 22.0,
            "turbidity": 5.0,
            "level_high": True,
            "level_low": True,
        },
        "air": {"temperature": 24.0, "humidity": 60.0, "pressure": 1013.0, "co2": 800},
        "root": {"temperature": 21.0},
        "light": {"lux": 25000, "led_power": 80},
    }


@pytest.fixture
def mock_config():
    """Sample configuration for testing"""
    return {
        "version": "1.0.0",
        "grow_phase": "vegetative",
        "reservoir_volume_l": 20,
        "baseline_dosing_ml_per_week": 50,
        "targets": {
            "ph_target": 6.0,
            "ph_min": 5.5,
            "ph_max": 6.5,
            "ec_target": 1.6,
            "ec_min": 1.2,
            "ec_max": 2.0,
            "temp_target": 22,
            "temp_min": 18,
            "temp_max": 26,
            "humidity_target": 60,
            "humidity_min": 50,
            "humidity_max": 70,
            "co2_target": 800,
            "co2_min": 400,
            "co2_max": 1200,
        },
        "schedules": {
            "light_hours": 16,
            "light_start_time": "06:00",
            "light_power_day": 80,
            "light_power_night": 0,
            "fan_base_speed": 20,
            "sensor_poll_interval_s": 60,
            "control_loop_interval_s": 600,
        },
        "hardware": {
            "gpio_pins": {
                "pump_a": 17,
                "pump_b": 27,
                "ph_pump": 22,
                "refill_pump": 25,
                "fan_pwm": 18,
                "led_pwm": 13,
                "float_hi": 23,
                "float_lo": 24,
            },
            "flow_rates_ml_per_s": {
                "pump_a": 2.5,
                "pump_b": 2.5,
                "ph_pump": 1.0,
                "refill_pump": 50.0,
            },
        },
    }


@pytest.fixture
def temp_db():
    """Temporary database for testing"""
    from app.memory.db import Database

    # Create temporary database file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_file.close()

    db = Database(temp_file.name)

    yield db

    # Cleanup
    try:
        asyncio.run(db.close())
    except Exception:
        pass

    try:
        os.unlink(temp_file.name)
    except Exception:
        pass


@pytest.fixture
def mock_openai():
    """Mock OpenAI API responses"""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]

    # Load mocked response content from JSON file for reuse
    mock_file = Path("tests/data/o3_mock.json")
    with mock_file.open("r") as f:
        mock_payload = json.load(f)

    mock_response.choices[0].message.content = json.dumps(mock_payload)

    with patch("openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_chromadb():
    """Mock ChromaDB for vector memory testing"""
    mock_client = MagicMock()
    mock_collection = MagicMock()

    # Mock collection methods
    mock_collection.count.return_value = 10
    mock_collection.add = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["test document 1", "test document 2"]],
        "metadatas": [
            [
                {"timestamp": "2023-01-01T12:00:00", "data": '{"test": "data1"}'},
                {"timestamp": "2023-01-01T13:00:00", "data": '{"test": "data2"}'},
            ]
        ],
        "distances": [[0.1, 0.2]],
    }
    mock_collection.get.return_value = {
        "ids": ["id1", "id2"],
        "metadatas": [
            {"timestamp": "2023-01-01T12:00:00", "data": '{"test": "data1"}'},
            {"timestamp": "2023-01-01T13:00:00", "data": '{"test": "data2"}'},
        ],
    }

    mock_client.get_or_create_collection.return_value = mock_collection

    with patch("chromadb.PersistentClient", return_value=mock_client):
        yield mock_collection


@pytest.fixture
def mock_gpio():
    """Mock GPIO operations"""
    with patch("RPi.GPIO") as mock_gpio:
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.IN = 1
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PUD_UP = 22
        yield mock_gpio


@pytest.fixture
def sample_kpis():
    """Sample KPI data for testing"""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "ph_in_spec": 1.0,
        "ec_in_spec": 0.95,
        "temp_in_spec": 1.0,
        "humidity_in_spec": 0.9,
        "co2_in_spec": 0.8,
        "health_score": 0.93,
        "ph_value": 6.0,
        "ec_value": 1.6,
        "temp_value": 22.0,
        "humidity_value": 60.0,
        "co2_value": 800,
        "ml_total_24h": 15.5,
        "pump_a_ml_24h": 8.0,
        "pump_b_ml_24h": 5.0,
        "ph_pump_ml_24h": 2.5,
        "days_since_reservoir_change": 3,
    }


@pytest.fixture
def mock_serial():
    """Mock serial communication for CO2 sensor"""
    with patch("serial.Serial") as mock_serial:
        mock_instance = MagicMock()
        mock_instance.write = MagicMock()
        mock_instance.read.return_value = (
            b"\xff\x86\x01\x90\x00\x00\x00\x00\x79"  # 400 ppm CO2
        )
        mock_serial.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_camera():
    """Mock camera operations"""
    with patch("cv2.VideoCapture") as mock_cap:
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = True
        mock_instance.read.return_value = (True, MagicMock())  # Success, frame
        mock_cap.return_value = mock_instance
        yield mock_instance


# Pytest configuration
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line("markers", "asyncio: mark test as async")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers"""
    for item in items:
        # Add asyncio marker to async tests
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)

        # Add slow marker to tests that might be slow
        if "llm" in item.name.lower() or "integration" in item.name.lower():
            item.add_marker(pytest.mark.slow)
