"""
The reading-judge instrument for the entailment pairs, and the final exhibit.

    python scripts/entailment-judge.py prepare OUT_DIR
    python scripts/entailment-judge.py merge --model NAME RESULTS.json [...]

`prepare` writes four batch files of 30 claims each. No batch holds both
members of a pair, so a judge never sees a claim beside its negation and has
to score each one against reference.md on its own.

Give a language model reference.md and one batch, and ask it to score every
claim from 0 (the substrate contradicts it) to 100 (the substrate asserts
it), with a quotation from reference.md as evidence for any score other than
50. Its reply for a batch is a JSON file:

    {"rows": [{"key": "pair-01-a", "support": 100, "evidence": "..."}, ...]}

`merge` checks the result files (every claim scored exactly once, scores in
range, evidence present), computes the judge's paired AUC overall and per
negation type, combines it with the mechanical instruments' scores written by
scripts/entailment-instruments.py, and writes corpus/exhibits/entailment.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
GATE = 0.80
BATCHES = 4


def paired_auc(scores: dict[str, tuple[float, float]]) -> float:
    wins = sum(1.0 if a > n else (0.5 if a == n else 0.0)
               for a, n in scores.values())
    return wins / len(scores)


def _pairs() -> list[dict[str, str]]:
    return cast("list[dict[str, str]]", json.loads(
        (ROOT / "corpus" / "entailment-pairs.json").read_text(encoding="utf-8"))["pairs"])


def _summary(pairs: list[dict[str, str]],
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


def prepare(out_dir: Path) -> int:
    pairs = _pairs()
    batches: list[list[dict[str, str]]] = [[] for _ in range(BATCHES)]
    for i, p in enumerate(pairs):
        # the two members of a pair land two batches apart
        batches[i % BATCHES].append({"key": p["id"] + "-a", "claim": p["assertion"]})
        batches[(i + BATCHES // 2) % BATCHES].append(
            {"key": p["id"] + "-n", "claim": p["negation"]})
    out_dir.mkdir(parents=True, exist_ok=True)
    for n, claims in enumerate(batches, 1):
        claims.sort(key=lambda c: c["key"])
        (out_dir / f"batch-{n}.json").write_text(
            json.dumps({"claims": claims}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")
        print(f"batch-{n}.json: {len(claims)} claims")
    return 0


def merge(model: str, result_files: list[Path]) -> int:
    pairs = _pairs()
    expected = {p["id"] + s for p in pairs for s in ("-a", "-n")}
    support: dict[str, int] = {}
    evidence: dict[str, str] = {}
    for path in result_files:
        rows = cast("list[dict[str, Any]]", json.loads(
            path.read_text(encoding="utf-8"))["rows"])
        for r in rows:
            key, s = str(r["key"]), r["support"]
            if key in support:
                raise SystemExit(f"{path.name}: {key} scored twice")
            if not isinstance(s, int) or not 0 <= s <= 100:
                raise SystemExit(f"{path.name}/{key}: support must be 0-100, got {s!r}")
            if s != 50 and not str(r.get("evidence", "")).strip():
                raise SystemExit(f"{path.name}/{key}: a score other than 50 needs evidence")
            support[key] = s
            evidence[key] = str(r.get("evidence", ""))
    if set(support) != expected:
        raise SystemExit(f"claim coverage mismatch: {sorted(set(support) ^ expected)[:10]}")

    judge = {p["id"]: (float(support[p["id"] + "-a"]), float(support[p["id"] + "-n"]))
             for p in pairs}
    scores_path = ROOT / "corpus" / "cache" / "entailment-scores.json"
    if not scores_path.is_file():
        raise SystemExit("run scripts/entailment-instruments.py first")
    mechanical = cast("dict[str, dict[str, list[float]]]", json.loads(
        scores_path.read_text(encoding="utf-8")))
    instruments: dict[str, object] = {
        name: _summary(pairs, {p["id"]: (scores[p["id"]][0], scores[p["id"]][1])
                               for p in pairs})
        for name, scores in mechanical.items()
    }
    instruments["lm-judge"] = {**_summary(pairs, judge), "model": model,
                               "batches": len(result_files)}

    exhibit = {
        "run": {"scripts": ["scripts/entailment-instruments.py",
                            "scripts/entailment-judge.py"],
                "judge_protocol": ("four pair-disjoint batches of 30 claims; each claim "
                                   "scored independently 0-100 for support against the "
                                   "substrate, with a mandatory evidence quote; the judge "
                                   "sees reference.md and nothing else; one pass, no "
                                   "best-of-n")},
        "n_pairs": len(pairs),
        "gate": f"AUC >= {GATE:.2f}",
        "instruments": instruments,
        "judge_rows": {k: {"support": support[k], "evidence": evidence[k][:240]}
                       for k in sorted(support)},
    }
    out = ROOT / "corpus" / "exhibits" / "entailment.json"
    out.write_text(json.dumps(exhibit, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in exhibit.items() if k != "judge_rows"}, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="The reading-judge instrument for the entailment pairs.")
    sub = ap.add_subparsers(dest="verb", required=True)
    p_prepare = sub.add_parser("prepare", help="write the pair-disjoint claim batches")
    p_prepare.add_argument("out_dir", type=Path)
    p_merge = sub.add_parser("merge", help="check judge results and write the exhibit")
    p_merge.add_argument("--model", required=True, help="the judging model's id")
    p_merge.add_argument("results", type=Path, nargs="+")
    args = ap.parse_args()
    if args.verb == "prepare":
        return prepare(args.out_dir)
    return merge(args.model, args.results)


if __name__ == "__main__":
    sys.exit(main())
