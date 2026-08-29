"""Tests for src/messages/documents/document_handler.py."""

import importlib


def test_document_handler_module_importable():
    import src.messages.documents.document_handler as mod
    importlib.reload(mod)
    assert mod is not None
