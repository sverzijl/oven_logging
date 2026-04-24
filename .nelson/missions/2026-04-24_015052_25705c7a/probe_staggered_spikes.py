"""Probe: staggered single-sample spikes across 8 sensors.

Synthetic curve where the 8 sensors each show a single-sample transient spike
at different indices within a 20-sample window in the cool region. No
coordinated probe pull happened — each sensor drops once then recovers.

With any-sensor-per-sample and confirm_n=2:
  At each sample during the "spike storm" one sensor might be dropping while
  the others are not — does the any-sensor rule require the SAME sensor across
  the 2-confirmation window, or just SOME sensor at each sample?

Vanguard's code says "SOME sensor at each sample" — so if T1 spikes at idx=k
and T2 spikes at idx=k+1, both samples would show a drop ≥ threshold (T1 at k,
T2 at k+1) and the 2-sample confirmation would fire even though no coordinated
probe pull happened.

If this fires contamination, the any-sensor semantics are too weak.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO_ROOT)

from src.data.thermodynamic_sensor_classifier import (  # noqa: E402
    identify_core_sensor_combined_rank,
    _detect_probe_removal_in_cool_window,
)
from config.constants import CORE_DETECTION_CONFIG  # noqa: E402


def build_staggered_spike_df(
    n_total: int = 400,
    period: float = 5.0,
    spike_magnitude: float = 15.0,  # single-sample drop (= 3.0 °C/s at dt=5s, above threshold 2.0)
    spike_start_idx: int = 300,  # in the cool window
    spike_spread: int = 20,
) -> pd.DataFrame:
    """Build 8 sensors rising to plateau then each showing a single-sample spike
    at different indices spread across ``spike_spread`` samples.
    """
    ts = np.arange(n_total) * period
    data = {"Timestamp": ts}
    sensors = [f"T{i}" for i in range(1, 9)]
    rng = np.random.default_rng(42)
    for k, s in enumerate(sensors):
        # Rise 30 → 98 over first 200 samples, then flat at ~98 with tiny drift.
        vals = np.zeros(n_total)
        vals[:200] = np.linspace(30.0, 98.0 - k * 0.3, 200)
        vals[200:] = 98.0 - k * 0.3
        # tiny drift / jitter
        vals += rng.normal(0.0, 0.02, n_total)
        # Stagger each sensor's spike across the window.
        spike_at = spike_start_idx + (k * (spike_spread // len(sensors)))
        if spike_at < n_total - 2:
            vals[spike_at] -= spike_magnitude
            # Recover on next sample
            vals[spike_at + 1] = vals[spike_at - 1] if spike_at - 1 >= 0 else vals[spike_at + 1]
        data[s] = vals

    df = pd.DataFrame(data)
    df["VirtualCoreTemperature"] = df["T1"]
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def build_single_transient_df(
    n_total: int = 400,
    period: float = 5.0,
    spike_rate_c_s: float = 2.1,
    spike_at: int = 305,
    duration: int = 1,
) -> pd.DataFrame:
    """Build a baseline curve and inject a single transient on T1 near peak+5.

    ``spike_rate_c_s`` chosen so one-sample-drop / period = rate. With period=5
    and rate=2.1 → drop magnitude = 10.5 °C. duration=1 should NOT fire
    confirm_n=2. duration=2 SHOULD fire.
    """
    ts = np.arange(n_total) * period
    data = {"Timestamp": ts}
    sensors = [f"T{i}" for i in range(1, 9)]
    for k, s in enumerate(sensors):
        vals = np.zeros(n_total)
        vals[:200] = np.linspace(30.0, 98.0 - k * 0.3, 200)
        vals[200:] = 98.0 - k * 0.3
        data[s] = vals

    df = pd.DataFrame(data)
    drop_per_sample = spike_rate_c_s * period
    for d in range(duration):
        idx = spike_at + d
        if idx < n_total:
            df.loc[idx, "T1"] = df.loc[spike_at - 1, "T1"] - drop_per_sample * (d + 1)
    df["VirtualCoreTemperature"] = df["T1"]
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def main():
    sensor_cols = [f"T{i}" for i in range(1, 9)]
    threshold = CORE_DETECTION_CONFIG["PROBE_REMOVAL_RATE_C_PER_SEC"]
    confirm_n = CORE_DETECTION_CONFIG["PROBE_REMOVAL_CONFIRM_SAMPLES"]

    print("=== STAGGERED SPIKES (8 sensors, 1-sample drop each, spread across 20 samples) ===")
    # 1-sample gap: every sensor pops on its own sample
    df = build_staggered_spike_df(spike_spread=20, spike_magnitude=15.0)
    idx = _detect_probe_removal_in_cool_window(
        df, common_peak_idx=200, cool_window_samples=150,
        sensor_columns=sensor_cols, rate_c_s=threshold, confirm_n=confirm_n,
    )
    winner, diag = identify_core_sensor_combined_rank(df, sensor_cols)
    print(f"  staggered (spread=20, mag=15): probe_removal_idx={idx}")
    print(f"  winner={winner}, contam={diag.get('cool_contamination_detected')}, "
          f"cool_available={diag.get('cool_available')}")

    # Tighter stagger (adjacent samples — classic "any-sensor at each sample" attack)
    df2 = build_staggered_spike_df(spike_spread=8, spike_magnitude=15.0)
    idx2 = _detect_probe_removal_in_cool_window(
        df2, common_peak_idx=200, cool_window_samples=150,
        sensor_columns=sensor_cols, rate_c_s=threshold, confirm_n=confirm_n,
    )
    winner2, diag2 = identify_core_sensor_combined_rank(df2, sensor_cols)
    print(f"  staggered (spread=8, mag=15): probe_removal_idx={idx2}")
    print(f"  winner={winner2}, contam={diag2.get('cool_contamination_detected')}")

    print()
    print("=== SINGLE-TRANSIENT TESTS ===")
    # 1-sample transient at 2.1 °C/s (above threshold) → confirm_n=2 should NOT fire
    df_t1 = build_single_transient_df(spike_rate_c_s=2.1, duration=1)
    idx_t1 = _detect_probe_removal_in_cool_window(
        df_t1, common_peak_idx=200, cool_window_samples=150,
        sensor_columns=sensor_cols, rate_c_s=threshold, confirm_n=confirm_n,
    )
    print(f"  1-sample transient @2.1 °C/s: idx={idx_t1} (expect None; confirm_n=2 guards)")

    # 2-sample sustained drop on one sensor at 2.1 °C/s → SHOULD fire
    df_t2 = build_single_transient_df(spike_rate_c_s=2.1, duration=2)
    idx_t2 = _detect_probe_removal_in_cool_window(
        df_t2, common_peak_idx=200, cool_window_samples=150,
        sensor_columns=sensor_cols, rate_c_s=threshold, confirm_n=confirm_n,
    )
    print(f"  2-sample sustained @2.1 °C/s: idx={idx_t2} (expect not None)")

    # 1-sample @0.6 °C/s (below threshold) → NOT fire
    df_t3 = build_single_transient_df(spike_rate_c_s=0.6, duration=1)
    idx_t3 = _detect_probe_removal_in_cool_window(
        df_t3, common_peak_idx=200, cool_window_samples=150,
        sensor_columns=sensor_cols, rate_c_s=threshold, confirm_n=confirm_n,
    )
    print(f"  1-sample transient @0.6 °C/s: idx={idx_t3} (expect None; below threshold)")


if __name__ == "__main__":
    main()
