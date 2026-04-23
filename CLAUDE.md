# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Streamlit application that analyzes CSV exports from **Combustion Inc. temperature probes** to profile bread baking in manufacturing environments. A single probe contains 8 sensors (T1–T8) arranged along its length; depending on how deep the probe is inserted into the loaf, different sensor ranges end up "in the bread" (core), "at the crust/interface" (surface), or "in the oven air" (ambient). The app infers those roles, extracts individual baking curves from the time series, and produces thermal-profile analytics.

## Key Commands

Virtual environment lives in `venv/` (Linux/macOS) or `venv\Scripts\` (Windows); activate before any command below.

```bash
# Setup
python3 -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run the app
streamlit run app.py
streamlit run app.py --server.port 8080

# Tests (no pytest config file — discovery is default)
pytest                                                # full suite under tests/
pytest tests/test_per_curve_sensor_identification.py  # single file
pytest tests/test_thermal_plotter.py::TestThermalPlotter::test_method_name  # single test
pytest --cov=src tests/                               # coverage

# Quality (tools are not currently pinned in requirements.txt — install as needed)
black .
flake8 src/ tests/
mypy src/
```

**Project layout note:** `tests/` holds the real pytest suite. The many `test_*.py`, `analyze_*.py`, `debug_*.py`, and `check_*.py` files at the **repo root** are one-off investigation scripts (not pytest tests) kept as historical artifacts — do not assume `pytest` at root picks them up, and be skeptical of them as specs. Two real CSVs (`ProbeData_*.csv`) and one curated sample under `data/sample_profiles/` are used as fixtures by several ad-hoc scripts.

## CSV Input Format

Combustion Inc. CSVs have **10 header lines of metadata** (colon-separated `key: value`) followed by the data table. The loader reads metadata with manual line splitting and then uses `pd.read_csv(..., skiprows=10)`. Columns of interest:

- `T1`…`T8` — raw sensor temperatures
- `Virtual{Core,Surface,Ambient}Temperature` — firmware-computed virtual channels
- `Virtual{Core,Surface,Ambient}Sensor` — which physical sensor (e.g. `T1`, `T4`) the firmware picked for each role at that sample. **This assignment can change sample-to-sample**, so the app takes the mode over the curve.
- Header fields used elsewhere: `Probe S/N`, `Sample Period` (ms, sometimes with trailing comma), `Created` (timestamp).

Probe-name labels shown in plots/legends are `{last4-of-S/N}_{HH:MM}[_C{n}]` (e.g. `98DE_13:51`, or `F3C1_09:11_C1` for multi-curve files) — this convention is relied on for legend compactness; falls back to filename parsing when metadata is missing.

## Architecture

### Runtime shape

- **`app.py` (~1,340 lines)** is the Streamlit entry point and holds all UI, tab layout, and per-widget session-state wiring. It imports analyzers from `src/analysis/`, loaders from `src/data/`, and plotting from `src/visualization/`. The tab set has two variants — 7 tabs for a single curve, 8 when multiple curves are loaded (adds **Curve Comparison**).
- **Multi-file / multi-curve session state** — `st.session_state.files` is `{filename: {loader, metadata, curves}}`. `st.session_state.all_curves` is a flat list across files; `global_curve_index` indexes into it; `current_curve_index` is the index **within the loader for the currently selected file**. When the user switches curves, the app rebuilds `ThermalAnalyzer` and `SCurveAnalyzer` from scratch — analyzers are not shared across curves.
- `curve_info` dicts (built in `app.py`) have `loader` at the **top level**, not nested inside `curve_data`. Don't look for it in `curve_data`.

### Data transformation pipeline (the heart of the bugs this project keeps hitting)

Standardised columns `CoreTemperature`, `SurfaceTemperature`, `AmbientTemperature` are produced by layering transformations — they are **not** the same as the raw `Virtual*Temperature` columns, because physics corrections and manual overrides can swap the underlying sensor.

Order of layers (must be preserved):
1. **Virtual columns** copied from the CSV's firmware-picked channels.
2. **Physics-based surface correction** (`src/data/surface_sensor_detector.py`) — overrides the firmware's surface pick when the thermodynamic classifier is more confident. Gated by `config/constants.py: SURFACE_DETECTION_CONFIG`.
3. **Manual overrides** from the sidebar UI, layered *on top of* physics corrections (never replacing them silently).
4. **Backward-compat averages** `CoreAverage` / `SurfaceAverage` — static means of T1–T4 / T5–T8. These **do not update with overrides** on purpose; any analysis that must respect overrides should read `CoreTemperature` / `SurfaceTemperature`.

Two implementations of this pipeline exist side by side:

- **`ThermalProfileLoader` (`src/data/loader.py`, ~1,400 lines)** — the live one used by `app.py`. It mutates DataFrames in place and uses a `physics_corrected` flag on `curve_sensor_assignments[curve_index]` to prevent `_regenerate_standard_columns()` / `_generate_standard_columns_for_df()` from clobbering the corrected surface channel. `self.data` tracks the *currently selected* curve and is swapped by `set_current_curve()`.
- **`TransformationManager` (`src/data/transformation_manager.py`)** — a newer, centralized, state-tracking replacement. **Not yet wired into the loader** — it exists and is tested but `app.py` still goes through the old path. See `TRANSFORMATION_MANAGER_INTEGRATION.md`. Expect to either finish that integration or delete it during the planned refactor.

### Per-curve sensor identification

A single CSV can contain multiple bakes (the probe is left on across runs). `_extract_all_baking_curves()` splits them; `_identify_sensor_roles_for_curve()` runs independently per curve and stores results in `curve_sensor_assignments[curve_index]`. This matters because the probe may be re-inserted at a different depth between runs, so **role→physical-sensor mapping genuinely differs per curve**. Sensor-aware getters all take an optional `curve_index` (falling back to `current_curve_index`): `get_core_sensor(i)`, `get_surface_sensor(i)`, `get_internal_sensors(i)`, `get_ambient_sensors(i)`, `get_sensor_assignments_with_overrides(i)`. Analysis/viz code should **always pass the index explicitly** when iterating multiple curves.

### Config as source of truth

`config/constants.py` is the canonical place for domain constants — do not hardcode:

- `TEMPERATURE_ZONES`, `S_CURVE_ZONES`, `S_CURVE_BENCHMARKS` — bread-chemistry zones (yeast-kill, starch gelatinization, etc.) and their target timings.
- `BAKEOUT_TARGETS`, `PRODUCT_MOISTURE` — per-product (white_pan, sourdough, baguette, …) bake-out windows and moisture decay parameters.
- `SURFACE_DETECTION_CONFIG`, `INTERNAL_SENSOR_CONFIG` — tunables for the physics-based classifiers; `INTERNAL_SENSOR_CONFIG.TEMP_THRESHOLD = 103.0` (max temp counted as internal crumb) is deliberately set at 100 °C + 3 °C margin.
- `SENSOR_NAMES` — default labels; the UI overlays dynamic role-based names on top via `app.py: get_dynamic_sensor_names()`.

`src/visualization/visualization_config.py` (`VisualizationConfig`) centralises colors, formatting, and zone-based color mapping used across plots — new plots should route through it rather than re-defining palettes.

## Known Fragile Areas

These are the recurring bug surfaces called out across `REFACTORING_ANALYSIS.md`, `CODE_REVIEW_SUMMARY.md`, and the `*_FIX_*.md` files (the repo has ~25 such docs — they are investigation/plan notes, not authoritative specs):

- **Column regeneration** — any code path that recreates `CoreTemperature` / `SurfaceTemperature` must check the `physics_corrected` flag or it will undo the surface correction. This has bitten the project more than once.
- **Curve switching** — `set_current_curve()` has hidden side-effects (rewrites `self.data`, triggers regeneration); manual overrides and physics corrections must survive the switch.
- **Internal-sensor filtering** — `get_internal_sensors()` is recomputed per call with no cache; if called with a stale `data` argument it returns wrong sensors.
- **`loader.py.backup`** is an old snapshot kept in-tree — do not edit it and do not assume it is current.

## Repo Hygiene Notes

- The repo root is cluttered with ad-hoc `analyze_*.py`, `debug_*.py`, `check_*.py` scripts and ~25 `*_PLAN.md` / `*_SUMMARY.md` / `*_ANALYSIS.md` files. Treat them as historical context, not specs. A documented goal is to clean these up during refactoring.
- Real CSV probe exports live at the repo root (`ProbeData_*.csv`) — several scripts load them by relative path.
- Generated artifacts like `zone_comparison_test.html` (4.6 MB) and PNG screenshots are committed; avoid regenerating/committing more unless asked.
- `tests/` uses class-based pytest style and injects `sys.path` in each file rather than relying on a `conftest.py` — adding new tests should either follow the same pattern or introduce a real `conftest.py`.
