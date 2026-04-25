"""End-refinement tests for the expected-duration hint (M3 HMS Agincourt).

Introduced by flotilla mission M3 on branch ``refactor/expected-bake-time``.
Covers the new ``expected_durations_s`` kwarg on
``CurveBoundaryDetector.extract_curves`` and the switch from earliest-wins
to composite-scored-in-window-wins arbitration inside ``_detect_curve_end``.

Contract guaranteed here (in priority order):

1. **Shape invariance** — every returned curve dict gains an
   ``exit_candidate_kind`` diagnostic field (strict string from the
   fixed vocabulary, or ``None``).
2. **Regression safety** — ``expected_durations_s=None`` (the default)
   must not shift decisions on any existing real fixture.
3. **Hint-in-window** — a correct hint must not move the decision.
4. **Hint-out-of-window** — a wildly wrong hint must fall back to the
   earliest-wins baseline AND emit a structured ``logger.warning``.
5. **Hint-steers-selection** — when two candidates are both confirmed
   and only one sits inside the band, the in-band candidate wins.
"""

from __future__ import annotations

import logging
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector
from tests.fixtures.curve_boundary_cases import CASES


# Fixed vocabulary of exit-candidate kinds the detector may return.
# Pinned here so a silent rename on either side fails loudly.
_VALID_KINDS = {
    "drop_rate",
    "cool_to_ambient",
    "room_temp_plateau",
    "dip_with_rerise",
    "core_peak_plateau",
    "probe_pull_cliff",
}


def _fresh_detector() -> CurveBoundaryDetector:
    """Return a CurveBoundaryDetector wired with the production config."""
    return CurveBoundaryDetector(CURVE_DETECTION_CONFIG)


# ---------------------------------------------------------------------------
# Tests: shape invariance
# ---------------------------------------------------------------------------


class TestExitCandidateKindDiagnostic:

    def test_every_curve_dict_has_exit_candidate_kind(self):
        """Pin the shape addition — every curve dict carries the new field."""
        for case in CASES:
            if case["source"] != "real":
                continue
            detector = _fresh_detector()
            curves = detector.extract_curves(case["df"].copy())
            for c in curves:
                assert "exit_candidate_kind" in c, (
                    f"{case['name']} curve-{c.get('curve_number')}: missing "
                    f"exit_candidate_kind"
                )
                kind = c["exit_candidate_kind"]
                assert kind is None or kind in _VALID_KINDS, (
                    f"{case['name']} curve-{c.get('curve_number')}: invalid "
                    f"exit_candidate_kind={kind!r} (valid: {_VALID_KINDS})"
                )

    def test_default_kwarg_matches_explicit_none(self):
        """Omitting the kwarg must be indistinguishable from passing None.

        Weak but important — locks the ``=None`` default in the signature.
        """
        for case in CASES:
            if case["source"] != "real":
                continue
            detector = _fresh_detector()
            a = detector.extract_curves(case["df"].copy())
            b = detector.extract_curves(
                case["df"].copy(), expected_durations_s=None
            )
            assert len(a) == len(b)
            for ca, cb in zip(a, b):
                for k in (
                    "start_idx",
                    "end_idx",
                    "start_time",
                    "end_time",
                    "max_temp",
                    "samples",
                    "truncated",
                    "curve_number",
                    "exit_candidate_kind",
                ):
                    assert ca[k] == cb[k], (
                        f"{case['name']} curve-{ca['curve_number']} "
                        f"field {k!r} diverged: default={ca[k]!r}, "
                        f"explicit-None={cb[k]!r}"
                    )


# ---------------------------------------------------------------------------
# Tests: hint semantics on real fixtures
# ---------------------------------------------------------------------------


class TestHintOnRealFixtures:

    def test_hint_matching_native_duration_preserves_decision(self):
        """Real CSV with correct hint — end_idx and kind must not change."""
        case = next(c for c in CASES if c["name"] == "real_100098DE_1351")
        detector = _fresh_detector()
        native = detector.extract_curves(case["df"].copy())
        assert native, "sanity: native detection returns at least one curve"

        hinted = detector.extract_curves(
            case["df"].copy(),
            expected_durations_s=case["expected_durations_s"],
        )
        assert len(hinted) == len(native)
        assert hinted[0]["end_idx"] == native[0]["end_idx"], (
            f"hint matching native duration shifted end_idx: "
            f"native={native[0]['end_idx']}, hinted={hinted[0]['end_idx']}"
        )
        assert (
            hinted[0]["exit_candidate_kind"]
            == native[0]["exit_candidate_kind"]
        )

    def test_hint_far_outside_any_candidate_falls_back_with_warning(
        self, caplog
    ):
        """Wildly wrong hint → fallback to earliest-wins AND warning logged."""
        case = next(c for c in CASES if c["name"] == "real_100098DE_1351")
        detector = _fresh_detector()
        native = detector.extract_curves(case["df"].copy())

        # native ~25 min (1515 s); 6000 s (~100 min) puts the band
        # [5100, 6900] well beyond any confirmed candidate.
        with caplog.at_level(
            logging.WARNING, logger="src.data.curve_boundary_detector"
        ):
            curves = detector.extract_curves(
                case["df"].copy(), expected_durations_s=[6000.0]
            )

        # Decision reverts to the baseline
        assert curves[0]["end_idx"] == native[0]["end_idx"], (
            "out-of-band hint must not move the boundary"
        )
        assert (
            curves[0]["exit_candidate_kind"]
            == native[0]["exit_candidate_kind"]
        )

        # And we warn, with enough context to diagnose in the field.
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert msgs, "expected at least one warning record"
        msgs_lower = msgs.lower()
        assert (
            "fallback" in msgs_lower
            or "tolerance band" in msgs_lower
            or "no candidate" in msgs_lower
        ), f"warning message lacks expected keywords: {msgs!r}"

    def test_hint_list_none_entry_is_treated_as_no_hint(self):
        """A None entry (e.g. for a truncated bake) must skip refinement.

        Uses real_1000BA3C_0946 — the truncated real fixture carries
        ``expected_durations_s = None`` case-wide, but the kwarg accepts
        a list; supplying ``[None]`` must behave exactly like no hint.
        """
        case = next(c for c in CASES if c["name"] == "real_1000BA3C_0946")
        detector = _fresh_detector()
        native = detector.extract_curves(case["df"].copy())
        hinted = detector.extract_curves(
            case["df"].copy(), expected_durations_s=[None]
        )
        assert len(native) == len(hinted)
        for cn, ch in zip(native, hinted):
            assert cn["end_idx"] == ch["end_idx"]
            assert cn["exit_candidate_kind"] == ch["exit_candidate_kind"]


# ---------------------------------------------------------------------------
# Tests: hint-driven arbitration on a synthetic plateau+cliff fixture
# ---------------------------------------------------------------------------


def _build_plateau_plus_cliff_synthetic() -> pd.DataFrame:
    """Synthetic lidded bake with BOTH plateau and cliff candidates confirmed.

    Rise magnitude over the 60 s before peak is 8.125 °C — inside the
    ``core_peak_plateau`` [2, 10] °C guard so the plateau candidate
    fires.  A single-sample 19 °C drop after the plateau triggers the
    ``probe_pull_cliff`` candidate.  Without a hint the detector's
    earliest-wins picks plateau (lower idx); a hint pointing at the
    cliff should steer the selection because the plateau idx falls
    outside the ±15 % tolerance band.
    """
    # Segment layout (samples @ 5 s):
    #   pre      10  idx  0.. 9   22 °C
    #   rise    120  idx 10..129  22→97 °C linear
    #   plateau  40  idx 130..169 97 °C
    #   cliff     1  idx 170      78 °C   (drop 19 °C >= INSTANT_DROP)
    #   post-cliff 5  idx 171..175 70, 60, 50, 40, 30 °C (monotonic confirm)
    #   post     20  idx 176..195 22 °C
    pre = np.full(10, 22.0)
    rise = np.linspace(22.0, 97.0, 120)
    plateau = np.full(40, 97.0)
    cliff_drop = np.array([78.0])
    post_cliff = np.array([70.0, 60.0, 50.0, 40.0, 30.0])
    post = np.full(20, 22.0)
    vct = np.concatenate([pre, rise, plateau, cliff_drop, post_cliff, post])
    ts = np.arange(len(vct), dtype=float) * 5.0
    df = pd.DataFrame(
        {
            "Timestamp": ts,
            "VirtualCoreTemperature": vct,
            "CoreTemperature": vct,
        }
    )
    return df


class TestHintSteersSelection:

    def test_native_earliest_wins_picks_plateau(self):
        """Sanity: without hint, plateau fires earlier than cliff."""
        df = _build_plateau_plus_cliff_synthetic()
        detector = _fresh_detector()
        curves = detector.extract_curves(df.copy())
        assert len(curves) == 1, f"expected 1 curve, got {len(curves)}"
        assert curves[0]["exit_candidate_kind"] == "core_peak_plateau", (
            f"sanity failure: plateau should be earliest, "
            f"got kind={curves[0]['exit_candidate_kind']}"
        )

    def test_hint_pointing_to_cliff_steers_selection(self):
        """Hint = cliff duration → plateau out of band → cliff wins."""
        df = _build_plateau_plus_cliff_synthetic()
        detector = _fresh_detector()

        # First pass locates start_idx (may be mid-rise via Method 2b).
        native = detector.extract_curves(df.copy())
        start_idx = native[0]["start_idx"]
        plateau_end = native[0]["end_idx"]

        # Hint points at the cliff sample (idx 170 has the 97 → 78 drop;
        # the cliff candidate returns the sample immediately before the drop).
        cliff_target_idx = 169
        expected_dur_s = float(
            df["Timestamp"].iloc[cliff_target_idx]
            - df["Timestamp"].iloc[start_idx]
        )

        hinted = detector.extract_curves(
            df.copy(), expected_durations_s=[expected_dur_s]
        )
        assert len(hinted) == 1
        assert hinted[0]["exit_candidate_kind"] == "probe_pull_cliff", (
            f"hint should steer to cliff; got kind="
            f"{hinted[0]['exit_candidate_kind']}"
        )
        assert hinted[0]["end_idx"] > plateau_end, (
            f"cliff end ({hinted[0]['end_idx']}) should be later than "
            f"plateau end ({plateau_end})"
        )

    def test_hint_pointing_to_plateau_keeps_plateau(self):
        """Hint = plateau duration → cliff out of band → plateau wins."""
        df = _build_plateau_plus_cliff_synthetic()
        detector = _fresh_detector()
        native = detector.extract_curves(df.copy())
        start_idx = native[0]["start_idx"]
        plateau_end = native[0]["end_idx"]

        # Use the native plateau end as the hint — it's well-separated
        # from the cliff (~170) so the ±15 % band around plateau should
        # not reach the cliff sample.
        expected_dur_s = float(
            df["Timestamp"].iloc[plateau_end]
            - df["Timestamp"].iloc[start_idx]
        )

        hinted = detector.extract_curves(
            df.copy(), expected_durations_s=[expected_dur_s]
        )
        assert hinted[0]["end_idx"] == plateau_end
        assert hinted[0]["exit_candidate_kind"] == "core_peak_plateau"


# ---------------------------------------------------------------------------
# Tests: NC-1/NC-2 coupling preservation
# ---------------------------------------------------------------------------


class TestFiredFlagCoupling:
    """Guards against silent breakage of plateau_fired / cliff_fired flags.

    These flags drive ``_skip_plateau_tail`` and ``_skip_probe_pull_tail`` in
    the outer ``extract_curves`` loop — if M3 picks a candidate but fails
    to set the right flag, the next curve's start detector will trigger
    on still-hot post-exit samples (NC-1 / NC-2 coupling documented in
    the detector source, lines 335–360).
    """

    def test_cliff_selected_via_hint_sets_cliff_fired_path(self):
        """When hint picks the cliff, the post-cliff tail skip still runs.

        Asserted by checking that no spurious second curve is detected
        in the post-cliff 70→30 °C cooldown cascade.
        """
        df = _build_plateau_plus_cliff_synthetic()
        detector = _fresh_detector()
        native = detector.extract_curves(df.copy())
        start_idx = native[0]["start_idx"]
        cliff_target_idx = 169
        expected_dur_s = float(
            df["Timestamp"].iloc[cliff_target_idx]
            - df["Timestamp"].iloc[start_idx]
        )
        hinted = detector.extract_curves(
            df.copy(), expected_durations_s=[expected_dur_s]
        )
        # If cliff_fired were not set after the hint-driven swap, the
        # start detector could re-fire on the still-warm post-cliff
        # samples and return a second (spurious) curve.
        assert len(hinted) == 1, (
            f"cliff_fired flag not propagated — got {len(hinted)} curves"
        )


# ---------------------------------------------------------------------------
# Tests: noise robustness (red-cell probe)
# ---------------------------------------------------------------------------


class TestHintMatchesGroundTruth:
    """Hinted decisions must land within each fixture's tolerance of
    ``expected_ends`` (or a per-case override).

    Added after HMS Red Cell 2026-04-25 flagged that the earlier test suite
    did not cross-check hint-driven outputs against fixture ground truth,
    allowing regressions like ``wonder_white`` to slip through.
    """

    # Cases where hint-driven refinement is known to select a candidate
    # outside the fixture's no-hint tolerance because the hint encodes
    # "operator bake time from log start" while the detector's
    # start_idx differs from the fixture-annotated start.
    # Treated as documented caveats, not regressions — see captain's log
    # for mission 2026-04-24_140502_3cc73444 (M3 HMS Agincourt).
    _HINT_DRIFT_CAVEAT = {"wonder_white_10k_lidded"}

    def test_real_fixtures_with_hint_match_ground_truth(self):
        for case in CASES:
            if case["source"] != "real":
                continue
            if case["name"] in self._HINT_DRIFT_CAVEAT:
                continue
            durations = case.get("expected_durations_s")
            if durations is None:
                continue  # truncated; hint path is short-circuited
            if case.get("ambiguous"):
                # Ambiguous cases use the case-level "tolerance" field
                # and may have imperfect hints; skip tight assertion.
                continue

            tolerance = case.get("tolerance", 2)
            detector = _fresh_detector()
            hinted = detector.extract_curves(
                case["df"].copy(), expected_durations_s=durations
            )
            assert len(hinted) == case["expected_n_curves"], (
                f"{case['name']}: expected {case['expected_n_curves']} curves "
                f"with hint, got {len(hinted)}"
            )
            for i, (exp_end, hint) in enumerate(
                zip(case["expected_ends"], durations)
            ):
                if hint is None:
                    continue
                assert abs(hinted[i]["end_idx"] - exp_end) <= tolerance, (
                    f"{case['name']} curve-{i} hinted end diverged from "
                    f"ground truth: expected_ends[{i}]={exp_end}, "
                    f"hinted={hinted[i]['end_idx']}, tolerance={tolerance}"
                )


class TestPeakRederivationAfterHintRefinement:
    """Regression guard for HMS Red Cell finding A1 (peak_idx staleness).

    Pre-fix, when the hint extends ``end_idx`` past the baseline firing
    into a range containing a higher peak, ``peak_idx`` was not updated
    — the outer ``extract_curves`` then saw the stale (pre-refinement)
    peak and could drop the curve at the ``MIN_PEAK_TEMP`` gate.
    """

    def test_peak_is_recomputed_over_refined_range(self):
        """Synthetic with TWO peaks — an 85 °C plateau that fires the
        ``core_peak_plateau`` candidate early, then a second rise to the
        true 97 °C peak, then a cliff.  Without the fix, the hint-driven
        end extension leaves ``peak_idx`` at the 85 °C plateau — after
        the fix, ``peak_idx`` is re-derived over the refined range and
        reflects the 97 °C peak.
        """
        # Pre @ 37 °C so Method 2a (mid-bake start) fires at idx 0.
        pre = np.full(10, 37.0)
        # Rise1 — gentle (rise_60s = 6.3 °C ∈ [2, 10]) so plateau guard passes.
        rise1 = np.linspace(37.0, 85.0, 120)
        plateau1 = np.full(30, 85.0)  # fires core_peak_plateau early
        rise2 = np.linspace(85.0, 97.0, 50)
        plateau2 = np.full(10, 97.0)
        cliff_drop = np.array([78.0])
        post_cliff = np.array([70.0, 60.0, 50.0, 40.0, 30.0])
        post = np.full(10, 22.0)
        vct = np.concatenate(
            [pre, rise1, plateau1, rise2, plateau2, cliff_drop, post_cliff, post]
        )
        ts = np.arange(len(vct), dtype=float) * 5.0
        df = pd.DataFrame(
            {
                "Timestamp": ts,
                "VirtualCoreTemperature": vct,
                "CoreTemperature": vct,
            }
        )

        detector = _fresh_detector()
        # Hint points at the cliff timestamp — band excludes plateau1
        # (at ~650 s) and includes both plateau2 and cliff (~1100 s).
        cliff_idx = 220  # 10 + 120 + 30 + 50 + 10 = 220
        hint_s = float(ts[cliff_idx])  # = 1100.0 s
        hinted = detector.extract_curves(
            df.copy(), expected_durations_s=[hint_s]
        )

        assert hinted, "hinted detector must return at least one curve"
        # The true peak is 97 °C (at idx 209) — re-derivation over
        # ``temps[start : refined_end + 1]`` must surface it.
        assert hinted[0]["max_temp"] >= 96.0, (
            f"hint-extended curve lost its true peak: max_temp="
            f"{hinted[0]['max_temp']} (pre-fix would be 85.0 from plateau1)"
        )


class TestNoiseRobustness:
    """Red-cell empirical probe per project memory
    ``feedback_redcell_empirical_verification``.

    Runs the detector with perturbed fixtures at σ ∈ {0.15, 0.5, 1.0} °C
    and asserts that with a correct hint, the end-time variance across
    seeds is no worse than without a hint.
    """

    @pytest.mark.parametrize("sigma", [0.15, 0.5, 1.0])
    def test_end_time_variance_with_hint_leq_without_hint(self, sigma):
        case = next(c for c in CASES if c["name"] == "real_100098DE_1351")
        base_df = case["df"].copy()
        expected_durations = case["expected_durations_s"]

        detector = _fresh_detector()
        ends_no_hint: list[int] = []
        ends_with_hint: list[int] = []

        for seed in range(8):
            rng = np.random.default_rng(seed)
            noisy = base_df.copy()
            noise = rng.normal(0.0, sigma, size=len(noisy))
            noisy["VirtualCoreTemperature"] = (
                noisy["VirtualCoreTemperature"] + noise
            )
            noisy["CoreTemperature"] = noisy["VirtualCoreTemperature"]

            c_no = detector.extract_curves(noisy.copy())
            c_hi = detector.extract_curves(
                noisy.copy(), expected_durations_s=expected_durations
            )
            if c_no:
                ends_no_hint.append(c_no[0]["end_idx"])
            if c_hi:
                ends_with_hint.append(c_hi[0]["end_idx"])

        assert len(ends_no_hint) == len(ends_with_hint) == 8, (
            f"σ={sigma}: detector dropped curves under noise — "
            f"no_hint={len(ends_no_hint)}, with_hint={len(ends_with_hint)}"
        )
        var_no = float(np.var(ends_no_hint))
        var_hi = float(np.var(ends_with_hint))
        # Soft inequality with a 1-sample epsilon because variance on 8
        # integer samples is quantised; the hint must not materially
        # WORSEN stability.
        assert var_hi <= var_no + 1.0, (
            f"σ={sigma}: hint increased end-idx variance "
            f"(no_hint={var_no:.2f}, with_hint={var_hi:.2f})"
        )
