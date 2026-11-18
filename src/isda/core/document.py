"""
The document model: one parse, shared by every measure.

A Document is built from a single parse, and every feature a measure reads
derives from it, so two measures cannot disagree about what a paragraph is.

The prose projection excludes frontmatter, fenced code, HTML comments and table
rows; removes inline code; keeps the visible text of a link and drops its
target; and drops emphasis markers while keeping the emphasized text. The rules
are held fixed so that prose statistics stay comparable, and the projection is
computed in one place, on the block parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property

from .blocks import Block, BlockKind, PROSE_KINDS, Span, parse_blocks

_INLINE_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\([^)\n]*\)")
_WIKILINK = re.compile(r"\[\[([^\]\n|]+)(?:\|([^\]\n]+))?\]\]")
_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)(?=\S)(.*?)(?<=\S)\1", re.DOTALL)


def scrub_inline(text: str) -> str:
    """Remove inline markup from prose text, keeping the visible words."""
    text = _INLINE_COMMENT.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _MD_LINK.sub(lambda m: m.group(1), text)
    text = _WIKILINK.sub(lambda m: m.group(2) or m.group(1).split("/")[-1], text)
    text = _EMPHASIS.sub(lambda m: m.group(2), text)
    return text


@dataclass(frozen=True)
class ProseUnit:
    """One prose-bearing block, scrubbed. `span` is provenance into the source."""

    kind: BlockKind
    text: str
    span: Span


class Document:
    """A parsed source. Construct via Document.parse(). Parsing is total:
    any str yields a Document; there is no invalid input."""

    def __init__(self, source: str, blocks: tuple[Block, ...]):
        self.source = source
        self.blocks = blocks

    @classmethod
    def parse(cls, source: str) -> "Document":
        return cls(source, parse_blocks(source))

    @cached_property
    def total_bytes(self) -> int:
        return len(self.source.encode("utf-8"))

    @cached_property
    def prose_units(self) -> tuple[ProseUnit, ...]:
        units: list[ProseUnit] = []
        for b in self.blocks:
            if b.kind in PROSE_KINDS:
                text = scrub_inline(b.content).strip()
                if text:
                    units.append(ProseUnit(b.kind, text, b.span))
        return tuple(units)

    @cached_property
    def prose_text(self) -> str:
        return "\n\n".join(u.text for u in self.prose_units)

    @cached_property
    def headings(self) -> tuple[Block, ...]:
        return tuple(b for b in self.blocks if b.kind is BlockKind.HEADING)
