"""
Inter-rater agreement over the ratings in corpus/rating/ratings/.

    python scripts/rating-agreement.py

Recomputes from the rating files on every run and writes
corpus/exhibits/inter-rater.json:

  - per stratum, the spread of the raters' compressed-size estimates as a
    standard deviation in log2. Size estimates disagree multiplicatively, so
    an SD of 1.0 means raters typically differ by a factor of two either way.
  - the interval that spread induces on SCR, ND and RI, by Monte Carlo
    through the ledger arithmetic (resampling size and intensity tag per
    stratum)
  - per stratum, Fleiss' kappa across the model raters together with raw
    agreement, the tag distribution and the modal tag's share
  - where human ratings exist, Cohen's kappa of the model raters' modal tag
    against the human tag

Agreement between raters is reliability, not validity: K is uncomputable, no
rater has access to a true compressed size, and raters can agree and be wrong
together. Kappa between a human and a model family says whether their tags
are interchangeable for a stratum, not which of them is right.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

STRATA = ("grammatica", "dialectica", "rhetorica", "arithmetica",
          "geometria", "musica", "astronomia")
RATING = ROOT / "corpus" / "rating"
SEED = 0
DRAWS = 20000


def _docs() -> list[dict[str, str]]:
    data = json.loads((RATING / "documents.json").read_text(encoding="utf-8"))
    return cast("list[dict[str, str]]", data["documents"])


def _doc_bytes() -> dict[str, int]:
    """Raw length of every rated document, from files the repository carries:
    the specimen bodies, and block B's published byte counts."""
    block_b = json.loads((ROOT / "corpus" / "block-b.json").read_text(encoding="utf-8"))
    sizes = {str(d["id"]): int(d["bytes"]) for d in block_b["documents"]}
    for doc in _docs():
        if doc["kind"] == "specimen":
            path = ROOT / "corpus" / "specimens" / doc["id"] / "text.md"
            sizes[doc["id"]] = len(path.read_bytes())
    return sizes


def _load_ratings() -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """family -> rater -> doc -> ledger"""
    out: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    root = RATING / "ratings"
    if not root.is_dir():
        return out
    for fam_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for rater_dir in sorted(p for p in fam_dir.iterdir() if p.is_dir()):
            for f in sorted(rater_dir.glob("*.json")):
                row = cast("dict[str, Any]", json.loads(f.read_text(encoding="utf-8")))
                out.setdefault(fam_dir.name, {}).setdefault(
                    rater_dir.name, {})[str(row["doc"])] = cast(
                        "dict[str, Any]", row["ledger"])
    return out


def _fleiss_kappa(rows: list[list[str]]) -> float | None:
    """Fleiss' kappa over subjects x raters (each row = one subject's tags)."""
    if not rows or len(rows[0]) < 2:
        return None
    n = len(rows[0])
    cats = sorted({t for row in rows for t in row})
    if len(cats) == 1:
        return None  # unanimous on one tag: no variance for kappa to describe
    p_j = {c: sum(row.count(c) for row in rows) / (len(rows) * n) for c in cats}
    p_i = [(sum(row.count(c) ** 2 for c in cats) - n) / (n * (n - 1)) for row in rows]
    p_bar = statistics.fmean(p_i)
    p_e = sum(v * v for v in p_j.values())
    if p_e == 1.0:
        return None
    return (p_bar - p_e) / (1 - p_e)


def _cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if len(a) != len(b) or not a:
        return None
    cats = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / len(a)
    pe = sum((a.count(c) / len(a)) * (b.count(c) / len(b)) for c in cats)
    if pe == 1.0:
        return None
    return (po - pe) / (1 - pe)


def analyze() -> int:
    ratings = _load_ratings()
    model_families = {f: raters for f, raters in ratings.items() if f != "human"}
    human: dict[str, dict[str, Any]] = {}
    for rater in ratings.get("human", {}).values():
        human.update(rater)
    docs = {d["id"]: d for d in _docs()}

    exhibit: dict[str, Any] = {
        "run": {"script": "scripts/rating-agreement.py", "seed": SEED, "draws": DRAWS},
        "raters": {f: sorted(raters) for f, raters in ratings.items()},
    }

    # ---- spread of compressed-size estimates, per stratum ----------------
    per_stratum_logsd: dict[str, list[float]] = defaultdict(list)
    doc_rows: dict[str, dict[str, Any]] = {}
    all_raters: list[tuple[str, str]] = [
        (f, r) for f, raters in model_families.items() for r in raters]
    for doc_id in docs:
        ledgers = [model_families[f][r][doc_id]
                   for f, r in all_raters
                   if doc_id in model_families[f][r]]
        if len(ledgers) < 2:
            continue
        row: dict[str, Any] = {"n_raters": len(ledgers)}
        for stratum in STRATA:
            sizes = [float(led[stratum]["compressed"]) for led in ledgers]
            sd = statistics.stdev([math.log2(x) for x in sizes])
            per_stratum_logsd[stratum].append(sd)
            row[stratum] = {
                "sizes": sizes,
                "log2_sd": round(sd, 3),
                "tags": [led[stratum]["intensity"] for led in ledgers],
            }
        doc_rows[doc_id] = row

    exhibit["per_stratum_log2_sd_median"] = {
        s: (round(statistics.median(per_stratum_logsd[s]), 3)
            if per_stratum_logsd[s] else None)
        for s in STRATA
    }
    exhibit["n_docs_rated_by_2plus"] = len(doc_rows)

    # ---- the interval that spread induces on the metrics -----------------
    if doc_rows:
        from isda.framework.metrics import score_ledger
        raw = _doc_bytes()
        rng = random.Random(SEED)
        mc: dict[str, dict[str, float]] = {}
        for doc_id, row in doc_rows.items():
            draws: dict[str, list[float]] = {"SCR": [], "ND": [], "RI": []}
            for _ in range(DRAWS):
                strata_draw: dict[str, dict[str, object]] = {}
                for stratum in STRATA:
                    logs = [math.log2(x) for x in row[stratum]["sizes"]]
                    mu = statistics.fmean(logs)
                    sd = statistics.stdev(logs) if len(logs) > 1 else 0.0
                    size = max(1, round(2 ** rng.gauss(mu, sd)))
                    tag = rng.choice(row[stratum]["tags"])
                    strata_draw[stratum] = {"compressed": size, "intensity": tag}
                scored = score_ledger({"raw_bytes": raw[doc_id], "strata": strata_draw})
                if scored.get("ok"):
                    m = cast("dict[str, float]", scored["metrics"])
                    for k in draws:
                        draws[k].append(float(m[k]))
            mc[doc_id] = {k: round(statistics.stdev(v), 3)
                          for k, v in draws.items() if len(v) > 2}
        exhibit["monte_carlo_metric_sd_median"] = {
            k: round(statistics.median([d[k] for d in mc.values() if k in d]), 3)
            for k in ("SCR", "ND", "RI")
        }
        exhibit["monte_carlo_metric_sd_per_doc"] = mc

    # ---- tag agreement ----------------------------------------------------
    # Kappa is reported with raw agreement and the tag distribution beside
    # it. Where one tag takes nearly every rating, chance agreement rises to
    # meet observed agreement and kappa falls toward zero although the raters
    # almost always agree; read alone, the coefficient would say the opposite.
    kappa: dict[str, Any] = {}
    for stratum in STRATA:
        rows = [cast("list[str]", doc_rows[d][stratum]["tags"])
                for d in doc_rows
                if len(set(len(cast("list[str]", doc_rows[x][stratum]["tags"]))
                           for x in doc_rows)) == 1]
        k = _fleiss_kappa(rows) if rows else None
        all_tags = [t for d in doc_rows
                    for t in cast("list[str]", doc_rows[d][stratum]["tags"])]
        counts = Counter(all_tags)
        top_share = counts.most_common(1)[0][1] / len(all_tags) if all_tags else 0.0
        unanimous = sum(
            1 for d in doc_rows
            if len(set(cast("list[str]", doc_rows[d][stratum]["tags"]))) == 1)
        kappa[stratum] = {
            "fleiss_kappa": None if k is None else round(k, 3),
            "raw_agreement": round(unanimous / len(doc_rows), 3) if doc_rows else None,
            "tag_distribution": dict(counts.most_common()),
            "modal_tag_share": round(top_share, 3),
            "kappa_unreadable_prevalence_skew": top_share >= 0.90,
        }
    if human:
        for stratum in STRATA:
            humans: list[str] = []
            models: list[str] = []
            for doc_id, row in doc_rows.items():
                if doc_id not in human:
                    continue
                cell = cast("dict[str, Any]", human[doc_id]).get(stratum)
                if not cell or not cell.get("intensity"):
                    continue  # a skipped row is a non-answer, not a datum
                tags = cast("list[str]", row[stratum]["tags"])
                models.append(Counter(tags).most_common(1)[0][0])
                humans.append(str(cell["intensity"]))
            ck = _cohen_kappa(models, humans)
            kappa[stratum]["cohen_model_mode_vs_human"] = (
                None if ck is None else round(ck, 3))
            kappa[stratum]["raw_agreement_model_vs_human"] = (
                round(sum(1 for a, b in zip(models, humans) if a == b) / len(models), 3)
                if models else None)
            kappa[stratum]["n_human_docs"] = len(humans)
    exhibit["human_rated_docs"] = len(human)
    exhibit["kappa_per_stratum"] = kappa

    out = ROOT / "corpus" / "exhibits" / "inter-rater.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(exhibit, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    slim = {k: v for k, v in exhibit.items()
            if k != "monte_carlo_metric_sd_per_doc"}
    print(json.dumps(slim, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(analyze())
