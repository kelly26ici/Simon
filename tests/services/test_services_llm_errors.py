"""Tests for custom LLM exception classes in src/services/llm.py."""

from src.services.llm import (
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMAuthenticationError,
    LLMError,
)


def test_llm_rate_limit_error_is_exception():
    assert issubclass(LLMRateLimitError, Exception)


def test_llm_service_unavailable_error_is_exception():
    assert issubclass(LLMServiceUnavailableError, Exception)


def test_llm_auth_error_is_exception():
    assert issubclass(LLMAuthenticationError, Exception)


def test_llm_error_is_exception():
    assert issubclass(LLMError, Exception)
