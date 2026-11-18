"""
The four CLI verbs: measure, analyze, score, measures.

The set is kept to four on purpose: each answers a question that recurs, and
a verb kept for symmetry rather than use is dead weight the next reader must
rule out.

Each verb returns (payload, exit_code); `main` in cli/__init__.py owns the
envelope, the rendering, and the process exit. Payloads are JSON-safe dicts, so
the same object feeds --json and the human renderer.

The report/detail split. A report is O(1) in document length: bounded by the
registry size, safe to log, diff, and keep. Per-unit rows (one line per block)
are O(n) and opt-in via --detail PATH, written as JSONL. Inlining them in the
report would make every report as large as its document and every diff
unreadable.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

from ..core import tokens
from ..core.blocks import BlockKind, PROSE_KINDS
from ..core.document import Document, scrub_inline
from ..core.features import FeatureContext
from ..framework.metrics import score_ledger as _score_ledger
from ..framework.strata import STRATA
from ..framework.uncertainty import precision_note as _precision_note
from ..kernel import registry
from ..kernel.descriptor import MeasureUnavailable


class VerbError(Exception):
    """A user-facing failure: `code` names the class, the message says what to do."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _read_text(path: str, what: str = "file") -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise VerbError("io", f"no such {what}: {path}") from None
    except UnicodeDecodeError as exc:
        raise VerbError(
            "encoding",
            f"{path} is not valid UTF-8: {exc}. Re-encode the file, or pipe a "
            "decoded copy through stdin.",
        ) from None
    except OSError as exc:
        raise VerbError("io", f"cannot read {what} {path}: {exc}") from None


def _load_ledger(path: str) -> dict[str, Any]:
    raw = _read_text(path, "ledger")
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VerbError("bad-ledger", f"{path}: invalid JSON: {exc}") from None
    if not isinstance(parsed, dict):
        raise VerbError("bad-ledger", f"{path}: ledger must be a JSON object")
    return {str(k): v for k, v in cast("dict[Any, Any]", parsed).items()}


def _scored_or_raise(ledger: dict[str, Any]) -> dict[str, Any]:
    result = _score_ledger(ledger)
    if not result.get("ok"):
        errs = result.get("errors", [])
        raise VerbError("bad-ledger", "; ".join(str(e) for e in errs))
    return result


def _measure_rows(doc: Document) -> list[dict[str, Any]]:
    """Every non-retired registered measure evaluated on this document.

    Retired measures emit no value here by design: an invalid number corrupts
    whatever is reasoned from the report. Their records live in the `measures`
    verb.
    """
    import isda.measures  # noqa: F401  # import-time registration
    assert isda.measures

    rows: list[dict[str, Any]] = []
    for desc in sorted(registry.all_measures(), key=lambda m: m.id):
        row: dict[str, Any] = {
            "id": desc.id,
            "version": desc.version,
            "kind": desc.kind.value,
            "status": desc.status.value,
            "strata": list(desc.strata),
        }
        try:
            row["value"] = desc.compute(FeatureContext(doc, frozenset(desc.requires)))
        except MeasureUnavailable as exc:
            # A statement about the machine, not the text: the optional
            # backend is absent here. Reported separately from "error" because
            # an error reads as a fault in the measure, and this is not one.
            row["value"] = None
            row["unavailable"] = str(exc)
        except Exception as exc:  # a raising measure is recorded in its row, not fatal
            row["value"] = None
            row["error"] = repr(exc)
        rows.append(row)
    return rows


def _write_detail(doc: Document, path: str) -> int:
    """One JSON line per non-blank block: the O(n) side of the report/detail split."""
    lines: list[str] = []
    for i, b in enumerate(doc.blocks):
        if b.kind is BlockKind.BLANK:
            continue
        row: dict[str, Any] = {
            "type": "block",
            "index": i,
            "kind": b.kind.value,
            "start": b.span.start,
            "end": b.span.end,
        }
        if b.kind is BlockKind.HEADING:
            row["level"] = b.level
        if b.kind in PROSE_KINDS:
            row["words"] = len(tokens.words(scrub_inline(b.content)))
        lines.append(json.dumps(row, ensure_ascii=False))
    try:
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        raise VerbError("io", f"cannot write detail to {path}: {exc}") from None
    return len(lines)


# ---------------------------------------------------------------- verbs

def measure(path: str, telos: str | None, substrate: str | None,
            detail: str | None) -> tuple[dict[str, Any], int]:
    """Mechanical measurement of one document: counts and registered measures."""
    text = _read_text(path)
    doc = Document.parse(text)
    kinds = Counter(b.kind.value for b in doc.blocks if b.kind is not BlockKind.BLANK)
    prose_text = doc.prose_text

    payload: dict[str, Any] = {
        "file": path,
        "telos": telos,
        "substrate": substrate,
        # The source/prose split is explicit: document size is a source-level
        # fact; word, sentence and paragraph statistics are prose-view facts.
        # The report states which is which instead of leaving it to be inferred.
        "source": {
            "bytes": doc.total_bytes,
            "blocks": dict(sorted(kinds.items())),
        },
        "prose": {
            "bytes": len(prose_text.encode("utf-8")),
            "words": len(tokens.words(prose_text)),
            "sentences": len(tokens.sentence_units(doc)),
            "paragraphs": len(tokens.paragraph_units(doc)),
        },
        "measures": _measure_rows(doc),
        "notes": [
            "source.* is computed on the raw document; prose.* on the "
            "markup-stripped prose view. One shared parse, never mixed.",
            "Measurement, not judgment: stratum classification, intensity "
            "tags, and the ledger are the analyst's work.",
        ],
    }
    if detail:
        payload["detail"] = {"path": detail, "rows": _write_detail(doc, detail)}
    return payload, 0


def score(ledger_path: str, document: str | None,
          substrate_file: str | None) -> tuple[dict[str, Any], int]:
    """Ledger arithmetic: SCR / ND / RI from a completed seven-row ledger."""
    ledger = _load_ledger(ledger_path)
    if document:
        ledger["document"] = _read_text(document, "document")
    if substrate_file:
        ledger["substrate_text"] = _read_text(substrate_file, "substrate")
    result = _scored_or_raise(ledger)
    payload = {k: v for k, v in result.items() if k != "ok"}
    payload["ledger"] = ledger_path
    return payload, 0


def analyze(path: str, ledger_path: str, telos: str | None,
            substrate: str | None) -> tuple[dict[str, Any], int]:
    """The full analysis surface: ledger-first, scalars beneath, evidence last.

    The seven-row stratum profile is the headline artifact; SCR/ND/RI are lossy
    projections of it. The document always travels with the ledger here, so the
    raw-byte coupling and the compression floor are enforced on every run.
    """
    text = _read_text(path)
    ledger = _load_ledger(ledger_path)
    ledger["document"] = text
    scored = _scored_or_raise(ledger)
    doc = Document.parse(text)

    per: dict[str, Any] = scored["per_stratum"]
    ledger_rows = [{"stratum": s, **per[s]} for s in STRATA if s in per]

    warnings: list[str] = []
    if not telos:
        warnings.append(
            "no telos stated: the analysis compresses toward an undefined "
            "target; pass --telos"
        )
    if not substrate:
        warnings.append(
            "no substrate named: retrievability is undefined; pass --substrate"
        )

    payload: dict[str, Any] = {
        "file": path,
        "telos": telos,
        "substrate": substrate,
        "raw_bytes": scored["raw_bytes"],
        "total_compressed": scored["total_compressed"],
        "ledger": ledger_rows,
        "metrics": scored["metrics"],
        # The precision note travels at the point of the numbers, never in a
        # footnote. framework/uncertainty.py states what these figures are and
        # what they are not.
        "precision": _precision_note(),
        "dominant_stratum": scored["dominant_stratum"],
        "dominant_share_of_core": scored["dominant_share_of_core"],
        "arithmetic": scored["arithmetic"],
        "compression_floor": scored["compression_floor"],
        "measures": _measure_rows(doc),
    }
    if warnings:
        payload["warnings"] = warnings
    return payload, 0


def measures(write: bool, check: bool) -> tuple[dict[str, Any], int]:
    """The registry as the durable partition record: active/provisional/retired."""
    import isda.measures  # noqa: F401  # import-time registration
    assert isda.measures

    man = registry.manifest()
    payload: dict[str, Any] = dict(man)

    if write or check:
        from ..corpus import repo_root
        try:
            target = repo_root() / "data" / "measures.json"
        except FileNotFoundError:
            raise VerbError(
                "io",
                "--write/--check need the repo (no corpus/ found above the "
                "package); plain `measures` works anywhere",
            ) from None
        rendered = json.dumps(man, indent=2, ensure_ascii=False) + "\n"
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8", newline="\n")
            payload["written"] = str(target)
        if check:
            on_disk = target.read_text(encoding="utf-8") if target.is_file() else None
            match = on_disk == rendered
            payload["check"] = {"path": str(target), "match": match}
            if not match:
                # Drift exits 1, not 64: the run itself succeeded; the registry
                # changed and the checked-in manifest did not. Regenerate with
                # --write.
                return payload, 1
    return payload, 0
