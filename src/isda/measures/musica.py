"""
Musica: per-token surprisal variance.

Musica and Astronomia share one theoretical spine: deviation from a Uniform
Information Density baseline, at local scale (prosody) and global scale
(trajectory). This measure operationalizes the local half: the variance of
per-token surprisal under a fixed small causal language model. Uniform
delivery, with each token contributing about the same information, scores low;
rhythm that concentrates information at stressed points (sprung stress,
coinages, periodic build) scores high. The lyric specimen (Hopkins, "Pied
Beauty") is a sprung-rhythm poem, so a prosody measure should rank it in the
top quartile of block B (working markdown); this measure places it at
quantile 0.96.

The backend is GPT-2-small via `transformers`, on CPU: a public model that
yields per-token log-probabilities and is pinned to an exact revision, so
values are comparable across machines. `transformers` is used directly rather
than through a wrapper such as `minicons`, which adds a dependency for the
identical quantity. The model and its parameters travel in `params`, because a
surprisal value is meaningless without the model that assigned it.

The backend ships behind the `[surprisal]` extra. Registration is pure
metadata and works everywhere; `compute` raises MeasureUnavailable on a
machine without the extra and without a warm cache, and every consumer (pins,
verify, the CLI) treats that as a statement about the machine, never about
the text. The disk cache under corpus/cache/ is keyed by content hash plus a
params fingerprint, so it cannot serve a stale value.
"""

from __future__ import annotations

import math
from typing import Any, cast

from ..core.features import FeatureContext
from ..kernel.descriptor import (
    Kind, MeasureDescriptor, MeasureUnavailable, NullModel, Status,
)
from ..kernel.perturb import SCRAMBLE_IN_SENTENCE, SCRAMBLE_WORDS
from ..kernel.registry import register
from ._cache import HashCache

# The measurement parameters are part of the measure's identity: a value
# computed under a different model or windowing is a different quantity.
# The cache fingerprint invalidates the disk cache when any of them change.
PARAMS: dict[str, object] = {
    "model": "gpt2",            # GPT-2-small, 124M parameters
    "revision": "607a30d783dfa663caf39e06633721c8d4cfcd7e",  # pinned HF snapshot
    "window": 1024,             # GPT-2's full context
    "stride": 512,              # after the first window, every token sees >= 512 context
    "unit": "bits",
    "scope": "prose",           # the markup-stripped prose view, not the source
}

_cache = HashCache(
    "surprisal-gpt2.json", PARAMS,
    "isda.measures.musica: derived state, keyed by content hash; delete "
    "freely, it rebuilds",
)


# ---------------------------------------------------------------- the model

_model_state: list[object] | None = None  # [tokenizer, model] after loading


def _backend() -> tuple[Any, Any, Any]:
    """
    (torch, tokenizer, model), loaded on first call and cached; raises
    MeasureUnavailable when the backend is not installed.
    """
    global _model_state
    if _model_state is not None:
        return cast("tuple[Any, Any, Any]", tuple(_model_state))
    try:
        import torch
        import transformers
    except ImportError as exc:
        raise MeasureUnavailable(
            "the surprisal measures need the [surprisal] extra "
            "(pip install isda[surprisal]) and no cached value exists for "
            "this text on this machine"
        ) from exc
    hub = cast(Any, transformers)
    # The tokenizer warns on every text longer than the model window; the
    # windowing below is exactly how that is handled, so the warning is noise.
    hub.logging.set_verbosity_error()
    tok = hub.GPT2TokenizerFast.from_pretrained(
        str(PARAMS["model"]), revision=str(PARAMS["revision"]))
    model = hub.GPT2LMHeadModel.from_pretrained(
        str(PARAMS["model"]), revision=str(PARAMS["revision"]))
    model.eval()
    _model_state = [cast(Any, torch), tok, model]
    return cast(Any, torch), tok, model


def _surprisal_stats(text: str) -> tuple[int, float, float] | None:
    """(n_scored, mean_bits, variance_bits2) for one prose text, cached."""
    row = _cache.get(text)
    if row is not None:
        return int(row[0]), row[1], row[2]

    torch, tok, model = _backend()

    ids: list[int] = list(tok(text)["input_ids"])
    if len(ids) < 2:
        return None  # nothing is predicted: no context-conditioned token exists

    window = int(cast(int, PARAMS["window"]))
    stride = int(cast(int, PARAMS["stride"]))
    surprisals: list[float] = []
    with torch.no_grad():
        start = 0
        while start < len(ids) - 1:
            end = min(start + window, len(ids))
            chunk = torch.tensor([ids[start:end]])
            logits = model(chunk).logits[0]           # (len, vocab)
            # logprob(target) = logit[target] − logsumexp(logits): the same
            # quantity as log_softmax without materializing a full-vocab
            # log-probability tensor per window.
            lse = torch.logsumexp(logits, dim=-1)
            # score positions after the first; on later windows, skip the
            # overlap already scored with at least `stride` context
            first = 1 if start == 0 else window - stride
            for pos in range(first, end - start):
                lp = float(logits[pos - 1, ids[start + pos]]) - float(lse[pos - 1])
                surprisals.append(-lp / math.log(2.0))
            if end == len(ids):
                break
            start += stride

    n = len(surprisals)
    mean = sum(surprisals) / n
    var = sum((s - mean) ** 2 for s in surprisals) / n
    _cache.put(text, (float(n), mean, var))
    return n, mean, var


# ---------------------------------------------------------------- the measure

def surprisal_variance(ctx: FeatureContext) -> float | None:
    text = cast(str, ctx.get("prose.text"))
    if not text.strip():
        return None
    stats = _surprisal_stats(text)
    return None if stats is None else stats[2]


SURPRISAL_VARIANCE = register(MeasureDescriptor(
    id="musica.surprisal-variance",
    version="1.0.0",
    construct=(
        "Deviation from uniform information density at local scale: the "
        "variance of per-token surprisal (bits) under a fixed small causal "
        "LM (GPT-2-small), over the prose view. Uniform delivery scores low; "
        "prosody that concentrates information at stressed points scores high."
    ),
    requires=("prose.text",),
    kind=Kind.CLAIM,
    compute=surprisal_variance,
    must_move_under=(SCRAMBLE_IN_SENTENCE, SCRAMBLE_WORDS),
    null=NullModel(
        kind="permutation",
        derived_from=(
            "the same document with word order destroyed (scramble_words): "
            "the surprisal profile of order-free text is the no-prosody "
            "expectation the observed variance is read against"
        ),
    ),
    strata=("musica",),
    # Gate evidence, block B, n = 198
    # (corpus/exhibits/surprisal-variance.json): scramble_within_sentence and
    # scramble_words move it 0.53 and 0.67 of interquartile spread; the lyric
    # specimen ranks at quantile 0.96 against a gate of 0.75; the largest
    # |rho| against any admitted measure is 0.205 and against markup fraction
    # -0.05. No DiscriminationClaim: omega-squared 0.0857 at power (floor
    # 0.0523, p = 0.0015) is significant but below the 0.10 claim threshold.
    status=Status.ACTIVE,
    interpretation=(
        "A model-conditioned quantity: values are comparable only under the "
        "identical model, revision and windowing recorded in params. Computed "
        "on the prose view, so markup weight does not register as rhythm "
        "(rho with markup fraction is -0.05 on block B, n = 198). No genre "
        "claim: omega-squared across block B genres is 0.0857 (p = 0.0015, "
        "label-noise floor 0.0523), significant but below the 0.10 claim "
        "threshold. The lyric specimen ranks at quantile 0.96 of block B "
        "against a gate of 0.75 (corpus/exhibits/surprisal-variance.json)."
    ),
    params=PARAMS,
))
