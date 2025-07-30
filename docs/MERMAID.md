# System Architecture Diagrams

## Overall System Architecture

```mermaid
graph TB
    subgraph "Hardware Layer"
        S1[pH Sensor]
        S2[EC Sensor]
        S3[Temperature Sensors]
        S4[Humidity/CO2]
        S5[Water Level]
        S6[Light Sensor]
        
        A1[Pump A]
        A2[Pump B]
        A3[pH Pump]
        A4[Refill Pump]
        A5[Fan PWM]
        A6[LED PWM]
    end
    
    subgraph "Application Layer"
        SI[Sensor Interface]
        AC[Actuator Controller]
        
        subgraph "Intelligence Layer"
            RE[Rules Engine]
            LLM[LLM Agent]
        end
        
        subgraph "Memory Layer"
            DB[(Database)]
            VM[(Vector Memory)]
            KC[KPI Calculator]
        end
    end
    
    subgraph "Service Layer"
        SP[Sensor Poll]
        CL[Control Loop]
        KR[KPI Rollup]
        BS[Brain Sync]
        WD[Watchdog]
    end
    
    subgraph "Interface Layer"
        API[REST API]
        NR[Node-RED Dashboard]
    end
    
    S1 --> SI
    S2 --> SI
    S3 --> SI
    S4 --> SI
    S5 --> SI
    S6 --> SI
    
    SI --> DB
    SI --> SP
    
    SP --> CL
    CL --> KC
    KC --> RE
    RE --> LLM
    LLM --> VM
    
    RE --> AC
    LLM --> AC
    
    AC --> A1
    AC --> A2
    AC --> A3
    AC --> A4
    AC --> A5
    AC --> A6
    
    DB --> KR
    KR --> BS
    
    WD --> SP
    WD --> CL
    
    API --> SI
    API --> AC
    API --> DB
    
    NR --> API
```

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant HW as Hardware
    participant SI as Sensor Interface
    participant DB as Database
    participant KC as KPI Calculator
    participant RE as Rules Engine
    participant LLM as LLM Agent
    participant AC as Actuator Controller
    
    loop Every Minute
        HW->>SI: Read sensor data
        SI->>DB: Store readings
        SI->>SI: Validate data
        Note over SI: Check safety limits
    end
    
    loop Every 10 Minutes
        DB->>KC: Get recent data
        KC->>KC: Calculate KPIs
        KC->>RE: Current performance
        RE->>RE: Evaluate rules
        
        alt Rules suggest action
            RE->>LLM: Get LLM decision
            LLM->>LLM: Analyze context
            LLM->>RE: Recommended actions
        end
        
        RE->>RE: Apply stable-unless-better
        RE->>AC: Execute actions
        AC->>HW: Control actuators
        AC->>DB: Log actions
    end
    
    loop Hourly
        DB->>KC: Calculate period KPIs
        KC->>DB: Store KPI rollups
    end
    
    loop Daily
        DB->>LLM: Sync decisions to vector memory
        LLM->>LLM: Generate daily analysis
    end
```

## Control Logic Flow

```mermaid
flowchart TD
    Start([Sensor Reading]) --> Validate{Valid Data?}
    
    Validate -->|No| Alert[Generate Alert]
    Validate -->|Yes| Store[Store in Database]
    
    Store --> Control{Control Cycle?}
    Control -->|No| End([End])
    Control -->|Yes| KPI[Calculate KPIs]
    
    KPI --> Rules[Evaluate Rules]
    
    Rules --> Freeze{System Frozen?}
    Freeze -->|Yes| NoAction[No Action Needed]
    Freeze -->|No| CheckRules{Rules Triggered?}
    
    CheckRules -->|No| NoAction
    CheckRules -->|Yes| LLMCheck{Use LLM?}
    
    LLMCheck -->|No| RulesOnly[Rules Decision Only]
    LLMCheck -->|Yes| LLMQuery[Query LLM Agent]
    
    LLMQuery --> Combine[Combine Decisions]
    RulesOnly --> Safety{Safety Check?}
    Combine --> Safety
    
    Safety -->|Fail| SafetyAlert[Safety Alert]
    Safety -->|Pass| Stable[Apply Stable-Unless-Better]
    
    Stable --> Execute[Execute Actions]
    Execute --> Log[Log Results]
    
    NoAction --> End
    SafetyAlert --> End
    Log --> End
```

## Service Interaction Diagram

```mermaid
graph TB
    subgraph "Systemd Services"
        SP[sensor_poll.service<br/>Every 1 min]
        CL[control_loop.service<br/>Every 10 min]
        KR[kpi_rollup.service<br/>Every hour]
        BS[brain_sync.service<br/>Daily]
        WD[watchdog.service<br/>Continuous]
    end
    
    subgraph "Shared Resources"
        DB[(SQLite Database)]
        VM[(ChromaDB)]
        FS[File System]
    end
    
    subgraph "External Interfaces"
        API[REST API :8000]
        NR[Node-RED :1880]
        LOG[Log Files]
    end
    
    SP -->|Write| DB
    SP -->|Write| LOG
    
    CL -->|Read/Write| DB
    CL -->|Read/Write| VM
    CL -->|Write| LOG
    
    KR -->|Read/Write| DB
    KR -->|Write| LOG
    
    BS -->|Read/Write| DB
    BS -->|Read/Write| VM
    BS -->|Write| LOG
    
    WD -->|Monitor| SP
    WD -->|Monitor| CL
    WD -->|Restart| SP
    WD -->|Restart| CL
    
    API -->|Read| DB
    NR -->|HTTP| API
    
    SP -.->|Triggers every 10th run| CL
```

## Database Schema Diagram

```mermaid
erDiagram
    sensor_readings {
        int id PK
        datetime timestamp
        real ph
        real ec
        real water_temp
        real air_temp
        real humidity
        int co2
        real root_temp
        real lux
        real turbidity
        boolean level_high
        boolean level_low
        real pressure
        int led_power
        text raw_data
    }
    
    actuator_actions {
        int id PK
        datetime timestamp
        text action_type
        real pump_a_ml
        real pump_b_ml
        real ph_pump_ml
        real refill_ml
        int fan_speed
        int led_power
        int duration_minutes
        text reason
        boolean success
        text raw_data
    }
    
    system_events {
        int id PK
        datetime timestamp
        text event_type
        text severity
        text category
        text message
        text details
        boolean acknowledged
        boolean resolved
    }
    
    kpi_rollups {
        int id PK
        datetime timestamp
        text period
        real ph_avg
        real ph_in_spec_pct
        real ec_avg
        real ec_in_spec_pct
        real temp_avg
        real temp_in_spec_pct
        real humidity_avg
        real co2_avg
        real health_score
        real ml_total
        real pump_a_ml
        real pump_b_ml
        real ph_pump_ml
        int days_since_change
        text raw_data
    }
    
    llm_decisions {
        int id PK
        datetime timestamp
        text sensor_context
        text decision_data
        text reasoning
        real confidence
        boolean executed
        text outcome
    }
    
    config_changes {
        int id PK
        datetime timestamp
        text config_version
        text changes
        text reason
        boolean user_initiated
    }
    
    sensor_readings ||--o{ kpi_rollups : "aggregates"
    actuator_actions ||--o{ system_events : "triggers"
    llm_decisions ||--o{ actuator_actions : "causes"
```

## Hardware Connection Diagram

```mermaid
graph LR
    subgraph "Raspberry Pi Zero 2 W"
        subgraph "GPIO Pins"
            GPIO17[GPIO 17 - Pump A]
            GPIO27[GPIO 27 - Pump B]
            GPIO22[GPIO 22 - pH Pump]
            GPIO25[GPIO 25 - Refill]
            GPIO18[GPIO 18 - Fan PWM]
            GPIO13[GPIO 13 - LED PWM]
            GPIO23[GPIO 23 - Float Hi]
            GPIO24[GPIO 24 - Float Lo]
            GPIO4[GPIO 4 - 1-Wire]
        end
        
        subgraph "I2C Bus"
            I2C[SDA/SCL]
        end
        
        subgraph "UART"
            UART[RX/TX]
        end
    end
    
    subgraph "Sensors"
        ADS[ADS1115 ADC<br/>0x48]
        BME[BME280<br/>0x76]
        DS18[DS18B20<br/>1-Wire]
        CO2[MH-Z19B<br/>UART]
        FH[Float High]
        FL[Float Low]
    end
    
    subgraph "Sensor Probes"
        PH[pH Probe]
        EC[EC Probe]
        TURB[Turbidity Sensor]
        LUX[Light Sensor]
    end
    
    subgraph "Actuators"
        PA[Pump A Relay]
        PB[Pump B Relay]
        PPH[pH Pump Relay]
        PR[Refill Pump Relay]
        FAN[Fan Controller]
        LED[LED Driver]
    end
    
    I2C --- ADS
    I2C --- BME
    GPIO4 --- DS18
    UART --- CO2
    GPIO23 --- FH
    GPIO24 --- FL
    
    ADS --- PH
    ADS --- EC
    ADS --- TURB
    ADS --- LUX
    
    GPIO17 --- PA
    GPIO27 --- PB
    GPIO22 --- PPH
    GPIO25 --- PR
    GPIO18 --- FAN
    GPIO13 --- LED
```

## Deployment Architecture

```mermaid
graph TB
    subgraph "Development"
        DEV[Development Environment]
        TEST[Test Suite]
        MOCK[Mock Hardware]
    end
    
    subgraph "CI/CD Pipeline"
        GH[GitHub Actions]
        LINT[Linting & Formatting]
        UNIT[Unit Tests]
        INT[Integration Tests]
        SEC[Security Scan]
        BUILD[Docker Build]
    end
    
    subgraph "Deployment Targets"
        subgraph "Local Development"
            LOCAL[Local Python]
            DOCKER_DEV[Docker Compose]
        end
        
        subgraph "Production"
            PI[Raspberry Pi]
            DOCKER_PROD[Docker Production]
            SYS[Systemd Services]
        end
    end
    
    subgraph "Monitoring"
        LOGS[Log Files]
        HEALTH[Health Checks]
        ALERTS[Alert System]
        BACKUP[Automated Backup]
    end
    
    DEV --> GH
    TEST --> GH
    MOCK --> GH
    
    GH --> LINT
    GH --> UNIT
    GH --> INT
    GH --> SEC
    GH --> BUILD
    
    BUILD --> LOCAL
    BUILD --> DOCKER_DEV
    BUILD --> PI
    BUILD --> DOCKER_PROD
    
    PI --> SYS
    DOCKER_PROD --> SYS
    
    SYS --> LOGS
    SYS --> HEALTH
    SYS --> ALERTS
    SYS --> BACKUP
```