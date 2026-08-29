"""Tests for secret sanitization in src/tools/registry.py."""

from src.tools.registry import _sanitize


def test_sanitize_api_key():
    text = "Error: api_key='sk-abcdef1234567890abcdef' is invalid"
    clean = _sanitize(text)
    assert "sk-abcdef" not in clean
    assert "[REDACTED]" in clean


def test_sanitize_token():
    text = "Received token: ghp_123456789012345678901234567890"
    clean = _sanitize(text)
    assert "ghp_" not in clean
    assert "[REDACTED]" in clean


def test_sanitize_clean_text_unchanged():
    text = "Looking for 3 bedroom house in Nairobi"
    clean = _sanitize(text)
    assert clean == text
