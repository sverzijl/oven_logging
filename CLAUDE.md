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

**Project layout note:** `tests/` holds the real pytest suite. The repo root now holds only the live Streamlit entry points (`app.py`, `sidebar.py`, `session_state.py`, `sensor_naming.py`) — historical investigation scripts (`analyze_*.py`, `debug_*.py`, `check_*.py`) and superseded plan/summary `.md` files have been pruned across recent refactor flotillas. Real probe CSVs live at the repo root and are mapped via `tests/fixtures/curve_boundary_cases.py:_REAL_CSVS`.

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

Standardised columns `CoreTemperature`, `SurfaceTemperature`, `AmbientTemperature` (and conditionally `LidTemperature`) are produced by layering transformations — they are **not** the same as the raw `Virtual*Temperature` columns, because the spatial-reconstruction classifier and manual overrides can swap the underlying sensor.

Order of layers (must be preserved):
1. **Manual override** from the sidebar UI / `loader.set_sensor_override(curve_index, role, sensor)` — the highest-precedence layer; topology-validated via `_validate_override_topology` before commit.
2. **Classifier assignment** — `assignment.<role>.temperature_series` from the per-curve `SpatialAssignment` returned by `src.data.spatial_reconstruction.classify`. The interpolated series is assigned to the standard column when it differs from a single sensor; otherwise the underlying `Tn` column is reused verbatim.
3. **Legacy fallback** — only `resolve_core_temperature_series` remains as a helper for code paths that historically fell back to `VirtualCoreTemperature`. Surface / ambient / lid have no legacy fallback; the classifier is authoritative.
4. **Backward-compat averages** `CoreAverage` / `SurfaceAverage` — static means of T1–T4 / T5–T8. These **do not update with overrides** on purpose; any analysis that must respect overrides should read `CoreTemperature` / `SurfaceTemperature`.

Pipeline implementation:

- **`ThermalProfileLoader` (`src/data/loader.py`)** — the live one used by `app.py`. It mutates DataFrames in place; `_identify_sensor_roles_for_curve` is a thin wrapper around `spatial_reconstruction.classify` that stores the `SpatialAssignment` plus per-role sensor picks under `curve_sensor_assignments[curve_index]`. `self.data` tracks the *currently selected* curve and is swapped by `set_current_curve()`. Override application calls `_apply_standard_columns(df_curve, curve_index)` which writes `LidTemperature` only when `assignment.lid is not None` and drops it when lid is `None` on the next regeneration.

### Per-curve sensor identification

A single CSV can contain multiple bakes (the probe is left on across runs). `_extract_all_baking_curves()` splits them; `_identify_sensor_roles_for_curve()` runs independently per curve. Per curve, `_identify_sensor_roles_for_curve` calls `src.data.spatial_reconstruction.classify(df, sample_period_ms, probe_geometry)` which returns a `SpatialAssignment` (dataclass) holding per-role `PositionalAssignment` records (`position_normalised`, `nearest_sensor`, `temperature_series`, `confidence`, `reason`). Roles supported: **core** (always), **surface** (`None` for full-immersion), **ambient** (list, may be empty), **lid** (`None` when no lid contact detected). Manual overrides via `loader.set_sensor_override(curve_index, role, sensor)` win over classifier output; topology validated via `_validate_override_topology` with the **through-loaf exception** (probe pierces the loaf so ambient sensors split into a low-T prefix and a high-T suffix around the surface index).

Probe re-insertion depth genuinely differs per curve, so role→physical-sensor mapping is per-curve. Sensor-aware getters all take an optional `curve_index` (falling back to `current_curve_index`): `get_core_sensor(i)`, `get_surface_sensor(i)`, `get_lid_sensor(i)`, `get_internal_sensors(i)`, `get_ambient_sensors(i)`, `get_sensor_assignments_with_overrides(i)`. Analysis/viz code should **always pass the index explicitly** when iterating multiple curves.

### Config as source of truth

`config/constants.py` is the canonical place for domain constants — do not hardcode:

- `TEMPERATURE_ZONES`, `S_CURVE_ZONES`, `S_CURVE_BENCHMARKS` — bread-chemistry zones (yeast-kill, starch gelatinization, etc.) and their target timings.
- `BAKEOUT_TARGETS`, `PRODUCT_MOISTURE` — per-product (white_pan, sourdough, baguette, …) bake-out windows and moisture decay parameters.
- `ROLE_CLASSIFIER_CONFIG` — the authoritative tuning surface for `spatial_reconstruction.classify` (plateau detection, rise-slope band, oven-proxy tolerance, lid-contact gap, dough/air-interface jump, default model).
- `INTERNAL_SENSOR_CONFIG` — legacy temperature-threshold filter retained for `loader.get_internal_sensors`; `TEMP_THRESHOLD = 103.0` (100 °C + 3 °C margin). A position-based replacement using `assignment.<role>.position_normalised` is a future follow-up.
- `CORE_DETECTION_CONFIG` — keys still consumed by `identify_core_sensor_combined_rank` (used by curve-boundary detection's probe-removal-contamination path) and the `_drop_rate_detection` helper.
- `CURVE_DETECTION_CONFIG` — curve-boundary detector tunables (cliff, plateau, sigmoid refinement).
- `SENSOR_NAMES` — default labels; the UI overlays dynamic role-based names on top via `app.py: get_dynamic_sensor_names()`.

`src/visualization/visualization_config.py` (`VisualizationConfig`) centralises colors, formatting, and zone-based color mapping used across plots — new plots should route through it rather than re-defining palettes.

### Spatial-reconstruction classifier

The classifier replacing the old `surface_sensor_detector` + `ThermodynamicSensorClassifier` pair lives at `src/data/spatial_reconstruction/`:

- `geometry.py` — `PROBE_GEOMETRIES` registry (Combustion Inc. probe normalised positions) and `lookup_geometry`.
- `profile.py` — `ProfileFit`, `extract_features`, `compute_oven_proxy` (per-curve features: plateau, rise slope, terminal mean, cavity proxy).
- `piecewise.py` — default `fit_piecewise` model (dough plateau + air-side rise).
- `stefan.py` — opt-in `fit_stefan` Stefan-front physics-constrained model (`STEFAN_FRONT_TEMP_C = 100`).
- `classifier.py` — `classify`, `SpatialAssignment`, `PositionalAssignment` — the public entry point used by the loader.
- `comparison.py` — `ModelComparison`, `benchmark_fixture`, `benchmark_all_cases`, `write_comparison_report`.

The empirical model-comparison and perturbation baselines are at `tests/baselines/spatial_model_comparison.md` and `tests/baselines/role_classifier_flip_rates.md` — regenerate via the comparison harness when adding fixtures.

## Known Fragile Areas

These are the recurring bug surfaces:

- **`LidTemperature` column lifecycle** — only present when `assignment.lid is not None`. The column is dropped on curve switches when the new curve has no lid (`_apply_standard_columns` is responsible). Any code that sums or iterates standardised columns must treat `LidTemperature` as optional.
- **Override topology validation** — `_validate_override_topology` enforces `core_idx < surface_idx <= min(ambient_idx) <= max(ambient_idx) <= lid_idx`. The **through-loaf exception** is the one case the strict ordering rule does NOT apply (ambient splits into a contiguous low-T prefix and a contiguous high-T suffix; surface sits between them). A future override rule change must preserve this exception.
- **Curve switching** — `set_current_curve()` has hidden side-effects (rewrites `self.data`, triggers regeneration); manual overrides and classifier picks must survive the switch.
- **Internal-sensor filtering** — `get_internal_sensors()` is recomputed per call with no cache; if called with a stale `data` argument it returns wrong sensors. (Position-based replacement is a future follow-up.)
- **`loader.py.backup`** is an old snapshot kept in-tree (if present) — do not edit it and do not assume it is current.

## Repo Hygiene Notes

- Historical `analyze_*.py` / `debug_*.py` / `check_*.py` scripts and `*_PLAN.md` / `*_SUMMARY.md` / `*_ANALYSIS.md` files have been pruned across recent refactor flotillas; root-level Python is now `app.py`, `sidebar.py`, `session_state.py`, `sensor_naming.py` only. Treat anything under `.nelson/missions/` as mission archives, not specs.
- Real CSV probe exports live at the repo root (`ProbeData_*.csv`, `wonder white 10k 13.01.2026.csv`, `Post Wonder Meal 20251017.csv`) — fixtures load them by `_REAL_CSVS` mapping in `tests/fixtures/curve_boundary_cases.py`.
- Generated artifacts like `zone_comparison_test.html` and PNG screenshots may exist; avoid regenerating/committing more unless asked.
- `tests/` uses class-based pytest style and injects `sys.path` in each file rather than relying on a `conftest.py` — adding new tests should either follow the same pattern or introduce a real `conftest.py`.
