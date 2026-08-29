"""Tests for src/core/logging_config.py."""

import sys
from unittest.mock import patch, MagicMock
from src.core.logging_config import configure_logging, CONSOLE_LOG_FORMAT, FILE_LOG_FORMAT


def test_console_log_format_is_string():
    assert isinstance(CONSOLE_LOG_FORMAT, str)
    assert "{time" in CONSOLE_LOG_FORMAT
    assert "{message}" in CONSOLE_LOG_FORMAT


def test_file_log_format_is_string():
    assert isinstance(FILE_LOG_FORMAT, str)
    assert "{time" in FILE_LOG_FORMAT
    assert "{message}" in FILE_LOG_FORMAT


def test_configure_logging_accepts_level():
    """configure_logging should accept any string log level without raising."""
    configure_logging(level="DEBUG", log_file=None)


def test_configure_logging_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging(log_file=None)  # should not raise


def test_configure_logging_no_file():
    """Passing log_file=None should skip file sink creation."""
    configure_logging(level="WARNING", log_file=None)


def test_configure_logging_with_file(tmp_path):
    log_path = str(tmp_path / "test.log")
    configure_logging(level="INFO", log_file=log_path)
