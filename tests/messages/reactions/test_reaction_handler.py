"""Tests for src/messages/reactions/reaction_handler.py."""

import importlib


def test_reaction_handler_module_importable():
    import src.messages.reactions.reaction_handler as mod
    importlib.reload(mod)
    assert mod is not None
