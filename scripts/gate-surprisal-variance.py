"""
The admission gate for `musica.surprisal-variance`.

Run against block B (working markdown) and the lyric specimen, it reports:

  - discrimination: omega-squared across block B genres with its permutation
    p-value and detectability floor (a genre claim needs >= 0.10 at p < 0.01)
  - the falsifier harness: both declared destroyers must move the measure by
    at least a quarter of its interquartile spread
  - the lyric specimen ("Pied Beauty") as a quantile of block B: a prosody
    measure should place a sprung-rhythm poem in the top quartile
  - redundancy: |rho| <= 0.90 against every other registered measure, and
    |rho| <= 0.50 against markup fraction, since a measure that tracks how
    much of a file is markup is reading the markup

Needs the `[surprisal]` extra and a built corpus cache. Prints the exhibit as
JSON; redirect it to corpus/exhibits/surprisal-variance.json.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.core.document import Document
from isda.core.features import FeatureContext
from isda.corpus import load_block
from isda.kernel.descriptor import DiscriminationClaim
from isda.kernel.registry import all_measures, discriminate, verify
from isda.kernel.stats import spearman
from isda.measures.musica import SURPRISAL_VARIANCE
from isda.specimens import load_specimens

SEED = 0
N_PERM = 2000


def value_of(desc, text):  # type: ignore[no-untyped-def]
    return desc.compute(FeatureContext(Document.parse(text),
                                       frozenset(desc.requires)))


def main() -> int:
    t0 = time.time()
    docs = load_block("block-b")
    exhibit: dict[str, object] = {
        "measure": SURPRISAL_VARIANCE.id,
        "run": {"script": "scripts/gate-surprisal-variance.py",
                "seed": SEED, "n_perm": N_PERM},
        "n_docs": len(docs),
    }

    # -- values (this pass also fills the disk cache) -----------------------
    values: dict[str, float] = {}
    by_genre: dict[str, list[str]] = defaultdict(list)
    for i, d in enumerate(docs):
        v = value_of(SURPRISAL_VARIANCE, d.text)
        if v is not None:
            values[d.id] = v
        by_genre[d.genre].append(d.text)
        if (i + 1) % 25 == 0:
            print(f"  ... {i + 1}/{len(docs)} docs, {time.time() - t0:.0f}s",
                  file=sys.stderr)

    # -- discrimination -----------------------------------------------------
    probe = replace(SURPRISAL_VARIANCE,
                    discrimination=DiscriminationClaim(groups_by="genre"))
    dv = discriminate(probe, by_genre, n_perm=N_PERM, seed=SEED)
    exhibit["discrimination"] = {
        "omega2": round(dv.omega2, 4), "p": round(dv.p, 5),
        "floor": round(dv.floor, 4), "threshold": dv.threshold,
        "adequately_powered": dv.adequately_powered, "passed": dv.passed,
        "n": dv.n, "k": dv.k,
    }

    # -- falsifier harness --------------------------------------------------
    hv = verify(SURPRISAL_VARIANCE, [d.text for d in docs], seed=SEED)
    exhibit["falsifiers"] = {
        "spread_iqr": None if hv.spread is None else round(hv.spread, 4),
        "results": [
            {"perturbation": r.perturbation, "expectation": r.expectation,
             "normalised_move": r.normalised, "passed": r.passed,
             "reason": r.reason}
            for r in hv.results
        ],
        "errors": hv.errors,
        "passed": hv.passed,
    }

    # -- the lyric specimen as a quantile of block B ------------------------
    lyric = next(s for s in load_specimens() if s.slug == "lyric-musica-original")
    own = value_of(SURPRISAL_VARIANCE, lyric.text)
    if own is None:
        raise SystemExit("the lyric specimen produced no value")
    corpus_vals = sorted(values.values())
    q = sum(1 for v in corpus_vals if v <= own) / len(corpus_vals)
    exhibit["lyric_specimen"] = {
        "value": round(own, 3), "quantile": round(q, 3),
        "gate": ">= 0.75", "passed": q >= 0.75,
        "corpus_median": round(statistics.median(corpus_vals), 3),
    }

    # -- redundancy, and the markup confound --------------------------------
    rows: dict[str, float | None] = {}
    doc_order = [d for d in docs if d.id in values]
    xs = [values[d.id] for d in doc_order]
    for other in all_measures():
        if other.id == SURPRISAL_VARIANCE.id:
            continue
        ys = [value_of(other, d.text) for d in doc_order]
        pairs = [(a, b) for a, b in zip(xs, ys) if b is not None]
        if len(pairs) < 10:
            rows[other.id] = None
            continue
        try:
            rows[other.id] = round(spearman([p[0] for p in pairs],
                                            [p[1] for p in pairs]), 3)
        except ValueError:
            rows[other.id] = None
    # markup fraction: 1 - prose bytes / source bytes
    mk: list[float] = []
    for d in doc_order:
        doc = Document.parse(d.text)
        total = doc.total_bytes
        mk.append(0.0 if total == 0 else
                  1.0 - len(doc.prose_text.encode("utf-8")) / total)
    rows["markup_fraction"] = round(spearman(xs, mk), 3)
    exhibit["spearman_vs"] = rows
    exhibit["redundancy"] = {
        "max_abs_rho_vs_measures": max(
            abs(v) for k, v in rows.items()
            if v is not None and k != "markup_fraction"),
        "rho_vs_markup": rows["markup_fraction"],
    }

    print(json.dumps(exhibit, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
