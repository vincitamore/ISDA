"""
Specimens: named documents that carry their framework claims as executable
assertions.

A worked example makes claims about itself ("Musica is the dominant stratum",
"seven Stock rows give RI exactly 1.0"). A specimen turns each such claim into
an assertion that executes and is counted as PASSING, FAILING or UNTESTABLE.
The summary line always includes the UNTESTABLE count, so a claim the
framework has no instrument for stays visible as an obligation instead of
reading as true.

The five-file contract (corpus/manifest.json pins the layout):

- text.md          the body, committed verbatim. Its byte length must equal the
                   ledger's raw_bytes: every metric is scored against that
                   figure, so a body that differs from its ledger invalidates
                   every number derived from it.
- ledger.json      the analyst's seven-row ledger, in exactly the format
                   isda_preprocess.py --ledger accepts. Authored judgment.
- assertions.json  the framework's claims about this specimen, as typed
                   executable assertions. Authored intent.
- expected.json    derived state, written only by `python -m isda.specimens
                   pin`: content hash, measured counts, registered-measure
                   values, scored metrics and assertion verdicts. Any
                   difference from the re-derived state is reported as STALE,
                   and nothing refreshes the pin except an explicit `pin` run.
                   A verdict flip is a finding to examine before a deliberate
                   re-pin.
- analysis.md      provenance, topic, telos/substrate and the worked reading.
                   The topic lives here and only here: directory slugs name
                   the framework role a specimen exercises, never its subject.

Assertion kinds (the complete vocabulary):

- metric    a scored ledger metric (SCR / ND / RI) against a comparator.
- ledger    an arithmetic property of the ledger itself: dominant_stratum,
            stratum_share, intensity_rungs, uniform_intensity.
- measure   a registered measure evaluated on text.md. UNTESTABLE when the
            named measure is not registered.
- quantile  the specimen's rank on a measure against a corpus block.
            UNTESTABLE when the measure is not registered or the block is not
            built.
- judgment  a claim with no instrument, listed so the UNTESTABLE count shows
            how much of the framework has no executable test.

Scoring goes through isda.framework.metrics, the package's canonical
implementation of the metric arithmetic. The standalone isda_preprocess.py
keeps its own copy because a prose-only skill directory has no package to
import; tests/test_metrics_parity.py requires the two to agree exactly, so a
change made to only one copy fails a test.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, cast

from .core.document import Document
from .core.features import FeatureContext
from .core.tokens import words as _prose_words
from .corpus import repo_root
from .kernel.descriptor import MeasureUnavailable

FIVE_FILES = ("text.md", "ledger.json", "assertions.json", "expected.json", "analysis.md")
STRATA = ("grammatica", "dialectica", "rhetorica", "arithmetica",
          "geometria", "musica", "astronomia")
INTENSITIES = ("Stock", "Implied", "Selected", "Original")

Verdict = Literal["PASSING", "FAILING", "UNTESTABLE"]


class SpecimenInvalid(RuntimeError):
    """The specimen violates its own contract. The message names the file."""


@dataclass(frozen=True)
class Specimen:
    slug: str
    path: Path
    text: str
    ledger: dict[str, Any]
    assertions: list[dict[str, Any]]
    expected: dict[str, Any] | None  # None when expected.json is absent (not pinned)


@dataclass(frozen=True)
class AssertionResult:
    assertion_id: str
    claim: str
    verdict: Verdict
    detail: str


# ---------------------------------------------------------------- loading

def _specimen_dir(root: Path | None = None) -> Path:
    return repo_root(root) / "corpus" / "specimens"


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_specimen(path: Path) -> Specimen:
    """Load one specimen and enforce the parts of the contract that are local
    to it: the four authored files present (expected.json is derived and may
    be absent), a well-formed seven-row ledger, and the raw-byte coupling
    between body and ledger."""
    missing = [n for n in FIVE_FILES if not (path / n).is_file()
               and not (n == "expected.json")]
    if missing:
        raise SpecimenInvalid(f"{path.name}: missing {', '.join(missing)}")

    text = (path / "text.md").read_text(encoding="utf-8")
    ledger_raw: Any = _read_json(path / "ledger.json")
    if not isinstance(ledger_raw, dict) or set(cast(dict[str, Any], ledger_raw)) != {
        "raw_bytes", "strata"
    }:
        raise SpecimenInvalid(
            f"{path.name}: ledger.json must be exactly {{raw_bytes, strata}}: "
            "provenance belongs in analysis.md"
        )
    ledger = cast(dict[str, Any], ledger_raw)
    strata = cast(dict[str, dict[str, Any]], ledger["strata"])
    if set(strata) != set(STRATA):
        raise SpecimenInvalid(f"{path.name}: ledger strata != the seven strata")
    for name, row in strata.items():
        if row.get("intensity") not in INTENSITIES:
            raise SpecimenInvalid(f"{path.name}: {name}: bad intensity {row.get('intensity')!r}")
        if not isinstance(row.get("compressed"), (int, float)) or row["compressed"] <= 0:
            raise SpecimenInvalid(f"{path.name}: {name}: compressed must be a positive number")

    actual = len(text.encode("utf-8"))
    if actual != ledger["raw_bytes"]:
        raise SpecimenInvalid(
            f"{path.name}: text.md is {actual} B but ledger.json says "
            f"{ledger['raw_bytes']}: the body has moved under the ledger, so "
            "every metric scored against it would be wrong"
        )

    assertions_raw: Any = _read_json(path / "assertions.json")
    if not isinstance(assertions_raw, dict):
        raise SpecimenInvalid(f"{path.name}: assertions.json must be {{specimen, assertions: [...]}}")
    rows_any = cast(dict[str, Any], assertions_raw).get("assertions")
    if not isinstance(rows_any, list):
        raise SpecimenInvalid(f"{path.name}: assertions.json must be {{specimen, assertions: [...]}}")
    rows = cast(list[dict[str, Any]], rows_any)
    seen: set[str] = set()
    for arow in rows:
        for req in ("id", "claim", "kind"):
            if not isinstance(arow.get(req), str) or not arow[req]:
                raise SpecimenInvalid(f"{path.name}: every assertion needs id, claim, kind")
        if arow["id"] in seen:
            raise SpecimenInvalid(f"{path.name}: duplicate assertion id {arow['id']!r}")
        seen.add(cast(str, arow["id"]))

    expected_path = path / "expected.json"
    expected: dict[str, Any] | None = (
        cast(dict[str, Any], _read_json(expected_path)) if expected_path.is_file() else None
    )
    return Specimen(path.name, path, text, ledger, rows, expected)


def load_specimens(root: Path | None = None) -> tuple[Specimen, ...]:
    sdir = _specimen_dir(root)
    dirs = sorted(p for p in sdir.iterdir() if p.is_dir())
    if not dirs:
        raise SpecimenInvalid(f"no specimens under {sdir}")
    return tuple(load_specimen(p) for p in dirs)


# ---------------------------------------------------------------- scoring

def score_ledger(specimen: Specimen, root: Path | None = None) -> dict[str, Any]:
    """Score the specimen's ledger through the canonical metric implementation.

    The document is attached to the ledger so the compression floor runs, as
    isda_preprocess.py does for --ledger-document. `root` is accepted so the
    signature matches the other loaders; scoring needs no filesystem beyond
    what the Specimen already carries.
    """
    del root  # unused; see docstring
    from .framework.metrics import score_ledger as _score

    result = _score({**specimen.ledger, "document": specimen.text})
    if not result.get("ok"):
        errors = "; ".join(str(e) for e in result.get("errors", []))
        raise SpecimenInvalid(f"{specimen.slug}: ledger scoring failed: {errors[:300]}")
    return result


# ---------------------------------------------------------------- assertions

def _compare(value: float | str | None, spec: Mapping[str, Any]) -> tuple[bool, str]:
    """Evaluate the comparator vocabulary: equals(+tol) | min | max | between."""
    if value is None:
        return False, "no value produced"
    if "equals" in spec:
        target = spec["equals"]
        if isinstance(target, str) or isinstance(value, str):
            ok = value == target
            return ok, f"{value!r} vs {target!r}"
        tol = float(spec.get("tol", 0.0))
        ok = abs(float(value) - float(target)) <= tol
        return ok, f"{value} vs {target} (tol {tol})"
    if "between" in spec:
        lo, hi = spec["between"]
        ok = float(lo) <= float(value) <= float(hi)
        return ok, f"{value} in [{lo}, {hi}]"
    checks: list[str] = []
    ok = True
    if "min" in spec:
        ok = ok and float(value) >= float(spec["min"])
        checks.append(f"{value} >= {spec['min']}")
    if "max" in spec:
        ok = ok and float(value) <= float(spec["max"])
        checks.append(f"{value} <= {spec['max']}")
    if not checks:
        return False, "assertion declares no comparator (equals/between/min/max)"
    return ok, " and ".join(checks)


def _ledger_property(row: Mapping[str, Any], scored: Mapping[str, Any],
                     ledger: Mapping[str, Any]) -> float | str | None:
    prop = row.get("property")
    if prop == "dominant_stratum":
        return str(scored["dominant_stratum"])
    if prop == "stratum_share":
        per: Mapping[str, Any] = scored["per_stratum"]
        return float(per[str(row["stratum"])]["share_of_core"])
    if prop == "intensity_rungs":
        strata: Mapping[str, Any] = ledger["strata"]
        return float(len({r["intensity"] for r in strata.values()}))
    if prop == "uniform_intensity":
        strata2: Mapping[str, Any] = ledger["strata"]
        tags = {r["intensity"] for r in strata2.values()}
        return tags.pop() if len(tags) == 1 else None
    raise SpecimenInvalid(f"unknown ledger property {prop!r}")


def _registered_measure(measure_id: str) -> Any | None:
    import isda.measures  # noqa: F401  # import-time registration
    assert isda.measures  # the import registers the measures; the assert marks it used for pyright
    from .kernel import registry
    try:
        return registry.get(measure_id)
    except KeyError:
        return None


def run_assertion(specimen: Specimen, row: Mapping[str, Any],
                  scored: Mapping[str, Any], root: Path | None = None) -> AssertionResult:
    aid, claim, kind = str(row["id"]), str(row["claim"]), str(row["kind"])

    if kind == "judgment":
        return AssertionResult(aid, claim, "UNTESTABLE",
                               "judgment-only claim; no instrument exists")

    if kind == "metric":
        metrics: Mapping[str, Any] = scored["metrics"]
        value = metrics.get(str(row["metric"]).upper())
        ok, detail = _compare(value, row)
        return AssertionResult(aid, claim, "PASSING" if ok else "FAILING", detail)

    if kind == "ledger":
        value = _ledger_property(row, scored, specimen.ledger)
        ok, detail = _compare(value, row)
        return AssertionResult(aid, claim, "PASSING" if ok else "FAILING", detail)

    if kind == "measure":
        desc = _registered_measure(str(row["measure"]))
        if desc is None:
            return AssertionResult(aid, claim, "UNTESTABLE",
                                   f"measure {row['measure']!r} is not registered")
        try:
            ctx = FeatureContext(Document.parse(specimen.text), frozenset(desc.requires))
            value = desc.compute(ctx)
        except MeasureUnavailable as exc:  # the backend is absent on this machine: not a failure
            return AssertionResult(aid, claim, "UNTESTABLE",
                                   f"backend unavailable: {exc}")
        except Exception as exc:  # crashing on real text is a failure, not a gap
            return AssertionResult(aid, claim, "FAILING", f"compute raised: {exc!r}")
        ok, detail = _compare(value, row)
        return AssertionResult(aid, claim, "PASSING" if ok else "FAILING", detail)

    if kind == "quantile":
        desc = _registered_measure(str(row["measure"]))
        if desc is None:
            return AssertionResult(aid, claim, "UNTESTABLE",
                                   f"measure {row['measure']!r} is not registered")
        from .corpus import CorpusUnavailable, load_block
        try:
            docs = load_block(str(row["block"]), root)
        except CorpusUnavailable as exc:
            return AssertionResult(aid, claim, "UNTESTABLE",
                                   f"corpus unavailable: {exc}")
        allowed = frozenset(desc.requires)
        try:
            values = [v for d in docs
                      if (v := desc.compute(FeatureContext(Document.parse(d.text), allowed)))
                      is not None]
            own = desc.compute(FeatureContext(Document.parse(specimen.text), allowed))
        except MeasureUnavailable as exc:
            return AssertionResult(aid, claim, "UNTESTABLE",
                                   f"backend unavailable: {exc}")
        if own is None or not values:
            return AssertionResult(aid, claim, "FAILING", "no comparable values produced")
        q = sum(1 for v in values if v <= own) / len(values)
        ok = q >= float(row["min_quantile"])
        return AssertionResult(aid, claim, "PASSING" if ok else "FAILING",
                               f"quantile {q:.3f} vs min {row['min_quantile']}"
                               f" (n={len(values)})")

    raise SpecimenInvalid(f"{specimen.slug}: unknown assertion kind {kind!r}")


def run_assertions(specimen: Specimen, root: Path | None = None,
                   scored: Mapping[str, Any] | None = None) -> list[AssertionResult]:
    scored = scored if scored is not None else score_ledger(specimen, root)
    return [run_assertion(specimen, row, scored, root) for row in specimen.assertions]


def summary_line(results: list[AssertionResult]) -> str:
    """Count the verdicts on one line. The line always includes the UNTESTABLE
    count, so claims without an instrument stay visible wherever it is printed."""
    n = {v: sum(1 for r in results if r.verdict == v)
         for v in ("PASSING", "FAILING", "UNTESTABLE")}
    return (f"{len(results)} assertions ({n['PASSING']} passing, "
            f"{n['FAILING']} failing, {n['UNTESTABLE']} untestable)")


# ---------------------------------------------------------------- pin/verify

def _measure_pins(specimen: Specimen) -> tuple[dict[str, float], set[str]]:
    """Every registered measure's value on this body, plus the ids whose
    optional backend is absent on this machine. The caller treats those as
    unknowable here, never as drift."""
    import isda.measures  # noqa: F401  # import-time registration
    assert isda.measures
    from .kernel import registry
    pins: dict[str, float] = {}
    unavailable: set[str] = set()
    for desc in registry.all_measures():
        try:
            v = desc.compute(FeatureContext(Document.parse(specimen.text),
                                            frozenset(desc.requires)))
        except MeasureUnavailable:
            unavailable.add(desc.id)
            continue
        except Exception:
            continue
        if v is not None:
            pins[desc.id] = round(float(v), 6)
    return pins, unavailable


def _derive_expected(
    specimen: Specimen, root: Path | None = None,
) -> tuple[dict[str, Any], list[AssertionResult], set[str]]:
    scored = score_ledger(specimen, root)
    results = run_assertions(specimen, root, scored)
    floor: Mapping[str, Any] = scored["compression_floor"]
    pins, unavailable = _measure_pins(specimen)
    return {
        "written_by": "python -m isda.specimens pin: derived state, never hand-edited",
        "sha256": hashlib.sha256(specimen.text.encode("utf-8")).hexdigest(),
        "raw_bytes": len(specimen.text.encode("utf-8")),
        "prose_words": len(_prose_words(Document.parse(specimen.text).prose_text)),
        "measures": pins,
        "metrics": dict(scored["metrics"]),
        "compression_floor": {
            "checked": bool(floor.get("checked")),
            "C": floor.get("C"),
            "margin_bytes": floor.get("margin_bytes"),
        },
        "verdicts": {r.assertion_id: r.verdict for r in results},
    }, results, unavailable


def pin(root: Path | None = None, only: str | None = None) -> int:
    """Write expected.json for each specimen, or only the one named by `only`.
    Re-pinning is deliberate: review the diff, because a changed verdict or
    metric needs investigation before it is accepted."""
    for sp in load_specimens(root):
        if only and sp.slug != only:
            continue
        expected, results, unavailable = _derive_expected(sp, root)
        (sp.path / "expected.json").write_text(
            json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")
        note = (f"; {len(unavailable)} measure(s) unavailable here, unpinned"
                if unavailable else "")
        print(f"{sp.slug}: pinned: {summary_line(results)}{note}")
    return 0


def verify_specimens(root: Path | None = None) -> int:
    """Check every specimen against its pin; return 1 if any is invalid,
    unpinned or STALE. The contract, the pinned values and the pinned verdicts
    are all re-derived, and any difference prints STALE."""
    failures = 0
    sdir = _specimen_dir(root)
    for path in sorted(p for p in sdir.iterdir() if p.is_dir()):
        try:
            sp = load_specimen(path)
        except SpecimenInvalid as exc:
            print(f"INVALID: {exc}")
            failures += 1
            continue
        if sp.expected is None:
            print(f"{sp.slug}: UNPINNED: run `python -m isda.specimens pin`")
            failures += 1
            continue
        derived, results, unavailable = _derive_expected(sp, root)
        drift = _drift_keys(derived, sp.expected, results, unavailable)
        if drift:
            print(f"{sp.slug}: STALE: {', '.join(drift)} differ from the pin; "
                  "investigate, then re-pin deliberately")
            failures += 1
        else:
            note = (f"; {len(unavailable)} measure(s) unavailable here, pins "
                    "not checked" if unavailable else "")
            print(f"{sp.slug}: OK: {summary_line(results)}{note}")
    return 1 if failures else 0


def _drift_keys(derived: Mapping[str, Any], expected: Mapping[str, Any],
                results: list[AssertionResult], unavailable: set[str]) -> list[str]:
    """Pin/derivation differences that count as drift on this machine.

    A measure whose optional backend is absent here cannot be checked here,
    and neither can a quantile against a corpus block that is not built
    here: the pinned value, and any verdict whose runner reported either
    gap, are skipped, as corpus tests skip where a block is not built.
    Everything else compares exactly, including a measure that is available
    here but missing from the pin: that counts as drift, because a new
    measure needs a deliberate re-pin.
    """
    drift: list[str] = []
    backend_gaps = {r.assertion_id for r in results
                    if r.verdict == "UNTESTABLE"
                    and r.detail.startswith(("backend unavailable",
                                             "corpus unavailable"))}
    for k in derived:
        if k == "written_by":
            continue
        if k == "measures":
            exp_m = cast("Mapping[str, Any]", expected.get("measures", {}))
            der_m = cast("Mapping[str, Any]", derived["measures"])
            bad = sorted(
                mid for mid in set(exp_m) | set(der_m)
                if mid not in unavailable and exp_m.get(mid) != der_m.get(mid)
            )
            if bad:
                drift.append("measures(" + ", ".join(bad) + ")")
        elif k == "verdicts":
            exp_v = cast("Mapping[str, Any]", expected.get("verdicts", {}))
            der_v = cast("Mapping[str, Any]", derived["verdicts"])
            bad = sorted(
                aid for aid in set(exp_v) | set(der_v)
                if aid not in backend_gaps and exp_v.get(aid) != der_v.get(aid)
            )
            if bad:
                drift.append("verdicts(" + ", ".join(bad) + ")")
        elif derived[k] != expected.get(k):
            drift.append(k)
    return drift


# ---------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    verb = argv[0] if argv else "verify"
    if verb == "pin":
        return pin(only=argv[1] if len(argv) > 1 else None)
    if verb == "verify":
        return verify_specimens()
    if verb == "run":
        total: list[AssertionResult] = []
        for sp in load_specimens():
            results = run_assertions(sp)
            total.extend(results)
            print(f"{sp.slug}: {summary_line(results)}")
            for r in results:
                print(f"  {r.verdict:10s} {r.assertion_id}: {r.detail}")
        print(f"\nall specimens: {summary_line(total)}")
        return 0
    print("usage: python -m isda.specimens [pin [slug] | verify | run]")
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
