"""Tests for WhatsAppFormatter bold/italic stripping."""

import pytest
from src.messages.formatter import WhatsAppFormatter


@pytest.fixture
def fmt():
    return WhatsAppFormatter(max_length=4096, table_mode="text", debug=False)


def test_bold_double_asterisk_stripped(fmt):
    result = " ".join(fmt.format("**bold text**"))
    assert "**" not in result
    assert "bold text" in result


def test_bold_double_underscore_stripped(fmt):
    result = " ".join(fmt.format("__bold text__"))
    assert "__" not in result
    assert "bold text" in result


def test_plain_text_passthrough(fmt):
    text = "Hello, this is plain text."
    result = " ".join(fmt.format(text))
    assert "Hello" in result
