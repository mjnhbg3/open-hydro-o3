#!/usr/bin/env python3
"""
Shadow validation script - replays sensor data to validate system behavior
"""

import argparse
import asyncio
import json
import logging
import sys
import csv
from datetime import datetime
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sensor_io import SensorInterface
from app.actuators import ActuatorController
from app.llm_agent import LLMAgent
from app.rules import RulesEngine
from app.memory.db import Database
from app.memory.kpis import KPICalculator
from app.utils import setup_logging
from app.utils import load_config


class ShadowValidator:
    """Shadow validation system for testing with historical data"""
    
    def __init__(self, data_file: str = None):
        self.data_file = data_file or "tests/data/sensors_sample.csv"
        self.config = load_config()
        self.db = None
        self.sensors = None
        self.actuators = None
        self.llm_agent = None
        self.rules_engine = None
        self.kpi_calc = None
        self.logger = logging.getLogger(__name__)
        
        # Validation results
        self.results = {
            "start_time": datetime.utcnow().isoformat(),
            "total_readings": 0,
            "in_spec_readings": 0,
            "safety_violations": 0,
            "actions_taken": 0,
            "errors": [],
            "performance_metrics": {}
        }
    
    async def initialize(self):
        """Initialize all components in mock mode"""
        try:
            self.db = Database(":memory:")  # Use in-memory DB for testing
            await self.db.init()
            
            # All components in mock mode for validation
            self.sensors = SensorInterface(mock=True)
            self.actuators = ActuatorController(mock=True)
            self.kpi_calc = KPICalculator(self.db)
            self.rules_engine = RulesEngine(self.config, self.db)
            
            # LLM agent in test mode (no API calls)
            try:
                self.llm_agent = LLMAgent()
            except Exception as e:
                self.logger.warning(f"LLM agent not available for validation: {e}")
                self.llm_agent = None
            
            self.logger.info("Shadow validator initialized")
            
        except Exception as e:
            self.logger.error(f"Shadow validator initialization failed: {e}")
            raise
    
    async def run_validation(self) -> dict:
        """Run complete shadow validation"""
        try:
            self.logger.info(f"Starting shadow validation with data file: {self.data_file}")
            
            # Load sensor data
            sensor_readings = self._load_sensor_data()
            
            if not sensor_readings:
                raise ValueError("No sensor data loaded")
            
            self.results["total_readings"] = len(sensor_readings)
            
            # Process each reading
            for i, reading in enumerate(sensor_readings):
                try:
                    await self._process_reading(reading, i)
                except Exception as e:
                    self.logger.error(f"Error processing reading {i}: {e}")
                    self.results["errors"].append(f"Reading {i}: {str(e)}")
            
            # Calculate final metrics
            await self._calculate_final_metrics()
            
            self.results["end_time"] = datetime.utcnow().isoformat()
            self.results["success"] = len(self.results["errors"]) == 0
            
            # Validate results against requirements
            validation_passed = self._validate_requirements()
            self.results["validation_passed"] = validation_passed
            
            self.logger.info(f"Shadow validation completed: {validation_passed}")
            
            return self.results
            
        except Exception as e:
            self.logger.error(f"Shadow validation failed: {e}")
            self.results["error"] = str(e)
            self.results["success"] = False
            return self.results
    
    def _load_sensor_data(self) -> list:
        """Load sensor data from CSV file"""
        readings = []
        
        try:
            data_path = Path(self.data_file)
            
            if not data_path.exists():
                # Create sample data if file doesn't exist
                self._create_sample_data(data_path)
            
            with open(data_path, 'r') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Convert string values to appropriate types
                    reading = {
                        "timestamp": row["timestamp"],
                        "water": {
                            "ph": float(row["ph"]),
                            "ec": float(row["ec"]),
                            "temperature": float(row["water_temp"]),
                            "turbidity": float(row["turbidity"]),
                            "level_high": row["level_high"].lower() == "true",
                            "level_low": row["level_low"].lower() == "true"
                        },
                        "air": {
                            "temperature": float(row["air_temp"]),
                            "humidity": float(row["humidity"]),
                            "pressure": float(row["pressure"]),
                            "co2": int(row["co2"])
                        },
                        "root": {
                            "temperature": float(row["root_temp"])
                        },
                        "light": {
                            "lux": float(row["lux"]),
                            "led_power": int(row["led_power"])
                        }
                    }
                    
                    readings.append(reading)
            
            self.logger.info(f"Loaded {len(readings)} sensor readings")
            return readings
            
        except Exception as e:
            self.logger.error(f"Failed to load sensor data: {e}")
            return []
    
    def _create_sample_data(self, data_path: Path):
        """Create sample sensor data for testing"""
        import random
        from datetime import timedelta
        
        data_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate 24 hours of sample data (1440 readings at 1-minute intervals)
        start_time = datetime.utcnow() - timedelta(days=1)
        
        with open(data_path, 'w', newline='') as f:
            fieldnames = [
                "timestamp", "ph", "ec", "water_temp", "turbidity", "level_high", "level_low",
                "air_temp", "humidity", "pressure", "co2", "root_temp", "lux", "led_power"
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for i in range(1440):  # 24 hours of minute-by-minute data
                timestamp = start_time + timedelta(minutes=i)
                
                # Simulate realistic but occasionally problematic values
                ph_base = 6.0
                ec_base = 1.6
                
                # Add some drift and noise
                if i > 720:  # After 12 hours, introduce some drift
                    ph_base += random.gauss(0, 0.1)
                    ec_base += random.gauss(0, 0.05)
                
                # Occasionally create out-of-spec conditions
                if random.random() < 0.05:  # 5% chance of issues
                    ph_base += random.choice([-0.5, 0.5])
                
                if random.random() < 0.03:  # 3% chance of EC issues
                    ec_base += random.choice([-0.3, 0.3])
                
                row = {
                    "timestamp": timestamp.isoformat(),
                    "ph": round(max(4.0, min(8.0, ph_base + random.gauss(0, 0.05))), 2),
                    "ec": round(max(0.5, min(3.0, ec_base + random.gauss(0, 0.02))), 2),
                    "water_temp": round(22 + random.gauss(0, 0.5), 1),
                    "turbidity": round(5 + random.gauss(0, 1), 1),
                    "level_high": "true",  # Assume good water level
                    "level_low": "true",
                    "air_temp": round(24 + random.gauss(0, 1), 1),
                    "humidity": round(max(30, min(90, 60 + random.gauss(0, 5))), 1),
                    "pressure": round(1013 + random.gauss(0, 10), 1),
                    "co2": max(300, min(1500, int(800 + random.gauss(0, 100)))),
                    "root_temp": round(21 + random.gauss(0, 0.5), 1),
                    "lux": max(0, int(25000 + random.gauss(0, 5000))),
                    "led_power": 80 if 6 <= timestamp.hour <= 22 else 0
                }
                
                writer.writerow(row)
        
        self.logger.info(f"Created sample data file: {data_path}")
    
    async def _process_reading(self, reading: dict, index: int):
        """Process a single sensor reading"""
        try:
            # Store reading in database
            await self.db.store_sensor_reading(reading)
            
            # Check if reading is in spec
            in_spec = self._check_reading_in_spec(reading)
            if in_spec:
                self.results["in_spec_readings"] += 1
            
            # Check for safety violations
            safety_violation = self._check_safety_violations(reading)
            if safety_violation:
                self.results["safety_violations"] += 1
                # Safety violations are tracked but not treated as script errors
            
            # Run control logic every 10 readings (simulating 10-minute intervals)
            if index % 10 == 0:
                await self._run_control_logic(reading)
            
        except Exception as e:
            self.logger.error(f"Error processing reading {index}: {e}")
            raise
    
    def _check_reading_in_spec(self, reading: dict) -> bool:
        """Check if reading is within specification"""
        try:
            targets = self.config.get('targets', {})
            
            water = reading.get('water', {})
            air = reading.get('air', {})
            
            ph_in_spec = targets.get('ph_min', 5.5) <= water.get('ph', 0) <= targets.get('ph_max', 6.5)
            ec_in_spec = targets.get('ec_min', 1.2) <= water.get('ec', 0) <= targets.get('ec_max', 2.0)
            temp_in_spec = targets.get('temp_min', 18) <= air.get('temperature', 0) <= targets.get('temp_max', 26)
            
            return ph_in_spec and ec_in_spec and temp_in_spec
            
        except Exception:
            return False
    
    def _check_safety_violations(self, reading: dict) -> str:
        """Check for safety limit violations"""
        try:
            water = reading.get('water', {})
            air = reading.get('air', {})
            
            # Check absolute safety limits
            if water.get('ph', 7) < 4.0 or water.get('ph', 7) > 8.0:
                return f"pH {water.get('ph')} outside safety limits (4.0-8.0)"
            
            if water.get('ec', 1.6) < 0.5 or water.get('ec', 1.6) > 3.0:
                return f"EC {water.get('ec')} outside safety limits (0.5-3.0)"
            
            if air.get('temperature', 22) < 10 or air.get('temperature', 22) > 35:
                return f"Temperature {air.get('temperature')}°C outside safety limits (10-35°C)"
            
            if not water.get('level_high', True) and not water.get('level_low', True):
                return "Critical water level - both sensors indicate low"
            
            return None
            
        except Exception as e:
            return f"Safety check error: {e}"
    
    async def _run_control_logic(self, reading: dict):
        """Run control logic for a reading"""
        try:
            # Calculate KPIs
            kpis = await self.kpi_calc.calculate_current_kpis(reading, self.config.get('targets', {}))
            
            # Run rules engine
            rules_result = await self.rules_engine.evaluate_rules(reading, kpis)
            
            # Execute any recommended actions
            actions = rules_result.get('actions', {})
            
            if actions:
                self.results["actions_taken"] += 1
                
                # Simulate action execution
                if 'dose' in actions:
                    dose_result = await self.actuators.dose_nutrients(actions['dose'])
                    if dose_result.get('errors'):
                        self.results["errors"].extend(dose_result['errors'])
                
                if 'fan' in actions:
                    await self.actuators.control_fan(actions['fan'].get('fan_speed', 0))
                
                if 'led' in actions:
                    await self.actuators.control_led(actions['led'].get('led_power', 0))
            
        except Exception as e:
            self.logger.error(f"Control logic error: {e}")
            self.results["errors"].append(f"Control logic error: {str(e)}")
    
    async def _calculate_final_metrics(self):
        """Calculate final performance metrics"""
        try:
            total_readings = self.results["total_readings"]
            in_spec_readings = self.results["in_spec_readings"]
            
            if total_readings > 0:
                in_spec_percentage = (in_spec_readings / total_readings) * 100
                
                self.results["performance_metrics"] = {
                    "in_spec_percentage": round(in_spec_percentage, 2),
                    "safety_violation_rate": round((self.results["safety_violations"] / total_readings) * 100, 2),
                    "action_rate": round((self.results["actions_taken"] / (total_readings / 10)) * 100, 2),
                    "error_rate": round((len(self.results["errors"]) / total_readings) * 100, 2)
                }
            
            # Get database statistics
            db_stats = await self.db.get_database_stats()
            self.results["database_stats"] = db_stats
            
        except Exception as e:
            self.logger.error(f"Final metrics calculation failed: {e}")
    
    def _validate_requirements(self) -> bool:
        """Validate against system requirements"""
        try:
            metrics = self.results["performance_metrics"]
            
            # Requirement: ≥95% readings in-spec
            in_spec_ok = metrics.get("in_spec_percentage", 0) >= 95.0
            
            # Requirement: 0 safety limit breaches
            safety_ok = self.results["safety_violations"] == 0
            
            # Requirement: Error rate < 1%
            error_ok = metrics.get("error_rate", 100) < 1.0
            
            self.results["requirements_check"] = {
                "in_spec_requirement": {"passed": in_spec_ok, "value": metrics.get("in_spec_percentage", 0), "threshold": 95.0},
                "safety_requirement": {"passed": safety_ok, "value": self.results["safety_violations"], "threshold": 0},
                "error_requirement": {"passed": error_ok, "value": metrics.get("error_rate", 100), "threshold": 1.0}
            }
            
            return in_spec_ok and safety_ok and error_ok
            
        except Exception as e:
            self.logger.error(f"Requirements validation failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.actuators:
            await self.actuators.shutdown()
        
        if self.db:
            await self.db.close()
        
        self.logger.info("Shadow validator cleanup complete")


async def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='Shadow validation for hydroponic controller')
    parser.add_argument('--data', default='tests/data/sensors_sample.csv', 
                       help='CSV file with sensor data (default: tests/data/sensors_sample.csv)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    setup_logging('DEBUG' if args.verbose else 'INFO')
    logger = logging.getLogger(__name__)
    
    validator = ShadowValidator(args.data)
    
    try:
        logger.info("Starting shadow validation")
        
        await validator.initialize()
        result = await validator.run_validation()
        
        # Print results
        print(json.dumps(result, indent=2, default=str))
        
        if result.get('validation_passed', False):
            logger.info("Shadow validation PASSED")
            exit_code = 0
        else:
            logger.error("Shadow validation FAILED")
            exit_code = 1
        
    except Exception as e:
        logger.error(f"Shadow validation script failed: {e}")
        print(json.dumps({
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, indent=2))
        exit_code = 2
    
    finally:
        await validator.cleanup()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())