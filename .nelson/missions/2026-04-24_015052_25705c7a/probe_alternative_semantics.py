"""Probe: evaluate alternative semantics that might reduce false positives.

Alternative A: coordinated-drop — require at least K sensors (K>=3) to show
drop above threshold on the SAME sample, confirmed for confirm_n samples.
Rationale: a real probe pull drops MANY sensors simultaneously; random noise
rarely does.

Alternative B: coordinated-sum — at each sample in confirm window, compute the
median (or count) of sensors exceeding a softer rate threshold; require that
count/median clear a bar.

Run against:
  - BA3C_1759 (clean unlidded, σ=1.0 noise) — expect LOW false positive rate
  - post_wonder_meal (PWM, truncated) — expect HIGH true positive rate
  - staggered spikes spread=8 — expect NO false positive

If an alternative that kills false positives on real noise AND fires on PWM
exists, that makes the any-sensor-per-sample even more suspect as a design.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO_ROOT)


def rate_at(temps: np.ndarray, timestamps: np.ndarray, idx: int) -> float:
    if idx == 0:
        return 0.0
    dt = timestamps[idx] - timestamps[idx - 1]
    if dt <= 0:
        return 0.0
    return (temps[idx - 1] - temps[idx]) / dt


def coordinated_k_drop(
    sensor_temps: dict[str, np.ndarray],
    timestamps: np.ndarray,
    first_scan: int,
    rate_c_s: float,
    confirm_n: int,
    min_k_sensors: int,
    upper_bound: int | None = None,
) -> int | None:
    """Coordinated-drop variant: require at least `min_k_sensors` sensors to
    exceed threshold on each sample of the confirm window."""
    n = len(timestamps)
    if upper_bound is None:
        upper_bound = n
    upper_bound = min(upper_bound, n)

    for j in range(first_scan, upper_bound):
        if j == 0:
            continue
        window_ok = True
        for k in range(confirm_n):
            idx = j + k
            if idx >= n:
                window_ok = False
                break
            count = sum(
                1 for temps in sensor_temps.values()
                if idx < len(temps) and rate_at(temps, timestamps, idx) >= rate_c_s
            )
            if count < min_k_sensors:
                window_ok = False
                break
        if window_ok:
            return j
    return None


def load_real_csv(name: str) -> pd.DataFrame:
    paths = {
        "100098DE": os.path.join(_REPO_ROOT, "ProbeData_100098DE_2025-05-30 13_51_07.csv"),
        "BA3C_0946": os.path.join(_REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"),
        "BA3C_1759": os.path.join(_REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"),
        "PWM": os.path.join(_REPO_ROOT, "Post Wonder Meal 20251017.csv"),
    }
    df = pd.read_csv(paths[name], skiprows=10)
    unnamed = [c for c in df.columns if c.startswith("Unnamed:")]
    if unnamed:
        df = df.drop(columns=unnamed)
    df = df.dropna(subset=["VirtualCoreTemperature"]).reset_index(drop=True)
    return df


def detect_with_k(df, sensor_cols, min_k: int, rate_c_s: float = 2.0, confirm_n: int = 2) -> bool:
    """Find common_peak_idx analog and call coordinated_k_drop over cool window."""
    available = [s for s in sensor_cols if s in df.columns]
    if len(available) < 2:
        return False
    first_peak_indices = [int(df[s].idxmax()) for s in available]
    latest_sensor_pos = int(np.argmax(first_peak_indices))
    latest_sensor = available[latest_sensor_pos]
    arr = df[latest_sensor].to_numpy()
    max_val = float(np.nanmax(arr))
    hits = np.flatnonzero(arr >= max_val - 0.05)
    common_peak_idx = int(hits[-1]) if len(hits) else int(df[latest_sensor].idxmax())
    ts = df["Timestamp"].to_numpy(dtype=float)
    dt = float(np.median(np.diff(ts))) if len(ts) >= 2 else 5.0
    if dt <= 0:
        dt = 5.0
    cool_window_samples = max(1, int(round(60.0 / dt)))
    upper = min(common_peak_idx + cool_window_samples, len(df))
    sensor_temps = {
        s: df[s].to_numpy(dtype=float) for s in available
    }
    idx = coordinated_k_drop(
        sensor_temps, ts, max(common_peak_idx, 1),
        rate_c_s, confirm_n, min_k, upper,
    )
    return idx is not None


def main():
    sensor_cols = [f"T{i}" for i in range(1, 9)]

    print("=== BASELINE firing on real PWM (should be True — true positive) ===")
    pwm = load_real_csv("PWM")
    for k in [1, 2, 3, 4, 5]:
        fires = detect_with_k(pwm, sensor_cols, min_k=k)
        print(f"  min_k={k}: PWM fires={fires}")

    print()
    print("=== NOISE PERTURBATION at σ=1.0 across k values (100 seeds, BA3C_1759) ===")
    ba3c = load_real_csv("BA3C_1759")
    for k in [1, 2, 3, 4, 5]:
        rng_master = np.random.default_rng(12345)
        flips = 0
        for seed in range(100):
            rng = np.random.default_rng(int(rng_master.integers(0, 2**31 - 1)))
            noisy = ba3c.copy()
            for s in sensor_cols:
                if s in noisy.columns:
                    noisy[s] = noisy[s] + rng.normal(0.0, 1.0, size=len(noisy))
            if detect_with_k(noisy, sensor_cols, min_k=k):
                flips += 1
        print(f"  min_k={k}: BA3C_1759 false-positive rate = {flips}/100 ({flips}%)")

    print()
    print("=== NOISE at σ=1.0 across k values (100 seeds, 100098DE) ===")
    de = load_real_csv("100098DE")
    for k in [1, 2, 3, 4, 5]:
        rng_master = np.random.default_rng(12345)
        flips = 0
        for seed in range(100):
            rng = np.random.default_rng(int(rng_master.integers(0, 2**31 - 1)))
            noisy = de.copy()
            for s in sensor_cols:
                if s in noisy.columns:
                    noisy[s] = noisy[s] + rng.normal(0.0, 1.0, size=len(noisy))
            if detect_with_k(noisy, sensor_cols, min_k=k):
                flips += 1
        print(f"  min_k={k}: 100098DE false-positive rate = {flips}/100 ({flips}%)")


if __name__ == "__main__":
    main()
