"""Inspect the wonder-white integration path — loader-sliced df and classifier behaviour.

Briefing says heat-only fallback fires because cool window extends past EOF.
Verify and check whether the synthetic disagreeing_metrics fixture accidentally
triggers heat-only fallback.
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
from tests.fixtures.curve_boundary_cases import load_wonder_white, CASES
from config.constants import CORE_DETECTION_CONFIG


def inspect_synthetic_disagreeing():
    case = next(c for c in CASES if c["name"] == "core_sensor_disagreeing_metrics")
    df = case["df"]
    print("-" * 72)
    print(f"core_sensor_disagreeing_metrics: n={len(df)}")
    sensors = [f"T{i}" for i in range(1, 9)]
    winner, diag = identify_core_sensor_combined_rank(df, sensors)
    peak_idx = diag[sensors[0]]["common_peak_idx"]
    ts = df["Timestamp"].to_numpy()
    dt = float(np.median(np.diff(ts)))
    cool_window_samples = max(1, int(round(60 / dt)))
    cool_sample_idx = peak_idx + cool_window_samples
    print(f"  common_peak_idx = {peak_idx}")
    print(f"  cool_window_samples = {cool_window_samples}")
    print(f"  cool_sample_idx = {cool_sample_idx}")
    print(f"  cool_available = {cool_sample_idx < len(df)}   (False => heat-only fallback)")
    print(f"  winner={winner}")
    print("  If heat-only fallback fired, T5 (slowest heat) would win — instead T6 "
          "wins in combined mode. Verify:")
    for s in ["T5", "T6", "T7"]:
        d = diag[s]
        print(f"    {s}: heat_rank={d['heat_rank']} cool_rank={d['cool_rank']} "
              f"combined={d['combined_score']}")


def inspect_wonder_white():
    print("-" * 72)
    # Raw CSV first
    raw = load_wonder_white()
    print(f"wonder_white raw n={len(raw)}")
    # Now via loader
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=os.path.join(REPO, "wonder white 10k 13.01.2026.csv"))
    print(f"loader.data n={len(loader.data)}  (post-curve-slice for curve 0)")
    df = loader.data
    sensors = [f"T{i}" for i in range(1, 9) if f"T{i}" in df.columns]
    winner, diag = identify_core_sensor_combined_rank(df, sensors)
    peak_idx = diag[winner]["common_peak_idx"]
    ts = df["Timestamp"].to_numpy()
    dt = float(np.median(np.diff(ts)))
    cool_window_samples = max(1, int(round(60 / dt)))
    cool_sample_idx = peak_idx + cool_window_samples
    print(f"  dt={dt} cool_window_samples={cool_window_samples}")
    print(f"  common_peak_idx={peak_idx}   cool_sample_idx={cool_sample_idx}")
    print(f"  cool_available = {cool_sample_idx < len(df)}")
    print(f"  loader-sliced EOF={len(df) - 1}   peak_idx_to_eof_gap={len(df) - 1 - peak_idx}")

    # Without loader slicing — if the caller passes the raw df (before curve boundary
    # trimming), is the cool window available?
    winner2, diag2 = identify_core_sensor_combined_rank(
        raw, [f"T{i}" for i in range(1, 9)]
    )
    peak_idx2 = diag2[winner2]["common_peak_idx"]
    cool_sample_idx2 = peak_idx2 + cool_window_samples
    print(f"  raw (non-sliced): common_peak_idx={peak_idx2}  cool_sample_idx={cool_sample_idx2}")
    print(f"    cool_available(raw) = {cool_sample_idx2 < len(raw)}")
    print(f"    raw EOF={len(raw) - 1}   peak_idx_to_eof_gap={len(raw) - 1 - peak_idx2}")


if __name__ == "__main__":
    inspect_synthetic_disagreeing()
    inspect_wonder_white()
