"""Loader baseline-curve snapshot tests (M7 HMS Inspector).

After ``load_csv`` runs, ``loader.baseline_curves`` holds an immutable
snapshot of detector output with no hint and no override applied.
Subsequent ``set_expected_durations`` and ``set_curve_boundaries``
mutate ``loader.all_curves`` but must NOT touch ``baseline_curves`` —
the Boundary Review tab uses the baseline to show the operator what
auto-optimisation moved.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BA3C_1759_CSV = _REPO_ROOT / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"


def _load() -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=str(_BA3C_1759_CSV))
    return loader


class TestBaselineCurvesPopulated:

    def test_attribute_exists_before_load(self):
        loader = ThermalProfileLoader()
        assert hasattr(loader, "baseline_curves")
        assert loader.baseline_curves == []

    def test_populated_after_load(self):
        loader = _load()
        # BA3C_1759 — 3 bakes detected at load time.
        assert len(loader.baseline_curves) == 3

    def test_baseline_matches_initial_detection(self):
        """At load time, all_curves and baseline_curves agree on
        boundaries (no hint, no override applied yet)."""
        loader = _load()
        for b, c in zip(loader.baseline_curves, loader.all_curves):
            assert b["start_idx"] == c["start_idx"]
            assert b["end_idx"] == c["end_idx"]
            assert b["exit_candidate_kind"] == c["exit_candidate_kind"]


class TestBaselineImmutableAcrossOperations:
    """``set_expected_durations`` and ``set_curve_boundaries`` mutate
    ``all_curves`` but baseline_curves stays anchored to the initial
    no-hint, no-override detection."""

    def test_baseline_unchanged_after_set_expected_durations(self):
        loader = _load()
        snapshot = [
            (c["start_idx"], c["end_idx"], c["exit_candidate_kind"])
            for c in loader.baseline_curves
        ]
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        after = [
            (c["start_idx"], c["end_idx"], c["exit_candidate_kind"])
            for c in loader.baseline_curves
        ]
        assert snapshot == after

    def test_baseline_unchanged_after_set_curve_boundaries(self):
        loader = _load()
        snapshot = [
            (c["start_idx"], c["end_idx"], c["exit_candidate_kind"])
            for c in loader.baseline_curves
        ]
        c0 = loader.all_curves[0]
        loader.set_curve_boundaries(0, c0["start_idx"] + 5, c0["end_idx"] - 5)
        after = [
            (c["start_idx"], c["end_idx"], c["exit_candidate_kind"])
            for c in loader.baseline_curves
        ]
        assert snapshot == after

    def test_baseline_unchanged_after_clear_curve_boundaries(self):
        loader = _load()
        c0 = loader.all_curves[0]
        loader.set_curve_boundaries(0, c0["start_idx"] + 5, c0["end_idx"] - 5)
        snapshot = [
            (c["start_idx"], c["end_idx"], c["exit_candidate_kind"])
            for c in loader.baseline_curves
        ]
        loader.clear_curve_boundaries(0)
        after = [
            (c["start_idx"], c["end_idx"], c["exit_candidate_kind"])
            for c in loader.baseline_curves
        ]
        assert snapshot == after

    def test_baseline_data_independent_of_all_curves(self):
        """Mutating a baseline curve dict must not bleed into all_curves
        and vice versa."""
        loader = _load()
        loader.baseline_curves[0]["spurious_marker"] = True
        assert "spurious_marker" not in loader.all_curves[0]
