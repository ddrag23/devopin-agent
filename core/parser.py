import re
import logging
import os
import glob
import json
from typing import Optional,List
from datetime import datetime
from models.data_classes import LogEntry
from dateutil import parser
logger = logging.getLogger(__name__)

class LogParser:
    """Handles parsing of different log file formats"""
    
    def __init__(self, timestamp_file: str = "last_timestamp.json"):
        # Laravel log pattern - updated to match PRD specification
        self.laravel_pattern = re.compile(r"\[(.*?)\]\s(\w+)\.(\w+):\s(.+)")
        self.timestamp_file = timestamp_file
        
        # django_flask log pattern (Django/Flask)
        self.django_flask = re.compile(
            r'(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}[,.]?\d*)\s+'
            r'(?P<level>\w+)\s+'
            r'(?P<message>.*?)(?:\s+\[(?P<file>.*?):(?P<line>\d+)\])?'
        )
        
        # Node.js log pattern
        self.nodejs_pattern = re.compile(
            r'(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)\s+'
            r'(?P<level>\w+):\s+'
            r'(?P<message>.*?)(?:\s+at\s+(?P<controller>.*?)\s+\((?P<file>.*?):(?P<line>\d+):\d+\))?'
        )
        
        self.python_pattern = re.compile(
            r'(?P<timestamp>\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}[.,]?\d*)\s*-\s*'
            r'(?P<level>\w+)\s*-\s*'
            r'(?P<message>.+)'
        )
        
        # FastAPI log pattern
        self.fastapi_pattern = re.compile(
            r'(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s*-\s*'
            r'(?P<module>[\w.]+)\s*-\s*'
            r'(?P<level>\w+)\s*-\s*'
            r'(?P<file>\w+\.py):(?P<line>\d+)\s*-\s*'
            r'(?P<message>.+)'
        )

        
        # Generic error patterns for extracting controller/file info
        self.controller_patterns = [
            re.compile(r'(?:Controller|controller)\\(?P<controller>\w+Controller)'),
            re.compile(r'at\s+(?P<controller>\w+Controller)'),
            re.compile(r'in\s+(?P<file>[^:]+):(?P<line>\d+)'),
            re.compile(r'File\s+"(?P<file>[^"]+)",\s+line\s+(?P<line>\d+)'),
        ]
        
    def save_last_timestamp(self, project_id: str, timestamp: datetime):
        """Save the last processed timestamp with atomic writing to prevent corruption."""
        data = {}
        
        # Try to load existing data with error handling
        if os.path.exists(self.timestamp_file):
            try:
                with open(self.timestamp_file, "r") as f:
                    content = f.read().strip()
                    if content:  # Only parse if file has content
                        data = json.loads(content)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read timestamp file {self.timestamp_file}: {e}. Starting fresh.")
                data = {}

        # Update the timestamp
        data[str(project_id)] = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        # Write atomically using temporary file
        temp_file = self.timestamp_file + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename
            os.rename(temp_file, self.timestamp_file)
            logger.debug(f"Saved timestamp for project {project_id}: {timestamp}")
        except Exception as e:
            logger.error(f"Failed to save timestamp for project {project_id}: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def get_last_timestamp(self, project_id: str) -> Optional[datetime]:
        """Get the last processed timestamp from cache with error handling."""
        if os.path.exists(self.timestamp_file):
            try:
                with open(self.timestamp_file, "r") as f:
                    content = f.read().strip()
                    if content:  # Only parse if file has content
                        data = json.loads(content)
                        timestamp_str = data.get(str(project_id), None)
                        # If exists, convert to datetime directly
                        if timestamp_str:
                            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except (json.JSONDecodeError, IOError, ValueError) as e:
                logger.warning(f"Failed to read timestamp for project {project_id}: {e}")
                return None
        return None
        
    def parse_laravel_log(self, log_line: str) -> Optional[LogEntry]:
        """Parse Laravel log format"""
        match = self.laravel_pattern.match(log_line.strip())
        if not match:
            return None
            
        timestamp, _, level, message = match.groups()
        # Extract controller info from message
        controller, line_number, file_path = self._extract_error_location(message)
        
        return LogEntry(
            timestamp=timestamp,
            level=level.upper(),
            message=message.strip(),
            context=None,
            controller=controller,
            line_number=line_number,
            file_path=file_path
        )

    def parse_django_flask_log(self, log_line: str) -> Optional[LogEntry]:
        """Parse django_flask (Django/Flask) log format"""
        match = self.django_flask.match(log_line.strip())
        if not match:
            return None
            
        data = match.groupdict()
        
        controller, line_number, file_path = self._extract_error_location(data['message'])
        
        return LogEntry(
            timestamp=data['timestamp'],
            level=data['level'].upper(),
            message=data['message'],
            controller=controller,
            line_number=data.get('line') or line_number,
            file_path=data.get('file') or file_path
        )

    def parse_nodejs_log(self, log_line: str) -> Optional[LogEntry]:
        """Parse Node.js log format"""
        match = self.nodejs_pattern.match(log_line.strip())
        if not match:
            return None
            
        data = match.groupdict()
        
        return LogEntry(
            timestamp=data['timestamp'],
            level=data['level'].upper(),
            message=data['message'],
            controller=data.get('controller'),
            line_number=data.get('line'),
            file_path=data.get('file')
        )
    def parse_python_log(self, line: str) -> Optional[LogEntry]:
        match = self.python_pattern.match(line)
        if not match:
            return None
        data = match.groupdict()
        return LogEntry(
            timestamp=data['timestamp'],
            level=data['level'].upper(),
            message=data['message'],
        )

    def parse_fastapi_log(self, line: str) -> Optional[LogEntry]:
        """Parse FastAPI log format: 2025-06-29 12:32:30 - app.api - INFO - route.py:59 - Running threshold monitoring..."""
        match = self.fastapi_pattern.match(line.strip())
        if not match:
            return None
        
        data = match.groupdict()
        return LogEntry(
            timestamp=data['timestamp'],
            level=data['level'].upper(),
            message=data['message'],
            controller=data['module'],
            line_number=data['line'],
            file_path=data['file']
        )


    def _extract_error_location(self, message: str) -> tuple:
        """
        Extract controller/class/function, line number, and file path
        from Laravel, django_flask, and Node.js logs.
        """
        controller = None
        line_number = None
        file_path = None

        self.controller_patterns = [
            # Laravel: at /var/www/.../UserController.php:87
            re.compile(r'at (?P<path>/[^\s]+/)(?P<controller>\w+Controller)\.php:(?P<line>\d+)'),

            # Laravel: UserController::method() at /path/file.php:123
            re.compile(r'(?P<controller>\w+Controller)::\w+\(.*?\).*?at (?P<file>/[^\s]+):(?P<line>\d+)'),

            # django_flask style
            re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<controller>\w+))?'),

            # Node.js
            re.compile(r'at (?P<controller>\w+) \((?P<file>[^:]+):(?P<line>\d+)(?::\d+)?\)'),
            re.compile(r'at (?P<file>[^:]+):(?P<line>\d+)(?::\d+)?'),
        ]

        for pattern in self.controller_patterns:
            match = pattern.search(message)
            if match:
                groups = match.groupdict()

                controller = groups.get('controller')
                line_number = groups.get('line')

                # Handle case where controller and path are separated
                if 'path' in groups and controller:
                    file_path = groups['path'] + controller + '.php'
                else:
                    file_path = groups.get('file')
                break

        return controller, line_number, file_path

    def parse_log_file(self, file_path: str, log_type: str, project_id: str |None= None) -> List[LogEntry]:
        """Parse log file or directory containing logs using timestamp-based approach"""
        entries = []

        parser_map = {
            'laravel': self.parse_laravel_log,
            'django': self.parse_django_flask_log,
            'flask': self.parse_django_flask_log,
            'nodejs': self.parse_nodejs_log,
            'python':self.parse_python_log,
            'fastapi':self.parse_fastapi_log,
        }

        parser_log = parser_map.get(log_type.lower())
        if not parser_log:
            logger.error(f"Unsupported log type: {log_type}")
            return []

        # Get last processed timestamp
        last_timestamp = None
        if project_id:
            last_timestamp = self.get_last_timestamp(project_id)

        # Jika file_path adalah folder
        if os.path.isdir(file_path):
            log_files = sorted(glob.glob(os.path.join(file_path, '*.log')))
        elif os.path.isfile(file_path):
            log_files = [file_path]
        else:
            logger.error(f"Log file or directory not found: {file_path}")
            return []

        new_entries_count = 0
        skipped_entries_count = 0
        
        for log_file in log_files:
            try:
                # Debug: Check file permissions
                file_stat = os.stat(log_file)
                # logger.info(f"File {log_file} - Size: {file_stat.st_size}, Mode: {oct(file_stat.st_mode)}, Owner: {file_stat.st_uid}:{file_stat.st_gid}")
                
                logger.info(f"Processing {log_file} with last_timestamp: {last_timestamp}")
                
                with open(log_file, 'r', encoding='utf-8') as f:
                    line_count = 0
                    file_new_entries = 0
                    file_skipped_entries = 0
                    
                    for line in f:
                        if line.strip():
                            entry = parser_log(line)
                            if entry:
                                # Skip log if timestamp is less than or equal to last_timestamp
                                if last_timestamp:
                                    try:
                                        format_timestamp = parser.parse(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                                        log_time = datetime.strptime(format_timestamp, "%Y-%m-%d %H:%M:%S")
                                        if log_time <= last_timestamp:
                                            file_skipped_entries += 1
                                            logger.debug(f"Skipping entry with timestamp {entry.timestamp} <= {last_timestamp}")
                                            continue
                                    except ValueError as e:
                                        logger.warning(f"Failed to parse timestamp '{entry.timestamp}': {e}")
                                        # If timestamp parsing fails, include the entry
                                        pass
                                
                                entries.append(entry)
                                file_new_entries += 1
                                # logger.debug(f"Added entry with timestamp {entry.timestamp}")
                            line_count += 1
                    
                    new_entries_count += file_new_entries
                    skipped_entries_count += file_skipped_entries
                    # logger.info(f"Processed {line_count} lines from {log_file}: {file_new_entries} new, {file_skipped_entries} skipped")
                    
            except PermissionError as e:
                logger.error(f"Permission denied reading log file {log_file}: {e}")
            except Exception as e:
                logger.error(f"Error parsing log file {log_file}: {e}")
                
        logger.info(f"Total: {new_entries_count} new entries, {skipped_entries_count} skipped entries")

        # Save last timestamp if we have new entries
        if entries and project_id:
            try:
                # Find the latest timestamp from all new entries
                latest_timestamp = None
                for entry in entries:
                    try:
                        format_timestamp_entry = parser.parse(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                        entry_time = datetime.strptime(format_timestamp_entry, "%Y-%m-%d %H:%M:%S")
                        if latest_timestamp is None or entry_time > latest_timestamp:
                            latest_timestamp = entry_time
                    except ValueError:
                        logger.warning(f"Skipping invalid timestamp in save: {entry.timestamp}")
                        continue
                
                if latest_timestamp:
                    self.save_last_timestamp(project_id, latest_timestamp)
                    logger.info(f"Saved latest timestamp for project {project_id}: {latest_timestamp}")
                    
            except Exception as e:
                logger.error(f"Failed to save timestamp for project {project_id}: {e}")

        return entries
