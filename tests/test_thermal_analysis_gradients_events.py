"""Tests for ThermalAnalyzer robustness on degenerate inputs.

Covers three confirmed bugs:
  * #9  np.gradient crashes on bakes with < 2 samples
  * #21 calculate_heating_rates raises NameError for ``window`` when no
        T1..T8 sensor columns exist (window was only assigned inside the
        sensor loop, so the later core/surface gradient blocks referenced
        an undefined name).
  * #22 identify_process_events crashes (idxmax on all-NA) when core_rate
        is all NaN.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.analysis.thermal_analysis import ThermalAnalyzer  # noqa: E402


def _make_df(core_temps, sample_period_s=5.0, with_sensors=True):
    """Build a minimal analyzer-ready DataFrame.

    ``with_sensors`` toggles whether T1..T8 columns are present, to exercise
    the no-sensor-columns path (#21).
    """
    n = len(core_temps)
    time_min = np.arange(n) * sample_period_s / 60.0
    cols = {
        "Timestamp": pd.Timestamp("2024-01-01") + pd.to_timedelta(time_min, unit="m"),
        "TimeMinutes": time_min,
        "CoreTemperature": np.asarray(core_temps, dtype=float),
        "SurfaceTemperature": np.asarray(core_temps, dtype=float) + 5.0,
    }
    if with_sensors:
        for i, s in enumerate(["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]):
            cols[s] = np.asarray(core_temps, dtype=float) + i
    df = pd.DataFrame(cols)
    return df


# ---------------------------------------------------------------------------
# #9 — <2-sample gradient guard
# ---------------------------------------------------------------------------

def test_calculate_heating_rates_single_sample_does_not_crash():
    """np.gradient needs >=2 points; a single-sample bake must not raise."""
    df = _make_df([60.0])
    analyzer = ThermalAnalyzer(df, {"sample_period_s": 5.0})
    rates = analyzer.calculate_heating_rates()
    assert len(rates) == 1
    # Rate of a single sample is undefined → zero (or NaN), never an exception.
    assert "core_rate" in rates.columns
    val = rates["core_rate"].iloc[0]
    assert val == 0 or np.isnan(val)


def test_calculate_heating_rates_empty_does_not_crash():
    """A zero-length frame must not raise inside np.gradient."""
    df = _make_df([])
    analyzer = ThermalAnalyzer(df, {"sample_period_s": 5.0})
    rates = analyzer.calculate_heating_rates()
    assert len(rates) == 0


# ---------------------------------------------------------------------------
# #21 — no T1..T8 columns must not raise NameError for `window`
# ---------------------------------------------------------------------------

def test_calculate_heating_rates_no_sensor_columns():
    """When no T1..T8 columns exist, the core/surface gradient blocks must
    still find the smoothing ``window`` (NameError regression #21)."""
    df = _make_df([20.0, 40.0, 60.0, 80.0, 93.0], with_sensors=False)
    analyzer = ThermalAnalyzer(df, {"sample_period_s": 5.0})
    rates = analyzer.calculate_heating_rates(smooth=True)
    assert "core_rate" in rates.columns
    assert len(rates) == 5


# ---------------------------------------------------------------------------
# #22 — all-NaN core_rate must not crash idxmax
# ---------------------------------------------------------------------------

def test_identify_process_events_all_nan_core_rate():
    """When core_rate is all NaN, identify_process_events must skip the
    max-heating-rate event rather than crash on idxmax (#22)."""
    # Force an all-NaN core series so the resulting core_rate is all-NaN.
    df = _make_df([10.0, 20.0, 30.0, 40.0, 50.0])
    df["CoreTemperature"] = np.nan
    analyzer = ThermalAnalyzer(df, {"sample_period_s": 5.0})
    # Should not raise.
    events = analyzer.identify_process_events()
    assert isinstance(events, dict)
    # The max-heating-rate event must be skipped (no valid rate to report).
    assert "max_heating_rate" not in events


def test_identify_process_events_single_sample_does_not_crash():
    """A single-sample bake must not crash identify_process_events (#9/#22)."""
    df = _make_df([60.0])
    analyzer = ThermalAnalyzer(df, {"sample_period_s": 5.0})
    events = analyzer.identify_process_events()
    assert isinstance(events, dict)


def test_identify_process_events_normal_still_reports_max_rate():
    """Sanity: a normal multi-sample bake still reports max_heating_rate."""
    df = _make_df([20.0, 40.0, 60.0, 80.0, 93.0, 95.0, 96.0])
    analyzer = ThermalAnalyzer(df, {"sample_period_s": 5.0})
    events = analyzer.identify_process_events()
    assert "max_heating_rate" in events
    assert events["max_heating_rate"]["rate"] is not None
