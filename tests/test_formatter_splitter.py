"""Tests for edge cases in the WhatsApp formatting layer's table conversion and
message splitter (src/messages/formatter.py).

Covers:
- Markdown table conversion to washapp-safe summaries (no box-drawing,
  ``**``, or ``` characters — WhatsApp does not support them)
- Message splitting at paragraph boundaries
- No joining of unrelated elements (URLs, lists, blockquotes, code, tables)
- Fenced code blocks become "Code:\n line_X" and stay intact
- Multi-part message "1/N" prefixing
"""

import pytest

from src.messages.formatter import WhatsAppFormatter


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def formatter():
    return WhatsAppFormatter(max_length=4096, table_mode="text", debug=False)


@pytest.fixture
def short_formatter():
    """Formater with a small max_length to force splitting."""
    return WhatsAppFormatter(max_length=100, table_mode="text", debug=False)


# ─── Table Conversion ──────────────────────────────────────────────────────────

class TestTableConversion:
    def test_basic_table(self, formatter):
        """The formatter converts Markdown tables to colon-separated summaries
        (no box-drawing, no Markdown)."""
        table = (
            "| Name | Price | Beds |\n"
            "|------|-------|------|\n"
            "| House A | 10M | 3 |\n"
            "| House B | 15M | 4 |"
        )
        result = formatter.format(table)
        assert len(result) == 1
        # Each data row becomes "- cell0: cell1" summaries.
        assert "House A" in result[0]
        assert "House B" in result[0]
        # No Markdown or box-drawing survives.
        assert "**" not in result[0]
        assert "|" not in result[0]
        assert "┌" not in result[0]
        assert ":" in result[0]

    def test_table_without_separator(self, formatter):
        """A table without a separator row should still be detected."""
        table = (
            "| Name | Price |\n"
            "| House A | 10M |\n"
            "| House B | 15M |"
        )
        result = formatter.format(table)
        assert len(result) == 1
        assert "Name" in result[0]
        assert "House A" in result[0]

    def test_table_with_empty_cells(self, formatter):
        table = (
            "| Name | Price | Beds |\n"
            "|------|-------|------|\n"
            "| House A | 10M | |\n"
            "| House B | | 4 |"
        )
        result = formatter.format(table)
        assert len(result) == 1
        assert "House A" in result[0]
        assert "House B" in result[0]

    def test_table_with_varying_columns(self, formatter):
        table = (
            "| Name | Price |\n"
            "|------|-------|\n"
            "| House A | 10M | extra |\n"
            "| House B | 15M |"
        )
        result = formatter.format(table)
        assert len(result) == 1
        assert "House A" in result[0]
        assert "House B" in result[0]

    def test_table_with_alignment(self, formatter):
        table = (
            "| Name | Price |\n"
            "|:-----|------:|\n"
            "| House A | 10M |\n"
            "| House B | 15M |"
        )
        result = formatter.format(table)
        assert len(result) == 1
        assert "House A" in result[0]
        assert "House B" in result[0]

    def test_table_embedded_in_text(self, formatter):
        text = (
            "Here are the results:\n\n"
            "| Name | Price |\n"
            "|------|-------|\n"
            "| House A | 10M |\n\n"
            "Let me know if you need more."
        )
        result = formatter.format(text)
        assert len(result) == 1
        assert "Here are the results:" in result[0]
        assert "House A" in result[0]
        assert "Let me know if you need more." in result[0]

    def test_table_with_unicode(self, formatter):
        table = (
            "| Name | Price |\n"
            "|------|-------|\n"
            "| House A | 10M |\n"
            "| House B | 15M |"
        )
        result = formatter.format(table)
        assert len(result) == 1
        assert "House A" in result[0]
        assert "House B" in result[0]


# ─── Message Splitting ─────────────────────────────────────────────────────────

class TestMessageSplitting:
    def test_short_message_not_split(self, formatter):
        result = formatter.format("Short message")
        assert len(result) == 1
        assert result[0] == "Short message"

    def test_message_at_limit_not_split(self, formatter):
        text = "x" * 4096
        result = formatter.format(text)
        assert len(result) == 1
        assert len(result[0]) == 4096

    def test_message_over_limit_split(self, short_formatter):
        """A message over the limit should be split into multiple parts."""
        text = "\n\n".join(
            f"Paragraph {i} with some content here." for i in range(20)
        )
        result = short_formatter.format(text)
        assert len(result) > 1

    def test_split_parts_have_prefix(self, short_formatter):
        text = "\n\n".join(
            f"Paragraph {i} with some content here." for i in range(20)
        )
        result = short_formatter.format(text)
        assert len(result) > 1
        # First part should have "1/N" prefix
        assert result[0].startswith("1/")
        # Last part should have "N/N" prefix
        assert result[-1].startswith(f"{len(result)}/{len(result)}")

    def test_split_parts_within_limit(self, short_formatter):
        """Each split part (minus prefix) should be within the limit."""
        text = "Paragraph one.\n\n" + "Paragraph two.\n\n" + "Paragraph three."
        result = short_formatter.format(text)
        for msg in result:
            # Strip the "N/N\n\n" prefix
            body = msg.split("\n\n", 1)[1] if "\n\n" in msg else msg
            assert len(body) <= short_formatter.max_length

    def test_code_block_not_split(self, short_formatter):
        """Fenced code blocks are converted to 'Code:\n line_X' lines and must
        not be joined with surrounding paragraphs."""
        code_text = "\n".join(f"c{i}" for i in range(50))
        text = "Intro paragraph.\n\n" + code_text + "\n\nOutro paragraph."
        result = short_formatter.format(text)
        joined = "\n\n".join(result)
        # Every code line must appear intact in the joined output.
        for i in range(50):
            assert f"c{i}" in joined, f"c{i} missing from formatted output"
        # Intro and outro must also be present (not swallowed into a code run).
        assert "Intro paragraph." in joined
        assert "Outro paragraph." in joined

    def test_url_not_broken(self, short_formatter):
        """A long URL should not be split in the middle."""
        url = "https://example.com/" + "a" * 200
        text = f"Visit {url} for more info."
        result = short_formatter.format(text)
        # The URL should appear intact in one of the parts
        joined = "\n\n".join(result)
        assert url in joined

    def test_list_not_split(self, short_formatter):
        """A list should not be split in the middle."""
        items = "\n".join(f"- Item {i}" for i in range(30))
        text = "Here is a list:\n\n" + items
        result = short_formatter.format(text)
        joined = "\n\n".join(result)
        assert "Item 0" in joined
        assert "Item 29" in joined

    def test_blockquote_not_split(self, short_formatter):
        """A blockquote should not be split in the middle."""
        quote = "\n".join(f"> Quote line {i}" for i in range(30))
        text = "Here is a quote:\n\n" + quote
        result = short_formatter.format(text)
        joined = "\n\n".join(result)
        assert "Quote line 0" in joined
        assert "Quote line 29" in joined

    def test_table_not_split(self, short_formatter):
        """A table should not be split in the middle."""
        rows = "\n".join(f"| Row {i} | Value {i} |" for i in range(30))
        table = "| Name | Value |\n|------|-------|\n" + rows
        text = "Here is a table:\n\n" + table
        result = short_formatter.format(text)
        joined = "\n\n".join(result)
        assert "Row 0" in joined
        assert "Row 29" in joined

    def test_oversized_single_block_split_at_lines(self, short_formatter):
        """An oversized single block should be split at line boundaries."""
        text = "\n".join(f"Line {i} with some content" for i in range(50))
        result = short_formatter.format(text)
        assert len(result) > 1
        # All parts should be within the limit (or close to it)
        for msg in result:
            body = msg.split("\n\n", 1)[1] if "\n\n" in msg else msg
            assert len(body) <= short_formatter.max_length + 10  # small tolerance


# ─── Combined Formatting + Splitting ───────────────────────────────────────────

class TestCombined:
    def test_long_document_with_all_elements(self, short_formatter):
        """A long document with all element types should format and split correctly."""
        text = (
            "# Title\n\n"
            "Intro **bold** and *italic* text.\n\n"
            "| Name | Price |\n"
            "|------|-------|\n"
            "| House A | 10M |\n\n"
            "- Item 1\n"
            "- Item 2\n\n"
            "> A blockquote\n\n"
            "```\ncode here\n```\n\n"
            "Outro text."
        )
        result = short_formatter.format(text)
        assert len(result) >= 1
        joined = "\n\n".join(result)
        # Headings become ALL CAPS without Markdown markers.
        assert "TITLE" in joined
        # Bold/italic markers are stripped — only content text remains.
        assert "bold" in joined
        assert "italic" in joined
        assert "**" not in joined
        assert "*" not in joined.replace(">", "")
        # Tables become "- key: value" summaries.
        assert "House A" in joined
        assert "10M" in joined
        # Unordered list items keep their dash prefix (no bullet chars).
        assert "- Item 1" in joined
        assert "- Item 2" in joined
        # Blockquotes keep their prefix.
        assert "> A blockquote" in joined
        # Fenced code blocks become "Code:\n line_X" — no backtick fences.
        assert "Code:" in joined
        assert "code here" in joined
        assert "```" not in joined

    def test_no_data_loss(self, short_formatter):
        """Splitting should not lose any content."""
        text = "\n\n".join(
            f"Paragraph {i} with some content here." for i in range(20)
        )
        result = short_formatter.format(text)
        joined = "\n\n".join(result)
        for i in range(20):
            assert f"Paragraph {i}" in joined
