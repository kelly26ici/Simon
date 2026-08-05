"""
WhatsApp Formatting Layer

Converts Markdown text from the LLM into WhatsApp-compatible format.
Sits between the LLM output and the WhatsApp Cloud API as the single
choke-point for all outgoing messages.

Supported conversions:
- **bold** / __bold__ → *bold*
- *italic* / _italic_ → _italic_
- ~~strikethrough~~ → ~strikethrough~
- `code` → `code` (preserved)
- ```code blocks``` → ```code blocks``` (preserved)
- # Headings → *Bold*
- [text](url) → text (url)
- | Tables | → aligned text grid
- Long messages → split at paragraph boundaries with "1/N" prefix
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
    type: str  # "paragraph", "code_block", "table", "list", "blockquote", "heading", "hr"
    content: str
    raw: str = ""


# ─── WhatsApp Formatter ───────────────────────────────────────────────────────

class WhatsAppFormatter:
    """Converts Markdown text from the LLM into WhatsApp-compatible format.

    This is the single choke-point for all outgoing WhatsApp messages.
    Every message sent via ``send_whatsapp_message()`` passes through here.
    """

    # ─── Regex Patterns ───────────────────────────────────────────────────────

    # Code span: `code` (but not ``` which is a code block fence)
    _CODE_SPAN_RE = re.compile(r'(?<!`)`([^`]+)`(?!`)')

    # Bold: **text** or __text__
    _BOLD_RE = re.compile(r'\*\*(.+?)\*\*|__(.+?)__')

    # Strikethrough: ~~text~~
    _STRIKETHROUGH_RE = re.compile(r'~~(.+?)~~')

    # Italic: *text* (single asterisks, not part of **text**)
    _ITALIC_ASTERISK_RE = re.compile(r'(?<!\*)\*([^*]+)\*(?!\*)')

    # Links: [text](url) or [text](url "title")
    _LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')

    # Images: ![alt](url) or ![alt](url "title")
    _IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')

    # Headings: #, ##, ###, etc.
    _HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')

    # Horizontal rule: ---, ***, ___
    _HR_RE = re.compile(r'^(-{3}|\*{3}|_{3})\s*$')

    # List items: - item, * item, 1. item
    _UNORDERED_LIST_RE = re.compile(r'^[-*]\s+')
    _ORDERED_LIST_RE = re.compile(r'^\d+\.\s+')

    # Null byte placeholder for protected content
    _NULL = '\x00'

    def __init__(
        self,
        max_length: Optional[int] = None,
        table_mode: Optional[str] = None,
        debug: Optional[bool] = None,
    ):
        self.max_length = max_length if max_length is not None else WHATSAPP_MAX_MESSAGE_LENGTH
        self.table_mode = table_mode if table_mode is not None else WHATSAPP_TABLE_MODE
        self.debug = debug if debug is not None else WHATSAPP_FORMAT_DEBUG

    def format(self, text: str) -> List[str]:
        """Format Markdown text and split into WhatsApp-compatible message chunks.

        Returns a list of message strings, each within the ``max_length`` limit.
        Multi-part messages are prefixed with ``"1/N"``.
        """
        if not text or not text.strip():
            return [""]

        if self.debug:
            logger.debug("Formatting text ({} chars)", len(text))

        # Parse into blocks
        blocks = self._parse_blocks(text)

        if self.debug:
            logger.debug("Parsed {} blocks", len(blocks))

        # Convert each block to WhatsApp format
        formatted_blocks: List[str] = []
        for block in blocks:
            formatted = self._format_block(block)
            if formatted:
                formatted_blocks.append(formatted)

        # Join and split if needed
        messages = self._join_and_split(formatted_blocks)

        if self.debug:
            logger.debug("Produced {} message(s)", len(messages))

        return messages

    # ─── Block Parsing ────────────────────────────────────────────────────────

    def _parse_blocks(self, text: str) -> List[FormatBlock]:
        """Parse Markdown text into semantic blocks."""
        lines = text.split('\n')
        blocks: List[FormatBlock] = []

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                i += 1
                continue

            # Fenced code block
            if stripped.startswith('```'):
                lang = stripped[3:].strip()
                code_lines: List[str] = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing ```
                content = '\n'.join(code_lines)
                blocks.append(FormatBlock(
                    type="code_block",
                    content=content,
                    raw=f"```{lang}\n{content}\n```",
                ))
                continue

            # Table (starts with | and has a separator row on the next line)
            if stripped.startswith('|') and i + 1 < len(lines) and self._is_table_separator(lines[i + 1]):
                table_lines = [line]
                i += 1
                while i < len(lines) and lines[i].strip().startswith('|'):
                    table_lines.append(lines[i])
                    i += 1
                blocks.append(FormatBlock(
                    type="table",
                    content='\n'.join(table_lines),
                    raw='\n'.join(table_lines),
                ))
                continue

            # Heading
            heading_match = self._HEADING_RE.match(stripped)
            if heading_match:
                content = heading_match.group(2)
                blocks.append(FormatBlock(
                    type="heading",
                    content=content,
                    raw=line,
                ))
                i += 1
                continue

            # Blockquote
            if stripped.startswith('>'):
                quote_lines: List[str] = []
                while i < len(lines) and lines[i].strip().startswith('>'):
                    quote_lines.append(lines[i].strip()[1:].strip())
                    i += 1
                blocks.append(FormatBlock(
                    type="blockquote",
                    content='\n'.join(quote_lines),
                    raw='\n'.join(quote_lines),
                ))
                continue

            # List
            if self._UNORDERED_LIST_RE.match(stripped) or self._ORDERED_LIST_RE.match(stripped):
                list_lines: List[str] = []
                while i < len(lines):
                    s = lines[i].strip()
                    if self._UNORDERED_LIST_RE.match(s) or self._ORDERED_LIST_RE.match(s):
                        list_lines.append(lines[i])
                        i += 1
                    else:
                        break
                blocks.append(FormatBlock(
                    type="list",
                    content='\n'.join(list_lines),
                    raw='\n'.join(list_lines),
                ))
                continue

            # Horizontal rule
            if self._HR_RE.match(stripped):
                blocks.append(FormatBlock(
                    type="hr",
                    content="—",
                    raw=line,
                ))
                i += 1
                continue

            # Paragraph (collect consecutive non-empty, non-block-start lines)
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
                blocks.append(FormatBlock(
                    type="paragraph",
                    content='\n'.join(para_lines),
                    raw='\n'.join(para_lines),
                ))
                continue

            # Fallback: skip the line
            i += 1

        return blocks

    def _is_table_separator(self, line: str) -> bool:
        """Check if a line is a Markdown table separator (|---|---|)."""
        stripped = line.strip()
        if not stripped.startswith('|'):
            return False
        cells = stripped.strip('|').split('|')
        return all(re.match(r'^[-:]+$', c.strip()) for c in cells if c.strip())

    def _is_block_start(self, line: str) -> bool:
        """Check if a line starts a new block (code, table, heading, etc.)."""
        stripped = line.strip()
        if not stripped:
            return True
        if stripped.startswith('```'):
            return True
        if stripped.startswith('|') and self._is_table_separator(line):
            return True
        if self._HEADING_RE.match(stripped):
            return True
        if stripped.startswith('>'):
            return True
        if self._UNORDERED_LIST_RE.match(stripped) or self._ORDERED_LIST_RE.match(stripped):
            return True
        if self._HR_RE.match(stripped):
            return True
        return False

    # ─── Block Formatting ─────────────────────────────────────────────────────

    def _format_block(self, block: FormatBlock) -> str:
        """Convert a single block to WhatsApp format."""
        if block.type == "code_block":
            return f"```\n{block.content}\n```"
        elif block.type == "table":
            return self._convert_table(block.content)
        elif block.type == "heading":
            # Format the content first, then wrap in *...* for bold.
            # (Wrapping first would make _format_inline treat it as italic.)
            return f"*{self._format_inline(block.content)}*"
        elif block.type == "blockquote":
            return self._format_blockquote(block.content)
        elif block.type == "list":
            return self._format_list(block.content)
        elif block.type == "hr":
            return "—"
        else:  # paragraph
            return self._format_inline(block.content)

    def _format_inline(self, text: str) -> str:
        """Convert inline Markdown to WhatsApp syntax.

        Order of operations:
        1. Protect code spans (so formatting chars inside them are ignored)
        2. Remove images (![alt](url) → removed) — must come before links
           so ``![alt](url)`` is removed before ``[alt](url)`` can match
        3. Convert links ([text](url) → text (url))
        4. Convert bold (**text** / __text__ → *text*)
        5. Convert strikethrough (~~text~~ → ~text~)
        6. Convert italic (*text* → _text_)
        7. Restore code spans and bold

        Links/images are processed before bold/italic so that ``**[link](url)**``
        (a bold link) is converted correctly.
        """
        # 1. Protect code spans
        code_spans: List[str] = []

        def _save_code_span(m: re.Match) -> str:
            code_spans.append(m.group(0))
            return f'{self._NULL}CODE{len(code_spans) - 1}{self._NULL}'

        text = self._CODE_SPAN_RE.sub(_save_code_span, text)

        # 2. Remove images FIRST: ![alt](url) → removed
        #    Must come before links so ``![alt](url)`` is fully consumed
        #    before ``[alt](url)`` can match as a link.
        text = self._IMAGE_RE.sub('', text)

        # 3. Convert links: [text](url) → text (url)
        text = self._LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)

        # 4. Convert bold: **text** or __text__ → *text*
        bold_matches: List[str] = []

        def _save_bold(m: re.Match) -> str:
            bold_matches.append(m.group(1) or m.group(2))
            return f'{self._NULL}BOLD{len(bold_matches) - 1}{self._NULL}'

        text = self._BOLD_RE.sub(_save_bold, text)

        # 5. Convert strikethrough: ~~text~~ → ~text~
        text = self._STRIKETHROUGH_RE.sub(lambda m: f"~{m.group(1)}~", text)

        # 6. Convert italic: *text* → _text_ (single asterisks only)
        text = self._ITALIC_ASTERISK_RE.sub(lambda m: f"_{m.group(1)}_", text)

        # 7. Restore bold
        for i, match in enumerate(bold_matches):
            text = text.replace(f'{self._NULL}BOLD{i}{self._NULL}', f'*{match}*')

        # 8. Restore code spans
        for i, span in enumerate(code_spans):
            text = text.replace(f'{self._NULL}CODE{i}{self._NULL}', span)

        return text

    def _format_blockquote(self, content: str) -> str:
        """Format a blockquote for WhatsApp."""
        lines = content.split('\n')
        formatted = []
        for line in lines:
            formatted.append(f"> {self._format_inline(line)}")
        return '\n'.join(formatted)

    def _format_list(self, content: str) -> str:
        """Format a list for WhatsApp."""
        lines = content.split('\n')
        formatted = []
        for line in lines:
            stripped = line.strip()
            # Convert Markdown list markers to WhatsApp-compatible
            if self._UNORDERED_LIST_RE.match(stripped):
                text = self._UNORDERED_LIST_RE.sub('• ', stripped)
            elif self._ORDERED_LIST_RE.match(stripped):
                text = stripped  # Keep numbered lists as-is
            else:
                text = stripped
            formatted.append(self._format_inline(text))
        return '\n'.join(formatted)

    def _convert_table(self, table_text: str) -> str:
        """Convert a Markdown table to a WhatsApp-friendly text grid."""
        lines = table_text.strip().split('\n')
        if not lines:
            return ""

        # Parse rows
        rows: List[List[str]] = []
        for line in lines:
            cells = [c.strip() for c in line.strip('|').split('|')]
            rows.append(cells)

        if not rows:
            return ""

        # Remove separator row (second row)
        if len(rows) > 1 and self._is_table_separator(lines[1]):
            rows = [rows[0]] + rows[2:]

        if not rows:
            return ""

        # Calculate column widths
        num_cols = max(len(row) for row in rows)
        col_widths = [0] * num_cols
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], self._display_width(cell))

        # Build the grid
        result_lines: List[str] = []

        # Top border
        border = "┌" + "┬".join("─" * (w + 2) for w in col_widths) + "┐"
        result_lines.append(border)

        # Header row
        header_cells = rows[0] + [''] * (num_cols - len(rows[0]))
        header = "│ " + " │ ".join(cell.ljust(w) for cell, w in zip(header_cells, col_widths)) + " │"
        result_lines.append(header)

        # Separator after header
        sep = "├" + "┼".join("─" * (w + 2) for w in col_widths) + "┤"
        result_lines.append(sep)

        # Data rows
        for row in rows[1:]:
            row = row + [''] * (num_cols - len(row))
            line = "│ " + " │ ".join(cell.ljust(w) for cell, w in zip(row, col_widths)) + " │"
            result_lines.append(line)

        # Bottom border
        bottom = "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘"
        result_lines.append(bottom)

        return '\n'.join(result_lines)

    def _display_width(self, text: str) -> int:
        """Calculate the display width of a string.

        Uses ``len()`` for now — accurate for ASCII but may be off for
        wide Unicode characters (CJK, emojis). A more robust implementation
        would use ``wcwidth`` or similar.
        """
        return len(text)

    # ─── Message Splitting ────────────────────────────────────────────────────

    def _join_and_split(self, blocks: List[str]) -> List[str]:
        """Join blocks and split into messages that fit within ``max_length``."""
        if not blocks:
            return [""]

        # First, try joining everything
        full_text = '\n\n'.join(blocks)

        if len(full_text) <= self.max_length:
            return [full_text]

        # Need to split — use greedy block-level splitting
        messages = self._split_blocks(blocks)

        # If we still have messages that are too long, split within blocks
        # at paragraph boundaries (but never break code blocks, URLs, lists,
        # tables, or blockquotes)
        final_messages: List[str] = []
        for msg in messages:
            if len(msg) <= self.max_length:
                final_messages.append(msg)
            else:
                # Split at paragraph boundaries within the message
                sub_parts = self._split_at_paragraphs(msg)
                final_messages.extend(sub_parts)

        # Add "1/N" prefix to multi-part messages
        if len(final_messages) > 1:
            total = len(final_messages)
            for i, msg in enumerate(final_messages):
                prefix = f"{i + 1}/{total}\n\n"
                final_messages[i] = prefix + msg

        return final_messages

    def _split_blocks(self, blocks: List[str]) -> List[str]:
        """Split blocks into messages that fit within ``max_length``.

        Uses a greedy approach: accumulate blocks until adding the next
        would exceed ``max_length``, then start a new message.
        """
        messages: List[str] = []
        current: List[str] = []
        current_len = 0

        for block in blocks:
            block_len = len(block)
            # Account for the '\n\n' separator
            separator_len = 2 if current else 0

            if current_len + separator_len + block_len <= self.max_length:
                current.append(block)
                current_len += separator_len + block_len
            else:
                if current:
                    messages.append('\n\n'.join(current))
                current = [block]
                current_len = block_len

        if current:
            messages.append('\n\n'.join(current))

        return messages

    def _split_at_paragraphs(self, text: str) -> List[str]:
        """Split text at paragraph boundaries.

        Never breaks code blocks, URLs, lists, tables, or blockquotes.
        Falls back to line-level splitting for oversized single blocks.
        """
        # Split by double newlines, but don't split inside code blocks
        paragraphs: List[str] = []
        current: List[str] = []
        in_code_block = False

        for line in text.split('\n'):
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                current.append(line)
                continue

            if not in_code_block and line.strip() == '':
                # Paragraph boundary
                if current:
                    paragraphs.append('\n'.join(current))
                    current = []
                current.append(line)  # Keep the empty line
            else:
                current.append(line)

        if current:
            paragraphs.append('\n'.join(current))

        # Now group paragraphs into messages
        messages: List[str] = []
        current: List[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            separator_len = 2 if current else 0

            if current_len + separator_len + para_len <= self.max_length:
                current.append(para)
                current_len += separator_len + para_len
            else:
                if current:
                    messages.append('\n\n'.join(current))
                current = [para]
                current_len = para_len

        if current:
            messages.append('\n\n'.join(current))

        # If any message is still too long, split at line boundaries
        # (last resort — handles oversized code blocks, tables, etc.)
        final: List[str] = []
        for msg in messages:
            if len(msg) <= self.max_length:
                final.append(msg)
            else:
                # Split at line boundaries
                lines = msg.split('\n')
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
                            final.append('\n'.join(current_lines))
                        current_lines = [line]
                        current_len = line_len

                if current_lines:
                    final.append('\n'.join(current_lines))

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
    """Format Markdown text for WhatsApp, returning a list of message chunks.

    Each chunk is within the WhatsApp 4096-character limit.
    Multi-part messages are prefixed with ``"1/N"``.
    """
    return get_formatter().format(text)
