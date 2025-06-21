from .parser import LogParser
from .system import SystemMonitor
from .service import ServiceMonitor
from ..models.data_classes import LogEntry,ServiceStatus,SystemMetrics
from typing import List,Dict,Any
import logging
import requests
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import os
import json

logger = logging.getLogger(__name__)

class MonitoringAgent:
    """Main monitoring agent class"""
    
    def __init__(self, backend_url:  str | None = None):
        self.log_parser = LogParser()
        self.system_monitor = SystemMonitor()
        self.service_monitor = ServiceMonitor()
        self.backend_url = backend_url
        
    def get_log_paths_from_backend(self) -> List[Dict[str, str]]:
        """Get log file paths from backend API"""
        if not self.backend_url:
            logger.warning("No backend URL configured")
            return []
            
        try:
            response = requests.get(f"{self.backend_url}/api/projects", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("data")
            else:
                logger.error(f"Failed to get log paths: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching log paths from backend: {e}")
            return []
    
    def parse_logs_from_backend(self) -> Dict[str, List[LogEntry]]:
        """Parse logs based on paths from backend"""
        projects = self.get_log_paths_from_backend()
        print(projects)
        log_paths = [(project.get("framework_type"),project.get("log_path")) for project in projects]
        parsed_logs = {}
        HOME = Path.home()
        for log_type, path in log_paths:
            logger.info(f"Parsing {log_type} log from: {path}")
            if path and log_type:
                path_obj = Path(path)
                full_path = path_obj if path_obj.is_absolute() else HOME / path_obj

                entries = self.log_parser.parse_log_file(str(full_path), log_type)
            else:
                entries = []
            parsed_logs[log_type] = entries
            logger.info(f"Parsed {len(entries)} entries from {log_type} log")
            
        return parsed_logs
    
    def monitor_system(self) -> SystemMetrics:
        """Get current system metrics"""
        return self.system_monitor.get_system_metrics()
    
    def monitor_services(self, service_names: List[str]) -> List[ServiceStatus]:
        """Monitor specified services"""
        return self.service_monitor.get_multiple_services_status(service_names)
    
    def send_data_to_backend(self, data: Dict[str, Any]) -> bool:
        """Send monitoring data to backend"""
        if not self.backend_url:
            logger.info("No backend URL configured, skipping data send")
            return False

        try:
            response = requests.post(
                f"{self.backend_url}/api/monitoring-data",
                json=data,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code == 200:
                logger.info("Successfully sent monitoring data to backend")
                return True
            else:
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text  # fallback kalau bukan JSON
                logger.error(f"Failed to send data to backend: {response.status_code} - {error_detail}")
                return False

        except Exception as e:
            logger.error(f"Error sending data to backend: {e}")
            return False

    
    def run_monitoring_cycle(self, services_to_monitor: List[str] | None = None):
        """Run a complete monitoring cycle"""
        if services_to_monitor is None:
            services_to_monitor = ['nginx', 'apache2', 'mysql', 'postgresql', 'redis-server']
        
        logger.info("Starting monitoring cycle...")
        
        # Parse logs
        logs = self.parse_logs_from_backend()
        
        # Get system metrics
        system_metrics = self.monitor_system()
        
        # Monitor services
        # service_statuses = self.monitor_services(services_to_monitor)
        service_statuses = []
        
        # Prepare data for backend
        monitoring_data = {
            'timestamp': datetime.now().isoformat(),
            'logs': {k: [asdict(entry) for entry in v] for k, v in logs.items()},
            'system_metrics': asdict(system_metrics),
            'services': [asdict(service) for service in service_statuses]
        }
        
        # Send to backend or save locally
        if not self.send_data_to_backend(monitoring_data):
            # Save locally if backend is not available
            self._save_data_locally(monitoring_data)
        
        logger.info("Monitoring cycle completed")
        return monitoring_data
    
    def _save_data_locally(self, data: Dict[str, Any]):
        """Save monitoring data locally as fallback"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = ".local_results"
        os.makedirs(folder, exist_ok=True)

        filename = f"monitoring_data_{timestamp}.json"
        filepath = os.path.join(folder, filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Monitoring data saved locally: {filepath}")
        except Exception as e:
            logger.error(f"Error saving data locally: {e}")
