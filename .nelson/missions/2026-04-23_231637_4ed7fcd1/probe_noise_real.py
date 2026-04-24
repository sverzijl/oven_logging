"""Add gaussian noise to the 3 real unlidded CSVs and re-run the classifier.

Does the combined-rank gap on any of them cross threshold=4 and cause a flip?
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
from tests.fixtures.curve_boundary_cases import _REAL_CSVS


def load_and_slice(path):
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=path)
    return loader.data.copy()


def perturb_and_run(df_base, seed, sigma):
    rng = np.random.default_rng(seed)
    df = df_base.copy()
    for s in [f"T{i}" for i in range(1, 9) if f"T{i}" in df.columns]:
        df[s] = df[s] + rng.normal(0.0, sigma, len(df))
    sensors = [f"T{i}" for i in range(1, 9) if f"T{i}" in df.columns]
    winner, diag = identify_core_sensor_combined_rank(df, sensors)
    if winner is None:
        return None, None, None
    return winner, diag, {s: diag[s]["combined_score"] for s in sensors}


def analyze(name, path, firmware_expected):
    df = load_and_slice(path)
    sensors = [f"T{i}" for i in range(1, 9) if f"T{i}" in df.columns]
    baseline_winner, baseline_diag = identify_core_sensor_combined_rank(df, sensors)
    baseline_scores = {s: baseline_diag[s]["combined_score"] for s in sensors}
    print(f"\n=== {name} ===  firmware expected = {firmware_expected}")
    print(f"  baseline winner={baseline_winner}  firmware score={baseline_scores[firmware_expected]}  "
          f"gap={baseline_scores[firmware_expected] - baseline_scores[baseline_winner]}")

    for sigma in [0.5, 1.0, 2.0]:
        winners = []
        gaps = []
        for seed in range(100):
            w, _, sc = perturb_and_run(df, seed, sigma)
            if w is None:
                continue
            winners.append(w)
            gaps.append(sc[firmware_expected] - sc[w])
        counts = pd.Series(winners).value_counts()
        gaps_a = np.array(gaps)
        would_flip = (gaps_a >= 4).sum()
        top = counts.idxmax()
        print(f"  σ={sigma}:  winners dist: {dict(counts)} — top={top}")
        print(f"    gap vs firmware: min {gaps_a.min()}  median {int(np.median(gaps_a))}  "
              f"p95 {int(np.percentile(gaps_a, 95))}  max {gaps_a.max()}")
        print(f"    #seeds where gap>=4 (would flip): {would_flip}/100")


if __name__ == "__main__":
    analyze("real_100098DE_1351", _REAL_CSVS["100098DE_1351"], "T4")
    analyze("real_1000BA3C_0946", _REAL_CSVS["1000BA3C_0946"], "T1")
    analyze("real_1000BA3C_1759", _REAL_CSVS["1000BA3C_1759"], "T1")
