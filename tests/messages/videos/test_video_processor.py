"""Tests for src/messages/videos/video_processor.py."""

import importlib


def test_video_processor_module_importable():
    import src.messages.videos.video_processor as mod
    importlib.reload(mod)
    assert mod is not None
