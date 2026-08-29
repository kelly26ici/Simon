"""Tests for transcriber lazy-import & missing key behavior."""

import pytest
from pathlib import Path
from unittest.mock import patch
from src.messages.audios.transcriber import transcribe_audio


@pytest.mark.asyncio
async def test_transcribe_audio_missing_file_returns_none(tmp_path):
    missing_file = tmp_path / "nonexistent.wav"
    result = await transcribe_audio(missing_file)
    assert result is None


@pytest.mark.asyncio
async def test_transcribe_audio_empty_file_returns_none(tmp_path):
    empty_file = tmp_path / "empty.wav"
    empty_file.touch()
    result = await transcribe_audio(empty_file)
    assert result is None
