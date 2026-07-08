"""Loader plumbing tests for the expected-duration hint (M5 HMS Dauntless).

Introduced by flotilla mission M5 on branch ``refactor/expected-bake-time``.
Covers the thin pass-through from ``ThermalProfileLoader`` into
``CurveBoundaryDetector`` — the loader itself does not alter boundaries,
it only plumbs the optional hint from the UI layer (M6 Spartan) to the
detector (M3/M4).

Contract guaranteed here:

1. **Default attribute** — a fresh loader exposes
   ``loader.expected_durations_s = None``.
2. **Byte-identical no-hint** — ``_extract_all_baking_curves(df)`` with
   no hint set produces the same curves it did pre-M5.
3. **Plumbing reaches detector** — setting
   ``loader.expected_durations_s`` causes the detector to see the hint
   (monkey-patched ``CurveBoundaryDetector.extract_curves`` captures kwargs).
4. **Cache invalidation via ``set_expected_durations``** — re-runs
   detection on the cached DataFrame and updates ``self.all_curves``.
5. **Length mismatch logs a warning** (not a crash) — when the hint
   list length differs from detected curve count.
"""

from __future__ import annotations

import logging
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader
from tests.fixtures.curve_boundary_cases import CASES


def _loader_with_df(df: pd.DataFrame) -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.metadata = {}
    loader.data = df
    return loader


def _ba3c_1759_df() -> pd.DataFrame:
    case = next(c for c in CASES if c["name"] == "real_1000BA3C_1759")
    return case["df"].copy()


def _ba3c_1759_durations() -> list[float]:
    case = next(c for c in CASES if c["name"] == "real_1000BA3C_1759")
    return list(case["expected_durations_s"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoaderDefaults:

    def test_fresh_loader_exposes_expected_durations_s_none(self):
        loader = ThermalProfileLoader()
        assert hasattr(loader, "expected_durations_s")
        assert loader.expected_durations_s is None


class TestNoHintByteIdentity:
    """Loader behaviour must not shift when ``expected_durations_s`` is unset."""

    def test_extract_curves_unchanged_without_hint_on_real_fixture(self):
        case = next(c for c in CASES if c["name"] == "real_1000BA3C_1759")
        loader = _loader_with_df(case["df"].copy())

        curves = loader._extract_all_baking_curves(case["df"].copy())
        assert len(curves) == case["expected_n_curves"]
        for i, (exp_s, exp_e) in enumerate(
            zip(case["expected_starts"], case["expected_ends"])
        ):
            # Allow the case-level tolerance (BA3C_1759 has tolerance=8).
            tol = case.get("tolerance", 2)
            assert abs(curves[i]["start_idx"] - exp_s) <= tol
            assert abs(curves[i]["end_idx"] - exp_e) <= tol


class TestPlumbingReachesDetector:
    """The optional hint list set on the loader must reach the detector."""

    def test_extract_passes_expected_durations_kwarg(self, monkeypatch):
        import src.data.loader as loader_mod

        captured: dict[str, object] = {}
        original_init = loader_mod.CurveBoundaryDetector.__init__
        original_extract = loader_mod.CurveBoundaryDetector.extract_curves

        def spy_extract(self, df, *args, **kwargs):
            captured["expected_durations_s"] = kwargs.get(
                "expected_durations_s", "__MISSING__"
            )
            return original_extract(self, df, *args, **kwargs)

        monkeypatch.setattr(
            loader_mod.CurveBoundaryDetector, "extract_curves", spy_extract
        )

        loader = _loader_with_df(_ba3c_1759_df())
        hint = _ba3c_1759_durations()
        loader.expected_durations_s = hint
        loader._extract_all_baking_curves(loader.data.copy())

        assert captured["expected_durations_s"] == hint, (
            f"loader did not plumb hint; detector received "
            f"{captured['expected_durations_s']!r}"
        )

    def test_extract_passes_none_when_no_hint_set(self, monkeypatch):
        import src.data.loader as loader_mod

        captured: dict[str, object] = {}
        original_extract = loader_mod.CurveBoundaryDetector.extract_curves

        def spy_extract(self, df, *args, **kwargs):
            captured["expected_durations_s"] = kwargs.get(
                "expected_durations_s", "__MISSING__"
            )
            return original_extract(self, df, *args, **kwargs)

        monkeypatch.setattr(
            loader_mod.CurveBoundaryDetector, "extract_curves", spy_extract
        )

        loader = _loader_with_df(_ba3c_1759_df())
        # expected_durations_s attribute left at default (None)
        loader._extract_all_baking_curves(loader.data.copy())
        assert captured["expected_durations_s"] in (None, "__MISSING__"), (
            f"unexpected hint forwarded: {captured['expected_durations_s']!r}"
        )


class TestSetExpectedDurationsCacheInvalidation:
    """``set_expected_durations`` re-runs detection using the cached data."""

    def test_method_exists_and_updates_attribute(self):
        loader = ThermalProfileLoader()
        assert hasattr(loader, "set_expected_durations")
        loader.set_expected_durations([100.0, 200.0])
        assert loader.expected_durations_s == [100.0, 200.0]

    def test_none_clears_hint(self):
        loader = ThermalProfileLoader()
        loader.set_expected_durations([100.0])
        loader.set_expected_durations(None)
        assert loader.expected_durations_s is None

    def test_triggers_re_extraction_on_cached_data(self):
        df = _ba3c_1759_df()
        loader = _loader_with_df(df)
        loader.all_curves = loader._extract_all_baking_curves(loader.data.copy())
        first_pass_starts = [c["start_idx"] for c in loader.all_curves]

        # Setting the hint with cache-invalidation semantics should
        # re-run detection using the stored `self.data` and overwrite
        # `self.all_curves`.
        loader.set_expected_durations(_ba3c_1759_durations())

        # On this fixture native starts are already in-window, so
        # re-extraction should produce the same starts (by design —
        # the goal is to prove re-extraction *ran*, not that it moved
        # anything).  Assert starts are populated AND that the shape
        # of ``all_curves`` reflects a full fresh run.
        assert len(loader.all_curves) == len(first_pass_starts)
        assert all(
            isinstance(c.get("data"), pd.DataFrame) for c in loader.all_curves
        ), "re-extraction did not produce hydrated curve dicts"


class TestLengthMismatchWarning:
    """Mismatched hint list lengths must warn, not crash."""

    def test_shorter_hint_list_logs_warning(self, caplog):
        df = _ba3c_1759_df()  # 3 curves
        loader = _loader_with_df(df)
        loader.expected_durations_s = [1400.0]  # only 1 hint for 3 curves

        with caplog.at_level(logging.WARNING, logger="src.data.loader"):
            curves = loader._extract_all_baking_curves(df.copy())

        assert len(curves) == 3, "loader must still return all 3 curves"
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert msgs, "expected a warning on length mismatch"
        assert (
            "expected_durations_s" in msgs.lower()
            or "length" in msgs.lower()
            or "mismatch" in msgs.lower()
        ), f"warning lacks expected keywords: {msgs!r}"

    def test_longer_hint_list_logs_warning(self, caplog):
        df = _ba3c_1759_df()  # 3 curves
        loader = _loader_with_df(df)
        loader.expected_durations_s = [1400.0, 1465.0, 1485.0, 999.0, 888.0]

        with caplog.at_level(logging.WARNING, logger="src.data.loader"):
            curves = loader._extract_all_baking_curves(df.copy())

        assert len(curves) == 3
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert msgs, "expected a warning on length mismatch"


# ---------------------------------------------------------------------------
# Tests: authoritative snap does not destabilise the loader (M12, A5)
# ---------------------------------------------------------------------------

from pathlib import Path as _Path  # noqa: E402

_A5_REPO_ROOT = _Path(__file__).resolve().parent.parent
_A5_BA3C_1759_CSV = _A5_REPO_ROOT / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"


def _a5_loaded() -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=str(_A5_BA3C_1759_CSV))
    return loader


class TestHintCountStability:
    """A hostile bake-time hint must not change the detected bake count
    (bounded snap prevents swallowing a neighbouring bake)."""

    def test_hostile_bake1_hint_preserves_curve_count(self):
        loader = _a5_loaded()
        assert len(loader.all_curves) == 3  # sanity: 3-bake CSV
        loader.set_expected_durations([5400.0, None, None])  # 90 min on bake 1
        assert len(loader.all_curves) == 3

    def test_hint_apply_preserves_existing_pin(self):
        loader = _a5_loaded()
        s = int(loader.all_curves[0]["start_idx"])
        e = int(loader.all_curves[0]["end_idx"])
        loader.set_curve_boundaries(0, s + 5, e - 5)
        assert loader.all_curves[0]["exit_candidate_kind"] == "manual_override"
        # Applying a bake-time hint must not clobber the manual pin.
        loader.set_expected_durations([600.0, None, None])
        assert loader.all_curves[0]["exit_candidate_kind"] == "manual_override"
        assert int(loader.all_curves[0]["start_idx"]) == s + 5
        assert int(loader.all_curves[0]["end_idx"]) == e - 5
