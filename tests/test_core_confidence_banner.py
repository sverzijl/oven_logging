"""Pure-helper tests for ``core_confidence_banner_text`` (M29).

The banner predicate is shared by the Temperature Profile, S-Curve, and
Spatial Evolution tabs. It maps ``(confidence, reason)`` to a
``(level, message)`` pair: ``"low"`` -> warning, ``"medium"`` -> caption,
``"high"`` / unknown -> no banner.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.core_confidence_banner import core_confidence_banner_text  # noqa: E402


class TestCoreConfidenceBannerText:

    def test_low_is_warning_and_mentions_metadata(self):
        level, message = core_confidence_banner_text(
            "low", "extrapolated past probe tip"
        )
        assert level == "warning"
        assert "metadata" in message.lower()
        assert "low" in message.lower()
        # The originating reason is preserved in the message.
        assert "extrapolated" in message.lower()

    def test_low_with_empty_reason_still_warns(self):
        level, message = core_confidence_banner_text("low", "")
        assert level == "warning"
        assert message
        assert "metadata" in message.lower()

    def test_medium_is_caption(self):
        level, message = core_confidence_banner_text("medium", "boundary anchor")
        assert level == "caption"
        assert "medium" in message.lower()
        assert "boundary anchor" in message

    def test_high_is_no_banner(self):
        assert core_confidence_banner_text("high", "clean fit") == (None, None)

    def test_unknown_is_no_banner(self):
        assert core_confidence_banner_text(None, None) == (None, None)
        assert core_confidence_banner_text("bogus", "x") == (None, None)
