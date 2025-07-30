"""
Actuator control interface with safety limits
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from .sensor_io import HARDWARE_PINS

try:
    import RPi.GPIO as GPIO

    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    logging.warning("GPIO library not available, using mock mode")


class ActuatorController:
    """Controls all system actuators with safety limits"""

    # Safety limits (ml per operation)
    SAFETY_LIMITS = {
        "pump_a_max_ml": 50,
        "pump_b_max_ml": 50,
        "ph_pump_max_ml": 20,
        "refill_max_ml": 1000,
        "daily_dose_limit": 200,  # Total daily dosing limit
        "fan_max_speed": 100,
        "led_max_power": 100,
    }

    # Pump flow rates (ml per second)
    FLOW_RATES = {"pump_a": 2.5, "pump_b": 2.5, "ph_pump": 1.0, "refill_pump": 50.0}

    def __init__(self, mock: bool = False):
        self.mock = mock or not HARDWARE_AVAILABLE
        self.logger = logging.getLogger(__name__)
        self.daily_doses = {}  # Track daily dosing amounts
        self.last_dose_reset = datetime.now().date()
        self.pins = HARDWARE_PINS

        # Current actuator states
        self.states = {
            "pumps": {
                "pump_a": False,
                "pump_b": False,
                "ph_pump": False,
                "refill_pump": False,
            },
            "fan_speed": 0,
            "led_power": 0,
            "last_updated": datetime.utcnow().isoformat(),
        }

        if not self.mock:
            self._init_hardware()
        else:
            self.logger.info("Running actuators in mock mode")

    def _init_hardware(self):  # pragma: no cover - hardware initialization
        """Initialize GPIO pins for actuators"""
        try:
            GPIO.setmode(GPIO.BCM)

            # Setup pump control pins
            for pump, pin in self.pins.items():
                if "pump" in pump:
                    GPIO.setup(pin, GPIO.OUT)
                    GPIO.output(pin, GPIO.LOW)

            # Setup PWM pins
            GPIO.setup(self.pins["fan_pwm"], GPIO.OUT)
            GPIO.setup(self.pins["led_pwm"], GPIO.OUT)

            # Initialize PWM
            self.fan_pwm = GPIO.PWM(self.pins["fan_pwm"], 1000)  # 1kHz
            self.led_pwm = GPIO.PWM(self.pins["led_pwm"], 1000)  # 1kHz

            self.fan_pwm.start(0)
            self.led_pwm.start(0)

            self.logger.info("Actuator hardware initialized")

        except Exception as e:
            self.logger.error(f"Actuator hardware init failed: {e}")
            self.logger.info("Falling back to mock mode")
            self.mock = True

    async def dose_nutrients(self, dosing_commands: Dict[str, Any]) -> Dict[str, Any]:
        """Execute nutrient dosing commands with safety checks"""
        self._reset_daily_doses_if_needed()

        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "executed": {},
            "skipped": {},
            "errors": [],
        }

        for pump_name, dose_data in dosing_commands.items():
            if pump_name not in ["pump_a", "pump_b", "ph_pump", "refill"]:
                continue

            ml_amount = dose_data.get("ml", 0)
            reason = dose_data.get("reason", "No reason provided")

            # Safety checks
            safety_check = self._check_dosing_safety(pump_name, ml_amount)
            if not safety_check["safe"]:
                results["skipped"][pump_name] = {
                    "ml": ml_amount,
                    "reason": safety_check["reason"],
                }
                continue

            # Execute dosing
            try:
                success = await self._execute_pump_dose(pump_name, ml_amount)
                if success:
                    results["executed"][pump_name] = {
                        "ml": ml_amount,
                        "reason": reason,
                        "duration_seconds": ml_amount
                        / self.FLOW_RATES.get(pump_name, 2.5),
                    }

                    # Track daily totals
                    if pump_name not in self.daily_doses:
                        self.daily_doses[pump_name] = 0
                    self.daily_doses[pump_name] += ml_amount

                else:
                    results["errors"].append(f"Failed to execute {pump_name} dosing")

            except Exception as e:
                self.logger.error(f"Error dosing {pump_name}: {e}")
                results["errors"].append(f"{pump_name}: {str(e)}")

        self.states["last_updated"] = datetime.utcnow().isoformat()
        return results

    async def control_fan(
        self, speed_percent: int, duration_minutes: int = None
    ) -> Dict[str, Any]:
        """Control fan speed"""
        speed_percent = max(0, min(100, speed_percent))

        if not self.mock:
            self.fan_pwm.ChangeDutyCycle(speed_percent)

        self.states["fan_speed"] = speed_percent
        self.states["last_updated"] = datetime.utcnow().isoformat()

        self.logger.info(f"Fan set to {speed_percent}%")

        # Auto-shutoff after duration
        if duration_minutes:
            asyncio.create_task(self._auto_fan_shutoff(duration_minutes))

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "fan_speed": speed_percent,
            "duration_minutes": duration_minutes,
        }

    async def control_led(
        self, power_percent: int, schedule: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Control LED power and schedule"""
        power_percent = max(0, min(100, power_percent))

        if not self.mock:
            self.led_pwm.ChangeDutyCycle(power_percent)

        self.states["led_power"] = power_percent
        self.states["last_updated"] = datetime.utcnow().isoformat()

        self.logger.info(f"LED set to {power_percent}%")

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "led_power": power_percent,
            "schedule": schedule,
        }

    async def emergency_stop(self) -> Dict[str, Any]:
        """Emergency stop all actuators"""
        self.logger.warning("EMERGENCY STOP activated")

        # Stop all pumps
        for pump in ["pump_a", "pump_b", "ph_pump", "refill_pump"]:
            if not self.mock:
                GPIO.output(self.pins[pump], GPIO.LOW)
            self.states["pumps"][pump] = False

        # Stop fan and LEDs
        if not self.mock:
            self.fan_pwm.ChangeDutyCycle(0)
            self.led_pwm.ChangeDutyCycle(0)

        self.states["fan_speed"] = 0
        self.states["led_power"] = 0
        self.states["last_updated"] = datetime.utcnow().isoformat()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "action": "emergency_stop",
            "status": "all_actuators_stopped",
        }

    async def get_status(self) -> Dict[str, Any]:
        """Get current actuator status"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "states": self.states.copy(),
            "daily_doses": self.daily_doses.copy(),
            "safety_limits": self.SAFETY_LIMITS.copy(),
            "mock_mode": self.mock,
        }

    def _check_dosing_safety(self, pump_name: str, ml_amount: float) -> Dict[str, Any]:
        """Check if dosing amount is within safety limits"""
        # Check single dose limit
        max_ml_key = f"{pump_name}_max_ml"
        if pump_name == "refill":
            max_ml_key = "refill_max_ml"

        max_single_dose = self.SAFETY_LIMITS.get(max_ml_key, 50)

        if ml_amount > max_single_dose:
            return {
                "safe": False,
                "reason": f"Dose {ml_amount}ml exceeds single dose limit {max_single_dose}ml",
            }

        # Check daily limit (except refill)
        if pump_name != "refill":
            daily_total = self.daily_doses.get(pump_name, 0) + ml_amount
            if daily_total > self.SAFETY_LIMITS["daily_dose_limit"]:
                return {
                    "safe": False,
                    "reason": f'Daily dose limit exceeded: {daily_total}ml > {self.SAFETY_LIMITS["daily_dose_limit"]}ml',
                }

        return {"safe": True, "reason": "Within safety limits"}

    async def _execute_pump_dose(self, pump_name: str, ml_amount: float) -> bool:
        """Execute actual pump dosing"""
        if ml_amount <= 0:
            return True

        flow_rate = self.FLOW_RATES.get(pump_name, 2.5)
        duration_seconds = ml_amount / flow_rate

        self.logger.info(
            f"Dosing {pump_name}: {ml_amount}ml for {duration_seconds:.1f}s"
        )

        try:
            # Turn on pump
            if not self.mock:
                GPIO.output(self.pins[pump_name], GPIO.HIGH)

            self.states["pumps"][pump_name] = True

            # Wait for dosing duration
            await asyncio.sleep(duration_seconds)

            # Turn off pump
            if not self.mock:
                GPIO.output(self.pins[pump_name], GPIO.LOW)

            self.states["pumps"][pump_name] = False

            return True

        except Exception as e:
            self.logger.error(f"Pump {pump_name} dosing failed: {e}")
            # Ensure pump is off
            if not self.mock:
                GPIO.output(self.pins[pump_name], GPIO.LOW)
            self.states["pumps"][pump_name] = False
            return False

    async def _auto_fan_shutoff(self, duration_minutes: int):
        """Auto-shutoff fan after specified duration"""
        await asyncio.sleep(duration_minutes * 60)
        await self.control_fan(0)
        self.logger.info(f"Fan auto-shutoff after {duration_minutes} minutes")

    def _reset_daily_doses_if_needed(self):
        """Reset daily dose counters at midnight"""
        today = datetime.now().date()
        if today > self.last_dose_reset:
            self.daily_doses = {}
            self.last_dose_reset = today
            self.logger.info("Daily dose counters reset")

    async def shutdown(self):  # pragma: no cover - cleanup
        """Graceful shutdown of all actuators"""
        self.logger.info("Shutting down actuators...")
        await self.emergency_stop()

        if not self.mock:
            try:
                self.fan_pwm.stop()
                self.led_pwm.stop()
                GPIO.cleanup()
            except Exception as e:
                self.logger.error(f"GPIO cleanup error: {e}")

    def __del__(self):  # pragma: no cover - cleanup
        """Cleanup on destruction"""
        if not self.mock and HARDWARE_AVAILABLE:
            try:
                if hasattr(self, "fan_pwm"):
                    self.fan_pwm.stop()
                if hasattr(self, "led_pwm"):
                    self.led_pwm.stop()
                GPIO.cleanup()
            except Exception:
                pass
