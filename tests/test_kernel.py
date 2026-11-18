"""
Kernel tests.

Most of these are negative tests: they assert that bad contracts are rejected
and that invariant measures fail. A harness that has only been shown to pass
good measures has not been shown to work, because a measure that reads the wrong
thing also looks like a passing measure unless a check is able to fail it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.core.features import FeatureContext, UndeclaredFeature  # noqa: E402
from isda.kernel import perturb  # noqa: E402
from isda.kernel.descriptor import (  # noqa: E402
    Kind, MeasureDescriptor, NullModel, Status,
)
from isda.kernel.registry import (  # noqa: E402
    clear, register, restore, snapshot, verify,
)

WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

CORPUS = [
    "Alpha beta gamma delta.\n\nEpsilon zeta eta theta iota kappa.\n\nLambda mu nu.",
    "One two.\n\nThree four five six seven eight nine ten eleven twelve.\n\nThirteen.",
    "Short.\n\nA considerably longer paragraph with many more words than the others here.",
    "Solo paragraph only, of middling length, with a handful of words in it.",
]


@pytest.fixture(autouse=True)
def _clean_registry():
    """Isolate each test in an empty registry, then restore what was there.

    Clearing without restoring removes the import-time registrations for every
    test that runs after this file: the re-import that would re-register never
    runs, because Python caches the module."""
    saved = snapshot()
    clear()
    yield
    restore(saved)


def _bytes_measure(ctx: FeatureContext) -> float:
    return float(cast(int, ctx.get("doc.bytes")))


def _d(**kw) -> MeasureDescriptor:
    base = dict(
        id="t.measure", version="1.0.0", construct="a test construct",
        requires=("doc.bytes",), kind=Kind.CLAIM, compute=_bytes_measure,
        must_move_under=(perturb.TRUNCATE_HALF,),
        null=NullModel(kind="synthetic", derived_from="empty input"),
    )
    base.update(kw)
    return MeasureDescriptor(**base)  # type: ignore[arg-type]


# ---------- the admission rule ----------

def test_claim_without_falsifier_is_rejected():
    """The admission rule: a CLAIM with no falsifier is refused."""
    with pytest.raises(ValueError, match="must name at least one perturbation"):
        _d(must_move_under=())


def test_claim_without_null_is_rejected():
    with pytest.raises(ValueError, match="must declare a null model"):
        _d(null=None)


def test_description_needs_no_falsifier():
    """A byte count cannot be wrong, so it owes no falsifier."""
    d = _d(kind=Kind.DESCRIPTION, must_move_under=(), null=None)
    assert d.kind is Kind.DESCRIPTION


def test_construct_is_required():
    with pytest.raises(ValueError, match="construct is required"):
        _d(construct="   ")


def test_contradictory_declarations_rejected():
    with pytest.raises(ValueError, match="both must-move and must-not-move"):
        _d(must_move_under=(perturb.TRUNCATE_HALF,),
           must_not_move_under=(perturb.TRUNCATE_HALF,))


def test_retired_measure_must_say_why():
    with pytest.raises(ValueError, match="must record why"):
        _d(status=Status.RETIRED, retired_because="")


def test_claim_with_empty_requires_is_rejected():
    """A measure that reads nothing is a constant; the falsifier check needs
    the declaration to have anything to check against."""
    with pytest.raises(ValueError, match="declare what it reads"):
        register(_d(requires=()))


def test_unknown_feature_in_requires_is_rejected():
    """`requires` is validated: a typo fails at registration, not at first use."""
    with pytest.raises(ValueError, match="unknown feature"):
        register(_d(requires=("doc.paragarphs",)))


def test_falsifier_that_cannot_touch_declared_features_is_rejected():
    """
    If every declared falsifier preserves everything the measure is allowed to
    read, the declaration is a test that cannot fire. Reordering perturbations
    cannot move a measure that reads only the word multiset.
    """
    with pytest.raises(ValueError, match="no declared falsifier destroys"):
        register(_d(requires=("prose.word_multiset",),
                    must_move_under=(perturb.SHUFFLE_PARAGRAPHS, perturb.SCRAMBLE_WORDS)))


def test_order_measure_with_reordering_falsifier_is_admitted():
    """
    Conversely, reordering perturbations preserve content because they destroy
    order, so they are the right falsifiers for an order-reading measure and
    must be admitted for one.
    """
    def first_word_position(ctx: FeatureContext) -> float:
        seq = cast(tuple[str, ...], ctx.get("prose.word_sequence"))
        return float(len(seq[0])) if seq else 0.0

    d = register(_d(id="t.order", requires=("prose.word_sequence",),
                    compute=first_word_position,
                    must_move_under=(perturb.SHUFFLE_PARAGRAPHS, perturb.SCRAMBLE_WORDS)))
    assert d.id == "t.order"


def test_scramble_words_cannot_falsify_a_word_multiset_measure():
    """
    scramble_words preserves the word multiset, so declaring it as the only
    falsifier of a measure that reads that multiset is refused at registration,
    without a measurement run. A RETIRED measure may keep such a declaration as
    a record (next test); a measure with any other status may not.
    """
    with pytest.raises(ValueError, match="no declared falsifier destroys"):
        register(_d(id="t.multiset-reader", requires=("prose.word_multiset",),
                    must_move_under=(perturb.SCRAMBLE_WORDS,)))


def test_retired_measure_keeps_its_false_declaration_as_record():
    d = register(_d(id="t.retired", requires=("prose.word_multiset",),
                    must_move_under=(perturb.SCRAMBLE_WORDS,),
                    status=Status.RETIRED, retired_because="the record"))
    assert d.status is Status.RETIRED


def test_duplicate_id_rejected():
    register(_d())
    with pytest.raises(ValueError, match="duplicate measure id"):
        register(_d())


# ---------- the harness must be able to fail ----------

def test_invariant_measure_fails_its_own_must_move():
    """A constant cannot move, so its must-move declaration is false."""
    d = register(_d(id="t.constant", compute=lambda ctx: 1.0))
    v = verify(d, CORPUS)
    assert not v.passed
    assert v.errors or any("invariant under destruction" in r.reason for r in v.results)


def test_confounded_measure_fails_its_must_not_move():
    """A measure claiming shape-independence while reading raw length."""
    d = register(_d(
        id="t.confounded",
        must_move_under=(perturb.TRUNCATE_HALF,),
        must_not_move_under=(perturb.WHITESPACE_NOISE,),
    ))
    v = verify(d, CORPUS)
    bad = [r for r in v.results if r.expectation == "must_not_move" and not r.passed]
    assert bad and "does not claim to read" in bad[0].reason


def test_zero_spread_is_untestable_not_failing():
    """
    A corpus on which the measure has no spread is a corpus gap, not a failing
    measure: the normalised delta is undefined, and forcing a ratio out of it
    would turn noise into a verdict.
    """
    d = register(_d(id="t.flat", compute=lambda ctx: 1.0))
    v = verify(d, ["same", "same"])
    assert any("untestable-on-corpus" in e for e in v.errors)


def test_measure_reading_undeclared_feature_fails_in_harness():
    """
    The fail-closed context is exercised by the harness itself: a measure whose
    code reads past its declaration fails on the corpus, before it can ship.
    """
    def overreaching(ctx: FeatureContext) -> float:
        return float(len(cast(str, ctx.get("prose.text"))))  # not declared

    d = register(_d(id="t.overreach", compute=overreaching))
    v = verify(d, CORPUS)
    assert v.errors and "UndeclaredFeature" in v.errors[0]


def test_feature_context_fails_closed_directly():
    from isda.core.document import Document

    ctx = FeatureContext(Document.parse("Some words here."), frozenset({"doc.bytes"}))
    with pytest.raises(UndeclaredFeature):
        ctx.get("prose.text")


# ---------- perturbation library properties ----------

def test_reverse_is_not_shuffle():
    """
    A statistic over adjacent pairs is exactly invariant under reversal, because
    reversal preserves the unordered pair set, while it moves under shuffling.
    Shuffle alone would therefore pass a measure that is blind to direction.
    """
    text = "\n\n".join(f"Paragraph {i} with some words." for i in range(8))

    def adjacent_pair_signature(t: str) -> float:
        paras = [p for p in re.split(r"\n\s*\n", t) if p.strip()]
        lens = [len(WORD.findall(p)) for p in paras]
        return float(sum(abs(a - b) for a, b in zip(lens, lens[1:])))

    base = adjacent_pair_signature(text)
    rev = adjacent_pair_signature(perturb.REVERSE_PARAGRAPHS.apply(text, 0))
    assert rev == base, "reversal must preserve a symmetric adjacency statistic"


def test_reordering_does_not_split_fenced_blocks():
    """
    A reorder that cuts through a code fence corrupts every downstream count, so
    a measure appears to move under its own null.
    """
    text = "Intro paragraph.\n\n```python\nline one\nline two\nline three\n```\n\nOutro paragraph."
    out = perturb.SHUFFLE_PARAGRAPHS.apply(text, 7)
    assert out.count("```") == 2
    assert "line one\nline two\nline three" in out


def test_scramble_words_preserves_the_multiset():
    """Preserving the multiset is why it cannot falsify a word-multiset measure."""
    text = "alpha beta gamma delta epsilon"
    out = perturb.SCRAMBLE_WORDS.apply(text, 3)
    assert sorted(out.split()) == sorted(text.split())


def test_destroys_rows_for_word_and_paragraph_multisets():
    """
    The admission rule depends on these rows most: no pure reordering may claim
    to destroy the word multiset, and the paragraph-boundary perturbations must
    claim the paragraph features. Those perturbations are whitespace-only edits,
    which a single global "multiset-preserving" label would misclassify.
    """
    for p in (perturb.SHUFFLE_PARAGRAPHS, perturb.REVERSE_PARAGRAPHS,
              perturb.SHUFFLE_SENTENCES, perturb.REVERSE_SENTENCES,
              perturb.SCRAMBLE_WORDS, perturb.SCRAMBLE_IN_SENTENCE):
        assert "prose.word_multiset" not in p.destroys, p.name
    for p in (perturb.MERGE_PARAGRAPHS, perturb.RESPLIT_PARAGRAPHS):
        assert "prose.paragraph_multiset" in p.destroys, p.name


def test_duplicate_document_cannot_move_order_statistics():
    """
    A proof, not a weak result: a duplicated multiset has the same median, so
    invariance under duplication is not evidence that a measure is robust.
    """
    import statistics as st
    text = "aa bb.\n\ncc dd ee ff.\n\ngg."
    med = lambda t: st.median(  # noqa: E731
        [len(WORD.findall(p)) for p in re.split(r"\n\s*\n", t) if p.strip()]
    )
    assert med(perturb.DUPLICATE_DOCUMENT.apply(text, 0)) == med(text)


def test_perturbations_are_deterministic():
    text = "\n\n".join(f"Para {i} here." for i in range(10))
    for p in perturb.LIBRARY.values():
        assert p.apply(text, 42) == p.apply(text, 42), f"{p.name} is not deterministic"


def test_null_derived_from_measured_corpus_is_rejected():
    """A null taken from the distribution it judges can never fire."""
    with pytest.raises(ValueError, match="cannot fire"):
        NullModel(kind="empirical-band",
                  derived_from="the interquartile range of the measured corpus")
