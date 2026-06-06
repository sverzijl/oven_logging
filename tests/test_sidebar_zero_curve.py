"""Tests for the sidebar load-outcome branch logic (#13, #28).

#13 — a CSV with 0 detected curves currently validates OK, says "Loaded
      successfully!", leaves the welcome screen and is then permanently
      skipped on re-upload (dedup keyed only on the filename). It must
      instead emit a WARNING and NOT be stored as a successful load.

#28 — a duplicate filename with *different content* is silently ignored
      (dedup keyed only on name). The load decision must surface a warning
      / disambiguate by content rather than silently skip.

The load-outcome decision is a pure function ``sidebar.classify_load_outcome``
keyed only on hashable values (curve count + an optional already-loaded
content signature) so it is unit-testable without the Streamlit runtime.
"""

from __future__ import annotations

import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sidebar  # noqa: E402


class TestClassifyLoadOutcome:
    def test_zero_curves_is_warning_not_success(self):
        outcome = sidebar.classify_load_outcome(
            filename="empty.csv", num_curves=0
        )
        assert outcome["status"] == "warning"
        assert outcome["store"] is False, (
            "#13: a 0-curve file must NOT be stored as a successful load"
        )
        assert "empty.csv" in outcome["message"]
        assert "no baking curve" in outcome["message"].lower()

    def test_single_curve_is_success_and_stored(self):
        outcome = sidebar.classify_load_outcome(
            filename="one.csv", num_curves=1
        )
        assert outcome["status"] == "success"
        assert outcome["store"] is True
        assert "one.csv" in outcome["message"]

    def test_multi_curve_reports_count_and_stored(self):
        outcome = sidebar.classify_load_outcome(
            filename="multi.csv", num_curves=3
        )
        assert outcome["status"] == "success"
        assert outcome["store"] is True
        assert "3" in outcome["message"]

    def test_duplicate_name_same_content_skipped(self):
        # Same filename, identical content signature -> genuinely already
        # loaded, nothing to do.
        outcome = sidebar.classify_load_outcome(
            filename="dup.csv",
            num_curves=2,
            existing_signature="abc123",
            new_signature="abc123",
        )
        assert outcome["status"] == "skip"
        assert outcome["store"] is False

    def test_duplicate_name_different_content_warns(self):
        # #28: same name, DIFFERENT content -> must not silently ignore.
        outcome = sidebar.classify_load_outcome(
            filename="dup.csv",
            num_curves=2,
            existing_signature="abc123",
            new_signature="zzz999",
        )
        assert outcome["status"] == "warning"
        assert outcome["store"] is False
        assert "dup.csv" in outcome["message"]
        # The message must point at the name-collision / differing content.
        msg = outcome["message"].lower()
        assert "already loaded" in msg or "different" in msg or "content" in msg
