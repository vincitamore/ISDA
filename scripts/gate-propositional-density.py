"""
The admission gate for `arithmetica.propositional-density` (CPIDR).

Run against block B (working markdown), block A and the specimens, it reports:

  - discrimination: omega-squared across block B genres with its permutation
    p-value and detectability floor (the claim needs >= 0.10 at p < 0.01)
  - the falsifier harness: `scramble_words` and `scramble_within_sentence`
    must each move the measure by at least a quarter of its interquartile
    spread
  - rank correlation with the standalone preprocessor's content-word ratio,
    and that ratio's own discrimination, so the two quantities can be told
    apart
  - DEPID (dependency-parse idea density) on the same documents: a second
    operationalization of the construct
  - the documents the English guard refuses
  - observed values per specimen and per genre, which the typical ranges
    quoted in SKILL.md are read from

Needs the `[nlp]` extra and a built corpus cache. Prints the exhibit as JSON;
redirect it to corpus/exhibits/propositional-density.json.
"""

from __future__ import annotations

import importlib
import json
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from isda.core.document import Document
from isda.core.features import FeatureContext
from isda.core.tokens import words as prose_words
from isda.corpus import load_block
from isda.kernel.descriptor import DiscriminationClaim
from isda.kernel.registry import discriminate, verify
from isda.kernel.stats import null_floor, omega_squared, permutation_p, spearman
from isda.measures.arithmetica_cpidr import (
    PROPOSITIONAL_DENSITY, depid_density, english_marker_rate,
)
from isda.specimens import load_specimens

SEED = 0
N_PERM = 2000

# The content-word ratio is computed with the standalone preprocessor's own
# stopword list, so the comparison is against the number that tool reports.
_preprocess = importlib.import_module("isda_preprocess")


def content_word_ratio(text: str) -> float | None:
    ws = [w.lower() for w in prose_words(text)]
    if not ws:
        return None
    return cast(Any, _preprocess).count_content_words(ws) / len(ws)


def prose_of(text: str) -> str:
    return Document.parse(text).prose_text


def value_of(desc, text):  # type: ignore[no-untyped-def]
    return desc.compute(FeatureContext(Document.parse(text),
                                       frozenset(desc.requires)))


def main() -> int:
    t0 = time.time()
    docs = load_block("block-b")
    exhibit: dict[str, object] = {
        "measure": PROPOSITIONAL_DENSITY.id,
        "run": {"script": "scripts/gate-propositional-density.py",
                "seed": SEED, "n_perm": N_PERM},
        "n_docs": len(docs),
    }

    # -- values, and the documents the English guard refuses ---------------
    cpidr_vals: dict[str, float] = {}
    excluded: list[dict[str, object]] = []
    by_genre: dict[str, list[str]] = defaultdict(list)
    for i, d in enumerate(docs):
        v = value_of(PROPOSITIONAL_DENSITY, d.text)
        if v is None:
            n, rate = english_marker_rate(prose_of(d.text))
            excluded.append({"id": d.id, "genre": d.genre,
                             "prose_words": n, "marker_rate": round(rate, 3)})
        else:
            cpidr_vals[d.id] = v
        by_genre[d.genre].append(d.text)
        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1}/{len(docs)} docs, {time.time() - t0:.0f}s",
                  file=sys.stderr)
    exhibit["guard_excluded"] = excluded

    # -- discrimination -----------------------------------------------------
    probe = replace(PROPOSITIONAL_DENSITY,
                    discrimination=DiscriminationClaim(groups_by="genre"))
    dv = discriminate(probe, by_genre, n_perm=N_PERM, seed=SEED)
    exhibit["discrimination"] = {
        "omega2": round(dv.omega2, 4), "p": round(dv.p, 5),
        "floor": round(dv.floor, 4), "threshold": dv.threshold,
        "adequately_powered": dv.adequately_powered, "passed": dv.passed,
        "n": dv.n, "k": dv.k,
    }

    # -- falsifier harness --------------------------------------------------
    hv = verify(PROPOSITIONAL_DENSITY, [d.text for d in docs], seed=SEED)
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

    # -- against the content-word ratio ------------------------------------
    doc_order = [d for d in docs if d.id in cpidr_vals]
    xs = [cpidr_vals[d.id] for d in doc_order]
    ratios = [content_word_ratio(prose_of(d.text)) for d in doc_order]
    pairs = [(x, r) for x, r in zip(xs, ratios) if r is not None]
    exhibit["rho_vs_content_word_ratio"] = round(
        spearman([p[0] for p in pairs], [p[1] for p in pairs]), 3)

    rgroups: dict[str, list[float]] = defaultdict(list)
    for d in docs:
        r = content_word_ratio(prose_of(d.text))
        if r is not None:
            rgroups[d.genre].append(r)
    exhibit["content_word_ratio_discrimination"] = {
        "omega2": round(omega_squared(rgroups), 4),
        "p": round(permutation_p(rgroups, n_perm=N_PERM, seed=SEED), 5),
        "floor": round(null_floor(rgroups, q=0.99, n_perm=N_PERM, seed=SEED), 4),
    }

    # -- DEPID, under the same English guard --------------------------------
    depid_vals: dict[str, float] = {}
    dgroups: dict[str, list[float]] = defaultdict(list)
    for d in docs:
        p_text = prose_of(d.text)
        n, rate = english_marker_rate(p_text)
        if n < 20 or rate < 0.05:
            continue
        depid_vals[d.id] = depid_density(p_text)
        dgroups[d.genre].append(depid_vals[d.id])
    dpairs = [(cpidr_vals[i], depid_vals[i])
              for i in cpidr_vals if i in depid_vals]
    exhibit["depid"] = {
        "omega2": round(omega_squared(dgroups), 4),
        "p": round(permutation_p(dgroups, n_perm=N_PERM, seed=SEED), 5),
        "floor": round(null_floor(dgroups, q=0.99, n_perm=N_PERM, seed=SEED), 4),
        "rho_vs_cpidr": round(
            spearman([p[0] for p in dpairs], [p[1] for p in dpairs]), 3),
        "n": len(depid_vals),
    }

    # -- observed values ----------------------------------------------------
    specimens: dict[str, object] = {}
    for sp in load_specimens():
        v = value_of(PROPOSITIONAL_DENSITY, sp.text)
        r = content_word_ratio(prose_of(sp.text))
        specimens[sp.slug] = {
            "cpidr": None if v is None else round(v, 3),
            "content_word_ratio": None if r is None else round(r, 3),
        }
    agroups: dict[str, list[float]] = defaultdict(list)
    for d in load_block("block-a"):
        v = value_of(PROPOSITIONAL_DENSITY, d.text)
        if v is not None:
            agroups[d.genre].append(v)
    all_b = sorted(cpidr_vals.values())
    exhibit["observed"] = {
        "specimens": specimens,
        "block_a_genre_medians": {
            g: round(statistics.median(vs), 3) for g, vs in sorted(agroups.items())},
        "block_b_genre_medians": {
            g: round(statistics.median([cpidr_vals[d.id] for d in docs
                                        if d.genre == g and d.id in cpidr_vals]), 3)
            for g in sorted(by_genre)},
        "block_b_quartiles": [round(all_b[len(all_b) // 4], 3),
                              round(statistics.median(all_b), 3),
                              round(all_b[3 * len(all_b) // 4], 3)],
    }

    print(json.dumps(exhibit, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
