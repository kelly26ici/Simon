"""Tests for src/messages/audios/tts.py."""

import importlib


def test_tts_module_importable():
    import src.messages.audios.tts as tts
    importlib.reload(tts)
    assert tts is not None
