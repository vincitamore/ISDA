# SPDX-License-Identifier: GPL-2.0-only
#
# Only this file is licensed GPL-2.0; the rest of this repository is MIT. It
# is the only file that imports `ideadensity` (GPL-2.0), and licensing it
# under the same terms as that dependency settles the combined-work question
# for this file. The package registers this module at import; `ideadensity`
# itself is imported lazily, when the measure runs with the [nlp] extra
# installed.
"""
Arithmetica: propositional density, measured with CPIDR.

reference.md §4 defines Arithmetica as proposition count via CPIDR, the
framework's most operationalizable formal claim and the only one with an
off-the-shelf validated implementation: CPIDR agrees with human consensus at
r = 0.97 against a human-to-human baseline of r = 0.82, and `ideadensity`
reproduces CPIDR 3.2 to within about 0.5%. A word scramble destroys every
proposition in a document while preserving its word multiset, so a measure
that reads propositions must move under it; the declared falsifiers are
`scramble_words` and `scramble_within_sentence`.

CPIDR's part-of-speech rules are English rules, and on non-English input they
emit a confident, meaningless number. The measure therefore fails closed: a
guard affirms that the prose is English before the backend runs, and anything
it cannot affirm (foreign-language prose, header and identifier text, texts
too short to judge) returns None rather than a wrong number.

The guard is the fraction of prose words that are distinctively English
function words, that is, function words that are not also common words in
German, French, Spanish, Italian or Dutch, so prose in those languages scores
near zero. The threshold is 0.05 with a 20-word minimum. On block B (working
markdown; n = 198, all English) the only documents under it are five emails
with rates of 0.004 to 0.031, listed under `guard_excluded` in
corpus/exhibits/propositional-density.json. Text that is mostly headers and
identifiers is refused by design: CPIDR on it does not measure propositional
density.
"""

from __future__ import annotations

from typing import Any, cast

from ..core.features import FeatureContext
from ..core.tokens import words as _words
from ..kernel.descriptor import (
    DiscriminationClaim, Kind, MeasureDescriptor, MeasureUnavailable,
    NullModel, Status,
)
from ..kernel.perturb import SCRAMBLE_IN_SENTENCE, SCRAMBLE_WORDS
from ..kernel.registry import register
from ._cache import HashCache

PARAMS: dict[str, object] = {
    "backend": "ideadensity",
    "backend_version": "0.5.1",       # pinned; any other version is refused
    "algorithm": "cpidr",
    "spacy_model": "en_core_web_sm",
    "spacy_model_version": "3.8.0",   # pinned; any other version is refused
    "language": "en",
    "scope": "prose",
    "english_guard_min_rate": 0.05,
    "english_guard_min_words": 20,
}

# Distinctively English: excludes every token that is also a common word in
# German, French, Spanish, Italian, or Dutch (in, an, was, man, so, on, a,
# at, will, over, us, ...). See the guard calibration in the module docstring.
_ENGLISH_MARKERS = frozenset(
    "the of and to is that it for with are by this be from or not we you "
    "they he she but have has had which their its one all when what who how "
    "if do does did than then there them his her your our my him out up "
    "down under after before into about".split()
)

_cache = HashCache(
    "cpidr.json", PARAMS,
    "isda.measures.arithmetica_cpidr: derived state, keyed by content hash; "
    "delete freely, it rebuilds",
)


def english_marker_rate(text: str) -> tuple[int, float]:
    """(prose_word_count, distinctively-English marker fraction)."""
    ws = [w.lower() for w in _words(text)]
    if not ws:
        return 0, 0.0
    return len(ws), sum(1 for w in ws if w in _ENGLISH_MARKERS) / len(ws)


_backend_fn: Any = None


def _backend() -> Any:
    global _backend_fn
    if _backend_fn is not None:
        return _backend_fn
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _v
    model = str(PARAMS["spacy_model"])
    try:
        import importlib

        ideadensity = importlib.import_module("ideadensity")  # no stubs shipped
        got = _v("ideadensity")
        model_version = _v(model)
    except (ImportError, PackageNotFoundError) as exc:
        raise MeasureUnavailable(
            "arithmetica.propositional-density needs the [nlp] extra "
            f"(pip install isda[nlp], then python -m spacy download {model}) "
            "and no cached value exists for this text on this machine"
        ) from exc
    # A version that differs from the pin is refused with an error rather than
    # measured under: the pinned versions are part of the measure's identity,
    # and a tagger upgrade can move every value. Update PARAMS deliberately
    # and re-pin.
    if got != PARAMS["backend_version"]:
        raise MeasureUnavailable(
            f"ideadensity {got} != pinned {PARAMS['backend_version']}; "
            "install the pinned version (pip install isda[nlp]), or update "
            "PARAMS deliberately and re-pin the corpus"
        )
    if model_version != PARAMS["spacy_model_version"]:
        raise MeasureUnavailable(
            f"{model} {model_version} != pinned "
            f"{PARAMS['spacy_model_version']}; install the pinned model "
            "(spaCy 3.8 downloads it), or update PARAMS deliberately and "
            "re-pin the corpus"
        )
    _backend_fn = cast(Any, ideadensity).cpidr
    return _backend_fn


def _cpidr_stats(text: str) -> tuple[float, float, float] | None:
    """(word_count, proposition_count, density) for one prose text, cached."""
    row = _cache.get(text)
    if row is not None:
        return row[0], row[1], row[2]
    cpidr = _backend()
    word_count, proposition_count, density, _ = cpidr(text)
    result = (float(word_count), float(proposition_count), float(density))
    _cache.put(text, result)
    return result


def depid_density(text: str) -> float:
    """
    DEPID (dependency-parse idea density) for one prose text, from the same
    pinned backend. It is not a registered measure: the gate script records it
    beside CPIDR as a second operationalization of the construct.
    """
    _backend()  # enforces the version pins
    import importlib

    depid = cast(Any, importlib.import_module("ideadensity")).depid
    density, _, _ = depid(text)
    return float(density)


def propositional_density(ctx: FeatureContext) -> float | None:
    text = cast(str, ctx.get("prose.text"))
    n, rate = english_marker_rate(text)
    if n < int(cast(int, PARAMS["english_guard_min_words"])):
        return None  # too short to affirm the language domain
    if rate < float(cast(float, PARAMS["english_guard_min_rate"])):
        return None  # cannot affirm English prose: fail closed, never guess
    stats = _cpidr_stats(text)
    return None if stats is None else stats[2]


PROPOSITIONAL_DENSITY = register(MeasureDescriptor(
    id="arithmetica.propositional-density",
    version="1.0.0",
    construct=(
        "Propositional density: propositions per word via CPIDR (the "
        "operationalization reference.md §4 names for the Arithmetica "
        "stratum), over the prose view. English-only by declaration; input "
        "the guard cannot affirm as English prose returns no value."
    ),
    requires=("prose.text",),
    kind=Kind.CLAIM,
    compute=propositional_density,
    must_move_under=(SCRAMBLE_WORDS, SCRAMBLE_IN_SENTENCE),
    null=NullModel(
        kind="permutation",
        derived_from=(
            "the same document with word order destroyed (scramble_words): "
            "CPIDR's proposition rules read syntax, so order-free text is "
            "the no-propositions expectation"
        ),
    ),
    strata=("arithmetica",),
    # Gate evidence (block B, corpus/exhibits/propositional-density.json):
    # separates genres at power (omega-squared 0.1439, p = 5e-4, label-noise
    # floor 0.0546, n = 193 after the language guard), and scramble_words
    # moves it 0.59 of interquartile spread. DEPID, a different
    # operationalization recorded in the same exhibit, also separates genres
    # (omega-squared 0.1511; rho 0.459 against CPIDR).
    discrimination=DiscriminationClaim(groups_by="genre"),
    status=Status.ACTIVE,
    interpretation=(
        "A rule-conditioned quantity: values are comparable only under the "
        "identical backend and tagger versions recorded in params. Computed "
        "on the prose view. None means the language guard refused, not zero "
        "density. Separates the seven block B genres: omega-squared 0.1439, "
        "p = 5e-4, n = 193 after the guard "
        "(corpus/exhibits/propositional-density.json)."
    ),
    params=PARAMS,
))
