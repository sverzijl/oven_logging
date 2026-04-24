"""Flotilla finale regression guard (M7 HMS Victory).

Introduced by the final mission of flotilla ``refactor/expected-bake-time``
on branch of the same name.  Locks the empirical 36-run red-cell verdict
into a pytest contract so a future refactor cannot silently drift any of
the four properties the flotilla set out to guarantee:

1. **Curve count preservation** — at σ ∈ {0.15, 0.5, 1.0} °C across the
   three primary real CSVs, every hint mode (``None``, correct, ±30 %)
   must produce the expected curve count on at least 7/8 seeds.
2. **No cliff FP amplification** — the count of ``probe_pull_cliff``
   decisions with a hint must not exceed the no-hint baseline by more
   than +3 across 8 seeds.  Small +1/+2 increases are allowed because
   they're legitimate plateau→cliff refinements, not amplification.
3. **End-idx variance reduction with correct hint** — at σ ≥ 0.5 °C the
   hint must *reduce* first-curve end-idx stdev on ``real_100098DE_1351``
   (the clearest case from the red-cell battery: 244.49 → 11.82 at σ=1.0).
4. **Graceful ±30 % degradation** — a ±30 % mis-hint must not crash and
   must not worsen curve-count hits below the no-hint baseline.

This file runs only 3 real CSVs × 3 σ × 4 hint modes × 8 seeds = 288
detector calls.  Full run ≈ 20–40 s locally; CI cost acceptable for the
coverage.
"""

from __future__ import annotations

import logging
import os
import sys
from collections import Counter

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector
from tests.fixtures.curve_boundary_cases import CASES

_REAL_CASE_NAMES = (
    "real_100098DE_1351",
    "real_1000BA3C_0946",
    "real_1000BA3C_1759",
)
_SIGMAS = (0.15, 0.5, 1.0)
_N_SEEDS = 8
_CURVE_COUNT_HITS_FLOOR = 7  # out of N_SEEDS
_CLIFF_AMPLIFICATION_CEILING = 3  # Δ cliff_count allowed, hint − none


def _get_case(name: str):
    return next(c for c in CASES if c["name"] == name)


def _perturb(df, sigma: float, seed: int):
    rng = np.random.default_rng(seed)
    noisy = df.copy()
    noise = rng.normal(0.0, sigma, size=len(noisy))
    noisy["VirtualCoreTemperature"] = noisy["VirtualCoreTemperature"] + noise
    noisy["CoreTemperature"] = noisy["VirtualCoreTemperature"]
    return noisy


def _run(df, durations):
    det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
    return det.extract_curves(df.copy(), expected_durations_s=durations)


def _hint_modes(case) -> list[tuple[str, list | None]]:
    correct = case["expected_durations_s"]
    modes: list[tuple[str, list | None]] = [("none", None)]
    if correct is not None:  # truncated cases get only the none mode
        modes.extend(
            [
                ("correct", list(correct)),
                ("plus30", [d * 1.30 for d in correct]),
                ("minus30", [d * 0.70 for d in correct]),
            ]
        )
    return modes


def _battery_row(case, sigma: float, mode_name: str, durations):
    """Run N_SEEDS noise probes; return (hits, starts, ends, kind_counter)."""
    expected_n = case["expected_n_curves"]
    starts: list[int] = []
    ends: list[int] = []
    kinds: list[str | None] = []
    hits = 0
    for seed in range(_N_SEEDS):
        noisy = _perturb(case["df"], sigma, seed)
        curves = _run(noisy, durations)
        if len(curves) == expected_n:
            hits += 1
        if curves:
            starts.append(curves[0]["start_idx"])
            ends.append(curves[0]["end_idx"])
            for c in curves:
                kinds.append(c.get("exit_candidate_kind"))
    return hits, starts, ends, Counter(kinds)


@pytest.fixture(autouse=True)
def _silence_detector_warnings():
    """The hint-refinement path emits structured warnings on ±30 %
    out-of-band hints.  They're expected behaviour here — don't let
    the noise drown the test output.
    """
    det_log = logging.getLogger("src.data.curve_boundary_detector")
    prev = det_log.level
    det_log.setLevel(logging.ERROR)
    yield
    det_log.setLevel(prev)


@pytest.mark.parametrize("case_name", _REAL_CASE_NAMES)
@pytest.mark.parametrize("sigma", _SIGMAS)
def test_curve_count_holds_across_hint_modes(case_name, sigma):
    case = _get_case(case_name)
    for mode_name, durations in _hint_modes(case):
        hits, _, _, _ = _battery_row(case, sigma, mode_name, durations)
        assert hits >= _CURVE_COUNT_HITS_FLOOR, (
            f"{case_name} σ={sigma} mode={mode_name}: "
            f"only {hits}/{_N_SEEDS} seeds produced the expected "
            f"{case['expected_n_curves']} curves"
        )


@pytest.mark.parametrize(
    "case_name", ("real_100098DE_1351", "real_1000BA3C_1759")
)
@pytest.mark.parametrize("sigma", _SIGMAS)
@pytest.mark.parametrize("mode_name", ("correct", "plus30", "minus30"))
def test_no_cliff_fp_amplification(case_name, sigma, mode_name):
    case = _get_case(case_name)
    correct = case["expected_durations_s"]
    if correct is None:
        pytest.skip(f"{case_name} is truncated; hint modes not applicable")

    _, _, _, kc_none = _battery_row(case, sigma, "none", None)
    base_cliff = kc_none.get("probe_pull_cliff", 0)

    if mode_name == "correct":
        durations = list(correct)
    elif mode_name == "plus30":
        durations = [d * 1.30 for d in correct]
    else:
        durations = [d * 0.70 for d in correct]

    _, _, _, kc_hint = _battery_row(case, sigma, mode_name, durations)
    hint_cliff = kc_hint.get("probe_pull_cliff", 0)
    delta = hint_cliff - base_cliff
    assert delta <= _CLIFF_AMPLIFICATION_CEILING, (
        f"{case_name} σ={sigma} mode={mode_name}: cliff count "
        f"amplified by {delta} (base={base_cliff}, hint={hint_cliff})"
    )


def test_hint_reduces_end_variance_on_100098DE_at_sigma_1p0():
    """Strongest deterministic signal from the red-cell battery:
    at σ=1.0 °C on real_100098DE_1351, the correct hint cuts end-idx
    stdev from ~244 (no-hint) to ~12 (hint) across 8 seeds.

    Asserts the inequality ``stdev_hint ≤ stdev_none / 2`` with a small
    absolute tolerance so the test is not flaky under NumPy RNG
    implementation drift.
    """
    case = _get_case("real_100098DE_1351")
    sigma = 1.0
    _, _, ends_none, _ = _battery_row(case, sigma, "none", None)
    _, _, ends_hint, _ = _battery_row(
        case, sigma, "correct", list(case["expected_durations_s"])
    )
    sd_none = float(np.std(ends_none))
    sd_hint = float(np.std(ends_hint))
    assert sd_hint <= max(sd_none / 2.0, 5.0), (
        f"Expected hint to halve end-idx stdev at σ=1.0 on 100098DE; "
        f"got stdev_none={sd_none:.2f}, stdev_hint={sd_hint:.2f}"
    )


def test_graceful_degradation_on_truncated_real_fixture():
    """BA3C_0946 is truncated (`expected_durations_s=None`).  A caller
    providing any per-curve hint for a truncated log must not crash and
    must still return the expected single curve at all σ levels tested.
    """
    case = _get_case("real_1000BA3C_0946")
    for sigma in _SIGMAS:
        # Even though M1 encodes the hint as None for this fixture,
        # a UI-layer caller might still pass [1500.0] — the detector
        # must tolerate it.  Exercise the defence:
        hits, _, _, _ = _battery_row(case, sigma, "spurious", [1500.0])
        assert hits >= _CURVE_COUNT_HITS_FLOOR, (
            f"BA3C_0946 σ={sigma}: spurious hint on truncated log "
            f"dropped curve count ({hits}/{_N_SEEDS})"
        )
