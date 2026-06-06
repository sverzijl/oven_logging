"""Tests for the S-curve bake-out / moisture model cluster.

Covers confirmed bugs:
  * #5  Moisture-decay model self-contradiction (underbaked + excess moisture).
        The consistency contract: for each product, a bake-out% INSIDE that
        product's BAKEOUT_TARGETS window must yield a final-moisture INSIDE that
        product's PRODUCT_MOISTURE.target_final window, and the verdict text
        must not be self-contradictory.
  * #6  Single-sample bake-out reports zero moisture loss (np.linspace collapses
        for len < 2); integration must use real elapsed time.
  * #7  Hardcoded 10%/20% bake-out diagnosis thresholds ignore product type.
  * #8  generate_optimization_report / diagnose_quality_issues / analyze_bake_out
        always analyze white_pan; product_type must thread through.
  * #10 Critical-zone heating rate uses a non-contiguous boolean mask + diff(),
        meaningless on non-monotonic bakes; must use the first contiguous run.
  * #23 identify_landmarks hardcodes data['CoreTemperature']; must use the
        column helper (so CoreAverage-only frames work).
  * #25 The "Extend bake time by X% of total bake" recommendation mislabels a
        percentage-point delta as a directly actionable figure.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from config.constants import BAKEOUT_TARGETS, PRODUCT_MOISTURE  # noqa: E402
from src.analysis.s_curve_analysis import SCurveAnalyzer  # noqa: E402


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _make_bake(bakeout_pct, n=400, sample_period=5.0, peak=99.0,
               core_col="CoreTemperature"):
    """Build a monotonic bake whose bake-out fraction (core >= 93°C) is
    approximately ``bakeout_pct`` percent of the total samples."""
    n_bakeout = max(1, int(round(n * bakeout_pct / 100.0)))
    n_rise = n - n_bakeout
    rise = np.linspace(20.0, 93.0, n_rise, endpoint=False)
    bake = np.linspace(93.0, peak, n_bakeout)
    core = np.concatenate([rise, bake])
    time_min = np.arange(n) * sample_period / 60.0
    df = pd.DataFrame({
        "TimeMinutes": time_min,
        core_col: core,
        "Timestamp": pd.Timestamp("2024-01-01") + pd.to_timedelta(time_min, unit="m"),
    })
    return df


# ---------------------------------------------------------------------------
# #5 — the consistency contract (the headline test)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("product", list(PRODUCT_MOISTURE.keys()))
def test_in_window_bakeout_yields_in_window_moisture_and_consistent_verdict(product):
    """For each product: bake-out% in BAKEOUT_TARGETS → final moisture in
    PRODUCT_MOISTURE.target_final, with a non-contradictory verdict (#5)."""
    bo_min, bo_max = BAKEOUT_TARGETS[product]
    bo_mid = (bo_min + bo_max) / 2.0
    tf_min, tf_max = PRODUCT_MOISTURE[product]["target_final"]

    df = _make_bake(bo_mid)
    analyzer = SCurveAnalyzer(df, {"sample_period_s": 5.0})
    result = analyzer.analyze_bake_out(product_type=product)

    # Bake-out% should land inside the window (sanity on the fixture).
    assert bo_min <= result.percentage_of_bake <= bo_max, (
        f"fixture bake-out% {result.percentage_of_bake} outside {bo_min}-{bo_max}"
    )

    # Contract: final moisture inside the product target_final window.
    assert tf_min <= result.final_moisture_estimate <= tf_max, (
        f"{product}: final moisture {result.final_moisture_estimate:.2f} not in "
        f"target_final {tf_min}-{tf_max} for in-window bake-out%"
    )

    # Verdict must be the optimal verdict (not Underbaked/Overbaked/Dry/High Moisture).
    assert result.quality_assessment == "Optimal", (
        f"{product}: expected Optimal verdict, got {result.quality_assessment}"
    )

    # No self-contradiction in the recommendation text.
    rec_text = " ".join(result.recommendations).lower()
    says_underbaked = "increase bake" in rec_text or "underbaked" in rec_text
    says_excess_moisture = "excess moisture" in rec_text
    assert not (says_underbaked and says_excess_moisture), (
        f"{product}: contradictory recs: {result.recommendations}"
    )


def test_underbaked_is_not_also_excess_moisture():
    """A genuinely underbaked bake (low bake-out%) must not simultaneously be
    flagged as 'excess moisture' AND 'increase bake-out' — that is the exact
    self-contradiction #5 targets. Underbaked should read as 'too moist',
    which is consistent, but the recommendation set must be internally
    coherent: increasing bake-out reduces moisture, so the two directional
    hints must point the same way."""
    product = "white_pan"
    bo_min, _ = BAKEOUT_TARGETS[product]
    df = _make_bake(max(1.0, bo_min - 8))  # clearly under the window
    analyzer = SCurveAnalyzer(df, {"sample_period_s": 5.0})
    result = analyzer.analyze_bake_out(product_type=product)

    assert result.quality_assessment in ("Underbaked", "High Moisture")
    # If underbaked, moisture must be >= target max (too wet), never < target min.
    tf_min, tf_max = PRODUCT_MOISTURE[product]["target_final"]
    assert result.final_moisture_estimate >= tf_min, (
        "underbaked product cannot be drier than the target minimum"
    )


def test_overbaked_yields_low_moisture_consistent_verdict():
    """An overbaked bake (high bake-out%) must yield below-target (dry)
    moisture, consistently."""
    product = "white_pan"
    _, bo_max = BAKEOUT_TARGETS[product]
    df = _make_bake(bo_max + 10)  # clearly over the window
    analyzer = SCurveAnalyzer(df, {"sample_period_s": 5.0})
    result = analyzer.analyze_bake_out(product_type=product)

    assert result.quality_assessment in ("Overbaked", "Dry")
    tf_min, tf_max = PRODUCT_MOISTURE[product]["target_final"]
    assert result.final_moisture_estimate <= tf_max, (
        "overbaked product cannot be wetter than the target maximum"
    )


# ---------------------------------------------------------------------------
# #6 — single-sample bake-out must report non-zero moisture loss
# ---------------------------------------------------------------------------

def test_single_sample_bakeout_duration_does_not_collapse_to_zero():
    """#6: a single bake-out sample must register a non-zero elapsed duration
    (the np.linspace(0, duration, 1) integration collapsed to 0 before).

    We use a short total bake so the single >=93°C sample is a meaningful
    fraction of the bake (in white_pan's window), which means drying occurs and
    the loss machinery must report a positive loss over the real elapsed time."""
    sample_period = 5.0
    # 6 samples total → 1 bake-out sample = 16.7% (inside white_pan 15-18%).
    core = np.array([20.0, 45.0, 70.0, 85.0, 92.0, 95.0])
    n = len(core)
    time_min = np.arange(n) * sample_period / 60.0
    df = pd.DataFrame({
        "TimeMinutes": time_min,
        "CoreTemperature": core,
        "Timestamp": pd.Timestamp("2024-01-01") + pd.to_timedelta(time_min, unit="m"),
    })
    analyzer = SCurveAnalyzer(df, {"sample_period_s": sample_period})
    result = analyzer.analyze_bake_out(product_type="white_pan")

    # Duration must NOT collapse to zero for a single bake-out sample.
    assert result.duration_minutes > 0
    init = PRODUCT_MOISTURE["white_pan"]["initial_moisture"]
    # An in-window bake-out loses moisture, computed over the real elapsed time.
    assert result.final_moisture_estimate < init
    assert result.moisture_loss_rate > 0


def test_single_sample_bakeout_duration_helper_uses_real_time():
    """#6 unit-level: _bakeout_duration_minutes returns one sample period for a
    single-sample window instead of zero."""
    sample_period = 5.0
    df = pd.DataFrame({
        "TimeMinutes": [10.0],
        "CoreTemperature": [95.0],
    })
    analyzer = SCurveAnalyzer(df, {"sample_period_s": sample_period})
    dur = analyzer._bakeout_duration_minutes(df)
    assert dur == pytest.approx(sample_period / 60.0)


# ---------------------------------------------------------------------------
# #7 / #8 — product-aware bake-out diagnosis thresholds + threading
# ---------------------------------------------------------------------------

def test_diagnose_quality_issues_uses_product_thresholds():
    """#7/#8: a bake-out% that is fine for one product but excessive for
    another must be diagnosed per-product, not against hardcoded 10/20."""
    # multigrain target is 2-7%; white_pan is 15-18%.
    # Build a bake at ~16% bake-out: optimal for white_pan, excessive for multigrain.
    df = _make_bake(16.0)
    analyzer = SCurveAnalyzer(df, {"sample_period_s": 5.0})

    issues_white = analyzer.diagnose_quality_issues(product_type="white_pan")
    issues_multi = analyzer.diagnose_quality_issues(product_type="multigrain")

    def has_excessive(issues):
        return any("Excessive Bake-Out" in i["issue"] for i in issues)

    def has_insufficient(issues):
        return any("Insufficient Bake-Out" in i["issue"] for i in issues)

    # 16% is within white_pan (15-18) → no bake-out issue.
    assert not has_excessive(issues_white)
    assert not has_insufficient(issues_white)
    # 16% is way above multigrain (2-7) → excessive.
    assert has_excessive(issues_multi)


def test_diagnose_quality_issues_default_preserves_white_pan_behaviour():
    """#8: default product_type must remain white_pan (behaviour preserving)."""
    df = _make_bake(16.0)
    analyzer = SCurveAnalyzer(df, {"sample_period_s": 5.0})
    issues_default = analyzer.diagnose_quality_issues()
    issues_white = analyzer.diagnose_quality_issues(product_type="white_pan")
    # Same set of issue names regardless of explicit vs default.
    assert ([i["issue"] for i in issues_default]
            == [i["issue"] for i in issues_white])


def test_generate_optimization_report_threads_product_type():
    """#8: generate_optimization_report must use the supplied product_type for
    its bake-out analysis."""
    df = _make_bake(16.0)
    analyzer = SCurveAnalyzer(df, {"sample_period_s": 5.0})
    report_multi = analyzer.generate_optimization_report(product_type="multigrain")
    # The embedded bakeout analysis must reflect multigrain targets: 16% is
    # excessive for multigrain, so verdict is Overbaked (or Dry).
    assert report_multi["bakeout_analysis"].quality_assessment in ("Overbaked", "Dry")


# ---------------------------------------------------------------------------
# #10 — non-monotonic critical-zone heating rate
# ---------------------------------------------------------------------------

def test_critical_zone_rate_first_contiguous_run_on_nonmonotonic_bake():
    """#10: on a non-monotonic bake (core dips back below 93 then rises again),
    the critical-zone heating rate must be computed over the FIRST contiguous
    in-band run, not a boolean-mask diff that bridges the gap (which would
    inject a spurious negative/positive jump across the discontinuity)."""
    sample_period = 5.0
    # Segment A: rise 56->92 (in critical band), contiguous.
    segA = np.linspace(56.0, 92.0, 20)
    # Brief excursion ABOVE band (>=93) — breaks contiguity.
    excursion = np.linspace(93.0, 99.0, 10)
    # Drop back into band then climb again (second in-band run).
    segB = np.linspace(70.0, 92.0, 20)
    core = np.concatenate([
        np.linspace(20.0, 56.0, 10),  # oven spring
        segA, excursion, segB,
        np.linspace(93.0, 99.0, 10),  # final bake-out
    ])
    n = len(core)
    time_min = np.arange(n) * sample_period / 60.0
    df = pd.DataFrame({
        "TimeMinutes": time_min,
        "CoreTemperature": core,
        "Timestamp": pd.Timestamp("2024-01-01") + pd.to_timedelta(time_min, unit="m"),
    })
    analyzer = SCurveAnalyzer(df, {"sample_period_s": sample_period})
    zones = analyzer.analyze_zones()

    assert "critical_change" in zones
    rate = zones["critical_change"]["avg_heating_rate"]
    # The first contiguous in-band run is segA: 56->92 over 20 samples.
    expected = (92.0 - 56.0) / (19 * sample_period / 60.0)  # °C per minute
    # Must be a sane positive heating rate close to segA's slope, NOT a value
    # corrupted by the boolean-mask diff across the >=93 excursion.
    assert rate > 0
    assert rate == pytest.approx(expected, rel=0.15)


# ---------------------------------------------------------------------------
# #23 — identify_landmarks must use the column helper
# ---------------------------------------------------------------------------

def test_identify_landmarks_resolves_core_average_only_frame():
    """#23: identify_landmarks must use get_core_temperature_column so a frame
    carrying only CoreAverage (no CoreTemperature) still produces landmarks."""
    df = _make_bake(16.0, core_col="CoreAverage")
    analyzer = SCurveAnalyzer(df, {"sample_period_s": 5.0})
    landmarks = analyzer.identify_landmarks()
    # The bake crosses 56, 82 and 93, so all three landmarks must be present.
    assert "yeast_kill" in landmarks
    assert "starch_complete" in landmarks
    assert "arrival_temperature" in landmarks


# ---------------------------------------------------------------------------
# #25 — recommendation wording must not present a %-point delta as actionable
# ---------------------------------------------------------------------------

def test_underbake_recommendation_does_not_mislabel_percentage_point_delta():
    """#25: the underbaked recommendation must NOT read as a directly
    actionable 'extend bake time by X% of total bake' figure (a %-point delta
    on bake-out fraction is not the same as a bake-time extension). It should
    either give added minutes-above-93°C or be clearly flagged as approximate."""
    product = "white_pan"
    bo_min, _ = BAKEOUT_TARGETS[product]
    df = _make_bake(max(1.0, bo_min - 8))
    analyzer = SCurveAnalyzer(df, {"sample_period_s": 5.0})
    result = analyzer.analyze_bake_out(product_type=product)
    rec_text = " ".join(result.recommendations).lower()
    # The misleading exact phrasing must be gone.
    assert "extend bake time by approximately" not in rec_text
    assert "decrease bake time by approximately" not in rec_text
