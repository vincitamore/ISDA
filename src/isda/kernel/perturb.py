"""
The perturbation library.

Each entry destroys one named structure. A measure claiming to read that structure
must move when it is destroyed; a measure claiming not to depend on it must not.

Three rules shape the library.

1. Shuffle and reverse are not interchangeable. A statistic that sums over
   adjacent pairs is exactly invariant under reversal, because reversal
   preserves the unordered pair set, while it moves freely under shuffling.
   Shuffle asks whether order matters; reverse asks whether direction does. A
   trajectory measure that cannot tell a document from its mirror image is not
   reading trajectory.

2. Reordering does not split fenced blocks. A paragraph shuffle that cuts
   through a code fence corrupts every downstream count, so a measure appears to
   move under its own null. Fences are masked before reordering and restored
   after.

3. What a perturbation preserves is relative to what a measure reads. Each
   perturbation carries `destroys`: the feature names (isda.core.features) whose
   values it does not preserve. A single list of "multiset-preserving"
   perturbations cannot express this: merge and resplit preserve the word
   multiset exactly (they are whitespace edits), but they are the right
   falsifiers for measures of paragraph boundaries because they destroy the
   paragraph features. The relation therefore lives in each row, and the
   registry checks falsifiers against the features a measure declares it reads.
"""

from __future__ import annotations

import random
import re

from .descriptor import Perturbation

_FENCE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", re.DOTALL | re.MULTILINE)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _mask_fences(text: str) -> tuple[str, list[str]]:
    """Replace fenced blocks with opaque tokens so reordering cannot cut them."""
    held: list[str] = []

    def take(m: re.Match[str]) -> str:
        held.append(m.group(0))
        return f"\x00FENCE{len(held) - 1}\x00"

    return _FENCE.sub(take, text), held


def _unmask_fences(text: str, held: list[str]) -> str:
    for i, block in enumerate(held):
        text = text.replace(f"\x00FENCE{i}\x00", block)
    return text


def _reorder(text: str, seed: int, unit: str, reverse: bool = False) -> str:
    masked, held = _mask_fences(text)
    if unit == "paragraph":
        parts = re.split(r"\n\s*\n", masked)
        joiner = "\n\n"
    elif unit == "sentence":
        parts = _SENT_SPLIT.split(masked)
        joiner = " "
    elif unit == "line":
        parts = masked.split("\n")
        joiner = "\n"
    else:  # pragma: no cover - unreachable: callers pass a known unit
        raise ValueError(unit)

    if reverse:
        parts = parts[::-1]
    else:
        rng = random.Random(seed)
        rng.shuffle(parts)
    return _unmask_fences(joiner.join(parts), held)


def _scramble_words(text: str, seed: int) -> str:
    """Destroy every proposition while preserving the exact word multiset."""
    masked, held = _mask_fences(text)
    words = re.findall(r"\S+", masked)
    rng = random.Random(seed)
    rng.shuffle(words)
    return _unmask_fences(" ".join(words), held)


def _scramble_within_sentence(text: str, seed: int) -> str:
    """Destroy syntax while preserving sentence boundaries and lengths."""
    masked, held = _mask_fences(text)
    rng = random.Random(seed)
    out: list[str] = []
    for sent in _SENT_SPLIT.split(masked):
        w = sent.split()
        rng.shuffle(w)
        out.append(" ".join(w))
    return _unmask_fences(" ".join(out), held)


def _merge_paragraphs(text: str, seed: int) -> str:
    """
    Remove paragraph boundaries, collapsing the document into one block.

    This is the destroyer for any measure about compositional unit size.
    Truncation is not: a median over a random half of a homogeneous population is
    approximately the same median, so a paragraph-length measure survives
    truncation by arithmetic.
    """
    masked, held = _mask_fences(text)
    merged = re.sub(r"\n\s*\n", " ", masked)
    return _unmask_fences(merged, held)


def _resplit_paragraphs(text: str, seed: int) -> str:
    """Re-cut paragraph boundaries at random, preserving word order and content."""
    masked, held = _mask_fences(text)
    # Split on any whitespace. Splitting on " " alone leaves embedded newlines
    # inside the chunks, so the rejoined "paragraphs" still contain blank lines
    # and the paragraph splitter re-cuts them; the perturbation would then
    # barely move a paragraph-length measure, which would read as failing its
    # falsifier.
    words = masked.split()
    if len(words) < 4:
        return text
    rng = random.Random(seed)
    out: list[str] = []
    i = 0
    while i < len(words):
        take = rng.randint(2, max(3, len(words) // 4))
        out.append(" ".join(words[i:i + take]))
        i += take
    return _unmask_fences("\n\n".join(out), held)


_ATX_MARKER = re.compile(r"^([ \t]{0,3})(#{1,6})(?=[ \t])", re.MULTILINE)
_ATX_FULL = re.compile(r"^([ \t]{0,3})#{1,6}[ \t]+", re.MULTILINE)


def _flatten_headings(text: str, seed: int) -> str:
    """
    Demote every ATX heading to level 1, leaving titles and layout untouched.

    The destroyer for measures about heading hierarchy: depth and branching
    collapse by construction while every word, chunk and section boundary
    survives. Setext headings are left alone: they encode only levels 1-2, and
    rewriting them would move the blank-line structure this perturbation exists
    to preserve; block B (working markdown) is ATX throughout.
    """
    masked, held = _mask_fences(text)
    return _unmask_fences(_ATX_MARKER.sub(r"\1#", masked), held)


def _strip_headings(text: str, seed: int) -> str:
    """
    Remove ATX heading markers so titles become plain paragraph lines.

    The destroyer for measures that need headings to exist at all.
    """
    masked, held = _mask_fences(text)
    return _unmask_fences(_ATX_FULL.sub(r"\1", masked), held)


_ATX_LINE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+\S.*$")


def _equalize_sections(text: str, seed: int) -> str:
    """
    Re-deal all post-first-heading material into equal-sized sections, with
    heading lines and their order untouched.

    The destroyer for measures about section-size unevenness. A paragraph
    shuffle cannot destroy unevenness, because a random deal of material is
    about as uneven as an authored one (random spacings are themselves highly
    dispersed); equalizing the sections does.
    """
    masked, held = _mask_fences(text)
    lines = masked.split("\n")
    first_heading = next(
        (i for i, ln in enumerate(lines) if _ATX_LINE.match(ln)), None)
    if first_heading is None:
        return text
    preamble = lines[:first_heading]
    headings: list[str] = []
    pool: list[str] = []
    for ln in lines[first_heading:]:
        if _ATX_LINE.match(ln):
            headings.append(ln)
        else:
            pool.extend(ln.split())
    share, rem = divmod(len(pool), len(headings))
    out: list[str] = ["\n".join(preamble).strip("\n")] if any(
        s.strip() for s in preamble) else []
    i = 0
    for k, h in enumerate(headings):
        take = share + (1 if k < rem else 0)
        body = " ".join(pool[i:i + take])
        i += take
        out.append(h + ("\n\n" + body if body else ""))
    return _unmask_fences("\n\n".join(out) + "\n", held)


def _duplicate(text: str, seed: int) -> str:
    """
    Double the document.

    Set statistics (median, min, max, range) are invariant under this by proof,
    since a duplicated multiset has the same order statistics. That invariance is
    arithmetic, not evidence that a measure is robust.
    """
    return text + "\n\n" + text


def _lowercase(text: str, seed: int) -> str:
    return text.lower()


def _whitespace_noise(text: str, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(c + ("  " if c == " " and rng.random() < 0.3 else "") for c in text)


def _truncate_half(text: str, seed: int) -> str:
    lines = text.split("\n")
    return "\n".join(lines[: max(1, len(lines) // 2)])


# Every perturbation edits the raw text, so a measure that declares it reads the
# raw text (doc.source / prose.text) may be moved by any of them.
_ANY_TEXT = frozenset({"doc.source", "prose.text"})

_ALL_CONTENT = _ANY_TEXT | frozenset({
    "doc.bytes",
    "prose.word_multiset", "prose.word_sequence",
    "prose.sentence_multiset", "prose.sentence_sequence",
    "prose.paragraph_multiset", "prose.paragraph_sequence",
    "doc.chunk_multiset",
    "doc.heading_level_sequence", "doc.section_word_counts",
    "doc.block_kind_multiset",
})

# Structure destroyed by any transformation that rejoins text with spaces or
# collapses blank lines: heading lines stop being headings, sections stop
# existing, and the block-kind mix collapses toward prose.
_RAZES_LAYOUT = frozenset({
    "doc.heading_level_sequence", "doc.section_word_counts",
    "doc.block_kind_multiset",
})

SHUFFLE_PARAGRAPHS = Perturbation(
    "shuffle_paragraphs", "paragraph order",
    lambda t, s: _reorder(t, s, "paragraph"),
    # Headings move with the shuffle as blank-line units, so their order, and
    # with it the level sequence and every section's contents, is destroyed,
    # while the level multiset survives by construction. The block-kind multiset
    # does not survive: kinds can depend on position (frontmatter is frontmatter
    # only at document start), so a kind-mix measure can move under a shuffle.
    destroys=_ANY_TEXT | frozenset({
        "prose.paragraph_sequence", "prose.sentence_sequence", "prose.word_sequence",
        "doc.heading_level_sequence", "doc.section_word_counts",
        "doc.block_kind_multiset",
    }))
REVERSE_PARAGRAPHS = Perturbation(
    "reverse_paragraphs", "paragraph direction",
    lambda t, s: _reorder(t, s, "paragraph", reverse=True), seeded=False,
    destroys=_ANY_TEXT | frozenset({
        "prose.paragraph_sequence", "prose.sentence_sequence", "prose.word_sequence",
        "doc.heading_level_sequence", "doc.section_word_counts",
        "doc.block_kind_multiset",
    }))
SHUFFLE_SENTENCES = Perturbation(
    "shuffle_sentences", "sentence order",
    lambda t, s: _reorder(t, s, "sentence"),
    # Rejoining with spaces collapses blank-line boundaries, so chunk structure
    # is destroyed as a side effect, alongside the order this perturbation is
    # designed to destroy.
    destroys=_ANY_TEXT | _RAZES_LAYOUT | frozenset({
        "prose.sentence_sequence", "prose.word_sequence", "doc.chunk_multiset",
    }))
REVERSE_SENTENCES = Perturbation(
    "reverse_sentences", "sentence direction",
    lambda t, s: _reorder(t, s, "sentence", reverse=True), seeded=False,
    destroys=_ANY_TEXT | _RAZES_LAYOUT | frozenset({
        "prose.sentence_sequence", "prose.word_sequence", "doc.chunk_multiset",
    }))
SCRAMBLE_WORDS = Perturbation(
    "scramble_words", "propositional content",
    _scramble_words,
    # Destroys all linguistic structure above the word multiset.
    destroys=_ANY_TEXT | _RAZES_LAYOUT | frozenset({
        "prose.word_sequence",
        "prose.sentence_multiset", "prose.sentence_sequence",
        "prose.paragraph_multiset", "prose.paragraph_sequence",
        "doc.chunk_multiset",
    }))
SCRAMBLE_IN_SENTENCE = Perturbation(
    "scramble_within_sentence", "syntax within sentences",
    _scramble_within_sentence,
    # Preserves sentence count and lengths; destroys word order and therefore
    # sentence identity (a sentence is its word-tuple). Rejoins with spaces,
    # so chunk boundaries are destroyed too.
    destroys=_ANY_TEXT | _RAZES_LAYOUT | frozenset({
        "prose.word_sequence",
        "prose.sentence_multiset", "prose.sentence_sequence",
        "doc.chunk_multiset",
    }))
DUPLICATE_DOCUMENT = Perturbation(
    "duplicate_document", "document length (not content)",
    _duplicate, seeded=False,
    # Doubles every count while leaving every ratio and order statistic fixed:
    # a duplicated multiset has the same median by proof. It changes all feature
    # values, so it may serve a size-reading measure as falsifier; the harness
    # decides whether the measure's projection moves.
    destroys=_ALL_CONTENT)
LOWERCASE = Perturbation(
    "lowercase", "capitalisation", _lowercase, seeded=False,
    # Word features are case-folded, so this touches only the raw text.
    destroys=_ANY_TEXT)
WHITESPACE_NOISE = Perturbation(
    "whitespace_noise", "whitespace layout", _whitespace_noise,
    destroys=_ANY_TEXT | frozenset({"doc.bytes"}))
TRUNCATE_HALF = Perturbation(
    "truncate_half", "the document's second half",
    _truncate_half, seeded=False,
    destroys=_ALL_CONTENT)
MERGE_PARAGRAPHS = Perturbation(
    "merge_paragraphs", "paragraph boundaries",
    _merge_paragraphs, seeded=False,
    # Collapsing blank lines inlines heading markers mid-line, so heading,
    # section and block-kind structure is destroyed as a side effect, alongside
    # the boundaries this perturbation is designed to destroy.
    destroys=_ANY_TEXT | _RAZES_LAYOUT | frozenset({
        "prose.paragraph_multiset", "prose.paragraph_sequence",
        "doc.chunk_multiset",
    }))
RESPLIT_PARAGRAPHS = Perturbation(
    "resplit_paragraphs", "paragraph boundary placement",
    _resplit_paragraphs,
    # Re-cutting splits on all whitespace, so sentence units change and heading
    # markers land mid-line: layout structure is destroyed, not just re-cut.
    destroys=_ANY_TEXT | _RAZES_LAYOUT | frozenset({
        "prose.paragraph_multiset", "prose.paragraph_sequence",
        "prose.sentence_multiset", "prose.sentence_sequence",
        "doc.chunk_multiset",
    }))

FLATTEN_HEADINGS = Perturbation(
    "flatten_headings", "heading hierarchy (levels, not titles)",
    _flatten_headings, seeded=False,
    # Every ATX heading becomes level 1: depth and branching collapse while
    # words, chunks, section boundaries and the block-kind mix all survive.
    destroys=_ANY_TEXT | frozenset({
        "doc.bytes", "doc.heading_level_sequence",
    }))
STRIP_HEADINGS = Perturbation(
    "strip_headings", "heading existence",
    _strip_headings, seeded=False,
    # Titles become plain paragraph lines: the level sequence empties, sections
    # stop existing, the kind mix shifts toward prose, and paragraph units
    # change. The word multiset survives because heading text participates in
    # prose statistics either way.
    destroys=_ANY_TEXT | frozenset({
        "doc.bytes", "doc.heading_level_sequence", "doc.section_word_counts",
        "doc.block_kind_multiset",
        "prose.paragraph_multiset", "prose.paragraph_sequence",
    }))
EQUALIZE_SECTIONS = Perturbation(
    "equalize_sections", "section-size unevenness",
    _equalize_sections, seeded=False,
    # Heading order and levels survive; the deal of material does not. Pooled
    # material is rejoined with spaces, so paragraph, chunk, sentence and
    # block-kind structure is destroyed as a side effect, alongside the
    # unevenness.
    destroys=_ANY_TEXT | frozenset({
        "doc.bytes", "doc.section_word_counts",
        "prose.paragraph_multiset", "prose.paragraph_sequence",
        "prose.sentence_multiset", "prose.sentence_sequence",
        "doc.chunk_multiset", "doc.block_kind_multiset",
    }))

LIBRARY: dict[str, Perturbation] = {
    p.name: p
    for p in (
        SHUFFLE_PARAGRAPHS, REVERSE_PARAGRAPHS,
        SHUFFLE_SENTENCES, REVERSE_SENTENCES,
        SCRAMBLE_WORDS, SCRAMBLE_IN_SENTENCE,
        DUPLICATE_DOCUMENT, LOWERCASE,
        WHITESPACE_NOISE, TRUNCATE_HALF,
        MERGE_PARAGRAPHS, RESPLIT_PARAGRAPHS,
        FLATTEN_HEADINGS, STRIP_HEADINGS, EQUALIZE_SECTIONS,
    )
}
