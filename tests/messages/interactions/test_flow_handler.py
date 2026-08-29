"""Tests for src/messages/interactions/flow_handler.py."""

import importlib


def test_flow_handler_module_importable():
    import src.messages.interactions.flow_handler as mod
    importlib.reload(mod)
    assert mod is not None
