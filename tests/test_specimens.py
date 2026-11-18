"""
Specimen tests: the five-file contract, the raw-byte coupling, the assertion
runner's verdict semantics, and the standing gate that reports STALE whenever
a pin differs from the state re-derived from the specimen.

Specimens are committed text, so every test here runs on every machine. An
assertion that needs a corpus block or an optional backend this machine
lacks is UNTESTABLE here and does not count as drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.corpus import repo_root  # noqa: E402
from isda.specimens import (  # noqa: E402
    FIVE_FILES, AssertionResult, Specimen, SpecimenInvalid,
    load_specimen, load_specimens, run_assertion, summary_line, verify_specimens,
)

SPECIMENS = repo_root() / "corpus" / "specimens"

LEDGER: dict[str, Any] = {
    "raw_bytes": 6,
    "strata": {s: {"compressed": 10, "intensity": "Stock"} for s in (
        "grammatica", "dialectica", "rhetorica", "arithmetica",
        "geometria", "musica", "astronomia")},
}


def _write_specimen(root: Path, ledger: dict[str, Any]) -> Path:
    d = root / "fixture-specimen"
    d.mkdir()
    (d / "text.md").write_text("hello\n", encoding="utf-8", newline="\n")
    (d / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (d / "assertions.json").write_text(json.dumps(
        {"specimen": "fixture-specimen", "assertions": []}), encoding="utf-8")
    (d / "analysis.md").write_text("# fixture\n", encoding="utf-8")
    return d


def _fake_specimen() -> Specimen:
    return Specimen("fixture", Path("."), "hello\n", LEDGER, [], None)


# ---------- the committed corpus (runs everywhere) ----------

def test_all_specimens_load_and_carry_the_five_files():
    specimens = load_specimens()
    assert len(specimens) >= 3
    for sp in specimens:
        for name in FIVE_FILES:
            assert (sp.path / name).is_file(), f"{sp.slug}: missing {name}"


def test_every_assertion_verdict_is_pinned():
    """Every declared assertion has a pinned verdict, since an unpinned
    verdict could change without verify reporting it."""
    for sp in load_specimens():
        assert sp.expected is not None, f"{sp.slug}: unpinned"
        pinned = set(sp.expected["verdicts"])
        declared = {a["id"] for a in sp.assertions}
        assert pinned == declared, f"{sp.slug}: {pinned ^ declared}"


def test_verify_reports_clean():
    """The standing gate: every pin re-derives to the same values and verdicts.
    A failure here is a real change to investigate before a deliberate re-pin,
    not an intermittent failure."""
    assert verify_specimens() == 0


# ---------- contract enforcement (temp fixtures) ----------

def test_body_moving_under_ledger_raises(tmp_path: Path):
    bad = dict(LEDGER, raw_bytes=999)
    d = _write_specimen(tmp_path, bad)
    with pytest.raises(SpecimenInvalid, match="moved under"):
        load_specimen(d)


def test_ledger_tolerates_no_extra_keys(tmp_path: Path):
    """Provenance belongs in analysis.md; the ledger holds exactly the keys
    the scorer reads."""
    bad = dict(LEDGER, provenance="examples.md")
    d = _write_specimen(tmp_path, bad)
    with pytest.raises(SpecimenInvalid, match="exactly"):
        load_specimen(d)


def test_ledger_requires_all_seven_strata(tmp_path: Path):
    bad: dict[str, Any] = {"raw_bytes": 6,
                           "strata": {k: v for k, v in LEDGER["strata"].items()
                                      if k != "musica"}}
    d = _write_specimen(tmp_path, bad)
    with pytest.raises(SpecimenInvalid, match="seven"):
        load_specimen(d)


# ---------- runner verdict semantics (no subprocess) ----------

SCORED: dict[str, Any] = {
    "metrics": {"SCR": 2.0, "ND": 0.5, "RI": 0.1},
    "dominant_stratum": "musica",
    "per_stratum": {"musica": {"share_of_core": 0.47}},
    "compression_floor": {"checked": False},
}


def test_metric_outside_its_bounds_fails_and_reports_the_value():
    r = run_assertion(_fake_specimen(),
                      {"id": "x", "claim": "c", "kind": "metric",
                       "metric": "scr", "between": [0.0, 1.0]}, SCORED)
    assert r.verdict == "FAILING" and "2.0" in r.detail


def test_unregistered_measure_is_untestable_not_failing():
    """A claim whose measure is not registered is UNTESTABLE rather than
    FAILING, so it stays visible as an obligation."""
    r = run_assertion(_fake_specimen(),
                      {"id": "x", "claim": "c", "kind": "measure",
                       "measure": "musica.does-not-exist", "min": 0}, SCORED)
    assert r.verdict == "UNTESTABLE" and "not registered" in r.detail


def test_judgment_is_always_untestable():
    r = run_assertion(_fake_specimen(),
                      {"id": "x", "claim": "c", "kind": "judgment"}, SCORED)
    assert r.verdict == "UNTESTABLE"


def test_quantile_without_its_block_is_untestable_and_not_drift(tmp_path):
    """On a clone where block B is not built, a quantile assertion cannot
    run. It reports the gap, and verify does not call the pinned PASSING
    stale."""
    import shutil
    from pathlib import Path

    from isda.specimens import _drift_keys  # pyright: ignore[reportPrivateUsage]
    (tmp_path / "corpus").mkdir()
    shutil.copy(Path(__file__).parents[1] / "corpus" / "block-b.json",
                tmp_path / "corpus" / "block-b.json")
    r = run_assertion(_fake_specimen(),
                      {"id": "q", "claim": "c", "kind": "quantile",
                       "measure": "inventory.prose-word-count",
                       "block": "block-b", "min_quantile": 0.5},
                      SCORED, root=tmp_path)
    assert r.verdict == "UNTESTABLE" and r.detail.startswith("corpus unavailable")
    drift = _drift_keys({"verdicts": {"q": "UNTESTABLE"}},
                        {"verdicts": {"q": "PASSING"}}, [r], set())
    assert drift == []


def test_registered_measure_assertion_runs():
    r = run_assertion(_fake_specimen(),
                      {"id": "x", "claim": "c", "kind": "measure",
                       "measure": "arithmetica.content-word-ratio",
                       "between": [0.0, 1.0]}, SCORED)
    assert r.verdict in ("PASSING", "FAILING")  # it ran; it did not abstain


def test_untestable_count_travels_in_the_summary_line():
    """The summary line always includes the UNTESTABLE count."""
    results = [AssertionResult("a", "c", "PASSING", ""),
               AssertionResult("b", "c", "UNTESTABLE", "")]
    line = summary_line(results)
    assert "1 untestable" in line and "1 passing" in line
