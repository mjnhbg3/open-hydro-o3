#!/usr/bin/env python3
"""
Sensor polling script - runs every minute to collect sensor data
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sensor_io import SensorInterface
from app.memory.db import Database
from app.utils import setup_logging, create_alert
from app.utils import load_config


class SensorPoller:
    """Main sensor polling class"""

    def __init__(self):
        self.config = load_config()
        self.db = None
        self.sensors = None
        self.logger = logging.getLogger(__name__)

        # Mock mode for development
        self.mock_mode = os.getenv("MOCK_HARDWARE", "true").lower() == "true"

    async def initialize(self):
        """Initialize database and sensors"""
        try:
            self.db = Database()
            await self.db.init()

            self.sensors = SensorInterface(mock=self.mock_mode)

            self.logger.info("Sensor poller initialized")

        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            raise

    async def poll_sensors(self) -> dict:
        """Poll all sensors and return readings"""
        try:
            # Read all sensor data
            sensor_data = await self.sensors.read_all()

            # Validate sensor data
            validation_result = self._validate_sensor_data(sensor_data)

            if not validation_result["valid"]:
                self.logger.warning(
                    f"Sensor validation issues: {validation_result['warnings']}"
                )

                # Create alert for critical validation failures
                if validation_result["critical"]:
                    alert = create_alert(
                        "error",
                        "sensor",
                        f"Critical sensor validation failures: {validation_result['critical']}",
                        {"sensor_data": sensor_data, "validation": validation_result},
                    )
                    await self.db.store_system_event(alert)

            # Store in database
            reading_id = await self.db.store_sensor_reading(sensor_data)

            self.logger.info(f"Sensor data collected and stored (ID: {reading_id})")

            return {
                "success": True,
                "reading_id": reading_id,
                "sensor_data": sensor_data,
                "validation": validation_result,
            }

        except Exception as e:
            self.logger.error(f"Sensor polling failed: {e}")

            # Store error event
            error_alert = create_alert(
                "error",
                "sensor",
                f"Sensor polling failed: {str(e)}",
                {"error": str(e), "timestamp": datetime.utcnow().isoformat()},
            )

            if self.db:
                try:
                    await self.db.store_system_event(error_alert)
                except Exception as db_error:
                    self.logger.error(f"Failed to store error event: {db_error}")

            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def _validate_sensor_data(self, sensor_data: dict) -> dict:
        """Validate sensor readings for reasonableness"""
        warnings = []
        critical = []

        try:
            water = sensor_data.get("water", {})
            air = sensor_data.get("air", {})

            # pH validation
            ph = water.get("ph")
            if ph is not None:
                if ph < 3.0 or ph > 10.0:
                    critical.append(f"pH {ph} outside possible range (3.0-10.0)")
                elif ph < 4.5 or ph > 8.0:
                    warnings.append(
                        f"pH {ph} outside typical hydroponic range (4.5-8.0)"
                    )

            # EC validation
            ec = water.get("ec")
            if ec is not None:
                if ec < 0.0 or ec > 5.0:
                    critical.append(f"EC {ec} outside possible range (0.0-5.0)")
                elif ec < 0.8 or ec > 3.0:
                    warnings.append(f"EC {ec} outside typical range (0.8-3.0)")

            # Temperature validation
            water_temp = water.get("temperature")
            if water_temp is not None:
                if water_temp < 0 or water_temp > 40:
                    critical.append(
                        f"Water temp {water_temp}°C outside safe range (0-40°C)"
                    )
                elif water_temp < 15 or water_temp > 30:
                    warnings.append(
                        f"Water temp {water_temp}°C outside optimal range (15-30°C)"
                    )

            air_temp = air.get("temperature")
            if air_temp is not None:
                if air_temp < -10 or air_temp > 50:
                    critical.append(
                        f"Air temp {air_temp}°C outside sensor range (-10-50°C)"
                    )
                elif air_temp < 16 or air_temp > 30:
                    warnings.append(
                        f"Air temp {air_temp}°C outside optimal range (16-30°C)"
                    )

            # Humidity validation
            humidity = air.get("humidity")
            if humidity is not None:
                if humidity < 0 or humidity > 100:
                    critical.append(
                        f"Humidity {humidity}% outside possible range (0-100%)"
                    )
                elif humidity > 85:
                    warnings.append(f"High humidity {humidity}% (>85%) - mold risk")
                elif humidity < 30:
                    warnings.append(
                        f"Low humidity {humidity}% (<30%) - plant stress risk"
                    )

            # Water level validation
            level_high = water.get("level_high")
            level_low = water.get("level_low")

            if level_low is False:
                critical.append(
                    "Water level critically low - refill needed immediately"
                )
            elif level_high is False and level_low is True:
                warnings.append("Water level low - refill recommended")

            return {
                "valid": len(critical) == 0,
                "warnings": warnings,
                "critical": critical,
            }

        except Exception as e:
            return {
                "valid": False,
                "warnings": [],
                "critical": [f"Validation error: {e}"],
            }

    async def cleanup(self):
        """Cleanup resources"""
        if self.db:
            await self.db.close()

        if self.sensors:
            # Sensors cleanup handled by destructor
            pass

        self.logger.info("Sensor poller cleanup complete")


async def main():
    """Main execution function"""
    setup_logging()
    logger = logging.getLogger(__name__)

    poller = SensorPoller()

    try:
        logger.info("Starting sensor poll cycle")

        await poller.initialize()
        result = await poller.poll_sensors()

        if result["success"]:
            logger.info("Sensor poll completed successfully")
            print(json.dumps(result, indent=2))
            exit_code = 0
        else:
            logger.error(f"Sensor poll failed: {result.get('error')}")
            print(json.dumps(result, indent=2))
            exit_code = 1

    except Exception as e:
        logger.error(f"Sensor poll script failed: {e}")
        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        exit_code = 2

    finally:
        await poller.cleanup()

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
