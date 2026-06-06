"""Sensor-role annotation helper (M1a HMS Truculent).

Pure helper module that loads each real-CSV fixture through
:class:`ThermalProfileLoader`, plots every detected baking curve as a per-sensor
trace PNG, and records human-curated surface/lid annotations into a JSON
manifest.  The annotator is *only* used to produce the artefacts a captain
inspects when picking ground truth — it does NOT auto-decide which sensor is the
surface or the lid.

Usage
-----
::

    from tests.fixtures._role_annotator import run_annotation_pass
    run_annotation_pass("/path/to/annotations")

This writes ``{fixture_key}_curve{N}.png`` into the supplied directory for every
real-CSV curve listed in :data:`REAL_CSV_FIXTURES`.  The captain then reads each
PNG, calls :func:`record_annotation` per curve to log their surface/lid pick
plus reasoning, and finally edits ``curve_boundary_cases.py`` to mirror the
manifest.

Design notes
------------
* ``matplotlib.use('Agg')`` is set at import time so this module runs cleanly
  in a headless test/CI context.
* The loader path mirrors the live app: we go through ``ThermalProfileLoader``
  rather than parsing the CSV by hand, so the per-curve DataFrames already
  carry whatever standardised columns ``_extract_all_baking_curves`` produces.
* Manifests are append-only JSON dicts keyed by ``f"{fixture_key}#{curve_index}"``
  so multiple :func:`record_annotation` calls accumulate without clobbering.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# ---------------------------------------------------------------------------
# Path setup — allow import of src.data.loader regardless of cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.data.loader import ThermalProfileLoader  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures to annotate (mirrors the real-CSV cases in curve_boundary_cases.py)
# ---------------------------------------------------------------------------
SENSOR_COLS = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]

REAL_CSV_FIXTURES: list[tuple[str, str]] = [
    ("100098DE_1351", "ProbeData_100098DE_2025-05-30 13_51_07.csv"),
    ("1000BA3C_0946", "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"),
    ("1000BA3C_1759", "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"),
    ("wonder_white_10k", "wonder white 10k 13.01.2026.csv"),
    ("post_wonder_meal_20251017", "Post Wonder Meal 20251017.csv"),
]


# ---------------------------------------------------------------------------
# Plot helper
# ---------------------------------------------------------------------------
def plot_curve(
    curve_df: pd.DataFrame,
    sample_period_ms: int,
    title: str,
    output_path: str,
) -> None:
    """Save a PNG with all 8 sensor traces and a max(T1..T8) overlay.

    X-axis is minutes from curve start; y-axis is temperature in degrees Celsius.
    The curve DataFrame must contain T1..T8 columns; missing sensors are skipped.
    A ``Timestamp`` column (seconds, monotonic) or ``TimeMinutes`` column is
    used for the x-axis when present, otherwise the index is used scaled by the
    supplied sample period.
    """
    fig, ax = plt.subplots(figsize=(11, 6.5))

    if "TimeMinutes" in curve_df.columns:
        x_min = curve_df["TimeMinutes"].to_numpy()
    elif "Timestamp" in curve_df.columns:
        ts = curve_df["Timestamp"].to_numpy()
        x_min = (ts - ts[0]) / 60.0
    else:
        x_min = (curve_df.index.to_numpy() * sample_period_ms / 1000.0) / 60.0

    sensor_present = [c for c in SENSOR_COLS if c in curve_df.columns]
    palette = plt.get_cmap("tab10")
    for i, col in enumerate(sensor_present):
        ax.plot(
            x_min,
            curve_df[col].to_numpy(),
            label=col,
            linewidth=1.4,
            color=palette(i),
        )

    if sensor_present:
        max_arr = curve_df[sensor_present].max(axis=1).to_numpy()
        ax.plot(
            x_min,
            max_arr,
            label="max(T1..T8)",
            linewidth=2.0,
            color="black",
            linestyle="--",
            alpha=0.6,
        )

    ax.axhline(100.0, color="grey", linestyle=":", linewidth=0.8, alpha=0.6)
    ax.set_xlabel("Time from curve start (minutes)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title(title)
    ax.legend(loc="best", ncol=2, fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Manifest helper
# ---------------------------------------------------------------------------
def record_annotation(
    manifest_path: str,
    fixture_key: str,
    curve_index: int,
    expected_core: str,
    expected_surface: str,
    expected_lid: Optional[str],
    reasoning: str,
) -> None:
    """Append (or overwrite) a single annotation entry in ``manifest.json``.

    The manifest is a dict keyed by ``f"{fixture_key}#{curve_index}"``.  Each
    entry records the captain's surface and (where applicable) lid pick plus a
    free-text reasoning string citing the visual evidence.
    """
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    else:
        manifest = {}

    key = f"{fixture_key}#{curve_index}"
    manifest[key] = {
        "fixture_key": fixture_key,
        "curve_index": curve_index,
        "expected_core_sensor": expected_core,
        "expected_surface_sensor": expected_surface,
        "expected_lid_sensor": expected_lid,
        "reasoning": reasoning,
    }

    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Top-level driver — produce one PNG per detected curve
# ---------------------------------------------------------------------------
def run_annotation_pass(annotator_output_dir: str) -> list[str]:
    """Load each real CSV, iterate baking curves, and write one PNG per curve.

    Returns the list of PNG paths written, in iteration order.  Does NOT touch
    the manifest — that is reserved for :func:`record_annotation` which the
    captain calls after visual inspection.
    """
    os.makedirs(annotator_output_dir, exist_ok=True)
    written: list[str] = []

    for fixture_key, csv_filename in REAL_CSV_FIXTURES:
        csv_path = os.path.join(_REPO_ROOT, csv_filename)
        loader = ThermalProfileLoader()
        loader.load_csv(file_path=csv_path)

        sample_period_ms = int(loader.metadata.get("sample_period_ms", 5000))
        curves = loader.all_curves or []

        for curve_index, curve in enumerate(curves):
            curve_df = curve["data"]
            title = (
                f"{fixture_key} — curve {curve_index + 1} of {len(curves)} "
                f"({len(curve_df)} samples @ {sample_period_ms} ms)"
            )
            output_path = os.path.join(
                annotator_output_dir,
                f"{fixture_key}_curve{curve_index + 1}.png",
            )
            plot_curve(curve_df, sample_period_ms, title, output_path)
            written.append(output_path)

    return written
