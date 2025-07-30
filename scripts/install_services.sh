#!/bin/bash
#
# Install systemd services for hydroponic controller
# 

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SYSTEMD_DIR="$PROJECT_DIR/systemd"
SERVICE_DIR="/etc/systemd/system"
USER="${SUDO_USER:-$USER}"
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"

echo "Installing hydroponic controller systemd services..."
echo "Project directory: $PROJECT_DIR"
echo "User: $USER"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)" 
   exit 1
fi

# Check if Python virtual environment exists
if [[ ! -f "$PYTHON_PATH" ]]; then
    echo "Error: Python virtual environment not found at $PYTHON_PATH"
    echo "Please run 'make venv' first to create the virtual environment"
    exit 1
fi

# Function to install a service file
install_service() {
    local service_name="$1"
    local service_file="$SYSTEMD_DIR/$service_name"
    local target_file="$SERVICE_DIR/$service_name"
    
    if [[ ! -f "$service_file" ]]; then
        echo "Error: Service file not found: $service_file"
        exit 1
    fi
    
    echo "Installing $service_name..."
    
    # Create service file with substituted paths
    sed -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
        -e "s|{{USER}}|$USER|g" \
        -e "s|{{PYTHON_PATH}}|$PYTHON_PATH|g" \
        "$service_file" > "$target_file"
    
    # Set correct permissions
    chmod 644 "$target_file"
    
    echo "  -> Installed $target_file"
}

# Function to install a timer file
install_timer() {
    local timer_name="$1"
    local timer_file="$SYSTEMD_DIR/$timer_name"
    local target_file="$SERVICE_DIR/$timer_name"
    
    if [[ ! -f "$timer_file" ]]; then
        echo "Error: Timer file not found: $timer_file"
        exit 1
    fi
    
    echo "Installing $timer_name..."
    cp "$timer_file" "$target_file"
    chmod 644 "$target_file"
    
    echo "  -> Installed $target_file"
}

# Install service files
install_service "sensor_poll.service"
install_service "control_loop.service"
install_service "kpi_rollup.service"
install_service "brain_sync.service"
install_service "shadow_validator.service"
install_service "watchdog.service"

# Install timer files
install_timer "kpi_rollup.timer"
install_timer "brain_sync.timer"
install_timer "shadow_validator.timer"

# Create systemd directories for user data
echo "Creating data directories..."
mkdir -p /home/$USER/hydro/{db,logs,chroma,images}
chown -R $USER:$USER /home/$USER/hydro

# Create log directory
mkdir -p /var/log/hydro
chown $USER:$USER /var/log/hydro

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

echo ""
echo "Services installed successfully!"
echo ""
echo "Available services:"
echo "  sensor_poll.service     - Sensor data collection (runs every minute)"
echo "  control_loop.service    - Control decisions (runs every 10 minutes)"
echo "  kpi_rollup.service      - KPI calculations (runs hourly via timer)"
echo "  brain_sync.service      - Daily LLM synchronization (runs daily via timer)"
echo "  shadow_validator.service - System validation (runs weekly via timer)"
echo "  watchdog.service        - System health monitoring"
echo ""
echo "To enable and start services:"
echo "  sudo systemctl enable sensor_poll.service"
echo "  sudo systemctl enable control_loop.service"
echo "  sudo systemctl enable kpi_rollup.timer"
echo "  sudo systemctl enable brain_sync.timer"
echo "  sudo systemctl enable shadow_validator.timer"
echo "  sudo systemctl enable watchdog.service"
echo ""
echo "  sudo systemctl start sensor_poll.service"
echo "  sudo systemctl start control_loop.service"
echo "  sudo systemctl start kpi_rollup.timer"
echo "  sudo systemctl start brain_sync.timer"
echo "  sudo systemctl start shadow_validator.timer"
echo "  sudo systemctl start watchdog.service"
echo ""
echo "To check service status:"
echo "  systemctl status hydro-sensor-poll"
echo "  systemctl status hydro-control-loop"
echo "  journalctl -u hydro-sensor-poll -f"
echo ""
echo "WARNING: Services are installed but not enabled or started."
echo "This is intentional for development/testing environments."
echo "Enable and start them when ready for production use."