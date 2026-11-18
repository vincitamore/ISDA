"""
The measure manifest is derived state and must agree with the registry.

data/measures.json records every measure's active/provisional/retired status
with the declarations that justify it, so the partition can be reviewed in one
file without reading the code. It is written only by
`python -m isda measures --write`. These tests fail when the file is edited by
hand or when a descriptor changes without regenerating it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import isda.measures  # noqa: F401,E402  # import-time registration
from isda.kernel import registry  # noqa: E402
from isda.kernel.descriptor import Kind, Status  # noqa: E402

assert isda.measures  # the import registers the measures; the assert marks it used

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data" / "measures.json"


def _rendered() -> str:
    return json.dumps(registry.manifest(), indent=2, ensure_ascii=False) + "\n"


def test_manifest_file_matches_registry_bytes() -> None:
    assert MANIFEST.is_file(), (
        "data/measures.json is missing: generate it with "
        "`python -m isda measures --write`"
    )
    on_disk = MANIFEST.read_text(encoding="utf-8")
    assert on_disk == _rendered(), (
        "data/measures.json differs from the registry: regenerate it with "
        "`python -m isda measures --write` and review the diff, because a "
        "changed status must be investigated before it is accepted"
    )


def test_partition_is_total_and_evidence_shaped() -> None:
    """Every measure sits in exactly one partition cell with the record its
    cell requires: retired rows carry a reason, and every other claim measure
    carries a falsifier and a null model."""
    measures = registry.all_measures(include_retired=True)
    assert measures, "registry is empty: measures failed to register"
    for m in measures:
        assert m.status in (Status.ACTIVE, Status.PROVISIONAL, Status.RETIRED)
        if m.status is Status.RETIRED:
            assert m.retired_because.strip(), f"{m.id}: retired without a record"
        elif m.kind is Kind.CLAIM:
            assert m.must_move_under, f"{m.id}: claim without a falsifier"
            assert m.null is not None, f"{m.id}: claim without a null model"


def test_manifest_lists_every_registered_measure() -> None:
    man = registry.manifest()
    listed = {row["id"] for row in man["measures"]}  # type: ignore[union-attr,index]
    registered = {m.id for m in registry.all_measures(include_retired=True)}
    assert listed == registered
