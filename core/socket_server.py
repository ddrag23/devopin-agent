import socket
import json
import threading
import logging
import os
import subprocess
import time
import signal
from pathlib import Path
from typing import Dict, Any, Optional
from .config import load_config

logger = logging.getLogger(__name__)

# Socket path logic with config support
def get_default_socket_path() -> str:
    """Get appropriate socket path from config.yaml or fallback to default."""
    try:
        config = load_config()
        socket_path = config.get('socket', {}).get('path')
        
        if socket_path:
            # If it's a relative path, make it absolute
            if not os.path.isabs(socket_path):
                project_root = Path(__file__).parent.parent.absolute()
                socket_path = str(project_root / socket_path)
            
            # Ensure directory exists
            socket_dir = os.path.dirname(socket_path)
            if socket_dir and not os.path.exists(socket_dir):
                os.makedirs(socket_dir, exist_ok=True)
            
            return socket_path
            
    except Exception as e:
        logger.warning(f"Failed to load socket path from config: {e}, using fallback")
    
    # Fallback logic (same as before)
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
        self.active_streams = {}  # Track active log streams by client id
        self.stream_lock = threading.Lock()
        self.command_handlers = {
            "start": self._handle_start_service,
            "stop": self._handle_stop_service,
            "restart": self._handle_restart_service,
            "status": self._handle_status_check,
            "enable": self._handle_enable_service,
            "disable": self._handle_disable_service,
            "logs_stream": self._handle_logs_stream,
            "logs_stop": self._handle_logs_stop,
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
            
            # Set permissions for socket file from config
            try:
                config = load_config()
                socket_permissions = config.get('socket', {}).get('permissions', 0o666)
                os.chmod(self.socket_path, socket_permissions)
            except Exception as e:
                logger.warning(f"Failed to read socket permissions from config: {e}, using default 0o666")
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
        
        # Stop all active log streams
        with self.stream_lock:
            stream_ids = list(self.active_streams.keys())
            for stream_id in stream_ids:
                stream_info = self.active_streams[stream_id]
                self._stop_log_stream(stream_id, stream_info)
        
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
            command = command_data.get("command")
            response = self._execute_command(command_data, client_socket)
            
            # For streaming commands, don't close socket immediately
            if command == "logs_stream" and response.get("streaming"):
                logger.info(f"Started streaming for command: {command}")
                # Socket will be closed when stream ends
                return
            else:
                self._send_response(client_socket, response)
            
        except Exception as e:
            logger.error(f"Error handling client: {e}")
            response = {"success": False, "message": f"Server error: {str(e)}"}
            self._send_response(client_socket, response)
        
        finally:
            # Only close if not streaming
            command = None
            try:
                command_data = json.loads(data) if 'data' in locals() else {}
                command = command_data.get("command")
            except:
                pass
            
            if command != "logs_stream":
                client_socket.close()
    
    def _send_response(self, client_socket, response: Dict[str, Any]):
        """Send response back to client"""
        try:
            response_json = json.dumps(response)
            client_socket.send(response_json.encode())
        except Exception as e:
            logger.error(f"Error sending response: {e}")
    
    def _execute_command(self, command_data: Dict[str, Any], client_socket=None) -> Dict[str, Any]:
        """Execute the received command"""
        command = command_data.get("command")
        service_name = command_data.get("service", "")
        stream_id = command_data.get("stream_id", "")
        
        if not command:
            return {"success": False, "message": "No command specified"}
        
        handler = self.command_handlers.get(command)
        if not handler:
            return {"success": False, "message": f"Unknown command: {command}"}
        
        try:
            # Special handling for streaming commands that need client socket
            if command == "logs_stream":
                return handler(service_name, client_socket)
            elif command == "logs_stop":
                return handler(stream_id)
            else:
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
    
    def _handle_logs_stream(self, service_name: str, client_socket=None) -> Dict[str, Any]:
        """Handle real-time log streaming command"""
        if not service_name:
            return {"success": False, "message": "Service name required for log streaming"}
        
        if not client_socket:
            return {"success": False, "message": "Client socket required for streaming"}
        
        try:
            # Generate unique client ID
            client_id = f"{service_name}_{int(time.time() * 1000)}"
            
            # Check if journalctl is available
            try:
                subprocess.run(["which", "journalctl"], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                return {"success": False, "message": "journalctl command not available"}
            
            # Start journalctl process for real-time streaming
            cmd = ["journalctl", "-u", service_name, "-f", "--output=json"]
            
            # Spawn journalctl process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )
            
            # Store stream info
            with self.stream_lock:
                self.active_streams[client_id] = {
                    "process": process,
                    "service": service_name,
                    "client_socket": client_socket,
                    "start_time": time.time()
                }
            
            # Send initial success response
            initial_response = {
                "success": True,
                "message": f"Log streaming started for {service_name}",
                "stream_id": client_id,
                "command": "logs_stream_started"
            }
            client_socket.send((json.dumps(initial_response) + "\n").encode())
            
            # Start streaming thread
            stream_thread = threading.Thread(
                target=self._stream_logs_to_client,
                args=(client_id, process, client_socket),
                daemon=True
            )
            stream_thread.start()
            
            return {"success": True, "streaming": True, "stream_id": client_id}
            
        except Exception as e:
            logger.error(f"Error starting log stream for {service_name}: {e}")
            return {"success": False, "message": f"Failed to start log streaming: {str(e)}"}
    
    def _handle_logs_stop(self, stream_id: str | None = None) -> Dict[str, Any]:
        """Handle stop log streaming command"""
        try:
            with self.stream_lock:
                if stream_id:
                    # Stop specific stream
                    if stream_id in self.active_streams:
                        stream_info = self.active_streams[stream_id]
                        self._stop_log_stream(stream_id, stream_info)
                        return {"success": True, "message": f"Log stream {stream_id} stopped"}
                    else:
                        return {"success": False, "message": f"Stream {stream_id} not found"}
                else:
                    # Stop all streams
                    stopped_count = 0
                    stream_ids = list(self.active_streams.keys())
                    for sid in stream_ids:
                        stream_info = self.active_streams[sid]
                        self._stop_log_stream(sid, stream_info)
                        stopped_count += 1
                    
                    return {"success": True, "message": f"Stopped {stopped_count} log streams"}
                    
        except Exception as e:
            logger.error(f"Error stopping log streams: {e}")
            return {"success": False, "message": f"Failed to stop log streaming: {str(e)}"}
    
    def _stream_logs_to_client(self, client_id: str, process: subprocess.Popen, client_socket):
        """Stream journalctl output to client in real-time"""
        try:
            logger.info(f"Starting log stream for client {client_id}")
            
            while True:
                # Check if process is still running
                if process.poll() is not None:
                    logger.info(f"journalctl process ended for client {client_id}")
                    break
                
                # Check if stream still exists
                with self.stream_lock:
                    if client_id not in self.active_streams:
                        logger.info(f"Stream {client_id} was stopped")
                        break
                
                # Read line from journalctl
                try:
                    line = process.stdout.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    
                    # Send log line to client
                    log_data = {
                        "success": True,
                        "command": "logs_data",
                        "stream_id": client_id,
                        "data": line.strip(),
                        "timestamp": time.time()
                    }
                    
                    message = json.dumps(log_data) + "\n"
                    client_socket.send(message.encode())
                    
                except Exception as e:
                    logger.error(f"Error reading/sending log data for {client_id}: {e}")
                    break
            
        except Exception as e:
            logger.error(f"Error in log streaming for {client_id}: {e}")
        finally:
            # Clean up stream
            with self.stream_lock:
                if client_id in self.active_streams:
                    stream_info = self.active_streams[client_id]
                    self._stop_log_stream(client_id, stream_info)
            
            # Send end message
            try:
                end_message = {
                    "success": True,
                    "command": "logs_stream_ended",
                    "stream_id": client_id,
                    "message": "Log streaming ended"
                }
                client_socket.send((json.dumps(end_message) + "\n").encode())
            except:
                pass
    
    def _stop_log_stream(self, client_id: str, stream_info: Dict[str, Any]):
        """Stop a specific log stream"""
        try:
            process = stream_info["process"]
            
            # Terminate the journalctl process
            if process.poll() is None:
                process.terminate()
                # Wait a bit for graceful termination
                time.sleep(0.5)
                if process.poll() is None:
                    process.kill()
            
            # Remove from active streams
            if client_id in self.active_streams:
                del self.active_streams[client_id]
            
            logger.info(f"Stopped log stream {client_id} for service {stream_info['service']}")
            
        except Exception as e:
            logger.error(f"Error stopping log stream {client_id}: {e}")


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