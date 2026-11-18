"""
The admission gate for the shape measures and the prose word count.

Run against block B (working markdown), it reports for each measure:

  - the between-document spread, as interquartile range and as max - min
  - the per-genre medians
  - discrimination: omega-squared across block B genres with its permutation
    p-value and detectability floor (a genre claim needs >= 0.10 at p < 0.01),
    and the same test on the residuals of a least-squares fit against markup
    fraction, which shows whether the genre separation survives once the
    share of the page that is markup is taken out
  - the falsifier harness on the measure's own declarations
  - the median move under each structural perturbation, declared or not, as
    a fraction of both spreads
  - Spearman rho against every other measure in the set and against markup
    fraction (the limits are 0.90 and 0.50)

Needs a built corpus cache and no optional backend. Prints the exhibit as
JSON; redirect it to corpus/exhibits/shape.json.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import isda.measures  # noqa: F401  (importing the package registers the measures)
from isda.core.document import Document
from isda.core.features import FeatureContext
from isda.corpus import load_block
from isda.kernel.descriptor import DiscriminationClaim, MeasureDescriptor
from isda.kernel.perturb import (
    EQUALIZE_SECTIONS, FLATTEN_HEADINGS, MERGE_PARAGRAPHS, RESPLIT_PARAGRAPHS,
    SHUFFLE_PARAGRAPHS, STRIP_HEADINGS,
)
from isda.kernel.registry import all_measures, discriminate, verify
from isda.kernel.stats import null_floor, omega_squared, permutation_p, spearman

SEED = 0
N_PERM = 2000
PERTURBATIONS = (SHUFFLE_PARAGRAPHS, MERGE_PARAGRAPHS, RESPLIT_PARAGRAPHS,
                 FLATTEN_HEADINGS, STRIP_HEADINGS, EQUALIZE_SECTIONS)


def value_of(desc: MeasureDescriptor, text: str) -> float | None:
    return desc.compute(FeatureContext(Document.parse(text),
                                       frozenset(desc.requires)))


def quartiles(values: list[float]) -> tuple[float, float, float]:
    q1, q2, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return q1, q2, q3


def main() -> int:
    docs = load_block("block-b")
    measures = [m for m in all_measures()
                if m.id.startswith("shape.") or m.id == "inventory.prose-word-count"]
    texts = [d.text for d in docs]
    by_genre: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        by_genre[d.genre].append(d.text)

    values: dict[str, list[float | None]] = {
        m.id: [value_of(m, t) for t in texts] for m in measures}
    markup: list[float] = []
    for t in texts:
        doc = Document.parse(t)
        markup.append(0.0 if doc.total_bytes == 0 else
                      1.0 - len(doc.prose_text.encode("utf-8")) / doc.total_bytes)

    def rho(xs: list[float | None], ys: list[float | None]) -> float | None:
        pairs = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
        if len(pairs) < 10:
            return None
        try:
            return round(spearman([p[0] for p in pairs], [p[1] for p in pairs]), 3)
        except ValueError:
            return None

    out: dict[str, object] = {}
    for m in measures:
        base = values[m.id]
        present = [v for v in base if v is not None]
        q1, q2, q3 = quartiles(present)
        iqr, full = q3 - q1, max(present) - min(present)

        probe = m if m.discrimination is not None else replace(
            m, discrimination=DiscriminationClaim(groups_by="genre"))
        dv = discriminate(probe, by_genre, n_perm=N_PERM, seed=SEED)
        hv = verify(m, texts, seed=SEED)

        # Genre separation net of markup share: the same statistic on what a
        # straight-line fit against markup fraction leaves unexplained.
        rows = [(v, mk, d.genre) for v, mk, d in zip(base, markup, docs)
                if v is not None]
        mean_v = statistics.fmean(r[0] for r in rows)
        mean_k = statistics.fmean(r[1] for r in rows)
        var_k = sum((r[1] - mean_k) ** 2 for r in rows)
        beta = 0.0 if var_k == 0 else sum(
            (r[1] - mean_k) * (r[0] - mean_v) for r in rows) / var_k
        resid: dict[str, list[float]] = defaultdict(list)
        for v, mk, genre in rows:
            resid[genre].append(v - mean_v - beta * (mk - mean_k))
        net = {
            "omega2": round(omega_squared(resid), 4),
            "p": round(permutation_p(resid, n_perm=N_PERM, seed=SEED), 5),
            "floor": round(null_floor(resid, q=0.99, n_perm=N_PERM, seed=SEED), 4),
        }

        moves: dict[str, object] = {}
        for p in PERTURBATIONS:
            deltas: list[float] = []
            after: list[float] = []
            for t, b in zip(texts, base):
                if b is None:
                    continue
                got = value_of(m, p.apply(t, SEED))
                if got is not None:
                    deltas.append(abs(got - b))
                    after.append(got)
            if not deltas:
                moves[p.name] = None
                continue
            med = statistics.median(deltas)
            moves[p.name] = {
                "of_iqr": None if iqr == 0 else round(med / iqr, 4),
                "of_range": None if full == 0 else round(med / full, 4),
                "median_after": round(statistics.median(after), 3),
            }

        genre_median: dict[str, float] = {}
        for genre, group in sorted(by_genre.items()):
            vals = [v for t in group if (v := value_of(m, t)) is not None]
            if vals:
                genre_median[genre] = round(statistics.median(vals), 3)

        out[m.id] = {
            "status": m.status.value,
            "n": len(present),
            "quartiles": [round(q1, 3), round(q2, 3), round(q3, 3)],
            "spread": {"iqr": round(iqr, 4), "range": round(full, 4)},
            "genre_median": genre_median,
            "discrimination": {
                "claimed": m.discrimination is not None,
                "omega2": round(dv.omega2, 4), "p": round(dv.p, 5),
                "floor": round(dv.floor, 4), "threshold": dv.threshold,
                "adequately_powered": dv.adequately_powered,
                "passed": dv.passed, "n": dv.n, "k": dv.k,
            },
            "discrimination_net_of_markup": net,
            "falsifiers": {
                "results": [
                    {"perturbation": r.perturbation, "expectation": r.expectation,
                     "normalised_move": r.normalised, "passed": r.passed}
                    for r in hv.results
                ],
                "errors": hv.errors,
                "passed": hv.passed,
            },
            "median_move": moves,
            "spearman_vs": {
                **{o.id: rho(base, values[o.id]) for o in measures if o.id != m.id},
                "markup_fraction": rho(base, list(markup)),
            },
        }

    exhibit = {
        "run": {"script": "scripts/gate-shape.py", "seed": SEED, "n_perm": N_PERM},
        "n_docs": len(docs),
        "measures": out,
    }
    text = json.dumps(exhibit, indent=2)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
