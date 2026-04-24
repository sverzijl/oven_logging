"""Q1 — What is the BA3C_1759 j=293 cliff, really?

Dump raw samples j=280..310 with Timestamp, core temp, PredictionState, and
raw T1..T8.  Dragon claims this is a probe-insertion artifact; verify.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import numpy as np
from src.data.loader import ThermalProfileLoader
from src.data.column_helpers import resolve_core_temperature_series

CSV = Path(__file__).resolve().parents[3] / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"

df = pd.read_csv(str(CSV), skiprows=10)
print(f"n rows: {len(df)}")
print(f"columns: {list(df.columns)[:20]}")

temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
ts = df["Timestamp"].to_numpy(dtype=float)
pred = df["PredictionState"].to_numpy() if "PredictionState" in df.columns else None

print("\n=== j=280..310 dump ===")
print(f"{'j':>4} {'t_s':>8} {'core':>7} {'pred':<22}", end="")
for col in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]:
    if col in df.columns:
        print(f" {col:>6}", end="")
print(f" {'VCS':>4}", end="")
print()
for j in range(280, 311):
    print(f"{j:>4} {ts[j]:>8.1f} {temps[j]:>7.2f} {str(pred[j] if pred is not None else '-'):<22}", end="")
    for col in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]:
        if col in df.columns:
            print(f" {df[col].iloc[j]:>6.2f}", end="")
    vcs = df["VirtualCoreSensor"].iloc[j] if "VirtualCoreSensor" in df.columns else "-"
    print(f" {str(vcs):>4}", end="")
    print()

# Where is the real bake peak?
print("\n=== Running peak up to j=1200 ===")
peak_idx = 0
peak_val = -1e9
for j in range(0, min(1200, len(df))):
    if temps[j] > peak_val:
        peak_val = float(temps[j])
        peak_idx = j
print(f"running peak at j=1200 is idx={peak_idx}, temp={peak_val:.2f}")

print("\n=== Samples around j=940..960 (real bake-1 end) ===")
for j in range(935, 965):
    print(f"j={j:>4} t={ts[j]:>8.1f} core={temps[j]:>7.2f} pred={str(pred[j] if pred is not None else '-'):<22}")

print("\n=== Q1 summary ===")
print(f"drop at j=293: {temps[293]:.2f} -> {temps[294]:.2f} = {temps[293]-temps[294]:.2f} C")
print(f"followup j=294..299: {[f'{temps[k]:.2f}' for k in range(293, 300)]}")
print(f"running peak at j=293: {max(temps[:294]):.2f} at j={int(np.argmax(temps[:294]))}")
print(f"running peak at j=944: {max(temps[:945]):.2f} at j={int(np.argmax(temps[:945]))}")
