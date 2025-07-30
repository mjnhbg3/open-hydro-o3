"""
Default configuration loader with validation
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

from ..utils import load_json_file, merge_dicts


def load_config() -> Dict[str, Any]:
    """Load configuration from files with environment overrides"""
    
    # Base configuration
    base_config = {
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
            "co2_max": 1200
        },
        
        "schedules": {
            "light_hours": 16,
            "light_start_time": "06:00",
            "light_power_day": 80,
            "light_power_night": 0,
            "fan_base_speed": 20,
            "sensor_poll_interval_s": 60,
            "control_loop_interval_s": 600
        },
        
        "hardware": {
            "i2c_bus": 1,
            "uart_device": "/dev/ttyAMA0",
            "gpio_pins": {
                "pump_a": 17,
                "pump_b": 27,
                "ph_pump": 22,
                "refill_pump": 25,
                "fan_pwm": 18,
                "led_pwm": 13,
                "float_hi": 23,
                "float_lo": 24
            },
            "ads1115_address": "0x48",
            "bme280_address": "0x76",
            "flow_rates_ml_per_s": {
                "pump_a": 2.5,
                "pump_b": 2.5,
                "ph_pump": 1.0,
                "refill_pump": 50.0
            }
        },
        
        "calibration": {
            "ph_probe": {
                "slope": -59.16,
                "offset": 7.0,
                "temp_compensation": True
            },
            "ec_probe": {
                "k_factor": 1.0,
                "temp_compensation": True,
                "reference_temp": 25.0
            },
            "turbidity": {
                "clear_voltage": 4.2,
                "scale_factor": 1000
            }
        },
        
        "alerts": {
            "enabled": True,
            "email_notifications": False,
            "mqtt_notifications": True,
            "thresholds": {
                "ph_deviation": 0.5,
                "ec_deviation": 0.3,
                "temp_deviation": 5.0,
                "low_water_alert": True,
                "pump_failure_timeout_s": 300
            }
        },
        
        "data_retention": {
            "sensor_data_days": 30,
            "action_history_days": 90,
            "kpi_history_days": 365,
            "log_retention_days": 30
        }
    }
    
    try:
        # Load from default.json if it exists
        config_dir = Path(__file__).parent
        default_file = config_dir / "default.json"
        
        if default_file.exists():
            file_config = load_json_file(str(default_file))
            base_config = merge_dicts(base_config, file_config)
        
        # Load current config (symlink to active config)
        current_file = config_dir / "current.json"
        if current_file.exists():
            current_config = load_json_file(str(current_file))
            base_config = merge_dicts(base_config, current_config)
        
        # Apply environment variable overrides
        env_overrides = _get_env_overrides()
        if env_overrides:
            base_config = merge_dicts(base_config, env_overrides)
        
        return base_config
        
    except Exception as e:
        print(f"Warning: Error loading configuration: {e}")
        print("Using default configuration")
        return base_config


def _get_env_overrides() -> Dict[str, Any]:
    """Get configuration overrides from environment variables"""
    overrides = {}
    
    # Simple environment variable mappings
    env_mappings = {
        'GROW_PHASE': ('grow_phase', str),
        'PH_TARGET': ('targets.ph_target', float),
        'EC_TARGET': ('targets.ec_target', float),
        'TEMP_TARGET': ('targets.temp_target', float),
        'LIGHT_HOURS': ('schedules.light_hours', int),
        'LIGHT_START_TIME': ('schedules.light_start_time', str),
        'SENSOR_POLL_INTERVAL': ('schedules.sensor_poll_interval_s', int),
        'CONTROL_LOOP_INTERVAL': ('schedules.control_loop_interval_s', int),
        'RESERVOIR_VOLUME': ('reservoir_volume_l', float),
        'BASELINE_DOSING': ('baseline_dosing_ml_per_week', float)
    }
    
    for env_var, (config_path, type_func) in env_mappings.items():
        env_value = os.getenv(env_var)
        if env_value is not None:
            try:
                # Convert value to correct type
                typed_value = type_func(env_value)
                
                # Set nested config value
                _set_nested_config(overrides, config_path, typed_value)
                
            except (ValueError, TypeError) as e:
                print(f"Warning: Invalid environment variable {env_var}={env_value}: {e}")
    
    return overrides


def _set_nested_config(config: Dict[str, Any], path: str, value: Any):
    """Set nested configuration value using dot notation"""
    keys = path.split('.')
    current = config
    
    # Navigate to parent of target key
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    # Set the final value
    current[keys[-1]] = value


def save_config(config: Dict[str, Any], version_name: str = None) -> str:
    """Save configuration with versioning"""
    from datetime import datetime
    from ..utils import save_json_file, get_config_hash
    
    config_dir = Path(__file__).parent
    
    # Generate version name if not provided
    if version_name is None:
        timestamp = datetime.now().strftime("%Y-%m-%d-v1")
        config_hash = get_config_hash(config)
        version_name = f"{timestamp}-{config_hash}"
    
    # Save versioned config
    versioned_file = config_dir / f"{version_name}.json"
    save_json_file(config, str(versioned_file))
    
    # Update current.json symlink
    current_file = config_dir / "current.json"
    if current_file.exists() or current_file.is_symlink():
        current_file.unlink()
    
    current_file.symlink_to(versioned_file.name)
    
    return version_name


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate configuration and return any errors"""
    errors = []
    warnings = []
    
    try:
        # Check required fields
        required_fields = ['targets', 'schedules', 'hardware']
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        # Validate target ranges
        targets = config.get('targets', {})
        if 'ph_min' in targets and 'ph_max' in targets:
            if targets['ph_min'] >= targets['ph_max']:
                errors.append("pH min must be less than pH max")
            if targets['ph_min'] < 4.0 or targets['ph_max'] > 8.0:
                warnings.append("pH targets outside typical hydroponic range (4.0-8.0)")
        
        if 'ec_min' in targets and 'ec_max' in targets:
            if targets['ec_min'] >= targets['ec_max']:
                errors.append("EC min must be less than EC max")
            if targets['ec_min'] < 0.5 or targets['ec_max'] > 3.0:
                warnings.append("EC targets outside typical range (0.5-3.0)")
        
        # Validate schedules
        schedules = config.get('schedules', {})
        if 'light_hours' in schedules:
            if not 8 <= schedules['light_hours'] <= 20:
                warnings.append("Light hours outside typical range (8-20)")
        
        # Validate hardware configuration
        hardware = config.get('hardware', {})
        if 'gpio_pins' in hardware:
            pins = hardware['gpio_pins']
            pin_values = [v for v in pins.values() if isinstance(v, int)]
            if len(pin_values) != len(set(pin_values)):
                errors.append("Duplicate GPIO pin assignments detected")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
        
    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Configuration validation failed: {e}"],
            'warnings': []
        }