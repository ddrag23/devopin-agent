# Devopin Agent

A comprehensive system monitoring and log parsing agent for the Devopin platform. This agent provides real-time system metrics collection, log file parsing, service monitoring, and remote control capabilities via Unix sockets.

## Features

- 📊 **System Monitoring**: CPU, memory, disk usage, and network I/O metrics
- 📝 **Log Parsing**: Support for Laravel, Django, Flask, Node.js, and Python log formats  
- 🔧 **Service Control**: Start, stop, restart, enable, and disable system services via web interface
- 🌐 **Remote Communication**: Unix socket server for secure local control
- 📤 **Data Transmission**: Sends monitoring data to Devopin backend
- 🔒 **Security**: Systemd hardening, user isolation, and permission controls
- 📦 **Easy Installation**: One-command installation with systemd integration

## Quick Installation

### Option 1: Direct Installation (Recommended)
```bash
# Download and install
curl -fsSL https://install.devopin.com/agent.sh | sudo bash

# Or download manually
wget https://releases.devopin.com/agent/install.sh
chmod +x install.sh
sudo ./install.sh install
```

### Option 2: Build from Source
```bash
# Clone repository
git clone https://github.com/yourusername/devopin-agent.git
cd devopin-agent

# Install using make
sudo make install

# Or use installation script
sudo ./install.sh install
```

### Option 3: Package Installation (Future)
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install devopin-agent

# RHEL/CentOS/Fedora
sudo dnf install devopin-agent
```

## System Requirements

- **Operating System**: Linux with systemd
- **Python**: 3.8 or higher
- **Privileges**: Root access for installation
- **Dependencies**: systemctl, python3-pip

## Configuration

The main configuration file is located at `/etc/devopin-agent/config.yaml`:

```yaml
# Backend configuration
backend_url: "https://your-devopin-backend.com"

# Socket configuration
socket:
  path: "/run/devopin-agent.sock"
  permissions: 0o660
  timeout: 30

# Monitoring settings
setting:
  monitoring_interval: 60  # seconds
  log_retention_days: 30
  max_log_entries_per_cycle: 1000

# Logging
logging:
  level: "INFO"
  file: "/var/log/devopin-agent/agent.log"
```

## Usage

### Service Management
```bash
# Start the agent
sudo systemctl start devopin-agent

# Enable auto-start on boot
sudo systemctl enable devopin-agent

# Check status
sudo systemctl status devopin-agent

# View logs
sudo journalctl -u devopin-agent -f

# Restart service
sudo systemctl restart devopin-agent
```

### Socket Communication
The agent provides a Unix socket interface for local control:

```bash
# Check agent status
echo '{"command": "status"}' | socat - UNIX-CONNECT:/run/devopin-agent.sock

# Control services
echo '{"command": "start", "service": "nginx"}' | socat - UNIX-CONNECT:/run/devopin-agent.sock
echo '{"command": "stop", "service": "nginx"}' | socat - UNIX-CONNECT:/run/devopin-agent.sock
echo '{"command": "restart", "service": "nginx"}' | socat - UNIX-CONNECT:/run/devopin-agent.sock
```

### Development Mode
```bash
# Run directly (for development)
cd /path/to/devopin-agent
python3 main.py

# Socket will be created at: ./tmp/devopin_agent.sock

# Test socket
echo '{"command":"status"}' | socat - UNIX-CONNECT:./tmp/devopin_agent.sock
```

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Interface │────│  Unix Socket     │────│  Agent Core     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                       ┌─────────────────────────────────┼─────────────────────────────────┐
                       │                                 │                                 │
                ┌──────▼──────┐                 ┌────────▼────────┐                ┌──────▼──────┐
                │Log Parser   │                 │System Monitor   │                │Service      │
                │             │                 │                 │                │Monitor      │
                │• Laravel    │                 │• CPU Usage      │                │             │
                │• Django     │                 │• Memory Usage   │                │• systemctl  │
                │• Flask      │                 │• Disk Usage     │                │• Status     │
                │• Node.js    │                 │• Network I/O    │                │• Control    │
                │• Python     │                 └─────────────────┘                └─────────────┘
                └─────────────┘                                                            │
                       │                                                                   │
                       └───────────────────────┐         ┌─────────────────────────────────┘
                                               │         │
                                        ┌──────▼─────────▼──────┐
                                        │   Backend API         │
                                        │   (HTTP/JSON)         │
                                        └───────────────────────┘
```

## Security

### System Security
- Runs as unprivileged `devopin` user
- Systemd security hardening enabled
- Read-only filesystem access where possible
- Limited system call access
- No new privileges allowed

### Socket Security
- Unix domain socket with restricted permissions
- Command whitelist validation
- Timeout protection
- Input sanitization

### File Permissions
```
/usr/local/lib/devopin-agent/     # 755 root:root
/etc/devopin-agent/               # 755 root:root  
/etc/devopin-agent/config.yaml    # 640 root:devopin
/var/log/devopin-agent/           # 750 devopin:devopin
/run/devopin-agent.sock           # 660 devopin:devopin
```

## Monitoring Data

The agent collects and transmits:

### System Metrics
- CPU usage percentage
- Memory usage and availability  
- Disk usage per mount point
- Network I/O statistics
- System load averages

### Log Data
- Application logs (Laravel, Django, Flask, etc.)
- Error tracking with stack traces
- Log levels and timestamps
- Request/response information

### Service Status
- Service active/inactive status
- Service enabled/disabled status
- Service uptime information
- Control command results

## Log Format Support

### Laravel
```
[2024-01-15 10:30:45] production.ERROR: Error message {"context":"data"} 
```

### Django/Flask  
```
2024-01-15 10:30:45,123 ERROR Error message [file.py:123]
```

### Node.js
```
2024-01-15T10:30:45.123Z ERROR: Error message at Controller (file.js:123:45)
```

### Python
```
2024-01-15 10:30:45,123 - ERROR - Error message
```

## API Integration

The agent communicates with the Devopin backend via HTTP JSON API:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "logs": {
    "laravel_1": [
      {
        "timestamp": "2024-01-15T10:30:45Z",
        "level": "ERROR", 
        "message": "Database connection failed",
        "context": "{\"host\":\"localhost\"}"
      }
    ]
  },
  "system_metrics": {
    "timestamp": "2024-01-15T10:30:45Z",
    "cpu_percent": 45.2,
    "memory_percent": 67.8,
    "memory_available": 2147483648,
    "disk_usage": {
      "/": {"total": 1000000000, "used": 500000000, "free": 500000000, "percent": 50.0}
    }
  },
  "services": [
    {
      "name": "nginx",
      "status": "active", 
      "active": true,
      "enabled": true,
      "uptime": "2d 5h 30m"
    }
  ]
}
```

## Development

### Setup Development Environment
```bash
# Clone repository
git clone https://github.com/yourusername/devopin-agent.git
cd devopin-agent

# Install development dependencies
make dev-install

# Run linting
make lint

# Format code
make format

# Run in development mode
python3 main.py
```

### Code Standards
- **Linting**: ruff with strict configuration
- **Formatting**: ruff formatter 
- **Type Checking**: mypy with strict mode
- **Python Version**: 3.8+ compatibility
- **Line Length**: 88 characters
- **Import Style**: single-line imports

### Project Structure
```
devopin-agent/
├── core/                    # Core modules
│   ├── config.py           # Configuration loading
│   ├── monitor_agent.py    # Main monitoring logic  
│   ├── parser.py           # Log parsing
│   ├── service.py          # Service monitoring
│   ├── socket_server.py    # Unix socket server
│   └── system.py           # System metrics
├── models/                  # Data models
│   └── data_classes.py     # Data structures
├── main.py                  # Entry point
├── config.yaml.example     # Example configuration
├── install.sh              # Installation script
├── Makefile                # Build system
├── pyproject.toml          # Project configuration
├── devopin-agent.service   # Systemd service
└── README.md               # Documentation
```

## Troubleshooting

### Common Issues

**Agent won't start**
```bash
# Check service status
sudo systemctl status devopin-agent

# Check logs
sudo journalctl -u devopin-agent -f

# Verify configuration
sudo /usr/local/lib/devopin-agent/venv/bin/python -m yaml /etc/devopin-agent/config.yaml
```

**Socket connection failed**
```bash
# Check socket exists
ls -la /run/devopin-agent.sock

# Check permissions
sudo systemctl show devopin-agent -p User,Group

# Test socket manually
echo '{"command": "status"}' | sudo -u devopin socat - UNIX-CONNECT:/run/devopin-agent.sock
```

**High CPU usage**
```bash
# Reduce monitoring frequency
sudo nano /etc/devopin-agent/config.yaml
# Increase monitoring_interval value

# Restart service
sudo systemctl restart devopin-agent
```

### Debug Mode
Enable debug logging:
```yaml
logging:
  level: "DEBUG"
  file: "/var/log/devopin-agent/agent.log"
```

## Uninstallation

```bash
# Using installation script
sudo ./install.sh uninstall

# Using make
sudo make uninstall

# Manual cleanup
sudo systemctl stop devopin-agent
sudo systemctl disable devopin-agent
sudo rm -rf /usr/local/lib/devopin-agent
sudo rm -rf /etc/devopin-agent
sudo rm -f /etc/systemd/system/devopin-agent.service
sudo systemctl daemon-reload
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes following code standards
4. Run tests and linting
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- **Documentation**: https://docs.devopin.com
- **Issues**: https://github.com/yourusername/devopin-agent/issues
- **Discussions**: https://github.com/yourusername/devopin-agent/discussions

## Changelog

### v1.0.0
- Initial release
- System monitoring capabilities
- Log parsing for multiple frameworks
- Unix socket control interface
- Systemd integration with security hardening
- Web interface integration