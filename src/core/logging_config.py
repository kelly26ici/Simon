# src/core/logging_config.py
from __future__ import annotations

import os
import sys
from loguru import logger

# Define standardized colorized format for console output
CONSOLE_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

FILE_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} - "
    "{message}"
)


def configure_logging(
    level: str | None = None,
    log_file: str | None = "logs/samantha.log",
) -> None:
    """
    Configures Loguru logging with explicit color schemes:
      - SUCCESS: Bold Green
      - WARNING: Bold Yellow
      - ERROR: Bold Red
      - CRITICAL: Bold White on Red background
      - INFO: Bold Blue / Cyan
      - DEBUG: Blue
    """
    active_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    # Configure custom level styling
    try:
        logger.level("SUCCESS", color="<bold><green>")
        logger.level("WARNING", color="<bold><yellow>")
        logger.level("ERROR", color="<bold><red>")
        logger.level("CRITICAL", color="<bold><white><bg red>")
        logger.level("INFO", color="<bold><blue>")
        logger.level("DEBUG", color="<blue>")
    except Exception:
        pass

    # Remove existing default handlers
    logger.remove()

    # Add colorized stdout/stderr sink
    logger.add(
        sys.stderr,
        format=CONSOLE_LOG_FORMAT,
        level=active_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Optional file logger sink
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        logger.add(
            log_file,
            format=FILE_LOG_FORMAT,
            level=active_level,
            rotation="100 MB",
            retention="14 days",
            compression="zip",
            enqueue=True,
        )


# Automatically initialize logging upon module import
configure_logging()
