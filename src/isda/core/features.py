"""
Named features over a Document, and the fail-closed context measures read from.

The rule: a measure declares in `requires` exactly which features it reads, and
at run time it receives a FeatureContext that serves only those. Reading an
undeclared feature raises instead of answering. Enforcement at read time is
what keeps `requires` true: a field that nothing provides or validates can
drift from what the measure reads. Every feature derives from the Document's
single parse, so two measures that read the same feature read the same value.

Multiset and sequence are distinct features on purpose. A measure that reads
only the word multiset cannot be moved by any reordering, so the projection a
measure declares determines which perturbations can falsify it. The registry's
falsifier rule consumes this distinction: at least one declared falsifier must
destroy a feature the measure declares, so declaring the narrowest feature the
measure reads is what makes its falsifier list checkable. Broad declarations
(doc.source, prose.text) are valid but weaken the static check; the falsifier
harness remains the arbiter either way.

Multiset-valued features are canonicalized as sorted tuples so equality is
order-free by construction.
"""

from __future__ import annotations

import re
from typing import Callable, Mapping, cast

from .blocks import BlockKind
from .document import Document
from . import tokens


def _word_sequence(d: Document) -> tuple[str, ...]:
    return tokens.words(d.prose_text)


def _word_multiset(d: Document) -> tuple[str, ...]:
    return tuple(sorted(_word_sequence(d)))


def _sentence_sequence(d: Document) -> tuple[tuple[str, ...], ...]:
    return tokens.sentence_units(d)


def _sentence_multiset(d: Document) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(tokens.sentence_units(d)))


def _paragraph_sequence(d: Document) -> tuple[tuple[str, ...], ...]:
    return tokens.paragraph_units(d)


def _paragraph_multiset(d: Document) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(tokens.paragraph_units(d)))


def _chunk_multiset(d: Document) -> tuple[tuple[str, ...], ...]:
    """
    Blank-line-delimited chunks of the raw source, as case-folded word-tuples:
    list items and headings included. Coarser than prose paragraphs by design:
    chunk size is a layout property of how the author breaks the page, a
    different construct from prose-paragraph size.
    """
    return tuple(sorted(
        w for chunk in re.split(r"\n\s*\n", d.source)
        if (w := tokens.words(chunk))
    ))


def _heading_level_sequence(d: Document) -> tuple[int, ...]:
    """Heading levels in document order: the skeleton of the sectioning tree."""
    return tuple(b.level for b in d.headings)


def _section_word_counts(d: Document) -> tuple[int, ...]:
    """
    Words in each heading-delimited section, heading text excluded. One count
    per heading (the material down to the next heading); the preamble before
    the first heading counts as a section only when it has words. No headings
    means no sections: an empty tuple, so downstream measures answer None
    rather than inventing a section for sectionless prose.
    """
    counts: list[int] = []
    current = 0
    seen_heading = False
    for b in d.blocks:
        if b.kind is BlockKind.HEADING:
            if seen_heading or current:
                counts.append(current)
            current, seen_heading = 0, True
        elif b.kind in (BlockKind.PARAGRAPH, BlockKind.LIST_ITEM) and b.content:
            current += len(tokens.words(b.content))
    if seen_heading:
        counts.append(current)
    return tuple(counts)


def _block_kind_multiset(d: Document) -> tuple[str, ...]:
    """Non-blank block kinds as a sorted multiset: the page's material mix."""
    return tuple(sorted(
        b.kind.value for b in d.blocks if b.kind is not BlockKind.BLANK
    ))


FEATURES: Mapping[str, Callable[[Document], object]] = {
    "doc.source": lambda d: d.source,
    "doc.bytes": lambda d: d.total_bytes,
    "doc.blocks": lambda d: d.blocks,
    "doc.headings": lambda d: d.headings,
    "prose.text": lambda d: d.prose_text,
    "prose.word_sequence": _word_sequence,
    "prose.word_multiset": _word_multiset,
    "prose.sentence_sequence": _sentence_sequence,
    "prose.sentence_multiset": _sentence_multiset,
    "prose.paragraph_sequence": _paragraph_sequence,
    "prose.paragraph_multiset": _paragraph_multiset,
    "doc.chunk_multiset": _chunk_multiset,
    "doc.heading_level_sequence": _heading_level_sequence,
    "doc.section_word_counts": _section_word_counts,
    "doc.block_kind_multiset": _block_kind_multiset,
}


class UnknownFeature(KeyError):
    """The feature name is not in FEATURES: a typo, or a feature with no provider."""


class UndeclaredFeature(LookupError):
    """The measure reads a feature it did not declare in `requires`."""


class FeatureContext:
    """
    What a measure is allowed to see: the declared features of one Document.

    Fails closed. An unknown name raises UnknownFeature; a known name outside
    the measure's declaration raises UndeclaredFeature, whose message says to
    add the name to `requires`. Values are cached on the Document so two
    measures reading the same feature read the same object, not two parses.
    """

    def __init__(self, document: Document, allowed: frozenset[str]):
        self._doc = document
        self._allowed = allowed
        if not hasattr(document, "_feature_cache"):
            document._feature_cache = {}  # type: ignore[attr-defined]

    def get(self, name: str) -> object:
        if name not in FEATURES:
            raise UnknownFeature(
                f"no feature named {name!r}; known features: {sorted(FEATURES)}"
            )
        if name not in self._allowed:
            raise UndeclaredFeature(
                f"measure reads {name!r} but declared only {sorted(self._allowed)}; "
                "add it to `requires`: the declaration is what makes the "
                "falsifier list checkable"
            )
        cache = cast("dict[str, object]", self._doc._feature_cache)  # type: ignore[attr-defined]
        if name not in cache:
            cache[name] = FEATURES[name](self._doc)
        return cache[name]
