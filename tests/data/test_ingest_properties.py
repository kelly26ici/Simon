"""Tests for ingest properties functions in src/data/ingest_properties.py."""

import importlib
from src.data import ingest_properties


def test_ingest_properties_module_importable():
    importlib.reload(ingest_properties)
    assert ingest_properties is not None
