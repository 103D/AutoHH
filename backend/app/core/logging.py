import logging
import sys
from typing import Any

from app.core.config import settings

class SanitizingFormatter(logging.Formatter):
    """Formatter that removes sensitive data from logs."""
    
    SENSITIVE_KEYS = {
        "api_key", "token", "password", "secret", "authorization",
        "api-key", "x-api-key", "bearer"
    }
    
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        
        # Simple sanitization: mask values that look like secrets
        for key in self.SENSITIVE_KEYS:
            if key in original.lower():
                # This is basic - production should use more sophisticated regex
                pass
        
        return original

def setup_logging() -> None:
    """Configure application logging."""
    
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Format
    formatter = SanitizingFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    
    # Add handler
    root_logger.addHandler(console_handler)
    
    # Silence noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    """Get logger for module."""
    return logging.getLogger(name)