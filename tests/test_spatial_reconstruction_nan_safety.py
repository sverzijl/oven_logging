"""NaN-safety pin tests for the spatial-reconstruction package (fix/deep-review).

A single dead/NaN sensor terminal must NOT silently disable downstream role
detection. The bugs these tests pin:

* ``classifier`` / ``piecewise`` / ``stefan`` cavity-proxy terminal was
  ``np.max(...)`` over per-sensor terminals → NaN if ANY sensor terminal is
  NaN, which disables every lid / ambient gap test (gap = proxy - T is NaN).
* The piecewise lid-bake span check ``np.max(temps) - np.min(temps)`` and the
  degraded core fallback ``np.argmin`` over a NaN-containing terminal vector
  could pick or be poisoned by the dead sensor.
* ``profile._safe_robust_mean`` returned NaN if the terminal window contained
  a SINGLE NaN sample, propagating NaN into the terminal-temp feature.

The contract: a curve with one dead sensor still classifies (core assigned,
ambient/lid detection still functions, no NaN proxy poisoning).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.classifier import classify  # noqa: E402
from src.data.spatial_reconstruction.profile import (  # noqa: E402
    _safe_robust_mean,
    extract_features,
)


def _ts(n: int, period_s: float = 5.0) -> np.ndarray:
    return np.arange(n, dtype=float) * period_s


def _make_canonical_with_lid(period_s: float = 5.0) -> pd.DataFrame:
    """A canonical bake with a clear in-dough cluster, an air-side rise, and a
    two-sensor lid plateau ~40 C below the cavity proxy.

    T1-T4 dough (~95-100 C), T5 surface kink-and-rise, T6 air toward cavity,
    T7-T8 a lid pair plateauing ~150 C below a ~190 C cavity.
    """
    n_pre, n_rise, n_fall, n_post = 20, 60, 30, 10
    n = n_pre + n_rise + n_fall + n_post
    t_room = 22.0

    def _trace(peak: float, kink: float | None = None, cap: float | None = None):
        pre = np.full(n_pre, t_room)
        if kink is None:
            rise = np.linspace(t_room, peak, n_rise)
        else:
            a = n_rise // 3
            b = n_rise // 3
            c = n_rise - a - b
            rise = np.concatenate(
                [np.linspace(t_room, kink, a), np.full(b, kink), np.linspace(kink, peak, c)]
            )
        fall = np.linspace(peak, t_room + 5.0, n_fall)
        post = np.full(n_post, t_room + 5.0)
        tr = np.concatenate([pre, rise, fall, post])
        if cap is not None:
            tr = np.minimum(tr, cap)
        return tr

    df = pd.DataFrame({"Timestamp": _ts(n, period_s)})
    df["T1"] = _trace(95.0, cap=99.0)
    df["T2"] = _trace(97.0, cap=99.0)
    df["T3"] = _trace(99.0, cap=99.5)
    df["T4"] = _trace(100.0, cap=100.0)
    df["T5"] = _trace(150.0, kink=100.0)  # surface
    df["T6"] = _trace(190.0)              # air toward cavity
    df["T7"] = _trace(150.0)             # lid pair
    df["T8"] = _trace(150.0)             # lid pair
    return df


class TestSafeRobustMean:

    def test_single_nan_in_window_does_not_poison(self):
        # Window with one NaN: the mean must be the finite mean, NOT NaN.
        vals = np.array([98.0, 99.0, np.nan, 100.0, 101.0, 102.0])
        result = _safe_robust_mean(vals)
        assert np.isfinite(result)
        # Finite subset is [98,99,100,101,102]; the 5-95 pct clip keeps the
        # interior, mean ~100.
        assert abs(result - 100.0) < 1.5

    def test_all_nan_returns_nan(self):
        vals = np.array([np.nan, np.nan, np.nan])
        assert np.isnan(_safe_robust_mean(vals))

    def test_empty_returns_nan(self):
        assert np.isnan(_safe_robust_mean(np.array([], dtype=float)))

    def test_small_window_with_nan(self):
        # < 5 finite samples: still drop the NaN, mean the rest.
        vals = np.array([90.0, np.nan, 92.0])
        result = _safe_robust_mean(vals)
        assert np.isfinite(result)
        assert abs(result - 91.0) < 1e-9


class TestClassifyWithDeadSensor:

    def test_dead_sensor_does_not_disable_classification(self):
        """One fully-NaN sensor must NOT NaN-poison the cavity proxy and
        silently disable lid/ambient detection.
        """
        df = _make_canonical_with_lid()
        # Kill T2 entirely (a dead channel mid-probe).
        df["T2"] = np.nan

        result = classify(df, sample_period_ms=5000, model="piecewise")
        # Core must still be assigned (not None).
        assert result.core_assignment is not None
        # The cavity proxy used for gap tests must be finite, not NaN.
        proxy = result.profile_fit.fit_quality.get("cavity_proxy_T")
        assert proxy is not None and np.isfinite(proxy)
        # Lid detection must still fire (the T7/T8 plateau is ~40 C below the
        # ~190 C cavity proxy). A NaN proxy would have made every gap NaN and
        # disabled it.
        assert result.lid_assignment is not None

    def test_dead_sensor_stefan_path(self):
        df = _make_canonical_with_lid()
        df["T2"] = np.nan
        result = classify(df, sample_period_ms=5000, model="stefan")
        assert result.core_assignment is not None
        proxy = result.profile_fit.fit_quality.get("cavity_proxy_T")
        assert proxy is not None and np.isfinite(proxy)

    def test_dead_sensor_terminal_feature_is_nan_only_for_dead(self):
        df = _make_canonical_with_lid()
        df["T2"] = np.nan
        feats = extract_features(df, sample_period_ms=5000)
        assert np.isnan(feats["T2"]["terminal_temp"])
        # Every other sensor's terminal must be finite (not poisoned).
        for s in ("T1", "T3", "T4", "T5", "T6", "T7", "T8"):
            assert np.isfinite(feats[s]["terminal_temp"]), s
