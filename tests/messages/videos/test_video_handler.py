"""Tests for src/messages/videos/video_handler.py."""

import importlib


def test_video_handler_module_importable():
    import src.messages.videos.video_handler as mod
    importlib.reload(mod)
    assert mod is not None
