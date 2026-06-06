"""Empirical diagnostic for the M23 HMS Drake temporal classifier wrapper.

Standalone script (NOT a pytest collection — leading underscore filename).
Loads BA3C_0946 via ``ThermalProfileLoader``, runs ``classify_temporal`` with
default settings, generates a 4-panel matplotlib PNG with the ``Agg`` backend,
and prints summary statistics to stdout.

Usage:
    python tests/_diagnose_temporal_BA3C.py

PNG output:
    .nelson/missions/2026-04-29_090640_f657208a/temporal-traces-BA3C_0946.png
"""

from __future__ import annotations

import os
import sys
import time

import matplotlib
matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.data.loader import ThermalProfileLoader  # noqa: E402
from src.data.spatial_reconstruction.temporal import classify_temporal  # noqa: E402

_BA3C_0946_CSV = os.path.join(
    REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
)
_PNG_OUT = os.path.join(
    REPO_ROOT,
    ".nelson",
    "missions",
    "2026-04-29_090640_f657208a",
    "temporal-traces-BA3C_0946.png",
)


def _confidence_color(conf: str) -> str:
    return {"high": "#2ca02c", "medium": "#ff7f0e", "low": "#d62728"}.get(
        conf, "#7f7f7f"
    )


def main() -> int:
    if not os.path.exists(_BA3C_0946_CSV):
        print(f"FATAL: CSV not found: {_BA3C_0946_CSV}", file=sys.stderr)
        return 2

    print(f"Loading {_BA3C_0946_CSV} ...")
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=_BA3C_0946_CSV)
    if not loader.all_curves:
        print("FATAL: no curves detected", file=sys.stderr)
        return 2
    df_curve = loader.all_curves[0]["data"]
    sample_period_ms = int(loader.metadata.get("sample_period_ms", 5000))
    print(
        f"  curve 0: {len(df_curve)} samples, "
        f"sample period {sample_period_ms} ms"
    )

    t0 = time.perf_counter()
    result = classify_temporal(
        df_curve,
        sample_period_ms=sample_period_ms,
        stride_seconds=30.0,
        smoothing_window_seconds=120.0,
        smoothing_polyorder=2,
    )
    t1 = time.perf_counter()
    print(f"classify_temporal wall time: {t1 - t0:.2f} s")
    print(f"  n_strides: {result.t_grid_s.size}")

    # ------------------------------------------------------------------
    # Summary stats
    # ------------------------------------------------------------------
    bake_minutes = float(result.t_grid_s[-1]) / 60.0 if result.t_grid_s.size else 0.0
    x_core_finite = result.x_core_t[np.isfinite(result.x_core_t)]
    x_core_mean = float(np.mean(x_core_finite)) if x_core_finite.size else float("nan")
    x_core_std = float(np.std(x_core_finite)) if x_core_finite.size else float("nan")
    # late-bake (last-quarter) std — the physically meaningful "stability" measure
    if result.t_grid_s.size >= 4:
        q_idx = 3 * result.t_grid_s.size // 4
        x_core_late = result.x_core_t[q_idx:]
        x_core_late = x_core_late[np.isfinite(x_core_late)]
        x_core_late_std = (
            float(np.std(x_core_late)) if x_core_late.size else float("nan")
        )
    else:
        x_core_late_std = float("nan")

    front_finite_mask = np.isfinite(result.x_stefan_front_t)
    front = result.x_stefan_front_t[front_finite_mask]
    front_t = result.t_grid_s[front_finite_mask]
    if front.size >= 2:
        front_start = float(front[0])
        front_end = float(front[-1])
        # Monotone-decreasing trend test
        front_monotone = bool(front_end <= front_start)
        front_t_start = float(front_t[0]) / 60.0
        front_t_end = float(front_t[-1]) / 60.0
    else:
        front_start = front_end = float("nan")
        front_monotone = False
        front_t_start = front_t_end = float("nan")

    surface_finite = result.x_surface_t[np.isfinite(result.x_surface_t)]
    x_surface_mean = (
        float(np.mean(surface_finite)) if surface_finite.size else float("nan")
    )
    x_surface_std = (
        float(np.std(surface_finite)) if surface_finite.size else float("nan")
    )

    print("\n=== summary statistics ===")
    print(f"  bake duration       : {bake_minutes:.2f} min")
    print(f"  x_core mean / std   : {x_core_mean:.4f} / {x_core_std:.4f}")
    print(f"  x_core late-bake std: {x_core_late_std:.4f}  (target < 0.05)")
    print(
        f"  x_stefan_front      : {front_start:.4f} -> {front_end:.4f}  "
        f"({front_t_start:.1f} -> {front_t_end:.1f} min)"
    )
    print(f"  Stefan monotone-↓   : {front_monotone}")
    print(f"  x_surface mean / std: {x_surface_mean:.4f} / {x_surface_std:.4f}")

    # ------------------------------------------------------------------
    # Plotting
    # ------------------------------------------------------------------
    os.makedirs(os.path.dirname(_PNG_OUT), exist_ok=True)
    fig, axes = plt.subplots(4, 1, figsize=(10, 14), sharex=True)
    t_min = result.t_grid_s / 60.0

    # Panel 1: 8 sensor temperatures over time.
    ax = axes[0]
    sensor_t_min = (
        np.arange(len(df_curve)) * sample_period_ms / 1000.0 / 60.0
    )
    palette = plt.get_cmap("turbo")
    for i in range(1, 9):
        col = f"T{i}"
        if col in df_curve.columns:
            ax.plot(
                sensor_t_min,
                df_curve[col].to_numpy(),
                label=col,
                color=palette(0.05 + 0.9 * (i - 1) / 7.0),
                lw=1.0,
            )
    ax.set_ylabel("Sensor T (°C)")
    ax.set_title("Panel 1 — 8 raw sensors (T1..T8) over the bake")
    ax.legend(loc="lower right", ncol=4, fontsize=8, frameon=False)
    ax.grid(alpha=0.3)

    # Panel 2: x_core_t with confidence band.
    ax = axes[1]
    ax.plot(
        t_min, result.x_core_t_raw, "o", ms=3, color="#888", alpha=0.45,
        label="x_core (raw)",
    )
    ax.plot(t_min, result.x_core_t, "-", color="#1f77b4", lw=2.0, label="x_core (smoothed)")
    # Confidence-coloured dots on the smoothed line
    for i in range(result.t_grid_s.size):
        if np.isfinite(result.x_core_t[i]):
            ax.scatter(
                t_min[i], result.x_core_t[i], s=18,
                color=_confidence_color(result.confidence_t[i]),
                edgecolors="black", linewidths=0.3, zorder=5,
            )
    ax.set_ylabel("x_core (normalised)")
    ax.set_title("Panel 2 — Inferred core position (raw + smoothed); dot color = per-snapshot confidence")
    ax.set_ylim(-0.15, 1.05)
    ax.axhline(0.0, color="k", lw=0.5, alpha=0.5)
    ax.axhline(1.0, color="k", lw=0.5, alpha=0.5)
    ax.grid(alpha=0.3)
    # Synthetic legend
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], color="#1f77b4", lw=2.0, label="x_core (smoothed)"),
        Line2D([0], [0], marker="o", linestyle="", color="#888",
               label="x_core (raw)"),
        Line2D([0], [0], marker="o", linestyle="", color=_confidence_color("high"),
               label="conf=high"),
        Line2D([0], [0], marker="o", linestyle="", color=_confidence_color("medium"),
               label="conf=medium"),
        Line2D([0], [0], marker="o", linestyle="", color=_confidence_color("low"),
               label="conf=low"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8, frameon=False)

    # Panel 3: x_surface and x_stefan_front over time, raw + smoothed.
    ax = axes[2]
    ax.plot(t_min, result.x_surface_t_raw, "s", ms=3, color="#999", alpha=0.4,
            label="x_surface (raw)")
    ax.plot(t_min, result.x_surface_t, "-", color="#d62728", lw=2.0, label="x_surface (smoothed)")
    ax.plot(t_min, result.x_stefan_front_t_raw, "^", ms=3, color="#aac",
            alpha=0.4, label="x_stefan_front (raw)")
    ax.plot(t_min, result.x_stefan_front_t, "-", color="#9467bd", lw=2.0,
            label="x_stefan_front (smoothed)")
    ax.set_ylabel("Position (normalised)")
    ax.set_title("Panel 3 — Surface and Stefan-front (100 °C) positions over time")
    ax.set_ylim(-0.05, 1.05)
    ax.axhline(0.0, color="k", lw=0.5, alpha=0.5)
    ax.axhline(1.0, color="k", lw=0.5, alpha=0.5)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8, frameon=False)

    # Panel 4: T_core and T_surface over time.
    ax = axes[3]
    ax.plot(t_min, result.T_core_t, "-", color="#1f77b4", lw=2.0,
            label="T_core (interp)")
    ax.plot(t_min, result.T_surface_t, "-", color="#d62728", lw=2.0,
            label="T_surface (interp)")
    ax.axhline(100.0, color="grey", lw=0.5, ls="--", alpha=0.6)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title("Panel 4 — Interpolated core / surface temperatures over time")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=8, frameon=False)

    fig.suptitle(
        "BA3C_0946 — temporal-classifier traces (M23 HMS Drake)",
        y=0.995, fontsize=13, weight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(_PNG_OUT, dpi=140)
    print(f"\nPNG written to: {_PNG_OUT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
