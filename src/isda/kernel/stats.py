"""
The statistics the gates run on: discrimination, detectability, redundancy.

Standard library only. Every quantity here is simple enough to compute from its
definition, and a zero-dependency core is a standing contract of this package.
The price is that nothing here is fast; the corpus is hundreds of documents, not
millions, and the permutation counts are explicit parameters.

Two rules apply.

1. A threshold needs a detectability floor beside it. A non-significant result
   on an underpowered corpus is suggestive, never conclusive: with small
   per-group cells only large effects can be detected, so a null result there is
   not grounds for retiring a measure. `null_floor` states what effect size
   label noise alone reaches at this N and k; report it beside every gate
   threshold, and treat any observed effect below it as undetectable rather
   than absent.

2. Redundancy detectors must guard against constants. A zero-variance series
   trivially satisfies ratio- and difference-constancy tests, so an unguarded
   detector flags every constant series as identical to every other. Constant
   series are excluded from the pairwise detectors and reported separately,
   because a constant field is its own finding.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Mapping, Sequence

# ------------------------------------------------------------ discrimination

def omega_squared(groups: Mapping[str, Sequence[float]]) -> float:
    """
    One-way ANOVA effect size ω²: the share of population variance attributable
    to group membership. It can be slightly negative when the effect is near
    zero; it is reported as computed and never clamped.
    """
    cells = [list(v) for v in groups.values() if v]
    if len(cells) < 2:
        raise ValueError("omega_squared needs at least two non-empty groups")
    all_values = [x for cell in cells for x in cell]
    n_total = len(all_values)
    k = len(cells)
    if n_total <= k:
        raise ValueError("more groups than degrees of freedom")
    grand = statistics.fmean(all_values)
    ssb = sum(len(c) * (statistics.fmean(c) - grand) ** 2 for c in cells)
    ssw = sum((x - statistics.fmean(c)) ** 2 for c in cells for x in c)
    msw = ssw / (n_total - k)
    denom = ssb + ssw + msw
    if denom == 0:
        return 0.0
    return (ssb - (k - 1) * msw) / denom


def _permuted_omegas(groups: Mapping[str, Sequence[float]],
                     n_perm: int, seed: int) -> list[float]:
    sizes = [len(v) for v in groups.values() if v]
    pooled = [x for v in groups.values() for x in v]
    rng = random.Random(seed)
    out: list[float] = []
    for _ in range(n_perm):
        rng.shuffle(pooled)
        regrouped: dict[str, list[float]] = {}
        i = 0
        for j, size in enumerate(sizes):
            regrouped[str(j)] = pooled[i:i + size]
            i += size
        out.append(omega_squared(regrouped))
    return out


def permutation_p(groups: Mapping[str, Sequence[float]],
                  n_perm: int = 2000, seed: int = 0) -> float:
    """
    Label-permutation p-value for the observed ω². Exact in the limit and
    assumption-free, which is why it is used instead of an F distribution.
    """
    observed = omega_squared(groups)
    perms = _permuted_omegas(groups, n_perm, seed)
    exceed = sum(1 for w in perms if w >= observed)
    return (exceed + 1) / (n_perm + 1)


def null_floor(groups: Mapping[str, Sequence[float]],
               q: float = 0.99, n_perm: int = 2000, seed: int = 0) -> float:
    """
    The detectability floor: the ω² that label noise alone reaches at quantile
    `q` for this corpus shape. An observed effect at or below this value is
    indistinguishable from noise at significance 1−q, so state it beside every
    threshold. It is an α-floor, not a power analysis: it says what cannot be
    detected, not what would be detected reliably.
    """
    perms = sorted(_permuted_omegas(groups, n_perm, seed))
    idx = min(len(perms) - 1, max(0, math.ceil(q * len(perms)) - 1))
    return perms[idx]


# ------------------------------------------------------------ correlation

def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for t in range(i, j + 1):
            ranks[order[t]] = avg
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Spearman rank correlation with average-rank ties."""
    if len(xs) != len(ys) or len(xs) < 3:
        raise ValueError("spearman needs two equal series of length >= 3")
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if vx == 0 or vy == 0:
        raise ValueError("constant series have no rank correlation")
    return cov / (vx * vy)


# ------------------------------------------------------------ redundancy

@dataclass(frozen=True)
class RedundancyFinding:
    kind: str      # 'constant' | 'exact' | 'rank' | 'constant-ratio' | 'constant-difference'
    measures: tuple[str, ...]
    value: float
    detail: str


def redundancy_findings(
    series: Mapping[str, Sequence[float | None]],
    rho_threshold: float = 0.90,
    cv_threshold: float = 0.02,
    min_overlap: int = 10,
) -> list[RedundancyFinding]:
    """
    Find pairs of reported numbers that are one quantity under two names. Four
    detectors run over every pair: exact float equality, constant difference,
    constant ratio, and |Spearman| above threshold. The constancy detectors run
    first, so an affine identity is reported as one and not as a correlation.
    """
    findings: list[RedundancyFinding] = []
    usable: dict[str, Sequence[float | None]] = {}
    for name, vals in series.items():
        present = [v for v in vals if v is not None]
        if len(present) >= min_overlap and max(present) > min(present):
            usable[name] = vals
        elif present and max(present) == min(present):
            findings.append(RedundancyFinding(
                "constant", (name,), present[0],
                "zero variance across the corpus; excluded from pairwise "
                "detectors, which it would trivially satisfy"))

    names = sorted(usable)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pairs = [(x, y) for x, y in zip(usable[a], usable[b])
                     if x is not None and y is not None]
            if len(pairs) < min_overlap:
                continue
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            if xs == ys:
                findings.append(RedundancyFinding(
                    "exact", (a, b), 1.0, f"byte-identical on {len(pairs)} documents"))
                continue
            spread = max(max(xs) - min(xs), max(ys) - min(ys))
            diffs = [x - y for x, y in pairs]
            if spread > 0 and statistics.pstdev(diffs) <= cv_threshold * spread:
                findings.append(RedundancyFinding(
                    "constant-difference", (a, b), statistics.fmean(diffs),
                    f"difference constant at {statistics.fmean(diffs):.4g} "
                    f"across {len(pairs)} documents"))
                continue
            ratios = [x / y for x, y in pairs if y != 0]
            if len(ratios) >= min_overlap:
                mean_r = statistics.fmean(ratios)
                if mean_r != 0 and statistics.pstdev(ratios) / abs(mean_r) < cv_threshold:
                    findings.append(RedundancyFinding(
                        "constant-ratio", (a, b), mean_r,
                        f"ratio pinned at {mean_r:.4g} across {len(ratios)} documents"))
                    continue
            try:
                rho = spearman(xs, ys)
            except ValueError:
                continue
            if abs(rho) > rho_threshold:
                findings.append(RedundancyFinding(
                    "rank", (a, b), rho,
                    f"|Spearman| {abs(rho):.3f} exceeds {rho_threshold} undeclared"))
    return findings
