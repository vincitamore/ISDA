"""
Tokenization over the parsed document: words, sentence units, section segments.

Tokenization is block-aware by construction: a heading or a list item is its
own sentence unit whether or not it ends in terminal punctuation, because the
parser knows what it is and no punctuation heuristic has to guess. Splitting on
terminal punctuation alone would read a list of unpunctuated items as one long
sentence and corrupt every downstream rhythm feature.

Word tokenization is Unicode-aware and case-folded: under an ASCII-only class no
word boundary exists between `f` and `é`, and `café` would match nothing.

Combining marks join their base character. Under UAX #29 (Unicode text
segmentation), word-boundary rule WB4 ignores Extend characters, so combining
marks never break a word, and grapheme clusters put a base and its marks in one
cluster. Treating a diacritic as a word boundary, which no orthography does,
shatters pointed Hebrew, Arabic with harakat, Devanagari and NFD-normalized
Latin into fragments. Precomposed (NFC) text such as polytonic Greek would
survive that treatment, but the same text in NFD would not, so the rule is
general rather than script-specific.

Hebrew niqqud have no precomposed forms, so normalization alone cannot fix
this and the mark class is required. The class is derived from the running
interpreter's Unicode tables at import (about 0.1 s, cached in the compiled
pattern) rather than hand-listed, so marks added by a Python upgrade are picked
up instead of missing from a fixed list.
"""

from __future__ import annotations

import re
import sys
import unicodedata

from .blocks import BlockKind
from .document import Document, ProseUnit


def _mark_class() -> str:
    """The Unicode combining marks (Mn/Mc/Me) as a regex character class."""
    marks = [cp for cp in range(sys.maxunicode + 1)
             if unicodedata.category(chr(cp)) in ("Mn", "Mc", "Me")]
    parts: list[str] = []
    start = prev = marks[0]
    for cp in marks[1:]:
        if cp == prev + 1:
            prev = cp
            continue
        parts.append(re.escape(chr(start)) if start == prev
                     else f"{re.escape(chr(start))}-{re.escape(chr(prev))}")
        start = prev = cp
    parts.append(re.escape(chr(start)) if start == prev
                 else f"{re.escape(chr(start))}-{re.escape(chr(prev))}")
    return "".join(parts)


MARKS = _mark_class()
# A word is a run of letters, each of which may carry combining marks. A word
# may not start with a mark: a stray mark after punctuation is not a word.
WORD = re.compile(rf"[^\W\d_][{MARKS}]*(?:[^\W\d_][{MARKS}]*)*", re.UNICODE)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def words(text: str) -> tuple[str, ...]:
    """Case-folded word tokens of a prose string."""
    return tuple(WORD.findall(text.lower()))


def word_spans(text: str) -> tuple[tuple[int, int], ...]:
    """(start, end) codepoint offsets of each word within `text`."""
    return tuple(m.span() for m in WORD.finditer(text))


def sentence_units(doc: Document) -> tuple[tuple[str, ...], ...]:
    """
    Sentences as case-folded word-tuples, block-aware.

    Headings and list items are one unit each; paragraphs split on terminal
    punctuation. Units are word-tuples rather than raw strings so that
    whitespace differences cannot change them.
    """
    units: list[tuple[str, ...]] = []
    for u in doc.prose_units:
        if u.kind in (BlockKind.HEADING, BlockKind.LIST_ITEM):
            w = words(u.text)
            if w:
                units.append(w)
        else:
            for sent in _SENT_SPLIT.split(u.text):
                w = words(sent)
                if w:
                    units.append(w)
    return tuple(units)


def paragraph_units(doc: Document) -> tuple[tuple[str, ...], ...]:
    """
    Paragraphs as case-folded word-tuples, from `PARAGRAPH` blocks only.

    Headings and list items are compositional units of a different kind and are
    excluded. A raw blank-line split would count them as paragraphs; that split
    is the separate feature `doc.chunk_multiset`.
    """
    return tuple(
        w for u in doc.prose_units
        if u.kind is BlockKind.PARAGRAPH and (w := words(u.text))
    )


def sections(doc: Document) -> tuple[tuple[str, tuple[ProseUnit, ...]], ...]:
    """
    Heading-delimited segments: (heading title, prose units under it).

    Prose before any heading lands under the label '(preamble)'. This is the
    segment layer for local-density rollups. It has no feature-registry entry
    because no registered measure reads it.
    """
    out: list[tuple[str, list[ProseUnit]]] = []
    label = "(preamble)"
    bucket: list[ProseUnit] = []
    for u in doc.prose_units:
        if u.kind is BlockKind.HEADING:
            if bucket:
                out.append((label, bucket))
            label, bucket = u.text, []
        else:
            bucket.append(u)
    if bucket or not out:
        out.append((label, bucket))
    return tuple((lbl, tuple(us)) for lbl, us in out)
