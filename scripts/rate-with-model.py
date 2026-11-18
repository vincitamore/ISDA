"""
Rate the public documents with a model behind an OpenAI-compatible endpoint.

    python scripts/rate-with-model.py --base-url http://127.0.0.1:8080/v1 \\
        --model MODEL --family FAMILY --rater ID [--api-key-env VAR]

Each document is one request: the protocol (corpus/rating/protocol.md), the
document's telos and substrate, and the document itself, answered with a
single JSON ledger. A reply is accepted only if it carries all seven strata,
a positive integer size and a valid intensity tag per stratum, and evidence
on every row; anything else is skipped and reported, and the document stays
unrated. Accepted ratings land in corpus/rating/ratings/<family>/<rater>/,
where `python scripts/rating-agreement.py` picks them up. Re-running resumes
at the first unrated document.

Only public- and context-tier documents are rated here, because they carry
their own substrate. A corpus-tier document is judged against a knowledge
base the model cannot read through this script, and a rater who cannot check
whether content is retrievable is pushed toward `Original`.

`--family` names the model family (raters of one family share its biases, so
agreement within a family says less than agreement across families);
`--rater` distinguishes independent runs of the same family.

`--max-tokens` covers the whole reply. A reasoning model spends most of its
budget before it emits the answer, and a ceiling sized for the answer alone
returns empty content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
RATING = ROOT / "corpus" / "rating"
STRATA = ("grammatica", "dialectica", "rhetorica", "arithmetica",
          "geometria", "musica", "astronomia")
TAGS = ("Stock", "Implied", "Selected", "Original")


def _docs() -> list[dict[str, str]]:
    data = cast("dict[str, Any]", json.loads(
        (RATING / "documents.json").read_text(encoding="utf-8")))
    docs = cast("list[dict[str, str]]", data["documents"])
    return [d for d in docs if d["tier"] in ("public", "context")]


def _prompt(doc: dict[str, str], body: str) -> str:
    protocol = (RATING / "protocol.md").read_text(
        encoding="utf-8").split("## The task", 1)[1]
    return (
        f"DOCUMENT ID: {doc['id']}\n"
        f"TELOS: {doc['telos']}\n"
        f"SUBSTRATE: {doc['substrate']}\n\n"
        f"## The task{protocol}\n\n"
        f"--- DOCUMENT ---\n{body}\n--- END ---\n"
    )


def _extract(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return cast("dict[str, Any]", json.loads(m.group(0)))
    except json.JSONDecodeError:
        return None


def validate(ledger: dict[str, Any]) -> str | None:
    """The reason a ledger is unusable, or None if it is valid."""
    if set(ledger) != set(STRATA):
        return f"strata {sorted(ledger)} are not the seven"
    for stratum, row in ledger.items():
        row = cast("dict[str, Any]", row)
        if row.get("intensity") not in TAGS:
            return f"{stratum}: unknown intensity {row.get('intensity')!r}"
        size = row.get("compressed")
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            return f"{stratum}: compressed must be a positive integer, got {size!r}"
        if not str(row.get("evidence", "")).strip():
            return f"{stratum}: no evidence"
    return None


def rate(doc: dict[str, str], args: argparse.Namespace) -> dict[str, Any] | None:
    body = (ROOT / "corpus" / "specimens" / doc["id"] / "text.md").read_text(
        encoding="utf-8")
    payload = json.dumps({
        "model": args.model,
        "messages": [{"role": "user", "content": _prompt(doc, body)}],
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }).encode()
    headers = {"Content-Type": "application/json"}
    key = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        args.base_url.rstrip("/") + "/chat/completions", payload, headers)
    with urllib.request.urlopen(req, timeout=args.timeout) as r:  # noqa: S310
        out = cast("dict[str, Any]", json.load(r))
    msg = cast("dict[str, Any]", out["choices"][0]["message"])
    parsed = _extract(str(msg.get("content") or ""))
    if parsed is None:
        print("    no JSON object in the reply")
        return None
    ledger = cast("dict[str, Any]", parsed.get("ledger", {}))
    problem = validate(ledger)
    if problem:
        print(f"    {problem}")
        return None
    for row in ledger.values():
        row["compressed"] = int(row["compressed"])
    rating: dict[str, Any] = {
        "doc": doc["id"], "family": args.family, "rater": args.rater,
        "model": args.model, "ledger": ledger,
    }
    notes = str(parsed.get("notes", "")).strip()
    if notes:
        rating["notes"] = notes
    return rating


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0].strip())
    ap.add_argument("--base-url", required=True,
                    help="OpenAI-compatible API root, e.g. http://127.0.0.1:8080/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--family", required=True, help="model family, e.g. llama")
    ap.add_argument("--rater", required=True, help="id of this run, e.g. r1")
    ap.add_argument("--api-key-env", default="",
                    help="name of the environment variable holding the API key")
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--timeout", type=int, default=1200, help="seconds per document")
    args = ap.parse_args()

    out_dir = RATING / "ratings" / args.family / args.rater
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = _docs()
    t0 = time.time()
    for i, doc in enumerate(docs, 1):
        target = out_dir / f"{doc['id']}.json"
        if target.is_file():
            print(f"  [{i}/{len(docs)}] {doc['id']}: already rated")
            continue
        print(f"  [{i}/{len(docs)}] {doc['id']} ...", flush=True)
        try:
            rating = rate(doc, args)
        except Exception as exc:
            print(f"    request failed: {exc!r}")
            continue
        if rating is None:
            continue
        target.write_text(json.dumps(rating, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8", newline="\n")
        print(f"    ok ({time.time() - t0:.0f}s elapsed)")
    done = len(list(out_dir.glob("*.json")))
    print(f"{args.family}/{args.rater}: {done}/{len(docs)} rated")
    return 0 if done == len(docs) else 1


if __name__ == "__main__":
    sys.exit(main())
