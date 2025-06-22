#!/usr/bin/env python3
"""
Comprehensive Monitoring Agent
Handles log parsing, system monitoring, and service monitoring
"""

import logging
from core.monitor_agent import MonitoringAgent
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitoring_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Main function to run the monitoring agent"""
    # Configuration
    BACKEND_URL = "http://localhost:8080"  # Ganti dengan URL backend Anda
    SERVICES_TO_MONITOR = [
        'nginx',
        'apache2', 
        'mysql',  
        'postgresql',
        'redis-server',
        'docker',
        'ssh'
    ]
    MONITORING_INTERVAL = 60  # seconds
    
    # Initialize agent
    agent = MonitoringAgent(backend_url=BACKEND_URL)
    
    logger.info("Monitoring Agent started")
    logger.info(f"Backend URL: {BACKEND_URL}")
    logger.info(f"Monitoring interval: {MONITORING_INTERVAL} seconds")
    logger.info(f"Services to monitor: {', '.join(SERVICES_TO_MONITOR)}")
    
    try:
        while True:
            agent.run_monitoring_cycle(SERVICES_TO_MONITOR)
            time.sleep(MONITORING_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Monitoring Agent stopped by user")
    except Exception as e:
        logger.error(f"Monitoring Agent crashed: {e}")

if __name__ == "__main__":
    main()