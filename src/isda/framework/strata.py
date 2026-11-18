"""
The seven strata and the intensity ladder, as data.

These constants define the framework's judgment vocabulary: the analyst
supplies a seven-row ledger over them, and the metric arithmetic consumes them.
The standalone `isda_preprocess.py` carries a second copy because it must run
alone in a prose-only skill directory, with no package alongside;
`tests/test_metrics_parity.py` pins the two copies together, so a weight
changed in one place and not the other fails a test.

Weight provenance: SKILL.md Step 5 defines ND's intensity_weight
(Stock 0.0, Implied 0.1, Selected 0.3, Original 1.0) and RI's
retrievable_weight (Stock 1.0, Implied 0.7, Selected 0.0, Original 0.0).
Changing either requires re-scoring every ledger in examples.md in the same
change; `tests/test_examples_doc.py` enforces this.
"""

from __future__ import annotations

STRATA: tuple[str, ...] = (
    "grammatica", "dialectica", "rhetorica",
    "arithmetica", "geometria", "musica", "astronomia",
)

INTENSITIES: tuple[str, ...] = ("Stock", "Implied", "Selected", "Original")

ND_WEIGHT: dict[str, float] = {
    "Stock": 0.0, "Implied": 0.1, "Selected": 0.3, "Original": 1.0,
}
RI_WEIGHT: dict[str, float] = {
    "Stock": 1.0, "Implied": 0.7, "Selected": 0.0, "Original": 0.0,
}
