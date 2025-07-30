"""
Sensor input/output interface with hardware abstraction
"""

import logging
import random
import time
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import RPi.GPIO as GPIO
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    import adafruit_bme280
    import adafruit_dht
    import serial
    from w1thermsensor import W1ThermSensor

    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    logging.warning("Hardware libraries not available, using mock data")

# Shared hardware mappings
HARDWARE_PINS: Dict[str, int] = {  # pragma: no cover - constants
    "pump_a": 17,
    "pump_b": 27,
    "ph_pump": 22,
    "refill_pump": 25,
    "fan_pwm": 18,
    "led_pwm": 13,
    "float_hi": 23,
    "float_lo": 24,
}

I2C_ADDRESSES: Dict[str, int] = {  # pragma: no cover - constants
    "ads1115": 0x48,
    "bme280": 0x76,
}

UART_PORTS: Dict[str, str] = {  # pragma: no cover - constants
    "co2": "/dev/ttyAMA0",
}

ONEWIRE_IDS: Dict[str, Optional[str]] = {  # pragma: no cover - constants
    "ds18b20": None,  # Default sensor
}

ADS_CHANNELS: Dict[str, int] = {  # pragma: no cover - constants
    "ph": 0,
    "ec": 1,
    "turbidity": 2,
    "lux": 3,
}


class SensorInterface:
    """Manages all sensor inputs with mock capability"""

    def __init__(self, mock: bool = False):
        self.mock = mock or not HARDWARE_AVAILABLE
        self.logger = logging.getLogger(__name__)

        if not self.mock:
            self._init_hardware()
        else:
            self.logger.info("Running in mock mode")

    def _init_hardware(self):  # pragma: no cover - hardware init
        """Initialize all hardware sensors"""
        try:
            # GPIO setup
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(HARDWARE_PINS["float_hi"], GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(HARDWARE_PINS["float_lo"], GPIO.IN, pull_up_down=GPIO.PUD_UP)

            # I2C setup
            i2c = busio.I2C(board.SCL, board.SDA)

            # ADS1115 ADC
            self.ads = ADS.ADS1115(i2c, address=I2C_ADDRESSES["ads1115"])
            self.ads_channels = {
                name: AnalogIn(self.ads, getattr(ADS, f"P{ch}"))
                for name, ch in ADS_CHANNELS.items()
            }

            # BME280 environmental sensor
            self.bme280 = adafruit_bme280.Adafruit_BME280_I2C(
                i2c, address=I2C_ADDRESSES["bme280"]
            )

            # DHT22 humidity sensor (backup)
            self.dht = adafruit_dht.DHT22(board.D2)

            # DS18B20 1-wire temperature
            sensor_id = ONEWIRE_IDS.get("ds18b20")
            if sensor_id is not None:
                self.ds18b20 = W1ThermSensor(sensor_id)
            else:
                self.ds18b20 = W1ThermSensor()

            # MH-Z19B CO2 sensor
            self.co2_serial = serial.Serial(UART_PORTS["co2"], 9600, timeout=1)

            self.logger.info("Hardware sensors initialized")

        except Exception as e:
            self.logger.error(f"Hardware initialization failed: {e}")
            self.logger.info("Falling back to mock mode")
            self.mock = True

    async def read_all(self) -> Dict[str, Any]:
        """Read all sensors and return structured data"""
        if self.mock:
            return self._mock_sensor_data()

        try:
            # Read water sensors
            water_data = await self._read_water_sensors()

            # Read air sensors
            air_data = await self._read_air_sensors()

            # Read root temperature
            root_data = await self._read_root_sensors()

            # Read light sensors
            light_data = await self._read_light_sensors()

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "water": water_data,
                "air": air_data,
                "root": root_data,
                "light": light_data,
            }

        except Exception as e:
            self.logger.error(f"Sensor read error: {e}")
            return self._mock_sensor_data()

    async def _read_water_sensors(self) -> Dict[str, Any]:
        """Read water-related sensors"""
        # Read pH from ADS1115 channel 0
        ph_voltage = self.ads_channels["ph"].voltage
        ph_value = self._voltage_to_ph(ph_voltage)

        # Read EC from ADS1115 channel 1
        ec_voltage = self.ads_channels["ec"].voltage
        ec_value = self._voltage_to_ec(ec_voltage)

        # Read turbidity from ADS1115 channel 2
        turbidity_voltage = self.ads_channels["turbidity"].voltage
        turbidity_value = self._voltage_to_turbidity(turbidity_voltage)

        # Read water temperature from DS18B20
        water_temp = self.ds18b20.get_temperature()

        # Read float switches
        level_high = not GPIO.input(HARDWARE_PINS["float_hi"])  # Inverted logic
        level_low = not GPIO.input(HARDWARE_PINS["float_lo"])

        return {
            "ph": round(ph_value, 2),
            "ec": round(ec_value, 2),
            "turbidity": round(turbidity_value, 1),
            "temperature": round(water_temp, 1),
            "level_high": level_high,
            "level_low": level_low,
        }

    async def _read_air_sensors(self) -> Dict[str, Any]:
        """Read air environment sensors"""
        # BME280 readings
        temperature = self.bme280.temperature
        humidity = self.bme280.relative_humidity
        pressure = self.bme280.pressure

        # Read CO2 from MH-Z19B
        co2_value = self._read_co2_sensor()

        return {
            "temperature": round(temperature, 1),
            "humidity": round(humidity, 1),
            "pressure": round(pressure, 1),
            "co2": co2_value,
        }

    async def _read_root_sensors(self) -> Dict[str, Any]:
        """Read root zone sensors"""
        try:
            root_temp = self.ds18b20.get_temperature()
        except Exception:
            root_temp = 22.0  # Fallback

        return {"temperature": round(root_temp, 1)}

    async def _read_light_sensors(self) -> Dict[str, Any]:
        """Read light-related sensors"""
        # Read light sensor from ADS1115 channel 3
        lux_voltage = self.ads_channels["lux"].voltage
        lux_value = self._voltage_to_lux(lux_voltage)

        # Get current LED power (would be read from PWM controller)
        led_power = 75  # Mock value, would read from actual controller

        return {"lux": round(lux_value, 0), "led_power": led_power}

    def _read_co2_sensor(self) -> int:
        """Read CO2 from MH-Z19B sensor"""
        try:
            # Send read command to MH-Z19B
            self.co2_serial.write(b"\xff\x01\x86\x00\x00\x00\x00\x00\x79")
            response = self.co2_serial.read(9)

            if len(response) == 9 and response[0] == 0xFF and response[1] == 0x86:
                co2_value = (response[2] << 8) | response[3]
                return co2_value
            else:
                return 400  # Fallback value

        except Exception as e:
            self.logger.error(f"CO2 sensor read error: {e}")
            return 400

    def _voltage_to_ph(self, voltage: float) -> float:
        """Convert voltage to pH value"""
        # pH probe calibration: pH = -5.7 * V + 21.34
        return max(0, min(14, -5.7 * voltage + 21.34))

    def _voltage_to_ec(self, voltage: float) -> float:
        """Convert voltage to EC value in mS/cm"""
        # EC probe calibration: EC = 2.5 * V
        return max(0, min(5, 2.5 * voltage))

    def _voltage_to_turbidity(self, voltage: float) -> float:
        """Convert voltage to turbidity in NTU"""
        # Turbidity sensor calibration
        return max(0, (5 - voltage) * 1000 / 5)

    def _voltage_to_lux(self, voltage: float) -> float:
        """Convert voltage to lux value"""
        # Light sensor calibration
        return max(0, voltage * 20000)

    def _mock_sensor_data(self) -> Dict[str, Any]:
        """Generate realistic mock sensor data"""
        time.time()

        # Simulate daily light cycle
        hour = datetime.now().hour
        light_factor = max(0, min(1, (hour - 6) / 6)) * max(0, min(1, (18 - hour) / 6))

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "water": {
                "ph": round(6.0 + random.gauss(0, 0.1), 2),
                "ec": round(1.8 + random.gauss(0, 0.05), 2),
                "turbidity": round(5 + random.gauss(0, 1), 1),
                "temperature": round(22 + random.gauss(0, 0.5), 1),
                "level_high": True,
                "level_low": True,
            },
            "air": {
                "temperature": round(24 + random.gauss(0, 1), 1),
                "humidity": round(65 + random.gauss(0, 5), 1),
                "pressure": round(1013 + random.gauss(0, 10), 1),
                "co2": int(400 + random.gauss(0, 50)),
            },
            "root": {"temperature": round(21 + random.gauss(0, 0.5), 1)},
            "light": {
                "lux": round(light_factor * 30000 + random.gauss(0, 1000), 0),
                "led_power": int(light_factor * 100),
            },
        }

    async def calibrate_sensor(
        self, sensor: str, calibration_data: Dict[str, float]
    ) -> bool:  # pragma: no cover - placeholder
        """Calibrate a specific sensor"""
        self.logger.info(f"Calibrating sensor: {sensor}")
        # In real implementation, would store calibration coefficients
        return True

    def __del__(self):  # pragma: no cover - cleanup
        """Cleanup GPIO on destruction"""
        if not self.mock and HARDWARE_AVAILABLE:
            try:
                GPIO.cleanup()
                if hasattr(self, "co2_serial"):
                    self.co2_serial.close()
            except Exception:
                pass


__all__ = [  # pragma: no cover - export list
    "SensorInterface",
    "HARDWARE_PINS",
    "I2C_ADDRESSES",
    "UART_PORTS",
    "ONEWIRE_IDS",
    "ADS_CHANNELS",
]
