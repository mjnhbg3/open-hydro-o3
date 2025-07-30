# Open Hydro O3 Architecture

## System Overview

Open Hydro O3 is an intelligent hydroponic controller that combines traditional rule-based control with LLM-powered decision making using OpenAI's o3 model. The system follows a "stable-unless-better" philosophy, making minimal interventions unless clear improvements are needed.

## Core Components

### 1. Sensor Interface (`app/sensor_io.py`)

**Purpose**: Hardware abstraction layer for all sensor inputs

**Key Features**:
- Mock mode for development/testing
- Real-time sensor data collection
- Hardware calibration support
- Error handling and fallback values

**Sensors Supported**:
- pH probe (ADS1115 ADC)
- EC probe (ADS1115 ADC) 
- Water temperature (DS18B20 1-Wire)
- Air environment (BME280 I2C)
- CO2 sensor (MH-Z19B UART)
- Water level (GPIO float switches)
- Light sensor (ADS1115 ADC)

### 2. Actuator Controller (`app/actuators.py`)

**Purpose**: Safe control of all system actuators

**Key Features**:
- Safety limit enforcement
- Daily dosing tracking
- Emergency stop capability
- Mock mode for testing

**Actuators Controlled**:
- Nutrient pumps (A, B, pH) - GPIO relay control
- Water refill pump - GPIO relay control
- Ventilation fan - PWM control
- LED grow lights - PWM control

### 3. LLM Agent (`app/llm_agent.py`)

**Purpose**: Intelligent decision making using OpenAI o3 model

**Key Features**:
- JSON schema validation
- Context-aware decision making
- Vector memory integration
- Temperature 0.0 for consistency
- Safety validation of all decisions

**Decision Types**:
- Nutrient dosing adjustments
- Environmental control (fan, LED)
- System optimization recommendations

### 4. Rules Engine (`app/rules.py`)

**Purpose**: Traditional rule-based control with stable-unless-better logic

**Key Features**:
- 7-day moving average analysis
- Performance-based intervention scaling
- Configuration rollback capability
- System freeze for excellent performance

**Rule Categories**:
- pH stability rules
- EC optimization rules
- Environmental control rules
- Reservoir change scheduling
- Safety violation handling

### 5. Memory System

#### Database (`app/memory/db.py`)
- SQLite3 storage for all operational data
- Automated data retention management
- Performance metrics tracking
- Event logging and alerting

#### Vector Memory (`app/memory/vector.py`)
- ChromaDB for contextual memory
- Decision similarity matching
- Historical pattern recognition
- Automatic memory cleanup

#### KPI Calculator (`app/memory/kpis.py`)
- Real-time performance metrics
- Trend analysis and forecasting
- Health score calculation
- Compliance reporting

## Data Flow Architecture

```
Sensors → Sensor Interface → Database
                ↓
        KPI Calculator → Rules Engine → LLM Agent
                ↓                          ↓
        Decision Logic ← Vector Memory ←────┘
                ↓
        Actuator Controller → Hardware
                ↓
        Database ← Feedback Loop
```

## Service Architecture

### Core Services (systemd)

1. **sensor_poll.service** (1-minute interval)
   - Collects all sensor data
   - Validates readings
   - Stores in database
   - Triggers alerts for anomalies

2. **control_loop.service** (10-minute interval)
   - Calculates current KPIs
   - Runs rules engine evaluation
   - Queries LLM for decisions
   - Executes approved actions
   - Applies stable-unless-better filtering

3. **kpi_rollup.service** (hourly)
   - Calculates period KPIs
   - Updates trend analysis
   - Generates performance alerts
   - Manages data retention

4. **brain_sync.service** (daily)
   - Synchronizes vector memory
   - Generates system analysis
   - Creates optimization recommendations
   - Manages memory cleanup

5. **watchdog.service** (continuous)
   - Monitors service health
   - Automatic service restart
   - System health reporting

## Configuration Management

### Configuration Files
- `app/config/default.json` - Base configuration
- `app/config/current.json` - Active configuration (symlink)
- `app/config/safety_limits.json` - Hard safety limits
- `app/config/*.json` - Versioned configurations

### Environment Variables
- Hardware mock mode control
- Database and storage paths
- LLM API configuration
- Logging levels and retention

## Safety Architecture

### Multi-Layer Safety System

1. **Hardware Safety**
   - Pump flow rate limits
   - Maximum single dose limits
   - Daily dosing limits
   - Emergency stop capability

2. **Software Safety**
   - JSON schema validation
   - Safety limit checking before execution
   - Rollback capability for failed changes
   - Automatic system freeze for excellent performance

3. **Monitoring Safety**
   - Real-time anomaly detection
   - Automatic alert generation
   - Service health monitoring
   - Data backup and recovery

## Scalability Considerations

### Horizontal Scaling
- Multiple grow zones support via configuration
- Distributed sensor networks
- Load balancing for high-frequency operations

### Vertical Scaling
- Database optimization for large datasets
- Vector memory compression
- Efficient KPI calculation algorithms

### Integration Points
- REST API for external systems
- Node-RED dashboard integration
- MQTT support for IoT ecosystems
- Webhook support for notifications

## Development Architecture

### Testing Strategy
- Unit tests with comprehensive mocks
- Integration tests with shadow validation
- Performance tests with realistic datasets
- Security testing with automated scans

### Deployment Options
- Direct installation on Raspberry Pi
- Docker containerization
- Kubernetes orchestration
- CI/CD pipeline automation

### Monitoring and Observability
- Structured logging with rotation
- Performance metrics collection
- Health check endpoints
- Error tracking and alerting

## Security Architecture

### Data Protection
- Local data storage (no cloud dependencies)
- Encrypted API communications
- Secure configuration management
- Access control and authentication

### Network Security
- Minimal network exposure
- VPN support for remote access
- Firewall configuration guidance
- Certificate management

### Operational Security
- Regular security updates
- Automated vulnerability scanning
- Backup and recovery procedures
- Incident response planning