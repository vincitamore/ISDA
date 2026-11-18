"""
The Musica surprisal measure: contract, availability semantics, cache, and,
where the backend or a warm cache exists, the values themselves.

The backend is an optional extra, so every consumer must read
MeasureUnavailable as a statement about the machine: the CLI renders it as
`unavailable`, specimen assertions are UNTESTABLE, and the drift gate skips
exactly the keys that cannot be known here while still failing on everything
it can check. A machine with a warm disk cache computes real values with no
backend installed at all: the cache is keyed by content hash plus a params
fingerprint, so it cannot serve a stale value.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.core.document import Document  # noqa: E402
from isda.core.features import FeatureContext  # noqa: E402
from isda.kernel.descriptor import Kind, MeasureUnavailable  # noqa: E402
from isda.measures import musica  # noqa: E402
from isda.specimens import (  # noqa: E402
    AssertionResult, _drift_keys,  # pyright: ignore[reportPrivateUsage]
)


def _ctx(text: str) -> FeatureContext:
    return FeatureContext(Document.parse(text),
                          frozenset(musica.SURPRISAL_VARIANCE.requires))


# ---------- contract ----------

def test_registered_as_a_claim_with_falsifiers_and_null():
    m = musica.SURPRISAL_VARIANCE
    assert m.kind is Kind.CLAIM
    assert m.null is not None
    assert {p.name for p in m.must_move_under} == {
        "scramble_within_sentence", "scramble_words"}
    assert m.strata == ("musica",)
    # the parameters are the measure's identity; a value without them cannot be
    # interpreted
    for key in ("model", "revision", "window", "stride", "unit", "scope"):
        assert key in m.params


def test_empty_prose_returns_none_not_zero():
    assert musica.surprisal_variance(_ctx("")) is None


# ---------- availability semantics ----------

class _StubCache:
    """An in-memory stand-in for the disk cache: same get/put surface."""

    def __init__(self, values: dict[str, list[float]] | None = None):
        self.values = dict(values or {})

    def get(self, text: str) -> list[float] | None:
        from isda.measures._cache import HashCache
        return self.values.get(HashCache.key(text))

    def put(self, text: str, row: list[float]) -> None:
        from isda.measures._cache import HashCache
        self.values[HashCache.key(text)] = list(row)


@pytest.fixture
def no_backend(monkeypatch: pytest.MonkeyPatch):
    """A machine with neither the extra nor a warm cache."""
    monkeypatch.setattr(musica, "_cache", _StubCache())

    def raise_unavailable() -> tuple[object, object, object]:
        raise MeasureUnavailable("no [surprisal] extra (test fixture)")

    monkeypatch.setattr(musica, "_backend", raise_unavailable)


def test_compute_raises_measure_unavailable_without_backend(no_backend: None):
    with pytest.raises(MeasureUnavailable):
        musica.surprisal_variance(_ctx("Some prose that is not cached.\n"))


def test_cache_answers_without_backend(monkeypatch: pytest.MonkeyPatch,
                                       no_backend: None):
    text = "Cached prose.\n"
    doc = Document.parse(text)
    cache = _StubCache()
    cache.put(doc.prose_text, [10.0, 5.0, 2.5])
    monkeypatch.setattr(musica, "_cache", cache)
    assert musica.surprisal_variance(_ctx(text)) == 2.5


def test_cli_renders_unavailability_not_error(no_backend: None):
    from isda.cli.verbs import measure
    payload, code = measure(str(Path(__file__).resolve().parents[1] / "README.md"),
                            None, None, None)
    assert code == 0
    row = next(r for r in payload["measures"]
               if r["id"] == "musica.surprisal-variance")
    assert row["value"] is None
    assert "unavailable" in row and "error" not in row


def test_specimen_assertion_goes_untestable_without_backend(no_backend: None):
    from isda.specimens import load_specimens, run_assertion, score_ledger
    lyric = next(s for s in load_specimens() if s.slug == "lyric-musica-original")
    row = next(a for a in lyric.assertions if a["id"] == "musica-top-quartile")
    result = run_assertion(lyric, row, score_ledger(lyric))
    assert result.verdict == "UNTESTABLE"
    # Where block B is not built the runner stops at that gap first.
    assert result.detail.startswith(("backend unavailable", "corpus unavailable"))


# ---------- drift semantics (pure function, no backend involved) ----------

def _expected(measures: dict[str, float], verdicts: dict[str, str]):
    return {"written_by": "x", "sha256": "abc", "measures": measures,
            "verdicts": verdicts}


def test_drift_skips_unavailable_measures_but_not_checkable_ones():
    expected = _expected({"musica.surprisal-variance": 20.0, "shape.x": 1.0},
                         {})
    derived = _expected({"shape.x": 2.0}, {})  # surprisal unknowable here
    drift = _drift_keys(derived, expected, [],
                        unavailable={"musica.surprisal-variance"})
    assert drift == ["measures(shape.x)"]


def test_drift_fires_on_available_but_unpinned_measure():
    """A measure computable here but absent from the pin is reported as drift,
    because a deliberate re-pin is due."""
    expected = _expected({}, {})
    derived = _expected({"musica.surprisal-variance": 20.0}, {})
    drift = _drift_keys(derived, expected, [], unavailable=set())
    assert drift == ["measures(musica.surprisal-variance)"]


def test_drift_skips_backend_gap_verdicts_only():
    expected = _expected({}, {"a": "PASSING", "b": "PASSING"})
    derived = _expected({}, {"a": "UNTESTABLE", "b": "FAILING"})
    results = [
        AssertionResult("a", "", "UNTESTABLE", "backend unavailable: x"),
        AssertionResult("b", "", "FAILING", "0.4 vs 0.9"),
    ]
    drift = _drift_keys(derived, expected, results, unavailable=set())
    assert drift == ["verdicts(b)"]


# ---------- real values (backend or warm cache; skip clean otherwise) ----------

def _value_or_skip(text: str) -> float:
    try:
        v = musica.surprisal_variance(_ctx(text))
    except MeasureUnavailable:
        pytest.skip("no [surprisal] backend and no cached value on this machine")
    assert v is not None
    return v


def test_deterministic_on_repeat():
    text = "The quick brown fox jumps over the lazy dog. It was the best of times.\n"
    assert _value_or_skip(text) == _value_or_skip(text)


def test_scramble_raises_mean_surprisal_on_real_prose():
    """Sanity check beside the falsifier harness: destroyed syntax must cost
    bits on average. The harness asks whether the variance moves; the mean has
    a fixed expected direction, since scrambled text that is not more
    surprising means the backend is not measuring language."""
    from isda.kernel.perturb import SCRAMBLE_IN_SENTENCE
    text = ("Photosynthesis converts light energy into chemical energy. "
            "The process occurs in the chloroplasts of plant cells. "
            "Water and carbon dioxide become glucose and oxygen.\n")
    _value_or_skip(text)
    scrambled = SCRAMBLE_IN_SENTENCE.apply(text, 0)
    _value_or_skip(scrambled)

    def mean_of(t: str) -> float:
        row = musica._cache.get(Document.parse(t).prose_text)  # pyright: ignore[reportPrivateUsage]
        assert row is not None
        return row[1]

    assert mean_of(scrambled) > mean_of(text)
