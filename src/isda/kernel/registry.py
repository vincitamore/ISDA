"""
The measure registry and the harness that tests declarations against a corpus.

The registry holds descriptors and refuses malformed ones; it does no measuring.
The harness takes a measure's own declarations (what it reads, what must move
it, what must not) and tries to falsify them on a real corpus. A declaration is
a hypothesis, and `verify` turns it into a result.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence

from ..core.document import Document
from ..core.features import FEATURES, FeatureContext
from .descriptor import Kind, MeasureDescriptor, Perturbation, Status
from .stats import null_floor, omega_squared, permutation_p

_REGISTRY: dict[str, MeasureDescriptor] = {}


def register(descriptor: MeasureDescriptor) -> MeasureDescriptor:
    """Admit a measure. Raises ValueError on a malformed contract (see MeasureDescriptor)."""
    if descriptor.id in _REGISTRY:
        raise ValueError(f"duplicate measure id: {descriptor.id}")

    # `requires` is checked, not just recorded: an unknown feature name fails
    # here instead of at first use.
    unknown = [r for r in descriptor.requires if r not in FEATURES]
    if unknown and descriptor.status is not Status.RETIRED:
        raise ValueError(
            f"{descriptor.id}: requires unknown feature(s) {unknown}; "
            f"known features: {sorted(FEATURES)}"
        )

    if descriptor.kind is Kind.CLAIM and descriptor.status is not Status.RETIRED:
        if not descriptor.requires:
            raise ValueError(
                f"{descriptor.id}: a CLAIM must declare what it reads in `requires`: "
                "a measure that reads nothing is a constant, and the falsifier "
                "check needs the declaration to have anything to check against."
            )

        # Falsifier rule. Whether a perturbation can move a measure is a
        # relation between the perturbation and what the measure reads. At least
        # one declared falsifier must destroy at least one declared feature;
        # otherwise every falsifier preserves everything the measure is allowed
        # to see, and the declaration is a test that cannot fire. For example,
        # scramble_words preserves the word multiset, so it cannot falsify a
        # measure that reads only that multiset. The check is static and needs no
        # measurement run.
        needed = set(descriptor.requires)
        if not any(p.destroys & needed for p in descriptor.must_move_under):
            detail = "; ".join(
                f"{p.name} destroys {sorted(p.destroys) or 'nothing declared'}"
                for p in descriptor.must_move_under
            )
            raise ValueError(
                f"{descriptor.id}: no declared falsifier destroys any feature this "
                f"measure reads ({sorted(needed)}). {detail}. Declare a perturbation "
                "that destroys what the measure reads, extend the "
                "perturbation's `destroys` row if it should cover one of those features, or "
                "reclassify as a DESCRIPTION."
            )

    _REGISTRY[descriptor.id] = descriptor
    return descriptor


def get(measure_id: str) -> MeasureDescriptor:
    return _REGISTRY[measure_id]


def all_measures(include_retired: bool = False) -> list[MeasureDescriptor]:
    return [
        m for m in _REGISTRY.values()
        if include_retired or m.status is not Status.RETIRED
    ]


def manifest() -> dict[str, object]:
    """
    The registry serialized as the durable partition record: every measure's
    status (active / provisional / retired) with the declarations that earned
    it. The record is generated and never hand-edited.
    `python -m isda measures --write` renders it to data/measures.json, and a
    test fails when the file and the registry disagree, so the reviewable
    artifact cannot drift from the code.

    Retired measures are included so that a reader who remembers a number can
    find why it is gone.
    """
    def _perturbation(p: Perturbation) -> dict[str, object]:
        return {
            "name": p.name,
            "structure_destroyed": p.structure_destroyed,
            "destroys": sorted(p.destroys),
        }

    def _measure(m: MeasureDescriptor) -> dict[str, object]:
        row: dict[str, object] = {
            "id": m.id,
            "version": m.version,
            "kind": m.kind.value,
            "status": m.status.value,
            "construct": m.construct,
            "requires": list(m.requires),
            "strata": list(m.strata),
            "must_move_under": [_perturbation(p) for p in m.must_move_under],
            "must_not_move_under": [_perturbation(p) for p in m.must_not_move_under],
            "null": None if m.null is None else {
                "kind": m.null.kind,
                "derived_from": m.null.derived_from,
                "expected_range": (list(m.null.expected_range)
                                   if m.null.expected_range else None),
            },
            "discrimination": None if m.discrimination is None else {
                "groups_by": m.discrimination.groups_by,
                "min_omega_squared": m.discrimination.min_omega_squared,
                "max_p": m.discrimination.max_p,
            },
            "interpretation": m.interpretation,
        }
        if m.retired_because:
            row["retired_because"] = m.retired_because
        if m.params:
            row["params"] = dict(m.params)
        return row

    return {
        "generated_by": ("python -m isda measures --write: derived from the "
                         "registry, never hand-edited"),
        "corpus": ("interpretations cite block A (public-domain prose, "
                   "genre-varied) and block B (working markdown), the corpus "
                   "blocks described in corpus/manifest.json"),
        "harness": {
            "move_threshold": MOVE_THRESHOLD,
            "still_threshold": STILL_THRESHOLD,
            "spread": "iqr",
        },
        "measures": [_measure(m) for m in
                     sorted(_REGISTRY.values(), key=lambda m: m.id)],
    }


def clear() -> None:
    """Test-support only."""
    _REGISTRY.clear()


def snapshot() -> dict[str, MeasureDescriptor]:
    """Test-support only: capture the registry so a fixture can restore it.

    Registration happens at import time. A fixture that clears the registry and
    does not restore it removes entries that no import recreates, because
    Python caches the module and the import that would re-register never runs.
    Isolation therefore means restoring what was there, not leaving the registry
    empty.
    """
    return dict(_REGISTRY)


def restore(snap: Mapping[str, MeasureDescriptor]) -> None:
    """Test-support only: the other half of snapshot()."""
    _REGISTRY.clear()
    _REGISTRY.update(snap)


@dataclass
class PerturbationResult:
    perturbation: str
    structure_destroyed: str
    expectation: str  # 'must_move' | 'must_not_move'
    baseline: float | None
    perturbed: float | None
    abs_delta: float | None
    normalised: float | None  # delta as a fraction of between-document spread
    passed: bool
    reason: str = ""


@dataclass
class MeasureVerdict:
    measure_id: str
    status: Status
    spread: float | None
    results: list[PerturbationResult] = field(default_factory=list[PerturbationResult])
    errors: list[str] = field(default_factory=list[str])

    @property
    def passed(self) -> bool:
        return not self.errors and all(r.passed for r in self.results)


# A move is real only relative to the spread the measure shows across documents.
# An absolute delta cannot be read on its own: the same delta is negligible for a
# measure that varies widely across documents and large for one that barely
# varies.
MOVE_THRESHOLD = 0.25   # must-move: at least this fraction of spread
STILL_THRESHOLD = 0.05  # must-not-move: at most this fraction of spread


def _spread(values: Iterable[float]) -> float | None:
    """
    Between-document spread: the interquartile range, falling back to max−min
    only when the IQR is degenerate.

    Under max−min a single outlier document sets the denominator and can make a
    valid falsifier read as failing. On block B (working markdown, n=198),
    equalize_sections moves the section-size-dispersion measure by 0.045 of the
    max−min spread but 0.821 of the IQR, and resplit_paragraphs moves the
    paragraph-length-median measure by 0.189 of the max−min spread (below the
    0.25 must-move threshold) but 2.380 of the IQR (corpus/exhibits/shape.json
    records both denominators). The IQR is insensitive to a single outlier,
    and the thresholds are the same under both denominators.
    """
    vals = list(values)
    if len(vals) < 2:
        return None
    q1, _, q3 = statistics.quantiles(vals, n=4, method="inclusive")
    iqr = q3 - q1
    if iqr > 0:
        return float(iqr)
    lo, hi = min(vals), max(vals)
    return hi - lo if hi > lo else None


def verify(
    descriptor: MeasureDescriptor,
    corpus: list[str],
    compute: Callable[[FeatureContext], float | None] | None = None,
    seed: int = 0,
) -> MeasureVerdict:
    """
    Test a measure's own declarations against a corpus.

    Each evaluated text (a corpus document or its perturbed copy) is parsed into
    a Document and read through a fail-closed FeatureContext limited to the
    measure's declared `requires`. The harness therefore also exercises the
    declaration itself: a measure that reads an undeclared feature fails here,
    on the corpus, before it can ship.

    Returns a verdict instead of raising: a failing measure is a finding to
    record, not an exception to handle.
    """
    fn = compute or descriptor.compute
    allowed = frozenset(descriptor.requires)

    def run(text: str) -> float | None:
        return fn(FeatureContext(Document.parse(text), allowed))

    verdict = MeasureVerdict(descriptor.id, descriptor.status, None)

    if descriptor.status is Status.RETIRED:
        return verdict
    if len(corpus) < 2:
        verdict.errors.append("corpus too small to establish a spread (need >= 2 documents)")
        return verdict

    try:
        baselines = [run(doc) for doc in corpus]
    except Exception as exc:  # a measure that raises on real text fails
        verdict.errors.append(f"compute raised on the corpus: {exc!r}")
        return verdict

    spread = _spread([b for b in baselines if b is not None])
    verdict.spread = spread
    if spread is None:
        # A gap in the corpus, not a fault in the measure: without a spread the
        # normalised delta is undefined, and forcing a ratio out of it would turn
        # noise into a verdict.
        verdict.errors.append(
            "no between-document spread on this corpus; normalisation is undefined "
            "(untestable-on-corpus, not failing)"
        )
        return verdict

    def check(p: Perturbation, expectation: str) -> PerturbationResult:
        deltas: list[float] = []
        for doc, base in zip(corpus, baselines):
            if base is None:
                continue
            try:
                got = run(p.apply(doc, seed))
            except Exception as exc:
                return PerturbationResult(p.name, p.structure_destroyed, expectation,
                                          base, None, None, None, False,
                                          f"compute raised under perturbation: {exc!r}")
            if got is not None:
                deltas.append(abs(got - base))
        if not deltas:
            return PerturbationResult(p.name, p.structure_destroyed, expectation,
                                      None, None, None, None, False,
                                      "no comparable values produced")
        med = statistics.median(deltas)
        norm = med / spread
        if expectation == "must_move":
            ok = norm >= MOVE_THRESHOLD
            why = "" if ok else (
                f"invariant under destruction of {p.structure_destroyed}: "
                f"median move {norm:.3f} of spread, below {MOVE_THRESHOLD}"
            )
        else:
            ok = norm <= STILL_THRESHOLD
            why = "" if ok else (
                f"sensitive to {p.structure_destroyed}, which it does not claim to read: "
                f"median move {norm:.3f} of spread, above {STILL_THRESHOLD}"
            )
        return PerturbationResult(p.name, p.structure_destroyed, expectation,
                                  None, None, med, round(norm, 4), ok, why)

    for p in descriptor.must_move_under:
        verdict.results.append(check(p, "must_move"))
    for p in descriptor.must_not_move_under:
        verdict.results.append(check(p, "must_not_move"))
    return verdict


@dataclass(frozen=True)
class DiscriminationVerdict:
    measure_id: str
    n: int
    k: int
    omega2: float
    p: float
    floor: float           # ω² reachable by label noise alone at this N and k
    threshold: float
    max_p: float
    adequately_powered: bool  # floor < threshold; otherwise no verdict is readable
    passed: bool


def discriminate(
    descriptor: MeasureDescriptor,
    corpus_by_group: Mapping[str, Sequence[str]],
    n_perm: int = 2000,
    seed: int = 0,
) -> DiscriminationVerdict:
    """
    Test a measure's optional DiscriminationClaim against a grouped corpus.

    The verdict carries the detectability floor next to the threshold. A corpus
    whose label-noise floor is at or above the claimed threshold cannot
    adjudicate the claim, so `passed` is False there whatever the measure does,
    and `adequately_powered` separates that case from a measure that was tested
    and failed.
    """
    if descriptor.discrimination is None:
        raise ValueError(f"{descriptor.id}: no DiscriminationClaim declared")
    claim = descriptor.discrimination
    allowed = frozenset(descriptor.requires)

    groups: dict[str, list[float]] = {}
    for group, texts in corpus_by_group.items():
        values: list[float] = []
        for text in texts:
            v = descriptor.compute(FeatureContext(Document.parse(text), allowed))
            if v is not None:
                values.append(v)
        if values:
            groups[group] = values

    omega2 = omega_squared(groups)
    p = permutation_p(groups, n_perm=n_perm, seed=seed)
    floor = null_floor(groups, q=1 - claim.max_p, n_perm=n_perm, seed=seed)
    powered = floor < claim.min_omega_squared
    return DiscriminationVerdict(
        measure_id=descriptor.id,
        n=sum(len(v) for v in groups.values()),
        k=len(groups),
        omega2=omega2, p=p, floor=floor,
        threshold=claim.min_omega_squared, max_p=claim.max_p,
        adequately_powered=powered,
        passed=powered and omega2 >= claim.min_omega_squared and p <= claim.max_p,
    )
