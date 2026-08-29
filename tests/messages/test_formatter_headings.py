"""Tests for WhatsAppFormatter heading rendering."""

import pytest
from src.messages.formatter import WhatsAppFormatter


@pytest.fixture
def fmt():
    return WhatsAppFormatter(max_length=4096, table_mode="text", debug=False)


def test_h1_becomes_uppercase(fmt):
    result = " ".join(fmt.format("# Title Here"))
    assert "TITLE HERE" in result


def test_h2_becomes_uppercase(fmt):
    result = " ".join(fmt.format("## Section"))
    assert "SECTION" in result


def test_h3_becomes_uppercase(fmt):
    result = " ".join(fmt.format("### Sub"))
    assert "SUB" in result


def test_heading_removes_hash_symbols(fmt):
    result = " ".join(fmt.format("# Hello"))
    assert "#" not in result
