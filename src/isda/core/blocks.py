"""
The block parse: source text to a tiling of typed blocks.

Every measure reads one shared parse, so two measures cannot disagree about
what a paragraph is. Headings, fences, tables, list items and frontmatter are
declared by markdown syntax, and this parser reads the declarations exactly. It
never guesses, and what it cannot know exactly it does not emit. Inferring
structure from capitalization or punctuation misreads what the syntax declares:
a capitalization heuristic can read a table row as a section heading, and a
punctuation-only sentence splitter can merge a list of unpunctuated items into
one sentence.

Tiling invariant. The returned blocks partition the source completely:
concatenating every block's source slice reproduces the source byte-for-byte.
Blank runs are blocks so the invariant is checkable rather than approximate.
Because no text can be dropped, every word count can be audited against the
source.

Scope decisions:

- Indented (4-space) code blocks are not recognized, so their text counts as
  prose. Recognizing them without full CommonMark machinery would misparse
  ordinary list continuations as code, and the corpora this tool serves use
  fenced code.
- A blockquote is parsed as a paragraph with its markers stripped: nothing
  downstream reads quote-ness, so a dedicated kind would have no consumer.
- Setext headings follow CommonMark precedence: a `---` line closes an open
  paragraph as a level-2 heading; on its own it is a thematic break. A table
  delimiter row starts with `|` and is therefore never a setext candidate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class BlockKind(str, Enum):
    FRONTMATTER = "frontmatter"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE_FENCE = "code_fence"
    HTML_COMMENT = "html_comment"
    TABLE = "table"
    LIST_ITEM = "list_item"
    THEMATIC_BREAK = "thematic_break"
    BLANK = "blank"


# Kinds whose text participates in prose statistics.
PROSE_KINDS = frozenset({BlockKind.HEADING, BlockKind.PARAGRAPH, BlockKind.LIST_ITEM})


@dataclass(frozen=True)
class Span:
    """Half-open [start, end) in codepoint offsets into the source string."""

    start: int
    end: int

    def slice(self, source: str) -> str:
        return source[self.start:self.end]


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    span: Span
    content: str = ""  # structurally extracted inner text; "" for non-prose kinds
    level: int = 0     # heading level; 0 elsewhere
    info: str = ""     # fence info string; list marker; "" elsewhere


_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_ATX_CLOSE = re.compile(r"[ \t]+#+[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_THEMATIC = re.compile(r"^ {0,3}((?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*(.*)$")
_LIST = re.compile(r"^ {0,3}([-*+]|\d{1,9}[.)])[ \t]+(.*)$")
_QUOTE = re.compile(r"^ {0,3}> ?")
_FM_CLOSE = re.compile(r"^(---|\.\.\.)[ \t]*$")


def _is_table_row(raw: str) -> bool:
    s = raw.strip()
    return s.startswith("|") and raw.count("|") >= 2


def _is_comment_open(raw: str) -> bool:
    return raw.lstrip().startswith("<!--")


def _interrupts_paragraph(raw: str) -> bool:
    """Line starts that close an open paragraph (checked after setext)."""
    return (
        not raw.strip()
        or _ATX.match(raw) is not None
        or _FENCE_OPEN.match(raw) is not None
        or _THEMATIC.match(raw) is not None
        or _LIST.match(raw) is not None
        or _is_table_row(raw)
        or _is_comment_open(raw)
    )


def parse_blocks(source: str) -> tuple[Block, ...]:
    if not source:
        return ()

    lines = source.splitlines(keepends=True)
    starts: list[int] = []
    off = 0
    for ln in lines:
        starts.append(off)
        off += len(ln)
    n = len(lines)

    def span(i0: int, i1: int) -> Span:
        """Span covering lines i0..i1 inclusive."""
        return Span(starts[i0], starts[i1] + len(lines[i1]))

    raws = [ln.rstrip("\r\n") for ln in lines]
    blocks: list[Block] = []

    # Paragraph accumulation state.
    para_start: int | None = None
    para_text: list[str] = []

    def flush_para(last_line: int) -> None:
        nonlocal para_start, para_text
        if para_start is not None:
            blocks.append(Block(BlockKind.PARAGRAPH, span(para_start, last_line),
                                content="\n".join(para_text)))
            para_start, para_text = None, []

    i = 0

    # Frontmatter: only at the very start, and only if a closing delimiter line follows.
    if raws[0] == "---":
        close = next((j for j in range(1, n) if _FM_CLOSE.match(raws[j])), None)
        if close is not None:
            blocks.append(Block(BlockKind.FRONTMATTER, span(0, close)))
            i = close + 1

    while i < n:
        raw = raws[i]

        if para_start is not None:
            # Setext takes precedence over thematic break while a paragraph is open.
            m = _SETEXT.match(raw)
            if m:
                level = 1 if m.group(1)[0] == "=" else 2
                first = para_start
                title = "\n".join(para_text)
                para_start, para_text = None, []
                blocks.append(Block(BlockKind.HEADING, span(first, i),
                                    content=title, level=level))
                i += 1
                continue
            if _interrupts_paragraph(raw):
                flush_para(i - 1)
                continue  # reprocess this line outside the paragraph
            para_text.append(_QUOTE.sub("", raw))
            i += 1
            continue

        if not raw.strip():
            j = i
            while j + 1 < n and not raws[j + 1].strip():
                j += 1
            blocks.append(Block(BlockKind.BLANK, span(i, j)))
            i = j + 1
            continue

        fence = _FENCE_OPEN.match(raw)
        if fence:
            marker = fence.group(1)
            close_re = re.compile(rf"^ {{0,3}}{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$")
            j = next((k for k in range(i + 1, n) if close_re.match(raws[k])), n - 1)
            blocks.append(Block(BlockKind.CODE_FENCE, span(i, j), info=fence.group(2).strip()))
            i = j + 1
            continue

        if _is_comment_open(raw):
            j = next((k for k in range(i, n) if "-->" in raws[k]), n - 1)
            blocks.append(Block(BlockKind.HTML_COMMENT, span(i, j)))
            i = j + 1
            continue

        m = _ATX.match(raw)
        if m:
            title = _ATX_CLOSE.sub("", m.group(2) or "").strip()
            blocks.append(Block(BlockKind.HEADING, span(i, i),
                                content=title, level=len(m.group(1))))
            i += 1
            continue

        if _is_table_row(raw):
            j = i
            while j + 1 < n and _is_table_row(raws[j + 1]):
                j += 1
            blocks.append(Block(BlockKind.TABLE, span(i, j)))
            i = j + 1
            continue

        if _THEMATIC.match(raw):
            blocks.append(Block(BlockKind.THEMATIC_BREAK, span(i, i)))
            i += 1
            continue

        m = _LIST.match(raw)
        if m:
            marker, first_text = m.group(1), m.group(2)
            item = [first_text]
            j = i
            while (j + 1 < n and raws[j + 1].strip()
                   and not _interrupts_paragraph(raws[j + 1])
                   and _SETEXT.match(raws[j + 1]) is None):
                j += 1
                item.append(raws[j].strip())
            blocks.append(Block(BlockKind.LIST_ITEM, span(i, j),
                                content="\n".join(item), info=marker))
            i = j + 1
            continue

        # Anything else opens a paragraph (blockquote markers stripped per line).
        para_start = i
        para_text = [_QUOTE.sub("", raw)]
        i += 1

    flush_para(n - 1)
    return tuple(blocks)
