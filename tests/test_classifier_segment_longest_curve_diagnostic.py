"""M5 — _segment_longest_curve diagnostic pin tests (M28).

The helper previously swallowed ALL exceptions silently (``except Exception``),
hiding genuine detector bugs. It now narrows to ``(ImportError, ValueError,
KeyError)`` and emits a ``logging.warning`` on the fallback path.
"""

from __future__ import annotations

import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.data.curve_boundary_detector as cbd  # noqa: E402
from src.data.spatial_reconstruction import classifier as clf  # noqa: E402


class TestSegmentLongestCurveDiagnostic:

    def test_fallback_logs_warning_and_returns_full_df(self, monkeypatch, caplog):
        class _BoomDetector:
            def __init__(self, cfg):
                raise ValueError("simulated detector failure")

        monkeypatch.setattr(cbd, "CurveBoundaryDetector", _BoomDetector)
        df = pd.DataFrame({"T1": [20.0, 50.0, 90.0]})
        with caplog.at_level(logging.WARNING):
            out = clf._segment_longest_curve(df)
        assert out is df  # unchanged full DataFrame
        assert any("fell back" in r.getMessage() for r in caplog.records), (
            "expected a warning on the silent-fallback path"
        )

    def test_no_warning_on_the_happy_path(self, monkeypatch, caplog):
        class _OkDetector:
            def __init__(self, cfg):
                pass

            def extract_curves(self, df):
                return [{"start_idx": 0, "end_idx": len(df) - 1}]

        monkeypatch.setattr(cbd, "CurveBoundaryDetector", _OkDetector)
        df = pd.DataFrame({"T1": [20.0, 50.0, 90.0, 99.0]})
        with caplog.at_level(logging.WARNING):
            out = clf._segment_longest_curve(df)
        assert len(out) == len(df)
        assert not any(
            "fell back" in r.getMessage() for r in caplog.records
        ), "happy path must not log a fallback warning"
