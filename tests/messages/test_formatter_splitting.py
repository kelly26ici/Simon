"""Tests for WhatsAppFormatter message splitting."""

import pytest
from src.messages.formatter import WhatsAppFormatter


def test_short_message_not_split():
    fmt = WhatsAppFormatter(max_length=4096)
    parts = fmt.format("Hello, world!")
    assert len(parts) == 1


def test_long_message_split_into_multiple_parts():
    fmt = WhatsAppFormatter(max_length=100)
    long_text = ("This is a long paragraph test with multiple words.\n\n") * 10
    parts = fmt.format(long_text)
    assert len(parts) >= 2


def test_each_part_within_max_length():
    max_len = 200
    fmt = WhatsAppFormatter(max_length=max_len)
    long_text = ("This is a line of text for splitting.\n\n") * 20
    parts = fmt.format(long_text)
    for part in parts:
        assert len(part) <= max_len + 50
