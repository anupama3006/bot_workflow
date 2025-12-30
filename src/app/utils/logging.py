import logging
import re
import sys
from typing import Any, Dict

from pythonjsonlogger import jsonlogger

from .settings import SETTINGS


class SanitizedJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that sanitizes sensitive information."""

    SENSITIVE_KEYS = {'token', 'password', 'secret', 'authorization', 'api_key', 'access_token'}
    TOKEN_PATTERNS = [
        r'eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+',  # JWT tokens
        r'"token"\s*:\s*"[^"]*"',  # JSON token field
        r'\'token\'\s*:\s*\'[^\']*\''  # JSON token field with single quotes
    ]

    def process_log_record(self, log_record: Dict[str, Any]) -> Dict[str, Any]:
        """Process and sanitize log records before formatting."""
        # Sanitize the message field
        if 'message' in log_record and isinstance(log_record['message'], str):
            for pattern in self.TOKEN_PATTERNS:
                log_record['message'] = re.sub(pattern, '[REDACTED]', log_record['message'])

        # Process with parent class, passing the full log_record dict
        return super().process_log_record(log_record)

def setup_logging():
    default_logger = logging.getLogger()
    default_logger.setLevel(SETTINGS.logging_level)

    logger = logging.getLogger(SETTINGS.app_name)
    logger.setLevel(SETTINGS.app_logging_level)

    # Use sanitized JSON logging
    formatter = SanitizedJsonFormatter(
        fmt='%(levelname)s %(asctime)s %(name)s %(funcName)s %(lineno)d %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        json_default=str
    )

    log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    default_logger.addHandler(log_handler)

    # Prevent duplicate logs
    default_logger.propagate = False

    return logger

logger = setup_logging()
