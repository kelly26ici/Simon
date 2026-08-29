"""Tests for normalise_audio() error handling and sanitization."""

import pytest
from src.messages.audios.normaliser import _sanitise_ffmpeg_stderr


def test_sanitise_ffmpeg_stderr():
    sample_stderr = "Stream #0:0\nOutput #0\nError opening filters\nConversion failed!"
    result = _sanitise_ffmpeg_stderr(sample_stderr)
    assert "Conversion failed!" in result
