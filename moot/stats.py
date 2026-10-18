"""Small-sample arithmetic for the eval files. No dependencies, so the harness can be unit-tested on its own."""
from __future__ import annotations

import math

Z95_ONE_SIDED = 1.6449
Z95_TWO_SIDED = 1.9600


def wilson(k: int, n: int, z: float = Z95_TWO_SIDED) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials. With z = 1.645 each end is a one-sided 95% bound."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def wilson_upper(k: int, n: int) -> float:
    """One-sided 95% upper bound on a rate: '0 of 20' means the true rate is below this with 95% confidence."""
    return wilson(k, n, Z95_ONE_SIDED)[1]


def nearest_rank(xs: list[float], q: float) -> float:
    """Nearest-rank percentile (no interpolation): the smallest sample with at least q% of samples at or below it."""
    if not xs:
        raise ValueError("no samples")
    s = sorted(xs)
    return s[max(1, math.ceil(q / 100 * len(s))) - 1]


def timing_summary(samples_ms: list[float], warmup: int = 0, cold_ms: float | None = None) -> dict:
    """n, p50, p95 and max over the samples after dropping `warmup` leading ones. `cold_ms` is reported apart, never
    folded into the warm percentiles, and is required to be present (None means it was not measured, and says so)."""
    warm = samples_ms[warmup:]
    if not warm:
        raise ValueError("every sample was warmup")
    return dict(n=len(warm), warmup=warmup, p50=round(nearest_rank(warm, 50), 2), p95=round(nearest_rank(warm, 95), 2),
                max=round(max(warm), 2), cold=None if cold_ms is None else round(cold_ms, 2))


def fmt_rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} (95% CI {lo:.2f}–{hi:.2f})"
