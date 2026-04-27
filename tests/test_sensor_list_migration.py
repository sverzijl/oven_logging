"""
Regression guard: ensures hardcoded T1..T8 sensor lists have been fully
migrated to SENSOR_LIST from config.constants.

Part of M4 HMS Spey SENSOR_LIST sweep migration.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Patterns that must NOT appear in production source (outside allow-list).
# These match only the canonical 8-element forms.
# ---------------------------------------------------------------------------
FORBIDDEN_PATTERNS = [
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

# Root of the repository (two levels up from this file: tests/ -> repo root)
REPO_ROOT = Path(__file__).parent.parent

# Files / directories that ARE allowed to contain these patterns.
ALLOWLIST_DIRS = {
    REPO_ROOT / "config",     # canonical definition lives here
    REPO_ROOT / "tests",      # fixture purposes
    REPO_ROOT / ".nelson",    # review artefacts
    REPO_ROOT / "archive",    # legacy scripts, not production
}

# Production source files / directories to scan.
SCAN_TARGETS = [
    REPO_ROOT / "src",
    REPO_ROOT / "tabs",
    REPO_ROOT / "sidebar.py",
    REPO_ROOT / "app.py",
    REPO_ROOT / "sensor_naming.py",
    REPO_ROOT / "session_state.py",
]


def _is_allowlisted(path: Path) -> bool:
    for allowed in ALLOWLIST_DIRS:
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


# ---------------------------------------------------------------------------
# Test 1 — no hardcoded T1..T8 lists in production source
# ---------------------------------------------------------------------------

def test_no_hardcoded_sensor_list_in_production_source():
    """All canonical T1..T8 lists must have been replaced with SENSOR_LIST."""
    py_files = _collect_py_files(SCAN_TARGETS)
    violations: list[str] = []

    for path in py_files:
        if _is_allowlisted(path):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(source):
                line_num = source[: match.start()].count("\n") + 1
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_num}: {match.group()!r}"
                )

    assert not violations, (
        "Hardcoded T1..T8 sensor list(s) still present in production source:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Test 2 — migrated files import SENSOR_LIST; _SENSOR_COLUMNS resolved
# ---------------------------------------------------------------------------

MIGRATED_FILES = [
    REPO_ROOT / "sidebar.py",
    REPO_ROOT / "src" / "visualization" / "plots.py",
    REPO_ROOT / "src" / "data" / "loader.py",
    REPO_ROOT / "src" / "analysis" / "curve_comparison.py",
    REPO_ROOT / "src" / "data" / "curve_boundary_detector.py",
]


def _contains_sensor_list_import(path: Path) -> bool:
    """Return True if the file imports SENSOR_LIST from config.constants.

    Handles both single-line and parenthesised multi-line import forms.
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    # Single-line: from config.constants import ..., SENSOR_LIST, ...
    if re.search(r"from\s+config\.constants\s+import\b.*\bSENSOR_LIST\b", source):
        return True
    # Multi-line parenthesised: from config.constants import (\n    ...\n    SENSOR_LIST\n)
    if re.search(
        r"from\s+config\.constants\s+import\s*\([^)]*\bSENSOR_LIST\b",
        source,
        re.DOTALL,
    ):
        return True
    return False


def test_sensor_list_imported_at_known_sites():
    """Every migrated file must import SENSOR_LIST from config.constants."""
    missing: list[str] = []
    for path in MIGRATED_FILES:
        if not path.exists():
            missing.append(f"{path.relative_to(REPO_ROOT)} (file not found)")
            continue
        if not _contains_sensor_list_import(path):
            missing.append(str(path.relative_to(REPO_ROOT)))

    assert not missing, (
        "The following files do not import SENSOR_LIST from config.constants:\n"
        + "\n".join(missing)
    )


def test_curve_boundary_detector_no_private_sensor_columns():
    """_SENSOR_COLUMNS in curve_boundary_detector should be deleted (Option A)."""
    path = REPO_ROOT / "src" / "data" / "curve_boundary_detector.py"
    assert path.exists(), f"Expected file not found: {path}"
    source = path.read_text(encoding="utf-8", errors="replace")
    assert "_SENSOR_COLUMNS" not in source, (
        "curve_boundary_detector.py still contains _SENSOR_COLUMNS; "
        "expected it to be deleted and replaced with SENSOR_LIST (Option A)."
    )
