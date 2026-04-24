"""Perturb synthetic fixtures with shortened/lengthened plateaus — find the exact
margin where cliff stops/starts firing.

Synthetic cliff fixture: plateau length 240..300..320 → cliff at 300→301 (20 °C).
We mutate plateau length to determine min plateau samples at which cliff fires.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from config import constants  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402


def build(rise_n: int, plateau_n: int, cliff_mag: float = 20.0, tail_n: int = 100, period: float = 5.0,
          plateau_peak_final: float = 96.0, rise_start: float = 30.0, rise_peak: float = 95.0):
    """Synthetic analog of cliff fixture with tunable plateau_n.

    Plateau creep: rise_peak..plateau_peak_final linearly over plateau_n samples.
    Cliff = one-sample drop of cliff_mag after plateau; tail monotonically decreases
    and then a small random tail.
    """
    rise = np.linspace(rise_start, rise_peak, rise_n)
    # Plateau: continues to rise slowly to plateau_peak_final
    plateau = np.linspace(rise_peak, plateau_peak_final, plateau_n + 1)[1:]  # plateau_n samples
    # Decline after cliff
    cliff_top = plateau[-1]
    cliff_bot = cliff_top - cliff_mag
    decline = np.linspace(cliff_bot, cliff_bot - 35.0, 40)  # 40 samples of monotonic decline
    tail = np.full(tail_n, 30.0) + np.random.default_rng(7).normal(0, 0.2, tail_n)
    vct = np.concatenate([rise, plateau, decline, tail])
    ts = np.arange(len(vct)) * period
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
    return df, rise_n, rise_n + plateau_n  # peak_idx, cliff_idx


def main():
    cfg = dict(constants.CURVE_DETECTION_CONFIG)
    threshold_s = cfg["CLIFF_PRE_PEAK_PLATEAU_SECONDS"]
    print(f"Current threshold: {threshold_s}s at 5s/sample → {threshold_s / 5:.0f} samples")
    print(f"\n{'plateau_n':>10} {'plateau_s':>10} {'expected_end':>13} {'actual_end':>11} {'truncated':>10}")
    for plat_n in (30, 40, 48, 49, 50, 51, 52, 55, 60, 65, 70):
        df, peak_idx, cliff_idx = build(rise_n=240, plateau_n=plat_n)
        det = CurveBoundaryDetector(cfg)
        curves = det.extract_curves(df)
        end = curves[0]["end_idx"] if curves else None
        trunc = curves[0]["truncated"] if curves else None
        print(f"{plat_n:>10} {plat_n * 5:>10} {cliff_idx:>13} {str(end):>11} {str(trunc):>10}")

    # 15 °C cliff threshold: exactly 15.0 °C drop
    print(f"\n\n--- cliff magnitude sweep (plat_n=65, 325s) ---")
    print(f"{'cliff_mag':>10} {'end':>6} {'trunc':>6}")
    for cmag in (14.0, 14.9, 15.0, 15.1, 16.0, 20.0, 30.0):
        df, peak_idx, cliff_idx = build(rise_n=240, plateau_n=65, cliff_mag=cmag)
        det = CurveBoundaryDetector(cfg)
        curves = det.extract_curves(df)
        end = curves[0]["end_idx"] if curves else None
        trunc = curves[0]["truncated"] if curves else None
        print(f"{cmag:>10} {str(end):>6} {str(trunc):>6}")

    # Monotonicity break: inject a bump in the decline
    print(f"\n--- inject a bump in the decline — does cliff still fire? ---")
    for bump_offset, bump_mag in [(1, 0.0), (2, 0.0), (1, 0.1), (2, 0.5), (3, 1.0), (5, 2.0)]:
        df, peak_idx, cliff_idx = build(rise_n=240, plateau_n=65)
        # decline starts at cliff_idx+1
        if cliff_idx + bump_offset < len(df):
            df.loc[cliff_idx + bump_offset, "VirtualCoreTemperature"] += bump_mag
            df.loc[cliff_idx + bump_offset, "CoreTemperature"] += bump_mag
        det = CurveBoundaryDetector(cfg)
        curves = det.extract_curves(df)
        end = curves[0]["end_idx"] if curves else None
        trunc = curves[0]["truncated"] if curves else None
        print(f"  bump_offset={bump_offset} mag={bump_mag:.2f}: end={end} trunc={trunc}")


if __name__ == "__main__":
    main()
