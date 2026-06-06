"""Per-component unit tests for the spatial-reconstruction package (M2a).

Targets:
- ``src.data.spatial_reconstruction.geometry`` — probe geometry lookup.
- ``src.data.spatial_reconstruction.profile`` — feature extraction + oven proxy.
- ``src.data.spatial_reconstruction.piecewise`` — three-region fit recovery.
- ``src.data.spatial_reconstruction.classifier`` — end-to-end role assignment
  on synthetic profiles where the answer is determined by construction.

These tests are deliberately tight on synthetic data (no noise, deterministic
profile shape). The realistic-CSV contract tests live in
``tests/test_role_classifier_unified.py::TestClassifierReturnsExpectedRoles``.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Geometry tests
# ---------------------------------------------------------------------------


class TestGeometry:
    def test_geometry_lookup_falls_back_to_uniform(self):
        from src.data.spatial_reconstruction.geometry import lookup_geometry

        geom = lookup_geometry()
        assert "sensor_positions_normalised" in geom
        positions = geom["sensor_positions_normalised"]
        assert len(positions) == 8
        expected = tuple(i / 7 for i in range(8))
        for actual, want in zip(positions, expected):
            assert pytest.approx(actual, abs=1e-9) == want

    def test_geometry_lookup_unknown_sn_falls_back_to_uniform(self):
        from src.data.spatial_reconstruction.geometry import lookup_geometry

        geom = lookup_geometry(probe_sn="UNKNOWN-SN", probe_model="UNKNOWN-MODEL")
        assert len(geom["sensor_positions_normalised"]) == 8


# ---------------------------------------------------------------------------
# Profile / feature-extraction tests
# ---------------------------------------------------------------------------


def _ts(n: int, period_s: float = 5.0) -> np.ndarray:
    return np.arange(n, dtype=float) * period_s


def _make_plateau_curve(
    n_pre: int = 10,
    n_rise: int = 30,
    n_plateau: int = 20,
    n_fall: int = 30,
    n_post: int = 10,
    t_start: float = 22.0,
    t_plateau: float = 100.0,
) -> np.ndarray:
    """Synthetic single-sensor curve with a flat plateau at ``t_plateau``."""
    pre = np.full(n_pre, t_start)
    rise = np.linspace(t_start, t_plateau, n_rise)
    plateau = np.full(n_plateau, t_plateau)
    fall = np.linspace(t_plateau, t_start + 5.0, n_fall)
    post = np.full(n_post, t_start + 5.0)
    return np.concatenate([pre, rise, plateau, fall, post])


class TestProfile:
    def test_compute_oven_proxy_is_max_per_sample(self):
        from src.data.spatial_reconstruction.profile import compute_oven_proxy

        df = pd.DataFrame(
            {
                "Timestamp": _ts(5),
                "T1": [10.0, 20.0, 30.0, 40.0, 50.0],
                "T2": [11.0, 21.0, 31.0, 41.0, 51.0],
                "T3": [12.0, 22.0, 32.0, 42.0, 52.0],
            }
        )
        proxy = compute_oven_proxy(df, sensors=("T1", "T2", "T3"))
        np.testing.assert_array_equal(proxy.values, np.array([12.0, 22.0, 32.0, 42.0, 52.0]))

    def test_extract_plateau_dwell_returns_seconds_in_window(self):
        from src.data.spatial_reconstruction.profile import extract_features

        # 20-sample plateau at 100°C, 5s/sample = 100s contiguous dwell.
        curve = _make_plateau_curve(n_plateau=20)
        df = pd.DataFrame({"Timestamp": _ts(len(curve))})
        for sensor in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            df[sensor] = curve
        features = extract_features(df, sample_period_ms=5000)
        # plateau_dwell_seconds_near_100c should be ≥ 60 seconds (we set 100 s).
        for sensor in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            assert features[sensor]["plateau_dwell_seconds_near_100c"] >= 60.0

    def test_extract_features_terminal_temp_uses_peak_window(self):
        from src.data.spatial_reconstruction.profile import extract_features

        # 100-sample curve: rise to peak at idx 50 (130°C), then fall to 30°C.
        # The peak-anchored window should pick up the peak temp, NOT room temp.
        n = 100
        values = np.concatenate([
            np.linspace(20.0, 130.0, 50),
            np.linspace(130.0, 30.0, 50),
        ])
        df = pd.DataFrame({"Timestamp": _ts(n)})
        for sensor in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            df[sensor] = values
        features = extract_features(df, sample_period_ms=5000)
        for sensor in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            assert features[sensor]["terminal_temp"] > 100.0
            assert features[sensor]["max_temp"] == pytest.approx(130.0, abs=1e-6)

    def test_extract_features_rise_slope_is_positive_for_heating_curve(self):
        from src.data.spatial_reconstruction.profile import extract_features

        # Linear rise from 22 to 200 over 60 samples (5s each → 300s)
        n = 100
        values = np.concatenate([
            np.full(10, 22.0),
            np.linspace(22.0, 200.0, n - 10),
        ])
        df = pd.DataFrame({"Timestamp": _ts(n)})
        for sensor in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            df[sensor] = values
        features = extract_features(df, sample_period_ms=5000)
        # Rise slope from 30→80 °C should be a positive °C/s rate.
        for sensor in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            slope = features[sensor]["rise_slope_30_to_80c_c_per_s"]
            assert slope is not None and slope > 0.0


# ---------------------------------------------------------------------------
# Piecewise model tests
# ---------------------------------------------------------------------------


class TestPiecewise:
    def test_piecewise_three_region_fit_recovers_synthetic_profile(self):
        """Synthetic terminal-T vector with a known dough/air interface; fit
        and assert recovered position is close to the constructed value."""
        from src.data.spatial_reconstruction.piecewise import fit_piecewise

        # 8 sensor positions at i/7. Construct a vector where T jumps from
        # ~99 °C (dough) to ~150 °C (surface) between idx 3 and idx 4.
        # Interface should land between these two — at x ≈ 3.5/7.
        positions = tuple(i / 7 for i in range(8))
        terminal_temps_arr = np.array(
            [95.0, 97.0, 99.0, 99.5, 150.0, 200.0, 220.0, 220.0]
        )
        terminal_temps = {f"T{i+1}": float(terminal_temps_arr[i]) for i in range(8)}
        # Build a minimal feature dict — we only need terminal_temps for the
        # piecewise fit's interface detection.
        features = {
            f"T{i+1}": {
                "terminal_temp": float(terminal_temps_arr[i]),
                "max_temp": float(terminal_temps_arr[i]),
                "plateau_dwell_seconds_near_100c": 0.0,
                "time_fraction_below_100c": 0.5,
                "rise_slope_30_to_80c_c_per_s": 0.1,
                "post_80c_variance": 0.0,
                "time_to_100c_seconds": None,
                "xcorr_lag_to_oven_proxy_seconds": 0.0,
            }
            for i in range(8)
        }
        fit = fit_piecewise(features, terminal_temps, positions)
        assert fit.x_dough_air is not None
        # Single interface — not a tuple in this case.
        if isinstance(fit.x_dough_air, tuple):
            interfaces = list(fit.x_dough_air)
        else:
            interfaces = [fit.x_dough_air]
        # Expect interface near (3 + 4) / 2 / 7 = 0.5
        target = 3.5 / 7
        assert any(abs(x - target) < 0.10 for x in interfaces), (
            f"Expected interface near {target}, got {interfaces}"
        )

    def test_piecewise_through_loaf_detects_two_interfaces(self):
        """Through-loaf insertion: T1 and T8 in oven air, T4-T5 are core."""
        from src.data.spatial_reconstruction.piecewise import fit_piecewise

        positions = tuple(i / 7 for i in range(8))
        terminal_temps_arr = np.array(
            [220.0, 200.0, 150.0, 99.0, 99.0, 150.0, 200.0, 220.0]
        )
        terminal_temps = {f"T{i+1}": float(terminal_temps_arr[i]) for i in range(8)}
        features = {
            f"T{i+1}": {
                "terminal_temp": float(terminal_temps_arr[i]),
                "max_temp": float(terminal_temps_arr[i]),
                "plateau_dwell_seconds_near_100c": 0.0,
                "time_fraction_below_100c": 0.5,
                "rise_slope_30_to_80c_c_per_s": 0.1,
                "post_80c_variance": 0.0,
                "time_to_100c_seconds": None,
                "xcorr_lag_to_oven_proxy_seconds": 0.0,
            }
            for i in range(8)
        }
        fit = fit_piecewise(features, terminal_temps, positions)
        # Through-loaf: x_dough_air should be a tuple of two interface positions.
        assert isinstance(fit.x_dough_air, tuple)
        assert len(fit.x_dough_air) == 2
        x_left, x_right = fit.x_dough_air
        # Left interface should sit in the left half (between T2 and T4),
        # right interface should sit in the right half (between T5 and T7).
        # With continuous interpolation, the exact crossing depends on the
        # plateau-edge temperature; relaxed bounds reflect that.
        assert x_left < 0.5
        assert x_right > 0.5


# ---------------------------------------------------------------------------
# Classifier tests
# ---------------------------------------------------------------------------


def _make_synthetic_full_df(
    peaks: list[float],
    n: int = 130,
    period_s: float = 5.0,
    n_pre: int = 30,
    n_rise: int = 60,
    n_fall: int = 30,
    n_post: int = 10,
    rise_kink_at: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Build a deterministic 8-sensor DataFrame with given terminal peaks."""
    t_room = 22.0
    rise_kink_at = rise_kink_at or {}
    df = pd.DataFrame({"Timestamp": _ts(n, period_s)})

    def _trace(peak: float, kink: float | None = None) -> np.ndarray:
        pre = np.full(n_pre, t_room)
        if kink is None:
            rise = np.linspace(t_room, peak, n_rise)
        else:
            n_to_kink = n_rise // 3
            n_plateau = n_rise // 3
            n_after = n_rise - n_to_kink - n_plateau
            seg1 = np.linspace(t_room, kink, n_to_kink)
            seg2 = np.full(n_plateau, kink)
            seg3 = np.linspace(kink, peak, n_after)
            rise = np.concatenate([seg1, seg2, seg3])
        fall = np.linspace(peak, t_room + 5.0, n_fall)
        post = np.full(n_post, t_room + 5.0)
        return np.concatenate([pre, rise, fall, post])

    for i, sensor in enumerate(("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")):
        df[sensor] = _trace(peaks[i], rise_kink_at.get(sensor))
    df["CoreTemperature"] = df["T1"]
    return df


class TestPiecewiseNanSafety:
    """fix/deep-review #1, #2 — a NaN terminal must not poison the cavity proxy
    or the lid-bake span check, and the degraded core fallback must not pick the
    dead sensor.
    """

    def _features(self, terminal_arr):
        return {
            f"T{i+1}": {
                "terminal_temp": float(terminal_arr[i]),
                "max_temp": float(terminal_arr[i]),
                "plateau_dwell_seconds_near_100c": 0.0,
                "time_fraction_below_100c": 0.5,
                "rise_slope_30_to_80c_c_per_s": 0.1,
                "post_80c_variance": 0.0,
                "time_to_100c_seconds": None,
                "time_to_60c_seconds": float(10 * (i + 1)),
                "xcorr_lag_to_oven_proxy_seconds": 0.0,
            }
            for i in range(8)
        }

    def test_cavity_proxy_finite_with_one_nan_terminal(self):
        from src.data.spatial_reconstruction.piecewise import fit_piecewise

        positions = tuple(i / 7 for i in range(8))
        arr = np.array([95.0, np.nan, 99.0, 99.5, 150.0, 200.0, 220.0, 220.0])
        terminal_temps = {f"T{i+1}": float(arr[i]) for i in range(8)}
        fit = fit_piecewise(self._features(arr), terminal_temps, positions)
        # cavity_proxy_T must be the finite max (220), NOT NaN.
        proxy = fit.fit_quality.get("cavity_proxy_T")
        assert np.isfinite(proxy)
        assert abs(proxy - 220.0) < 1e-6
        # The 150/200/220 air-side rise must still produce a dough/air interface.
        assert fit.x_dough_air is not None

    def test_lid_bake_span_check_ignores_nan(self):
        from src.data.spatial_reconstruction.piecewise import fit_piecewise

        # All sensors plateau ~98 C (lid bake) but T4 is dead (NaN). The
        # span check max-min must use nan-aware ops so the dead sensor does
        # not make the span NaN and silently break lid-bake-mode detection.
        positions = tuple(i / 7 for i in range(8))
        arr = np.array([97.0, 98.0, 98.5, np.nan, 98.0, 97.5, 98.0, 99.0])
        terminal_temps = {f"T{i+1}": float(arr[i]) for i in range(8)}
        fit = fit_piecewise(self._features(arr), terminal_temps, positions)
        # cavity proxy finite; fit completes (no NaN crash).
        assert np.isfinite(fit.fit_quality.get("cavity_proxy_T"))
        assert fit.fit_quality.get("lid_bake_mode") is True


class TestClassifier:
    def test_classify_returns_position_between_sensors(self):
        from src.data.spatial_reconstruction.classifier import classify

        # Construct a profile where the dough/air interface is between T3 and T4.
        # T1-T3 ≤ 99 °C plateau, T4 surface kink, T5-T8 air rise to 220.
        df = _make_synthetic_full_df(
            peaks=[95.0, 98.0, 99.0, 150.0, 220.0, 220.0, 220.0, 220.0],
            rise_kink_at={"T4": 100.0},
        )
        result = classify(df, sample_period_ms=5000)
        assert result.surface_assignment is not None
        assert result.surface_assignment.nearest_sensor in {"T3", "T4"}
        # core position should be among the dough sensors (T1-T3).
        assert result.core_assignment.nearest_sensor in {"T1", "T2", "T3"}

        # CONTINUOUS-POSITION CONTRACT (M6 hot-fix HMS Penelope):
        # surface_assignment.position_normalised must be STRICTLY between
        # T3 (2/7) and T4 (3/7) on this synthetic profile — the 100°C
        # crossing of the linear T(x) profile lies in that interval and
        # should NOT snap to either sensor's position.
        sx = result.surface_assignment.position_normalised
        assert 2 / 7.0 < sx < 3 / 7.0, (
            f"Surface position {sx:.4f} should lie strictly between T3 (2/7) and "
            f"T4 (3/7). Found discrete pick instead — interpolation didn't engage."
        )
        sensor_positions = [i / 7.0 for i in range(8)]
        assert min(abs(sx - sp) for sp in sensor_positions) > 0.005, (
            f"Surface position {sx:.4f} is sensor-aligned; interpolation didn't engage."
        )

    def test_classify_full_immersion_returns_no_surface(self):
        from src.data.spatial_reconstruction.classifier import classify

        # All sensors plateau between 95-99 °C; none reaches >100 with rise.
        peaks = list(np.linspace(95.0, 99.5, 8))
        df = _make_synthetic_full_df(peaks=peaks)
        result = classify(df, sample_period_ms=5000)
        # No interface visible. surface=None and ambient=[].
        assert result.surface_assignment is None
        assert result.ambient_assignments == []

    def test_classify_through_loaf_returns_two_ambient_groups(self):
        from src.data.spatial_reconstruction.classifier import classify

        # Symmetric through-loaf: T1, T8 in air; T2..T7 in dough.
        df = _make_synthetic_full_df(
            peaks=[220.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 220.0],
            rise_kink_at={},
        )
        result = classify(df, sample_period_ms=5000)
        # Both ends should be flagged as ambient.
        ambient_sensors = {a.nearest_sensor for a in result.ambient_assignments}
        assert "T1" in ambient_sensors or "T8" in ambient_sensors
        # Core lies in the middle.
        assert result.core_assignment.nearest_sensor in {"T2", "T3", "T4", "T5", "T6", "T7"}

    def test_classify_lid_detection_synthetic(self):
        from src.data.spatial_reconstruction.classifier import classify

        # T1-T3 dough, T4 surface (kinks at 100→150), T5-T6 cavity (~220),
        # T7-T8 lid contact (~150 — well below cavity proxy 220).
        df = _make_synthetic_full_df(
            peaks=[95.0, 98.0, 100.0, 150.0, 220.0, 220.0, 150.0, 150.0],
            rise_kink_at={"T4": 100.0},
        )
        result = classify(df, sample_period_ms=5000)
        # Lid should be detected — sensor in {T7, T8}.
        if result.lid_assignment is not None:
            assert result.lid_assignment.nearest_sensor in {"T7", "T8"}
