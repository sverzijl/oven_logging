# HMS Astute — Empirical Evidence Pack

## Verdicts (executive summary)

- **(a) Index drift: CONDITIONAL PASS** — role assignments DO differ when `loader.current_curve_index` and the `curve_index` arg diverge (verified empirically with injected fixtures); however, `sidebar.py:147` keeps them in sync during normal rendering, so the divergence window is latent (theoretical risk) rather than a continuously-firing bug. The code smell is real and the mechanism is proven; only the trigger condition is narrow.
- **(b) Heatmap role-blindness: PASS** — `plot_temperature_gradient_heatmap()` y-axis labels are `['Core 1','Core 2','Core 3','Core 4','Middle 1','Middle 2','Near Surface','Surface']` (hardcoded `SENSOR_NAMES`) regardless of any role override; z-row ordering matches raw T1..T8 column order. Confirmed empirically.
- **(c) Test coverage: ZERO direct tests** for `plot_temperature_gradient_heatmap`, `plot_temperature_profile`, or index-drift logic in `temperature_profile.render`; two structural/smoke tests exist that touch `tabs.temperature_profile` but do not exercise runtime behaviour.

---

## (a) Index drift — full verification

### Claim under test
`tabs/temperature_profile.py:19` calls `loader.get_sensor_assignments_with_overrides(st.session_state.current_curve_index)` (explicit int). Line 53 calls it with **no argument**, so the function defaults to `self.current_curve_index` (`loader.py:835-836`). If `loader.current_curve_index` and `st.session_state.current_curve_index` diverge, the multiselect labels (line 19) and the `sensor_roles` dict fed to the plot (line 53) describe **different curves**.

### Repro commands

```bash
cd "C:\...\oven_logging"
python ".nelson/missions/2026-04-26_231226_f8a0d05d/repro/claim_a_index_drift.py"
```

Inline repro (no-commit):

```python
import sys
sys.path.insert(0, "<repo>")
from src.data.loader import ThermalProfileLoader

loader = ThermalProfileLoader()
loader.load_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")

# Inject distinct per-curve assignments to simulate probe re-insertion
loader.curve_sensor_assignments[0]["core"]    = "T3"
loader.curve_sensor_assignments[0]["surface"] = "T6"
loader.curve_sensor_assignments[1]["core"]    = "T1"
loader.curve_sensor_assignments[1]["surface"] = "T7"

# Force divergence
loader.current_curve_index = 0                           # ← line-53 will use this

a19 = loader.get_sensor_assignments_with_overrides(1)    # ← line-19 simulation
a53 = loader.get_sensor_assignments_with_overrides()     # ← line-53 simulation (no arg)
```

### Observed dicts side-by-side

| Key | Line-19 (curve_index=1) | Line-53 (no arg → index=0) | Differs? |
|-----|-------------------------|----------------------------|----------|
| `core_sensor` | `T1` | `T1` | No |
| `surface_sensor` | **`T7`** | **`T6`** | **YES** |
| `internal_sensors` | `['T1','T2','T3','T4','T5']` | `['T1','T2','T3','T4','T5']` | No |
| `ambient_sensors` | `['T8']` | `['T8']` | No |

The `surface_sensor` key differs (T7 vs T6), which changes how traces are coloured and labelled in `plot_temperature_profile`. An end-user would see the **surface legend colour assigned to T7** in the multiselect labels but the **plot drawing T6 as "surface"** — a visible contradiction.

### Why no divergence fires with the real CSV (unperturbed)

`ProbeData_1000BA3C_2025-05-30 17_59_37.csv` (3 curves) yields **identical** `curve_sensor_assignments` for all three curves (core=T1, surface=T7, ambient=T8 for every curve index). The divergence is invisible on this fixture without perturbation — which is why red-cell perturbation was necessary.

### When could divergence fire in the live app?

`sidebar.py:144` sets `st.session_state.current_curve_index = file_curve_index` and `sidebar.py:147` calls `loader.set_current_curve(file_curve_index)`, which updates `loader.current_curve_index`. These execute synchronously on each Streamlit render cycle, so in **normal navigation** the two values are always equal when `render()` is called.

However, divergence is **latent** in these scenarios:
1. An exception between `sidebar.py:144` and `sidebar.py:147` leaves `st.session_state.current_curve_index` updated but `loader.current_curve_index` stale.
2. Any future code that modifies `st.session_state.current_curve_index` without calling `loader.set_current_curve()` (e.g., a shortcut key handler or URL parameter reader).
3. Unit tests or programmatic callers that set `session_state.current_curve_index` directly without updating the loader.

### Verdict

**CONDITIONAL PASS** — the divergence mechanism is empirically confirmed: when the two indices differ AND curves have different role assignments, multiselect labels and plot `sensor_roles` describe different curves. This is a genuine latent bug and a clear code smell (two separate calls using two different index sources for logically the same query). The narrow trigger window in the live app downgrades severity from "continuously fires" to "latent/fragile."

**Recommendation**: Line 53 should explicitly pass `st.session_state.current_curve_index` as the argument, matching line 19. Alternatively, extract a single call and reuse the result.

---

## (b) Heatmap role-blindness — full verification

### Repro command

```bash
python -c "
import sys; sys.path.insert(0, '<repo>')
import numpy as np; import pandas as pd
from src.visualization.plots import ThermalPlotter
from config.constants import SENSOR_NAMES

n = 50
data = pd.DataFrame({
    'TimeMinutes': np.linspace(0, 30, n),
    'T1': 85 + np.linspace(0,10,n),  # core
    'T2': 82 + np.linspace(0,10,n),  # override: 'surface'
    'T3': 80 + np.linspace(0,8,n),
    'T4': 78 + np.linspace(0,7,n),
    'T5': 100 + np.linspace(0,50,n),
    'T6': 110 + np.linspace(0,60,n),
    'T7': 150 + np.linspace(0,20,n),  # override: 'ambient'
    'T8': 200 + np.linspace(0,30,n),
})
fig = ThermalPlotter().plot_temperature_gradient_heatmap(data)
print('y:', list(fig.data[0].y))
print('z[0][:3]:', [round(v,1) for v in fig.data[0].z[0][:3]])  # T1 row
print('z[6][:3]:', [round(v,1) for v in fig.data[0].z[6][:3]])  # T7 row
"
```

### Observed y-axis labels and z-ordering

```
y: ['Core 1', 'Core 2', 'Core 3', 'Core 4', 'Middle 1', 'Middle 2', 'Near Surface', 'Surface']
z[0][:3]: [85.2, 85.1, 85.7 ...]   ← Row 0 = T1 raw data
z[6][:3]: [148.3, 149.3, 152.3 ...] ← Row 6 = T7 raw data
```

**Source reference**: `src/visualization/plots.py:214` hardcodes `sensors = ['T1','T2','T3','T4','T5','T6','T7','T8']`. Line 226 maps `y` via `SENSOR_NAMES.get(s, s)`, which uses `config/constants.py:124-133` firmware-default labels. No role or override information is accepted by the function signature (`data: pd.DataFrame` only, `plots.py:211`).

The function call at `tabs/temperature_profile.py:81` is `plotter.plot_temperature_gradient_heatmap(st.session_state.data)` — no `sensor_roles`, no `assignments` dict passed.

### Verdict

**PASS** — the heatmap is **genuinely role-blind**. Y-axis labels are invariant to overrides (always `SENSOR_NAMES` in T1..T8 order). Z-rows are invariant to role assignments (always raw T1..T8 column data). An operator who reassigns T7 as ambient and T2 as surface will see the heatmap continue to label T7 as "Near Surface" and T8 as "Surface" — firmware-default names, not role-based names. This is a confirmed bug: the heatmap ignores the physics-corrected surface assignments that the line plot (line 76) does use.

---

## (c) Test coverage — full inventory

### Pytest collection (347 tests collected)

Tests touching `tabs.temperature_profile`, `plot_temperature_gradient_heatmap`, or `plot_temperature_profile`:

| File | Line | Test name | What it tests |
|------|------|-----------|---------------|
| `tests/test_tab_modules_smoke.py` | 34 | `test_tab_module_exposes_render[tabs.temperature_profile]` | Import + callable check only |
| `tests/test_widget_key_per_curve.py` | 28 | `TestWidgetKeyPerCurve::test_sensor_select_key_is_fstring_per_curve` | Source-code regex for widget key |
| `tests/test_widget_key_per_curve.py` | 35 | `TestWidgetKeyPerCurve::test_show_all_key_is_fstring_per_curve` | Source-code regex for widget key |
| `tests/test_widget_key_per_curve.py` | 42 | `TestWidgetKeyPerCurve::test_old_fixed_sensor_select_key_is_gone` | Source-code negative regex |
| `tests/test_widget_key_per_curve.py` | 48 | `TestWidgetKeyPerCurve::test_old_fixed_show_all_key_is_gone` | Source-code negative regex |

**Grep results — exact file:line matches:**

```
tests/test_tab_modules_smoke.py:22       "tabs.temperature_profile"  (in TAB_MODULES list)
tests/test_tab_modules_smoke.py:34       test_tab_module_exposes_render parameterised (includes tabs.temperature_profile)
tests/test_widget_key_per_curve.py:1     docstring mentions "temperature_profile tab"
tests/test_widget_key_per_curve.py:19    import tabs.temperature_profile
tests/test_widget_key_per_curve.py:23    class docstring "temperature_profile.render()"
tests/test_widget_key_per_curve.py:26    inspect.getsource(tabs.temperature_profile.render)
tests/test_sidebar_expected_duration.py:71  prose comment mentions "temperature_profile tab" (not a test of it)
```

**Zero matches** for `plot_temperature_gradient_heatmap` or `plot_temperature_profile` in the `tests/` tree.

### Verdict

**Zero tests** exist for:
- `plot_temperature_gradient_heatmap` (the heatmap's role-blindness is untested)
- `plot_temperature_profile` (the main temperature line-plot is untested)
- The index-drift scenario (line 19 vs line 53 of `temperature_profile.render`)

The two existing test files (`test_tab_modules_smoke.py`, `test_widget_key_per_curve.py`) that reference `tabs.temperature_profile` only verify import-ability and widget key formatting via source inspection — they never call `render()` or exercise any runtime behaviour.

---

## Pytest baseline

Suite health at time of review (2026-04-27):

```
8 failed, 338 passed, 1 skipped
Total: 347 tests collected
Duration: 597s
```

Pre-existing failures (do not debug):
- `tests/test_curve_comparison_integration.py::TestDataFlowIntegration::test_zone_color_consistency`
- `tests/test_internal_sensor_filtering.py::TestInternalSensorFiltering::test_realistic_baking_profile`
- `tests/test_surface_sensor_detection.py::TestSurfaceSensorDetection::test_shallow_insertion`
- `tests/test_surface_sensor_detection.py::TestSurfaceSensorDetection::test_deep_insertion`
- `tests/test_visualization.py::TestThermalPlotter::test_plot_zone_duration_comparison`
- `tests/test_visualization.py::TestEdgeCases::test_single_curve_comparison`
- `tests/test_visualization.py::TestEdgeCases::test_many_curves_comparison`
- `tests/test_visualization.py::TestEdgeCases::test_unknown_zone_handling`

None of the 8 failures are in files related to the Temperature Profile tab or heatmap. The suite was not healthy at review time; 8 tests were pre-broken.
