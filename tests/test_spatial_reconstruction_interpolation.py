"""Continuous-position interpolation tests (M6 hot-fix HMS Penelope).

These tests exercise the architectural promise of the spatial classifier:
that ``position_normalised`` is a continuous off-sensor position (when the
underlying physics does not snap to a sensor) and that
``temperature_series`` is a TRUE per-timestep spatial interpolation, not a
copy of the nearest sensor's series.

Why a separate test file? The contract being verified here cuts across
the piecewise fit, the Stefan fit, the classifier, and the new
``interpolate_temperature_series_at`` helper in ``profile.py``. A single
focused file makes the substantive win observable.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helper: parabolic interpolation (white-box test against the implementation
# in piecewise._parabolic_vertex).
# ---------------------------------------------------------------------------


class TestParabolicInterpolation:
    def test_parabolic_interpolation_recovers_off_sensor_minimum(self):
        """Synthetic 3-point parabola whose vertex is at x=0.42 (between T3 at
        3/7 and T4 at 4/7); the helper recovers x≈0.42 within 0.005."""
        from src.data.spatial_reconstruction.piecewise import _parabolic_vertex

        # Sensor positions T1..T8 at i/7. We construct a parabola y(x) =
        # -100*(x - 0.42)**2 + 50 sampled at T3, T4, T5 (positions 3/7,
        # 4/7, 5/7). The vertex is at x = 0.42.
        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        x_vertex = 0.42
        ys = -100.0 * (positions - x_vertex) ** 2 + 50.0
        # T4 is the argmax (closest sensor to 0.42).
        anchor = int(np.argmax(ys))
        recovered = _parabolic_vertex(positions, ys, anchor)
        assert abs(recovered - x_vertex) < 0.005, (
            f"Expected vertex near {x_vertex}, got {recovered:.4f}"
        )

    def test_parabolic_interpolation_boundary_anchor_returns_sensor_position(self):
        """Anchor at index 0 cannot form a 3-point parabola → return sensor pos."""
        from src.data.spatial_reconstruction.piecewise import _parabolic_vertex

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        ys = np.linspace(50.0, 10.0, 8)  # max at idx 0
        recovered = _parabolic_vertex(positions, ys, 0)
        assert recovered == pytest.approx(positions[0])

    def test_parabolic_interpolation_collinear_returns_sensor_position(self):
        """Three collinear points → degenerate parabola → return middle pos."""
        from src.data.spatial_reconstruction.piecewise import _parabolic_vertex

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        ys = np.linspace(10.0, 50.0, 8)  # strictly linear
        recovered = _parabolic_vertex(positions, ys, 4)
        # Collinear → denominator ≈ 0 → fall back to anchor's position.
        assert recovered == pytest.approx(positions[4])


# ---------------------------------------------------------------------------
# interpolate_temperature_series_at
# ---------------------------------------------------------------------------


class TestInterpolateTemperatureSeriesAt:
    def test_at_sensor_position_returns_sensor_series(self):
        """Degenerate case: x_target lands exactly on a sensor → that sensor's
        series is returned (within numerical noise)."""
        from src.data.spatial_reconstruction.profile import (
            interpolate_temperature_series_at,
        )

        positions = tuple(i / 7.0 for i in range(8))
        df = pd.DataFrame({f"T{i+1}": np.arange(10) * (i + 1) for i in range(8)})
        result = interpolate_temperature_series_at(df, positions, 3 / 7.0)
        np.testing.assert_array_almost_equal(result.to_numpy(), df["T4"].to_numpy())

    def test_between_two_sensors_returns_linear_blend(self):
        """x_target halfway between sensor index 3 (T4, position 3/7) and
        index 4 (T5, position 4/7) → 50% T4 + 50% T5 = 45 everywhere."""
        from src.data.spatial_reconstruction.profile import (
            interpolate_temperature_series_at,
        )

        positions = tuple(i / 7.0 for i in range(8))
        df = pd.DataFrame(
            {
                f"T{i+1}": np.full(5, float(i + 1) * 10.0)
                for i in range(8)
            }
        )
        # Halfway between idx 3 (T4=40) and idx 4 (T5=50): expect 45.0.
        x_mid = (3 / 7.0 + 4 / 7.0) / 2.0
        result = interpolate_temperature_series_at(df, positions, x_mid)
        np.testing.assert_array_almost_equal(result.to_numpy(), np.full(5, 45.0))

    def test_below_first_sensor_clamps_to_first(self):
        from src.data.spatial_reconstruction.profile import (
            interpolate_temperature_series_at,
        )

        positions = tuple(i / 7.0 for i in range(8))
        df = pd.DataFrame({f"T{i+1}": np.arange(5) for i in range(8)})
        result = interpolate_temperature_series_at(df, positions, -0.1)
        np.testing.assert_array_almost_equal(result.to_numpy(), df["T1"].to_numpy())

    def test_above_last_sensor_clamps_to_last(self):
        from src.data.spatial_reconstruction.profile import (
            interpolate_temperature_series_at,
        )

        positions = tuple(i / 7.0 for i in range(8))
        df = pd.DataFrame({f"T{i+1}": np.arange(5) * (i + 1) for i in range(8)})
        result = interpolate_temperature_series_at(df, positions, 2.0)
        np.testing.assert_array_almost_equal(result.to_numpy(), df["T8"].to_numpy())


# ---------------------------------------------------------------------------
# Crossing-position interpolation (surface / Stefan front).
# ---------------------------------------------------------------------------


class TestSurfaceCrossingInterpolation:
    def test_surface_position_lies_between_largest_jump(self):
        """Synthetic where the largest adjacent terminal jump is between T4
        (idx 3, 99.5°C) and T5 (idx 4, 180°C). The 100°C crossing of the
        piecewise-linear T(x) profile lies strictly in (3/7, 4/7) — and
        importantly is OFF-SENSOR (not at 3/7 or 4/7)."""
        from src.data.spatial_reconstruction.piecewise import _crossing_position

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        # Dough plateau through T1..T4 (≤100°C); T5 surface jump. T4 is well
        # below 100 (80°C) so the linear-interp crossing is genuinely off any
        # sensor: frac = (100-80)/(180-80) = 0.20 → x = 3/7 + 0.20*(1/7) ≈
        # 0.4571.
        temps = np.array([60.0, 70.0, 75.0, 80.0, 180.0, 200.0, 210.0, 215.0])
        x_cross = _crossing_position(positions, temps, 100.0)
        assert x_cross is not None
        assert 3 / 7.0 < x_cross < 4 / 7.0, (
            f"Expected crossing in (3/7, 4/7), got {x_cross:.4f}"
        )
        # Off-sensor: not within 0.005 of any sensor position.
        sensor_positions = [i / 7.0 for i in range(8)]
        assert min(abs(x_cross - sp) for sp in sensor_positions) > 0.005, (
            f"x_cross={x_cross:.4f} is sensor-aligned; interpolation didn't engage"
        )

    def test_no_crossing_returns_none(self):
        from src.data.spatial_reconstruction.piecewise import _crossing_position

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        temps = np.full(8, 90.0)  # never crosses 100
        assert _crossing_position(positions, temps, 100.0) is None


# ---------------------------------------------------------------------------
# End-to-end classifier interpolation: temperature_series is a real spatial
# interpolation, not a copy of the nearest sensor.
# ---------------------------------------------------------------------------


def _ts(n: int, period_s: float = 5.0) -> np.ndarray:
    return np.arange(n, dtype=float) * period_s


def _make_synthetic_for_off_sensor_core(n: int = 200) -> pd.DataFrame:
    """Construct a synthetic 8-sensor curve where the slowest-heating dough
    sensor is T3 (idx 2) but the parabolic vertex of (time_to_60c) lies
    OFF-sensor (between T2 and T3 or T3 and T4) so x_core != 2/7."""
    period_s = 5.0
    t_room = 22.0
    df = pd.DataFrame({"Timestamp": _ts(n, period_s)})

    # Per-sensor delay (samples held at room temp before rise begins).
    # T3 has the longest delay (slowest = anchor). T2 and T4 are also delayed
    # so that the parabolic vertex (in time_to_60c) sits between T3 and one
    # of its neighbours.
    rise_delays_samples = {
        "T1": 5,
        "T2": 25,   # second slowest
        "T3": 30,   # slowest (anchor)
        "T4": 18,   # slightly slower than T1
        "T5": 8,
        "T6": 4,
        "T7": 2,
        "T8": 0,
    }
    peak_target = {
        "T1": 95.0, "T2": 99.0, "T3": 99.0, "T4": 99.0,
        "T5": 200.0, "T6": 220.0, "T7": 220.0, "T8": 220.0,
    }
    n_rise = 80
    n_plateau = 30
    n_fall = 40
    for s, delay in rise_delays_samples.items():
        peak = peak_target[s]
        pre = np.full(delay, t_room)
        rise = np.linspace(t_room, peak, n_rise)
        plateau = np.full(n_plateau, peak)
        fall = np.linspace(peak, t_room + 5.0, n_fall)
        used = len(pre) + len(rise) + len(plateau) + len(fall)
        n_post = max(0, n - used)
        post = np.full(n_post, t_room + 5.0)
        arr = np.concatenate([pre, rise, plateau, fall, post])
        # Trim or pad to exactly n samples.
        if len(arr) > n:
            arr = arr[:n]
        elif len(arr) < n:
            arr = np.concatenate([arr, np.full(n - len(arr), arr[-1])])
        df[s] = arr
    df["CoreTemperature"] = df["T1"]
    return df


class TestClassifierTemperatureSeriesIsInterpolated:
    def test_temperature_series_is_spatial_interpolation(self):
        """Synthetic where x_core lands between T2 and T3 with linear
        interpolation expected; assert that for each timestep
        ``assignment.core.temperature_series[t] ≈ frac*T2[t] + (1-frac)*T3[t]``.
        """
        from src.data.spatial_reconstruction.classifier import classify

        df = _make_synthetic_for_off_sensor_core()
        result = classify(df, sample_period_ms=5000)
        x_core = result.core_assignment.position_normalised
        # x_core must NOT be exactly at T2 (1/7) or T3 (2/7) — it must be
        # interpolated.
        assert x_core not in (1 / 7.0, 2 / 7.0), (
            f"x_core={x_core} is sensor-aligned; interpolation never engaged."
        )
        # Compute expected blend: x_core falls between two sensors at p_lo, p_hi.
        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        upper = int(np.searchsorted(positions, x_core))
        lower = upper - 1
        assert 0 <= lower < 7
        x_lo, x_hi = positions[lower], positions[upper]
        frac = (x_core - x_lo) / (x_hi - x_lo)
        s_lo, s_hi = f"T{lower+1}", f"T{upper+1}"
        expected = (1 - frac) * df[s_lo].to_numpy() + frac * df[s_hi].to_numpy()

        actual = result.core_assignment.temperature_series.to_numpy()
        np.testing.assert_allclose(actual, expected, rtol=1e-6)

        # And it must not be byte-identical to the nearest sensor's series.
        nearest = result.core_assignment.nearest_sensor
        nearest_series = df[nearest].to_numpy()
        diff_max = np.max(np.abs(actual - nearest_series))
        assert diff_max > 0.1, (
            f"temperature_series identical to {nearest} (max diff={diff_max:.4f})"
        )


# ---------------------------------------------------------------------------
# Real-CSV regression: at least one fixture must have an off-sensor position
# (offset > 0.005 from the nearest i/7).
# ---------------------------------------------------------------------------


class TestRealCsvInterpolationEngages:
    @pytest.fixture(scope="class")
    def loaders(self):
        from src.data.loader import ThermalProfileLoader
        from tests.fixtures.curve_boundary_cases import _REAL_CSVS

        out = []
        for name, path in _REAL_CSVS.items():
            if not os.path.exists(path):
                continue
            ld = ThermalProfileLoader()
            ld.load_csv(file_path=path)
            out.append((name, ld))
        return out

    def test_real_csv_interpolation_engages_on_at_least_one_fixture(self, loaders):
        sensor_positions = [i / 7.0 for i in range(8)]

        def _is_off_sensor(p):
            if p is None:
                return False
            return min(abs(p - sp) for sp in sensor_positions) > 0.005

        off_sensor_count = 0
        total = 0
        for name, loader in loaders:
            for curve_idx in range(loader.get_curve_count()):
                a = loader.curve_sensor_assignments.get(curve_idx, {})
                core_x = a.get("core_position_normalised")
                surface_x = a.get("surface_position_normalised")
                if _is_off_sensor(core_x) or _is_off_sensor(surface_x):
                    off_sensor_count += 1
                total += 1
        assert off_sensor_count >= 1, (
            f"No real-CSV fixture has off-sensor position "
            f"({off_sensor_count}/{total} interpolated). Expected ≥1."
        )


# ---------------------------------------------------------------------------
# Stefan model: front position is the continuous T = 100 °C crossing.
# ---------------------------------------------------------------------------


class TestStefanFrontIsContinuous:
    def test_stefan_front_is_continuous_crossing(self):
        """Stefan model: x_dough_air should be a continuous interpolation,
        not a sensor-aligned midpoint."""
        from src.data.spatial_reconstruction.classifier import classify

        # Construct a fixture where the 100°C crossing is at x ≈ 0.5
        # between T4 (=99.5) and T5 (=180): linear interp at T=100 →
        # x = 3/7 + (100-99.5)/(180-99.5) * (4/7 - 3/7) = 3/7 + 0.0062*(1/7) ≈ 0.4295
        # Wait, our positions are 0..1/7..2/7..3/7..4/7..5/7..6/7..1.0
        # Let's place the jump between idx 3 (3/7≈0.4286) and idx 4 (4/7≈0.5714).
        df = _make_synthetic_for_stefan_crossing()
        result = classify(df, sample_period_ms=5000, model="stefan")
        x = result.profile_fit.x_dough_air
        # Single interface; not tuple.
        assert x is not None and not isinstance(x, tuple)
        # Off-sensor: not exactly at 3/7 or 4/7.
        sensor_positions = [i / 7.0 for i in range(8)]
        assert min(abs(x - sp) for sp in sensor_positions) > 0.005, (
            f"Stefan front x={x:.4f} is sensor-aligned"
        )


def _make_synthetic_for_stefan_crossing(n: int = 130) -> pd.DataFrame:
    """Synthetic where the spatial T(x) profile crosses 100°C strictly between
    T4 and T5 (so the Stefan front sits at a continuous off-sensor x)."""
    period_s = 5.0
    t_room = 22.0
    df = pd.DataFrame({"Timestamp": _ts(n, period_s)})
    # Terminal temps engineered so linear interp crosses 100 well between
    # T4 (99.0) and T5 (160.0): frac = (100-99)/(160-99) ≈ 0.0164.
    # x_cross = 3/7 + 0.0164 * (1/7) ≈ 0.4309. Off from 3/7 by ~0.002 — too
    # close to the sensor. Use T4=80, T5=180 → frac=(100-80)/(180-80)=0.20.
    # x_cross = 3/7 + 0.20*(1/7) = 3.2/7 ≈ 0.4571.
    peaks = [40.0, 60.0, 75.0, 80.0, 180.0, 200.0, 210.0, 215.0]
    n_pre, n_rise, n_plateau, n_fall = 30, 60, 20, 20
    n_post = n - n_pre - n_rise - n_plateau - n_fall
    for i, s in enumerate(("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")):
        peak = peaks[i]
        pre = np.full(n_pre, t_room)
        rise = np.linspace(t_room, peak, n_rise)
        plateau = np.full(n_plateau, peak)
        fall = np.linspace(peak, t_room + 5.0, n_fall)
        post = np.full(n_post, t_room + 5.0)
        df[s] = np.concatenate([pre, rise, plateau, fall, post])
    df["CoreTemperature"] = df["T1"]
    return df
