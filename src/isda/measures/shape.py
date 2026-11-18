"""
Shape and lexical measures, with the retirement record of one lexical measure.

- `shape.chunk-length-median` reads the size of blank-line-delimited layout
  chunks, list items and headings included. It carries the genre-discrimination
  claim, which it passes at power on block B (working markdown): omega-squared
  0.125, p = 5e-4, against a label-noise floor of 0.055. The gate results for
  both measures are in corpus/exhibits/shape.json.

- `shape.paragraph-length-median` reads the size of prose paragraphs from the
  shared parse. Its construct declarations pass and it makes no
  genre-discrimination claim: prose-paragraph size does not separate genres at
  power (omega-squared 0.0125, p = 0.17). It is a separate measure from the
  chunk measure because the two read different quantities. A paragraph measure
  computed over raw blank-line splits would read layout chunks under a prose
  name, and the genre signal sits on the layout side (list-heavy genres
  against prose genres), not in prose paragraphs.

- `arithmetica.content-word-ratio` is retired. A global word scramble destroys
  every proposition and preserves the word multiset it counts, so it cannot be
  reading propositions; it is a lexical register statistic. It stays
  registered, marked retired, with its record. The admission rule catches its
  false declaration statically: `scramble_words` preserves the word multiset,
  the only feature it reads, so registering it as non-retired fails at
  registration rather than after a measurement run.

All measures read the document through the fail-closed FeatureContext: they
declare what they read in `requires`, and the context serves nothing else.
"""

from __future__ import annotations

import statistics
from typing import cast

from ..core.features import FeatureContext
from ..kernel.descriptor import (
    DiscriminationClaim, Kind, MeasureDescriptor, NullModel, Status,
)
from ..kernel.perturb import (
    DUPLICATE_DOCUMENT, LOWERCASE, MERGE_PARAGRAPHS, RESPLIT_PARAGRAPHS,
    SCRAMBLE_WORDS, SHUFFLE_PARAGRAPHS, WHITESPACE_NOISE,
)
from ..kernel.registry import register

STOPWORDS = frozenset("""
a an the am is are was were be been being have has had having do does did doing done
will would shall should can could may might must ought i me my mine myself you your
yours he him his she her hers it its we us our ours they them their theirs this that
these those who whom whose which what and or but nor yet so for if then else when
where while as because though although since unless until whether some any all every
each no none many much more most few several such of in on at to from by with about
into onto upon over under through between among against before after during without
within not only even also just very too there here now
""".split())


def paragraph_length_median(ctx: FeatureContext) -> float | None:
    """Median words per prose paragraph. Reads document shape, not content."""
    paragraphs = cast(tuple[tuple[str, ...], ...], ctx.get("prose.paragraph_multiset"))
    lengths = [len(words) for words in paragraphs if words]
    return float(statistics.median(lengths)) if lengths else None


def chunk_length_median(ctx: FeatureContext) -> float | None:
    """Median words per blank-line-delimited layout chunk."""
    chunks = cast(tuple[tuple[str, ...], ...], ctx.get("doc.chunk_multiset"))
    lengths = [len(words) for words in chunks if words]
    return float(statistics.median(lengths)) if lengths else None


def content_word_ratio(ctx: FeatureContext) -> float | None:
    """Fraction of tokens that are not function words; not propositional density."""
    words = cast(tuple[str, ...], ctx.get("prose.word_multiset"))
    if not words:
        return None
    return sum(1 for w in words if w not in STOPWORDS) / len(words)


PARAGRAPH_LENGTH_MEDIAN = register(MeasureDescriptor(
    id="shape.paragraph-length-median",
    version="2.0.0",
    construct=(
        "The typical size of the author's prose paragraph: how much material is "
        "packed between paragraph breaks in running prose, headings and list items "
        "excluded. A shape property of the document, independent of what the words "
        "say."
    ),
    requires=("prose.paragraph_multiset",),
    kind=Kind.CLAIM,
    compute=paragraph_length_median,
    # The construct is the size of the compositional unit, so its falsifiers
    # are the perturbations that move its boundaries: merging them away, or
    # re-cutting them at random.
    #
    # `truncate_half` cannot falsify it: a median over a random half of a
    # homogeneous population is approximately the same median, so this measure
    # survives truncation by arithmetic.
    must_move_under=(MERGE_PARAGRAPHS, RESPLIT_PARAGRAPHS),
    must_not_move_under=(SHUFFLE_PARAGRAPHS, LOWERCASE, WHITESPACE_NOISE),
    null=NullModel(
        kind="permutation",
        derived_from=(
            "documents with paragraph boundaries removed, so no compositional unit "
            "exists to measure (not from the distribution of the corpus being judged)"
        ),
    ),
    # No DiscriminationClaim: tested at power on block B (n = 198, k = 7,
    # label-noise floor 0.051), prose-paragraph size does not separate genres
    # (omega-squared 0.0125, p = 0.17). The genre signal sits in layout chunks;
    # see shape.chunk-length-median, which carries the claim.
    strata=("geometria",),
    status=Status.ACTIVE,
    interpretation=(
        "Valid as a construct (its falsifiers move it, its invariances hold) and "
        "not a genre discriminator: prose-paragraph size is close to constant "
        "across the seven block B genres (omega-squared 0.0125, p = 0.17, "
        "n = 198). The genre signal belongs to layout chunks, which "
        "shape.chunk-length-median reads."
    ),
))


CHUNK_LENGTH_MEDIAN = register(MeasureDescriptor(
    id="shape.chunk-length-median",
    version="1.0.0",
    construct=(
        "The typical size of the author's layout chunk: how much material sits "
        "between blank lines, counting list items, headings and prose alike. A "
        "property of how the author breaks the page, not of what the words say."
    ),
    requires=("doc.chunk_multiset",),
    kind=Kind.CLAIM,
    compute=chunk_length_median,
    must_move_under=(MERGE_PARAGRAPHS, RESPLIT_PARAGRAPHS),
    must_not_move_under=(SHUFFLE_PARAGRAPHS, LOWERCASE, WHITESPACE_NOISE),
    null=NullModel(
        kind="permutation",
        derived_from=(
            "documents with blank-line boundaries removed, so no layout chunk "
            "exists to measure (not from the distribution of the corpus being judged)"
        ),
    ),
    discrimination=DiscriminationClaim(groups_by="genre", min_omega_squared=0.10),
    strata=("geometria",),
    status=Status.ACTIVE,
    interpretation=(
        "Separates the seven block B genres: omega-squared 0.125 (p = 5e-4, "
        "label-noise floor 0.055, n = 198) against the 0.10 discrimination "
        "gate. Prose-heavy genres run long chunks, list-heavy genres run "
        "short ones."
    ),
))


CONTENT_WORD_RATIO = register(MeasureDescriptor(
    id="arithmetica.content-word-ratio",
    version="2.0.0",
    construct=(
        "Fraction of tokens carrying lexical content rather than grammatical function: "
        "a lexical register statistic, not a measure of propositional density."
    ),
    requires=("prose.word_multiset",),
    kind=Kind.CLAIM,
    compute=content_word_ratio,
    # Declared falsifier: scramble_words. The declaration is false: scrambling
    # preserves the word multiset, the only feature the measure reads. The
    # admission rule refuses this shape for non-retired measures, so the
    # retired row keeps the declaration unmodified as the record.
    must_move_under=(SCRAMBLE_WORDS,),
    must_not_move_under=(DUPLICATE_DOCUMENT,),
    null=NullModel(
        kind="synthetic",
        derived_from="text drawn from the function-word list alone, giving a ratio near zero",
    ),
    strata=("arithmetica",),
    status=Status.RETIRED,
    retired_because=(
        "Invariant under a global word scramble, so it cannot be reading propositions: "
        "the scramble destroys every proposition and preserves the word multiset the "
        "measure counts. It is a content-word ratio, a lexical register statistic."
    ),
    interpretation=(
        "Retained as a retirement record. The quantity is well defined and varies by "
        "register; it is not a stratum measure."
    ),
))
