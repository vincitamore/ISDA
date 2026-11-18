"""
Astronomia: the shape of information over document position.

Trajectory is a property of order, so a trajectory measure has to move when
order is destroyed and again when direction is reversed. The second condition
is the stricter one: any statistic that sums over adjacent pairs is exactly
invariant under reversal, because reversal preserves the set of adjacent
pairs.

Both measures read one profile: mean per-token surprisal in each decile of
the document, taken over the prose view so that markup weight cannot register
as an arc.

- `surprisal-slope` is the least-squares slope of that profile against
  normalized position. It is signed: a reversed profile has the negated
  slope, where a magnitude would be reversal-invariant.
- `surprisal-peak-position` is the normalized position of the densest decile.
  A reversed profile peaks at 1 - p.

Reversing the paragraphs reverses the profile only approximately, because
each paragraph is then scored with different context before it.

A language model has least context at the start of any text, so mean
surprisal is raised in the first decile whatever the content (7.5 bits
against 6.3 to 6.8 in the other nine on block B, where half the documents
peak there), and the slope of a text with no arc tends negative, not zero.
The declared null is therefore the same document with its paragraphs
shuffled: it keeps the position effect and removes the arc.

Neither measure carries a genre claim. On block B (working markdown) both
differ across genres, and the slope also tracks document length; the gate
result is in corpus/exhibits/surprisal-trajectory.json.
"""

from __future__ import annotations

import math
from typing import cast

from ..core.features import FeatureContext
from ..kernel.descriptor import Kind, MeasureDescriptor, NullModel, Status
from ..kernel.perturb import REVERSE_PARAGRAPHS, SHUFFLE_PARAGRAPHS
from ..kernel.registry import register
from ._cache import HashCache

DECILES = 10

PARAMS: dict[str, object] = {
    "model": "gpt2",
    "revision": "607a30d783dfa663caf39e06633721c8d4cfcd7e",
    "window": 1024,
    "stride": 512,
    "bins": DECILES,
    "unit": "bits",
    "scope": "prose",
    "min_tokens": 60,  # below this a per-decile profile is noise, not a shape
}

# A separate cache file from Musica's: this row is a positional profile, that
# one a scalar summary, and one fingerprint cannot cover both shapes.
_cache = HashCache(
    "surprisal-profile-gpt2.json", PARAMS,
    "isda.measures.astronomia - derived state, keyed by content hash; delete "
    "freely, it rebuilds",
)


def _profile(text: str) -> list[float] | None:
    """Mean surprisal (bits) per decile of document position."""
    row = _cache.get(text)
    if row is not None:
        return None if not row else row

    from .musica import _backend  # pyright: ignore[reportPrivateUsage]
    torch, tok, model = _backend()

    ids: list[int] = list(tok(text)["input_ids"])
    if len(ids) < int(cast(int, PARAMS["min_tokens"])):
        _cache.put(text, [])
        return None

    window = int(cast(int, PARAMS["window"]))
    stride = int(cast(int, PARAMS["stride"]))
    surprisals: list[float] = []
    with torch.no_grad():
        start = 0
        while start < len(ids) - 1:
            end = min(start + window, len(ids))
            logits = model(torch.tensor([ids[start:end]])).logits[0]
            lse = torch.logsumexp(logits, dim=-1)
            first = 1 if start == 0 else window - stride
            for pos in range(first, end - start):
                lp = float(logits[pos - 1, ids[start + pos]]) - float(lse[pos - 1])
                surprisals.append(-lp / math.log(2.0))
            if end == len(ids):
                break
            start += stride

    n = len(surprisals)
    if n < DECILES:
        _cache.put(text, [])
        return None
    bins: list[float] = []
    for b in range(DECILES):
        lo, hi = n * b // DECILES, n * (b + 1) // DECILES
        chunk = surprisals[lo:hi] or surprisals[lo:lo + 1]
        bins.append(sum(chunk) / len(chunk))
    _cache.put(text, bins)
    return bins


def _profile_or_none(ctx: FeatureContext) -> list[float] | None:
    text = cast(str, ctx.get("prose.text"))
    return _profile(text) if text.strip() else None


def surprisal_slope(ctx: FeatureContext) -> float | None:
    """OLS slope of per-decile surprisal against normalized position."""
    bins = _profile_or_none(ctx)
    if bins is None:
        return None
    xs = [(i + 0.5) / DECILES for i in range(len(bins))]
    mx = sum(xs) / len(xs)
    my = sum(bins) / len(bins)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, bins)) / denom


def surprisal_peak_position(ctx: FeatureContext) -> float | None:
    """Normalized position (0-1) of the densest decile."""
    bins = _profile_or_none(ctx)
    if bins is None:
        return None
    peak = max(range(len(bins)), key=lambda i: bins[i])
    return (peak + 0.5) / len(bins)


_NULL = NullModel(
    kind="permutation",
    derived_from=(
        "the same document with paragraph order destroyed (shuffle_paragraphs): "
        "the trajectory of order-free text is the no-arc expectation the "
        "observed shape is read against"
    ),
)

_INTERPRETATION = (
    "Model-conditioned: comparable only under the identical model, revision "
    "and binning in params. Computed on the prose view, so markup weight does "
    "not register as an arc (rho with markup fraction is -0.08 for the slope "
    "and -0.11 for the peak position on block B, n = 198). Mean surprisal is "
    "raised at the start of any text, where the model has least context, so "
    "read a value against the same document with its paragraphs shuffled, "
    "not against zero. No genre claim is registered: both measures differ "
    "across block B genres (omega-squared 0.22 and 0.19), and the slope also "
    "tracks document length (rho 0.44 with prose word count)."
)

SURPRISAL_SLOPE = register(MeasureDescriptor(
    id="astronomia.surprisal-slope",
    version="1.0.0",
    construct=(
        "Global-scale UID deviation, direction: the signed least-squares slope "
        "of per-decile mean surprisal (bits) against normalized document "
        "position. Positive means the document becomes more surprising as it "
        "proceeds."
    ),
    requires=("prose.text",),
    kind=Kind.CLAIM,
    compute=surprisal_slope,
    # Shuffle destroys order, reversal destroys direction. Reversal is a
    # falsifier only because the slope is signed.
    must_move_under=(SHUFFLE_PARAGRAPHS, REVERSE_PARAGRAPHS),
    null=_NULL,
    strata=("astronomia",),
    # Both falsifiers move it on block B: 0.51 of interquartile spread under
    # shuffle, 0.81 under reversal.
    status=Status.ACTIVE,
    interpretation=_INTERPRETATION,
    params=PARAMS,
))

SURPRISAL_PEAK_POSITION = register(MeasureDescriptor(
    id="astronomia.surprisal-peak-position",
    version="1.0.0",
    construct=(
        "Global-scale UID deviation, location: the normalized position (0-1) "
        "of the decile with the highest mean surprisal. Takes one of ten "
        "values."
    ),
    requires=("prose.text",),
    kind=Kind.CLAIM,
    compute=surprisal_peak_position,
    must_move_under=(SHUFFLE_PARAGRAPHS, REVERSE_PARAGRAPHS),
    null=_NULL,
    strata=("astronomia",),
    # Both falsifiers move it on block B: 0.25 of interquartile spread under
    # shuffle (the admission threshold), 0.50 under reversal.
    status=Status.ACTIVE,
    interpretation=_INTERPRETATION,
    params=PARAMS,
))


__all__ = ["SURPRISAL_SLOPE", "SURPRISAL_PEAK_POSITION"]
