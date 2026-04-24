"""Q2 — threshold fragility probe.

Perturb threshold CLIFF_PRE_PEAK_PLATEAU_SECONDS and observe whether cliff fires
on lidded and unlidded CSVs.  Also perturb the fixtures themselves: trim PWM
plateau, extend unlidded plateau.
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy

import numpy as np
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from config import constants  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402
from tests.fixtures.curve_boundary_cases import CASES, load_real_case  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402


def run_with_threshold(df: pd.DataFrame, threshold_s: float):
    cfg = dict(constants.CURVE_DETECTION_CONFIG)
    cfg["CLIFF_PRE_PEAK_PLATEAU_SECONDS"] = threshold_s
    det = CurveBoundaryDetector(cfg)
    curves = det.extract_curves(df)
    return curves


def summarize(curves):
    return [(c["start_idx"], c["end_idx"], c["truncated"]) for c in curves]


def case_df(name):
    return next(c for c in CASES if c["name"] == name)["df"]


def test_thresholds():
    print("\n=== Q2: threshold sweep across CURRENT fixtures ===")
    print(f"{'case':<45} {'200s':<15} {'220s':<15} {'240s':<15} {'250s':<15} {'300s':<15} {'350s':<15}")
    for name in [
        "post_wonder_meal_lidded", "cliff_probe_pull_with_monotonic_cooldown",
        "wonder_white_10k_lidded",
        "real_100098DE_1351", "real_1000BA3C_0946", "real_1000BA3C_1759",
        "lidded_bake_plateau_classic", "noise_spike_midbake",
    ]:
        df = case_df(name)
        row = []
        for t in (200, 220, 240, 250, 300, 350):
            try:
                cs = run_with_threshold(df, float(t))
                row.append(str(summarize(cs)[:2]))
            except Exception as e:
                row.append(f"ERR:{e.__class__.__name__}")
        print(f"{name:<45} " + " ".join(f"{x:<15}" for x in row))


def _extend_plateau_csv(df: pd.DataFrame, name: str, peak_idx: int, extra_seconds: float, tol: float = 2.0):
    """Inject a pseudo-plateau right before peak by duplicating peak-adjacent samples.

    Returns a new DataFrame with extra_seconds of at-peak hold inserted before peak_idx.
    """
    ts = df["Timestamp"].to_numpy(dtype=float)
    dt = float(np.median(np.diff(ts)))
    n_extra = max(int(round(extra_seconds / dt)), 1)
    # Synthesize n_extra samples at peak_temp - 0.5 °C (within tol) inserted at peak_idx.
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    peak_temp = float(temps[peak_idx])
    insert_block = pd.DataFrame({c: df.iloc[peak_idx][c] for c in df.columns}, index=range(n_extra))
    # Copy core temp slightly below peak (within tol)
    insert_block["Timestamp"] = [ts[peak_idx] + (k + 1) * dt for k in range(n_extra)]
    for core_col in ("CoreTemperature", "VirtualCoreTemperature"):
        if core_col in df.columns:
            insert_block[core_col] = peak_temp - 0.5
    # Shift original post-peak timestamps
    df_copy = df.copy()
    df_copy.loc[peak_idx + 1:, "Timestamp"] = df_copy.loc[peak_idx + 1:, "Timestamp"] + n_extra * dt
    out = pd.concat([df_copy.iloc[: peak_idx + 1], insert_block, df_copy.iloc[peak_idx + 1:]], ignore_index=True)
    return out


def test_fixture_perturb():
    print("\n=== Q2: perturb the FIXTURES themselves ===")
    print("--- extend unlidded plateau (should NOT fire cliff even if extended) ---")
    for name, peak_override in [
        ("real_100098DE_1351", None),
        ("real_1000BA3C_0946", None),
    ]:
        df = case_df(name)
        temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
        peak_idx = peak_override if peak_override is not None else int(np.argmax(temps))
        for extra_s in (180, 250, 350):
            df_pert = _extend_plateau_csv(df, name, peak_idx, extra_s)
            cfg = dict(constants.CURVE_DETECTION_CONFIG)
            det = CurveBoundaryDetector(cfg)
            curves = det.extract_curves(df_pert)
            print(f"  {name} +{extra_s}s flat pre-peak: {summarize(curves)}")

    print("--- trim PWM pre-cliff plateau (does cliff still fire?) ---")
    pwm = case_df("post_wonder_meal_lidded")
    # The PWM plateau spans from idx 313 (peak) down to idx 344 (just before cliff at idx 345).
    # To reduce pre-cliff plateau from ~310s toward shorter, drop samples between peak and idx 344.
    ts = pwm["Timestamp"].to_numpy(dtype=float)
    dt = float(np.median(np.diff(ts)))
    for target_plateau_s in (320, 280, 240, 220, 200, 180, 150):
        # Current plateau span = 310s (31 samples at 10s dt).
        # Remove samples from the plateau to reach target (by sub-sampling the plateau range).
        n_samples_to_keep = max(int(round(target_plateau_s / dt)), 1)
        plateau_start = 313  # peak idx
        plateau_end = 344    # last pre-cliff
        available = plateau_end - plateau_start + 1
        if n_samples_to_keep >= available:
            print(f"  PWM target plateau={target_plateau_s}s unreachable (need {n_samples_to_keep} samples, have {available})")
            continue
        # Keep first n_samples_to_keep of the plateau; drop the rest before the cliff
        drop = list(range(plateau_start + n_samples_to_keep, plateau_end + 1))
        pert = pwm.drop(index=drop).reset_index(drop=True)
        # Re-monotonize timestamps
        pert["Timestamp"] = np.arange(len(pert)) * dt
        cfg = dict(constants.CURVE_DETECTION_CONFIG)
        det = CurveBoundaryDetector(cfg)
        curves = det.extract_curves(pert)
        print(f"  PWM plateau trimmed to ~{target_plateau_s}s: {summarize(curves)}")


if __name__ == "__main__":
    test_thresholds()
    test_fixture_perturb()
