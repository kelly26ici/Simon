"""Tests for MediaError enum in src/messages/downloader.py."""

from src.messages.downloader import (
    MediaError,
    INVALID_MEDIA_ID,
    AUTH_FAILED,
    RATE_LIMITED,
    DOWNLOAD_FAILED,
    TRANSPORT_ERROR,
    EMPTY_BODY,
)


def test_media_error_is_enum():
    from enum import Enum
    assert issubclass(MediaError, Enum)


def test_all_aliases_are_media_error_members():
    assert INVALID_MEDIA_ID == MediaError.INVALID_MEDIA_ID
    assert AUTH_FAILED == MediaError.AUTH_FAILED
    assert RATE_LIMITED == MediaError.RATE_LIMITED
    assert DOWNLOAD_FAILED == MediaError.DOWNLOAD_FAILED
    assert TRANSPORT_ERROR == MediaError.TRANSPORT_ERROR
    assert EMPTY_BODY == MediaError.EMPTY_BODY


def test_media_error_values_are_strings():
    for member in MediaError:
        assert isinstance(member.value, str)


def test_invalid_media_id_value():
    assert MediaError.INVALID_MEDIA_ID.value == "invalid_media_id"


def test_auth_failed_value():
    assert MediaError.AUTH_FAILED.value == "auth_failed"
