#!/usr/bin/env python
"""Headless driver / smoke test for the Thermal Profile Analyzer (Streamlit).

Drives the actual analysis pipeline that backs the "Spatial Evolution" tab —
WITHOUT a browser — so a future agent can validate a change in seconds:

    load a real probe CSV -> ThermalProfileLoader
      -> loader.isothermal_assignment(curve)        (the moisture-front tracker)
      -> plot_isothermal_positions / plot_fixed_position_temperatures
      -> write a viewable HTML chart artifact

This is the layer almost every change here touches (the spatial-reconstruction
analysis + the figures). The full browser UI is the *secondary* path — see
SKILL.md "Run (real browser UI)".

Exit codes: 0 = ran and the figures built; 1 = no curve / build failure;
2 = CSV not found.

Usage (run with the project's venv python, from anywhere):
    python .claude/skills/run-oven-logging/driver.py
    python .claude/skills/run-oven-logging/driver.py "wonder white 10k 13.01.2026.csv"
    python .claude/skills/run-oven-logging/driver.py --curve 0 --out /tmp/panelB.html
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Skill lives at <repo>/.claude/skills/run-oven-logging/driver.py -> repo is parents[3].
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless Spatial Evolution smoke")
    ap.add_argument(
        "csv",
        nargs="?",
        default="ProbeData_1000BA3C_2025-05-30 09_46_16.csv",
        help="probe CSV at the repo root, or an absolute path "
        "(default: a BA3C bake where the probe spans crumb->crust->air)",
    )
    ap.add_argument("--curve", type=int, default=0, help="curve index (default 0)")
    ap.add_argument(
        "--out",
        default=str(REPO / "_run_spatial_evolution.html"),
        help="HTML artifact path for the isotherm-front (Panel B) chart",
    )
    args = ap.parse_args()

    csv_path = args.csv if os.path.isabs(args.csv) else str(REPO / args.csv)
    if not os.path.exists(csv_path):
        print(f"CSV not found: {csv_path}")
        return 2

    import numpy as np  # noqa: E402
    from src.data.loader import ThermalProfileLoader  # noqa: E402
    from src.visualization.spatial_evolution_plots import (  # noqa: E402
        isotherm_coverage_warning,
        plot_fixed_position_temperatures,
        plot_isothermal_positions,
    )

    loader = ThermalProfileLoader()
    loader.load_csv(file_path=csv_path)
    if not loader.all_curves:
        print("No baking curves detected in CSV")
        return 1

    assignment = loader.isothermal_assignment(args.curve)
    conf, reason = loader.get_core_confidence(args.curve)

    print(f"CSV         : {os.path.basename(csv_path)}")
    print(f"curves      : {len(loader.all_curves)}   strides: {assignment.t_grid_s.size}")
    print(f"core_x/surf : {assignment.fixed_core_x:.3f} / {assignment.fixed_surface_x:.3f}")
    print(f"core conf   : {conf} — {reason}")
    for temp_c in assignment.isotherm_temps_C:
        arr = np.asarray(assignment.isotherm_positions[temp_c], dtype=float)
        fin = arr[np.isfinite(arr)]
        if fin.size:
            print(f"  {int(temp_c):3} C front: {fin.size:3} pts   {fin.max():.3f} -> {fin.min():.3f}")
        else:
            print(f"  {int(temp_c):3} C front: (never located in the probe span)")

    warning = isotherm_coverage_warning(assignment)
    if warning is None:
        print("coverage    : FRONTS TRACKED (the moisture front moves through the probe)")
    else:
        print("coverage    : DEGENERATE — " + warning.splitlines()[0])

    # Build both figures (proves the rendering path); write Panel B as the artifact.
    fig_b = plot_isothermal_positions(assignment)
    fig_c = plot_fixed_position_temperatures(assignment)
    if len(fig_b.data) == 0 or len(fig_c.data) < 2:
        print("Figure build produced no traces")
        return 1
    fig_b.write_html(args.out, include_plotlyjs="cdn")
    print(f"artifact    : {args.out}   ({len(fig_b.data)} Panel-B traces)")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
