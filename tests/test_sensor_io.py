from unittest.mock import MagicMock

import pytest

from app.sensor_io import SensorInterface


def test_voltage_conversions():
    si = SensorInterface(mock=True)
    assert si._voltage_to_ph(2.0) <= 14
    assert si._voltage_to_ph(0.0) >= 0
    assert si._voltage_to_ec(1.0) == 2.5
    assert si._voltage_to_turbidity(4.5) >= 0
    assert si._voltage_to_lux(0.5) == 10000


def test_mock_sensor_data_keys():
    si = SensorInterface(mock=True)
    data = si._mock_sensor_data()
    assert set(data.keys()) == {"timestamp", "water", "air", "root", "light"}


def test_read_co2_sensor_good():
    si = SensorInterface(mock=True)
    si.mock = False
    si.co2_serial = MagicMock()
    si.co2_serial.read.return_value = b"\xff\x86\x01\x90\x00\x00\x00\x00\x79"
    value = si._read_co2_sensor()
    assert value == 400


def test_read_co2_sensor_bad(monkeypatch):
    si = SensorInterface(mock=True)
    si.mock = False
    si.co2_serial = MagicMock()
    si.co2_serial.read.return_value = b"bad"
    value = si._read_co2_sensor()
    assert value == 400


@pytest.mark.asyncio
async def test_read_all_returns_mock():
    si = SensorInterface(mock=True)
    data = await si.read_all()
    assert "water" in data and "air" in data


@pytest.mark.asyncio
async def test_read_water_air_light(monkeypatch):
    si = SensorInterface(mock=True)
    si.mock = False
    si.ads_channels = {
        "ph": MagicMock(voltage=2.0),
        "ec": MagicMock(voltage=1.0),
        "turbidity": MagicMock(voltage=4.0),
        "lux": MagicMock(voltage=0.5),
    }
    si.ds18b20 = MagicMock(get_temperature=MagicMock(return_value=22.5))
    gpio_mock = MagicMock()
    gpio_mock.input.return_value = 0
    monkeypatch.setattr("app.sensor_io.GPIO", gpio_mock)
    si.bme280 = MagicMock(temperature=24.0, relative_humidity=60.0, pressure=1013.0)
    si.co2_serial = MagicMock()
    si.co2_serial.read.return_value = b"\xff\x86\x01\x90\x00\x00\x00\x00\x79"
    water = await si._read_water_sensors()
    air = await si._read_air_sensors()
    light = await si._read_light_sensors()
    assert water["ph"] >= 0
    assert air["co2"] == 400
    assert light["lux"] == 10000
