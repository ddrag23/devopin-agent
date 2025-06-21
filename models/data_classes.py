from typing import Optional,Dict,List
from dataclasses import dataclass
@dataclass
class LogEntry:
    """Data class for parsed log entries"""
    timestamp: str
    level: str
    message: str
    context : Optional[str] = None
    controller: Optional[str] = None
    line_number: Optional[str] = None
    file_path: Optional[str] = None
    stack_trace: Optional[str] = None

@dataclass
class SystemMetrics:
    """Data class for system metrics"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_available: int
    disk_usage: Dict[str, float]
    network_io: Dict[str, int]
    load_average: List[float]

@dataclass
class ServiceStatus:
    """Data class for service status"""
    name: str
    status: str
    active: bool
    enabled: bool
    uptime: Optional[str] = None