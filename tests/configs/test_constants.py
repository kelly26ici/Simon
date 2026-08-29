"""Tests for src/configs/constants.py."""

from src.configs.constants import (
    GROQ_MODEL,
    GROQ_FALLBACK_MODEL,
    OPENROUTER_MODEL,
    NVIDIA_MODEL,
    GEMINI_MODEL,
)


def test_groq_model_is_string():
    assert isinstance(GROQ_MODEL, str) and len(GROQ_MODEL) > 0


def test_groq_fallback_model_is_string():
    assert isinstance(GROQ_FALLBACK_MODEL, str) and len(GROQ_FALLBACK_MODEL) > 0


def test_openrouter_model_is_string():
    assert isinstance(OPENROUTER_MODEL, str) and len(OPENROUTER_MODEL) > 0


def test_nvidia_model_is_string():
    assert isinstance(NVIDIA_MODEL, str) and len(NVIDIA_MODEL) > 0


def test_gemini_model_is_string():
    assert isinstance(GEMINI_MODEL, str) and len(GEMINI_MODEL) > 0


def test_groq_model_has_no_surrounding_whitespace():
    assert GROQ_MODEL == GROQ_MODEL.strip()


def test_nvidia_model_no_provider_prefix():
    """NVIDIA model ID must NOT carry the nvidia_nim/ routing prefix."""
    assert not NVIDIA_MODEL.startswith("nvidia_nim/")
