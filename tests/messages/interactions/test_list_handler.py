"""Tests for src/messages/interactions/list_handler.py."""

import importlib


def test_list_handler_module_importable():
    import src.messages.interactions.list_handler as mod
    importlib.reload(mod)
    assert mod is not None
