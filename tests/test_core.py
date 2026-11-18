"""
Document-model tests: parse invariants, then structure read from syntax.

The invariant section asserts three properties over a battery of adversarial
documents: the block tiling reproduces the source exactly, spans are ordered and
in bounds, and the prose projection never invents words. The structure section
asserts that structure comes from declared markdown syntax and is never
inferred: table rows are not headings, and a list of unpunctuated items yields
one sentence unit per item.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.core.blocks import BlockKind, parse_blocks  # noqa: E402
from isda.core.document import Document  # noqa: E402
from isda.core.features import (  # noqa: E402
    FEATURES, FeatureContext, UndeclaredFeature, UnknownFeature,
)
from isda.core.tokens import (  # noqa: E402
    WORD, paragraph_units, sections, sentence_units, word_spans, words,
)

BATTERY = {
    "plain": "One paragraph of ordinary prose. It has two sentences.",
    "empty": "",
    "blank-only": "\n\n\n",
    "no-trailing-newline": "# Title\n\nBody text",
    "crlf": "# Title\r\n\r\nFirst para.\r\n\r\nSecond para.\r\n",
    "frontmatter": "---\ntype: note\ntags: [a, b]\n---\n\n# Doc\n\nBody.\n",
    "atx-heading": "# One\n\n## Two words\n\ntext\n",
    "closed-atx": "## Title ##\n\ntext\n",
    "hashtag-not-heading": "#hashtag starts this paragraph.\n",
    "setext": "Title Line\n---\n\nBody paragraph.\n",
    "thematic-after-blank": "Para one.\n\n---\n\nPara two.\n",
    "table": "| Command | Purpose |\n|---|---|\n| a | does a |\n\nProse after.\n",
    "fence": "Before.\n\n```python\ncode_token = 1\n# not a heading\n```\n\nAfter.\n",
    "unclosed-fence": "Before.\n\n```\ncode to end of file\nmore code",
    "tilde-fence": "~~~\nfenced\n~~~\n\nProse.\n",
    "list": "- first item\n- second item\n- third item\n\nParagraph.\n",
    "ordered-list": "1. one\n2. two\n10) ten\n",
    "list-continuation": "- item text\n  continues here\n- next item\n",
    "blockquote": "> Quoted line one.\n> Quoted line two.\n\nPlain.\n",
    "comment": "<!-- hidden -->\n\nVisible prose.\n",
    "multiline-comment": "<!-- hidden\nstill hidden -->\n\nVisible.\n",
    "links": "See [the label](https://example.com/slug) and [[path/to/target|shown]].\n",
    "emphasis": "This is **bold** and *italic* and ***both***.\n",
    "inline-code": "Run `some --command` to start.\n",
    # U+2014 is written as an escape: the fixture needs a non-ASCII dash
    # between words, and it must not count as a word.
    "unicode": "Café naïveté \u2014 Übung macht den Meister.\n",
    "index-list": "# Index\n\n" + "\n".join(f"- item number {i}" for i in range(18)) + "\n",
}


# ---------- invariants ----------

@pytest.mark.parametrize("name", sorted(BATTERY))
def test_block_tiling_reproduces_source_exactly(name):
    """No text is dropped: the blocks' source slices concatenate to the source,
    so word counts can be audited against it."""
    source = BATTERY[name]
    blocks = parse_blocks(source)
    assert "".join(b.span.slice(source) for b in blocks) == source


@pytest.mark.parametrize("name", sorted(BATTERY))
def test_spans_are_ordered_and_in_bounds(name):
    source = BATTERY[name]
    blocks = parse_blocks(source)
    pos = 0
    for b in blocks:
        assert b.span.start == pos, f"gap or overlap before {b.kind} at {b.span.start}"
        assert b.span.start <= b.span.end <= len(source)
        pos = b.span.end
    if blocks:
        assert pos == len(source)


@pytest.mark.parametrize("name", sorted(BATTERY))
def test_prose_projection_never_invents_words(name):
    """Stripping never increases the word count."""
    source = BATTERY[name]
    doc = Document.parse(source)
    assert len(words(doc.prose_text)) <= len(WORD.findall(source.lower()))


@pytest.mark.parametrize("name", sorted(BATTERY))
def test_parse_is_total_and_deterministic(name):
    source = BATTERY[name]
    assert parse_blocks(source) == parse_blocks(source)


# ---------- headings are known exactly, not heuristically ----------

def kinds(source):
    return [b.kind for b in parse_blocks(source)]


def test_table_delimiter_row_is_not_a_heading():
    """A table delimiter row starts with a pipe and is a table by declaration; a
    capitalization heuristic would read table rows as section headings."""
    doc = Document.parse(BATTERY["table"])
    assert [h.content for h in doc.headings] == []
    assert BlockKind.TABLE in [b.kind for b in doc.blocks]


def test_setext_heading_vs_thematic_break():
    """`---` under a paragraph is a level-2 heading; after a blank it is a break."""
    setext = Document.parse(BATTERY["setext"])
    assert [(h.content, h.level) for h in setext.headings] == [("Title Line", 2)]
    thematic = Document.parse(BATTERY["thematic-after-blank"])
    assert thematic.headings == ()
    assert BlockKind.THEMATIC_BREAK in [b.kind for b in thematic.blocks]


def test_atx_heading_requires_the_space():
    assert Document.parse(BATTERY["hashtag-not-heading"]).headings == ()
    doc = Document.parse(BATTERY["atx-heading"])
    assert [(h.content, h.level) for h in doc.headings] == [("One", 1), ("Two words", 2)]


def test_closing_hashes_are_stripped():
    doc = Document.parse(BATTERY["closed-atx"])
    assert [h.content for h in doc.headings] == ["Title"]


def test_heading_inside_fence_is_code_not_heading():
    doc = Document.parse(BATTERY["fence"])
    assert doc.headings == ()


def test_frontmatter_is_not_prose_and_not_headings():
    doc = Document.parse(BATTERY["frontmatter"])
    assert [h.content for h in doc.headings] == ["Doc"]
    assert "tags" not in doc.prose_text


# ---------- prose exclusion semantics ----------

def test_fenced_code_is_excluded_even_unclosed():
    doc = Document.parse(BATTERY["unclosed-fence"])
    assert "code" not in doc.prose_text
    assert doc.prose_text == "Before."


def test_inline_markup_is_scrubbed_keeping_visible_text():
    doc = Document.parse(BATTERY["links"])
    assert "the label" in doc.prose_text and "shown" in doc.prose_text
    assert "example.com" not in doc.prose_text and "path/to" not in doc.prose_text
    emphasized = Document.parse(BATTERY["emphasis"]).prose_text
    assert "bold" in emphasized and "**" not in emphasized
    code = Document.parse(BATTERY["inline-code"]).prose_text
    assert "command" not in code


def test_comments_are_excluded():
    for name in ("comment", "multiline-comment"):
        assert "hidden" not in Document.parse(BATTERY[name]).prose_text


def test_unicode_words_count():
    """Word matching is Unicode-aware: `café` is a word and the dash is not."""
    doc = Document.parse(BATTERY["unicode"])
    assert "café" in words(doc.prose_text)
    assert len(words(doc.prose_text)) == 6


# ---------- block-aware tokenization ----------

def test_index_list_is_units_not_one_sentence():
    """An index of unpunctuated list items is one sentence unit per item, not one
    long sentence: splitting on terminal punctuation alone would merge them."""
    doc = Document.parse(BATTERY["index-list"])
    units = sentence_units(doc)
    assert len(units) == 19  # heading + 18 items
    assert max(len(u) for u in units) <= 4


def test_paragraphs_exclude_headings_and_list_items():
    doc = Document.parse(BATTERY["list"])
    assert paragraph_units(doc) == (("paragraph",),)


def test_sentences_split_within_paragraphs():
    doc = Document.parse(BATTERY["plain"])
    assert len(sentence_units(doc)) == 2


def test_sections_bucket_prose_under_headings():
    doc = Document.parse("intro\n\n# A\n\none\n\n# B\n\ntwo\n\nthree\n")
    got = [(label, len(units)) for label, units in sections(doc)]
    assert got == [("(preamble)", 1), ("A", 1), ("B", 2)]


def test_word_spans_are_in_bounds():
    text = "café one two"
    for start, end in word_spans(text):
        assert 0 <= start < end <= len(text)


# ---------- the feature context ----------

def test_unknown_feature_raises():
    ctx = FeatureContext(Document.parse("x"), frozenset(FEATURES))
    with pytest.raises(UnknownFeature):
        ctx.get("prose.paragarphs")


def test_undeclared_feature_raises_with_instruction():
    ctx = FeatureContext(Document.parse("x"), frozenset({"doc.bytes"}))
    with pytest.raises(UndeclaredFeature, match="requires"):
        ctx.get("prose.text")


def test_features_are_cached_per_document():
    doc = Document.parse("Some words here.\n\nMore words there.")
    a = FeatureContext(doc, frozenset({"prose.paragraph_multiset"}))
    b = FeatureContext(doc, frozenset({"prose.paragraph_multiset"}))
    assert a.get("prose.paragraph_multiset") is b.get("prose.paragraph_multiset")


def test_multiset_features_are_order_free():
    a = Document.parse("alpha beta.\n\ngamma delta.")
    b = Document.parse("gamma delta.\n\nalpha beta.")
    for feature in ("prose.word_multiset", "prose.paragraph_multiset",
                    "prose.sentence_multiset"):
        ca = FeatureContext(a, frozenset({feature}))
        cb = FeatureContext(b, frozenset({feature}))
        assert ca.get(feature) == cb.get(feature), feature


def test_every_feature_has_a_working_provider():
    """The registry validates requires against FEATURES, so every name must
    produce a value on an ordinary document."""
    doc = Document.parse(BATTERY["frontmatter"])
    ctx = FeatureContext(doc, frozenset(FEATURES))
    for name in FEATURES:
        ctx.get(name)  # must not raise


# ---------- combining marks ----------

def test_combining_marks_join_their_base_character():
    """UAX #29 WB4: Extend characters never break a word, in any script. Pointed
    Hebrew, Arabic with harakat, Devanagari and NFD-normalized Latin each
    tokenize into whole words."""
    import unicodedata
    cases = [
        ("בְּרֵאשִׁית "
         "בָּרָא", 2),          # pointed Hebrew
        ("بِسْمِ اللَّ"
         "هِ", 2),                                   # Arabic + harakat
        ("नमस्ते संसार", 2),  # Devanagari
        (unicodedata.normalize("NFD", "Tiếng Việt"), 2),  # NFD Latin
        ("café naïve", 2),                           # NFC Latin
        ("The quick brown fox", 4),                            # ASCII unchanged
    ]
    for text, expected in cases:
        assert len(words(text)) == expected, repr(text)


def test_a_stray_combining_mark_is_not_a_word():
    """A word may not start with a mark: a mark attaches to a base letter and
    never stands alone."""
    assert words("word, ́ next") == ("word", "next")


def test_dotted_capital_i_survives_lowercasing():
    """Turkish U+0130 lowercases to i plus a combining dot above, so a letter-run
    pattern that rejects combining marks splits one word into two."""
    assert len(words("İstanbul")) == 1
