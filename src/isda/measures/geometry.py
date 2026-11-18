"""
The Geometria shape layer: document architecture read mechanically.

The measures here read the sectioning skeleton and the page's material mix.
Each status below is set from measured evidence on block B (working markdown;
198 documents, seven genres), recorded in corpus/exhibits/shape.json by
scripts/gate-shape.py. The gates are: omega-squared >= 0.10 at p < 0.01 with
the detectability floor stated (the omega-squared that label noise alone
reaches at this n and k) for a genre-discrimination claim; |rho| <= 0.90
against every admitted feature (redundancy); and |rho| <= 0.50 against markup
fraction (a measure that tracks markup is reading markup). Normalised moves
are fractions of the between-document interquartile spread (see
kernel/registry._spread).

- heading-tree-depth: the construct test passes (flatten moves it 1.0 of
  spread). Omega-squared is 0.0883, below 0.10 at power (p = 0.001, floor
  0.051), so it is active and no discrimination claim is made.
- heading-branching: the construct test passes (flatten moves it 1.67 of
  spread). No genre signal at power (omega-squared 0.0079, p = 0.28): active,
  with no genre claim.
- section-size-dispersion: omega-squared 0.2276 (p = 5e-4, floor 0.064), the
  strongest shape discriminator measured on block B. Its falsifier is
  EQUALIZE_SECTIONS, which drives it toward the declared null of 0 (a median
  move of 0.82 of spread; the corpus median falls from 0.86 to 0.12). A
  paragraph shuffle moves it further (1.54 of spread) but upward, to a median
  of 2.15: a random deal of the material is more uneven than the authored
  one, so a shuffle does not remove what the measure reads.
- block-kind-entropy: the construct test passes (merge moves it 1.47 of
  spread). Omega-squared is 0.1448 (p = 5e-4, floor 0.051), but rho against
  markup fraction is +0.53, over the 0.50 limit, and on the residuals of a
  fit against markup fraction the separation is 0.0998, under 0.10. It is
  active and no discrimination claim is made: its genre separation cannot be
  told apart from the share of the page that is markup. Shuffle invariance is
  not claimed either: block kinds depend on position (shuffled frontmatter
  stops being frontmatter), and a shuffle moves it 0.0502 of spread, above
  the 0.05 limit for a perturbation that must not move it.
- skipped-heading-levels: omega-squared 0.2027 (p = 5e-4, floor 0.059) as a
  description. The count cannot be wrong; the discrimination claim is the
  tested assertion, and its null is the label permutation.

Redundancy: the largest |rho| among these five measures is 0.424 (depth
against dispersion), far below the 0.90 limit.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import cast

from ..core.features import FeatureContext
from ..kernel.descriptor import (
    DiscriminationClaim, Kind, MeasureDescriptor, NullModel, Status,
)
from ..kernel.perturb import (
    EQUALIZE_SECTIONS, FLATTEN_HEADINGS, LOWERCASE, MERGE_PARAGRAPHS,
    SHUFFLE_PARAGRAPHS, WHITESPACE_NOISE,
)
from ..kernel.registry import register


def heading_tree_depth(ctx: FeatureContext) -> float | None:
    """Deepest heading level in use; None for headingless documents."""
    levels = cast(tuple[int, ...], ctx.get("doc.heading_level_sequence"))
    return float(max(levels)) if levels else None


def heading_branching(ctx: FeatureContext) -> float | None:
    """
    Mean children per parent heading, parents being headings with at least one
    child. A child is a subsequent deeper heading before the next heading at
    the parent's level or shallower. Flat documents (no nesting) read 0.0;
    documents with fewer than two headings read None, since branching needs a
    tree.
    """
    levels = cast(tuple[int, ...], ctx.get("doc.heading_level_sequence"))
    if len(levels) < 2:
        return None
    counts = [0] * len(levels)
    stack: list[tuple[int, int]] = []  # (index, level)
    for i, lv in enumerate(levels):
        while stack and stack[-1][1] >= lv:
            stack.pop()
        if stack:
            counts[stack[-1][0]] += 1
        stack.append((i, lv))
    parents = [c for c in counts if c > 0]
    return float(sum(parents) / len(parents)) if parents else 0.0


def section_size_dispersion(ctx: FeatureContext) -> float | None:
    """
    Relative spread of section sizes: IQR over median of words-per-section.
    None below three sections or on a zero median, where the dispersion is
    undefined rather than 0.
    """
    sizes = cast(tuple[int, ...], ctx.get("doc.section_word_counts"))
    if len(sizes) < 3:
        return None
    med = statistics.median(sizes)
    if med <= 0:
        return None
    q1, _, q3 = statistics.quantiles(sizes, n=4, method="inclusive")
    return float((q3 - q1) / med)


def block_kind_entropy(ctx: FeatureContext) -> float | None:
    """
    Shannon entropy (bits) of the non-blank block-kind distribution: how mixed
    the page's material is between prose, headings, lists, tables, code.
    """
    kinds = cast(tuple[str, ...], ctx.get("doc.block_kind_multiset"))
    if not kinds:
        return None
    total = len(kinds)
    ent = -sum((n / total) * math.log2(n / total)
               for n in Counter(kinds).values())
    # A single-kind document yields -0.0 (IEEE negation of a zero sum); emit
    # the positive zero so pins and JSON carry one canonical representation.
    return ent + 0.0


HEADING_TREE_DEPTH = register(MeasureDescriptor(
    id="shape.heading-tree-depth",
    version="1.0.0",
    construct=(
        "How deep the document's sectioning hierarchy nests: the deepest "
        "heading level in use. A property of the outline's shape, independent "
        "of what any section says."
    ),
    requires=("doc.heading_level_sequence",),
    kind=Kind.CLAIM,
    compute=heading_tree_depth,
    must_move_under=(FLATTEN_HEADINGS,),
    must_not_move_under=(SHUFFLE_PARAGRAPHS, LOWERCASE, WHITESPACE_NOISE),
    null=NullModel(
        kind="synthetic",
        derived_from=(
            "documents with every heading flattened to level 1, where depth "
            "is 1 by construction (not from the corpus being judged)"
        ),
    ),
    strata=("geometria",),
    status=Status.ACTIVE,
    # No DiscriminationClaim: tested at power on block B, it misses the gate
    # (omega-squared 0.0883, p = 0.001, floor 0.051). A valid construct that is
    # not a genre discriminator, as with shape.paragraph-length-median.
    interpretation=(
        "Depth of the outline. Reordering sections cannot move it (the level "
        "multiset survives a shuffle); only re-levelling can. On block B, "
        "omega-squared is 0.0883 (p = 0.001, label-noise floor 0.051), below "
        "the 0.10 discrimination gate, so no genre claim is carried."
    ),
))


HEADING_BRANCHING = register(MeasureDescriptor(
    id="shape.heading-branching",
    version="1.0.0",
    construct=(
        "How wide the outline fans: mean immediate subsections per sectioning "
        "heading that has any. Flat outlines read 0."
    ),
    requires=("doc.heading_level_sequence",),
    kind=Kind.CLAIM,
    compute=heading_branching,
    must_move_under=(FLATTEN_HEADINGS,),
    must_not_move_under=(LOWERCASE, WHITESPACE_NOISE),
    null=NullModel(
        kind="synthetic",
        derived_from=(
            "documents with every heading flattened to level 1, where no "
            "parent-child relation exists and branching is 0 by construction"
        ),
    ),
    strata=("geometria",),
    status=Status.ACTIVE,
    # No DiscriminationClaim: no genre signal at power (omega-squared 0.0079,
    # p = 0.28, floor 0.058). The construct test passes: flatten moves it 1.67
    # of interquartile spread.
    interpretation=(
        "Fan-out of the outline tree, read beside depth: a deep narrow tree "
        "and a shallow wide one differ at the same heading count. Carries no "
        "genre claim: omega-squared is 0.0079 at power (p = 0.28, block B). "
        "Order-invariance is not claimed: a paragraph shuffle reorders the "
        "level sequence and re-parents subtrees."
    ),
))


SECTION_SIZE_DISPERSION = register(MeasureDescriptor(
    id="shape.section-size-dispersion",
    version="1.0.0",
    construct=(
        "How unevenly material is distributed across sections: interquartile "
        "range over median of words-per-section. Uniform sectioning reads "
        "near 0; a page with one giant section among stubs reads high."
    ),
    requires=("doc.section_word_counts",),
    kind=Kind.CLAIM,
    compute=section_size_dispersion,
    # The falsifier is equalize_sections, not shuffle_paragraphs. Equalizing
    # drives the measure toward the declared null of 0 (0.82 of spread on
    # block B). A shuffle moves it too (1.54 of spread) but upward, since a
    # random deal is more uneven than an authored one, so it does not remove
    # the unevenness the construct names.
    must_move_under=(EQUALIZE_SECTIONS,),
    must_not_move_under=(LOWERCASE, WHITESPACE_NOISE),
    null=NullModel(
        kind="synthetic",
        derived_from=(
            "documents with material dealt equally across their headings, "
            "where dispersion is 0 by construction (not the judged corpus's "
            "own distribution)"
        ),
    ),
    discrimination=DiscriminationClaim(groups_by="genre", min_omega_squared=0.10),
    strata=("geometria",),
    status=Status.ACTIVE,
    interpretation=(
        "Evenness of the sectioning: how the author budgets material, not "
        "what the material says. The strongest shape discriminator measured "
        "on block B: omega-squared 0.2276 (p = 5e-4, label-noise floor 0.064, "
        "n = 157 of 198; the measure abstains below three sections or on a "
        "zero median)."
    ),
))


BLOCK_KIND_ENTROPY = register(MeasureDescriptor(
    id="shape.block-kind-entropy",
    version="1.0.0",
    construct=(
        "How mixed the page's material is: Shannon entropy of the non-blank "
        "block-kind distribution (prose, headings, list items, tables, code "
        "fences). Pure prose reads near 0; working documentation that "
        "alternates kinds reads high."
    ),
    requires=("doc.block_kind_multiset",),
    kind=Kind.CLAIM,
    compute=block_kind_entropy,
    # Collapsing blank lines merges the mix into one prose mass, so entropy
    # falls toward 0 for any document that had a mix at all. Shuffle
    # invariance is not claimed: block kinds depend on position (shuffled
    # frontmatter stops being frontmatter), and a shuffle moves the entropy
    # 0.0502 of spread, above the 0.05 limit for a must-not-move perturbation.
    must_move_under=(MERGE_PARAGRAPHS,),
    must_not_move_under=(LOWERCASE, WHITESPACE_NOISE),
    null=NullModel(
        kind="synthetic",
        derived_from=(
            "merged documents collapsed to a single prose block, where the "
            "kind distribution is degenerate and entropy is near 0 by "
            "construction"
        ),
    ),
    strata=("geometria",),
    status=Status.ACTIVE,
    interpretation=(
        "Material mix of the page. No genre claim is registered: it differs "
        "across block B genres (omega-squared 0.1448, p = 5e-4, label-noise "
        "floor 0.051), but rho against markup fraction is +0.53, over the "
        "0.50 limit, and with markup fraction fitted out the separation is "
        "0.0998, under the 0.10 a claim needs."
    ),
))


def skipped_heading_levels(ctx: FeatureContext) -> float | None:
    """Count of heading transitions that skip a level downward (H2 to H4)."""
    levels = cast(tuple[int, ...], ctx.get("doc.heading_level_sequence"))
    if not levels:
        return None
    return float(sum(1 for a, b in zip(levels, levels[1:]) if b - a >= 2))


SKIPPED_HEADING_LEVELS = register(MeasureDescriptor(
    id="shape.skipped-heading-levels",
    version="1.0.0",
    construct=(
        "How often the outline skips levels on the way down: a count of "
        "heading transitions that deepen by two or more. An inventory of "
        "outline discipline; most documents count 0."
    ),
    requires=("doc.heading_level_sequence",),
    # A description: the count cannot be wrong, and it cannot pass a
    # median-normalised falsifier test on block B (the median document has no
    # skipped level to destroy; flattening moves only the skip-carrying tail).
    # What it claims, that the count separates genres, is the discrimination
    # claim below, whose falsifier is the label permutation in the standing
    # gate.
    kind=Kind.DESCRIPTION,
    compute=skipped_heading_levels,
    discrimination=DiscriminationClaim(groups_by="genre", min_omega_squared=0.10),
    strata=("geometria",),
    status=Status.ACTIVE,
    interpretation=(
        "Outline discipline by genre: omega-squared 0.2027 (p = 5e-4, "
        "label-noise floor 0.059) on block B; informal genres skip levels, "
        "curated ones do not. Read as a count, not a quality score."
    ),
))
