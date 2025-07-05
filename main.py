#!/usr/bin/env python3
"""Enhanced Devopin Monitoring Agent.

Handles log parsing, system monitoring, service monitoring, and socket control.
"""

import logging
import signal
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

from core.config import load_config
from core.monitor_agent import MonitoringAgent
from core.socket_server import AgentSocketServer

if TYPE_CHECKING:
    from types import FrameType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("devopin-agent.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class DevopinAgent:
    """Enhanced Devopin Agent with socket control support."""

    def __init__(self) -> None:
        """Initialize the Devopin Agent."""
        self.config: dict[str, Any] | None = None
        self.monitoring_agent: MonitoringAgent | None = None
        self.socket_server: AgentSocketServer | None = None
        self.is_running: bool = False
        self.monitoring_thread: threading.Thread | None = None
        self.socket_thread: threading.Thread | None = None

    def load_configuration(self) -> bool:
        """Load agent configuration.
        
        Returns:
            bool: True if configuration loaded successfully, False otherwise
        """
        try:
            self.config = load_config()
            if not self.config:
                logger.error("Failed to load configuration")
                return False

            logger.info("Configuration loaded successfully")
            logger.info("Backend URL: %s", self.config.get("backend_url", "Not configured"))

            return True

        except Exception:
            logger.exception("Error loading configuration")
            return False

    def initialize_components(self) -> bool:
        """Initialize monitoring and socket components.
        
        Returns:
            bool: True if components initialized successfully, False otherwise
        """
        try:
            if not self.config:
                logger.error("Configuration not loaded")
                return False

            # Initialize monitoring agent
            backend_url = self.config.get("backend_url")
            self.monitoring_agent = MonitoringAgent(backend_url=backend_url, config=self.config)

            # Initialize socket server
            socket_config = self.config.get("socket", {})
            socket_path = socket_config.get("path", "/tmp/devopin-agent.sock")
            self.socket_server = AgentSocketServer(socket_path)

            logger.info("Components initialized successfully")
            return True

        except Exception:
            logger.exception("Error initializing components")
            return False

    def start_socket_server(self) -> bool:
        """Start socket server in background thread.
        
        Returns:
            bool: True if socket server started successfully, False otherwise
        """
        def socket_worker() -> None:
            """Socket server worker function."""
            try:
                if self.socket_server and self.socket_server.start_server():
                    logger.info("Socket server started successfully")
                    # Keep socket server alive
                    while self.is_running and self.socket_server.is_running:
                        time.sleep(1)
                else:
                    logger.error("Failed to start socket server")
            except Exception:
                logger.exception("Socket server error")

        self.socket_thread = threading.Thread(target=socket_worker, daemon=True)
        self.socket_thread.start()

        # Wait a moment for socket to initialize
        time.sleep(0.5)
        return self.socket_server.is_running if self.socket_server else False

    def start_monitoring(self) -> None:
        """Start monitoring loop in background thread."""
        def monitoring_worker() -> None:
            """Monitoring worker function."""
            if not self.config or not self.monitoring_agent:
                logger.error("Configuration or monitoring agent not initialized")
                return

            monitoring_interval = self.config.get("setting", {}).get("monitoring_interval", 60)
            logger.info("Starting monitoring loop with %ds interval", monitoring_interval)

            while self.is_running:
                try:
                    # Run monitoring cycle
                    self.monitoring_agent.run_monitoring_cycle()

                    # Sleep for the configured interval
                    for _ in range(monitoring_interval):
                        if not self.is_running:
                            break
                        time.sleep(1)

                except Exception:
                    logger.exception("Error in monitoring cycle")
                    time.sleep(10)  # Wait before retrying

        self.monitoring_thread = threading.Thread(target=monitoring_worker, daemon=True)
        self.monitoring_thread.start()
        logger.info("Monitoring thread started")

    def start(self) -> bool:
        """Start the Devopin Agent.
        
        Returns:
            bool: True if agent started successfully, False otherwise
        """
        logger.info("Starting Enhanced Devopin Monitoring Agent...")

        # Load configuration
        if not self.load_configuration():
            return False

        # Initialize components
        if not self.initialize_components():
            return False

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.is_running = True

        # Start socket server
        if not self.start_socket_server():
            logger.error("Failed to start socket server")
            return False

        # Start monitoring
        self.start_monitoring()

        logger.info("Devopin Agent started successfully")
        logger.info("Agent is running... Press Ctrl+C to stop")

        return True

    def stop(self) -> None:
        """Stop the Devopin Agent."""
        logger.info("Stopping Devopin Agent...")

        self.is_running = False

        # Stop socket server
        if self.socket_server:
            self.socket_server.stop_server()

        # Wait for threads to finish (with timeout)
        if self.socket_thread and self.socket_thread.is_alive():
            self.socket_thread.join(timeout=5)

        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)

        logger.info("Devopin Agent stopped")

    def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    def _signal_handler(self, signum: int, frame: "FrameType | None") -> None:
        """Handle system signals for graceful shutdown.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        logger.info("Received signal %d, initiating shutdown...", signum)
        self.stop()


def main() -> None:
    """Main function."""
    # Create agent instance
    agent = DevopinAgent()

    try:
        # Start the agent
        if not agent.start():
            logger.error("Failed to start Devopin Agent")
            sys.exit(1)

        # Wait for shutdown
        agent.wait_for_shutdown()

    except KeyboardInterrupt:
        logger.info("Devopin Agent interrupted by user")
    except Exception:
        logger.exception("Devopin Agent crashed")
        sys.exit(1)
    finally:
        agent.stop()


if __name__ == "__main__":
    main()