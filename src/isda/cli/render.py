"""
Human rendering of verb payloads. One renderer per verb, all pure functions
payload -> str, so what a human reads and what --json emits are projections of
the same object and cannot disagree.

The analyze layout puts the seven-row stratum profile first and the scalar
metrics beneath it: a scalar is a lossy projection of the profile, and
rendering ND or any other scalar first invites reading it standalone. The
precision stamp renders at the point of the numbers, not in a footnote.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence, cast


def _fmt_value(v: object) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _measure_lines(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    width = max((len(str(r["id"])) for r in rows), default=0)
    for r in rows:
        flags = str(r["kind"])
        if r["status"] != "active":
            flags += f", {r['status']}"
        value = "unavailable" if "unavailable" in r else _fmt_value(r.get("value"))
        line = f"  {str(r['id']).ljust(width)}  {value}  ({flags})"
        if "error" in r:
            line += f"  ERROR {r['error']}"
        out.append(line)
        if "unavailable" in r:
            # The reason names the extra or the pinned version to install.
            out.append(f"      {r['unavailable']}")
    return out


def render_measure(p: Mapping[str, Any]) -> str:
    src: Mapping[str, Any] = p["source"]
    prose: Mapping[str, Any] = p["prose"]
    blocks: Mapping[str, Any] = src["blocks"]
    lines: list[str] = [
        f"isda measure: {p['file']}",
        f"  telos:     {p['telos'] or '(none stated)'}",
        f"  substrate: {p['substrate'] or '(none named)'}",
        "",
        f"  source  {src['bytes']} B · blocks: "
        + (", ".join(f"{k} {v}" for k, v in blocks.items()) or "none"),
        f"  prose   {prose['bytes']} B · {prose['words']} words · "
        f"{prose['sentences']} sentences · {prose['paragraphs']} paragraphs",
        "",
        "measures (registered, non-retired):",
        *_measure_lines(cast("Sequence[Mapping[str, Any]]", p["measures"])),
    ]
    detail = p.get("detail")
    if detail is not None:
        lines.append("")
        lines.append(f"detail: {detail['rows']} block rows -> {detail['path']}")
    for note in cast("Sequence[str]", p.get("notes", [])):
        lines.append(f"note: {note}")
    return "\n".join(lines)


def _metrics_block(p: Mapping[str, Any]) -> list[str]:
    metrics: Mapping[str, Any] = p["metrics"]
    arithmetic: Mapping[str, Any] = p.get("arithmetic", {})
    out: list[str] = []
    for name in ("SCR", "ND", "RI"):
        line = f"  {name:3s}  {metrics[name]}"
        if name in arithmetic:
            line += f"  (= {arithmetic[name]})"
        out.append(line)
    return out


def _floor_line(floor: Mapping[str, Any]) -> str:
    if not floor.get("checked"):
        return f"compression floor: not checked ({floor.get('reason', '')})"
    return (f"compression floor: OK ({floor['mode']}, C={floor['C']} B, "
            f"margin {floor['margin_bytes']} B)")


def _precision_line(note: object) -> str:
    """The metrics heading, carrying the inter-rater interval and its scope."""
    if not isinstance(note, Mapping):
        return f"metrics (precision: {note}):"
    stamp = cast("Mapping[str, Any]", note)
    sd = cast("Mapping[str, Any]", stamp.get("median_sd", {}))
    spread = " · ".join(f"{name} ±{value}" for name, value in sd.items())
    return (f"metrics (median inter-rater SD: {spread}; reliability, not "
            "validity; raters of one model family):")


def render_score(p: Mapping[str, Any]) -> str:
    per: Mapping[str, Any] = p["per_stratum"]
    rows = [(name, cast("Mapping[str, Any]", row)) for name, row in per.items()]
    width = max(len(n) for n, _ in rows)
    lines: list[str] = [
        f"isda score: {p['ledger']}",
        f"  raw {p['raw_bytes']} B · core {float(p['total_compressed']):g} B",
        "",
        "metrics (byte-weighted over compressed sizes, never estimated):",
        *_metrics_block(p),
        "",
        "per stratum:",
    ]
    for name, row in rows:
        lines.append(
            f"  {name.ljust(width)}  {row['compressed']:>7g} B  "
            f"{str(row['intensity']):8s}  {row['share_of_core']:6.1%} of core"
        )
    lines.append("")
    lines.append(f"dominant: {p['dominant_stratum']} "
                 f"({float(p['dominant_share_of_core']):.1%} of core)")
    lines.append(_floor_line(cast("Mapping[str, Any]", p["compression_floor"])))
    return "\n".join(lines)


def render_analyze(p: Mapping[str, Any]) -> str:
    ledger_rows = cast("Sequence[Mapping[str, Any]]", p["ledger"])
    width = max(len(str(r["stratum"])) for r in ledger_rows)
    lines: list[str] = [
        f"ISDA analysis: {p['file']}",
        f"  telos:     {p['telos'] or '(none stated)'}",
        f"  substrate: {p['substrate'] or '(none named)'}",
        f"  raw {p['raw_bytes']} B · core {float(p['total_compressed']):g} B",
        "",
        "stratum ledger (the headline: scalars below are its lossy projection):",
    ]
    for r in ledger_rows:
        lines.append(
            f"  {str(r['stratum']).ljust(width)}  {r['compressed']:>7g} B  "
            f"{str(r['intensity']):8s}  {r['share_of_core']:6.1%} of core"
        )
    lines += [
        "",
        _precision_line(p["precision"]),
        *_metrics_block(p),
        f"  dominant: {p['dominant_stratum']} "
        f"({float(p['dominant_share_of_core']):.1%} of core; it sets ND almost alone, "
        "so read the profile above alongside the number)",
        "",
        _floor_line(cast("Mapping[str, Any]", p["compression_floor"])),
        "",
        "mechanical evidence (registered measures on this document):",
        *_measure_lines(cast("Sequence[Mapping[str, Any]]", p["measures"])),
    ]
    for w in cast("Sequence[str]", p.get("warnings", [])):
        lines.append(f"WARNING: {w}")
    return "\n".join(lines)


def render_measures(p: Mapping[str, Any]) -> str:
    rows = cast("Sequence[Mapping[str, Any]]", p["measures"])
    id_w = max(len(str(r["id"])) for r in rows)
    st_w = max(len(str(r["status"])) for r in rows)
    lines: list[str] = [
        f"registered measures ({len(rows)}), the partition record; "
        "data/measures.json is the generated artifact:",
    ]
    for r in rows:
        strata = ",".join(cast("Sequence[str]", r["strata"])) or "-"
        lines.append(
            f"  {str(r['id']).ljust(id_w)}  {str(r['status']).ljust(st_w)}  "
            f"{str(r['kind']):11s}  strata: {strata}"
        )
        if "retired_because" in r:
            lines.append(f"      retired: {str(r['retired_because'])[:120]}")
    written = p.get("written")
    if written:
        lines.append(f"written: {written}")
    check = p.get("check")
    if check is not None:
        check_m = cast("Mapping[str, Any]", check)
        state = "matches the registry" if check_m["match"] else \
            "DRIFT (regenerate with `python -m isda measures --write`)"
        lines.append(f"check: {check_m['path']} {state}")
    return "\n".join(lines)
