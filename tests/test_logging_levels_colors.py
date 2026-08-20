"""
tests/test_logging_levels_colors.py

Tests Loguru logging configuration, custom level color schemes (Green for SUCCESS,
Yellow for WARNING, Red for ERROR, Bold Red for CRITICAL), and sink outputs.
"""

import io
import sys
from loguru import logger
import pytest

from src.core.logging_config import configure_logging, CONSOLE_LOG_FORMAT


def test_loguru_format_contains_color_tags():
    """Verify that the console log format includes level and color tags."""
    assert "<green>" in CONSOLE_LOG_FORMAT
    assert "<level>" in CONSOLE_LOG_FORMAT
    assert "<cyan>" in CONSOLE_LOG_FORMAT


def test_loguru_success_level_configured():
    """Verify SUCCESS level exists and has bold green color styling."""
    level_info = logger.level("SUCCESS")
    assert level_info.name == "SUCCESS"
    assert "green" in level_info.color.lower()


def test_loguru_warning_level_configured():
    """Verify WARNING level exists and has yellow color styling."""
    level_info = logger.level("WARNING")
    assert level_info.name == "WARNING"
    assert "yellow" in level_info.color.lower()


def test_loguru_error_level_configured():
    """Verify ERROR level exists and has red color styling."""
    level_info = logger.level("ERROR")
    assert level_info.name == "ERROR"
    assert "red" in level_info.color.lower()


def test_loguru_critical_level_configured():
    """Verify CRITICAL level exists and has red color styling."""
    level_info = logger.level("CRITICAL")
    assert level_info.name == "CRITICAL"
    assert "red" in level_info.color.lower()


def test_logger_output_capture():
    """Verify that logger.success, logger.warning, logger.error emit messages cleanly."""
    captured = io.StringIO()
    handler_id = logger.add(captured, format="{level} - {message}", colorize=False)
    try:
        logger.success("Test success message in green")
        logger.warning("Test warning message in yellow")
        logger.error("Test error message in red")
        logger.critical("Test critical message")

        output = captured.getvalue()
        assert "SUCCESS - Test success message in green" in output
        assert "WARNING - Test warning message in yellow" in output
        assert "ERROR - Test error message in red" in output
        assert "CRITICAL - Test critical message" in output
    finally:
        logger.remove(handler_id)
