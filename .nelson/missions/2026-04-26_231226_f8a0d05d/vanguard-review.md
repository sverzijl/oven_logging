# HMS Vanguard — Temperature Profile Tab Review

**Captain 2 — Review + DRY Captain**
**Date:** 2026-04-27
**Mission:** 2026-04-26_231226_f8a0d05d
**Scope:** `tabs/temperature_profile.py` and its direct dependencies

---

## Out of Scope

The following are explicitly excluded from this review per mission standing orders:

- Keyless widgets in `tabs/zone_analysis.py` and `tabs/heating_analysis.py`
- `TransformationManager` integration (`src/data/transformation_manager.py`)
- `loader.py.backup`
- Full `app.py` split
- Root-level historical investigation scripts (`analyze_*.py`, `debug_*.py`, `check_*.py`)

---

## 1. Bugs

### B1 — Heatmap role-blindness

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File:line** | `src/visualization/plots.py:211-238` (call site: `tabs/temperature_profile.py:81`) |
| **What it does wrong** | `plot_temperature_gradient_heatmap()` accepts only `data: pd.DataFrame` (`plots.py:211`). Line 214 hardcodes `sensors = ['T1','T2','T3','T4','T5','T6','T7','T8']`. Line 226 labels the y-axis via `SENSOR_NAMES.get(s, s)` — the firmware-default dict at `config/constants.py:124-133`. The tab calls it at `tabs/temperature_profile.py:81` as `plotter.plot_temperature_gradient_heatmap(st.session_state.data)` with no role or override information. |
| **What the user observes** | An operator who uses the sidebar to reassign T7 as ambient and T2 as surface will see the line plot correctly update (it receives `sensor_roles` at `tabs/temperature_profile.py:75`), but the heatmap immediately below will continue to label T7 as "Near Surface" and T8 as "Surface" — the firmware-default names — regardless of any override. The two visualisations describe the same curve with contradictory role labels. |
| **Astute verdict** | **PASS (confirmed bug)** — see `astute-evidence.md §(b)`. Empirical output was `y: ['Core 1', 'Core 2', 'Core 3', 'Core 4', 'Middle 1', 'Middle 2', 'Near Surface', 'Surface']` invariant to perturbed role assignments. |

Note on severity: rated Medium rather than High because the heatmap is a secondary visualisation and the line plot (which correctly reflects overrides) is the primary user-facing output. However, the inconsistency is user-visible and directly contradicts the purpose of the sidebar override feature.

---

### B2 — Index drift between line 19 and line 53

| Field | Value |
|-------|-------|
| **Severity** | Low-Medium (latent / fragile) |
| **File:line** | `tabs/temperature_profile.py:19` vs `tabs/temperature_profile.py:53` |
| **What it does wrong** | Line 19 calls `loader.get_sensor_assignments_with_overrides(st.session_state.current_curve_index)` — passing the UI index explicitly. Line 53 calls `loader.get_sensor_assignments_with_overrides()` — no argument — defaulting to `loader.current_curve_index` inside the method at `src/data/loader.py:835-836`. If these two index values diverge (e.g., an exception between `sidebar.py:144` and `sidebar.py:147`, or a future URL parameter reader updating session state without calling `set_current_curve()`), the multiselect labels built from line 19 describe a different curve than the `sensor_roles` dict fed to the plot at line 75. The perturbed-fixture proof: `surface_sensor` became `T7` for index 1 vs `T6` for index 0 — an end-user would see the surface legend colour assigned to T7 in the dropdown but the plot drawing T6 as "surface". |
| **What the user observes** | Under normal navigation: no visible effect — `sidebar.py:144-147` keeps both indices synchronised on every render cycle. Under divergence: multiselect dropdown labels contradict the plot's role-based colouring. |
| **Astute verdict** | **CONDITIONAL PASS** — see `astute-evidence.md §(a)`. Divergence mechanism proven empirically with perturbed fixtures (`surface_sensor` differed: T7 vs T6). Trigger window is narrow (normal navigation never fires it). Latent fragility is confirmed. |

**Recommended fix:** Replace line 53 with an explicit index argument `loader.get_sensor_assignments_with_overrides(st.session_state.current_curve_index)`, or better: hoist both calls into a single assignment before the `if not show_all_sensors:` branch and reuse the result. The second option also eliminates the redundant double-fetch (see S6 below).

---

## 2. Code Smells

### S1 — Pattern A duplication (label-building loop)

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File:line** | `tabs/temperature_profile.py:22-38` |

A 13-line inline loop iterates `['T1'..'T8']`, tests each sensor against four role fields extracted from `assignments`, and builds a `sensor_labels` dict mapping sensors to display strings of the form `"T1 (Core)"`, `"T3 (Internal)"`, etc. This logic exists only to feed the `format_func` on the `st.multiselect` at line 45 and has no standalone abstraction.

---

### S2 — Pattern B duplication (role-dict-building loop)

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File:line** | `tabs/temperature_profile.py:52-67` |

A second 13-line loop iterates the same `['T1'..'T8']` list, performs the same four-way role test against the same four extracted fields (`core_sensor`, `surface_sensor`, `internal_sensors`, `ambient_sensors`), and builds a `sensor_roles` dict mapping sensors to role strings `'core'`, `'surface'`, `'internal'`, `'ambient'`. This is structurally identical to S1 with only the output format differing (role string vs. display label).

S1 and S2 are separated by 14 lines and operate on separately fetched `assignments` dicts (itself a smell — see S6). A single canonical helper would eliminate both.

---

### S3 — Empty-input fragility in heatmap

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File:line** | `src/visualization/plots.py:217-221` |

The loop `for sensor in sensors: if sensor in data.columns: heatmap_data.append(data[sensor].values)` silently produces an empty list if the DataFrame has no T* columns. Line 221 then calls `np.array(heatmap_data)` on an empty list, which produces a `(0,)` shaped array. `go.Heatmap(z=...)` will not immediately raise but will render an empty or broken chart. On a `data` argument with mismatched column names (e.g., a synthetic fixture), the failure is silent and hard to diagnose.

A guard `if not heatmap_data: raise ValueError(...)` or early return before line 221 would surface the problem at the point of failure rather than in the Plotly rendering engine.

---

### S4 — st.session_state coupling makes tab untestable

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File:line** | `tabs/temperature_profile.py:14, 19, 40, 46, 53, 72, 73` |

Seven direct reads of `st.session_state` are scattered through `render()`. There is no dependency injection: the function cannot be called in a plain pytest context without Streamlit's `AppTest` harness. Astute confirmed zero runtime-behaviour tests exist for this tab (`astute-evidence.md §(c)`). The `AppTest` harness is not currently used in the test suite. The pattern blocks unit testing of the role-building logic (S1/S2), the index-drift scenario (B2), and the plot call assembly.

Follow-up mitigation: introduce a `render(state)` signature where `state` is a simple namespace (or dataclass) holding `loader`, `current_curve_index`, `data`, and `show_zones`. Callers pass `st.session_state`; tests pass a lightweight stub.

---

### S5 — Accessibility: color-only role distinction partially mitigated

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File:line** | `src/visualization/plots.py:96-101` |

Role styles use distinct colors (`darkblue`, `red`, `steelblue`, `orange`) as the primary visual differentiator. For users with color vision deficiency the four roles could be ambiguous. The line-style differentiation (`solid/solid/dot/dash` at lines 97-100) partially mitigates this — core and surface are both `solid` but in distinctly different colors, while internal (`dot`) and ambient (`dash`) have different dash patterns. Not a blocking issue given the line-style backup, but worth noting for a future accessibility pass.

---

### S6 — Redundant double-fetch of assignments

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File:line** | `tabs/temperature_profile.py:19` and `tabs/temperature_profile.py:53` |

`get_sensor_assignments_with_overrides()` is called twice in `render()`: once at line 19 (inside the `if not show_all_sensors:` branch) and again unconditionally at line 53. The second call is always executed; the first is only executed when `show_all_sensors` is False. Because the loader recalculates the assignments on each call (no in-call cache within `render()`), both calls hit the same computation. Beyond the B2 index-drift risk, this is a needless double read. A single hoisted call before line 14 would serve both uses.

---

### S7 — Duplicate role-iteration logic between tab and plot

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File:line** | `tabs/temperature_profile.py:52-67` and `src/visualization/plots.py:107-113` |

The tab builds `sensor_roles` (Pattern B, lines 52-67) and passes it to `plot_temperature_profile`. Inside `plot_temperature_profile`, lines 107-113 then iterate `sensors` again, calling `sensor_roles.get(sensor, 'unknown')` and building a display label `f"{label} ({role.capitalize()})"`. The tab's Pattern B loop and the plot's internal label-building loop each independently encode the assumption that the canonical sensor list is `['T1'..'T8']`. If a future probe model adds T9, both sites must be updated independently.

---

## 3. DRY Inventory

### Group A: The canonical `['T1'..'T8']` sensor list

There is currently **no single source of truth** for the canonical 8-sensor list. It is hardcoded at every call site independently:

| File | Line(s) | Form |
|------|---------|------|
| `tabs/temperature_profile.py` | 28, 43, 59 | `['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']` |
| `sidebar.py` | 239, 240, 249, 250 | `['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']` |
| `src/visualization/plots.py` | 91, 214 | `['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']` (full list) |
| `src/visualization/plots.py` | 339 | `['T1', 'T2', 'T3', 'T4']` (T1-T4 subset) |
| `src/data/loader.py` | 865, 1404 | `['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']` |
| `src/data/loader.py` | 1391 | `['Timestamp', 'T1', ..., 'T8']` (required cols context) |
| `src/data/loader.py` | 1243 | `['Timestamp', 'TimeMinutes', 'T1', ..., 'T8', ...]` |
| `src/data/curve_boundary_detector.py` | 36 | `_SENSOR_COLUMNS = ("T1", ..., "T8")` — private tuple, not shared |
| `src/data/column_helpers.py` | 11 | `_T1_T4 = ['T1', 'T2', 'T3', 'T4']` — private T1-T4 subset only |
| `src/data/sensor_assignment_manager.py` | 54 | `['T1', 'T2', 'T3', 'T4']` — T1-T4 subset |
| `src/analysis/curve_comparison.py` | 31 | `[f'T{i}' for i in range(1, 9)]` — generated form |
| `src/analysis/zone_analysis.py` | 320 | `['T1', 'T2', 'T3', 'T4']` — T1-T4 subset |
| `sensor_naming.py` | 74, 107 | Partial (fallback defaults, not the full list) |

The `_SENSOR_COLUMNS` private constant in `curve_boundary_detector.py:36` and `_T1_T4` in `column_helpers.py:11` are module-private and not shared even within the `src/data/` package.

**Canonical home:** `SENSOR_LIST = ('T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8')` belongs in `config/constants.py` (the project's documented source of truth per `CLAUDE.md`), alongside `SENSOR_NAMES`. `VisualizationConfig` in `src/visualization/visualization_config.py` is NOT the right home — it is for plot formatting, not domain constants.

---

### Group B: The role-iteration loop (Pattern A and Pattern B)

The four-way `if/elif/elif/elif` role-assignment pattern appears three times:

| Site | File:line | Output format |
|------|-----------|---------------|
| Pattern A (label map) | `tabs/temperature_profile.py:22-38` | `{sensor: "T1 (Core)"}` for `format_func` |
| Pattern B (role map) | `tabs/temperature_profile.py:52-67` | `{sensor: 'core'}` for `sensor_roles` |
| `transform_sensor_assignments_to_roles` | `src/analysis/curve_comparison.py:12-36` | `{sensor: role}` — but takes a different input shape (see §4) |

Pattern A and Pattern B differ only in the value written to the output dict. Both iterate the same `['T1'..'T8']` list and test against the same four role fields. They should collapse to a single helper that returns the role map (Pattern B shape), with a trivial format wrapper for Pattern A.

---

## 4. Canonical Helper API and SENSOR_LIST Location

### Recommended placement

```python
# config/constants.py (add near line 123, before SENSOR_NAMES)
SENSOR_LIST: tuple[str, ...] = ('T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8')
```

This makes `SENSOR_LIST` the single authoritative source. `SENSOR_NAMES` (already at `config/constants.py:124-133`) maps the full list to firmware-default display labels and already imports cleanly across the codebase.

---

### Proposed canonical helper module

```python
# src/ui/sensor_role_helpers.py  (new module)
from config.constants import SENSOR_LIST
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.data.loader import ThermalProfileLoader


def build_sensor_role_map(loader: 'ThermalProfileLoader', curve_index: int) -> dict[str, str]:
    """
    Returns {'T1': 'core', 'T2': 'internal', ..., 'T8': 'ambient'}
    for every sensor in SENSOR_LIST, respecting per-curve overrides.

    Sensors with no role assignment are omitted (not mapped to 'internal'
    by default — the caller decides what to do with unmapped sensors).
    """


def build_sensor_label_map(
    loader: 'ThermalProfileLoader',
    curve_index: int,
    *,
    suffix_format: str = "({role})",
) -> dict[str, str]:
    """
    Returns {'T1': 'T1 (Core)', 'T2': 'T2 (Internal)', ...}
    for use as format_func in st.multiselect.

    Delegates to build_sensor_role_map; the suffix_format kwarg
    controls capitalisation style.
    """
```

Both functions call `loader.get_sensor_assignments_with_overrides(curve_index)` once and operate on `SENSOR_LIST`. The `render()` function in `tabs/temperature_profile.py` would call each helper once — eliminating S1, S2, and S6.

---

### Why existing helpers are not directly reusable

**`sensor_naming.get_dynamic_sensor_names()` (`sensor_naming.py:12-60`)**

This function reads `loader.get_sensor_assignments()` (not `get_sensor_assignments_with_overrides()`) and derives labels from the `core_info.all_sensors` histogram dict — an internal loader data structure that represents all sensors that were *ever* observed in the core role across firmware samples. The resulting label scheme is `"Core (Primary)"` / `"Core"` / `"Surface (Primary)"` etc., which does not match the tab's required `"T1 (Core)"` / `"T3 (Internal)"` format. The mismatch is structural: this function labels every sensor that appears in the firmware histogram, whereas the tab needs a clean per-sensor role for the *current curve* only. The two purposes are genuinely different, not stylistically interchangeable.

**`src/analysis/curve_comparison.py:transform_sensor_assignments_to_roles()` (`curve_comparison.py:12-36`)**

This function expects `sensor_assignments` to be a dict of the form `{'core': ['T1', 'T2'], 'surface': ['T7'], 'ambient': ['T8']}` — lists keyed by role name. The loader's `get_sensor_assignments_with_overrides()` returns `{'core_sensor': 'T1', 'surface_sensor': 'T7', 'internal_sensors': [...], 'ambient_sensors': [...]}` — singular scalars for core and surface, lists for internal and ambient, different key names. Adapting `transform_sensor_assignments_to_roles` to accept the loader's output would require either a bespoke adaptor or a signature change. More critically, the function fills unmapped sensors with `'internal'` unconditionally (`curve_comparison.py:30-34`), which conflates unmapped sensors with truly classified internal sensors — a semantic difference the tab's Pattern B deliberately avoids by leaving sensors unassigned when no role is known. A clean canonical helper is preferable to wrapping this function.

---

### Migration map

| Existing construct | Action after canonical-helper adoption |
|--------------------|---------------------------------------|
| `tabs/temperature_profile.py` Pattern A (lines 22-38) | Delete; replace with `build_sensor_label_map(loader, curve_index)` |
| `tabs/temperature_profile.py` Pattern B (lines 52-67) | Delete; replace with `build_sensor_role_map(loader, curve_index)` |
| `sensor_naming.get_dynamic_sensor_names()` | Leave in place — it serves a different purpose (sidebar display names using the firmware histogram). No change needed in this mission. |
| `curve_comparison.transform_sensor_assignments_to_roles()` | Deprecate long-term; in the near term, add an adaptor function or migrate its callers to the new canonical helper. Do not modify in this mission. |
| `src/data/curve_boundary_detector._SENSOR_COLUMNS` | Leave as module-private; import `SENSOR_LIST` from constants as a follow-up if desired, but it is not required to unblock the tab refactor. |
| `src/data/column_helpers._T1_T4` | Leave as module-private (it represents a domain-specific T1-T4 subset, not the full sensor list). |
| `sidebar.py:239-250` hardcoded lists | Replace with `list(SENSOR_LIST)` after SENSOR_LIST is introduced in Captain 4 migration sweep. |
| `src/visualization/plots.py:91, 214` hardcoded lists | Replace with `list(SENSOR_LIST)` in Captain 4; heatmap signature change in Captain 2. |
| `src/data/loader.py:865, 1404` hardcoded lists | Replace with `SENSOR_LIST` in Captain 4 migration sweep. |
| `src/analysis/curve_comparison.py:31` generated form | Replace with `SENSOR_LIST` in Captain 4 migration sweep. |

---

## 5. Recommended Captain Count for Follow-up Flotilla

**Branch:** `refactor/temperature-profile-canonical-roles`

**Estimated captains: 4 + 1 optional Red-cell navigator**

**Captain 1 — SENSOR_LIST + canonical helper module (TDD)**
Deliverable: `config/constants.py` gains `SENSOR_LIST`. New module `src/ui/sensor_role_helpers.py` with `build_sensor_role_map` and `build_sensor_label_map`. Failing tests written first (per project standing order) covering: correct role assignment for core/surface/internal/ambient; override-respecting behaviour; behaviour on None/missing sensors. No callers migrated yet.

**Captain 2 — Heatmap signature change + role-aware rendering (TDD)**
Deliverable: `plot_temperature_gradient_heatmap` accepts an optional `sensor_roles: dict[str, str] | None = None` parameter. When provided, y-axis labels reflect role names rather than firmware defaults. Call site at `tabs/temperature_profile.py:81` updated to pass `sensor_roles`. Failing tests written first covering: role-blind baseline (existing behaviour preserved when `sensor_roles=None`); role-aware y-axis labels; empty-input guard (S3 fix). Resolves B1.

**Captain 3 — Tab refactor: replace Patterns A/B; coalesce assignments calls (TDD)**
Deliverable: `tabs/temperature_profile.py` replaces lines 22-38 (Pattern A) and 52-67 (Pattern B) with calls to the canonical helpers. The two `get_sensor_assignments_with_overrides()` calls (lines 19 and 53) are merged into a single hoisted call. Line 53 explicit index fix applied (resolves B2 latent fragility). Failing tests written first for the render logic using the `render(state)` injection signature (S4 fix). No changes to plot functions.

**Captain 4 — Site-by-site SENSOR_LIST migration sweep**
Deliverable: Replace remaining hardcoded `['T1'..'T8']` literals in `sidebar.py:239-250`, `src/visualization/plots.py:91`, `src/data/loader.py:865, 1404`, `src/analysis/curve_comparison.py:31`, and any additional sites surfaced by `grep 'T1.*T2.*T3'`. Each replacement substitutes `list(SENSOR_LIST)` or `SENSOR_LIST` as appropriate. Failing regression tests written first to confirm no behaviour change at each site.

**Optional — Red-cell navigator (HMS Astute)**
Re-run the empirical scenarios from `astute-evidence.md` after each captain lands: (a) verify index-drift window is closed after Captain 3; (b) verify heatmap y-axis reflects role overrides after Captain 2; (c) verify suite passes (currently 8 pre-existing failures; no new failures introduced).

---

## Appendix: Astute Evidence Cross-Reference

| Claim in this report | Astute section |
|----------------------|----------------|
| B1 heatmap role-blindness confirmed | `astute-evidence.md §(b)` |
| B2 index-drift mechanism proven | `astute-evidence.md §(a)` |
| B2 latent (not continuously firing) | `astute-evidence.md §(a)` sidebar.py:144-147 note |
| Zero runtime-behaviour tests exist | `astute-evidence.md §(c)` |
| 8 pre-existing test failures (unrelated) | `astute-evidence.md` pytest baseline |
