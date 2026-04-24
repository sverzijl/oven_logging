"""Test common_peak_idx behaviour when multiple sensors have OVERLAPPING plateaus.

Briefing concern: "What happens when 2+ sensors have plateaus of different lengths
that overlap? Does the reference point fall INSIDE one sensor's plateau (biasing its
retained temp) but OUTSIDE another's (biasing against it)?"
"""
import os
import sys
import numpy as np
import pandas as pd

REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
sys.path.insert(0, REPO)
os.chdir(REPO)

from src.data.thermodynamic_sensor_classifier import identify_core_sensor_combined_rank


def case_overlapping_plateaus():
    """Two sensors with plateaus of different lengths.

    T1: peaks at idx 100, plateaus until idx 150 (long plateau).
    T2: peaks at idx 120, plateaus until idx 140 (shorter plateau, but peaks LATER).

    latest_peak_idx = argmax of per-sensor idxmax:
      T1.idxmax = 100, T2.idxmax = 120 → latest_sensor_pos = 1 → latest_sensor = T2
      common_peak_idx = _latest_at_max_idx(T2) = 140 (end of T2's plateau)

    At idx 140, T1 is PAST its plateau and cooling. T2 is AT its peak.
    So T2 gets an artificially high retained-temp reading. Does that bias?
    """
    n = 300
    period = 5.0
    ts = np.arange(n, dtype=float) * period
    df = pd.DataFrame({"Timestamp": ts})

    # T1: rise 0..99, plateau 100..150, cool 151..299
    t1 = np.concatenate([
        np.linspace(30, 95, 100),
        np.full(51, 95.0),
        np.linspace(95, 30, 149),
    ])
    # T2: rise 0..119, plateau 120..140, cool 141..299
    t2 = np.concatenate([
        np.linspace(30, 95, 120),
        np.full(21, 95.0),
        np.linspace(95, 30, 159),
    ])
    # T3..T8: fast-heating, no plateau
    def fast(offset):
        return np.concatenate([
            np.linspace(30, 95, 60 + offset),
            np.linspace(95, 30, n - (60 + offset)),
        ])
    df["T1"] = t1[:n]
    df["T2"] = t2[:n]
    for i, s in enumerate(["T3", "T4", "T5", "T6", "T7", "T8"], start=0):
        df[s] = fast(5 * i)[:n]

    winner, diag = identify_core_sensor_combined_rank(
        df, ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
    )
    print("Overlapping-plateau case:")
    print(f"  T1.idxmax={int(df['T1'].idxmax())} value={df['T1'].max():.2f}")
    print(f"  T2.idxmax={int(df['T2'].idxmax())} value={df['T2'].max():.2f}")
    peak = diag["T1"]["common_peak_idx"]
    print(f"  common_peak_idx = {peak}  (T1 value at this idx = {df['T1'].iloc[peak]:.2f}, "
          f"T2 value = {df['T2'].iloc[peak]:.2f})")
    for s in sorted(diag, key=lambda k: diag[k]["combined_score"]):
        d = diag[s]
        print(f"    {s}: heat={d['heat_rank']} cool={d['cool_rank']} "
              f"combined={d['combined_score']} retain={d['retained_c_at_cool_window']:.2f}")
    print(f"  winner = {winner}")

    # Additional case: single-peak unlidded curve (most real CSVs).
    # Does _latest_at_max_idx collapse to idxmax as Iron Duke claims?
    print()
    print("Single-peak case (no plateau):")
    n2 = 300
    ts2 = np.arange(n2, dtype=float) * period
    df2 = pd.DataFrame({"Timestamp": ts2})
    for i, s in enumerate(["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"], start=0):
        rise_n = 80 + 10 * i
        df2[s] = np.concatenate([
            np.linspace(30, 100, rise_n),
            np.linspace(100, 30, n2 - rise_n),
        ])[:n2]
    # Each T has a single-sample peak. latest_at_max should equal idxmax.
    winner2, diag2 = identify_core_sensor_combined_rank(
        df2, ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
    )
    peak2 = diag2["T1"]["common_peak_idx"]
    manual_idxmax = max(int(df2[s].idxmax()) for s in ["T1","T2","T3","T4","T5","T6","T7","T8"])
    print(f"  common_peak_idx = {peak2}")
    print(f"  max(idxmax across sensors) = {manual_idxmax}")
    print(f"  match = {peak2 == manual_idxmax}")


if __name__ == "__main__":
    case_overlapping_plateaus()
