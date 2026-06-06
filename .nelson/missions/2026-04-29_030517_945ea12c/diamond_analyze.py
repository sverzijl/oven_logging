"""HMS Diamond — bake-data sanity check (M19 task 3).

For each of 7 real-CSV fixtures, extract:
  - bake_duration_min
  - surface_max_C / core_max_C
  - core_temp_at_end_C
  - peak_to_end_min

Then generate one annotated PNG of the 1000BA3C_0946 fixture and save:
  diamond-bake-data-sanity.md
  diamond-bake-trace.png
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(
    r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited"
    r"\Dandenong\projects\combustion\oven_logging"
)
MISSION_DIR = REPO_ROOT / ".nelson" / "missions" / "2026-04-29_030517_945ea12c"
sys.path.insert(0, str(REPO_ROOT))

from src.data.loader import ThermalProfileLoader  # noqa: E402

# Fixture spec: (label, file, curve_index, expected_start, expected_end, sample_period_s)
# All real CSVs use 5 s sample period. expected_starts/ends from
# tests/fixtures/curve_boundary_cases.py.
FIXTURES = [
    ("BA3C_0946", "ProbeData_1000BA3C_2025-05-30 09_46_16.csv", 0, 13, 293, 5.0),
    ("BA3C_1759_C0", "ProbeData_1000BA3C_2025-05-30 17_59_37.csv", 0, 13, 293, 5.0),
    ("BA3C_1759_C1", "ProbeData_1000BA3C_2025-05-30 17_59_37.csv", 1, 651, 944, 5.0),
    ("BA3C_1759_C2", "ProbeData_1000BA3C_2025-05-30 17_59_37.csv", 2, 5888, 6185, 5.0),
    ("100098DE_1351", "ProbeData_100098DE_2025-05-30 13_51_07.csv", 0, 3, 306, 5.0),
    ("wonder_white_10k", "wonder white 10k 13.01.2026.csv", 0, 0, 340, 5.0),
    ("post_wonder_meal_20251017", "Post Wonder Meal 20251017.csv", 0, 3, 344, 5.0),
]


def load_fixture(csv_name: str, curve_index: int):
    """Return (loader, curve_df, core_sensor, surface_sensor, sample_period_s)."""
    loader = ThermalProfileLoader()
    df, metadata = loader.load_csv(file_path=str(REPO_ROOT / csv_name))
    sample_period_s = metadata.get("sample_period_s", 5.0)
    # ThermalProfileLoader exposes per-curve frames via all_curves
    all_curves = getattr(loader, "all_curves", None)
    if all_curves is None or len(all_curves) <= curve_index:
        # single-curve fixture; some loaders use loader.data
        curve_df = loader.data
    else:
        curve_df = all_curves[curve_index]
    core_sensor = loader.get_core_sensor(curve_index)
    try:
        surface_sensor = loader.get_surface_sensor(curve_index)
    except Exception:
        surface_sensor = None
    return loader, curve_df, core_sensor, surface_sensor, sample_period_s


def characterise(label: str, csv_name: str, curve_index: int,
                 expected_start: int, expected_end: int, period: float):
    loader, df, core_sensor, surface_sensor, period_loader = load_fixture(
        csv_name, curve_index
    )
    period = period_loader if period_loader else period

    # Slice the bake window. The detected per-curve dataframe is itself a slice
    # of the source CSV (curve start is curve-local idx 0). For consistency with
    # the fixture's expected_starts/ends we re-load the raw CSV and slice on
    # absolute indices for single-curve fixtures, but BA3C_1759 has 3 curves
    # spanning a single CSV — its expected_starts/ends are absolute indices in
    # the raw CSV. Use the raw file to be safe for everything.
    raw = pd.read_csv(str(REPO_ROOT / csv_name), skiprows=10)
    # Drop unnamed phantom columns
    unnamed = [c for c in raw.columns if c.startswith("Unnamed:")]
    if unnamed:
        raw = raw.drop(columns=unnamed)
    # Drop trailing NaN rows (wonder white has them)
    if "VirtualCoreTemperature" in raw.columns:
        raw = raw.dropna(subset=["VirtualCoreTemperature"]).reset_index(drop=True)

    bake = raw.iloc[expected_start:expected_end + 1].reset_index(drop=True)

    # Core / surface readings
    core_col = core_sensor if core_sensor in bake.columns else "VirtualCoreTemperature"
    if surface_sensor and surface_sensor in bake.columns:
        surf_col = surface_sensor
    elif "VirtualSurfaceTemperature" in bake.columns:
        surf_col = "VirtualSurfaceTemperature"
    else:
        surf_col = None

    core_series = bake[core_col].astype(float)
    core_max = float(core_series.max())
    core_at_end = float(core_series.iloc[-1])
    peak_idx_local = int(core_series.idxmax())
    n_samples = len(bake)
    duration_s = (expected_end - expected_start) * period
    peak_to_end_s = (n_samples - 1 - peak_idx_local) * period
    surface_max = (
        float(bake[surf_col].astype(float).max()) if surf_col else float("nan")
    )

    return {
        "label": label,
        "csv": csv_name,
        "curve_index": curve_index,
        "expected_start": expected_start,
        "expected_end": expected_end,
        "period_s": period,
        "n_samples": n_samples,
        "duration_min": duration_s / 60.0,
        "core_sensor": core_col,
        "surface_sensor": surf_col,
        "core_max_C": core_max,
        "surface_max_C": surface_max,
        "core_at_end_C": core_at_end,
        "peak_to_end_min": peak_to_end_s / 60.0,
        "raw_df": raw,
        "bake_df": bake,
    }


def annotated_png(result: dict, out_path: Path):
    raw = result["raw_df"]
    period = result["period_s"]
    start = result["expected_start"]
    end = result["expected_end"]
    duration_min = result["duration_min"]
    core_sensor = result["core_sensor"]
    surface_sensor = result["surface_sensor"]

    t_min = np.arange(len(raw)) * period / 60.0

    fig, ax = plt.subplots(figsize=(11, 6.5))
    sensors = [f"T{i}" for i in range(1, 9)]
    cmap = plt.get_cmap("tab10")
    for i, s in enumerate(sensors):
        if s not in raw.columns:
            continue
        is_core = (s == core_sensor)
        is_surface = (s == surface_sensor)
        lw = 2.2 if is_core else (1.8 if is_surface else 1.0)
        ls = "-" if is_core else ("--" if is_surface else ":")
        label = s
        if is_core:
            label += " (core)"
        elif is_surface:
            label += " (surface)"
        ax.plot(t_min, raw[s].astype(float), color=cmap(i), linewidth=lw,
                linestyle=ls, label=label, alpha=0.95 if is_core else 0.8)

    ax.axvline(t_min[start], color="green", linewidth=1.5, linestyle="-",
               label=f"expected_start (idx {start})")
    ax.axvline(t_min[end], color="red", linewidth=1.5, linestyle="-",
               label=f"expected_end (idx {end})")
    ax.axhline(100, color="black", linestyle="--", linewidth=1.0, alpha=0.6,
               label="100 °C (latent-heat plateau)")
    ax.axhline(95, color="purple", linestyle=":", linewidth=1.0, alpha=0.7,
               label="95 °C (target core)")

    ax.set_title(
        f"BA3C_0946 — annotated bake trace\n"
        f"bake_duration = {duration_min:.2f} min "
        f"(expected_start={start}, expected_end={end}, period={period:.1f} s)"
    )
    ax.set_xlabel("time (min)")
    ax.set_ylabel("temperature (°C)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(str(out_path), dpi=140)
    plt.close(fig)


def main():
    results = []
    for label, csv_name, ci, s, e, p in FIXTURES:
        try:
            r = characterise(label, csv_name, ci, s, e, p)
            results.append(r)
            print(f"{label:30s}  dur={r['duration_min']:6.2f} min  "
                  f"core_max={r['core_max_C']:6.2f}  "
                  f"core_at_end={r['core_at_end_C']:6.2f}  "
                  f"peak_to_end={r['peak_to_end_min']:5.2f} min  "
                  f"surf_max={r['surface_max_C']:6.2f}")
        except Exception as exc:
            print(f"{label}: FAIL {exc!r}")
            raise

    # Annotated PNG for BA3C_0946
    ba3c_0946 = next(r for r in results if r["label"] == "BA3C_0946")
    png_path = MISSION_DIR / "diamond-bake-trace.png"
    annotated_png(ba3c_0946, png_path)
    print(f"PNG written: {png_path}")

    # Markdown report
    md = MISSION_DIR / "diamond-bake-data-sanity.md"
    rows = []
    for r in results:
        rows.append(
            f"| {r['label']} | {r['duration_min']:.2f} | "
            f"{r['surface_max_C']:.2f} | {r['core_max_C']:.2f} | "
            f"{r['core_at_end_C']:.2f} | {r['peak_to_end_min']:.2f} | "
            f"{r['core_sensor']} | {r['surface_sensor']} |"
        )

    durations = [r["duration_min"] for r in results]
    cores_at_end = [r["core_at_end_C"] for r in results]
    core_max_vals = [r["core_max_C"] for r in results]

    in_target = [22.0 <= d <= 25.0 for d in durations]
    n_in = sum(in_target)
    incomplete = [r for r in results if r["core_at_end_C"] < 95.0
                  or r["core_max_C"] < 95.0]

    summary_lines = [
        "# HMS Diamond — bake-data sanity check (M19 task 3)",
        "",
        "## Per-fixture characterisation",
        "",
        "| fixture | duration (min) | surface_max (°C) | core_max (°C) | "
        "core_at_end (°C) | peak_to_end (min) | core_sensor | surface_sensor |",
        "|---|---:|---:|---:|---:|---:|---|---|",
        *rows,
        "",
        "Notes",
        "- All fixtures sampled at 5.0 s/sample (CSV header `Sample Period: 5000` ms).",
        "- `expected_start` / `expected_end` taken from "
        "`tests/fixtures/curve_boundary_cases.py` (M2a curve-detector ground truth).",
        "- `core_sensor` / `surface_sensor` taken from `ThermalProfileLoader`'s M2a "
        "spatial-reconstruction classifier (per-curve).",
        "- `peak_to_end_min` measures the cool-down phase length inside the "
        "detector-defined bake window: (expected_end − argmax(core)) × period.",
        "",
        "## Verdict",
        "",
        f"- Mean duration: **{np.mean(durations):.2f} min** "
        f"(σ={np.std(durations):.2f}, range "
        f"{min(durations):.2f}–{max(durations):.2f} min).",
        f"- {n_in}/{len(results)} fixtures fall inside the user-stated "
        f"22–25 min target band.",
        f"- Mean core temperature at end: "
        f"**{np.mean(cores_at_end):.2f} °C** "
        f"(range {min(cores_at_end):.2f}–{max(cores_at_end):.2f} °C).",
        f"- Mean core peak: **{np.mean(core_max_vals):.2f} °C** "
        f"(range {min(core_max_vals):.2f}–{max(core_max_vals):.2f} °C).",
        "",
    ]

    md.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"Markdown written: {md}")

    return results


if __name__ == "__main__":
    main()
