"""
WhatsApp Formatting Layer

Plain-text formatter for WhatsApp Cloud API text messages.

WhatsApp text messages do not reliably support Markdown-based formatting
in the way the previous formatter assumed. To avoid broken rendering this
module converts LLM Markdown into safe, readable plain text:

- Headings become ALL CAPS lines.
- Bold and italic markers are stripped; supported markup is removed
  instead of being converted into WhatsApp-specific delimiters.
- Tables become simple colon-separated property summaries.
- Lists become simple bullet lists.
- Code blocks become indented text blocks with a "Code:" prefix.
- Long messages are split at paragraph boundaries with "1/N" prefixes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from loguru import logger

from src.configs.settings import (
    WHATSAPP_MAX_MESSAGE_LENGTH,
    WHATSAPP_TABLE_MODE,
    WHATSAPP_FORMAT_DEBUG,
)


# ─── Block Types ──────────────────────────────────────────────────────────────


@dataclass
class FormatBlock:
    """A parsed block of content from the LLM response."""

    type: str  # paragraph, code_block, table, list, blockquote, heading, hr
    content: str
    raw: str = ""


# ─── WhatsApp Formatter ───────────────────────────────────────────────────────


class WhatsAppFormatter:
    """Converts Markdown text from the LLM into WhatsApp-safe plain text.

    This is the single choke-point for all outgoing WhatsApp messages.
    Every message sent via ``send_whatsapp_message()`` passes through here.
    """

    _CODE_SPAN_RE = re.compile(r"(?<!`)`([^`]+)`(?!`)")
    _BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
    _STRIKETHROUGH_RE = re.compile(r"~~(.+?)~~")
    _ITALIC_ASTERISK_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
    _ITALIC_UNDERSCORE_RE = re.compile(r"(?<!_)_([^_]+)_(?!_)")
    _LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    _IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
    _HR_RE = re.compile(r"^(-{3}|\*{3}|_{3})\s*$")
    _UNORDERED_LIST_RE = re.compile(r"^[-*]\s+")
    _ORDERED_LIST_RE = re.compile(r"^\d+\.\s+")

    def __init__(
        self,
        max_length: Optional[int] = None,
        table_mode: Optional[str] = None,
        debug: Optional[bool] = None,
    ) -> None:
        self.max_length = (
            max_length if max_length is not None else WHATSAPP_MAX_MESSAGE_LENGTH
        )
        self.table_mode = (
            table_mode if table_mode is not None else WHATSAPP_TABLE_MODE
        )
        self.debug = (
            debug
            if debug is not None
            else WHATSAPP_FORMAT_DEBUG
        )

    def format(self, text: str) -> List[str]:
        """Convert text into one or more WhatsApp-safe message chunks."""
        if not text or not text.strip():
            return [""]

        if self.debug:
            logger.debug("Formatting text ({} chars)", len(text))

        blocks = self._parse_blocks(text)
        formatted_blocks: List[str] = []

        for block in blocks:
            formatted = self._format_block(block)
            if formatted:
                formatted_blocks.append(formatted)

        messages = self._join_and_split(formatted_blocks)

        if self.debug:
            logger.debug("Produced {} message(s)", len(messages))

        return messages

    # ─── Block Parsing ────────────────────────────────────────────────────────

    def _parse_blocks(self, text: str) -> List[FormatBlock]:
        """Parse text into semantic blocks."""
        lines = text.split("\n")
        blocks: List[FormatBlock] = []
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                code_lines: List[str] = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing ```
                content = "\n".join(code_lines)
                blocks.append(
                    FormatBlock(
                        type="code_block",
                        content=content,
                        raw=f"```{lang}\n{content}\n```",
                    )
                )
                continue

            if stripped.startswith("|") and i + 1 < len(lines) and self._is_table_separator(
                lines[i + 1]
            ):
                table_lines = [line]
                i += 1
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                blocks.append(
                    FormatBlock(
                        type="table",
                        content="\n".join(table_lines),
                        raw="\n".join(table_lines),
                    )
                )
                continue

            heading_match = self._HEADING_RE.match(stripped)
            if heading_match:
                content = heading_match.group(2)
                blocks.append(
                    FormatBlock(
                        type="heading",
                        content=content,
                        raw=line,
                    )
                )
                i += 1
                continue

            if stripped.startswith(">"):
                quote_lines: List[str] = []
                while i < len(lines) and lines[i].strip().startswith(">"):
                    quote_lines.append(lines[i].strip()[1:].strip())
                    i += 1
                blocks.append(
                    FormatBlock(
                        type="blockquote",
                        content="\n".join(quote_lines),
                        raw="\n".join(quote_lines),
                    )
                )
                continue

            if (
                self._UNORDERED_LIST_RE.match(stripped)
                or self._ORDERED_LIST_RE.match(stripped)
            ):
                list_lines: List[str] = []
                while i < len(lines):
                    s = lines[i].strip()
                    if (
                        self._UNORDERED_LIST_RE.match(s)
                        or self._ORDERED_LIST_RE.match(s)
                    ):
                        list_lines.append(lines[i])
                        i += 1
                    else:
                        break
                blocks.append(
                    FormatBlock(
                        type="list",
                        content="\n".join(list_lines),
                        raw="\n".join(list_lines),
                    )
                )
                continue

            if self._HR_RE.match(stripped):
                blocks.append(
                    FormatBlock(
                        type="hr",
                        content="-",
                        raw=line,
                    )
                )
                i += 1
                continue

            # Paragraph
            para_lines: List[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if not s:
                    break
                if self._is_block_start(s):
                    break
                para_lines.append(lines[i])
                i += 1

            if para_lines:
                blocks.append(
                    FormatBlock(
                        type="paragraph",
                        content="\n".join(para_lines),
                        raw="\n".join(para_lines),
                    )
                )

        return blocks

    def _is_table_separator(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped.startswith("|"):
            return False
        cells = stripped.strip("|").split("|")
        return all(re.match(r"^[-:]+$", c.strip()) for c in cells if c.strip())

    def _is_block_start(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        if stripped.startswith("```"):
            return True
        if stripped.startswith("|") and self._is_table_separator(line):
            return True
        if self._HEADING_RE.match(stripped):
            return True
        if stripped.startswith(">"):
            return True
        if (
            self._UNORDERED_LIST_RE.match(stripped)
            or self._ORDERED_LIST_RE.match(stripped)
        ):
            return True
        if self._HR_RE.match(stripped):
            return True
        return False

    # ─── Block Formatting ─────────────────────────────────────────────────────

    def _format_block(self, block: FormatBlock) -> str:
        if block.type == "code_block":
            return self._format_code_block(block.content)
        if block.type == "table":
            return self._convert_table(block.content)
        if block.type == "heading":
            return self._format_heading(block.content)
        if block.type == "blockquote":
            return self._format_blockquote(block.content)
        if block.type == "list":
            return self._format_list(block.content)
        if block.type == "hr":
            return "-"
        return self._format_inline(block.content)

    def _format_heading(self, content: str) -> str:
        cleaned = self._format_inline(content)
        if not cleaned:
            return ""
        return cleaned.upper()

    def _format_inline(self, text: str) -> str:
        # 1. Protect code spans
        code_spans: List[str] = []

        def _save_code_span(match: re.Match) -> str:
            code_spans.append(match.group(0))
            return f"\x00CODE{len(code_spans) - 1}\x00"

        text = self._CODE_SPAN_RE.sub(_save_code_span, text)

        # 2. Remove images before links
        text = self._IMAGE_RE.sub("", text)

        # 3. Convert links to plain text URLs
        text = self._LINK_RE.sub(
            lambda m: f"{m.group(1)} ({m.group(2)})",
            text,
        )

        def _clean_markup(m: re.Match) -> str:
            content = m.group(1) or m.group(2) or ""
            return content.strip("_*~")

        # 4. Remove unsupported bold markers
        text = self._BOLD_RE.sub(_clean_markup, text)

        # 5. Remove unsupported italic markers
        text = self._ITALIC_ASTERISK_RE.sub(_clean_markup, text)
        text = self._ITALIC_UNDERSCORE_RE.sub(_clean_markup, text)

        # 6. Remove unsupported strikethrough markers
        text = self._STRIKETHROUGH_RE.sub(lambda m: m.group(1), text)

        # 7. Restore code spans
        for index, span in enumerate(code_spans):
            text = text.replace(f"\x00CODE{index}\x00", span)

        return text

    def _format_blockquote(self, content: str) -> str:
        lines = content.split("\n")
        formatted = []
        for line in lines:
            formatted.append(f"> {self._format_inline(line)}")
        return "\n".join(formatted)

    def _format_list(self, content: str) -> str:
        lines = content.split("\n")
        formatted = []
        for line in lines:
            stripped = line.strip()
            if self._UNORDERED_LIST_RE.match(stripped):
                text = self._UNORDERED_LIST_RE.sub("- ", stripped)
            elif self._ORDERED_LIST_RE.match(stripped):
                text = stripped
            else:
                text = stripped
            formatted.append(self._format_inline(text))
        return "\n".join(formatted)

    def _format_code_block(self, content: str) -> str:
        lines = content.split("\n")
        if not lines:
            return ""
        return "Code:\n" + "\n".join(f"  {line}" for line in lines)

    def _convert_table(self, table_text: str) -> str:
        lines = table_text.strip().split("\n")
        if not lines:
            return ""

        rows: List[List[str]] = []
        for line in lines:
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)

        if not rows:
            return ""

        if len(rows) > 1 and self._is_table_separator(lines[1]):
            rows = [rows[0]] + rows[2:]

        if not rows:
            return ""

        summaries: List[str] = []
        for row in rows:
            label = "Item"
            value = "details unavailable"
            for index, cell in enumerate(row):
                if not cell:
                    continue
                lowered = cell.lower()
                if index == 0 or lowered in {"property", "name", "location", "item"}:
                    label = cell
                    continue
                value = cell
                break
            summaries.append(f"- {label}: {value}")

        return "\n".join(summaries)

    def _display_width(self, text: str) -> int:
        return len(text)

    # ─── Message Splitting ────────────────────────────────────────────────────

    def _join_and_split(self, blocks: List[str]) -> List[str]:
        if not blocks:
            return [""]

        full_text = "\n\n".join(blocks)

        if len(full_text) <= self.max_length:
            return [full_text]

        messages = self._split_blocks(blocks)

        final_messages: List[str] = []
        for msg in messages:
            if len(msg) <= self.max_length:
                final_messages.append(msg)
            else:
                final_messages.extend(self._split_at_paragraphs(msg))

        if len(final_messages) > 1:
            total = len(final_messages)
            for i, msg in enumerate(final_messages):
                prefix = f"{i + 1}/{total}\n\n"
                final_messages[i] = prefix + msg

        return final_messages

    def _split_blocks(self, blocks: List[str]) -> List[str]:
        messages: List[str] = []
        current: List[str] = []
        current_len = 0

        for block in blocks:
            block_len = len(block)
            separator_len = 2 if current else 0

            if current_len + separator_len + block_len <= self.max_length:
                current.append(block)
                current_len += separator_len + block_len
            else:
                if current:
                    messages.append("\n\n".join(current))
                current = [block]
                current_len = block_len

        if current:
            messages.append("\n\n".join(current))

        return messages

    def _split_at_paragraphs(self, text: str) -> List[str]:
        paragraphs: List[str] = []
        current: List[str] = []
        in_code_block = False

        for line in text.split("\n"):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                current.append(line)
                continue

            if not in_code_block and line.strip() == "":
                if current:
                    paragraphs.append("\n".join(current))
                current = []
                current.append(line)
            else:
                current.append(line)

        if current:
            paragraphs.append("\n".join(current))

        messages: List[str] = []
        current = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            separator_len = 2 if current else 0

            if current_len + separator_len + para_len <= self.max_length:
                current.append(para)
                current_len += separator_len + para_len
            else:
                if current:
                    messages.append("\n\n".join(current))
                current = [para]
                current_len = para_len

        if current:
            messages.append("\n\n".join(current))

        final: List[str] = []
        for msg in messages:
            if len(msg) <= self.max_length:
                final.append(msg)
            else:
                lines = msg.split("\n")
                current_lines: List[str] = []
                current_len = 0

                for line in lines:
                    line_len = len(line)
                    separator_len = 1 if current_lines else 0

                    if current_len + separator_len + line_len <= self.max_length:
                        current_lines.append(line)
                        current_len += separator_len + line_len
                    else:
                        if current_lines:
                            final.append("\n".join(current_lines))
                        current_lines = [line]
                        current_len = line_len

                if current_lines:
                    final.append("\n".join(current_lines))

        return final


# ─── Module-level convenience ─────────────────────────────────────────────────

_formatter: Optional[WhatsAppFormatter] = None


def get_formatter() -> WhatsAppFormatter:
    """Return a cached formatter instance."""
    global _formatter
    if _formatter is None:
        _formatter = WhatsAppFormatter()
    return _formatter


def format_for_whatsapp(text: str) -> List[str]:
    """Format text for WhatsApp, returning a list of message chunks."""
    return get_formatter().format(text)
