import subprocess
import re
import logging
from typing import Optional,List
from ..models.data_classes import ServiceStatus
logger = logging.getLogger(__name__)

class ServiceMonitor:
    """Handles systemctl service monitoring"""
    
    def get_service_status(self, service_name: str) -> Optional[ServiceStatus]:
        """Get status of a specific systemctl service"""
        try:
            # Get service status
            result = subprocess.run(
                ['systemctl', 'is-active', service_name],
                capture_output=True,
                text=True
            )
            is_active = result.stdout.strip() == 'active'
            
            # Get enabled status
            result = subprocess.run(
                ['systemctl', 'is-enabled', service_name],
                capture_output=True,
                text=True
            )
            is_enabled = result.stdout.strip() == 'enabled'
            
            # Get detailed status
            result = subprocess.run(
                ['systemctl', 'status', service_name],
                capture_output=True,
                text=True
            )
            status_output = result.stdout
            
            # Extract uptime from status output
            uptime = None
            for line in status_output.split('\n'):
                if 'Active:' in line:
                    uptime_match = re.search(r'since (.+?);', line)
                    if uptime_match:
                        uptime = uptime_match.group(1)
                    break
            
            return ServiceStatus(
                name=service_name,
                status='active' if is_active else 'inactive',
                active=is_active,
                enabled=is_enabled,
                uptime=uptime
            )
            
        except Exception as e:
            logger.error(f"Error getting service status for {service_name}: {e}")
            return None

    def get_multiple_services_status(self, service_names: List[str]) -> List[ServiceStatus]:
        """Get status of multiple services"""
        services = []
        for service_name in service_names:
            status = self.get_service_status(service_name)
            if status:
                services.append(status)
        return services
