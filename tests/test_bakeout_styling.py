"""Tests for robust bake-out recommendation styling (WAVE-A FOLLOW-UP b).

The Bake-Out tab styled recommendation lines by matching the substrings
"increase"/"reduce" to choose a warning vs success render. Wave A's reworded
#25 recommendation is a directional minutes line — "Approx. X more min above
93°C needed" / "Approx. X fewer min above 93°C needed" — which matches NEITHER
keyword, so an actionable underbake/overbake correction rendered as a green
success.

The analyzer emits a plain ``List[str]`` (no severity field, and it's
out-of-scope to change), so the styling is broadened in the tab via a pure
helper ``bakeout_rec_style`` that recognises directional language as a warning.
This is display-only.
"""

from __future__ import annotations

import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tabs.bakeout_analysis import bakeout_rec_style  # noqa: E402


class TestBakeoutRecStyle:
    def test_increase_is_warning(self):
        assert bakeout_rec_style(
            "Increase bake-out to 18% (currently 12.0%)"
        ) == "warning"

    def test_reduce_is_warning(self):
        assert bakeout_rec_style(
            "Reduce bake-out to 18% (currently 25.0%)"
        ) == "warning"

    def test_directional_more_minutes_is_warning(self):
        # The reworded #25 underbake line.
        assert bakeout_rec_style(
            "Approx. 3.2 more min above 93°C needed (directional estimate, "
            "not lab-calibrated)"
        ) == "warning"

    def test_directional_fewer_minutes_is_warning(self):
        # The reworded #25 overbake line.
        assert bakeout_rec_style(
            "Approx. 2.1 fewer min above 93°C needed (directional estimate, "
            "not lab-calibrated)"
        ) == "warning"

    def test_too_dry_is_warning(self):
        assert bakeout_rec_style(
            "Product too dry: 30.0% moisture (target: 35-38%)"
        ) == "warning"

    def test_excess_moisture_is_warning(self):
        assert bakeout_rec_style(
            "Excess moisture: 42.0% (target: 35-38%)"
        ) == "warning"

    def test_optimal_is_success(self):
        assert bakeout_rec_style(
            "Moisture content optimal: 36.5% (target: 35-38%)"
        ) == "success"

    def test_maintain_is_success(self):
        assert bakeout_rec_style("Maintain current settings") == "success"
