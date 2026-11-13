"""
MAHOUN Logging Utilities
========================

Provides consistent logging setup across all pipeline modules.
This is a wrapper around logging_utils for backward compatibility.
"""

import logging
import sys
from typing import Optional


def setup_logger(
    name: str,
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Set up and return a configured logger instance.
    
    Args:
        name: Logger name (usually module __name__)
        level: Logging level (default: INFO)
        format_string: Custom format string (optional)
    
    Returns:
        Configured Logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        
        if format_string is None:
            format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        formatter = logging.Formatter(format_string)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    
    return logger


# Alias for compatibility with logging_utils
get_logger = setup_logger


__all__ = ["setup_logger", "get_logger"]

