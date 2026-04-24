"""Construct fixtures with EXACT gap values and verify override gate.

Goal: show gap=4 fires override, gap=3 does not.

Strategy: build 8 sensors, manipulate ranks so firmware T1 has combined score
exactly N points above the winner.
"""
import os
import sys
import numpy as np
import pandas as pd

REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
sys.path.insert(0, REPO)
os.chdir(REPO)

from src.data.thermodynamic_sensor_classifier import identify_core_sensor_combined_rank
from src.data.loader import ThermalProfileLoader


def _sensor(n, period, t_base, t_peak, n_pre, rise_samples, plateau, cool_rate):
    pre = np.full(n_pre, t_base)
    rise = np.linspace(t_base, t_peak, rise_samples)
    plat = np.full(plateau, t_peak)
    remaining = n - n_pre - rise_samples - plateau
    drop_per = cool_rate * period
    cur = t_peak
    cool = []
    for _ in range(remaining):
        cur = max(t_base, cur - drop_per)
        cool.append(cur)
    full = np.concatenate([pre, rise, plat, np.array(cool)])
    if len(full) < n:
        full = np.concatenate([full, np.full(n - len(full), t_base)])
    return full[:n]


def build_df(rise, cool):
    n, period, t_base, t_peak, n_pre, plat = 600, 5.0, 30.0, 100.0, 10, 60
    ts = np.arange(n, dtype=float) * period
    df = pd.DataFrame({"Timestamp": ts})
    df["VirtualCoreSensor"] = "T1"
    for s in [f"T{i}" for i in range(1, 9)]:
        df[s] = _sensor(n, period, t_base, t_peak, n_pre,
                        rise[s], plat, cool[s])
    df["VirtualCoreTemperature"] = df["T1"]
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    df["VirtualSurfaceTemperature"] = df["T7"]
    df["VirtualAmbientTemperature"] = df["T8"]
    return df


def scores_for(rise, cool):
    df = build_df(rise, cool)
    sensors = [f"T{i}" for i in range(1, 9)]
    winner, diag = identify_core_sensor_combined_rank(df, sensors)
    scores = {s: diag[s]["combined_score"] for s in sensors}
    return df, winner, scores, diag


def try_override(df, firmware="T1"):
    loader = ThermalProfileLoader()
    loader.metadata = {}
    loader.data = df
    loader.curve_sensor_assignments = {0: {"core": firmware}}
    loader._sensor_overrides = {}
    loader.current_curve_index = 0
    loader._apply_physics_based_core_correction(df, 0)
    ca = loader.curve_sensor_assignments[0]
    return ca.get("core"), ca.get("core_physics_corrected", False)


def main():
    # Gap = 2: make T1 rank (2,2)=score 4, winner rank (1,1)=score 2
    # Create 2 "best" sensors (T4, T5) that split ranks 1 & 2 on each metric
    # Tune so T4 is clear winner, T1 is runner-up
    print("=" * 72)
    print("Constructed fixtures — verify override gate at CONFIDENCE_GAP_MIN=4")
    print("=" * 72)

    # Case A: gap = 2. T4 best, T1 runner-up on BOTH metrics (all others clearly worse)
    # T4 rise 240 (slowest), T1 rise 230 (next slowest); rest fast
    # T4 cool 0.02 (slowest), T1 cool 0.03 (next slowest); rest fast
    rise = {"T1": 230, "T2": 80, "T3": 80, "T4": 240, "T5": 80, "T6": 80, "T7": 80, "T8": 80}
    cool = {"T1": 0.03, "T2": 0.5, "T3": 0.5, "T4": 0.02, "T5": 0.5, "T6": 0.5, "T7": 0.5, "T8": 0.5}
    df, winner, scores, diag = scores_for(rise, cool)
    gap = scores["T1"] - scores[winner]
    print(f"\nA) Firmware T1 score {scores['T1']}, winner {winner} score {scores[winner]}, gap {gap}")
    new_core, corrected = try_override(df)
    print(f"   Override result: core={new_core} corrected={corrected}  "
          f"(expected: no override since gap < 4)")

    # Case B: gap = 3. T4 best, T1 fourth, making T1 score higher
    # T4 rise 240 (rank 1), T2 200 (rank 2), T3 190 (rank 3), T1 180 (rank 4)
    # T4 cool 0.02 (rank 1), T2 0.04 (rank 2), T3 0.06 (rank 3), T1 0.08 (rank 4)
    # T4 score 2, T1 score 8, gap 6 — too large. Let's target gap 3:
    # T4 score 2, T1 score 5 means T1 ranks (3,2) or (2,3). Hard to build with ties.
    # Use: T4 wins both (score 2); T2 is (2,3)=5; T3 (3,2)=5; T1 (4,4)=8 => gap=6 still.
    # Ties ARE permitted — let's try (1,2): T4, T1 tie on cool at rank 1 jointly?
    # Actually competition ranking: T4 0.02, T1 0.03 — no ties.
    # To get gap=3: T1 score 5, winner score 2. With ints only, gap 2,4,6 achievable from score 2.
    # But via ties we can fabricate non-trivial gaps.
    # Simpler: make T4 rank (1,1)=2 via clear lead; T1 rank (2,3)=5.
    # Needed: T1 is runner-up in heat (rise 230) and 3rd in cool (cool 0.04). Need a
    # 3rd sensor that beats T1 in cool.
    rise = {"T1": 230, "T2": 180, "T3": 180, "T4": 240, "T5": 80, "T6": 80, "T7": 80, "T8": 80}
    cool = {"T1": 0.04, "T2": 0.03, "T3": 0.5, "T4": 0.02, "T5": 0.5, "T6": 0.5, "T7": 0.5, "T8": 0.5}
    df, winner, scores, diag = scores_for(rise, cool)
    gap = scores["T1"] - scores[winner]
    print(f"\nB) Firmware T1 score {scores['T1']}, winner {winner} score {scores[winner]}, gap {gap}")
    new_core, corrected = try_override(df)
    print(f"   Override result: core={new_core} corrected={corrected}")

    # Case C: gap = 4 (exact threshold — should fire)
    # T4 score 2; T1 score 6 = (3,3) or (2,4) or (4,2)
    # Build: T4 (1,1)=2; T1 (3,3)=6
    rise = {"T1": 190, "T2": 200, "T3": 210, "T4": 240, "T5": 80, "T6": 80, "T7": 80, "T8": 80}
    cool = {"T1": 0.06, "T2": 0.05, "T3": 0.04, "T4": 0.02, "T5": 0.5, "T6": 0.5, "T7": 0.5, "T8": 0.5}
    df, winner, scores, diag = scores_for(rise, cool)
    print(f"\nC) Firmware T1 score {scores['T1']}, winner {winner} score {scores[winner]}, "
          f"gap {scores['T1'] - scores[winner]}")
    new_core, corrected = try_override(df)
    print(f"   Override result: core={new_core} corrected={corrected}  "
          f"(gap=4 should fire the override)")

    # Case D: gap = 5 — should fire
    rise = {"T1": 170, "T2": 200, "T3": 210, "T4": 240, "T5": 80, "T6": 80, "T7": 80, "T8": 80}
    cool = {"T1": 0.07, "T2": 0.05, "T3": 0.04, "T4": 0.02, "T5": 0.5, "T6": 0.5, "T7": 0.5, "T8": 0.5}
    df, winner, scores, diag = scores_for(rise, cool)
    print(f"\nD) Firmware T1 score {scores['T1']}, winner {winner} score {scores[winner]}, "
          f"gap {scores['T1'] - scores[winner]}")
    new_core, corrected = try_override(df)
    print(f"   Override result: core={new_core} corrected={corrected}")


if __name__ == "__main__":
    main()
