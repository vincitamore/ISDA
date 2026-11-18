"""
SCR / ND / RI from a completed stratum ledger: the metric arithmetic.

Arithmetic only, no judgment: the analyst supplies the compressed sizes and
intensity tags; this function reproduces the three metrics exactly as SKILL.md
Step 5 defines them and shows the per-stratum contributions.

ND and RI are byte-weighted sums over compressed sizes, not unweighted
per-stratum averages. Estimating them by eye is error-prone, which is why this
function computes them.

This is the package's single implementation, used by the CLI `score`/`analyze`
verbs and by the specimen runner. The standalone `isda_preprocess.py` carries
its own copy because a prose-only skill directory has no package to import;
`tests/test_metrics_parity.py` scores every specimen ledger through both and
asserts identical output, so the two cannot drift apart without a test
failing.

Expected ledger shape:
    {"raw_bytes": 14304,
     "strata": {"grammatica": {"compressed": 85, "intensity": "Selected"}, ...},
     "document": "...optional full text for the compression floor...",
     "substrate_text": "...optional priming dictionary..."}
"""

from __future__ import annotations

from typing import Any, Mapping, cast

from .floor import as_utf8_bytes, compress_upper_bound
from .strata import ND_WEIGHT, RI_WEIGHT, STRATA


def score_ledger(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Score a ledger. Returns {'ok': True, ...} or {'ok': False, 'errors': [...]}."""
    errors: list[str] = []

    raw_field = ledger.get("raw_bytes")
    raw = 0.0
    if isinstance(raw_field, (int, float)) and not isinstance(raw_field, bool) and raw_field > 0:
        raw = float(raw_field)
    else:
        errors.append("raw_bytes must be a positive number")

    strata_field = ledger.get("strata")
    strata: Mapping[str, Any]
    if not isinstance(strata_field, Mapping):
        errors.append("strata must be an object keyed by the seven stratum names")
        strata = {}
    else:
        strata = cast("Mapping[str, Any]", strata_field)

    missing = [s for s in STRATA if s not in strata]
    if missing:
        errors.append(f"missing strata: {', '.join(missing)}")
    unknown = [s for s in strata if s not in STRATA]
    if unknown:
        errors.append(f"unknown strata: {', '.join(unknown)}")

    rows: dict[str, tuple[float, str]] = {}
    for name in STRATA:
        row = strata.get(name)
        if not isinstance(row, Mapping):
            continue
        row_m = cast("Mapping[str, Any]", row)
        size = row_m.get("compressed")
        tag = row_m.get("intensity")
        if not isinstance(size, (int, float)) or size < 0:
            errors.append(f"{name}: compressed must be a non-negative number")
            continue
        if tag not in ND_WEIGHT:
            errors.append(
                f"{name}: intensity must be one of Stock, Implied, Selected, Original "
                f"(got {tag!r})"
            )
            continue
        rows[name] = (float(size), str(tag))

    if errors:
        return {"ok": False, "errors": errors}

    total = sum(size for size, _ in rows.values())

    # A compressed core larger than the document it compresses is incoherent.
    # This is also the weak form of the compression floor: K_tau <= |d|.
    if total > raw:
        return {"ok": False, "errors": [
            f"total compressed ({total:g} B) exceeds raw_bytes ({raw:g} B). "
            "The telos-preserving core cannot be larger than the text; check the "
            "ledger rows or the measured raw length."
        ]}
    if total <= 0:
        return {"ok": False, "errors": ["total compressed size is zero"]}

    # The compression floor: the sum of compressed sizes must not exceed
    # C(d | D). A violation is a provable estimation error: the ledger claims a
    # telos-preserving core larger than a known lossless encoding of the whole
    # document.
    floor_info: dict[str, Any] = {
        "checked": False,
        "reason": "no document supplied, so the floor was not checked",
    }
    doc_field = ledger.get("document")
    if doc_field is not None:
        try:
            doc_bytes = as_utf8_bytes(doc_field, "document")
        except TypeError as exc:
            return {"ok": False, "errors": [str(exc)]}
        if len(doc_bytes) != int(raw):
            return {"ok": False, "errors": [
                f"document is {len(doc_bytes)} bytes but raw_bytes is {raw:g}; "
                "the SCR numerator and the compression floor must describe the "
                "same object."
            ]}
        sub_bytes: bytes | None = None
        sub_field = ledger.get("substrate_text")
        if sub_field is not None:
            try:
                sub_bytes = as_utf8_bytes(sub_field, "substrate_text")
            except TypeError as exc:
                return {"ok": False, "errors": [str(exc)]}
        c_bound, mode = compress_upper_bound(doc_bytes, sub_bytes)
        if total > c_bound:
            return {"ok": False, "errors": [
                f"total compressed ({total:g} B) exceeds the zlib {mode} upper bound "
                f"C(d|D)={c_bound} B. The telos-preserving core cannot exceed a lossless "
                f"compression of the document, so at least one ledger row is overstated. "
                f"(One-sided: this catches cores claimed too large and cannot detect "
                f"cores claimed too small.)"
            ]}
        floor_info = {
            "checked": True,
            "mode": mode,
            "C": c_bound,
            "margin_bytes": round(c_bound - total, 2),
            "SCR_lower_bound": round(raw / c_bound, 4),
            "note": ("Passing is necessary but not sufficient: it does not validate "
                     "any estimate, and only means no row is provably impossible."),
        }

    contributions: dict[str, Any] = {}
    nd_num = 0.0
    ri_num = 0.0
    for name, (size, tag) in rows.items():
        nd_c = size * ND_WEIGHT[tag]
        ri_c = size * RI_WEIGHT[tag]
        nd_num += nd_c
        ri_num += ri_c
        contributions[name] = {
            "compressed": size,
            "intensity": tag,
            "share_of_core": round(size / total, 4),
            "nd_contribution": round(nd_c, 3),
            "ri_contribution": round(ri_c, 3),
        }

    dominant = max(rows, key=lambda n: rows[n][0])

    return {
        "ok": True,
        "raw_bytes": raw_field,
        "total_compressed": round(total, 2),
        "metrics": {
            "SCR": round(raw / total, 2),
            "ND": round(nd_num / total, 3),
            "RI": round(ri_num / total, 3),
        },
        "arithmetic": {
            "SCR": f"{raw} / {round(total, 2)}",
            "ND": f"{round(nd_num, 2)} / {round(total, 2)}",
            "RI": f"{round(ri_num, 2)} / {round(total, 2)}",
        },
        "per_stratum": contributions,
        "dominant_stratum": dominant,
        "dominant_share_of_core": round(rows[dominant][0] / total, 4),
        "compression_floor": floor_info,
        "notes": [
            "ND and RI are byte-weighted over compressed sizes, not over raw bytes "
            "and not averaged per stratum.",
            'RI answers "how much of the irreducible core is a substrate pointer", '
            'not "how much of this text could be looked up". An all-Stock ledger '
            "scores exactly 1.0.",
            f"{dominant} carries {round(rows[dominant][0] / total * 100)}% of the core, "
            "so it dominates ND by construction; read the stratum profile alongside "
            "the number.",
        ],
    }
