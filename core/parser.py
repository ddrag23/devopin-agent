import re
import logging
import os
import glob
from typing import Optional,List
from models.data_classes import LogEntry
logger = logging.getLogger(__name__)

class LogParser:
    """Handles parsing of different log file formats"""
    
    def __init__(self,offset_dir: str = ".offsets"):
        # Laravel log pattern
        self.laravel_pattern = re.compile(
            r'\[(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\]\s+'
            r'(?P<environment>\w+)\.(?P<level>\w+):\s+'
            r'(?P<message>.*?)(?=\s*\{)'
            r'\s(?P<context>\{.*\})?$',
            re.DOTALL
        )
        
        # Python log pattern (Django/Flask)
        self.python_pattern = re.compile(
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
        
        # Generic error patterns for extracting controller/file info
        self.controller_patterns = [
            re.compile(r'(?:Controller|controller)\\(?P<controller>\w+Controller)'),
            re.compile(r'at\s+(?P<controller>\w+Controller)'),
            re.compile(r'in\s+(?P<file>[^:]+):(?P<line>\d+)'),
            re.compile(r'File\s+"(?P<file>[^"]+)",\s+line\s+(?P<line>\d+)'),
        ]
        self.offset_dir = offset_dir
        os.makedirs(self.offset_dir, exist_ok=True)
        
    def parse_laravel_log(self, log_line: str) -> Optional[LogEntry]:
        """Parse Laravel log format"""
        match = self.laravel_pattern.match(log_line.strip())
        if not match:
            return None
            
        data = match.groupdict()
        # Extract controller info from message or context
        controller, line_number, file_path = self._extract_error_location(data['message'])
        
        return LogEntry(
            timestamp=data['timestamp'],
            level=data['level'].upper(),
            message=data['message'],
            context=data['context'],
            controller=controller,
            line_number=line_number,
            file_path=file_path
        )

    def parse_python_log(self, log_line: str) -> Optional[LogEntry]:
        """Parse Python (Django/Flask) log format"""
        match = self.python_pattern.match(log_line.strip())
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

    def _extract_error_location(self, message: str) -> tuple:
        """
        Extract controller/class/function, line number, and file path
        from Laravel, Python, and Node.js logs.
        """
        controller = None
        line_number = None
        file_path = None

        self.controller_patterns = [
            # Laravel: at /var/www/.../UserController.php:87
            re.compile(r'at (?P<path>/[^\s]+/)(?P<controller>\w+Controller)\.php:(?P<line>\d+)'),

            # Laravel: UserController::method() at /path/file.php:123
            re.compile(r'(?P<controller>\w+Controller)::\w+\(.*?\).*?at (?P<file>/[^\s]+):(?P<line>\d+)'),

            # Python style
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

    def parse_log_file(self, file_path: str, log_type: str) -> List[LogEntry]:
        """Parse log file or directory containing logs"""
        entries = []

        parser_map = {
            'laravel': self.parse_laravel_log,
            'python': self.parse_python_log,
            'nodejs': self.parse_nodejs_log
        }

        parser = parser_map.get(log_type.lower())
        if not parser:
            logger.error(f"Unsupported log type: {log_type}")
            return []

        # Jika file_path adalah folder
        if os.path.isdir(file_path):
            log_files = sorted(glob.glob(os.path.join(file_path, '*.log')))
        elif os.path.isfile(file_path):
            log_files = [file_path]
        else:
            logger.error(f"Log file or directory not found: {file_path}")
            return []

        for log_file in log_files:
            try:
                last_offset = self._load_offset(log_file)
                with open(log_file, 'r', encoding='utf-8') as f:
                    f.seek(last_offset)
                    for line in f:
                        if line.strip():
                            entry = parser(line)
                            if entry:
                                entries.append(entry)
                    self._save_offset(log_file, f.tell())  # Simpan posisi terakhir
            except Exception as e:
                logger.error(f"Error parsing log file {log_file}: {e}")

        return entries
    
    def _get_offset_file(self, log_file: str) -> str:
        log_name = os.path.basename(log_file)
        return os.path.join(self.offset_dir, f"{log_name}.offset")

    def _load_offset(self, log_file: str) -> int:
        offset_path = self._get_offset_file(log_file)
        if os.path.exists(offset_path):
            with open(offset_path, 'r') as f:
                try:
                    return int(f.read())
                except Exception:
                    return 0
        return 0

    def _save_offset(self, log_file: str, offset: int):
        offset_path = self._get_offset_file(log_file)
        with open(offset_path, 'w') as f:
            f.write(str(offset))
