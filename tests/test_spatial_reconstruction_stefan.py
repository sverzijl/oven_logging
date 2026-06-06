"""Per-component unit tests for the Stefan-physics-constrained spatial fit
(M2b HMS Vanguard).

The Stefan model treats the dough/air interface as an evaporation front
pinned at exactly T = 100 °C and constrains the crust slope through a single
effective thermal-diffusivity coupling parameter ``alpha_crust``.

These tests cover:

- 100 °C pin invariant (dough/air front sits at exactly 100 °C).
- Canonical insertion recovery (single front between in-dough and air sensors).
- Through-loaf recovery (two fronts when both ends are in air).
- Full-immersion graceful degradation (no front when no sensor exceeds 100 °C).
- Lid detection (sensors plateauing below cavity).
- End-to-end dispatch via ``classify(model='stefan')`` on real fixtures (no
  crash) and on synthetic cases (agreement with piecewise on unambiguous
  physics).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers — mirror the synthetic builders in
# tests/test_spatial_reconstruction_piecewise.py.
# ---------------------------------------------------------------------------


def _make_8_sensor_df(
    peaks: list,
    n_pre: int = 20,
    n_rise: int = 60,
    n_fall: int = 30,
    n_post: int = 10,
    period_s: float = 5.0,
    rise_kink_at: dict | None = None,
    plateau_caps: dict | None = None,
) -> pd.DataFrame:
    """Build a synthetic 8-sensor DataFrame with controllable peaks.

    Parameters
    ----------
    peaks:
        list of 8 peak values for T1..T8 (peak temp of the rise).
    rise_kink_at:
        Optional ``{sensor: kink_temp}`` — sensor curves plateau at
        ``kink_temp`` for the middle third of the rise before continuing
        to ``peak``. Models the latent-heat plateau-then-rise of a surface
        sensor.
    plateau_caps:
        Optional ``{sensor: plateau_T}`` — sensor stays flat at plateau_T
        across the entire rise/fall (used to model a sensor that never
        clears the plateau, e.g. a deep-dough sensor).
    """
    n = n_pre + n_rise + n_fall + n_post
    rise_kink_at = rise_kink_at or {}
    plateau_caps = plateau_caps or {}
    rng = np.random.default_rng(11)
    t_room = 22.0

    def _trace(sensor: str, peak: float) -> np.ndarray:
        if sensor in plateau_caps:
            cap = plateau_caps[sensor]
            pre = np.full(n_pre, t_room)
            rise = np.linspace(t_room, cap, n_rise)
            plateau = np.full(n_fall, cap)
            post = np.full(n_post, cap)
            return np.concatenate([pre, rise, plateau, post])
        if sensor in rise_kink_at:
            k = rise_kink_at[sensor]
            n_to_kink = n_rise // 3
            n_plat = n_rise // 3
            n_after = n_rise - n_to_kink - n_plat
            pre = np.full(n_pre, t_room)
            seg1 = np.linspace(t_room, k, n_to_kink)
            seg2 = np.full(n_plat, k)
            seg3 = np.linspace(k, peak, n_after)
            rise = np.concatenate([seg1, seg2, seg3])
            fall = np.linspace(peak, t_room + 5.0, n_fall)
            post = np.full(n_post, t_room + 5.0)
            return np.concatenate([pre, rise, fall, post])
        pre = np.full(n_pre, t_room)
        rise = np.linspace(t_room, peak, n_rise)
        fall = np.linspace(peak, t_room + 5.0, n_fall)
        post = np.full(n_post, t_room + 5.0)
        trace = np.concatenate([pre, rise, fall, post])
        return trace + rng.normal(0, 0.3, n)

    df = pd.DataFrame({"Timestamp": np.arange(n, dtype=float) * period_s})
    for i, sensor in enumerate(("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")):
        df[sensor] = _trace(sensor, peaks[i])
    df["CoreTemperature"] = df["T1"]
    df["VirtualCoreTemperature"] = df["T1"]
    df["VirtualCoreSensor"] = "T1"
    df["VirtualSurfaceSensor"] = "T7"
    df["VirtualAmbientSensor"] = "T8"
    df["VirtualSurfaceTemperature"] = df["T7"]
    df["VirtualAmbientTemperature"] = df["T8"]
    return df


def _build_features_and_terminals(df: pd.DataFrame) -> tuple[dict, dict, tuple]:
    """Run feature extraction and return (features, terminal_temps, positions)."""
    from src.data.spatial_reconstruction.profile import extract_features
    from src.data.spatial_reconstruction.geometry import lookup_geometry

    features = extract_features(df, sample_period_ms=5000)
    sensors = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")
    terminal_temps = {
        s: features.get(s, {}).get("terminal_temp", float("nan")) for s in sensors
    }
    positions = tuple(lookup_geometry()["sensor_positions_normalised"])
    return features, terminal_temps, positions


# ---------------------------------------------------------------------------
# Stefan fit — unit tests
# ---------------------------------------------------------------------------


class TestStefanFitInvariants:
    def test_fit_stefan_pins_plateau_at_100c(self):
        """The Stefan front position must correspond to T = 100 °C exactly.

        We verify by interpolating the (x_i, T_i) terminal vector at the
        fit's ``x_dough_air`` and asserting T(x_dough_air) ≈ 100 °C.
        """
        from src.data.spatial_reconstruction.stefan import fit_stefan

        # Canonical insertion: T1-T4 dough plateau (≤100), T5-T8 free-rising air.
        peaks = [95.0, 97.0, 99.0, 100.0, 140.0, 180.0, 200.0, 215.0]
        df = _make_8_sensor_df(
            peaks,
            rise_kink_at={"T5": 100.0, "T6": 100.0, "T7": 100.0, "T8": 100.0},
        )
        _, terminal_temps, positions = _build_features_and_terminals(df)
        features, _, _ = _build_features_and_terminals(df)
        fit = fit_stefan(features, terminal_temps, positions)

        assert fit.model == "stefan"
        assert fit.x_dough_air is not None
        # Interpolate terminal vector at fit position; should equal 100 °C.
        xs = np.array(positions)
        ts = np.array([terminal_temps[s] for s in
                       ("T1","T2","T3","T4","T5","T6","T7","T8")])
        x_front = fit.x_dough_air if not isinstance(fit.x_dough_air, tuple) else fit.x_dough_air[0]
        T_at_front = float(np.interp(x_front, xs, ts))
        assert abs(T_at_front - 100.0) <= 0.5, (
            f"Stefan front should pin T at 100°C; got T={T_at_front:.2f} at x={x_front:.3f}"
        )

    def test_fit_stefan_recovers_canonical_insertion_position(self):
        """Single-front canonical insertion: T4 ≈ 99°C, T5 ≈ 100°C, T6 hot.

        Stefan should place the front between T4 and T5 (positions 3/7 and 4/7).
        """
        from src.data.spatial_reconstruction.stefan import fit_stefan

        peaks = [95.0, 96.0, 98.0, 99.0, 100.0, 140.0, 180.0, 210.0]
        df = _make_8_sensor_df(
            peaks,
            rise_kink_at={"T6": 100.0, "T7": 100.0, "T8": 100.0},
            plateau_caps={"T1": 95.0, "T2": 96.0, "T3": 98.0, "T4": 99.0, "T5": 100.0},
        )
        _, terminal_temps, positions = _build_features_and_terminals(df)
        features, _, _ = _build_features_and_terminals(df)
        fit = fit_stefan(features, terminal_temps, positions)

        assert fit.x_dough_air is not None
        x_front = fit.x_dough_air if not isinstance(fit.x_dough_air, tuple) else fit.x_dough_air[1]
        # Front should sit between positions[3]=3/7 and positions[5]=5/7.
        assert 3 / 7 <= x_front <= 5 / 7, (
            f"front x={x_front:.3f} not between T4 (3/7≈0.43) and T6 (5/7≈0.71)"
        )

    def test_fit_stefan_through_loaf_returns_two_fronts(self):
        """T1, T8 in air; T2-T7 dough cluster ≈ 95-99°C. Stefan returns 2 fronts."""
        from src.data.spatial_reconstruction.stefan import fit_stefan

        peaks = [200.0, 95.0, 96.0, 97.0, 97.0, 96.0, 95.0, 200.0]
        df = _make_8_sensor_df(
            peaks,
            rise_kink_at={"T1": 100.0, "T8": 100.0},
            plateau_caps={"T2": 95.0, "T3": 96.0, "T4": 97.0,
                          "T5": 97.0, "T6": 96.0, "T7": 95.0},
        )
        _, terminal_temps, positions = _build_features_and_terminals(df)
        features, _, _ = _build_features_and_terminals(df)
        fit = fit_stefan(features, terminal_temps, positions)

        assert isinstance(fit.x_dough_air, tuple), (
            f"expected 2-tuple of fronts; got {fit.x_dough_air!r}"
        )
        x_left, x_right = fit.x_dough_air
        assert x_left < x_right
        assert x_left < 0.5 < x_right

    def test_fit_stefan_full_immersion_returns_no_front(self):
        """All 8 sensors plateau ≤ 100 °C → no Stefan front detectable."""
        from src.data.spatial_reconstruction.stefan import fit_stefan

        peaks = [95.0, 95.5, 96.0, 96.5, 97.0, 97.5, 98.0, 98.5]
        df = _make_8_sensor_df(
            peaks,
            plateau_caps={s: peaks[i] for i, s in enumerate(
                ("T1","T2","T3","T4","T5","T6","T7","T8"))},
        )
        _, terminal_temps, positions = _build_features_and_terminals(df)
        features, _, _ = _build_features_and_terminals(df)
        fit = fit_stefan(features, terminal_temps, positions)

        assert fit.x_dough_air is None, (
            f"full-immersion case should yield no front; got {fit.x_dough_air!r}"
        )

    def test_fit_stefan_alpha_crust_is_numeric_on_full_immersion(self):
        """fix/deep-review #7 — alpha_crust is a float-typed field. On the
        full-immersion / all-air / lid-bake paths (no air-side crust fit) it
        must store float('nan'), NOT None, matching piecewise's float-only
        fields and keeping the field numeric for downstream consumers.
        """
        import math

        from src.data.spatial_reconstruction.stefan import fit_stefan

        peaks = [95.0, 95.5, 96.0, 96.5, 97.0, 97.5, 98.0, 98.5]
        df = _make_8_sensor_df(
            peaks,
            plateau_caps={s: peaks[i] for i, s in enumerate(
                ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"))},
        )
        features, terminal_temps, positions = _build_features_and_terminals(df)
        fit = fit_stefan(features, terminal_temps, positions)
        alpha = fit.fit_quality.alpha_crust
        assert alpha is not None, "alpha_crust must be numeric (nan), not None"
        assert isinstance(alpha, float)
        assert math.isnan(alpha), f"expected nan on full-immersion, got {alpha}"

    def test_fit_stefan_lid_detection(self):
        """Lid bake: T1-T4 dough, T5-T6 air at cavity, T7-T8 lid plateau ~150°C.

        Stefan should report ``x_lid`` somewhere in the T7/T8 region.
        """
        from src.data.spatial_reconstruction.stefan import fit_stefan

        peaks = [95.0, 97.0, 99.0, 100.0, 220.0, 220.0, 150.0, 150.0]
        df = _make_8_sensor_df(
            peaks,
            rise_kink_at={"T5": 100.0, "T6": 100.0, "T7": 100.0, "T8": 100.0},
            plateau_caps={"T1": 95.0, "T2": 97.0, "T3": 99.0, "T4": 100.0},
        )
        _, terminal_temps, positions = _build_features_and_terminals(df)
        features, _, _ = _build_features_and_terminals(df)
        fit = fit_stefan(features, terminal_temps, positions)

        assert fit.x_lid is not None, "lid plateau on T7/T8 should yield x_lid"
        assert fit.x_lid >= positions[6] - 1e-6, (
            f"lid position {fit.x_lid} should sit at T7/T8 (≥ {positions[6]:.3f})"
        )


# ---------------------------------------------------------------------------
# End-to-end classify(model="stefan") dispatch tests
# ---------------------------------------------------------------------------


class TestClassifyStefanDispatch:
    @pytest.mark.parametrize("case_name", [
        "real_100098DE_1351",
        "real_1000BA3C_0946",
        "wonder_white_10k_lidded",
        "post_wonder_meal_lidded",
        # NOTE: real_1000BA3C_1759 is multi-curve; classify operates on
        # single-curve slices. Excluded from the smoke loop.
    ])
    def test_classify_stefan_model_runs_on_real_fixtures(self, case_name):
        """Smoke test: classify(model='stefan') runs without crashing."""
        from src.data.spatial_reconstruction.classifier import classify
        from tests.fixtures.curve_boundary_cases import CASES

        case = next(c for c in CASES if c["name"] == case_name)
        result = classify(case["df"], sample_period_ms=5000, model="stefan")
        assert result is not None
        assert result.model_used == "stefan"
        # core is always populated (worst case, falls back to coldest terminal).
        assert result.core is not None

    @pytest.mark.parametrize("case_name", [
        "synthetic_shallow_insertion",
        "synthetic_full_immersion",
        "synthetic_lid_touch",
        "synthetic_probe_pull_mid_bake",
    ])
    def test_classify_piecewise_and_stefan_agree_on_synthetics(self, case_name):
        """On the synthetic fixtures (unambiguous physics), both models must
        return the same role assignments."""
        from src.data.spatial_reconstruction.classifier import classify
        from tests.fixtures.curve_boundary_cases import CASES

        case = next(c for c in CASES if c["name"] == case_name)
        df = case["df"]
        pw = classify(df, sample_period_ms=5000, model="piecewise")
        sf = classify(df, sample_period_ms=5000, model="stefan")
        assert pw.core == sf.core, (
            f"{case_name}: piecewise.core={pw.core}, stefan.core={sf.core}"
        )
        assert pw.surface == sf.surface, (
            f"{case_name}: piecewise.surface={pw.surface}, stefan.surface={sf.surface}"
        )
