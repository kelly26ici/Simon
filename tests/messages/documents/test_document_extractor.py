"""Tests for src/messages/documents/extractor.py."""

import importlib


def test_document_extractor_module_importable():
    import src.messages.documents.extractor as mod
    importlib.reload(mod)
    assert mod is not None
