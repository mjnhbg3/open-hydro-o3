# Open Hydro O3

An LLM-driven hydroponic controller powered by OpenAI's o3 model, designed to run on Raspberry Pi Zero 2 W.

## Overview

This system provides intelligent hydroponic grow management using:
- Real-time sensor monitoring (pH, EC, temperature, humidity, CO2)
- LLM-powered decision making with OpenAI o3
- Automated nutrient dosing and environmental control
- Memory system for learning and optimization
- Safety-first operation with configurable limits

## Hardware Requirements

- Raspberry Pi Zero 2 W
- ADS1115 ADC (I2C 0x48)
- BME280 environmental sensor (I2C 0x76)
- DS18B20 temperature probe (1-Wire on GPIO4)
- MH-Z19B CO2 sensor (UART)
- Various pumps and sensors (see docs/ARCH.md)

## Quick Start

```bash
# Setup environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your OpenAI API key

# Run tests
make test

# Start services (on Pi)
sudo make install-services
```

## Architecture

See `docs/ARCH.md` for detailed system architecture and `docs/MERMAID.md` for visual diagrams.

## Configuration

All configuration is JSON-based in `app/config/`:
- `default.json` - Base configuration
- `safety_limits.json` - Hard safety limits
- `current.json` - Symlink to active config

## Services

- `sensor_poll.service` - Collects sensor data every minute
- `control_loop.service` - Runs control decisions every 10 minutes
- `kpi_rollup.service` - Hourly KPI calculations
- `brain_sync.service` - Daily LLM synchronization
- `watchdog.service` - System health monitoring

## Development

```bash
make lint        # Run ruff and black
make test        # Run pytest with coverage
make shadow-run  # Simulate full day operation
```

## License

MIT License - see LICENSE file