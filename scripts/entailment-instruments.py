"""
Can a mechanical instrument tell a claim from its negation?

The pairs in corpus/entailment-pairs.json each hold a claim that reference.md
asserts and a minimal negation of it. Every instrument scores each text
independently for support against reference.md; the paired AUC is the
fraction of pairs in which the assertion outscores its negation (ties count
half). The passing mark is AUC >= 0.80.

Four mechanical instruments:

  zlib-zdict    deflate size of the text with reference.md as preset
                dictionary (deflate's window caps the dictionary at 32 KB)
  lzma-concat   lzma(reference + text) - lzma(reference)
  gpt2-cond     mean per-token log-probability of the text given the
                section of reference.md the pair was drawn from
  gpt2-uncond   the same with no context: the control that shows how much
                of gpt2-cond comes from reading the substrate

For the compression instruments a smaller conditional size means more
support, so the size is negated. Results are broken down by negation type,
because a compressor responds to surface distance and the types differ in
how much of the surface they change.

Needs the `[surprisal]` extra. Writes raw scores to
corpus/cache/entailment-scores.json for scripts/entailment-judge.py and
prints the per-instrument summary.
"""

from __future__ import annotations

import json
import lzma
import math
import re
import sys
import zlib
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

GATE = 0.80


def _sections(text: str) -> dict[str, str]:
    """reference.md split by its `## N.` headings, keyed by section number."""
    out: dict[str, str] = {}
    current, buf = None, []
    for line in text.split("\n"):
        m = re.match(r"^## (\d+)\.", line)
        if m:
            if current:
                out[current] = "\n".join(buf)
            current, buf = m.group(1), [line]
        elif current:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf)
    return out


def zdict_size(text: str, dictionary: bytes) -> int:
    co = zlib.compressobj(9, zlib.DEFLATED, -15, 9, zlib.Z_DEFAULT_STRATEGY,
                          dictionary)
    return len(co.compress(text.encode("utf-8")) + co.flush())


def lzma_size(data: bytes) -> int:
    return len(lzma.compress(data, preset=6))


def gpt2_mean_logprob(text: str, context: str) -> float:
    """Mean per-token log-probability (bits) of `text` given `context` as prefix."""
    from isda.measures.musica import _backend  # pyright: ignore[reportPrivateUsage]
    torch, tok, model = _backend()
    ctx_ids: list[int] = list(tok(context)["input_ids"]) if context else []
    txt_ids: list[int] = list(tok(text)["input_ids"])
    window = 1024
    # keep the whole claim; trim the head of the context to fit the window
    keep = window - len(txt_ids)
    if keep < 0:
        raise SystemExit(f"claim longer than the model window: {len(txt_ids)}")
    ctx_ids = ctx_ids[-keep:] if keep else []
    ids = ctx_ids + txt_ids
    with torch.no_grad():
        logits = model(torch.tensor([ids])).logits[0]
        lse = torch.logsumexp(logits, dim=-1)
        total = 0.0
        n = 0
        start = max(len(ctx_ids), 1)  # position 0 has no prediction
        for pos in range(start, len(ids)):
            total += (float(logits[pos - 1, ids[pos]]) - float(lse[pos - 1]))
            n += 1
    return (total / n) / math.log(2.0)


def paired_auc(scores: dict[str, tuple[float, float]]) -> float:
    """Fraction of pairs where the assertion outscores the negation; ties half."""
    wins = sum(1.0 if a > n else (0.5 if a == n else 0.0)
               for a, n in scores.values())
    return wins / len(scores)


def summarize(pairs: list[dict[str, str]],
              scores: dict[str, tuple[float, float]]) -> dict[str, object]:
    types = sorted({p["type"] for p in pairs})
    auc = paired_auc(scores)
    return {
        "auc": round(auc, 3),
        "passed": auc >= GATE,
        "auc_by_negation_type": {
            t: round(paired_auc({p["id"]: scores[p["id"]]
                                 for p in pairs if p["type"] == t}), 3)
            for t in types
        },
    }


def main() -> int:
    data: dict[str, Any] = json.loads(
        (ROOT / "corpus" / "entailment-pairs.json").read_text(encoding="utf-8"))
    pairs = cast("list[dict[str, str]]", data["pairs"])
    substrate = (ROOT / "reference.md").read_text(encoding="utf-8")
    sections = _sections(substrate)
    kb = substrate.encode("utf-8")
    zdict = kb[:32768]
    lz_kb = lzma_size(kb)

    per_instrument: dict[str, dict[str, tuple[float, float]]] = {
        "zlib-zdict": {}, "lzma-concat": {}, "gpt2-cond": {}, "gpt2-uncond": {},
    }
    for i, p in enumerate(pairs):
        a, n, sec = p["assertion"], p["negation"], p["section"]
        context = sections.get(sec, "")
        per_instrument["zlib-zdict"][p["id"]] = (
            -float(zdict_size(a, zdict)), -float(zdict_size(n, zdict)))
        per_instrument["lzma-concat"][p["id"]] = (
            -float(lzma_size(kb + a.encode("utf-8")) - lz_kb),
            -float(lzma_size(kb + n.encode("utf-8")) - lz_kb))
        per_instrument["gpt2-cond"][p["id"]] = (
            gpt2_mean_logprob(a, context), gpt2_mean_logprob(n, context))
        per_instrument["gpt2-uncond"][p["id"]] = (
            gpt2_mean_logprob(a, ""), gpt2_mean_logprob(n, ""))
        if (i + 1) % 10 == 0:
            print(f"  ... {i + 1}/{len(pairs)} pairs", file=sys.stderr)

    cache = ROOT / "corpus" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "entailment-scores.json").write_text(
        json.dumps({k: {i: list(v) for i, v in s.items()}
                    for k, s in per_instrument.items()}, indent=0),
        encoding="utf-8", newline="\n")
    print(json.dumps({
        "n_pairs": len(pairs), "gate": f"AUC >= {GATE:.2f}",
        "instruments": {name: summarize(pairs, scores)
                        for name, scores in per_instrument.items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
