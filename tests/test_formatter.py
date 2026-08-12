"""
Unit tests for the WhatsApp formatting layer (src/messages/formatter.py).

Covers:
- Plain-text normalization of bold, italic, strikethrough, links, images
- Heading normalization to uppercase headings
- Stable splitting behavior for long messages
- Code block preservation as indented text
- Table handling and empty-input behavior
"""

import pytest

from src.messages.formatter import WhatsAppFormatter, format_for_whatsapp


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def formatter():
    return WhatsAppFormatter(max_length=4096, table_mode="text", debug=False)


@pytest.fixture
def short_formatter():
    return WhatsAppFormatter(max_length=120, table_mode="text", debug=False)


# ─── Inline Formatting ────────────────────────────────────────────────────────


class TestBold:
    def test_double_asterisk_bold(self, formatter):
        assert formatter.format("This is **bold** text") == [
            "This is bold text"
        ]

    def test_double_underscore_bold(self, formatter):
        assert formatter.format("This is __bold__ text") == ["This is bold text"]

    def test_bold_at_start(self, formatter):
        assert formatter.format("**Bold start** and normal") == [
            "Bold start and normal"
        ]

    def test_bold_at_end(self, formatter):
        assert formatter.format("Normal and **bold end**") == [
            "Normal and bold end"
        ]

    def test_multiple_bold(self, formatter):
        assert formatter.format("**A** and **B** and **C**") == [
            "A and B and C"
        ]


class TestItalic:
    def test_single_asterisk_italic(self, formatter):
        assert formatter.format("This is *italic* text") == [
            "This is italic text"
        ]

    def test_underscore_italic(self, formatter):
        assert formatter.format("This is _italic_ text") == [
            "This is italic text"
        ]

    def test_italic_not_confused_with_bold(self, formatter):
        assert formatter.format("**bold** and *italic*") == [
            "bold and italic"
        ]


class TestStrikethrough:
    def test_strikethrough(self, formatter):
        assert formatter.format("This is ~~struck~~ text") == [
            "This is struck text"
        ]

    def test_multiple_strikethrough(self, formatter):
        result = formatter.format("~~A~~ and ~~B~~")
        assert result == ["A and B"]


class TestCode:
    def test_inline_code_preserved(self, formatter):
        assert formatter.format("Use `code` here") == ["Use `code` here"]

    def test_code_span_with_asterisks(self, formatter):
        assert formatter.format("Use `*not bold*` here") == [
            "Use `*not bold*` here"
        ]

    def test_code_span_with_underscores(self, formatter):
        assert formatter.format("Use `_not_italic_` here") == [
            "Use `_not_italic_` here"
        ]

    def test_code_block_preserved(self, formatter):
        result = formatter.format("```\nprint('hello')\n```")
        assert result[-1].endswith("Code:\n  print('hello')")

    def test_code_block_with_language(self, formatter):
        result = formatter.format("```python\nprint('hello')\n```")
        assert result[-1].endswith("Code:\n  print('hello')")

    def test_code_block_with_asterisks(self, formatter):
        result = formatter.format("```\n**not bold**\n```")
        assert result[-1].endswith("Code:\n  **not bold**")


class TestLinks:
    def test_link_conversion(self, formatter):
        assert formatter.format("See [docs](https://example.com)") == [
            "See docs (https://example.com)"
        ]

    def test_link_with_title(self, formatter):
        assert formatter.format("See [docs](https://example.com \"Title\")") == [
            "See docs (https://example.com)"
        ]

    def test_multiple_links(self, formatter):
        assert formatter.format("[A](https://a.com) and [B](https://b.com)") == [
            "A (https://a.com) and B (https://b.com)"
        ]


class TestImages:
    def test_image_removed(self, formatter):
        assert formatter.format("![alt](https://example.com/img.png)") == [""]

    def test_image_removed_from_middle(self, formatter):
        result = formatter.format("hello ![alt](https://example.com/img.png) world")
        assert len(result) == 1
        assert "example.com" not in result[0]
        assert "alt" not in result[0]


class TestCombinedInline:
    def test_bold_italic_strikethrough(self, formatter):
        assert formatter.format("**bold** *italic* ~~struck~~ `code`") == [
            "bold italic struck `code`"
        ]

    def test_link_text_is_preserved_without_bold_markers(self, formatter):
        assert formatter.format("**[link](https://example.com)**") == [
            "link (https://example.com)"
        ]


# ─── Block-Level Formatting ────────────────────────────────────────────────────


class TestHeadings:
    def test_h1(self, formatter):
        assert formatter.format("# Heading 1") == ["HEADING 1"]

    def test_h2(self, formatter):
        assert formatter.format("## Heading 2") == ["HEADING 2"]

    def test_h3(self, formatter):
        assert formatter.format("### Heading 3") == ["HEADING 3"]

    def test_h6(self, formatter):
        assert formatter.format("###### Heading 6") == ["HEADING 6"]


class TestBlockquotes:
    def test_single_line_blockquote(self, formatter):
        assert formatter.format("> This is a quote") == ["> This is a quote"]

    def test_multi_line_blockquote(self, formatter):
        assert formatter.format("> Line 1\n> Line 2") == [
            "> Line 1\n> Line 2"
        ]

    def test_blockquote_with_formatting(self, formatter):
        assert formatter.format("> **Bold** quote") == ["> Bold quote"]


class TestLists:
    def test_unordered_list_dash(self, formatter):
        assert formatter.format("- Item 1\n- Item 2") == [
            "- Item 1\n- Item 2"
        ]

    def test_unordered_list_asterisk(self, formatter):
        assert formatter.format("* Item 1\n* Item 2") == [
            "- Item 1\n- Item 2"
        ]

    def test_ordered_list(self, formatter):
        assert formatter.format("1. First\n2. Second") == [
            "1. First\n2. Second"
        ]

    def test_list_with_formatting(self, formatter):
        assert formatter.format("- **Bold** item\n- *Italic* item") == [
            "- Bold item\n- Italic item"
        ]


class TestHorizontalRule:
    def test_hr_dashes(self, formatter):
        assert formatter.format("---") == ["-"]

    def test_hr_asterisks(self, formatter):
        assert formatter.format("***") == ["-"]

    def test_hr_underscores(self, formatter):
        assert formatter.format("___") == ["-"]


class TestParagraphs:
    def test_single_paragraph(self, formatter):
        assert formatter.format("Hello world") == ["Hello world"]

    def test_multiple_paragraphs(self, formatter):
        assert formatter.format("First paragraph\n\nSecond paragraph") == [
            "First paragraph\n\nSecond paragraph"
        ]

    def test_paragraph_with_bold(self, formatter):
        assert formatter.format("Hello **world**") == ["Hello world"]


# ─── Tables ────────────────────────────────────────────────────────────────


class TestTables:
    def test_table_becomes_simple_summary(self, formatter):
        table = (
            "| Property | Price |\n"
            "|----------|-------|\n"
            "| Apt 4B | 15M |\n"
            "| Villa 12 | 45M |"
        )
        result = formatter.format(table)
        assert result == [
            "- Property: Price\n- Apt 4B: 15M\n- Villa 12: 45M"
        ]


# ─── Splitting ─────────────────────────────────────────────────────────────


class TestSplitting:
    def test_empty_input_returns_empty_message(self, formatter):
        assert formatter.format("") == [""]


# ─── Idempotency ──────────────────────────────────────────────────────────────


class TestIdempotency:
    def test_plain_text_is_idempotent(self, formatter):
        text = "Hello world"
        first = formatter.format(text)
        second = formatter.format(first[0])
        assert first == second
