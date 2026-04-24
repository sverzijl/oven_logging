"""Failing test ladder for curve boundary detection stabilisation.

Golden-master (test 1) pins current-main behaviour so refactoring cannot silently
drift it.  Tests 2-12 define the TARGET behaviour; all must be RED on main and
GREEN after CurveBoundaryDetector is implemented.

Convention: class-based pytest, sys.path injected at module level, no conftest
changes.  API under test: ThermalProfileLoader._extract_all_baking_curves(df).
Invocation: create a bare loader (ThermalProfileLoader()), set loader.metadata={}
then call loader._extract_all_baking_curves(df.copy()).
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader
from src.data.thermodynamic_sensor_classifier import identify_core_sensor_combined_rank
from tests.fixtures.curve_boundary_cases import CASES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loader_with_df(df: pd.DataFrame) -> ThermalProfileLoader:
    """Return a bare loader with metadata and data attributes pre-set."""
    loader = ThermalProfileLoader()
    loader.metadata = {}
    loader.data = df
    return loader


def _run(case_name: str):
    """Run detector on the named CASES entry; return list of curve dicts."""
    case = next(c for c in CASES if c["name"] == case_name)
    loader = _loader_with_df(case["df"])
    return loader._extract_all_baking_curves(case["df"].copy())


def _run_df(df: pd.DataFrame):
    """Run detector on an arbitrary DataFrame."""
    loader = _loader_with_df(df)
    return loader._extract_all_baking_curves(df.copy())


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestCurveBoundaryDetection:
    """Regression and target-behaviour tests for bread entry/exit detection."""

    # Test 1 — Golden master deleted (2026-04-23 refactor).
    # test_ground_truth_real_csvs_tight now serves both roles: it pins the same
    # 3 real CSVs at tighter ±2 tolerance, making the ±5 golden master redundant.

    # ------------------------------------------------------------------
    # Test 2 — Ground-truth (tight tolerance, skip ambiguous)
    # ------------------------------------------------------------------

    def test_ground_truth_real_csvs_tight(self):
        """Ground-truth annotated boundaries within ±2 samples for unambiguous cases.

        Bake-2 of real_1000BA3C_1759 is skipped because it carries ambiguous=True.
        """
        TOLERANCE = 2

        for case in CASES:
            if case["source"] != "real":
                continue
            # 1759 is ambiguous — test bake-1 only before the tolerance/lidded skip.
            if case.get("ambiguous") and case["name"] == "real_1000BA3C_1759":
                curves = _run(case["name"])
                assert len(curves) >= 1, f"{case['name']}: no curves detected"
                c0 = curves[0]
                assert abs(c0["start_idx"] - case["expected_starts"][0]) <= TOLERANCE, (
                    f"{case['name']} bake-1 start: expected {case['expected_starts'][0]}, "
                    f"got {c0['start_idx']}"
                )
                assert abs(c0["end_idx"] - case["expected_ends"][0]) <= TOLERANCE, (
                    f"{case['name']} bake-1 end: expected {case['expected_ends'][0]}, "
                    f"got {c0['end_idx']}"
                )
                continue
            # Skip lidded real cases — they have a different end-detection contract
            # tested by TestLiddedBakeDetection, not by this tight-tolerance loop.
            if case.get("tolerance") is not None:
                continue

            curves = _run(case["name"])
            assert len(curves) == case["expected_n_curves"], (
                f"{case['name']}: expected {case['expected_n_curves']} curves, got {len(curves)}"
            )
            for i, (exp_start, exp_end) in enumerate(
                zip(case["expected_starts"], case["expected_ends"])
            ):
                assert abs(curves[i]["start_idx"] - exp_start) <= TOLERANCE, (
                    f"{case['name']} curve-{i} start: expected {exp_start}, "
                    f"got {curves[i]['start_idx']}"
                )
                assert abs(curves[i]["end_idx"] - exp_end) <= TOLERANCE, (
                    f"{case['name']} curve-{i} end: expected {exp_end}, "
                    f"got {curves[i]['end_idx']}"
                )

    # ------------------------------------------------------------------
    # Test 3 — Noise spike mid-bake (finding 3)
    # ------------------------------------------------------------------

    def test_noise_spike_midbake(self):
        """A single −20 °C spike mid-plateau must NOT end the curve.

        The detector must require confirmation (multiple samples) before
        declaring a curve end, so a single noisy sample is ignored.
        Expected: 1 curve, boundaries match clean-bake boundaries (±5 samples).
        """
        case = next(c for c in CASES if c["name"] == "noise_spike_midbake")
        curves = _run("noise_spike_midbake")

        assert len(curves) == 1, (
            f"Noise spike incorrectly ended the curve: got {len(curves)} curves"
        )
        exp_start = case["expected_starts"][0]
        exp_end = case["expected_ends"][0]
        assert abs(curves[0]["start_idx"] - exp_start) <= 5, (
            f"start: expected ~{exp_start}, got {curves[0]['start_idx']}"
        )
        assert abs(curves[0]["end_idx"] - exp_end) <= 5, (
            f"end: expected ~{exp_end}, got {curves[0]['end_idx']}"
        )

    # ------------------------------------------------------------------
    # Test 4 — Slow cool-down ends at correct index (finding 7)
    # ------------------------------------------------------------------

    def test_slow_cooldown_ends_at_inflection(self):
        """Slow post-peak cooldown (0.5 °C/s) must end at the last index where
        temperature is still within the bake window (≥ 40 °C).

        The log ends with VCT at 45 °C (still above 40); the correct end_idx is
        the last index of the log (79, where VCT=45 °C), not an earlier exit
        caused by a spurious drop-rate threshold triggering mid-cooldown.

        Current main incorrectly exits at idx 76 (VCT≈53 °C) due to the 2 °C/s
        drop-rate threshold being exceeded during the 0.5 °C/s cooldown when
        sample-period scaling is absent.  Target is end_idx within ±2 of 79.
        """
        case = next(c for c in CASES if c["name"] == "slow_cooldown")
        curves = _run("slow_cooldown")

        assert len(curves) == 1, f"Expected 1 curve, got {len(curves)}"

        exp_end = case["expected_ends"][0]  # 79 (last index, still above 40 °C)
        actual_end = curves[0]["end_idx"]

        assert abs(actual_end - exp_end) <= 2, (
            f"Slow-cooldown end: expected ~{exp_end} (last idx ≥ 40 °C), "
            f"got {actual_end}. "
            "Current main exits prematurely because drop-rate threshold is not "
            "normalised to °C/s (addressing finding 7 + finding 4)."
        )

    # ------------------------------------------------------------------
    # Test 5 — Truncated log returns truncated=True flag (finding 7)
    # ------------------------------------------------------------------

    def test_truncated_log_flag(self):
        """Truncated log (ends while still rising at 80 °C) must return curve
        with end_idx == len(df)-1 and a 'truncated': True key in the curve dict.
        """
        case = next(c for c in CASES if c["name"] == "truncated_log")
        df = case["df"]
        curves = _run("truncated_log")

        assert len(curves) == 1, f"Expected 1 curve, got {len(curves)}"

        c0 = curves[0]
        assert c0["end_idx"] == len(df) - 1, (
            f"Expected end_idx={len(df) - 1} (EOF), got {c0['end_idx']}"
        )
        assert c0.get("truncated") is True, (
            f"Expected curve dict to contain truncated=True, got: {c0.get('truncated')!r}"
        )

    # ------------------------------------------------------------------
    # Test 6 — Mid-bake start accepted at index 0 (finding 1)
    # ------------------------------------------------------------------

    def test_midbake_start_returns_index_zero(self):
        """Log beginning at 60 °C must accept the first sample as curve start (idx 0).

        Current main requires a rise from below 40 °C or a PredictionState
        transition, so it silently discards the log.
        """
        case = next(c for c in CASES if c["name"] == "midbake_start")
        curves = _run("midbake_start")

        assert len(curves) == 1, (
            f"Expected 1 curve for mid-bake start, got {len(curves)}"
        )
        assert curves[0]["start_idx"] == 0, (
            f"Expected start_idx=0, got {curves[0]['start_idx']}"
        )

    # ------------------------------------------------------------------
    # Test 7 — Two bakes with no full cooldown between (finding 2)
    # ------------------------------------------------------------------

    def test_two_bakes_no_cool_between(self):
        """Two peaks joined by a dip that stays above 60 °C must produce 2 curves.

        The golden-master behaviour (single run of current main) is captured as
        a reference assertion. The TARGET assertion requires n_curves == 2.
        Because the line-878 change may already affect this case, both assertions
        are present so the test documents intent regardless of current state.
        """
        case = next(c for c in CASES if c["name"] == "two_bakes_no_cool")
        curves = _run("two_bakes_no_cool")

        # Target: detector must split two distinct bakes.
        assert len(curves) == 2, (
            f"Expected 2 curves for two-bake no-cool case, got {len(curves)}"
        )

        bounds = case["df"].attrs["two_bakes_boundaries"]
        TOLERANCE = 10  # larger here because the inter-bake dip is subtle

        assert abs(curves[0]["start_idx"] - bounds["bake1_start"]) <= TOLERANCE, (
            f"bake-1 start: expected ~{bounds['bake1_start']}, got {curves[0]['start_idx']}"
        )
        assert abs(curves[1]["start_idx"] - bounds["bake2_start"]) <= TOLERANCE, (
            f"bake-2 start: expected ~{bounds['bake2_start']}, got {curves[1]['start_idx']}"
        )

    # ------------------------------------------------------------------
    # Test 8 — Start-index convention consistent (finding 5)
    # ------------------------------------------------------------------

    def test_start_index_convention_consistent(self):
        """Rapid-rise-from-cold and sustained-rise paths must agree on convention.

        We run both a cold-start case (starts well below 40 °C) and a mid-bake
        case (starts above 40 °C) and check that both start indices point to a
        sample whose temperature is above the detection threshold (not to a
        pre-rise sample from a lookback offset).

        The detection threshold used as a proxy for 'bake started' is 40 °C
        (the fixture VCT-start convention).
        """
        # Cold-start case: variable_sample_period_1s begins at ambient
        cold_case = next(c for c in CASES if c["name"] == "variable_sample_period_1s")
        cold_curves = _run("variable_sample_period_1s")

        assert len(cold_curves) >= 1, "Cold-start case produced no curves"
        cold_start = cold_curves[0]["start_idx"]
        cold_df = cold_case["df"]

        # Mid-bake case
        mid_curves = _run("midbake_start")
        assert len(mid_curves) >= 1, "Mid-bake case produced no curves"
        mid_start = mid_curves[0]["start_idx"]

        # Both start indices must point to a temperature >= 35 °C.
        # (Using 35 rather than 40 to allow for the convention that the
        # start may be the sample immediately before the first 40 °C crossing.)
        cold_temp_at_start = cold_df["CoreTemperature"].iloc[cold_start]
        assert cold_temp_at_start >= 35, (
            f"Cold-start path: start_idx={cold_start} has temp {cold_temp_at_start:.1f}°C "
            f"(< 35 °C), suggesting a j-5 backdating from a different path"
        )

        mid_df = next(c for c in CASES if c["name"] == "midbake_start")["df"]
        mid_temp_at_start = mid_df["CoreTemperature"].iloc[mid_start]
        assert mid_temp_at_start >= 35, (
            f"Mid-bake path: start_idx={mid_start} has temp {mid_temp_at_start:.1f}°C "
            f"(< 35 °C), inconsistent with cold-start convention"
        )

    # ------------------------------------------------------------------
    # Test 9 — Non-monotonic timestamps raise ValueError (finding 8)
    # ------------------------------------------------------------------

    def test_non_monotonic_timestamps_raises(self):
        """Detector must raise ValueError with a clear message when Timestamp
        is not monotonically increasing.

        Current main silently computes negative rates, which is a latent bug.
        """
        case = next(c for c in CASES if c["name"] == "non_monotonic_timestamps")
        assert case["raises"] is ValueError

        with pytest.raises(ValueError, match=r"(?i)(timestamp|monoton)"):
            _run("non_monotonic_timestamps")

    # ------------------------------------------------------------------
    # Test 10 — Variable sample period consistency (finding 4)
    # ------------------------------------------------------------------

    def test_variable_sample_period_consistency(self):
        """1 s and 10 s sampled variants of the same physical bake must produce
        curve-0 durations (seconds) within ±5 s of each other.

        This fails on main because thresholds are expressed in °C/sample rather
        than °C/s, so the two periods produce drastically different results.
        """
        curves_1s = _run("variable_sample_period_1s")
        curves_10s = _run("variable_sample_period_10s")

        assert len(curves_1s) >= 1, "1 s case: no curves detected"
        assert len(curves_10s) >= 1, "10 s case: no curves detected"

        case_1s = next(c for c in CASES if c["name"] == "variable_sample_period_1s")
        case_10s = next(c for c in CASES if c["name"] == "variable_sample_period_10s")

        # Compute duration in seconds using Timestamp column
        def _duration_s(curves, df):
            c = curves[0]
            return float(
                df["Timestamp"].iloc[c["end_idx"]] - df["Timestamp"].iloc[c["start_idx"]]
            )

        dur_1s = _duration_s(curves_1s, case_1s["df"])
        dur_10s = _duration_s(curves_10s, case_10s["df"])

        assert abs(dur_1s - dur_10s) <= 5.0, (
            f"Duration mismatch: 1s-sampled={dur_1s:.1f}s, 10s-sampled={dur_10s:.1f}s "
            f"(diff={abs(dur_1s - dur_10s):.1f}s, limit=5s). "
            "Rate thresholds must be normalised to °C/s not °C/sample."
        )

    # ------------------------------------------------------------------
    # Test 11 — Detector does not mutate input DataFrame (finding 10)
    # ------------------------------------------------------------------

    def test_detector_does_not_mutate_input_df(self):
        """_extract_all_baking_curves must not add columns to the caller's DataFrame.

        Current main adds temp_change and temp_smooth to the passed-in df.
        """
        case = next(c for c in CASES if c["name"] == "real_100098DE_1351")
        df = case["df"].copy()
        cols_before = df.columns.tolist()

        loader = _loader_with_df(df)
        loader._extract_all_baking_curves(df)  # pass the SAME df, not a copy

        cols_after = df.columns.tolist()
        assert cols_before == cols_after, (
            f"Detector mutated input df columns.\n"
            f"Added: {sorted(set(cols_after) - set(cols_before))}\n"
            f"Removed: {sorted(set(cols_before) - set(cols_after))}"
        )

    # ------------------------------------------------------------------
    # Test 12 — Deprecated _extract_baking_curve wrapper gone (finding 9)
    # ------------------------------------------------------------------

    def test_deprecated_wrapper_gone(self):
        """_extract_baking_curve must not exist on ThermalProfileLoader after
        the DRY refactor.  Its presence is a dead-code DRY violation.

        On current main this test is red because the method still exists.
        After Captain Victory + Kent, it must be absent (or raise AttributeError
        if kept but re-raised intentionally).
        """
        assert not hasattr(ThermalProfileLoader, "_extract_baking_curve"), (
            "ThermalProfileLoader._extract_baking_curve still exists. "
            "This deprecated wrapper must be deleted as part of the DRY refactor."
        )


# ---------------------------------------------------------------------------
# Lidded-bake contract tests (target behaviour — must be RED on branch HEAD)
# ---------------------------------------------------------------------------

class TestLiddedBakeDetection:
    """Target-behaviour tests for lidded-bake end detection via core-peak-plateau.

    All three primary tests (1–3) MUST fail red against branch HEAD because the
    detector currently uses probe-removal or EOF as the end signal instead of
    plateau onset.  Test 4 (guardrail) must pass on HEAD and stay green after
    the fix.
    """

    # ------------------------------------------------------------------
    # Test L1 — Real wonder-white 10k lidded CSV
    # ------------------------------------------------------------------

    def test_wonder_white_lidded_real_csv(self):
        """Real lidded bake must terminate at oven-exit (idx ~340), not EOF (~358).

        Current HEAD returns end_idx=358 with truncated=True because the detector
        falls through to EOF.  Target: end_idx within ±5 of 340, truncated=False.

        MUST be RED on branch HEAD.
        """
        case = next(c for c in CASES if c["name"] == "wonder_white_10k_lidded")
        tolerance = case["tolerance"]
        expected_end = case["expected_ends"][0]  # 340

        curves = _run("wonder_white_10k_lidded")

        assert len(curves) == 1, (
            f"Expected 1 curve, got {len(curves)}"
        )
        actual_end = curves[0]["end_idx"]
        assert abs(actual_end - expected_end) <= tolerance, (
            f"Lidded real CSV end: expected ~{expected_end} (oven-exit), "
            f"got {actual_end}. Current HEAD falls through to EOF (~358) with "
            f"truncated=True — the plateau-onset candidate is not yet implemented."
        )

    # ------------------------------------------------------------------
    # Test L2 — Synthetic classic lidded bake ends at plateau, not probe-removal
    # ------------------------------------------------------------------

    def test_synthetic_lidded_plateau_classic_ends_at_plateau_not_removal(self):
        """Classic lidded bake must end at plateau onset (idx ~300), not probe-removal (~480).

        The fixture has a probe-removal distractor at idx ~480 (>2 °C/s drop).
        Current HEAD returns end_idx=480 because it uses probe-removal as the
        exit signal.  Target: end_idx within ±5 of 300 AND strictly < 475.

        MUST be RED on branch HEAD.
        """
        case = next(c for c in CASES if c["name"] == "lidded_bake_plateau_classic")
        tolerance = case["tolerance"]
        expected_end = case["expected_ends"][0]  # 300

        curves = _run("lidded_bake_plateau_classic")

        assert len(curves) == 1, (
            f"Expected 1 curve, got {len(curves)}"
        )
        actual_end = curves[0]["end_idx"]
        assert actual_end < 475, (
            f"Lidded classic: end_idx={actual_end} is at or past the probe-removal "
            f"distractor at idx ~480. Detector must identify plateau onset (~300) "
            f"not probe-removal as the bake end."
        )
        assert abs(actual_end - expected_end) <= tolerance, (
            f"Lidded classic end: expected ~{expected_end} (plateau onset), "
            f"got {actual_end} (tolerance ±{tolerance})."
        )

    # ------------------------------------------------------------------
    # Test L3 — Synthetic truncated lidded bake ends at plateau, not EOF
    # ------------------------------------------------------------------

    def test_synthetic_lidded_plateau_truncated_ends_at_plateau_not_eof(self):
        """Truncated lidded bake must end at plateau onset (idx ~300), not EOF (359).

        The log ends mid-plateau at idx 359.  Current HEAD returns end_idx=359
        with truncated=True.  Target: end_idx within ±5 of 300, truncated=False
        (plateau-onset candidate confirms — no fallthrough to EOF).

        MUST be RED on branch HEAD.
        """
        case = next(c for c in CASES if c["name"] == "lidded_bake_plateau_truncated")
        tolerance = case["tolerance"]
        expected_end = case["expected_ends"][0]  # 300
        df = case["df"]
        eof_idx = len(df) - 1  # 359

        curves = _run("lidded_bake_plateau_truncated")

        assert len(curves) == 1, (
            f"Expected 1 curve, got {len(curves)}"
        )
        c0 = curves[0]
        actual_end = c0["end_idx"]
        assert abs(actual_end - expected_end) <= tolerance, (
            f"Lidded truncated end: expected ~{expected_end} (plateau onset), "
            f"got {actual_end}. Current HEAD falls through to EOF ({eof_idx}) "
            f"with truncated=True."
        )
        assert c0.get("truncated") is not True, (
            f"Expected truncated=False (plateau-onset candidate confirmed), "
            f"got truncated={c0.get('truncated')!r}. Detector must NOT fall through "
            f"to EOF when the plateau-onset candidate fires."
        )

    # ------------------------------------------------------------------
    # Test L4 — Guardrail: existing non-lidded fixtures unchanged
    # ------------------------------------------------------------------

    def test_existing_unlidded_fixtures_unchanged(self):
        """Guardrail: the plateau-onset candidate must NOT spuriously fire on non-lidded cases.

        Iterates all non-lidded CASES (synthetic + real) with expected_n_curves and
        expected_ends defined.  Each must produce the same number of curves and
        end indices within ±5 samples of ground truth.

        MUST pass on branch HEAD and MUST still pass after Warspite's fix.
        """
        TOLERANCE = 5
        LIDDED_NAMES = {
            "wonder_white_10k_lidded",
            "lidded_bake_plateau_classic",
            "lidded_bake_plateau_truncated",
            "post_wonder_meal_lidded",
            "cliff_probe_pull_with_monotonic_cooldown",
        }
        # Skip: non-monotonic (raises), lidded (own class), ambiguous (uncertain ground
        # truth), and cases whose end detection is a known open issue on HEAD so they
        # cannot serve as stable guardrails for a NEW regression.
        SKIP_END_CHECK_NAMES = {
            "two_bakes_no_cool",               # end detection already off on HEAD (separate ticket)
            "probe_removal_contaminates_cool_rank",  # end lands in probe-removal zone on HEAD; Vanguard fixes
        }
        SKIP_NAMES = {"non_monotonic_timestamps"}

        for case in CASES:
            name = case["name"]
            if name in LIDDED_NAMES or name in SKIP_NAMES:
                continue
            if case.get("raises") is not None:
                continue
            # Skip ambiguous cases — their end annotations are uncertain by design.
            if case.get("ambiguous"):
                continue

            curves = _run(name)

            assert len(curves) == case["expected_n_curves"], (
                f"{name}: expected {case['expected_n_curves']} curves, got {len(curves)}"
            )
            if name in SKIP_END_CHECK_NAMES:
                continue
            for i, exp_end in enumerate(case["expected_ends"]):
                if i >= len(curves):
                    break
                actual_end = curves[i]["end_idx"]
                assert abs(actual_end - exp_end) <= TOLERANCE, (
                    f"{name} curve-{i} end: expected ~{exp_end}, "
                    f"got {actual_end} (tolerance ±{TOLERANCE}). "
                    f"Plateau-onset candidate may be firing spuriously."
                )


# ---------------------------------------------------------------------------
# Core-sensor classifier tests
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_REAL_CSV_PATHS = {
    "real_100098DE_1351": os.path.join(
        _REPO_ROOT, "ProbeData_100098DE_2025-05-30 13_51_07.csv"
    ),
    "real_1000BA3C_0946": os.path.join(
        _REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
    ),
    "real_1000BA3C_1759": os.path.join(
        _REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"
    ),
    "wonder_white_10k_lidded": os.path.join(
        _REPO_ROOT, "wonder white 10k 13.01.2026.csv"
    ),
}


def _load_real_core_sensor(case_name: str) -> str:
    """Load a real CSV via ThermalProfileLoader and return the resolved core sensor for curve 0."""
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=_REAL_CSV_PATHS[case_name])
    return loader.get_core_sensor(curve_index=0)


def _run_synthetic_core_sensor(case_name: str) -> str:
    """Run _extract_all_baking_curves on a synthetic CASES entry and return core sensor for curve 0."""
    case = next(c for c in CASES if c["name"] == case_name)
    loader = _loader_with_df(case["df"])
    loader._extract_all_baking_curves(case["df"].copy())
    return loader.get_core_sensor(curve_index=0)


class TestCoreSensorClassifier:
    """Failing tests for physics-based core-sensor classifier.

    Tests 1-3 are TARGET-BEHAVIOUR: RED on HEAD (firmware returns T1 for all).
    Tests 4-6 are GUARDRAIL: GREEN on HEAD (firmware already correct, classifier must not override).
    """

    # ------------------------------------------------------------------
    # Test C1 — Wonder white lidded: resolved core is T5 or T6 (TARGET, RED on HEAD)
    # ------------------------------------------------------------------

    def test_wonder_white_core_is_t5_or_t6(self):
        """Real lidded bake must resolve core to T5 or T6 via combined-rank analysis.

        HEAD returns T1 (firmware VirtualCoreSensor mode = T1 — clearly wrong for a
        lidded bake where T5/T6 exhibit the slowest heating and best heat retention).
        MUST be RED on HEAD.
        """
        resolved_core = _load_real_core_sensor("wonder_white_10k_lidded")
        assert resolved_core in {"T5", "T6"}, (
            f"wonder_white_10k_lidded: expected core T5 or T6 (combined-rank winner), "
            f"got {resolved_core!r}. HEAD returns T1 (firmware pick) — classifier not yet implemented."
        )

    # ------------------------------------------------------------------
    # Test C2 — Synthetic unambiguous: resolved core is T4 (TARGET, RED on HEAD)
    # ------------------------------------------------------------------

    def test_synthetic_unambiguous_core_is_t4(self):
        """Synthetic case where T4 is unambiguously core (slowest heating AND slowest cooling).

        HEAD returns T1 (firmware VirtualCoreSensor='T1' for the synthetic fixture).
        MUST be RED on HEAD.
        """
        resolved_core = _run_synthetic_core_sensor("core_sensor_unambiguous")
        assert resolved_core == "T4", (
            f"core_sensor_unambiguous: expected core T4 (combined score 2, clear winner), "
            f"got {resolved_core!r}. HEAD returns T1 (firmware pick) — classifier not yet implemented."
        )

    # ------------------------------------------------------------------
    # Test C3 — Synthetic disagreeing metrics: resolved core is T6 (TARGET, RED on HEAD)
    # ------------------------------------------------------------------

    def test_synthetic_disagreeing_metrics_core_is_t6(self):
        """Synthetic case where heat-rank and cool-rank winners differ; combined rank picks T6.

        T5 wins heat rank (slowest to 80 °C), T7 wins cool rank (most heat retained).
        Combined-rank winner is T6 (heat rank 2, cool rank 2 → combined score 4).
        HEAD returns T1 (firmware pick). MUST be RED on HEAD.
        """
        resolved_core = _run_synthetic_core_sensor("core_sensor_disagreeing_metrics")
        assert resolved_core == "T6", (
            f"core_sensor_disagreeing_metrics: expected core T6 (combined score 4, "
            f"beats T5=5 and T7=7), got {resolved_core!r}. "
            f"HEAD returns T1 (firmware pick) — classifier not yet implemented."
        )

    # ------------------------------------------------------------------
    # Test C4 — Guardrail: real_100098DE_1351 core is T4 (GREEN on HEAD)
    # ------------------------------------------------------------------

    def test_real_100098DE_core_is_t4(self):
        """Guardrail: firmware correctly picks T4 for this clean unlidded bake.

        Classifier must not override firmware when firmware is already correct.
        MUST pass on HEAD and MUST still pass after the classifier is implemented.
        """
        resolved_core = _load_real_core_sensor("real_100098DE_1351")
        assert resolved_core == "T4", (
            f"real_100098DE_1351: expected core T4 (firmware mode T4 = correct), "
            f"got {resolved_core!r}. Classifier must not override a correct firmware pick."
        )

    # ------------------------------------------------------------------
    # Test C5 — Guardrail: real_1000BA3C_0946 core is T1 (GREEN on HEAD)
    # ------------------------------------------------------------------

    def test_real_1000BA3C_0946_core_is_t1(self):
        """Guardrail: firmware correctly picks T1 for this clean unlidded bake.

        MUST pass on HEAD and MUST still pass after the classifier is implemented.
        """
        resolved_core = _load_real_core_sensor("real_1000BA3C_0946")
        assert resolved_core == "T1", (
            f"real_1000BA3C_0946: expected core T1 (firmware mode T1 = correct), "
            f"got {resolved_core!r}. Classifier must not override a correct firmware pick."
        )

    # ------------------------------------------------------------------
    # Test C6 — Guardrail: real_1000BA3C_1759 core is T1 (GREEN on HEAD)
    # ------------------------------------------------------------------

    def test_real_1000BA3C_1759_core_is_t1(self):
        """Guardrail: firmware correctly picks T1 for this clean unlidded bake (both curves).

        Tests curve 0 only (bake-1 at idx 13..955, T1 dominates with 817/943 samples).
        MUST pass on HEAD and MUST still pass after the classifier is implemented.
        """
        resolved_core = _load_real_core_sensor("real_1000BA3C_1759")
        assert resolved_core == "T1", (
            f"real_1000BA3C_1759: expected core T1 (firmware mode T1 = correct for bake-1), "
            f"got {resolved_core!r}. Classifier must not override a correct firmware pick."
        )


# ---------------------------------------------------------------------------
# Probe-removal contamination tests
# ---------------------------------------------------------------------------

class TestProbeRemovalContamination:
    """Failing tests for probe-removal contamination detection in the cool-rank window.

    Tests PR1-PR2 are TARGET-BEHAVIOUR: RED on HEAD (contaminated combined-rank
    returns wrong sensor).  Test PR3 is a GUARDRAIL: GREEN on HEAD (real slow
    cooldown must not spuriously trigger contamination detection).  Test PR4 is
    ADDITIONAL: RED on HEAD (diagnostic key not yet wired).
    """

    # ------------------------------------------------------------------
    # Test PR1 — Real post-wonder-meal lidded: resolved core is T5 (TARGET, RED on HEAD)
    # ------------------------------------------------------------------

    def test_post_wonder_meal_lidded_core_is_t5(self):
        """Real lidded bake with probe-removal contamination must resolve core to T5.

        Current HEAD returns T7 (combined-rank contaminated by probe-removal in the
        cool window).  Heat-only fallback correctly identifies T5 (heat rank 1,
        t80=1230 s).  MUST be RED on HEAD.
        """
        resolved_core = _run_synthetic_core_sensor("post_wonder_meal_lidded")
        assert resolved_core == "T5", (
            f"post_wonder_meal_lidded: expected core T5 (heat-only fallback when cool-rank "
            f"contaminated by probe removal at idx ~345), got {resolved_core!r}. "
            f"HEAD returns T7 (combined-rank contaminated) — contamination detection not yet "
            f"implemented."
        )

    # ------------------------------------------------------------------
    # Test PR2 — Synthetic probe removal: heat-only picks T4 (TARGET, RED on HEAD)
    # ------------------------------------------------------------------

    def test_synthetic_probe_removal_forces_heat_only(self):
        """Synthetic probe-removal case must resolve core to T4 via heat-only rank.

        Combined-rank (contaminated) ties T5 and T7 at score 7; heat-only correctly
        picks T4 (heat rank 1, t80≈895 s).  MUST be RED on HEAD.
        """
        resolved_core = _run_synthetic_core_sensor("probe_removal_contaminates_cool_rank")
        assert resolved_core == "T4", (
            f"probe_removal_contaminates_cool_rank: expected core T4 (heat-only winner, "
            f"heat rank 1) after contamination detected, got {resolved_core!r}. "
            f"HEAD returns T5 or T7 (contaminated combined-rank tie) — heat-only fallback "
            f"not yet implemented."
        )

    # ------------------------------------------------------------------
    # Test PR3 — Guardrail: real_1000BA3C_1759 still uses combined rank (GREEN on HEAD)
    # ------------------------------------------------------------------

    def test_real_1000BA3C_1759_still_uses_combined_rank(self):
        """Guardrail: genuine slow cooldown must NOT trigger contamination detection.

        BA3C_1759's max drop rate in the cool window is 0.32 °C/s — far below the
        probe-removal threshold.  Contamination detection must not fire spuriously,
        and the resolved core must remain T1 (firmware mode, correct for this bake).
        MUST pass on HEAD and MUST still pass after contamination fix.
        """
        resolved_core = _load_real_core_sensor("real_1000BA3C_1759")
        assert resolved_core == "T1", (
            f"real_1000BA3C_1759: expected core T1 (firmware correct, combined-rank "
            f"should agree on clean slow cooldown), got {resolved_core!r}. "
            f"Contamination detector may be firing spuriously on a genuine slow cooldown "
            f"(max drop rate 0.32 °C/s, well below probe-removal threshold)."
        )

    # ------------------------------------------------------------------
    # Test PR4 — Diagnostic flag surfaces cool_contamination_detected (ADDITIONAL, RED on HEAD)
    # ------------------------------------------------------------------

    def test_contamination_diagnostic_flag_surfaces(self):
        """identify_core_sensor_combined_rank must return cool_contamination_detected=True.

        Calling the classifier directly on the probe_removal_contaminates_cool_rank
        fixture must produce a diagnostic dict with cool_contamination_detected=True.
        HEAD will raise KeyError or return a dict without this key because the
        diagnostic flag is not yet wired.  MUST be RED on HEAD.
        """
        case = next(c for c in CASES if c["name"] == "probe_removal_contaminates_cool_rank")
        df = case["df"]
        sensor_columns = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
        _best, diag = identify_core_sensor_combined_rank(df, sensor_columns)
        assert diag.get("cool_contamination_detected") is True, (
            f"probe_removal_contaminates_cool_rank: expected diag['cool_contamination_detected'] "
            f"is True, got {diag.get('cool_contamination_detected')!r}. "
            f"Vanguard must wire this diagnostic flag in identify_core_sensor_combined_rank."
        )

    # ------------------------------------------------------------------
    # Test PR5 — Staggered single-sample spikes must NOT trigger contamination (Duncan)
    # ------------------------------------------------------------------

    def test_staggered_single_sample_spikes_do_not_trigger(self):
        """Staggered single-sensor noise spikes must NOT fire contamination detection.

        Construct a synthetic curve where 8 sensors each have a 1-sample spike
        at different indices spread across ~20 samples (no coordinated probe pull).
        With min_k_sensors=1 (Vanguard), back-to-back single-sensor spikes on adjacent
        samples fooled the any-sensor-per-sample rule.  With min_k_sensors=2 (Duncan /
        Audacious), ≥2 sensors must drop simultaneously — staggered individual spikes
        do not meet this bar.

        Added per Audacious red-cell verdict (mission 2026-04-24_015052_25705c7a).
        """
        from src.data._drop_rate_detection import find_confirmed_multi_sensor_drop

        n_total = 400
        period = 5.0
        spike_magnitude = 15.0  # 15 °C / 5 s = 3.0 °C/s, above threshold 2.0
        spike_start_idx = 300
        spike_spread = 20
        sensors = [f"T{i}" for i in range(1, 9)]

        ts = np.arange(n_total) * period
        data = {"Timestamp": ts}
        rng = np.random.default_rng(42)
        for k, s in enumerate(sensors):
            vals = np.zeros(n_total)
            vals[:200] = np.linspace(30.0, 98.0 - k * 0.3, 200)
            vals[200:] = 98.0 - k * 0.3
            vals += rng.normal(0.0, 0.02, n_total)
            # Each sensor spikes at a DIFFERENT index — staggered, not simultaneous
            spike_at = spike_start_idx + (k * (spike_spread // len(sensors)))
            if spike_at < n_total - 2:
                vals[spike_at] -= spike_magnitude
                # Recover: next sample returns to plateau
                vals[spike_at + 1] = vals[spike_at - 1] if spike_at - 1 >= 0 else vals[spike_at + 1]
            data[s] = vals

        df = pd.DataFrame(data)
        df["VirtualCoreTemperature"] = df["T1"]
        df["CoreTemperature"] = df["VirtualCoreTemperature"]

        sensor_temps = {s: df[s].to_numpy(dtype=float) for s in sensors}
        # common_peak_idx is around 200 (where plateau begins)
        probe_removal_idx = find_confirmed_multi_sensor_drop(
            sensor_temps,
            ts,
            first_scan=201,
            rate_c_s=2.0,
            confirm_n=2,
            min_k_sensors=2,
        )
        assert probe_removal_idx is None, (
            f"Staggered single-sample spikes spuriously fired contamination at "
            f"idx={probe_removal_idx}. With min_k_sensors=2, isolated per-sensor "
            f"noise spikes on different samples must NOT fire — only coordinated "
            f"simultaneous drops on ≥2 sensors should count."
        )

    # ------------------------------------------------------------------
    # Test PR6 — real_1000BA3C_0946: winner is T1 regardless of contamination state (Duncan)
    # ------------------------------------------------------------------

    def test_real_1000BA3C_0946_winner_correct_despite_short_log(self):
        """BA3C_0946 is a truncated log where the probe was pulled at the very end.

        At baseline: cool_available=False (cool window extends past EOF) AND
        cool_contamination_detected=True (≥2 sensors drop simultaneously at the
        log tail — the actual probe pull event is captured).  Despite both
        heat-only fallback conditions firing, the winner must remain T1 (firmware
        mode, correct for this bake).

        Key assertion: the winner is T1 in all cases (contamination or not), and
        cool_available is correctly reported as False.  cool_contamination_detected
        reflects physics (probe genuinely pulled) rather than a false positive.

        Added per Audacious red-cell verdict (mission 2026-04-24_015052_25705c7a)
        and Duncan empirical verification that min_k=2 does NOT suppress this fire
        (4 sensors drop simultaneously at the log tail — real physics, not noise).
        """
        loader = ThermalProfileLoader()
        loader.load_csv(file_path=_REAL_CSV_PATHS["real_1000BA3C_0946"])
        resolved_core = loader.get_core_sensor(curve_index=0)
        assert resolved_core == "T1", (
            f"real_1000BA3C_0946: expected core T1, got {resolved_core!r}. "
            f"Heat-only fallback (cool_available=False) must resolve T1 correctly "
            f"regardless of contamination detection state."
        )

        # Also verify the diagnostic directly: cool_available must be False
        df = pd.read_csv(_REAL_CSV_PATHS["real_1000BA3C_0946"], skiprows=10)
        df = df.dropna(subset=["VirtualCoreTemperature"]).reset_index(drop=True)
        sensor_columns = [f"T{i}" for i in range(1, 9)]
        _best, diag = identify_core_sensor_combined_rank(df, sensor_columns)
        assert diag.get("cool_available") is False, (
            f"real_1000BA3C_0946: expected cool_available=False (log truncated before "
            f"cool window), got {diag.get('cool_available')!r}."
        )


# ---------------------------------------------------------------------------
# Cliff probe-pull candidate tests (target behaviour — must be RED on branch HEAD)
# ---------------------------------------------------------------------------

class TestCliffProbePullDetection:
    """Tests for the _candidate_probe_pull_cliff end-detection candidate.

    Tests D1–D2 are TARGET-BEHAVIOUR: RED on HEAD because the cliff candidate
    does not yet exist.  Test D3 is a GUARDRAIL: GREEN on HEAD (wonder white's
    plateau candidate already fires correctly — the cliff candidate must not
    interfere with it).
    """

    # ------------------------------------------------------------------
    # Test D1 — Real post-wonder-meal lidded clips at cliff (TARGET, RED on HEAD)
    # ------------------------------------------------------------------

    def test_post_wonder_meal_lidded_clips_at_cliff(self):
        """Real PWM bake must terminate at idx 344 (just before the 18.7 °C cliff).

        HEAD returns end_idx≈375 with truncated=True because no candidate fires
        before the cool-to-ambient window expires (expanded to 1 hour by
        _probe_cooking_continuous=True).  Target: end_idx within ±5 of 344,
        truncated=False (cliff candidate fires → non-truncated exit).

        MUST be RED on branch HEAD.
        """
        case = next(c for c in CASES if c["name"] == "post_wonder_meal_lidded")
        df = case["df"]
        loader = ThermalProfileLoader()
        loader.metadata = {}
        loader.data = df
        curves = loader._extract_all_baking_curves(df.copy())

        assert len(curves) == 1, (
            f"post_wonder_meal_lidded: expected 1 curve, got {len(curves)}"
        )
        actual_end = curves[0]["end_idx"]
        assert abs(actual_end - 344) <= 5, (
            f"post_wonder_meal_lidded: expected end_idx≈344 (just before 18.7 °C cliff at "
            f"idx 344→345), got {actual_end}. HEAD returns ≈375 with truncated=True — "
            f"_candidate_probe_pull_cliff not yet implemented."
        )
        assert curves[0]["truncated"] is False, (
            f"post_wonder_meal_lidded: expected truncated=False (cliff candidate fires → "
            f"non-truncated exit), got truncated={curves[0].get('truncated')!r}. "
            f"HEAD falls through to EOF with truncated=True."
        )

    # ------------------------------------------------------------------
    # Test D2 — Synthetic cliff clips just before cliff (TARGET, RED on HEAD)
    # ------------------------------------------------------------------

    def test_synthetic_cliff_clips_just_before_cliff(self):
        """Synthetic cliff bake must terminate at idx 299 (just before the 20 °C cliff).

        Fixture: 400 samples, plateau at 96 °C up to idx 300, cliff at idx 300→301
        (20 °C drop in one 5 s sample = 4 °C/s, above the 15 °C/sample threshold),
        then monotonic decline 76→40 °C over idx 301..340, tail ~31 °C from idx 341.

        HEAD returns end_idx≈399 with truncated=True because no existing candidate
        fires on this signature.  Target: end_idx within ±5 of 299, truncated=False.

        MUST be RED on branch HEAD.
        """
        case = next(c for c in CASES if c["name"] == "cliff_probe_pull_with_monotonic_cooldown")
        df = case["df"]
        loader = ThermalProfileLoader()
        loader.metadata = {}
        loader.data = df
        curves = loader._extract_all_baking_curves(df.copy())

        assert len(curves) == 1, (
            f"cliff_probe_pull_with_monotonic_cooldown: expected 1 curve, got {len(curves)}"
        )
        actual_end = curves[0]["end_idx"]
        assert abs(actual_end - 299) <= 5, (
            f"cliff_probe_pull_with_monotonic_cooldown: expected end_idx≈299 (just before "
            f"20 °C cliff at idx 300→301), got {actual_end}. HEAD returns ≈399 with "
            f"truncated=True — _candidate_probe_pull_cliff not yet implemented."
        )
        assert curves[0]["truncated"] is False, (
            f"cliff_probe_pull_with_monotonic_cooldown: expected truncated=False (cliff "
            f"candidate fires → non-truncated exit), got truncated={curves[0].get('truncated')!r}."
        )

    # ------------------------------------------------------------------
    # Test D3 — Guardrail: wonder white still clips at plateau (GREEN on HEAD)
    # ------------------------------------------------------------------

    def test_existing_lidded_wonder_white_still_clips_at_plateau(self):
        """Guardrail: wonder white's plateau candidate must still fire at idx ~340.

        The cliff candidate must not fire earlier on wonder white (which has no
        single-sample >15 °C drop) and must not suppress or delay the plateau
        candidate that already works correctly on HEAD.

        MUST pass on HEAD and MUST still pass after Ark Royal's cliff implementation.
        """
        case = next(c for c in CASES if c["name"] == "wonder_white_10k_lidded")
        df = case["df"]
        loader = ThermalProfileLoader()
        loader.metadata = {}
        loader.data = df
        curves = loader._extract_all_baking_curves(df.copy())

        assert len(curves) == 1, (
            f"wonder_white_10k_lidded: expected 1 curve, got {len(curves)}"
        )
        actual_end = curves[0]["end_idx"]
        assert abs(actual_end - 340) <= 5, (
            f"wonder_white_10k_lidded: expected end_idx≈340 (plateau-onset oven-exit), "
            f"got {actual_end}. Cliff candidate may be firing spuriously on wonder white, "
            f"or the plateau candidate has regressed."
        )


# ---------------------------------------------------------------------------
# Oven-entry start detection tests (max-sensor-based — target behaviour RED on HEAD)
# ---------------------------------------------------------------------------

class TestOvenEntryStartDetection:
    """Target-behaviour tests for max-sensor-based oven-entry start detection.

    The current detector uses the core sensor only (bake_active_c=40 °C threshold
    on VirtualCoreTemperature) to decide when a bake starts.  For bakes 2 and 3 of
    real_1000BA3C_1759, the probe enters the oven well before the core sensor (T1,
    near the end of the probe) crosses 40 °C — the outermost sensors (T8, T7) reach
    40 °C first.  A max-sensor-based start criterion detects oven entry at the first
    sample where ANY sensor >= 40 °C, giving start indices ~660 and ~5888 for bakes
    2 and 3 respectively (vs. the core-only ~775 and ~6032 on HEAD).

    Tests M1–M3 are TARGET-BEHAVIOUR: RED on HEAD.
    """

    # ------------------------------------------------------------------
    # Test M1 — real_1000BA3C_1759 produces three bakes with correct duration
    # ------------------------------------------------------------------

    def test_1759_bake_durations_exceed_20_minutes(self):
        """Bakes 2 and 3 of real_1000BA3C_1759 must each last more than 20 minutes.

        With max-sensor start detection, bakes 2 and 3 start earlier (idx ~660 and
        ~5888 vs. core-only ~775 and ~6032), pushing their durations above 20 min.
        On HEAD: bake 2 ≈ 14.2 min, bake 3 ≈ 12.8 min → RED.

        MUST be RED on HEAD.
        """
        curves = _run("real_1000BA3C_1759")

        assert len(curves) == 3, (
            f"real_1000BA3C_1759: expected 3 curves, got {len(curves)}"
        )
        assert curves[1]["duration"] > 20, (
            f"real_1000BA3C_1759 bake-2: expected duration > 20 min (max-sensor start at "
            f"idx ~660), got {curves[1]['duration']:.1f} min. "
            f"HEAD uses core-only start (~775) giving ~14.2 min — max-sensor detector not "
            f"yet implemented."
        )
        assert curves[2]["duration"] > 20, (
            f"real_1000BA3C_1759 bake-3: expected duration > 20 min (max-sensor start at "
            f"idx ~5888), got {curves[2]['duration']:.1f} min. "
            f"HEAD uses core-only start (~6032) giving ~12.8 min — max-sensor detector not "
            f"yet implemented."
        )

    # ------------------------------------------------------------------
    # Test M2 — Bake 2 starts at oven entry (idx ~660)
    # ------------------------------------------------------------------

    def test_1759_bake_2_start_at_oven_entry(self):
        """Bake 2 of real_1000BA3C_1759 must start at idx 651 ± 8 (oven-entry via max sensor).

        HEAD returns curves[1]['start_idx'] ≈ 775 (core-sensor threshold). The max-sensor
        criterion fires earlier (~651, first sample where any sensor >= 40 °C — T8 jumps
        32.40→40.00 at idx 650→651). Admiral's original 660 estimate came from an
        every-10th-sample survey that missed the transition; the detector's principled
        threshold is the ground truth.

        MUST be RED on HEAD.
        """
        curves = _run("real_1000BA3C_1759")

        assert len(curves) >= 2, (
            f"real_1000BA3C_1759: expected at least 2 curves, got {len(curves)}"
        )
        actual_start = curves[1]["start_idx"]
        assert abs(actual_start - 651) <= 8, (
            f"real_1000BA3C_1759 bake-2 start: expected 651 ± 8, got {actual_start}. "
            f"HEAD returns ~775 (core-only threshold) — max-sensor start not yet implemented."
        )

    # ------------------------------------------------------------------
    # Test M3 — Bake 3 starts at oven entry (idx ~5888)
    # ------------------------------------------------------------------

    def test_1759_bake_3_start_at_oven_entry(self):
        """Bake 3 of real_1000BA3C_1759 must start at idx 5888 ± 8 (oven-entry via max sensor).

        HEAD returns curves[2]['start_idx'] ≈ 6032 (core-sensor threshold). The max-sensor
        criterion fires earlier (~5888, first sample where any sensor >= 40 °C).

        MUST be RED on HEAD.
        """
        curves = _run("real_1000BA3C_1759")

        assert len(curves) >= 3, (
            f"real_1000BA3C_1759: expected at least 3 curves, got {len(curves)}"
        )
        actual_start = curves[2]["start_idx"]
        assert abs(actual_start - 5888) <= 8, (
            f"real_1000BA3C_1759 bake-3 start: expected 5888 ± 8, got {actual_start}. "
            f"HEAD returns ~6032 (core-only threshold) — max-sensor start not yet implemented."
        )
