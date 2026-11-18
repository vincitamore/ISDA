"""
Inventory measures: descriptions, not claims. A count cannot be wrong about a
construct because it claims none, so it owes no falsifier and no null model.

`inventory.prose-word-count` is the measure behind the standing
`nonascii-word-coverage` specimen assertion on non-ASCII tokenizer coverage.
Word matching is Unicode-aware: under an ASCII-only word class no word
boundary exists between `f` and `é`, and `café` would match nothing. Every
word containing a non-ASCII letter would then count as zero words, which
biases every downstream figure against texts that use such letters.
"""

from __future__ import annotations

from typing import cast

from ..core.features import FeatureContext
from ..kernel.descriptor import Kind, MeasureDescriptor, Status
from ..kernel.registry import register


def prose_word_count(ctx: FeatureContext) -> float | None:
    words = cast(tuple[str, ...], ctx.get("prose.word_sequence"))
    return float(len(words)) if words else None


PROSE_WORD_COUNT = register(MeasureDescriptor(
    id="inventory.prose-word-count",
    version="1.0.0",
    construct=(
        "The number of word tokens in the document's prose view, markup "
        "excluded. An inventory count, not a stratum measure."
    ),
    requires=("prose.word_sequence",),
    kind=Kind.DESCRIPTION,
    compute=prose_word_count,
    strata=(),
    status=Status.ACTIVE,
    interpretation=(
        "Unicode-aware: a word containing non-ASCII letters counts as a word. "
        "On space-delimited scripts this tracks the whitespace-token count to "
        "within a few percent; a large gap indicates the tokenizer is dropping "
        "words."
    ),
))
