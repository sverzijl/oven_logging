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
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.classifier import classify  # noqa: E402
from src.data.spatial_reconstruction.piecewise import fit_piecewise  # noqa: E402
from src.data.spatial_reconstruction.profile import (  # noqa: E402
    _safe_robust_mean,
    extract_features,
)
from src.data.spatial_reconstruction.stefan import fit_stefan  # noqa: E402


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


# ---------------------------------------------------------------------------
# RESIDUAL #4b — a dead in-dough sensor (no time_to_60c / time_to_100c AND a
# NaN terminal) yields a NaN heat-up score. The fits then used:
#   * ``np.argmax(scores)`` over the score vector — which on a NaN-containing
#     array picks the NaN index, MIS-PLACING the core on the DEAD sensor; and
#   * ``np.mean(temps[in_dough_idx])`` for residual_sse — which a single NaN
#     terminal poisons to NaN, propagating into comparison.py's cross-fixture
#     SSE mean/report.
# The fix mirrors the existing nanmax / nanargmin guards: use np.nanargmax for
# the core pick and np.nanmean (with an all-NaN guard) for residual_sse.
#
# Scenario: a full-immersion (piecewise) / through-loaf (stefan) profile whose
# in-dough region contains one DEAD sensor (T2 piecewise / T4 stefan, near the
# probe tip) plus a genuinely-slowest LIVE sensor T5 (largest time_to_60c). The
# core must land on the live slowest sensor, not the dead one, and residual_sse
# must stay finite.
# ---------------------------------------------------------------------------


class TestDeadInDoughSensorDoesNotBecomeCore:

    _SENSORS = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
    _POS = tuple(i / 7.0 for i in range(8))

    def _features(self, t60: dict, terminals: dict) -> dict:
        return {
            s: {
                "time_to_60c_seconds": t60[s],
                "time_to_100c_seconds": None,
                "terminal_temp": terminals[s],
            }
            for s in self._SENSORS
        }

    def test_piecewise_full_immersion_dead_tip_sensor(self):
        # Wide-span (> 10 C, so NOT lid-bake) full-immersion profile (all
        # terminals <= plateau-hi, no interface). T2 (x=1/7~0.143) is DEAD;
        # T5 (x=4/7~0.571) is the genuinely slowest-heating live sensor.
        t60 = {"T1": 100.0, "T2": None, "T3": 150.0, "T4": 200.0,
               "T5": 400.0, "T6": 350.0, "T7": 300.0, "T8": 250.0}
        terminals = {"T1": 85.0, "T2": float("nan"), "T3": 90.0, "T4": 93.0,
                     "T5": 99.0, "T6": 98.0, "T7": 97.0, "T8": 95.0}
        fit = fit_piecewise(self._features(t60, terminals), terminals, self._POS)
        in_dough = fit.fit_quality.get("in_dough_indices")
        # The dead T2 is in the dough region (full immersion includes all).
        assert 1 in in_dough, in_dough
        # Core must be placed on the live slowest sensor T5 (x~0.571), NOT the
        # dead T2 (x~0.143) that np.argmax would pick from the NaN score.
        assert fit.x_core is not None and np.isfinite(fit.x_core)
        assert abs(fit.x_core - 4.0 / 7.0) < 0.05, fit.x_core
        # residual_sse must be finite (np.nanmean, not np.mean, over a region
        # that contains the dead sensor's NaN terminal).
        sse = fit.fit_quality.get("residual_sse")
        assert sse is not None and np.isfinite(sse), sse

    def test_stefan_through_loaf_dead_dough_sensor(self):
        # Through-loaf: T1/T8 air (~130), dough band T3..T6, two 100 C crossings.
        # T4 (x=3/7~0.429) is DEAD; T5 (x=4/7~0.571) is the slowest live sensor.
        terminals = {"T1": 130.0, "T2": 105.0, "T3": 95.0, "T4": float("nan"),
                     "T5": 92.0, "T6": 96.0, "T7": 108.0, "T8": 130.0}
        t60 = {"T1": 50.0, "T2": 80.0, "T3": 200.0, "T4": None,
               "T5": 500.0, "T6": 300.0, "T7": 90.0, "T8": 50.0}
        fit = fit_stefan(self._features(t60, terminals), terminals, self._POS)
        in_dough = fit.fit_quality.get("in_dough_indices")
        assert 3 in in_dough, in_dough  # the dead T4 sits in the dough band
        # Core on the live slowest T5 (x~0.571), not the dead T4 (x~0.429).
        assert fit.x_core is not None and np.isfinite(fit.x_core)
        assert abs(fit.x_core - 4.0 / 7.0) < 0.05, fit.x_core
        sse = fit.fit_quality.get("residual_sse")
        assert sse is not None and np.isfinite(sse), sse

    def test_classify_end_to_end_dead_sensor_core_is_live_slowest(self):
        # End-to-end through classify(): build a real DataFrame whose in-dough
        # region has a dead sensor; the reported core must be a live sensor and
        # the fit residual_sse finite.
        def _ts(n: int, p: float = 5.0):
            return np.arange(n, dtype=float) * p

        n_pre, n_rise, n_fall, n_post = 20, 60, 30, 10
        n = n_pre + n_rise + n_fall + n_post
        t_room = 22.0

        def trace(peak: float, rise_samples: int):
            pre = np.full(n_pre, t_room)
            rise = np.linspace(t_room, peak, rise_samples)
            plateau = np.full(max(0, n_rise - rise_samples), peak)
            fall = np.linspace(peak, t_room + 5.0, n_fall)
            post = np.full(n_post, t_room + 5.0)
            return np.concatenate([pre, rise, plateau, fall, post])[:n]

        df = pd.DataFrame({"Timestamp": _ts(n)})
        # Full-immersion plateau band, wide span. T5 slowest rise = true core.
        df["T1"] = trace(85.0, 30)
        df["T2"] = trace(90.0, 30)
        df["T3"] = trace(92.0, 33)
        df["T4"] = trace(94.0, 38)
        df["T5"] = trace(99.0, 58)  # slowest -> true core
        df["T6"] = trace(98.0, 52)
        df["T7"] = trace(96.0, 46)
        df["T8"] = trace(95.0, 42)
        df["T2"] = np.nan  # dead in-dough sensor near the tip

        res = classify(df, sample_period_ms=5000, model="piecewise")
        assert res.core_assignment is not None
        # The core sensor must NOT be the dead T2.
        assert res.core_assignment.nearest_sensor != "T2"
        sse = res.profile_fit.fit_quality.get("residual_sse")
        assert sse is not None and np.isfinite(sse), sse


# ---------------------------------------------------------------------------
# RESIDUAL #3b — ``profile._xcorr_lag_seconds`` emitted "Degrees of freedom
# <= 0 for slice" RuntimeWarnings (regression from the np.std -> np.nanstd
# switch) when a shifted segment is ENTIRELY NaN: np.nanstd over an all-NaN
# slice both warns and returns NaN. Results were still correct (0.0); the fix
# short-circuits when a segment has < 2 finite samples BEFORE calling nanstd,
# so the loop never feeds an all-NaN slice to np.nanstd.
# ---------------------------------------------------------------------------


class TestXcorrNoRuntimeWarning:

    def _bake_df(self, n: int = 120) -> pd.DataFrame:
        t_room = 22.0
        df = pd.DataFrame({"Timestamp": _ts(n)})

        def trace(peak: float) -> np.ndarray:
            return np.concatenate(
                [
                    np.full(20, t_room),
                    np.linspace(t_room, peak, 40),
                    np.linspace(peak, t_room + 5.0, 40),
                    np.full(20, t_room + 5.0),
                ]
            )[:n]

        rng = np.random.default_rng(7)
        for s in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            df[s] = trace(95.0 + rng.random() * 60.0)
        return df

    def test_xcorr_segment_all_nan_emits_no_runtime_warning(self):
        # A sensor that goes all-NaN early (dies at idx 35) leaves the finite
        # tail within max_lag of the start, so a shifted segment becomes
        # entirely NaN — the case that triggered the RuntimeWarning.
        df = self._bake_df()
        df.loc[35:, "T3"] = np.nan
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            feats = extract_features(df, sample_period_ms=5000)
        runtime = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        assert runtime == [], [str(w.message) for w in runtime]
        # The lag feature is still well-defined for the live sensors.
        for s in ("T1", "T2", "T4"):
            assert feats[s]["xcorr_lag_to_oven_proxy_seconds"] is not None

    def test_xcorr_back_half_nan_no_runtime_warning(self):
        # The skeptic's framing: a sensor goes all-NaN for the back half.
        df = self._bake_df()
        df.loc[len(df) // 2:, "T5"] = np.nan
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            extract_features(df, sample_period_ms=5000)
        runtime = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        assert runtime == [], [str(w.message) for w in runtime]

    def test_xcorr_direct_all_nan_segment_no_warning(self):
        # Direct unit on _xcorr_lag_seconds: a sensor finite only in its first
        # few samples forces an all-NaN shifted segment for lag past that point.
        from src.data.spatial_reconstruction.profile import _xcorr_lag_seconds

        n = 120
        sensor = np.full(n, np.nan)
        sensor[:12] = np.linspace(22.0, 50.0, 12)
        proxy = np.linspace(22.0, 200.0, n)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            r = _xcorr_lag_seconds(sensor, proxy, 5.0)
        runtime = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        assert runtime == [], [str(w.message) for w in runtime]
        # Result unchanged: still a finite lag (the correct degenerate value).
        assert np.isfinite(r)
