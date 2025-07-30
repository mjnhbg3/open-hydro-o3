"""
Utility functions for the hydroponic controller
"""

import json
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, Optional

import jsonschema


def setup_logging(log_level: str = None, log_path: str = None):
    """Setup application logging with rotation"""
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    if log_path is None:
        log_path = os.getenv('LOG_PATH', '~/hydro/logs/')
    
    log_dir = Path(log_path).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Rotating file handler (10MB, keep 5 files)
    log_file = log_dir / 'hydro.log'
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Error log (separate file for errors only)
    error_file = log_dir / 'hydro_errors.log'
    error_handler = RotatingFileHandler(
        error_file, maxBytes=5*1024*1024, backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    logger.addHandler(error_handler)
    
    logging.info(f"Logging initialized - Level: {log_level}, Path: {log_dir}")


def load_json_file(file_path: str) -> Dict[str, Any]:
    """Load JSON file with error handling"""
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {file_path}")
        
        with open(path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to load {file_path}: {e}")


def save_json_file(data: Dict[str, Any], file_path: str, backup: bool = True):
    """Save JSON file with optional backup"""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create backup if file exists and backup requested
        if backup and path.exists():
            backup_path = path.with_suffix(f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            path.rename(backup_path)
        
        # Write new file
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
            
    except Exception as e:
        raise RuntimeError(f"Failed to save {file_path}: {e}")


def load_json_schema(schema_path: str) -> Dict[str, Any]:
    """Load JSON schema for validation"""
    try:
        return load_json_file(schema_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load schema {schema_path}: {e}")


def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """Validate data against JSON schema"""
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        raise ValueError(f"Schema validation failed: {e.message}")
    except Exception as e:
        raise RuntimeError(f"Schema validation error: {e}")


def create_timestamp() -> str:
    """Create ISO timestamp string"""
    return datetime.utcnow().isoformat() + 'Z'


def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO timestamp string to datetime"""
    try:
        # Handle both with and without 'Z' suffix
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        
        return datetime.fromisoformat(timestamp_str)
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: {timestamp_str}")


def calculate_vpd(temperature: float, humidity: float) -> float:
    """Calculate Vapour Pressure Deficit (kPa)"""
    try:
        # Saturated vapor pressure (kPa) using Tetens formula
        es = 0.6108 * (10 ** ((7.5 * temperature) / (237.3 + temperature)))
        
        # Actual vapor pressure (kPa)
        ea = es * (humidity / 100)
        
        # VPD = saturated - actual
        vpd = es - ea
        
        return round(vpd, 2)
    except Exception:
        return 0.0


def calculate_dli(ppfd: float, hours: float) -> float:
    """Calculate Daily Light Integral (mol/m²/day)"""
    try:
        # Convert PPFD (μmol/m²/s) to DLI (mol/m²/day)
        # DLI = PPFD × hours × 3600 / 1,000,000
        dli = (ppfd * hours * 3600) / 1_000_000
        return round(dli, 1)
    except Exception:
        return 0.0


def ppfd_to_lux(ppfd: float) -> float:
    """Convert PPFD to approximate lux (for common LED spectra)"""
    try:
        # Rough conversion factor for typical LED grow lights
        # This varies significantly by spectrum
        return ppfd * 75  # Approximate conversion factor
    except Exception:
        return 0.0


def lux_to_ppfd(lux: float) -> float:
    """Convert lux to approximate PPFD"""
    try:
        return lux / 75  # Inverse of above conversion
    except Exception:
        return 0.0


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max"""
    return max(min_val, min(max_val, value))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division with default return"""
    try:
        if denominator == 0:
            return default
        return numerator / denominator
    except (TypeError, ZeroDivisionError):
        return default


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable string"""
    try:
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}m {secs}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    except Exception:
        return "0s"


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe filesystem usage"""
    import re
    # Remove/replace unsafe characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove control characters
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
    # Limit length
    return filename[:255]


def get_git_revision() -> Optional[str]:
    """Get current git revision if available"""
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_system_info() -> Dict[str, Any]:
    """Get basic system information"""
    import platform
    import psutil
    
    try:
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "disk_free_gb": round(psutil.disk_usage('/').free / (1024**3), 1),
            "git_revision": get_git_revision()
        }
    except Exception as e:
        return {"error": str(e)}


def create_alert(severity: str, category: str, message: str, 
                details: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create standardized alert dictionary"""
    return {
        "timestamp": create_timestamp(),
        "severity": severity,
        "category": category,
        "message": message,
        "details": details or {},
        "acknowledged": False,
        "resolved": False
    }


def exponential_backoff(attempt: int, base_delay: float = 1.0, 
                       max_delay: float = 60.0) -> float:
    """Calculate exponential backoff delay"""
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)


class SingletonMeta(type):
    """Metaclass for singleton pattern"""
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def retry_on_exception(max_retries: int = 3, delay: float = 1.0):
    """Decorator for retrying function calls on exception"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    
                    wait_time = exponential_backoff(attempt, delay)
                    logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                    
                    import time
                    time.sleep(wait_time)
            
        return wrapper
    return decorator


def merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any], 
                deep: bool = True) -> Dict[str, Any]:
    """Merge two dictionaries with optional deep merging"""
    if not deep:
        return {**dict1, **dict2}
    
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value, deep=True)
        else:
            result[key] = value
    
    return result


def get_config_hash(config: Dict[str, Any]) -> str:
    """Generate hash of configuration for change detection"""
    import hashlib
    
    # Convert to sorted JSON string for consistent hashing
    config_str = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


# Configuration loading ----------------------------------------------------
CONFIG_DIR = Path(__file__).resolve().parent / "config"


def _set_nested_config(config: Dict[str, Any], path: str, value: Any):
    """Set a value in a nested dictionary using dot notation."""
    keys = path.split(".")
    current = config
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _get_env_overrides() -> Dict[str, Any]:
    """Collect configuration overrides from environment variables."""
    overrides: Dict[str, Any] = {}
    env_mappings = {
        "GROW_PHASE": ("grow_phase", str),
        "PH_TARGET": ("targets.ph_target", float),
        "EC_TARGET": ("targets.ec_target", float),
        "TEMP_TARGET": ("targets.temp_target", float),
        "LIGHT_HOURS": ("schedules.light_hours", int),
        "LIGHT_START_TIME": ("schedules.light_start_time", str),
        "SENSOR_POLL_INTERVAL": ("schedules.sensor_poll_interval_s", int),
        "CONTROL_LOOP_INTERVAL": ("schedules.control_loop_interval_s", int),
        "RESERVOIR_VOLUME": ("reservoir_volume_l", float),
        "BASELINE_DOSING": ("baseline_dosing_ml_per_week", float),
    }

    for env_var, (config_path, type_func) in env_mappings.items():
        env_value = os.getenv(env_var)
        if env_value is not None:
            try:
                typed_value = type_func(env_value)
                _set_nested_config(overrides, config_path, typed_value)
            except (ValueError, TypeError):
                print(f"Warning: Invalid environment variable {env_var}={env_value}")

    return overrides


def load_config() -> Dict[str, Any]:
    """Load configuration from JSON files with environment overrides."""
    try:
        base_config = load_json_file(CONFIG_DIR / "default.json")

        current_file = CONFIG_DIR / "current.json"
        if current_file.exists():
            current_config = load_json_file(current_file)
            base_config = merge_dicts(base_config, current_config)

        env_overrides = _get_env_overrides()
        if env_overrides:
            base_config = merge_dicts(base_config, env_overrides)

        return base_config
    except Exception as exc:
        print(f"Warning: Error loading configuration: {exc}")
        return {}