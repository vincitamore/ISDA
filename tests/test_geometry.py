"""
Shape-layer unit tests: the features and perturbations behave as declared
on documents small enough to check by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.core.document import Document  # noqa: E402
from isda.core.features import FeatureContext  # noqa: E402
from isda.kernel.perturb import (  # noqa: E402
    EQUALIZE_SECTIONS, FLATTEN_HEADINGS, STRIP_HEADINGS,
)
from isda.measures.geometry import (  # noqa: E402
    block_kind_entropy, heading_branching, heading_tree_depth,
    section_size_dispersion, skipped_heading_levels,
)

DOC = """# Title

Alpha beta gamma delta epsilon.

## First

One two three four five six seven eight nine ten.

### Deep

Just three words.

## Second

Two words.
"""


def _ctx(text: str, *requires: str) -> FeatureContext:
    return FeatureContext(Document.parse(text), frozenset(requires))


def test_heading_features_read_the_hand_checked_values():
    assert heading_tree_depth(_ctx(DOC, "doc.heading_level_sequence")) == 3.0
    # Title parents First+Second (2 children); First parents Deep (1).
    assert heading_branching(_ctx(DOC, "doc.heading_level_sequence")) == 1.5
    assert skipped_heading_levels(_ctx(DOC, "doc.heading_level_sequence")) == 0.0
    assert skipped_heading_levels(_ctx("# A\n\n### B\n\nx.\n",
                                       "doc.heading_level_sequence")) == 1.0


def test_headingless_documents_abstain_rather_than_zero():
    assert heading_tree_depth(_ctx("Plain prose only.\n",
                                   "doc.heading_level_sequence")) is None
    assert section_size_dispersion(_ctx("Plain prose only.\n",
                                        "doc.section_word_counts")) is None


def test_section_word_counts_exclude_heading_text():
    ctx = _ctx(DOC, "doc.section_word_counts")
    assert ctx.get("doc.section_word_counts") == (5, 10, 3, 2)


def test_flatten_headings_collapses_depth_and_nothing_else():
    flat = FLATTEN_HEADINGS.apply(DOC, 0)
    assert heading_tree_depth(_ctx(flat, "doc.heading_level_sequence")) == 1.0
    # Same words, same section boundaries: counts survive re-levelling.
    assert _ctx(flat, "doc.section_word_counts").get("doc.section_word_counts") \
        == (5, 10, 3, 2)


def test_strip_headings_removes_the_outline_entirely():
    stripped = STRIP_HEADINGS.apply(DOC, 0)
    assert heading_tree_depth(_ctx(stripped, "doc.heading_level_sequence")) is None


def test_equalize_sections_zeroes_dispersion_and_keeps_the_outline():
    before = section_size_dispersion(_ctx(DOC, "doc.section_word_counts"))
    assert before is not None and before > 0.5  # (5, 10, 3, 2) is uneven
    dealt = EQUALIZE_SECTIONS.apply(DOC, 0)
    after = section_size_dispersion(_ctx(dealt, "doc.section_word_counts"))
    assert after is not None and after <= 0.25  # 20 words into 4 sections
    assert heading_tree_depth(_ctx(dealt, "doc.heading_level_sequence")) == 3.0


def test_entropy_reads_mix_not_content():
    prose_only = "One paragraph.\n\nAnother paragraph.\n\nA third.\n"
    mixed = "# H\n\nProse here.\n\n- item one\n- item two\n\n```\ncode\n```\n"
    e_prose = block_kind_entropy(_ctx(prose_only, "doc.block_kind_multiset"))
    e_mixed = block_kind_entropy(_ctx(mixed, "doc.block_kind_multiset"))
    assert e_prose == 0.0
    assert e_mixed is not None and e_mixed > 1.0
