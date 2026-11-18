"""
The CLI contract: four verbs, ok-first envelope, exit codes.

These are pinned because they are a public surface: scripts branch on `ok`
and on exit codes, so changing either is a breaking change and must fail a test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.cli import EXIT_FINDING, EXIT_OK, EXIT_USAGE, main  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HOPKINS = REPO / "corpus" / "specimens" / "lyric-musica-original"


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------- score

def test_score_json_envelope_is_ok_first(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(
        ["score", str(HOPKINS / "ledger.json"),
         "--document", str(HOPKINS / "text.md"), "--json"],
        capsys,
    )
    assert code == EXIT_OK
    envelope: dict[str, Any] = json.loads(out)
    assert list(envelope)[0] == "ok" and envelope["ok"] is True
    assert envelope["verb"] == "score"
    # The Hopkins specimen's figures, pinned exactly.
    assert envelope["metrics"] == {"SCR": 1.8, "ND": 0.57, "RI": 0.198}
    assert envelope["compression_floor"]["checked"] is True


def test_score_malformed_ledger_exits_64(tmp_path: Path,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"raw_bytes": 10, "strata": {}}', encoding="utf-8")
    code, out, err = _run(["score", str(bad), "--json"], capsys)
    assert code == EXIT_USAGE
    envelope = json.loads(out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "bad-ledger"
    assert "missing strata" in envelope["error"]["message"]
    assert err  # one-line stderr summary accompanies the JSON error


def test_score_missing_file_exits_64(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _run(["score", "no-such-ledger.json"], capsys)
    assert code == EXIT_USAGE
    assert "no such ledger" in err


# ---------------------------------------------------------------- measure

def test_measure_report_is_split_and_bounded(tmp_path: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("# Title\n\nSome prose here.\n\n- a list item\n", encoding="utf-8")
    detail = tmp_path / "detail.jsonl"
    code, out, _ = _run(
        ["measure", str(doc), "--json", "--detail", str(detail)], capsys)
    assert code == EXIT_OK
    envelope = json.loads(out)
    assert envelope["ok"] is True
    # Source facts and prose statistics are separate blocks.
    assert "bytes" in envelope["source"] and "blocks" in envelope["source"]
    assert set(envelope["prose"]) == {"bytes", "words", "sentences", "paragraphs"}
    # Retired measures emit no value in a measurement report.
    assert all(row["status"] != "retired" for row in envelope["measures"])
    # The O(n) rows go to the opt-in file, one JSON object per block.
    rows = [json.loads(line) for line in
            detail.read_text(encoding="utf-8").splitlines()]
    assert envelope["detail"]["rows"] == len(rows) == 3
    assert {r["kind"] for r in rows} == {"heading", "paragraph", "list_item"}


# ---------------------------------------------------------------- analyze

def test_analyze_is_ledger_first_with_precision_stamp(
        capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(
        ["analyze", str(HOPKINS / "text.md"),
         "--ledger", str(HOPKINS / "ledger.json"), "--json"],
        capsys,
    )
    assert code == EXIT_OK
    envelope = json.loads(out)
    ledger_rows: list[dict[str, Any]] = envelope["ledger"]
    assert [r["stratum"] for r in ledger_rows] == [
        "grammatica", "dialectica", "rhetorica", "arithmetica",
        "geometria", "musica", "astronomia",
    ]
    # The stamp travels with the numbers and carries its own scope: an interval
    # reported without "reliability, not validity" and without the rater family
    # reads as accuracy, which is the misreading the stamp exists to prevent.
    precision: dict[str, Any] = envelope["precision"]
    assert precision["status"] == "measured"
    assert set(precision["median_sd"]) == {"SCR", "ND", "RI"}
    assert precision["reliability_not_validity"]
    assert precision["within_family"]
    assert envelope["dominant_stratum"] == "musica"
    # With no telos or substrate stated, the warnings travel in the payload.
    assert any("telos" in w for w in envelope["warnings"])
    assert any("substrate" in w for w in envelope["warnings"])


def test_analyze_refuses_a_ledger_for_a_different_document(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    other = tmp_path / "other.md"
    other.write_text("Entirely different text.\n", encoding="utf-8")
    code, out, _ = _run(
        ["analyze", str(other), "--ledger", str(HOPKINS / "ledger.json"), "--json"],
        capsys,
    )
    assert code == EXIT_USAGE
    envelope = json.loads(out)
    assert envelope["ok"] is False
    assert "raw_bytes" in envelope["error"]["message"]


# ---------------------------------------------------------------- measures

def test_measures_check_drift_is_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    # A stale manifest in a fake repo root: drift exits 1 (something to act on),
    # not 64 (an error), because the run itself succeeded.
    (tmp_path / "corpus").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "measures.json").write_text("{}\n", encoding="utf-8")
    import isda.corpus
    monkeypatch.setattr(isda.corpus, "repo_root", lambda start=None: tmp_path)
    code, out, _ = _run(["measures", "--check", "--json"], capsys)
    assert code == EXIT_FINDING
    envelope = json.loads(out)
    assert envelope["ok"] is True and envelope["check"]["match"] is False


def test_unknown_verb_exits_64(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == EXIT_USAGE
    capsys.readouterr()  # drain argparse's stderr
