"""
Corpus tests: the manifests and the loader are validated everywhere; the built
blocks are validated where they exist.

The built blocks are block A (public-domain prose, genre-varied) and block B
(working markdown). The cache is machine-local, so tests over built blocks skip
on machines that have not run the builders; a skip means the cache is absent
there and says nothing about the corpus.

The last section pins each measure's gate outcome as a standing test. A
discrimination claim a measure declares is re-run against block B wherever
block B is built; a measure that declares no claim is asserted to have none, on
every machine. Re-runs use seeded permutation tests, so an outcome that flips
after a corpus rebuild reflects a change in the evidence, not test flakiness.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.corpus import (  # noqa: E402
    CorpusUnavailable, load_block, repo_root, verify,
)

CORPUS = repo_root() / "corpus"
_REF = re.compile(r"^(?:[1-3] )?[A-Z][A-Za-z ]+ \d+$")


# ---------- manifests (validate everywhere) ----------

def test_manifest_parses():
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["blocks"]) == {"block-a", "block-b", "specimens"}


def test_block_a_refs_are_well_formed_and_balanced():
    spec = json.loads((CORPUS / "block-a.json").read_text(encoding="utf-8"))
    seen: set[str] = set()
    for genre, refs in spec["genres"].items():
        assert len(refs) == 15, f"{genre}: {len(refs)} refs, design says 15"
        for ref in refs:
            assert _REF.match(ref), f"malformed ref {ref!r}"
            assert ref not in seen, f"duplicate ref {ref!r}"
            seen.add(ref)
    assert len(spec["genres"]) == 8


def test_local_files_are_ignored_by_git():
    ignore = (repo_root() / ".gitignore").read_text(encoding="utf-8")
    for needle in ("corpus/cache/", "block-b.config.json", "block-b.local.json"):
        assert needle in ignore, f"{needle} must never be committed"


# ---------- loader semantics (temp fixtures) ----------

def _fake_block_a(root: Path, text: str, digest_override: str | None = None) -> None:
    import hashlib
    cdir = root / "corpus"
    (cdir / "cache" / "block-a").mkdir(parents=True)
    (cdir / "cache" / "block-a" / "a-x-1.txt").write_text(text, encoding="utf-8")
    digest = digest_override or hashlib.sha256(text.encode()).hexdigest()
    (cdir / "block-a.lock.json").write_text(json.dumps({
        "source": {}, "documents": [
            {"id": "a-x-1", "ref": "X 1", "genre": "x", "sha256": digest},
        ]}), encoding="utf-8")


def test_loader_returns_pinned_documents(tmp_path):
    _fake_block_a(tmp_path, "In the beginning.\n")
    docs = load_block("block-a", tmp_path)
    assert len(docs) == 1 and docs[0].genre == "x"


def test_loader_raises_on_stale_text(tmp_path):
    """A document whose text differs from its pinned hash raises
    CorpusUnavailable; it is never measured as if it were the pinned text."""
    _fake_block_a(tmp_path, "In the beginning.\n", digest_override="0" * 64)
    with pytest.raises(CorpusUnavailable, match="stale"):
        load_block("block-a", tmp_path)


def test_loader_says_how_to_build_when_absent(tmp_path):
    (tmp_path / "corpus").mkdir()
    with pytest.raises(CorpusUnavailable, match="build-a"):
        load_block("block-a", tmp_path)


# ---------- built blocks (validate where they exist) ----------

built_a = (CORPUS / "block-a.lock.json").is_file() and (CORPUS / "cache" / "block-a").is_dir()
built_b = (CORPUS / "block-b.json").is_file() and (CORPUS / "cache" / "block-b").is_dir()


@pytest.mark.skipif(not built_a, reason="block A not built on this machine")
def test_built_block_a_loads_and_verifies():
    docs = load_block("block-a")
    assert len(docs) == 120
    assert len({d.genre for d in docs}) == 8
    assert all(d.text.strip() for d in docs)


@pytest.mark.skipif(not built_b, reason="block B not built on this machine")
def test_built_block_b_loads_and_verifies():
    docs = load_block("block-b")
    genres = {d.genre for d in docs}
    assert len(docs) >= 150 and len(genres) >= 6
    counts = {g: sum(1 for d in docs if d.genre == g) for g in genres}
    assert all(n >= 15 for n in counts.values()), counts


@pytest.mark.skipif(not (built_a and built_b), reason="corpus not built here")
def test_verify_reports_clean():
    assert verify() == 0


# ---------- standing gate outcomes (run where the corpus cache exists) ----------

@pytest.mark.skipif(not built_b, reason="block B not built on this machine")
def test_chunk_length_median_discriminates_at_power():
    """The chunk-length median's genre-discrimination claim passes its gate on
    block B, and block B is large enough to adjudicate it (the detectability
    floor is below the claim threshold)."""
    from collections import defaultdict

    from isda.kernel.registry import discriminate
    from isda.measures.shape import CHUNK_LENGTH_MEDIAN

    by_genre: dict[str, list[str]] = defaultdict(list)
    for d in load_block("block-b"):
        by_genre[d.genre].append(d.text)
    v = discriminate(CHUNK_LENGTH_MEDIAN, by_genre, n_perm=1000, seed=0)
    assert v.adequately_powered, f"floor {v.floor} >= threshold {v.threshold}"
    assert v.passed, f"omega2={v.omega2:.4f} p={v.p:.5f}"


def test_paragraph_measure_declares_no_discrimination_claim():
    """The paragraph-length median declares no discrimination claim: on block B
    at power it misses the gate (omega2 0.0125 against a detectability floor of
    0.051). A claim may be declared only with new evidence."""
    from isda.measures.shape import PARAGRAPH_LENGTH_MEDIAN

    assert PARAGRAPH_LENGTH_MEDIAN.discrimination is None


@pytest.mark.skipif(not built_b, reason="block B not built on this machine")
def test_geometria_discriminators_hold_at_power():
    """The section-size-dispersion and skipped-heading-levels discrimination
    claims pass their gates on block B at adequate power (omega2 0.2276 and
    0.2027, both p = 5e-4, against detectability floors of about 0.06)."""
    from collections import defaultdict

    from isda.kernel.registry import discriminate
    from isda.measures.geometry import (
        SECTION_SIZE_DISPERSION, SKIPPED_HEADING_LEVELS,
    )

    by_genre: dict[str, list[str]] = defaultdict(list)
    for d in load_block("block-b"):
        by_genre[d.genre].append(d.text)
    for m in (SECTION_SIZE_DISPERSION, SKIPPED_HEADING_LEVELS):
        v = discriminate(m, by_genre, n_perm=1000, seed=0)
        assert v.adequately_powered, f"{m.id}: floor {v.floor} >= {v.threshold}"
        assert v.passed, f"{m.id}: omega2={v.omega2:.4f} p={v.p:.5f}"


def test_ungranted_geometria_claims_stay_off():
    """Heading tree depth and heading branching declare no discrimination
    claim: on block B at power they miss the gate (omega2 0.0883 and 0.0079).
    Block-kind entropy declares none either: it passes the gate (0.1448) but
    tracks markup fraction (rho 0.53 against a 0.50 limit), and with markup
    fraction fitted out it misses (0.0998). A claim may be declared only with
    new evidence."""
    from isda.measures.geometry import (
        BLOCK_KIND_ENTROPY, HEADING_BRANCHING, HEADING_TREE_DEPTH,
    )

    assert HEADING_TREE_DEPTH.discrimination is None
    assert HEADING_BRANCHING.discrimination is None
    assert BLOCK_KIND_ENTROPY.discrimination is None


# Measures with an optional backend skip where the backend is not installed and
# the content-hash cache is cold; on the machine holding the private corpus,
# both run from cache in seconds.

def _skip_unless_computable(descriptor, text: str) -> None:  # type: ignore[no-untyped-def]
    from isda.core.document import Document
    from isda.core.features import FeatureContext
    from isda.kernel.descriptor import MeasureUnavailable
    try:
        descriptor.compute(FeatureContext(Document.parse(text),
                                          frozenset(descriptor.requires)))
    except MeasureUnavailable as exc:
        pytest.skip(str(exc))


@pytest.mark.skipif(not built_b, reason="block B not built on this machine")
def test_cpidr_discriminates_at_power_and_moves_under_scramble():
    """Propositional density (CPIDR) discriminates genre on block B at power
    and passes its falsifiers. Headline figures: omega2 0.1439 against a
    detectability floor of 0.0546, and scrambling the words moves the measure
    by 0.59 of the IQR spread (corpus/exhibits/propositional-density.json)."""
    from collections import defaultdict

    from isda.kernel.registry import discriminate, verify
    from isda.measures.arithmetica_cpidr import PROPOSITIONAL_DENSITY

    docs = load_block("block-b")
    _skip_unless_computable(PROPOSITIONAL_DENSITY, docs[0].text)
    by_genre: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        by_genre[d.genre].append(d.text)
    v = discriminate(PROPOSITIONAL_DENSITY, by_genre, n_perm=1000, seed=0)
    assert v.adequately_powered, f"floor {v.floor} >= threshold {v.threshold}"
    assert v.passed, f"omega2={v.omega2:.4f} p={v.p:.5f}"

    hv = verify(PROPOSITIONAL_DENSITY, [d.text for d in docs], seed=0)
    assert hv.passed, [r.reason for r in hv.results if not r.passed] + hv.errors


@pytest.mark.skipif(not built_b, reason="block B not built on this machine")
def test_surprisal_falsifiers_hold_on_block_b():
    """Both perturbations that must move surprisal variance on block B do:
    scramble_within_sentence by 0.53 and scramble_words by 0.67 of the IQR
    spread (corpus/exhibits/surprisal-variance.json). The top-quartile outcome
    is pinned by the specimen assertion lyric-musica-original /
    musica-top-quartile, not here."""
    from isda.kernel.registry import verify
    from isda.measures.musica import SURPRISAL_VARIANCE

    docs = load_block("block-b")
    _skip_unless_computable(SURPRISAL_VARIANCE, docs[0].text)
    hv = verify(SURPRISAL_VARIANCE, [d.text for d in docs], seed=0)
    assert hv.passed, [r.reason for r in hv.results if not r.passed] + hv.errors


def test_surprisal_missed_discrimination_claim_stays_off():
    """Surprisal variance declares no discrimination claim: on block B at power
    its effect is significant but below the claim threshold (omega2 0.0857
    against 0.10, detectability floor 0.0523, p 0.0015; see
    corpus/exhibits/surprisal-variance.json). A claim may be declared only with
    new corpus evidence."""
    from isda.measures.musica import SURPRISAL_VARIANCE

    assert SURPRISAL_VARIANCE.discrimination is None


@pytest.mark.skipif(not built_b, reason="block B not built on this machine")
@pytest.mark.parametrize("name", ["SURPRISAL_SLOPE", "SURPRISAL_PEAK_POSITION"])
def test_trajectory_falsifiers_hold_on_block_b(name: str):
    """A paragraph shuffle and a paragraph reversal each move both Astronomia
    measures on block B by at least the admission threshold
    (corpus/exhibits/surprisal-trajectory.json)."""
    from isda.kernel.registry import verify
    from isda.measures import astronomia

    descriptor = getattr(astronomia, name)
    docs = load_block("block-b")
    _skip_unless_computable(descriptor, docs[0].text)
    hv = verify(descriptor, [d.text for d in docs], seed=0)
    assert hv.passed, [r.reason for r in hv.results if not r.passed] + hv.errors
