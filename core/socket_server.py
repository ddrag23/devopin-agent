import socket
import json
import threading
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Simple socket path logic
def get_default_socket_path() -> str:
    """Get appropriate socket path."""
    # Production: check if running as systemd service or has access to /run
    if os.access("/run", os.W_OK):
        return "/run/devopin-agent.sock"
    
    # Development: use project tmp directory
    project_root = Path(__file__).parent.parent.absolute()
    tmp_dir = project_root / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    return str(tmp_dir / "devopin_agent.sock")

DEFAULT_SOCKET_PATH = get_default_socket_path()

class AgentSocketServer:
    """Socket server untuk menerima perintah kontrol dari web interface"""
    
    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        self.socket_path = socket_path
        self.server_socket = None
        self.is_running = False
        self.command_handlers = {
            "start": self._handle_start_service,
            "stop": self._handle_stop_service,
            "restart": self._handle_restart_service,
            "status": self._handle_status_check,
            "enable": self._handle_enable_service,
            "disable": self._handle_disable_service,
        }
    
    def start_server(self):
        """Start the socket server"""
        try:
            # Remove existing socket file if it exists
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
            
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(5)
            
            # Set permissions for socket file
            os.chmod(self.socket_path, 0o666)
            
            self.is_running = True
            logger.info(f"Agent socket server started at {self.socket_path}")
            
            # Start server thread
            server_thread = threading.Thread(target=self._accept_connections, daemon=True)
            server_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start socket server: {e}")
            return False
    
    def stop_server(self):
        """Stop the socket server"""
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except:
                pass
        
        logger.info("Agent socket server stopped")
    
    def _accept_connections(self):
        """Accept and handle incoming connections"""
        while self.is_running:
            try:
                if self.server_socket is None:
                    logger.error("Server socket is not initialized.")
                    break
                client_socket, _ = self.server_socket.accept()
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_client, 
                    args=(client_socket,),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.is_running:  # Only log if server is supposed to be running
                    logger.error(f"Error accepting connection: {e}")
                break
    
    def _handle_client(self, client_socket):
        """Handle individual client connection"""
        try:
            # Receive data
            data = client_socket.recv(1024).decode().strip()
            
            if not data:
                return
            
            # Parse command
            try:
                command_data = json.loads(data)
            except json.JSONDecodeError:
                response = {"success": False, "message": "Invalid JSON format"}
                self._send_response(client_socket, response)
                return
            
            # Execute command
            response = self._execute_command(command_data)
            self._send_response(client_socket, response)
            
        except Exception as e:
            logger.error(f"Error handling client: {e}")
            response = {"success": False, "message": f"Server error: {str(e)}"}
            self._send_response(client_socket, response)
        
        finally:
            client_socket.close()
    
    def _send_response(self, client_socket, response: Dict[str, Any]):
        """Send response back to client"""
        try:
            response_json = json.dumps(response)
            client_socket.send(response_json.encode())
        except Exception as e:
            logger.error(f"Error sending response: {e}")
    
    def _execute_command(self, command_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the received command"""
        command = command_data.get("command")
        service_name = command_data.get("service", "")
        
        if not command:
            return {"success": False, "message": "No command specified"}
        
        handler = self.command_handlers.get(command)
        if not handler:
            return {"success": False, "message": f"Unknown command: {command}"}
        
        try:
            return handler(service_name)
        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return {"success": False, "message": f"Command execution failed: {str(e)}"}
    
    def _run_systemctl_command(self, action: str, service_name: str, timeout: int = 30) -> Dict[str, Any]:
        """Run systemctl command with error handling"""
        try:
            cmd = ["systemctl", action, service_name]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return {
                    "success": True, 
                    "message": f"Successfully {action}ed {service_name}",
                    "output": result.stdout.strip()
                }
            else:
                error_msg = result.stderr.strip() or f"Failed to {action} {service_name}"
                return {"success": False, "message": error_msg}
                
        except subprocess.TimeoutExpired:
            return {"success": False, "message": f"Timeout {action}ing service {service_name}"}
        except FileNotFoundError:
            return {"success": False, "message": "systemctl command not found"}
        except Exception as e:
            return {"success": False, "message": f"Error running systemctl: {str(e)}"}
    
    def _handle_start_service(self, service_name: str) -> Dict[str, Any]:
        """Handle start service command"""
        if not service_name:
            return {"success": False, "message": "Service name required"}
        
        return self._run_systemctl_command("start", service_name)
    
    def _handle_stop_service(self, service_name: str) -> Dict[str, Any]:
        """Handle stop service command"""
        if not service_name:
            return {"success": False, "message": "Service name required"}
        
        return self._run_systemctl_command("stop", service_name)
    
    def _handle_restart_service(self, service_name: str) -> Dict[str, Any]:
        """Handle restart service command"""
        if not service_name:
            return {"success": False, "message": "Service name required"}
        
        return self._run_systemctl_command("restart", service_name)
    
    def _handle_enable_service(self, service_name: str) -> Dict[str, Any]:
        """Handle enable service command"""
        if not service_name:
            return {"success": False, "message": "Service name required"}
        
        return self._run_systemctl_command("enable", service_name)
    
    def _handle_disable_service(self, service_name: str) -> Dict[str, Any]:
        """Handle disable service command"""
        if not service_name:
            return {"success": False, "message": "Service name required"}
        
        return self._run_systemctl_command("disable", service_name)
    
    def _handle_status_check(self, service_name: Optional[str] = None) -> Dict[str, Any]:
        """Handle status check command"""
        if service_name:
            # Check specific service status
            try:
                # Get active status
                result = subprocess.run(
                    ["systemctl", "is-active", service_name],
                    capture_output=True,
                    text=True
                )
                active_status = result.stdout.strip()
                
                # Get enabled status
                result = subprocess.run(
                    ["systemctl", "is-enabled", service_name],
                    capture_output=True,
                    text=True
                )
                enabled_status = result.stdout.strip()
                
                # Get detailed status
                result = subprocess.run(
                    ["systemctl", "status", service_name, "--no-pager", "-l"],
                    capture_output=True,
                    text=True
                )
                
                return {
                    "success": True,
                    "message": f"Service {service_name} status retrieved",
                    "data": {
                        "service": service_name,
                        "active": active_status,
                        "enabled": enabled_status,
                        "status_output": result.stdout
                    }
                }
                
            except Exception as e:
                return {"success": False, "message": f"Error checking service status: {str(e)}"}
        else:
            # Check agent status
            return {"success": True, "message": "Devopin agent is running and responsive"}


# Global socket server instance
_socket_server = None

def start_socket_server(socket_path: str = DEFAULT_SOCKET_PATH):
    """Start the socket server - function called from main.py"""
    global _socket_server
    
    try:
        _socket_server = AgentSocketServer(socket_path)
        if _socket_server.start_server():
            logger.info("Socket server started successfully")
            # Keep the server running
            while _socket_server.is_running:
                import time
                time.sleep(1)
        else:
            logger.error("Failed to start socket server")
    except KeyboardInterrupt:
        logger.info("Socket server interrupted")
    except Exception as e:
        logger.error(f"Socket server error: {e}")
    finally:
        if _socket_server:
            _socket_server.stop_server()

def stop_socket_server():
    """Stop the socket server"""
    global _socket_server
    if _socket_server:
        _socket_server.stop_server()
        _socket_server = None

def get_socket_server():
    """Get the current socket server instance"""
    return _socket_server

# Helper function untuk testing socket connection
def test_socket_connection(socket_path: str = DEFAULT_SOCKET_PATH) -> bool:
    """Test if socket server is accessible"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(socket_path)
        
        # Send test command
        test_cmd = {"command": "status"}
        sock.send(json.dumps(test_cmd).encode())
        
        # Receive response
        response = sock.recv(1024).decode()
        result = json.loads(response)
        
        sock.close()
        return result.get("success", False)
        
    except Exception:
        return False