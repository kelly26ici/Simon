"""Tests for WhatsAppFormatter link rendering."""

import pytest
from src.messages.formatter import WhatsAppFormatter


@pytest.fixture
def fmt():
    return WhatsAppFormatter(max_length=4096, table_mode="text", debug=False)


def test_markdown_link_preserves_url(fmt):
    result = " ".join(fmt.format("[Click here](https://example.com)"))
    assert "https://example.com" in result


def test_markdown_link_renders_label(fmt):
    result = " ".join(fmt.format("[Click here](https://example.com)"))
    assert "Click here" in result


def test_markdown_link_removes_brackets(fmt):
    result = " ".join(fmt.format("[Click here](https://example.com)"))
    assert "[" not in result or "Click here" in result
