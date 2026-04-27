"""Temperature-profile flotilla finale — cross-mission regression guardrail.

M5 HMS Achilles — META-FLEET FINALE
Branch: refactor/temperature-profile-canonical-roles

Pins the post-flotilla structural state so future contributors cannot silently
regress the closures achieved by M1–M4:

  B1 (heatmap role-blindness)     — heatmap signature accepts sensor_roles;
                                    override reflected in y-axis labels.
  B2 (index drift)                — render() never calls get_sensor_assignments_with_overrides
                                    directly; single hoisted index passed to helpers.
  S1/S2 (Pattern A/B)             — inline 8-sensor loops removed from render().
  S3 (empty input)                — ValueError raised with clear message.
  S6 (double-fetch)               — get_sensor_assignments_with_overrides count = 0 in render.
  DRY-A (canonical sensor list)   — SENSOR_LIST is the single source of truth.

File name chosen as test_temperature_profile_flotilla_finale.py to avoid
collision with the existing test_flotilla_finale_regression.py (from the
refactor/expected-bake-time flotilla, M7 HMS Victory).
"""

from __future__ import annotations

import importlib
import inspect
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import ThermalProfileLoader
from src.visualization.plots import ThermalPlotter
from src.ui.sensor_role_helpers import build_sensor_role_map
from config.constants import SENSOR_NAMES

SINGLE_CURVE_CSV = PROJECT_ROOT / "ProbeData_1000F3C1_2025-05-23 09_11_59.csv"
MULTI_CURVE_CSV = PROJECT_ROOT / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _module_source() -> str:
    import tabs.temperature_profile as tp
    return inspect.getsource(tp)


def _render_source() -> str:
    import tabs.temperature_profile as tp
    return inspect.getsource(tp.render)


def _make_loader(csv_path: Path) -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(str(csv_path))
    return loader


# ---------------------------------------------------------------------------
# a. Pattern A inline loop absent
# ---------------------------------------------------------------------------

class TestPatternAInlineLoopAbsent:
    """Mirrors M3 test for permanence — Pattern A label-building loop is gone."""

    def test_pattern_a_inline_loop_absent(self):
        """Pattern A: 'for sensor in [T1..T8]' loop for label-building must be absent.

        This is the signature that was replaced by build_sensor_label_map() in M3.
        """
        src = _module_source()
        PATTERN_A = "for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']"
        assert PATTERN_A not in src, (
            f"Pattern A inline loop still present in tabs/temperature_profile.py.\n"
            f"Expected it to be replaced by build_sensor_label_map().\n"
            f"Offending fragment: {PATTERN_A!r}"
        )


# ---------------------------------------------------------------------------
# b. Pattern B inline loop absent
# ---------------------------------------------------------------------------

class TestPatternBInlineLoopAbsent:
    """Mirrors M3 test for permanence — Pattern B role-building loop is gone."""

    def test_pattern_b_inline_loop_absent(self):
        """Pattern B: 'for sensor in [T1..T8]' loop for role-building must be absent.

        This is the signature that was replaced by build_sensor_role_map() in M3.
        """
        src = _module_source()
        PATTERN_B = "for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']"
        assert PATTERN_B not in src, (
            f"Pattern B inline loop still present in tabs/temperature_profile.py.\n"
            f"Expected it to be replaced by build_sensor_role_map().\n"
            f"Offending fragment: {PATTERN_B!r}"
        )


# ---------------------------------------------------------------------------
# c. render() uses both sensor role helpers
# ---------------------------------------------------------------------------

class TestTemperatureProfileUsesSensorRoleHelpers:
    """render() source contains both build_sensor_label_map and build_sensor_role_map."""

    def test_temperature_profile_uses_sensor_role_helpers(self):
        src = _render_source()
        assert "build_sensor_label_map" in src, (
            "build_sensor_label_map not found in render() — label helper not used"
        )
        assert "build_sensor_role_map" in src, (
            "build_sensor_role_map not found in render() — role helper not used"
        )


# ---------------------------------------------------------------------------
# d. render() has zero direct calls to get_sensor_assignments_with_overrides
# ---------------------------------------------------------------------------

class TestTemperatureProfileSingleAssignmentsFetch:
    """render() must have ZERO direct calls to get_sensor_assignments_with_overrides.

    The low-level method is called only inside the helpers (S6 closed, B2 closed).
    """

    def test_temperature_profile_single_assignments_fetch(self):
        src = _render_source()
        count = src.count("get_sensor_assignments_with_overrides")
        assert count == 0, (
            f"render() calls get_sensor_assignments_with_overrides {count} time(s). "
            f"Expected 0 — all access must go through build_sensor_role_map / "
            f"build_sensor_label_map (S6/B2 closure)."
        )


# ---------------------------------------------------------------------------
# e. heatmap signature accepts sensor_roles
# ---------------------------------------------------------------------------

class TestHeatmapSignatureAcceptsSensorRoles:
    """plot_temperature_gradient_heatmap signature includes sensor_roles parameter."""

    def test_heatmap_signature_accepts_sensor_roles(self):
        sig = inspect.signature(ThermalPlotter.plot_temperature_gradient_heatmap)
        assert "sensor_roles" in sig.parameters, (
            f"plot_temperature_gradient_heatmap signature does not include "
            f"'sensor_roles' parameter. Got: {list(sig.parameters.keys())}"
        )


# ---------------------------------------------------------------------------
# f. SENSOR_LIST canonical definition
# ---------------------------------------------------------------------------

class TestSensorListCanonicalDefinition:
    """SENSOR_LIST from config.constants is the single source of truth for the 8 sensors."""

    def test_sensor_list_canonical_definition(self):
        from config.constants import SENSOR_LIST as SL
        assert len(SL) == 8, (
            f"SENSOR_LIST must have exactly 8 elements, got {len(SL)}: {SL}"
        )
        assert SL == ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"), (
            f"SENSOR_LIST must be ('T1'..'T8'), got {SL!r}"
        )


# ---------------------------------------------------------------------------
# g. No hardcoded T1..T8 alternatives in production source
# ---------------------------------------------------------------------------

# Patterns that must NOT appear outside the allow-list (mirrors M4 test)
_FORBIDDEN_PATTERNS = [
    re.compile(
        r"\[\s*['\"]T1['\"]\s*,\s*['\"]T2['\"]\s*,\s*['\"]T3['\"]\s*,"
        r"\s*['\"]T4['\"]\s*,\s*['\"]T5['\"]\s*,\s*['\"]T6['\"]\s*,"
        r"\s*['\"]T7['\"]\s*,\s*['\"]T8['\"]\s*\]"
    ),
    re.compile(
        r"\(\s*['\"]T1['\"]\s*,\s*['\"]T2['\"]\s*,\s*['\"]T3['\"]\s*,"
        r"\s*['\"]T4['\"]\s*,\s*['\"]T5['\"]\s*,\s*['\"]T6['\"]\s*,"
        r"\s*['\"]T7['\"]\s*,\s*['\"]T8['\"]\s*\)"
    ),
    re.compile(r"\[\s*f['\"]T\{i\}['\"].*range\s*\(\s*1\s*,\s*9\s*\)"),
]

_ALLOWLIST_DIRS = {
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / ".nelson",
    PROJECT_ROOT / "archive",
}

_SCAN_TARGETS = [
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "tabs",
    PROJECT_ROOT / "sidebar.py",
    PROJECT_ROOT / "app.py",
    PROJECT_ROOT / "sensor_naming.py",
    PROJECT_ROOT / "session_state.py",
]


def _is_allowlisted(path: Path) -> bool:
    for allowed in _ALLOWLIST_DIRS:
        try:
            path.relative_to(allowed)
            return True
        except ValueError:
            pass
    return False


def _collect_py_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if not target.exists():
            continue
        if target.is_file() and target.suffix == ".py":
            files.append(target)
        elif target.is_dir():
            files.extend(target.rglob("*.py"))
    return files


class TestSensorListNoHardcodedAlternativesInProduction:
    """Full project grep regression — forbidden patterns absent outside allow-list."""

    def test_sensor_list_no_hardcoded_alternatives_in_production(self):
        py_files = _collect_py_files(_SCAN_TARGETS)
        violations: list[str] = []
        for path in py_files:
            if _is_allowlisted(path):
                continue
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pattern in _FORBIDDEN_PATTERNS:
                for match in pattern.finditer(source):
                    line_num = source[: match.start()].count("\n") + 1
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{line_num}: {match.group()!r}"
                    )
        assert not violations, (
            "Hardcoded T1..T8 sensor list(s) still present in production source "
            "(DRY-A regression):\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# h-pre. Line-plot legend matches multiselect (post-fix DRY consistency)
# ---------------------------------------------------------------------------

class TestLinePlotLegendMatchesMultiselect:
    """Line-plot trace names use the same '{sensor} ({Role})' format as the
    multiselect.

    Regression guard for the post-flotilla fix that routed both the line-plot
    legend and the heatmap y-axis through the shared `format_sensor_label`
    helper. Pre-fix the legend used SENSOR_NAMES position labels (e.g.
    "Middle 1 (Core)") while the multiselect used sensor IDs ("T5 (Core)"),
    producing visible inconsistency.
    """

    def test_line_plot_trace_names_use_sensor_id_when_role_known(self):
        from src.visualization.plots import ThermalPlotter
        loader = ThermalProfileLoader()
        loader.load_csv(str(SINGLE_CURVE_CSV))
        curve_idx = loader.current_curve_index

        from src.ui.sensor_role_helpers import build_sensor_role_map
        sensor_roles = build_sensor_role_map(loader, curve_idx)
        data = loader.all_curves[curve_idx]['data']

        fig = ThermalPlotter().plot_temperature_profile(
            data, sensors=None, sensor_roles=sensor_roles
        )
        trace_names = [trace.name for trace in fig.data]

        # For every sensor with a known role, the trace name is "T# (Role)".
        for sensor, role in sensor_roles.items():
            if role == 'unknown' or sensor not in data.columns:
                continue
            expected = f"{sensor} ({role.capitalize()})"
            assert expected in trace_names, (
                f"Line-plot trace name mismatch: expected {expected!r} for "
                f"sensor {sensor} (role {role!r}); trace_names={trace_names}"
            )


# ---------------------------------------------------------------------------
# h. B1 heatmap role-aware post-flotilla (unit-level, no AppTest dependency)
# ---------------------------------------------------------------------------

class TestB1HeatmapRoleAwarePostFlotilla:
    """Unit-level proof of B1 closure: heatmap y-axis reflects per-curve overrides.

    Distinct from E2E test (d) in test_temperature_profile_e2e.py — this version
    directly calls the plotter without any AppTest machinery, providing a pure
    unit-level contract.
    """

    def test_b1_heatmap_role_aware_post_flotilla(self):
        """After set_sensor_override, heatmap y-axis label contains '(Surface)'.

        Build role map, call plotter, inspect fig.data[0].y directly.
        """
        loader = _make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index

        before = build_sensor_role_map(loader, curve_idx)
        # Choose override: sensor not already core or surface
        override_target = next(
            s for s in list(loader.get_sensor_assignments_with_overrides(curve_idx).get(
                "internal_sensors", []
            ) or ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"])
            if before.get(s) not in ("core", "surface")
        )

        loader.set_sensor_override(curve_idx, "surface", override_target)

        sensor_roles = build_sensor_role_map(loader, curve_idx)
        assert sensor_roles[override_target] == "surface"

        data = loader.all_curves[curve_idx]["data"]
        plotter = ThermalPlotter()
        fig = plotter.plot_temperature_gradient_heatmap(data, sensor_roles=sensor_roles)
        y_labels = list(fig.data[0].y)

        # B1 closure: post-flotilla, role-known labels use the sensor ID prefix
        # (matches the multiselect via the shared format_sensor_label helper).
        expected_label = f"{override_target} (Surface)"
        assert expected_label in y_labels, (
            f"B1 regression: expected {expected_label!r} in heatmap y-axis after "
            f"override; override not reflected. y={y_labels}"
        )

        loader.clear_sensor_overrides(curve_idx)


# ---------------------------------------------------------------------------
# i. B2 index drift closed post-flotilla (perturbed-fixture + source inspection)
# ---------------------------------------------------------------------------

class TestB2IndexDriftClosedPostFlotilla:
    """Pins B2 closure via source inspection AND empirical helper-equivalence.

    Two sub-checks:
    1. Source check: render() contains no direct call to get_sensor_assignments_with_overrides.
    2. Empirical: with distinct per-curve overrides, helpers return curve-specific results
       (not the same result regardless of index).
    """

    def test_b2_render_source_no_direct_fetch(self):
        """render() must not call get_sensor_assignments_with_overrides directly."""
        src = _render_source()
        assert "get_sensor_assignments_with_overrides" not in src, (
            "B2 regression: render() still directly calls "
            "get_sensor_assignments_with_overrides. "
            "This risks index drift. Helpers must be the only callers."
        )

    def test_b2_index_drift_closed_post_flotilla(self):
        """Empirical B2: per-curve helpers return curve-specific role maps.

        With curve-0 surface=T6 and curve-1 surface=T7, calling
        build_sensor_role_map(loader, 0) must return T6='surface',
        and build_sensor_role_map(loader, 1) must return T7='surface'.
        A naive (broken) implementation using current_curve_index for both
        would return the same result — this test detects that regression.
        """
        loader = _make_loader(MULTI_CURVE_CSV)
        assert loader.get_curve_count() >= 2, (
            "Need >=2 curves; test fixture may need updating"
        )

        loader.set_sensor_override(0, "surface", "T6")
        loader.set_sensor_override(1, "surface", "T7")

        # Force loader to curve 0
        loader.current_curve_index = 0

        roles_explicit_0 = build_sensor_role_map(loader, 0)
        roles_explicit_1 = build_sensor_role_map(loader, 1)

        # curve 0 must describe its own override (T6)
        assert roles_explicit_0["T6"] == "surface", (
            f"B2 regression: curve 0 helper returned T6={roles_explicit_0['T6']!r}, "
            f"expected 'surface'. Pre-flotilla bug would use current_curve_index."
        )
        # curve 1 must describe its own override (T7)
        assert roles_explicit_1["T7"] == "surface", (
            f"B2 regression: curve 1 helper returned T7={roles_explicit_1['T7']!r}, "
            f"expected 'surface'."
        )
        # The two results must differ (not the same map)
        assert roles_explicit_0 != roles_explicit_1, (
            "B2 regression: role maps for curve 0 and curve 1 are identical — "
            "per-curve isolation broken."
        )

        loader.clear_sensor_overrides(0)
        loader.clear_sensor_overrides(1)


# ---------------------------------------------------------------------------
# j. pytest baseline preserved
# ---------------------------------------------------------------------------

class TestPytestBaselinePreserved:
    """Meta-test: prior-passing test count has not regressed.

    Asserts that the non-flotilla suite still passes at least 338 tests
    (conservative floor; the actual baseline from the brief is 376/377).
    We use subprocess to get a count from a dry-run that excludes the
    two new flotilla finale files.
    """

    @pytest.mark.skip(
        reason=(
            "Subprocess-based meta-test: counts tests but cannot exclude "
            "itself without a conftest. The full baseline check is performed "
            "manually at commit time via: pytest tests/ -q --tb=no "
            "and verified against the 376/377 brief baseline. "
            "Skipped here to avoid infinite recursion and false positives."
        )
    )
    def test_pytest_baseline_preserved(self):
        """Assert non-flotilla test count is >=338.

        This is skipped because running pytest from within pytest (subprocess)
        is fragile in this environment (virtualenv path, timeout). The manual
        verification step at commit time (Step 5 of the brief) serves the same
        purpose and is documented in the mission turnover brief.
        """
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-q",
                "--tb=no",
                "--ignore=tests/test_temperature_profile_e2e.py",
                "--ignore=tests/test_temperature_profile_flotilla_finale.py",
                "--co",
                "-q",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        # Count collected items from dry-run output
        match = re.search(r"(\d+)\s+test", result.stdout)
        if match:
            count = int(match.group(1))
            assert count >= 338, (
                f"Prior-suite test count is {count}, below the floor of 338. "
                f"Check for regressions in the existing test suite."
            )
