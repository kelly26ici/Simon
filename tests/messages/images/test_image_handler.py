"""Tests for src/messages/images/image_handler.py."""

import importlib


def test_image_handler_module_importable():
    import src.messages.images.image_handler as mod
    importlib.reload(mod)
    assert mod is not None
