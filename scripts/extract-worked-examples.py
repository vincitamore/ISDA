#!/usr/bin/env python3
"""Copy the three worked-example bodies from examples.md into their specimens.

The copy is by byte range, never a retype. Each ledger is scored against a raw
length measured from the fenced block in examples.md, and a retyped body, even
one that reads identically, can move those bytes and with them every metric
derived from the ledger.

Run from the repo root. Idempotent: rewrites each text.md and reports byte
counts only. Exits 64 on any length mismatch, which means examples.md has
changed under the ledgers.
"""

from __future__ import annotations

import sys
from pathlib import Path

SOURCE = Path("examples.md")
SPECIMEN_ROOT = Path("corpus/specimens")

# (specimen, first body line, last body line, expected bytes)
# Line numbers are 1-indexed and name the lines inside the fence. Expected byte
# counts are the "Raw length: N bytes (measured)" figures in examples.md that
# the ledgers are scored against. Specimen names describe the role the
# specimen plays in the corpus; the topic is in each specimen's analysis.md.
BLOCKS = [
    ("lyric-musica-original", 16, 29, 577),
    ("argumentative-dialectica-original", 150, 266, 6552),
    ("expository-all-stock", 368, 462, 5643),
]


def main() -> int:
    if not SOURCE.exists():
        print(f"error: {SOURCE} not found; run from the repo root", file=sys.stderr)
        return 64

    lines = SOURCE.read_text(encoding="utf-8").split("\n")
    failures: list[str] = []

    for slug, first, last, expected in BLOCKS:
        body = "\n".join(lines[first - 1 : last]) + "\n"
        raw = body.encode("utf-8")
        out_dir = SPECIMEN_ROOT / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "text.md"
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)

        delta = len(raw) - expected
        status = "ok" if delta == 0 else f"MISMATCH {delta:+d}"
        print(f"{slug:26s} lines {first}-{last:<4d} {len(raw):6d} B  expected {expected:6d}  {status}")
        if delta != 0:
            failures.append(f"{slug}: wrote {len(raw)} B, ledger expects {expected} B")

    if failures:
        print("\nexamples.md has changed under the ledgers:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 64

    print(f"\n{len(BLOCKS)} specimen bodies extracted, all byte-exact against their ledgers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
