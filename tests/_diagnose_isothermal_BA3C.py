"""Empirical diagnostic for the M24 HMS Foxhound isothermal tracker.

Standalone script (NOT pytest collected — leading underscore filename).
Loads BA3C_0946 via ``ThermalProfileLoader``, runs ``track_isothermal``,
generates a 4-panel matplotlib PNG with the ``Agg`` backend, saves the
underlying assignment data to JSON, and prints a summary table to stdout.

Usage:
    python tests/_diagnose_isothermal_BA3C.py

PNG output:
    .nelson/missions/2026-04-29_092737_9b83d7ba/isothermal-traces-BA3C_0946.png
JSON output:
    .nelson/missions/2026-04-29_092737_9b83d7ba/isothermal-data-BA3C_0946.json
"""

from __future__ import annotations

import json
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
from src.data.spatial_reconstruction.isothermal import (  # noqa: E402
    track_isothermal,
)


_BA3C_0946_CSV = os.path.join(
    REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
)
_MISSION_DIR = os.path.join(
    REPO_ROOT,
    ".nelson",
    "missions",
    "2026-04-29_092737_9b83d7ba",
)
_PNG_OUT = os.path.join(_MISSION_DIR, "isothermal-traces-BA3C_0946.png")
_JSON_OUT = os.path.join(_MISSION_DIR, "isothermal-data-BA3C_0946.json")


_ISOTHERM_COLOURS = {
    60.0: "#2ca02c",   # green — yeast-kill
    80.0: "#ff7f0e",   # orange — starch gelatinisation
    100.0: "#d62728",  # red — Stefan front (boiling)
    110.0: "#9467bd",  # purple — crust formation
}


def _format_time_range(t_grid_s: np.ndarray, mask: np.ndarray) -> str:
    """Return 'first_min .. last_min' for the masked region."""
    if not mask.any():
        return "(never)"
    valid_t = t_grid_s[mask] / 60.0
    return f"{valid_t[0]:.2f} .. {valid_t[-1]:.2f} min"


def _format_position_range(arr: np.ndarray) -> str:
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return "(no finite)"
    return f"x={float(finite.min()):.3f} .. {float(finite.max()):.3f}"


def _to_serialisable(arr: np.ndarray) -> list:
    """Convert numpy array to JSON-safe list (NaN -> None)."""
    return [None if not np.isfinite(v) else float(v) for v in arr]


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

    isotherms = (60.0, 80.0, 100.0, 110.0)
    t0 = time.perf_counter()
    result = track_isothermal(
        df_curve,
        sample_period_ms=sample_period_ms,
        isotherms_C=isotherms,
        stride_seconds=30.0,
        smoothing_window_seconds=120.0,
        smoothing_polyorder=2,
    )
    t1 = time.perf_counter()
    print(f"track_isothermal wall time: {t1 - t0:.2f} s")
    print(f"  n_strides: {result.t_grid_s.size}")

    # ------------------------------------------------------------------
    # Summary stats
    # ------------------------------------------------------------------
    bake_minutes = (
        float(result.t_grid_s[-1]) / 60.0 if result.t_grid_s.size else 0.0
    )

    print("\n=== isothermal summary ===")
    print(f"  bake duration       : {bake_minutes:.2f} min")
    print(
        f"  fixed core_x        : {result.fixed_core_x:.4f}  "
        f"(probe-tip side; T1 at x=0)"
    )
    print(
        f"  fixed surface_x     : {result.fixed_surface_x:.4f}  "
        f"(stem side; T8 at x=1)"
    )
    if result.classification is not None:
        ca = result.classification.core_assignment
        sa = result.classification.surface_assignment
        if ca is not None:
            print(
                f"    core conf={ca.confidence}  reason={ca.reason!r}"
            )
        if sa is not None:
            print(
                f"    surface conf={sa.confidence}  reason={sa.reason!r}"
            )

    # T_at_fixed_core final value (target ~95 C).
    finite_T_core = result.T_at_fixed_core_t[
        np.isfinite(result.T_at_fixed_core_t)
    ]
    T_core_final = (
        float(finite_T_core[-1]) if finite_T_core.size else float("nan")
    )
    finite_T_surf = result.T_at_fixed_surface_t[
        np.isfinite(result.T_at_fixed_surface_t)
    ]
    T_surf_final = (
        float(finite_T_surf[-1]) if finite_T_surf.size else float("nan")
    )
    print(
        f"\n  T_at_fixed_core final  : {T_core_final:.2f} C  (target ~95)"
    )
    print(
        f"  T_at_fixed_surface end : {T_surf_final:.2f} C"
    )

    # Per-isotherm summary table.
    print("\n  isotherm | first appearance |  last appearance | position range")
    print("  ---------+------------------+------------------+-----------------------")
    for T in isotherms:
        arr = result.isotherm_positions[T]
        finite_mask = np.isfinite(arr)
        first = _format_time_range(result.t_grid_s, finite_mask).split(" .. ")[0]
        last = _format_time_range(result.t_grid_s, finite_mask).split(" .. ")[-1]
        rng = _format_position_range(arr)
        print(
            f"  {T:6.1f} C | {first:>16s} | {last:>16s} | {rng}"
        )

    # Monotonicity check on 100 C front (overall trend).
    front = result.isotherm_positions[100.0]
    valid_mask = np.isfinite(front)
    if valid_mask.sum() >= 5:
        valid_front = front[valid_mask]
        n = valid_front.size
        head = float(np.mean(valid_front[: max(1, n // 5)]))
        tail = float(np.mean(valid_front[-max(1, n // 5):]))
        monotone = bool(tail <= head + 0.05)
        print(
            f"\n  100 C front trend     : "
            f"head={head:.3f}  tail={tail:.3f}  "
            f"monotone-inward={monotone}"
        )
    else:
        print("\n  100 C front trend     : insufficient samples")

    # ------------------------------------------------------------------
    # JSON dump for HMS Astute
    # ------------------------------------------------------------------
    os.makedirs(_MISSION_DIR, exist_ok=True)
    payload = {
        "csv": os.path.basename(_BA3C_0946_CSV),
        "n_strides": int(result.t_grid_s.size),
        "stride_seconds": 30.0,
        "isotherm_temps_C": list(result.isotherm_temps_C),
        "fixed_core_x": float(result.fixed_core_x),
        "fixed_surface_x": float(result.fixed_surface_x),
        "t_grid_s": _to_serialisable(result.t_grid_s),
        "isotherm_positions": {
            f"{T:.1f}": _to_serialisable(result.isotherm_positions[T])
            for T in result.isotherm_temps_C
        },
        "isotherm_positions_raw": {
            f"{T:.1f}": _to_serialisable(result.isotherm_positions_raw[T])
            for T in result.isotherm_temps_C
        },
        "T_at_fixed_core_t": _to_serialisable(result.T_at_fixed_core_t),
        "T_at_fixed_surface_t": _to_serialisable(result.T_at_fixed_surface_t),
        "core_confidence": (
            result.classification.core_assignment.confidence
            if result.classification is not None
            and result.classification.core_assignment is not None
            else None
        ),
        "core_reason": (
            result.classification.core_assignment.reason
            if result.classification is not None
            and result.classification.core_assignment is not None
            else None
        ),
        "surface_confidence": (
            result.classification.surface_assignment.confidence
            if result.classification is not None
            and result.classification.surface_assignment is not None
            else None
        ),
    }
    with open(_JSON_OUT, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nJSON written to: {_JSON_OUT}")

    # ------------------------------------------------------------------
    # Plotting
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(4, 1, figsize=(11, 16))
    t_min = result.t_grid_s / 60.0
    sensor_t_min = (
        np.arange(len(df_curve)) * sample_period_ms / 1000.0 / 60.0
    )

    # Panel 1: 8 sensor temperatures over time.
    ax = axes[0]
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

    # Panel 2: Four isotherm positions over time.
    ax = axes[1]
    for T in isotherms:
        col = _ISOTHERM_COLOURS[T]
        # Raw as scatter, smoothed as line.
        raw = result.isotherm_positions_raw[T]
        smooth = result.isotherm_positions[T]
        ax.plot(t_min, raw, "o", ms=2.5, color=col, alpha=0.35)
        ax.plot(
            t_min, smooth, "-", color=col, lw=2.0,
            label=f"{T:.0f} °C front",
        )
    ax.set_ylabel("Isotherm position (normalised)")
    ax.set_title(
        "Panel 2 — Isothermal positions over time "
        "(60 C deepest, 110 C nearest surface)"
    )
    ax.set_ylim(-0.05, 1.05)
    ax.axhline(0.0, color="k", lw=0.5, alpha=0.5)
    ax.axhline(1.0, color="k", lw=0.5, alpha=0.5)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left", fontsize=9, frameon=False)

    # Panel 3: Fixed core and surface positions (horizontal lines), with
    # T_at_fixed_core and T_at_fixed_surface temperature traces overlaid
    # on a twin axis.
    ax = axes[2]
    ax.axhline(
        result.fixed_core_x,
        color="#1f77b4", lw=2.0, ls="--",
        label=f"core_x = {result.fixed_core_x:.3f}",
    )
    ax.axhline(
        result.fixed_surface_x,
        color="#d62728", lw=2.0, ls="--",
        label=f"surface_x = {result.fixed_surface_x:.3f}",
    )
    # Repeat the 100 C front for spatial context.
    ax.plot(
        t_min, result.isotherm_positions[100.0],
        "-", color="#aaaaaa", lw=1.0, alpha=0.6,
        label="100 C front (context)",
    )
    ax.set_ylabel("Position (normalised)")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title(
        "Panel 3 — Fixed core/surface positions and time-series "
        "T_at_fixed_core / T_at_fixed_surface"
    )
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    # Twin axis for temperatures.
    ax2 = ax.twinx()
    ax2.plot(
        t_min, result.T_at_fixed_core_t,
        "-", color="#1f77b4", lw=1.5,
        label="T at fixed core",
    )
    ax2.plot(
        t_min, result.T_at_fixed_surface_t,
        "-", color="#d62728", lw=1.5,
        label="T at fixed surface",
    )
    ax2.axhline(95.0, color="grey", lw=0.5, ls=":", alpha=0.6)
    ax2.set_ylabel("Temperature (°C)")
    ax2.legend(loc="upper right", fontsize=9, frameon=False)

    # Panel 4: combined view — sensor temperatures over time with
    # isotherm positions overlaid as horizontal lines drawn at each
    # stride's interpolated x (vertical bars at stride times).
    ax = axes[3]
    # Background: T1..T8 traces as faint context.
    for i in range(1, 9):
        col = f"T{i}"
        if col in df_curve.columns:
            ax.plot(
                sensor_t_min, df_curve[col].to_numpy(),
                color=palette(0.05 + 0.9 * (i - 1) / 7.0),
                lw=0.6, alpha=0.45,
            )
    # Overlay each isotherm: at each stride, plot a coloured marker at
    # (t, position-mapped-back-to-temperature) — i.e. the target T value
    # is the y, and the marker's x is the stride time. This gives the
    # user-facing 'where is each front right now' view.
    for T in isotherms:
        col = _ISOTHERM_COLOURS[T]
        smooth = result.isotherm_positions[T]
        finite_mask = np.isfinite(smooth)
        if finite_mask.any():
            ax.plot(
                t_min[finite_mask],
                np.full(finite_mask.sum(), T),
                "o", ms=4, color=col,
                label=f"{T:.0f} °C isotherm advancing",
            )
    ax.axhline(100.0, color="grey", lw=0.5, ls="--", alpha=0.6)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title(
        "Panel 4 — Combined: sensor traces + active isotherm timeline "
        "(markers show when each front is present)"
    )
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=8, frameon=False)

    fig.suptitle(
        "BA3C_0946 — isothermal-tracker traces (M24 HMS Foxhound)",
        y=0.995, fontsize=13, weight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(_PNG_OUT, dpi=140)
    print(f"PNG written to: {_PNG_OUT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
