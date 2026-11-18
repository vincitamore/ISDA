"""
The measure contract.

A measure is a claim about a text. This module makes that claim falsifiable by
construction: a CLAIM cannot register without naming a perturbation that must
destroy it and a null model that says what "no signal" looks like. A
DESCRIPTION, which cannot be wrong, owes neither. Every other field here exists
to make that rule enforceable.

Reading a measure's code does not show whether it responds to the construct it
names. Destroying the construct and recomputing does: an order measure must move
when order is shuffled, and one that does not is not reading order. A name is
not evidence of a distinct construct either, since two measures under different
names can compute one quantity (`stats.redundancy_findings` checks for this).
The harness (`registry.verify`) therefore tests each declaration against a
corpus and fails when it is false.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal, Mapping, Sequence

from ..core.features import FeatureContext


class MeasureUnavailable(RuntimeError):
    """
    The measure's optional backend is not installed on this machine.

    This is a statement about the machine, not about the text. Consumers
    (specimen pins, the verify gate, the CLI) must render it as unavailability
    and skip, the way corpus tests skip where a block is not built. Rendering it
    as an error, or reading it as drift against another machine's pins, would
    make a missing backend look like a failing measure and push consumers to
    suppress the gate.
    """


class Kind(str, Enum):
    """
    Whether a value can be wrong.

    A DESCRIPTION cannot be wrong: a byte count is a byte count. A CLAIM asserts
    something about the text and can therefore be false, so it needs a null model
    and a falsifier. Carrying the distinction in the type removes the need for a
    prose note beside each feature warning readers not to over-read it.
    """

    DESCRIPTION = "description"
    CLAIM = "claim"


class Status(str, Enum):
    """
    Whether a measure has earned its place. Status is independent of Kind.

    Kind asks whether a value can be wrong; Status asks whether the measure has
    proven itself. A retired measure keeps its record instead of being removed:
    the manifest row, with its `retired_because`, is how a reader who remembers a
    number learns why it is gone.
    """

    ACTIVE = "active"
    PROVISIONAL = "provisional"
    RETIRED = "retired"


@dataclass(frozen=True)
class Perturbation:
    """
    A named, deterministic transformation of a document.

    `structure_destroyed` names what the transformation removes, for a human
    reader; `destroys` names it for the machine, as the set of features (see
    isda.core.features) whose values the perturbation does not preserve. The
    admission rule consumes `destroys`: a CLAIM must name at least one falsifier
    that destroys a feature the measure declares it reads. Whether a perturbation
    can move a measure is a relation between the perturbation and what the
    measure reads, not a property of the perturbation alone. A single global
    label cannot express that: a reordering preserves content and destroys order,
    so it is the right falsifier for a measure that reads order and the wrong one
    for a measure that reads only content.

    `destroys` is kept narrow: the structures the perturbation is designed to
    remove plus those it mechanically removes as a side effect. Extend a row in
    the same change that adds a measure which legitimately relies on a side
    effect. A broad row weakens the static check without raising an error; a
    narrow one fails at registration.

    A seeded perturbation is reproducible for a given seed. An unseeded shuffle
    would make the harness flaky and its failures indistinguishable from noise.
    """

    name: str
    structure_destroyed: str
    apply: Callable[[str, int], str]  # (text, seed) -> text
    seeded: bool = True
    destroys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NullModel:
    """
    What "no signal" looks like, and where that expectation came from.

    A null derived from the corpus being judged cannot fire: a band equal to that
    corpus's own interquartile range contains the typical document by
    construction. `derived_from` records where the expectation came from, so a
    reviewer can see that mistake before the null is used, and an empirical band
    whose source is the measured corpus is rejected at construction.
    """

    kind: Literal["permutation", "synthetic", "analytic", "empirical-band"]
    derived_from: str
    expected_range: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.kind == "empirical-band" and "measured corpus" in self.derived_from.lower():
            raise ValueError(
                "a null derived from the corpus being judged cannot fire; "
                "derive it from destroyed, synthetic, or out-of-domain inputs"
            )


@dataclass(frozen=True)
class DiscriminationClaim:
    """
    An optional claim that a measure separates named groups.

    The claim is optional because a valid measure need not separate groups: on
    a corpus whose groups do not differ in the construct, it ought to fail a
    between-group test. Making discrimination mandatory would retire such
    measures and keep invalid ones whose apparent separation tracks a confound
    such as markup density. Group separation is therefore a claim a measure may
    make, tested when made. What is never optional is `must_move_under`:
    sensitivity to the destruction of what the measure says it reads.
    """

    groups_by: str
    min_omega_squared: float = 0.10
    max_p: float = 0.01


@dataclass(frozen=True)
class MeasureDescriptor:
    """
    One measure, with everything needed to falsify it.

    `strata` is projection metadata only and may be empty. Strata and measures are
    not one-to-one: a stratum with no measure is normal, a measure serving two
    strata is normal, and a measure serving none is inventory. Tying every
    stratum to exactly one measure would force a number into each slot whether or
    not anything could measure it.
    """

    id: str
    version: str
    construct: str
    requires: tuple[str, ...]
    kind: Kind
    compute: Callable[[FeatureContext], float | None]

    must_move_under: tuple[Perturbation, ...] = ()
    must_not_move_under: tuple[Perturbation, ...] = ()
    null: NullModel | None = None
    discrimination: DiscriminationClaim | None = None

    strata: tuple[str, ...] = ()
    status: Status = Status.PROVISIONAL
    interpretation: str = ""
    retired_because: str = ""
    params: Mapping[str, object] = field(default_factory=dict[str, object])

    def __post_init__(self) -> None:
        if not self.id or " " in self.id:
            raise ValueError(f"measure id must be a non-empty slug: {self.id!r}")
        if not self.construct.strip():
            raise ValueError(f"{self.id}: construct is required. Say what this claims to measure.")

        if self.status is Status.RETIRED:
            if not self.retired_because.strip():
                raise ValueError(f"{self.id}: a retired measure must record why")
            return  # a retired measure is a record: the checks below do not apply to it

        # Admission rule. A claim that no perturbation can destroy cannot be
        # checked, because nobody can state what would show the number wrong.
        if self.kind is Kind.CLAIM:
            if not self.must_move_under:
                raise ValueError(
                    f"{self.id}: a CLAIM must name at least one perturbation that destroys it. "
                    "If no perturbation can move it, it is not measuring anything specific: "
                    "either reclassify it as a DESCRIPTION or do not ship it."
                )
            if self.null is None:
                raise ValueError(
                    f"{self.id}: a CLAIM must declare a null model. Without one its value "
                    "cannot be read: there is no 'no signal' to compare against."
                )

        overlap = {p.name for p in self.must_move_under} & {p.name for p in self.must_not_move_under}
        if overlap:
            raise ValueError(
                f"{self.id}: {sorted(overlap)} declared as both must-move and must-not-move"
            )

    @property
    def falsifiers(self) -> Sequence[Perturbation]:
        return self.must_move_under
