"""
Parity pin: the package's ledger scorer and the standalone isda_preprocess.py
must agree exactly.

The ledger arithmetic exists twice: the package implementation
(isda.framework.metrics, used by the CLI and the specimen runner) and the
standalone single-file tool (isda_preprocess.py, which must run alone in a
prose-only skill directory with no package alongside). Two copies of a weighted
sum can drift apart, and this test fails when they do.

Two layers:
- constants parity: STRATA / ND_WEIGHT / RI_WEIGHT / ZDICT_CAP are compared
  directly against the standalone module, so a weight edit that misses one copy
  fails even if no fixture exercises the changed rung.
- score parity: every specimen ledger is scored through both paths (document
  attached, so the compression floor runs), and the full JSON outputs (shape,
  rounding and notes) must be deeply equal.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from isda.framework import floor as native_floor
from isda.framework import strata as native_strata
from isda.framework.metrics import score_ledger as native_score
from isda.specimens import load_specimens

REPO = Path(__file__).resolve().parent.parent
STANDALONE = REPO / "isda_preprocess.py"


def _standalone_module() -> Any:
    spec = importlib.util.spec_from_file_location("isda_preprocess_standalone", STANDALONE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_constants_parity() -> None:
    standalone = _standalone_module()
    assert tuple(standalone.STRATA) == native_strata.STRATA
    assert dict(standalone.ND_WEIGHT) == native_strata.ND_WEIGHT
    assert dict(standalone.RI_WEIGHT) == native_strata.RI_WEIGHT
    assert standalone.ZDICT_CAP == native_floor.ZDICT_CAP


def test_intensity_vocabulary_spans_the_weights() -> None:
    # The ladder and the weight tables must name the same four rungs.
    assert set(native_strata.INTENSITIES) == set(native_strata.ND_WEIGHT)
    assert set(native_strata.INTENSITIES) == set(native_strata.RI_WEIGHT)


def test_score_parity_on_every_specimen() -> None:
    """Both implementations score every specimen ledger identically."""
    specimens = load_specimens()
    assert specimens, "no specimens to test parity against"

    exercised: set[str] = set()
    for sp in specimens:
        proc = subprocess.run(
            [sys.executable, str(STANDALONE),
             "--ledger", str(sp.path / "ledger.json"),
             "--ledger-document", str(sp.path / "text.md")],
            capture_output=True, text=True, cwd=REPO,
        )
        assert proc.returncode == 0, f"{sp.slug}: standalone scorer failed: {proc.stderr[:300]}"
        standalone_result = json.loads(proc.stdout)

        native_result = native_score({**sp.ledger, "document": sp.text})
        # Round-trip through JSON so both sides carry identical type identities.
        assert json.loads(json.dumps(native_result)) == standalone_result, (
            f"{sp.slug}: package and standalone metric output diverge"
        )
        for row in sp.ledger["strata"].values():
            exercised.add(row["intensity"])

    # The pin is only as strong as the specimens' coverage of the ladder. If a
    # rung is not exercised, the constants test above still covers it, and this
    # assertion reports which rungs the specimens leave out.
    assert exercised == set(native_strata.INTENSITIES), (
        f"specimen ledgers exercise only {sorted(exercised)}; parity on the "
        "missing rungs rests on constants alone"
    )


def test_native_rejects_incoherent_core() -> None:
    """A ledger whose compressed core exceeds raw_bytes is rejected: the core
    cannot be larger than the document it compresses."""
    bad = {
        "raw_bytes": 100,
        "strata": {s: {"compressed": 50, "intensity": "Stock"}
                   for s in native_strata.STRATA},
    }
    result = native_score(bad)
    assert result["ok"] is False
    assert any("exceeds raw_bytes" in e for e in result["errors"])
