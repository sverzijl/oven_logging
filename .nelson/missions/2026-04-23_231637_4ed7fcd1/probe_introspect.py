"""Introspection: run classifier on all 6 core-sensor fixture cases, emit diagnostics.

Also traces common_peak_idx, heat-only fallback flag, and whether the integration
gate (CONFIDENCE_GAP_MIN=4) fires.
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
from tests.fixtures.curve_boundary_cases import CASES, _REAL_CSVS
from config.constants import CORE_DETECTION_CONFIG


def classify_synthetic(name):
    case = next(c for c in CASES if c["name"] == name)
    df = case["df"]
    sensors = [f"T{i}" for i in range(1, 9) if f"T{i}" in df.columns]
    winner, diag = identify_core_sensor_combined_rank(df, sensors)
    ts = df["Timestamp"].to_numpy()
    dt = float(np.median(np.diff(ts))) if len(ts) >= 2 else 5.0
    cool_window_samples = max(1, int(round(CORE_DETECTION_CONFIG["COOL_WINDOW_SECONDS"] / dt)))
    peak_idx = diag[winner]["common_peak_idx"] if winner else None
    cool_sample_idx = peak_idx + cool_window_samples if peak_idx is not None else None
    cool_available = cool_sample_idx is not None and cool_sample_idx < len(df)
    return {
        "name": name,
        "winner": winner,
        "diag": diag,
        "common_peak_idx": peak_idx,
        "n": len(df),
        "dt": dt,
        "cool_window_samples": cool_window_samples,
        "cool_sample_idx": cool_sample_idx,
        "cool_available": cool_available,
        "expected_core": case.get("expected_core_sensor"),
    }


def classify_real_via_loader(name, path):
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=path)
    resolved = loader.get_core_sensor(curve_index=0)
    ca = loader.curve_sensor_assignments.get(0, {})
    diag = ca.get("core_detection_diagnostics", {})
    # Find classifier's winner too
    df = loader.data  # post-curve-slice
    sensors = [f"T{i}" for i in range(1, 9) if f"T{i}" in df.columns]
    winner, _ = identify_core_sensor_combined_rank(df, sensors)
    ts = df["Timestamp"].to_numpy() if "Timestamp" in df.columns else None
    if ts is not None and len(ts) >= 2:
        dt = float(np.median(np.diff(ts)))
    else:
        dt = 5.0
    cool_window_samples = max(1, int(round(CORE_DETECTION_CONFIG["COOL_WINDOW_SECONDS"] / dt)))
    peak_idx = diag[winner]["common_peak_idx"] if winner and winner in diag else None
    cool_sample_idx = peak_idx + cool_window_samples if peak_idx is not None else None
    cool_available = cool_sample_idx is not None and cool_sample_idx < len(df)
    return {
        "name": name,
        "resolved_core": resolved,
        "classifier_winner": winner,
        "firmware_core": ca.get("firmware_core_sensor") or ca.get("core"),
        "core_physics_corrected": ca.get("core_physics_corrected", False),
        "diag": diag,
        "common_peak_idx": peak_idx,
        "n": len(df),
        "dt": dt,
        "cool_window_samples": cool_window_samples,
        "cool_sample_idx": cool_sample_idx,
        "cool_available": cool_available,
    }


def pretty(entry):
    print(f"=== {entry['name']} ===")
    print(f"  n={entry['n']} dt={entry['dt']}s cool_window_samples={entry['cool_window_samples']}")
    print(f"  common_peak_idx={entry['common_peak_idx']} cool_sample_idx={entry['cool_sample_idx']}")
    print(f"  cool_available={entry['cool_available']}  (False => heat-only fallback)")
    if "resolved_core" in entry:
        print(f"  resolved_core={entry['resolved_core']}  "
              f"classifier_winner={entry['classifier_winner']}  "
              f"firmware={entry['firmware_core']}  "
              f"core_physics_corrected={entry['core_physics_corrected']}")
    else:
        print(f"  winner={entry['winner']}  expected={entry['expected_core']}")
    diag = entry["diag"]
    if diag:
        print("  ladder (heat_rank, cool_rank, combined):")
        for s, d in sorted(diag.items(), key=lambda kv: kv[1]["combined_score"]):
            t = d.get("time_to_heat_threshold_s")
            r = d.get("retained_c_at_cool_window")
            print(f"    {s}: h{d['heat_rank']} c{d['cool_rank']} = {d['combined_score']}  "
                  f"(t80s={t} retain={r})")
    print()


def main():
    # Synthetic
    for name in ["core_sensor_unambiguous", "core_sensor_disagreeing_metrics"]:
        pretty(classify_synthetic(name))

    # Real via loader (integration path)
    for name, path in [
        ("real_100098DE_1351", _REAL_CSVS["100098DE_1351"]),
        ("real_1000BA3C_0946", _REAL_CSVS["1000BA3C_0946"]),
        ("real_1000BA3C_1759", _REAL_CSVS["1000BA3C_1759"]),
        ("wonder_white_10k", _REAL_CSVS["wonder_white_10k"]),
    ]:
        pretty(classify_real_via_loader(name, path))


if __name__ == "__main__":
    main()
