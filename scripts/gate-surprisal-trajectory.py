"""
The admission gate for the two Astronomia measures, `astronomia.surprisal-slope`
and `astronomia.surprisal-peak-position`.

Run against block B (working markdown), it reports for each measure:

  - the falsifier harness: a paragraph shuffle destroys order and a paragraph
    reversal destroys direction, and each must move the measure by at least a
    quarter of its interquartile spread
  - redundancy: |rho| <= 0.90 against every other registered measure, and
    |rho| <= 0.50 against markup fraction
  - discrimination across genres, reported without a threshold: neither
    measure registers a genre claim, so this is an observation, not a
    condition

and, for the corpus as a whole, the mean surprisal in each decile of position
with the share of documents whose highest decile is the first.

Needs the `[surprisal]` extra and a built corpus cache. Prints the exhibit as
JSON; redirect it to corpus/exhibits/surprisal-trajectory.json.
"""

from __future__ import annotations

import json
import statistics
import sys
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
from isda.measures.astronomia import (
    SURPRISAL_PEAK_POSITION, SURPRISAL_SLOPE,
    _profile_or_none,  # pyright: ignore[reportPrivateUsage]
)

SEED = 0
N_PERM = 1000


def value_of(desc, text):  # type: ignore[no-untyped-def]
    return desc.compute(FeatureContext(Document.parse(text),
                                       frozenset(desc.requires)))


def main() -> int:
    docs = load_block("block-b")
    by_genre: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        by_genre[d.genre].append(d.text)

    results: dict[str, object] = {}
    for desc in (SURPRISAL_SLOPE, SURPRISAL_PEAK_POSITION):
        print(f"  {desc.id} ...", file=sys.stderr, flush=True)
        hv = verify(desc, [d.text for d in docs], seed=SEED)
        row: dict[str, object] = {
            "spread_iqr": None if hv.spread is None else round(hv.spread, 5),
            "falsifiers": [
                {"perturbation": r.perturbation, "normalised_move": r.normalised,
                 "passed": r.passed, "reason": r.reason} for r in hv.results],
            "falsifiers_passed": hv.passed,
            "errors": hv.errors,
        }
        vals = {d.id: v for d in docs
                if (v := value_of(desc, d.text)) is not None}
        row["n_computable"] = len(vals)
        if vals:
            xs = sorted(vals.values())
            row["quartiles"] = [round(xs[len(xs) // 4], 4),
                                round(statistics.median(xs), 4),
                                round(xs[3 * len(xs) // 4], 4)]

        probe = replace(desc, discrimination=DiscriminationClaim(groups_by="genre"))
        dv = discriminate(probe, by_genre, n_perm=N_PERM, seed=SEED)
        row["discrimination"] = {
            "omega2": round(dv.omega2, 4), "p": round(dv.p, 5),
            "floor": round(dv.floor, 4),
        }

        order = [d for d in docs if d.id in vals]
        own = [vals[d.id] for d in order]
        rhos: dict[str, float | None] = {}
        for other in all_measures():
            if other.id == desc.id:
                continue
            ys = [value_of(other, d.text) for d in order]
            pairs = [(a, b) for a, b in zip(own, ys) if b is not None]
            if len(pairs) < 10:
                rhos[other.id] = None
                continue
            try:
                rhos[other.id] = round(spearman([p[0] for p in pairs],
                                                [p[1] for p in pairs]), 3)
            except ValueError:
                rhos[other.id] = None
        # markup fraction: 1 - prose bytes / source bytes
        mk: list[float] = []
        for d in order:
            doc = Document.parse(d.text)
            mk.append(0.0 if doc.total_bytes == 0 else
                      1.0 - len(doc.prose_text.encode("utf-8")) / doc.total_bytes)
        rhos["markup_fraction"] = round(spearman(own, mk), 3)
        row["spearman_vs"] = rhos
        row["max_abs_rho_vs_measures"] = max(
            abs(v) for k, v in rhos.items()
            if v is not None and k != "markup_fraction")
        results[desc.id] = row

    profiles = [p for d in docs
                if (p := _profile_or_none(FeatureContext(
                    Document.parse(d.text),
                    frozenset(SURPRISAL_SLOPE.requires)))) is not None]
    deciles = len(profiles[0])
    profile = {
        "n": len(profiles),
        "mean_surprisal_by_decile": [
            round(statistics.fmean(p[i] for p in profiles), 3)
            for i in range(deciles)],
        "share_peaking_in_first_decile": round(
            sum(1 for p in profiles if max(range(deciles), key=p.__getitem__) == 0)
            / len(profiles), 3),
    }

    print(json.dumps({
        "run": {"script": "scripts/gate-surprisal-trajectory.py",
                "seed": SEED, "n_perm": N_PERM},
        "n_docs": len(docs),
        "profile": profile,
        "measures": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
