"""Tests for src/messages/images/image_processor.py."""

import importlib


def test_image_processor_module_importable():
    import src.messages.images.image_processor as mod
    importlib.reload(mod)
    assert mod is not None
