"""Tests for AudioError enum in src/messages/audios/audio_handler.py."""

import pytest
from src.messages.audios.audio_handler import AudioError


def test_audio_error_is_enum():
    from enum import Enum
    assert issubclass(AudioError, Enum)


def test_no_raw_message_member_exists():
    assert hasattr(AudioError, "NO_RAW_MESSAGE")


def test_no_audio_object_member_exists():
    assert hasattr(AudioError, "NO_AUDIO_OBJECT")


def test_missing_media_id_member_exists():
    assert hasattr(AudioError, "MISSING_MEDIA_ID")


def test_all_error_values_are_strings():
    for member in AudioError:
        assert isinstance(member.value, str)
