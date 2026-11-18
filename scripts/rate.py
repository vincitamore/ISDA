"""
The guided rating walk-through for a human rater.

    python scripts/rate.py [--rater NAME] [--tags-only]

It picks the next document the rater has not rated, shows it with its telos
and substrate, asks one or two plain questions per stratum, and writes the
rating file itself. Quit at any prompt with `q`; the next run resumes at the
first unrated document.

A human rating is one more rater family, not a ground truth. K is
uncomputable and no rater, human or model, has access to a true compressed
size. Where a human and a model agree on a stratum their tags are
interchangeable there; where they differ, neither is the reference.

Private-corpus documents (ids starting `b-`) can be rated only on a machine
that holds the corpus cache; elsewhere they are skipped.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "corpus" / "rating" / "documents.json"

# The corpus includes non-ASCII text, and a Windows console defaults to
# cp1252, which raises UnicodeEncodeError on the first such character. An
# unrenderable glyph is replaced so the walk-through keeps running; the
# prompts themselves are ASCII for the same reason.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
STRATA: tuple[tuple[str, str, str], ...] = (
    ("grammatica", "sentence-level form",
     "The sentence shapes, clause structure, register, any coined phrases."),
    ("dialectica", "the inferential moves",
     "Claims the text argues or derives, as opposed to ones it simply states."),
    ("rhetorica", "curatorial decisions",
     "What was selected, in what order, framed how, out of what visible options."),
    ("arithmetica", "propositional content",
     "The atomic assertions the text carries, as a body of countable claims."),
    ("geometria", "document architecture",
     "Sectioning, hierarchy, layout: the shape of the page."),
    ("musica", "rhythm and prosody",
     "How information is paced within sentences and lines; stress, cadence, figures."),
    ("astronomia", "trajectory",
     "How intensity and argument unfold start to finish; the arc."),
)

TAGS: dict[str, tuple[str, str]] = {
    "s": ("Stock", "I could look this up in the substrate"),
    "i": ("Implied", "not stated there, but follows by ordinary reasoning"),
    "e": ("Selected", "a choice the author made from visible options"),
    "o": ("Original", "it had to be originated: not lookup, not derivation, not choice"),
}

# Log-spaced buckets. Raters' size estimates differ multiplicatively (model
# raters by about 1.2x), so a choice among sizes a factor of three apart
# loses little against an integer byte count and is far easier to answer.
BUCKETS: dict[str, tuple[str, int]] = {
    "1": ("a pointer: a few words naming it", 40),
    "2": ("a sentence", 120),
    "3": ("a paragraph", 400),
    "4": ("a section", 1200),
    "5": ("a page or more", 3500),
}


def _docs() -> list[dict[str, str]]:
    data = cast("dict[str, Any]", json.loads(DOCS.read_text(encoding="utf-8")))
    docs = cast("list[dict[str, str]]", data["documents"])
    # Interleave specimens with private-corpus documents so that any prefix
    # of the list is a mix, and a rater who stops early has not rated one
    # kind only.
    spec = [d for d in docs if d["kind"] == "specimen"]
    block = [d for d in docs if d["kind"] != "specimen"]
    out: list[dict[str, str]] = []
    for i in range(max(len(spec), len(block))):
        if i < len(spec):
            out.append(spec[i])
        if i < len(block):
            out.append(block[i])
    return out


def _text_path(doc: dict[str, str]) -> Path:
    if doc["kind"] == "specimen":
        return ROOT / "corpus" / "specimens" / doc["id"] / "text.md"
    return ROOT / "corpus" / "cache" / "block-b" / f"{doc['id']}.md"


def _out_dir(rater: str) -> Path:
    d = ROOT / "corpus" / "rating" / "ratings" / "human" / rater
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ask(prompt: str, valid: set[str]) -> str | None:
    """Read one key. Returns None if the rater wants to stop."""
    while True:
        try:
            raw = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw in ("q", "quit"):
            return None
        if raw in valid:
            return raw
        print(f"   (enter one of: {', '.join(sorted(valid))} - or q to stop)")


def _show(doc: dict[str, str], n: int, total: int, done: int) -> None:
    path = _text_path(doc)
    body = path.read_text(encoding="utf-8")
    print("\n" + "=" * 74)
    print(f"Document {n} of {total}   ({done} rated so far)")
    print(f"  {doc['id']}       {len(body.encode('utf-8')):,} bytes")
    print(f"  TELOS      {doc['telos']}")
    print(f"  SUBSTRATE  {doc['substrate']}")
    print("=" * 74)
    lines = body.splitlines()
    head = lines[:45]
    print("\n".join("  " + line for line in head))
    if len(lines) > 45:
        print(f"\n  ... {len(lines) - 45} more lines - press [v] at any prompt "
              f"to open the whole file")
    print()


def _open_in_editor(doc: dict[str, str]) -> None:
    path = _text_path(doc)
    try:
        if sys.platform == "win32":
            subprocess.run(["cmd", "/c", "start", "", str(path)], check=False)
        else:
            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open",
                            str(path)], check=False)
    except Exception as exc:  # a failed opener must not end the walk-through
        print(f"   (could not open an editor: {exc} - the file is at {path})")


def rate_document(doc: dict[str, str], n: int, total: int, done: int,
                  rater: str, ask_size: bool) -> bool:
    """Walk one document. Returns False if the rater stopped."""
    _show(doc, n, total, done)
    ledger: dict[str, dict[str, Any]] = {}

    for i, (key, gloss, helptext) in enumerate(STRATA, 1):
        print(f"- {i}/7   {key.upper()} - {gloss} " + "-" * max(0, 44 - len(key) - len(gloss)))
        print(f"  {helptext}\n")
        print("  Where does it come from?")
        for k, (tag, meaning) in TAGS.items():
            print(f"    [{k}] {tag:9s} {meaning}")
        print("    [?] not sure - skip this row")
        print("    [v] open the document       [q] stop and save")

        choice = _ask("  > ", set(TAGS) | {"?", "v"})
        while choice == "v":
            _open_in_editor(doc)
            choice = _ask("  > ", set(TAGS) | {"?", "v"})
        if choice is None:
            return False
        if choice == "?":
            print("   skipped\n")
            continue
        tag = TAGS[choice][0]

        size: int | None = None
        if ask_size:
            print("\n  How big a note would you need to reconstruct it?")
            for k, (label, _) in BUCKETS.items():
                print(f"    [{k}] {label}")
            print("    [?] not sure - skip")
            b = _ask("  > ", set(BUCKETS) | {"?"})
            if b is None:
                return False
            if b != "?":
                size = BUCKETS[b][1]

        ledger[key] = {"intensity": tag, "compressed": size}
        print()

    if not ledger:
        print("  (nothing recorded for this document)\n")
        return True

    out = _out_dir(rater) / f"{doc['id']}.json"
    out.write_text(json.dumps({
        "doc": doc["id"],
        "family": "human",
        "rater": rater,
        "instrument": "scripts/rate.py: guided walk-through, log-spaced size buckets",
        "ledger": ledger,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"  OK saved {out.relative_to(ROOT)}\n")
    return True


def main(argv: list[str]) -> int:
    rater = "human-1"
    ask_size = "--tags-only" not in argv
    for i, a in enumerate(argv):
        if a == "--rater" and i + 1 < len(argv):
            rater = argv[i + 1]

    docs = _docs()
    out_dir = _out_dir(rater)
    rated = {p.stem for p in out_dir.glob("*.json")}
    available = [d for d in docs if _text_path(d).is_file()]
    pending = [d for d in available if d["id"] not in rated]

    print("\n  ISDA rating pass -", rater)
    print(f"  {len(rated)} of {len(available)} documents rated.")
    if len(available) < len(docs):
        print(f"  ({len(docs) - len(available)} private-corpus documents are not "
              f"on this machine and are skipped.)")
    if not pending:
        print("\n  All done. Nothing left to rate.")
        print("  Run: python scripts/rating-agreement.py\n")
        return 0
    print("  Two questions per stratum, seven strata per document."
          if ask_size else "  One question per stratum, seven strata per document.")
    print("  Stop any time with q - progress is saved per document.")
    print("  There are no wrong answers: the study measures whether a human")
    print("  and a model read a text the same way, not who is right.\n")

    for doc in pending:
        n = available.index(doc) + 1
        if not rate_document(doc, n, len(available), len(rated), rater, ask_size):
            print("\n  Stopped. Run the same command to pick up here.\n")
            return 0
        rated.add(doc["id"])

    print("  All documents rated. Run: python scripts/rating-agreement.py\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
