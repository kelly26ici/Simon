"""Tests for src/messages/interactions/button_handler.py."""

import importlib


def test_button_handler_module_importable():
    import src.messages.interactions.button_handler as mod
    importlib.reload(mod)
    assert mod is not None
