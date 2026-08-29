"""Tests for _extract_retry_after() in src/messages/chats/text_handler.py."""

from src.messages.chats.text_handler import _extract_retry_after


def test_extract_retry_after_pattern_seconds():
    exc = Exception("Rate limit reached. Please retry after 45 seconds.")
    result = _extract_retry_after(exc)
    assert result == "45 seconds"


def test_extract_retry_after_pattern_minutes():
    exc = Exception("try again in 120s")
    result = _extract_retry_after(exc)
    assert "minute" in result


def test_extract_retry_after_none_when_unmatched():
    exc = Exception("Something went wrong completely")
    result = _extract_retry_after(exc)
    assert result is None
