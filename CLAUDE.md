# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the Devopin Agent - a comprehensive system monitoring and log parsing agent written in Python. The agent provides real-time system metrics collection, log file parsing for multiple frameworks (Laravel, Django, Flask, Node.js, Python), service monitoring via systemctl, and remote control capabilities through Unix sockets.

## Development Commands

### Running the Agent
```bash
# Run in development mode
python3 main.py

# The agent will create a socket at ./tmp/devopin_agent.sock in development
```

### Testing Socket Communication
```bash
# Test socket connection
echo '{"command":"status"}' | socat - UNIX-CONNECT:./tmp/devopin_agent.sock

# Control services
echo '{"command": "start", "service": "nginx"}' | socat - UNIX-CONNECT:./tmp/devopin_agent.sock
echo '{"command": "stop", "service": "nginx"}' | socat - UNIX-CONNECT:./tmp/devopin_agent.sock
echo '{"command": "restart", "service": "nginx"}' | socat - UNIX-CONNECT:./tmp/devopin_agent.sock
```

### Production Installation
```bash
# Install as systemd service (requires root)
sudo ./install.sh

# Service management
sudo systemctl start devopin-agent
sudo systemctl stop devopin-agent
sudo systemctl restart devopin-agent
sudo systemctl status devopin-agent

# View logs
sudo journalctl -u devopin-agent -f
```

### Binary Creation
```bash
# Create standalone binary using PyInstaller
pyinstaller devopin-agent.spec

# Binary will be created in dist/devopin-agent
```

### Mock SystemCtl for Development
```bash
# Set up mock systemctl for testing (when systemctl is not available)
./setup-systemctl.sh

# Test mock systemctl
./test-systemctl.sh

# Clean up mock services
./cleanup.sh
```

### Dependencies
```bash
# Install Python dependencies
pip3 install -r requirements.txt

# Key dependencies:
# - psutil (7.0.0): System metrics collection
# - PyYAML (6.0.2): Configuration file parsing  
# - requests (2.32.4): HTTP API communication
# - python-dateutil (2.9.0): Date/time parsing for logs
# - pyinstaller (6.14.1): Binary packaging
```

## Architecture

The agent follows a modular architecture with clear separation of concerns:

### Core Components
- **main.py** - Entry point and main DevopinAgent orchestrator class
- **core/monitor_agent.py** - Main monitoring logic that coordinates all monitoring activities
- **core/socket_server.py** - Unix socket server for remote control via web interface
- **core/system.py** - System metrics collection (CPU, memory, disk, network)
- **core/service.py** - Service monitoring via systemctl
- **core/parser.py** - Log parsing for multiple framework formats
- **core/config.py** - Configuration loading and management

### Data Models
- **models/data_classes.py** - Data structures for LogEntry, ServiceStatus, SystemMetrics

### Key Architecture Patterns

1. **Threading Model**: The agent uses separate threads for monitoring and socket server operations
2. **Configuration-Driven**: Backend URL, log paths, and service lists are fetched from remote backend API
3. **Fallback Strategy**: Data is saved locally if backend is unavailable
4. **Socket-Based Control**: Web interface communicates with agent via Unix domain sockets

### Data Flow
1. Agent fetches project configuration from backend API (`/api/projects` and `/api/workers`)
2. Monitoring cycle runs every N seconds (configurable):
   - Parse logs from configured paths
   - Collect system metrics
   - Monitor service statuses
   - Send data to backend API (`/api/monitoring-data`)
   - Fall back to local storage if backend unavailable

## Configuration

The agent uses `config.yaml` for configuration:
- **backend_url**: Backend API endpoint
- **socket.path**: Unix socket path (auto-detected: `/run/devopin-agent.sock` in production, `./tmp/devopin_agent.sock` in development)
- **setting.monitoring_interval**: Monitoring cycle interval in seconds
- **logging**: Log level and file configuration

## Socket Commands

The socket server accepts JSON commands:
- `{"command": "status"}` - Check agent/service status
- `{"command": "start", "service": "nginx"}` - Start service
- `{"command": "stop", "service": "nginx"}` - Stop service  
- `{"command": "restart", "service": "nginx"}` - Restart service
- `{"command": "enable", "service": "nginx"}` - Enable service
- `{"command": "disable", "service": "nginx"}` - Disable service
- `{"command": "logs_stream", "service": "nginx"}` - Start real-time log streaming
- `{"command": "logs_stop", "stream_id": "optional"}` - Stop log streaming (all streams if no ID)

### Real-time Log Streaming

The agent supports real-time log streaming via `journalctl -u <service> -f --output=json`. When backend opens the logs view, it sends a `logs_stream` command to spawn journalctl and stream output back to backend in real-time.

**Usage:**
```bash
# Start streaming logs for a service
echo '{"command": "logs_stream", "service": "devopin-agent"}' | socat - UNIX-CONNECT:./tmp/devopin_agent.sock

# Test with the provided script
python3 test_log_streaming.py --service devopin-agent

# Stop streaming
python3 test_log_streaming.py --stop
```

**Stream Response Format:**
- `logs_stream_started` - Initial confirmation with stream_id
- `logs_data` - Real-time log entries with JSON data from journalctl
- `logs_stream_ended` - Stream termination notification

## Log Parsing Support

The agent supports multiple log formats (implemented in core/parser.py):
- **Laravel**: `[2024-01-15 10:30:45] production.ERROR: message {"context":"data"}`
- **Django/Flask**: `2024-01-15 10:30:45,123 ERROR message [file.py:123]`
- **Node.js**: `2024-01-15T10:30:45.123Z ERROR: message at Controller (file.js:123:45)`
- **Python**: `2024-01-15 10:30:45,123 - ERROR - message`
- **FastAPI**: Custom pattern with module and file information

Each framework has specific regex patterns for extracting timestamp, level, message, and context information.

## API Integration

The agent communicates with the Devopin backend via HTTP JSON API:
- `GET /api/projects` - Fetch log paths and framework types
- `GET /api/workers` - Fetch services to monitor
- `POST /api/monitoring-data` - Send collected monitoring data

Data is sent in structured JSON format with timestamps, logs, system metrics, and service statuses.

## Security Considerations

- Agent runs with appropriate user permissions (devopin user in production)
- Unix socket has restricted permissions (0o666 in development, 0o660 in production)
- Command whitelist validation for socket commands
- Input sanitization and timeout protection
- No sensitive data logging
- Systemd security hardening (NoNewPrivileges, PrivateTmp, ProtectSystem)

## File Locations

### Development
- Socket: `./tmp/devopin_agent.sock`
- Config: `config.yaml`
- Logs: Console output

### Production
- Socket: `/run/devopin-agent/devopin-agent.sock`
- Config: `/etc/devopin/config.yaml`
- Binary: `/opt/devopin-agent/devopin-agent`
- Logs: `/var/log/devopin/` and systemd journal
- Data: `/var/lib/devopin-agent/`

## Important Development Notes

- The agent auto-detects production vs development environment based on file paths
- Use mock systemctl scripts for development when systemd is not available
- Configuration is fetched from backend API at runtime, local config.yaml provides defaults
- Socket communication uses JSON format with command validation
- All monitoring data includes timestamps and is structured for backend API consumption