"""Tests for the time-to-target percentage zero/None guard (#38).

quality_metrics.py divided ``time_to_target_minutes`` by the total bake time
with no guard. When the total bake time is 0 (degenerate / single-sample
curve) or NaN, or when ``time_to_target_minutes`` is None, the division
raised ZeroDivisionError or produced NaN. The computation is extracted into
a pure helper ``compute_time_to_target_fraction`` guarded by
``total_time > 0 and time_to_target is not None`` (else None).
"""

from __future__ import annotations

import math
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tabs.quality_metrics import compute_time_to_target_fraction  # noqa: E402


class TestComputeTimeToTargetFraction:
    def test_normal_case(self):
        assert compute_time_to_target_fraction(15.0, 30.0) == 0.5

    def test_none_time_to_target_returns_none(self):
        assert compute_time_to_target_fraction(None, 30.0) is None

    def test_zero_total_time_returns_none_not_zerodivision(self):
        # Must NOT raise ZeroDivisionError.
        assert compute_time_to_target_fraction(15.0, 0.0) is None

    def test_negative_total_time_returns_none(self):
        assert compute_time_to_target_fraction(15.0, -5.0) is None

    def test_nan_total_time_returns_none(self):
        assert compute_time_to_target_fraction(15.0, float("nan")) is None

    def test_none_total_time_returns_none(self):
        assert compute_time_to_target_fraction(15.0, None) is None

    def test_result_is_finite_when_defined(self):
        result = compute_time_to_target_fraction(10.0, 40.0)
        assert result is not None and math.isfinite(result)
