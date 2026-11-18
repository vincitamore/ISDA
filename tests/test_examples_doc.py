"""
The published worked examples must agree with the fixtures they describe.

examples.md holds the three analyses a reader calibrates their judgment
against. Each worked example is tied to the specimen that carries its body and
ledger. The published ledger table, total, raw length and metric table are
parsed out of the prose and compared with the specimen's ledger.json and its
natively scored metrics, so the prose in examples.md and the fixtures cannot
disagree. The corpus bodies are read by path and never retyped.

Scope: a passing run establishes only that the published numbers match the
arithmetic over the published ledgers. It does not establish that a ledger's
compressed sizes or intensity tags are the right judgments; no mechanical
check can, and they are the analyst's work.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.framework.metrics import score_ledger  # noqa: E402
from isda.framework.strata import STRATA  # noqa: E402
from isda.specimens import load_specimen  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples.md"

# The published example -> the specimen that carries its body and ledger.
# Specimen names describe the role the specimen plays in the corpus.
EXAMPLE_SPECIMENS = {
    'Example 1: Gerard Manley Hopkins, "Pied Beauty"': "lyric-musica-original",
    'Example 2: "The Problem of Defaults"': "argumentative-dialectica-original",
    'Example 3: "How Photosynthesis Works"': "expository-all-stock",
}

_LEDGER_ROW = re.compile(
    r"^\|\s*\*\*(?P<stratum>\w+)\*\*\s*\|.*?\|\s*~?(?P<size>[\d,]+)\s*B[^|]*\|"
    r"\s*\*\*(?P<intensity>Stock|Implied|Selected|Original)\*\*\s*\|",
    re.MULTILINE,
)
_METRIC_ROW = re.compile(
    r"^\|\s*(?P<metric>SCR|ND|RI)\s*\|\s*(?P<value>[\d.]+)\s*\|", re.MULTILINE)
_RAW = re.compile(r"Raw\s+(?P<raw>[\d,]+)\s*\(measured\)")
_TOTAL = re.compile(r"\*\*Total `K_τ\(d,[^`]*`\s*[≈=]\s*(?P<total>[\d,]+) bytes")


def _int(text: str) -> int:
    return int(text.replace(",", ""))


def _sections() -> dict[str, str]:
    """Split examples.md at its `## ` headings."""
    text = EXAMPLES.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    parts = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    for part in parts:
        out[part.splitlines()[0].strip()] = part
    return out


def _section_for(title_prefix: str, sections: dict[str, str]) -> str:
    for title, body in sections.items():
        if title.startswith(title_prefix):
            return body
    raise AssertionError(f"examples.md has no section starting {title_prefix!r}")


@pytest.mark.parametrize(("title", "slug"), sorted(EXAMPLE_SPECIMENS.items()))
def test_published_example_matches_its_specimen(title: str, slug: str) -> None:
    body = _section_for(title, _sections())
    specimen = load_specimen(REPO / "corpus" / "specimens" / slug)
    ledger = specimen.ledger

    # The raw length: the published figure must equal the specimen's raw_bytes,
    # which load_specimen ties to the byte length of the body.
    raw_match = _RAW.search(body)
    assert raw_match, f"{title}: no measured raw length published"
    assert _int(raw_match.group("raw")) == ledger["raw_bytes"], (
        f"{title}: published raw length disagrees with the specimen ledger"
    )

    # The ledger table: every stratum's compressed size and intensity. Only the
    # first (Framing A) table is authoritative; later framings in the same
    # section carry intensity tags without compressed sizes and are not scored.
    published_rows = _LEDGER_ROW.findall(body)
    assert len(published_rows) >= len(STRATA), (
        f"{title}: expected a seven-row ledger table, parsed {len(published_rows)}"
    )
    for stratum, size, intensity in published_rows[:len(STRATA)]:
        key = stratum.lower()
        assert key in ledger["strata"], f"{title}: unknown stratum {stratum!r}"
        row = ledger["strata"][key]
        assert _int(size) == row["compressed"], (
            f"{title}: {stratum} compressed size {size} != fixture {row['compressed']}"
        )
        assert intensity == row["intensity"], (
            f"{title}: {stratum} intensity {intensity} != fixture {row['intensity']}"
        )

    # The published total must equal the sum of the ledger's compressed sizes.
    total_match = _TOTAL.search(body)
    assert total_match, f"{title}: no published compressed total"
    fixture_total = sum(r["compressed"] for r in ledger["strata"].values())
    assert _int(total_match.group("total")) == fixture_total

    # The metrics, scored natively and compared at published precision.
    scored = score_ledger({**ledger, "document": specimen.text})
    assert scored["ok"] is True, scored.get("errors")
    computed = scored["metrics"]
    published = {m: v for m, v in _METRIC_ROW.findall(body)}
    assert set(published) == {"SCR", "ND", "RI"}, (
        f"{title}: published metrics table is incomplete: {sorted(published)}"
    )
    for metric, text_value in published.items():
        places = len(text_value.split(".")[1]) if "." in text_value else 0
        assert float(text_value) == pytest.approx(round(computed[metric], places)), (
            f"{title}: published {metric} {text_value} != computed "
            f"{computed[metric]}; recompute with `isda score`, never by hand"
        )


def test_readme_republished_metrics_agree() -> None:
    """README's example blurbs republish computed metrics. Each republished
    number is checked against the scorer, because a second copy of a number
    can drift independently of the first."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    by_token = {
        "Pied Beauty": "lyric-musica-original",
        "Problem of Defaults": "argumentative-dialectica-original",
        "Photosynthesis": "expository-all-stock",
    }
    checked = 0
    for line in readme.splitlines():
        # A blurb opens with the example's name in bold; match inside that
        # leading bold span so the body text cannot produce a false match.
        opening = re.match(r"\*\*(.+?)\*\*", line)
        if opening is None:
            continue
        slug = next((s for token, s in by_token.items()
                     if token in opening.group(1)), None)
        if slug is None:
            continue
        specimen = load_specimen(REPO / "corpus" / "specimens" / slug)
        metrics = score_ledger({**specimen.ledger, "document": specimen.text})["metrics"]
        published = dict(re.findall(r"`(SCR|ND|RI) = ([\d.]+)`", line))
        assert published, f"README blurb for {slug} publishes no computed metric"
        for metric, text_value in published.items():
            places = len(text_value.split(".")[1]) if "." in text_value else 0
            assert float(text_value) == pytest.approx(round(metrics[metric], places)), (
                f"README {metric} {text_value} for {slug} != computed {metrics[metric]}"
            )
        checked += 1
    assert checked == len(by_token), (
        f"matched {checked} README blurbs, expected {len(by_token)}: a renamed "
        "example must fail this test instead of being skipped"
    )


def test_cross_example_summary_table_agrees() -> None:
    """The takeaways table republishes SCR and ND. It can disagree with the
    per-example sections independently of them, so it is checked on its own."""
    body = _section_for("Cross-example takeaways", _sections())
    rows = re.findall(
        r"^\|\s*(?P<text>[^|]+?)\s*\|[^|]*\|[^|]*\|[^|]*\|\s*(?P<scr>[\d.]+)\s*\|"
        r"\s*(?P<nd>[\d.]+)\s*\|",
        body, re.MULTILINE)
    assert rows, "no computed rows parsed from the cross-example table"

    # Match a summary row to its specimen by the distinguishing token in the
    # text column, so a renamed example fails the test instead of being skipped.
    by_token = {
        "Pied Beauty": "lyric-musica-original",
        "Problem of Defaults": "argumentative-dialectica-original",
        "Photosynthesis": "expository-all-stock",
    }
    checked = 0
    for text, scr, nd in rows:
        slug = next((s for token, s in by_token.items() if token in text), None)
        assert slug is not None, f"unmapped summary row: {text!r}"
        specimen = load_specimen(REPO / "corpus" / "specimens" / slug)
        scored = score_ledger({**specimen.ledger, "document": specimen.text})
        metrics = scored["metrics"]
        assert float(scr) == pytest.approx(
            round(metrics["SCR"], len(scr.split(".")[1]) if "." in scr else 0))
        assert float(nd) == pytest.approx(
            round(metrics["ND"], len(nd.split(".")[1]) if "." in nd else 0))
        checked += 1
    assert checked == 3, f"expected three fully-ledgered rows, checked {checked}"
