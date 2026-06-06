"""M2 — shared heat-up-score helper pin tests (M28).

``profile._heat_up_score`` is the single source of the
``time_to_60c -> time_to_100c -> -terminal_temp`` fallback chain that the
piecewise and Stefan fits each previously inlined twice.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.profile import _heat_up_score  # noqa: E402


class TestHeatUpScore:

    def test_prefers_time_to_60c(self):
        feats = {"T1": {"time_to_60c_seconds": 120.0, "time_to_100c_seconds": 300.0}}
        assert _heat_up_score(feats, "T1", 95.0) == 120.0

    def test_falls_back_to_time_to_100c(self):
        feats = {"T2": {"time_to_60c_seconds": None, "time_to_100c_seconds": 280.0}}
        assert _heat_up_score(feats, "T2", 95.0) == 280.0

    def test_falls_back_to_negative_terminal(self):
        feats = {"T3": {"time_to_60c_seconds": None, "time_to_100c_seconds": None}}
        assert _heat_up_score(feats, "T3", 95.0) == -95.0

    def test_missing_sensor_uses_negative_terminal(self):
        assert _heat_up_score({}, "T9", 88.0) == -88.0

    def test_colder_terminal_wins_when_no_crossings(self):
        # Among sensors with no t60/t100, the coldest terminal scores highest
        # (most core-like): -80 > -120.
        feats = {"T1": {}, "T2": {}}
        s1 = _heat_up_score(feats, "T1", 80.0)
        s2 = _heat_up_score(feats, "T2", 120.0)
        assert s1 > s2
