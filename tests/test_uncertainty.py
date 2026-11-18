"""
The inter-rater interval and the agreement readings, pinned against the exhibit.

The precision stamp the CLI renders is derived from
corpus/exhibits/inter-rater.json. These tests keep the constants in
`isda.framework.uncertainty` equal to the exhibit, and keep the exhibit's
agreement figures readable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.corpus import repo_root  # noqa: E402
from isda.framework.uncertainty import MEASURED_SD, precision_note  # noqa: E402

EXHIBIT = repo_root() / "corpus" / "exhibits" / "inter-rater.json"


def _exhibit() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(EXHIBIT.read_text(encoding="utf-8")))


def test_precision_constants_match_the_exhibit():
    """The stamp the CLI renders is the exhibit's medians at two decimals,
    rounded half up, and the caveat's document count is the number of
    documents that produced an interval."""
    from decimal import ROUND_HALF_UP, Decimal

    from isda.framework.uncertainty import N_SCORED
    ex = _exhibit()
    measured = cast("dict[str, float]", ex["monte_carlo_metric_sd_median"])
    for metric, pinned in MEASURED_SD.items():
        rounded = float(Decimal(str(measured[metric]))
                        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        assert rounded == pinned, (
            f"{metric}: exhibit says {measured[metric]}, constant says {pinned}"
        )
    per_doc = cast("dict[str, Any]", ex["monte_carlo_metric_sd_per_doc"])
    assert sum(1 for v in per_doc.values() if v) == N_SCORED


def test_precision_note_carries_its_scope_not_just_its_number():
    """An interval reported bare reads as accuracy, so every qualifier is part
    of the payload."""
    note = precision_note()
    assert note["status"] == "measured"
    for key in ("median_sd", "basis", "reliability_not_validity",
                "within_family", "caveat"):
        assert note[key], f"precision note dropped {key}"
    assert note["within_family"] == ["grok-4.5-build"]


def test_analyze_renders_the_measured_precision():
    from isda.cli.verbs import analyze
    root = repo_root()
    spec = root / "corpus" / "specimens" / "expository-all-stock"
    payload, code = analyze(str(spec / "text.md"), str(spec / "ledger.json"),
                            "teach the mechanism", "public")
    assert code == 0
    precision = cast("dict[str, Any]", payload["precision"])
    assert precision["status"] == "measured"
    assert precision["median_sd"]["SCR"] == MEASURED_SD["SCR"]


def test_rhetorica_kappa_is_flagged_unreadable():
    """Rhetorica has the highest raw agreement of the seven strata and a
    Fleiss kappa near zero, because nearly every rating is `Selected`: chance
    agreement rises to meet observed agreement. Read alone the kappa would say
    the raters cannot agree, so the exhibit flags it as unreadable."""
    k = cast("dict[str, Any]", _exhibit()["kappa_per_stratum"])["rhetorica"]
    assert k["kappa_unreadable_prevalence_skew"] is True
    assert k["raw_agreement"] >= 0.90
    assert k["modal_tag_share"] >= 0.95
    assert k["fleiss_kappa"] < 0.10


def test_every_stratum_reports_agreement_beside_its_kappa():
    """A kappa is readable only with raw agreement and tag prevalence beside it."""
    for stratum, k in cast("dict[str, Any]",
                           _exhibit()["kappa_per_stratum"]).items():
        for field in ("fleiss_kappa", "raw_agreement", "tag_distribution",
                      "modal_tag_share", "kappa_unreadable_prevalence_skew"):
            assert field in k, f"{stratum} missing {field}"


def test_human_ratings_are_counted_and_compared_when_present():
    """The exhibit states how many documents carry a human rating. With none,
    every figure is within one model family; with some, each stratum carries
    the model-versus-human comparison."""
    ex = _exhibit()
    n_human = int(ex["human_rated_docs"])
    assert ("human" in ex["raters"]) == (n_human > 0)
    if n_human:
        for k in cast("dict[str, Any]", ex["kappa_per_stratum"]).values():
            assert "cohen_model_mode_vs_human" in k
