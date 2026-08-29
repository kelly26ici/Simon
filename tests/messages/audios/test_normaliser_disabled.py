"""Tests for normalise_audio when NORMALISER_DISABLED=true."""

import os
from unittest.mock import patch
from src.messages.audios.normaliser import normalise_audio


def test_normaliser_disabled_returns_raw_bytes():
    raw_audio = b"fake audio bytes"
    with patch.dict(os.environ, {"NORMALISER_DISABLED": "true"}):
        result = normalise_audio(raw_audio, source_mime="audio/ogg")
    assert result == raw_audio
