"""Fixture schema tests for CurveBoundaryDetector regression cases.

Introduced by flotilla mission M1 HMS Illustrious (branch
``refactor/expected-bake-time``).  Pins the *shape* of the new optional
``expected_durations_s`` and ``duration_tolerance_frac`` fields added to
``CASES`` so that subsequent missions (M3 Agincourt end-refinement, M4 Hood
start-refinement) can rely on the annotation contract without having to re-read
every case.

Contract
--------
* Every real case in ``CASES`` has an ``expected_durations_s`` key.
* The value is either ``None`` (used for truncated logs where duration is
  physically undefined) or a ``list[float]`` with exactly
  ``case["expected_n_curves"]`` entries.
* Each float is positive and agrees with the index-based ground truth to
  within one sample period (5 s assumed default — see ``Sample Period: 5000``
  in the real CSV headers).
* ``duration_tolerance_frac`` is *optional* — when present it must be a
  positive float ≤ 1.0.  Most cases omit it and fall back to the
  ``EXPECTED_DURATION_TOLERANCE_FRAC`` config default.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fixtures.curve_boundary_cases import CASES

_SAMPLE_PERIOD_S = 5.0  # All real CSVs in the fixture set use 5 s per sample.
_ONE_SAMPLE_TOLERANCE_S = _SAMPLE_PERIOD_S


class TestFixtureSchemaExpectedDurations:
    """Schema-shape contract for the optional per-curve duration hint fields."""

    def test_every_real_case_has_expected_durations_key(self):
        """Every real-CSV case must declare ``expected_durations_s`` explicitly.

        The field is optional on synthetic cases (they exist to exercise
        adversarial behaviour without hint influence) but REQUIRED on real
        cases so that M3/M4 refinement logic can rely on it.
        """
        for case in CASES:
            if case["source"] != "real":
                continue
            assert "expected_durations_s" in case, (
                f"{case['name']}: real-CSV case missing 'expected_durations_s' key"
            )

    def test_expected_durations_shape_matches_curve_count(self):
        """Value is ``None`` (truncated) or a list of length ``expected_n_curves``."""
        for case in CASES:
            if case["source"] != "real":
                continue
            durations = case.get("expected_durations_s")
            if durations is None:
                # None is only valid when the log is truncated — hint is
                # physically meaningless for an incomplete bake.
                assert case.get("truncated") is True, (
                    f"{case['name']}: expected_durations_s=None requires truncated=True "
                    f"(got truncated={case.get('truncated')})"
                )
                continue
            assert isinstance(durations, list), (
                f"{case['name']}: expected_durations_s must be list or None, "
                f"got {type(durations).__name__}"
            )
            assert len(durations) == case["expected_n_curves"], (
                f"{case['name']}: expected_durations_s has {len(durations)} entries "
                f"but expected_n_curves={case['expected_n_curves']}"
            )
            for i, d in enumerate(durations):
                assert isinstance(d, float), (
                    f"{case['name']} curve-{i}: expected_durations_s[{i}] "
                    f"must be float, got {type(d).__name__}"
                )
                assert d > 0.0, (
                    f"{case['name']} curve-{i}: duration must be positive, got {d}"
                )

    def test_expected_durations_agree_with_index_ground_truth(self):
        """Each duration is within one sample period of (end_idx - start_idx) × dt."""
        for case in CASES:
            if case["source"] != "real":
                continue
            durations = case.get("expected_durations_s")
            if durations is None:
                continue
            starts = case["expected_starts"]
            ends = case["expected_ends"]
            for i, (s, e, d) in enumerate(zip(starts, ends, durations)):
                # Index-based estimate using the default 5 s sample period.
                idx_based = float((e - s) * _SAMPLE_PERIOD_S)
                assert abs(d - idx_based) <= _ONE_SAMPLE_TOLERANCE_S, (
                    f"{case['name']} curve-{i}: expected_durations_s={d} s "
                    f"disagrees with (end-start)×dt={idx_based} s by more than "
                    f"one sample ({_ONE_SAMPLE_TOLERANCE_S} s)"
                )

    def test_duration_tolerance_frac_optional_and_bounded(self):
        """``duration_tolerance_frac`` is optional; when present 0 < x ≤ 1."""
        for case in CASES:
            if "duration_tolerance_frac" not in case:
                continue  # optional
            frac = case["duration_tolerance_frac"]
            assert isinstance(frac, float), (
                f"{case['name']}: duration_tolerance_frac must be float, "
                f"got {type(frac).__name__}"
            )
            assert 0.0 < frac <= 1.0, (
                f"{case['name']}: duration_tolerance_frac must be in (0, 1], got {frac}"
            )

    def test_truncated_real_case_has_none_durations(self):
        """Truncated real logs must declare ``expected_durations_s=None``.

        Anchors the convention that a hint is physically meaningless on a log
        that ends mid-bake — M3/M4 refinement must short-circuit on it.
        """
        truncated_real = [
            c for c in CASES
            if c["source"] == "real" and c.get("truncated") is True
        ]
        assert len(truncated_real) >= 1, (
            "No truncated real case in CASES — this test relies on at least one "
            "(currently real_1000BA3C_0946)"
        )
        for case in truncated_real:
            assert case.get("expected_durations_s") is None, (
                f"{case['name']}: truncated real case must have "
                f"expected_durations_s=None, got {case.get('expected_durations_s')!r}"
            )
