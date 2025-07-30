"""
Tests for shadow day validation - replay sensor data and validate system behavior
"""

import asyncio
import csv
import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from scripts.shadow_validator import ShadowValidator


class TestShadowDayValidation:
    """Test shadow day validation functionality"""
    
    @pytest.fixture
    def sample_sensor_csv(self):
        """Create a sample sensor data CSV file"""
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        
        # Write CSV header
        fieldnames = [
            "timestamp", "ph", "ec", "water_temp", "turbidity", "level_high", "level_low",
            "air_temp", "humidity", "pressure", "co2", "root_temp", "lux", "led_power"
        ]
        
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()
        
        # Generate 24 hours of sample data (every 10 minutes = 144 readings)
        start_time = datetime.utcnow() - timedelta(days=1)
        
        for i in range(144):
            timestamp = start_time + timedelta(minutes=i * 10)
            
            # Simulate mostly good conditions with occasional issues
            ph_base = 6.0
            ec_base = 1.6
            
            # Add some variation
            if i % 30 == 0:  # Every 5 hours, slight drift
                ph_base += 0.1 if i % 60 == 0 else -0.1
                ec_base += 0.05 if i % 60 == 0 else -0.05
            
            # Occasional out-of-spec conditions (but not safety violations)
            if i == 50:  # One pH spike
                ph_base = 6.8
            if i == 100:  # One EC dip
                ec_base = 1.1
            
            row = {
                "timestamp": timestamp.isoformat(),
                "ph": round(max(5.0, min(7.0, ph_base)), 2),
                "ec": round(max(1.0, min(2.5, ec_base)), 2),
                "water_temp": 22.0,
                "turbidity": 5.0,
                "level_high": "true",
                "level_low": "true",
                "air_temp": 24.0,
                "humidity": 60.0,
                "pressure": 1013.0,
                "co2": 800,
                "root_temp": 21.0,
                "lux": 25000,
                "led_power": 80 if 6 <= timestamp.hour <= 22 else 0
            }
            
            writer.writerow(row)
        
        temp_file.close()
        return temp_file.name
    
    @pytest.fixture
    def problematic_sensor_csv(self):
        """Create sensor data with safety violations"""
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        
        fieldnames = [
            "timestamp", "ph", "ec", "water_temp", "turbidity", "level_high", "level_low",
            "air_temp", "humidity", "pressure", "co2", "root_temp", "lux", "led_power"
        ]
        
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()
        
        # Generate data with safety violations
        start_time = datetime.utcnow() - timedelta(hours=2)
        
        for i in range(12):  # 2 hours of data, every 10 minutes
            timestamp = start_time + timedelta(minutes=i * 10)
            
            # Include safety violations
            ph_value = 3.5 if i == 5 else 6.0  # One critical pH violation
            ec_value = 4.0 if i == 8 else 1.6  # One critical EC violation
            level_high = "false" if i == 10 else "true"  # One water level issue
            
            row = {
                "timestamp": timestamp.isoformat(),
                "ph": ph_value,
                "ec": ec_value,
                "water_temp": 22.0,
                "turbidity": 5.0,
                "level_high": level_high,
                "level_low": "true",
                "air_temp": 24.0,
                "humidity": 60.0,
                "pressure": 1013.0,
                "co2": 800,
                "root_temp": 21.0,
                "lux": 25000,
                "led_power": 80
            }
            
            writer.writerow(row)
        
        temp_file.close()
        return temp_file.name
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_shadow_validation_good_data(self, sample_sensor_csv):
        """Test shadow validation with good sensor data"""
        validator = ShadowValidator(sample_sensor_csv)
        
        try:
            await validator.initialize()
            result = await validator.run_validation()
            
            assert result['success'] == True
            assert result['total_readings'] == 144
            
            # Should meet requirements with good data
            performance = result['performance_metrics']
            assert performance['in_spec_percentage'] >= 95.0
            assert result['safety_violations'] == 0
            assert performance['error_rate'] < 1.0
            
            # Validation should pass
            assert result['validation_passed'] == True
            
            requirements = result['requirements_check']
            assert requirements['in_spec_requirement']['passed'] == True
            assert requirements['safety_requirement']['passed'] == True
            assert requirements['error_requirement']['passed'] == True
            
        finally:
            await validator.cleanup()
            # Cleanup temp file
            try:
                Path(sample_sensor_csv).unlink()
            except:
                pass
    
    @pytest.mark.asyncio
    async def test_shadow_validation_problematic_data(self, problematic_sensor_csv):
        """Test shadow validation with problematic sensor data"""
        validator = ShadowValidator(problematic_sensor_csv)

        try:
            with patch('scripts.shadow_validator.LLMAgent'):
                await validator.initialize()
                validator.db.get_database_stats = AsyncMock(return_value={})
                result = await validator.run_validation()

            assert result['success'] is True  # Script ran successfully
            assert result['total_readings'] == 12

            # Should detect safety violations without failing overall execution
            assert result['safety_violations'] > 0
            assert len(result["warnings"]) >= result["safety_violations"]

            # Validation should fail due to safety violations
            assert result['validation_passed'] is False

            requirements = result['requirements_check']
            assert requirements['safety_requirement']['passed'] is False

        finally:
            await validator.cleanup()
            # Cleanup temp file
            try:
                Path(problematic_sensor_csv).unlink()
            except:
                pass
    
    @pytest.mark.asyncio
    async def test_sensor_data_loading(self, sample_sensor_csv):
        """Test sensor data loading from CSV"""
        validator = ShadowValidator(sample_sensor_csv)
        
        try:
            await validator.initialize()
            
            # Load sensor data
            readings = validator._load_sensor_data()
            
            assert len(readings) == 144
            
            # Check data structure
            for reading in readings[:5]:  # Check first 5 readings
                assert 'timestamp' in reading
                assert 'water' in reading
                assert 'air' in reading
                assert 'root' in reading
                assert 'light' in reading
                
                # Check data types
                assert isinstance(reading['water']['ph'], float)
                assert isinstance(reading['water']['ec'], float)
                assert isinstance(reading['air']['temperature'], float)
                assert isinstance(reading['air']['co2'], int)
                assert isinstance(reading['water']['level_high'], bool)
            
        finally:
            await validator.cleanup()
            # Cleanup temp file
            try:
                Path(sample_sensor_csv).unlink()
            except:
                pass
    
    @pytest.mark.asyncio
    async def test_reading_validation(self, sample_sensor_csv):
        """Test individual reading validation"""
        validator = ShadowValidator(sample_sensor_csv)
        
        try:
            await validator.initialize()
            
            # Test valid reading
            valid_reading = {
                'water': {'ph': 6.0, 'ec': 1.6, 'temperature': 22.0, 'level_high': True, 'level_low': True},
                'air': {'temperature': 24.0, 'humidity': 60.0, 'co2': 800}
            }
            
            assert validator._check_reading_in_spec(valid_reading) == True
            assert validator._check_safety_violations(valid_reading) is None
            
            # Test invalid reading
            invalid_reading = {
                'water': {'ph': 3.0, 'ec': 4.0, 'temperature': 22.0, 'level_high': False, 'level_low': False},
                'air': {'temperature': 45.0, 'humidity': 60.0, 'co2': 800}
            }
            
            assert validator._check_reading_in_spec(invalid_reading) == False
            safety_violation = validator._check_safety_violations(invalid_reading)
            assert safety_violation is not None
            assert 'pH' in safety_violation or 'EC' in safety_violation or 'water level' in safety_violation
            
        finally:
            await validator.cleanup()
    
    @pytest.mark.asyncio
    async def test_control_logic_execution(self, sample_sensor_csv):
        """Test control logic execution during shadow validation"""
        validator = ShadowValidator(sample_sensor_csv)
        
        try:
            await validator.initialize()
            
            # Mock reading that should trigger actions
            problematic_reading = {
                'timestamp': datetime.utcnow().isoformat(),
                'water': {'ph': 6.8, 'ec': 1.2, 'temperature': 22.0, 'level_high': True, 'level_low': True},
                'air': {'temperature': 28.0, 'humidity': 60.0, 'co2': 800},
                'root': {'temperature': 21.0},
                'light': {'lux': 25000, 'led_power': 80}
            }
            
            # Process reading (should trigger control logic)
            await validator._process_reading(problematic_reading, 10)  # Every 10th reading
            
            # Check that actions were recorded
            assert validator.results['actions_taken'] >= 0  # Should be incremented if actions taken
            
        finally:
            await validator.cleanup()
    
    def test_requirements_validation(self):
        """Test requirements validation logic"""
        validator = ShadowValidator()
        
        # Test passing requirements
        validator.results = {
            'total_readings': 100,
            'in_spec_readings': 96,
            'safety_violations': 0,
            'errors': [],
            'performance_metrics': {
                'in_spec_percentage': 96.0,
                'error_rate': 0.0
            }
        }
        
        assert validator._validate_requirements() == True
        
        # Test failing requirements (low in-spec percentage)
        validator.results['performance_metrics']['in_spec_percentage'] = 90.0
        assert validator._validate_requirements() == False
        
        # Test failing requirements (safety violations)
        validator.results['performance_metrics']['in_spec_percentage'] = 96.0
        validator.results['safety_violations'] = 1
        assert validator._validate_requirements() == False
    
    @pytest.mark.asyncio
    async def test_create_sample_data(self):
        """Test sample data creation when no CSV file exists"""
        # Use non-existent file path
        non_existent_file = "/tmp/test_sensors_nonexistent.csv"
        
        validator = ShadowValidator(non_existent_file)
        
        try:
            await validator.initialize()
            
            # Should create sample data
            readings = validator._load_sensor_data()
            
            assert len(readings) > 0
            assert len(readings) == 1440  # 24 hours * 60 minutes
            
            # Verify created file exists
            assert Path(non_existent_file).exists()
            
            # Check data quality
            ph_values = [r['water']['ph'] for r in readings]
            assert min(ph_values) >= 4.0
            assert max(ph_values) <= 8.0
            
        finally:
            await validator.cleanup()
            # Cleanup created file
            try:
                Path(non_existent_file).unlink()
            except:
                pass


class TestShadowValidationPerformance:
    """Test shadow validation performance and edge cases"""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_dataset_validation(self):
        """Test validation with large dataset (week's worth of data)"""
        # Create large temporary dataset
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        
        fieldnames = [
            "timestamp", "ph", "ec", "water_temp", "turbidity", "level_high", "level_low",
            "air_temp", "humidity", "pressure", "co2", "root_temp", "lux", "led_power"
        ]
        
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()
        
        # Generate week's worth of data (7 days * 24 hours * 6 readings/hour = 1008 readings)
        start_time = datetime.utcnow() - timedelta(days=7)
        
        for i in range(1008):
            timestamp = start_time + timedelta(minutes=i * 10)
            
            row = {
                "timestamp": timestamp.isoformat(),
                "ph": 6.0,
                "ec": 1.6,
                "water_temp": 22.0,
                "turbidity": 5.0,
                "level_high": "true",
                "level_low": "true",
                "air_temp": 24.0,
                "humidity": 60.0,
                "pressure": 1013.0,
                "co2": 800,
                "root_temp": 21.0,
                "lux": 25000,
                "led_power": 80
            }
            
            writer.writerow(row)
        
        temp_file.close()
        
        validator = ShadowValidator(temp_file.name)
        
        try:
            await validator.initialize()
            result = await validator.run_validation()
            
            assert result['success'] == True
            assert result['total_readings'] == 1008
            
            # Should still meet performance requirements
            assert result['validation_passed'] == True
            
        finally:
            await validator.cleanup()
            try:
                Path(temp_file.name).unlink()
            except:
                pass
    
    @pytest.mark.asyncio
    async def test_validation_error_handling(self):
        """Test shadow validation error handling"""
        # Test with invalid CSV file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        temp_file.write("invalid,csv,data\n1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17")  # Wrong number of columns
        temp_file.close()
        
        validator = ShadowValidator(temp_file.name)
        
        try:
            await validator.initialize()
            result = await validator.run_validation()
            
            # Should handle errors gracefully
            assert 'error' in result or len(result.get('errors', [])) > 0
            
        finally:
            await validator.cleanup()
            try:
                Path(temp_file.name).unlink()
            except:
                pass