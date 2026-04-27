"""Pure detector for bread entry/exit boundaries in a thermal-profile log.

Consumes a DataFrame with at minimum a ``Timestamp`` column and a core
temperature column resolvable via
:func:`src.data.column_helpers.resolve_core_temperature_series`.  Returns a
list of curve-descriptor dicts compatible with the legacy
``_extract_all_baking_curves`` output.

The detector is pure: it does not mutate the input DataFrame.  All rate
thresholds are expressed in °C/s so detection is invariant to sample period.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from config.constants import SENSOR_LIST
from src.data._drop_rate_detection import find_confirmed_drop_start
from src.data.column_helpers import resolve_core_temperature_series
from src.data.sigmoid_refinement import fit_logistic, score_end_candidate

logger = logging.getLogger(__name__)

# PredictionState value the firmware reports while the probe is out of the loaf.
PROBE_NOT_INSERTED_STATE = 'Probe Not Inserted'


def _resolve_max_sensor_series(df: pd.DataFrame, fallback: np.ndarray) -> np.ndarray:
    """Return max(T1..T8) across sensors when all 8 are present, else ``fallback``.

    Synthetic fixtures that only carry VirtualCoreTemperature/CoreTemperature
    drop back to the core series so their semantics are unchanged.
    Physical sensors on a Combustion Inc. probe.  When all 8 are present we use
    max(T1..T8) as the "is probe in a hot environment" signal (see mission
    2026-04-24_105032_1b3801f8): the ambient-end sensor (typically T8) reacts to
    oven entry/exit far faster than the core, so a max-over-sensors series
    captures the true oven-entry moment and keeps the post-cliff cooldown skip
    waiting until ALL sensors have actually cooled.
    """
    if all(col in df.columns for col in SENSOR_LIST):
        return df.loc[:, list(SENSOR_LIST)].to_numpy(dtype=float, copy=True).max(axis=1)
    return fallback


class CurveBoundaryDetector:
    """Extract curve boundaries from a thermal-profile DataFrame."""

    def __init__(self, config: dict[str, Any]):
        # Preserve the full config dict for the sigmoid scorer (score_end_candidate
        # reads its own thresholds via .get()).  Storing it verbatim avoids
        # duplicating each key and keeps future config additions zero-cost.
        self._config = dict(config)

        self._room_temp_max = float(config["ROOM_TEMP_MAX"])
        self._min_peak_temp = float(config["MIN_PEAK_TEMP"])
        self._min_duration_s = float(config["MIN_CURVE_DURATION_SECONDS"])
        self._drop_rate_c_s = float(config["DROP_RATE_THRESHOLD_C_PER_SEC"])
        self._confirm_n = int(config["CONFIRMATION_WINDOW_SAMPLES"])
        self._post_peak_grace = int(config["POST_PEAK_GRACE_SAMPLES"])
        self._large_drop_c = float(config["LARGE_DROP_FROM_PEAK_C"])
        self._start_rise_c = float(config["START_RISE_THRESHOLD_C"])
        self._plateau_rate_c_s = float(config["CORE_PEAK_PLATEAU_RATE_C_PER_SEC"])
        self._plateau_confirm_s = float(config["CORE_PEAK_PLATEAU_CONFIRM_SECONDS"])
        self._plateau_rate_window_s = float(config["CORE_PEAK_PLATEAU_RATE_WINDOW_SECONDS"])
        self._instant_drop_c = float(config["INSTANT_DROP_THRESHOLD_C"])
        self._cliff_confirm_n = int(config["CLIFF_MONOTONIC_CONFIRM_SAMPLES"])
        # Cliff-start gate — separate from _min_peak_temp (curve-acceptance).
        # Tuning one must not silently move the other.
        self._cliff_min_start_temp_c = float(config["CLIFF_MIN_START_TEMP_C"])
        # Cool-to-bake threshold: the VCT level below which we treat the
        # probe as "no longer baking".  Matches the fixture convention.
        self._bake_active_c = float(config["BAKE_ACTIVE_THRESHOLD_C"])
        # Optional expected-duration hint (M3 HMS Agincourt).  When a hint
        # is supplied for a curve, end-candidate arbitration switches from
        # earliest-wins to composite-scored-in-window-wins within this band.
        self._duration_tolerance_frac = float(
            config.get("EXPECTED_DURATION_TOLERANCE_FRAC", 0.15)
        )
        self._duration_min_tolerance_s = float(
            config.get("EXPECTED_DURATION_MIN_TOLERANCE_SECONDS", 60.0)
        )
        # Upper bound on start-refinement shifts (M4 HMS Hood).
        self._duration_max_start_shift_s = float(
            config.get("EXPECTED_DURATION_MAX_START_SHIFT_SECONDS", 30.0)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_curves(
        self,
        df: pd.DataFrame,
        expected_durations_s: list[float | None] | None = None,
    ) -> list[dict[str, Any]]:
        """Return list of curve-descriptor dicts — does not mutate ``df``.

        When ``expected_durations_s`` is ``None`` (default) the detector uses
        the earliest-wins arbitration it always has.  When supplied, each
        non-``None`` entry in the list is matched positionally to the
        detected curves: for a curve at position ``k``, a hint of
        ``expected_durations_s[k]`` (in seconds) narrows end-candidate
        arbitration to the ``±EXPECTED_DURATION_TOLERANCE_FRAC`` window
        around ``start_time + hint`` and picks the candidate with the
        highest composite sigmoid-fit + proximity score.  If no confirmed
        candidate lies inside the band the detector falls back to
        earliest-wins and emits a ``logger.warning`` — the decision is
        NEVER silently moved to a non-candidate index.

        Introduced by flotilla mission M3 HMS Agincourt.
        """
        if df is None or len(df) == 0:
            return []

        self._validate_timestamps(df)

        temps = resolve_core_temperature_series(df).to_numpy(dtype=float, copy=True)
        max_sensor = _resolve_max_sensor_series(df, temps)
        timestamps = df["Timestamp"].to_numpy(dtype=float, copy=True)
        pred_state = (
            df["PredictionState"].to_numpy(copy=True)
            if "PredictionState" in df.columns
            else None
        )

        curves: list[dict[str, Any]] = []
        n = len(df)
        # If PredictionState is present and never reverts to 'Probe Not Inserted'
        # *after* its first departure from it, the probe was continuously in
        # place; brief sub-bake-active cooldowns must not split the curve —
        # only a much longer quiescent period does.
        cooking_continuous = self._probe_cooking_continuous(pred_state)

        search_from = 0
        while search_from < n:
            start_idx = self._detect_start(temps, max_sensor, pred_state, search_from)
            if start_idx is None:
                break

            # Positional hint lookup — the hint for the curve we are about to
            # detect is at index ``len(curves)`` in the caller-supplied list.
            # A ``None`` entry or a list shorter than the detected curve count
            # cleanly falls through to the no-hint path.
            curve_slot = len(curves)
            expected_dur_s: float | None = None
            if (
                expected_durations_s is not None
                and curve_slot < len(expected_durations_s)
            ):
                hint_value = expected_durations_s[curve_slot]
                if hint_value is not None:
                    expected_dur_s = float(hint_value)

            (
                end_idx,
                peak_idx,
                truncated,
                plateau_fired,
                cliff_fired,
                exit_kind,
            ) = self._detect_curve_end(
                temps,
                timestamps,
                start_idx,
                cooking_continuous=cooking_continuous,
                expected_duration_s=expected_dur_s,
            )
            if peak_idx is None:
                break

            # Start refinement (M4 HMS Hood).  Runs only when a hint is
            # supplied AND the curve is not truncated (a truncated log's
            # duration is undefined, so duration-based start refinement
            # would be meaningless).  The refinement is bounded by
            # EXPECTED_DURATION_MAX_START_SHIFT_SECONDS, the horizon
            # (``search_from`` — prevents crossing a previous curve's
            # tail), and the PredictionState 'Probe Not Inserted' guard.
            if expected_dur_s is not None and not truncated:
                start_idx, peak_idx = self._refine_start_with_hint(
                    temps,
                    timestamps,
                    pred_state,
                    start_idx=start_idx,
                    end_idx=end_idx,
                    peak_idx=peak_idx,
                    expected_duration_s=expected_dur_s,
                    horizon=search_from,
                )

            peak_temp = float(temps[peak_idx])

            duration_s = float(timestamps[end_idx] - timestamps[start_idx])
            # Truncated curves are incomplete by construction, so only enforce
            # the peak-temperature gate on them; the duration floor applies
            # only when we observed a full start-through-exit sequence.
            duration_ok = truncated or duration_s >= self._min_duration_s
            if duration_ok and peak_temp >= self._min_peak_temp:
                curve_data = df.iloc[start_idx : end_idx + 1].copy()
                curve_data["Timestamp"] = (
                    curve_data["Timestamp"] - curve_data["Timestamp"].iloc[0]
                )
                curve_data["TimeMinutes"] = curve_data["Timestamp"] / 60.0
                curve_data = curve_data.reset_index(drop=True)

                curves.append(
                    {
                        "data": curve_data,
                        "start_idx": int(start_idx),
                        "end_idx": int(end_idx),
                        "start_time": float(timestamps[start_idx]),
                        "end_time": float(timestamps[end_idx]),
                        "duration": float(curve_data["TimeMinutes"].max()),
                        "max_temp": peak_temp,
                        "curve_number": len(curves) + 1,
                        "samples": len(curve_data),
                        "truncated": bool(truncated),
                        "exit_candidate_kind": exit_kind,
                    }
                )

            search_from = end_idx + 1
            # When a lidded-plateau exit fires, the curve ends at plateau-onset
            # but the probe is still at plateau temp for the remainder of the
            # plateau.  Advance past any contiguous samples still within
            # plateau-rate of peak so the start detector does not treat the
            # plateau tail as a second bake.  Non-plateau exits leave this
            # unchanged.
            if plateau_fired:
                search_from = self._skip_plateau_tail(
                    temps, timestamps, search_from, peak_temp
                )
            # When a cliff exit fires, the sample immediately after the cliff
            # is still hot (probe just pulled — VCT falls through room-temp
            # only after a cooldown delay).  Advance past samples still above
            # room_temp_max so the start detector does not re-trigger on the
            # still-warm post-cliff tail as a new bake.
            elif cliff_fired:
                search_from = self._skip_probe_pull_tail(max_sensor, search_from)

        return curves

    def _skip_probe_pull_tail(self, max_sensor: np.ndarray, search_from: int) -> int:
        """Advance ``search_from`` past the hot cooldown tail after a cliff exit.

        Operates on ``max_sensor`` — the per-sample max across T1..T8 — rather
        than the core sensor alone.  After a probe-pull cliff the ambient-end
        sensor (typically T8) stays hot for roughly 30 s of cliff-cooldown
        cascade, while the core (T1) falls below room temperature within a few
        seconds; advancing only on the core would release the skip while the
        probe is still demonstrably in a hot environment.  Using max(T1..T8)
        keeps the skip active until **all** sensors have cooled, which is the
        physical condition the outer start-search needs before it can safely
        look for the next bake (mission 2026-04-24_105032_1b3801f8).

        When T1..T8 are not all present (synthetic fixtures carrying only
        VCT/CoreTemperature), ``max_sensor`` is the core-series fallback and
        behaviour is unchanged from the pre-max-sensor implementation.

        Advances until the signal drops to or below ``_room_temp_max`` with
        ``_confirm_n`` consecutive confirmations, then returns that index so
        the next start-search begins in the post-cooldown quiescent region.

        TWO-LAYER DEFENSE against cliff firing inside post-cliff cascade
        (validated by mission 2026-04-24_090858_d46e235e, HMS Artful Q4 probe):

        - Layer 1 (unit-level): ``CLIFF_MIN_START_TEMP_C=80`` in
          ``_candidate_probe_pull_cliff`` prevents the cliff candidate from
          firing on samples already below 80 °C — blocks within-cascade re-fire
          even when the scan starts inside the cascade.
        - Layer 2 (outer-loop, this method): advances ``search_from`` past the
          entire cooldown tail before the next ``_detect_start`` call — prevents
          next-curve start detection from latching onto the still-warm tail.

        Both layers are retained because each guards a distinct failure mode:
        Layer 1 blocks within-cascade cliff re-fire (relevant when
        ``_detect_curve_end`` scans inside an ongoing cascade); Layer 2 blocks
        the outer start-search from treating the cooldown tail as a new bake.
        On the current fixture set either layer alone suffices end-to-end, but
        the guard is cheap and physically meaningful defense-in-depth.

        NC-1 (NON-BLOCKING, mission 2026-04-24_105032_1b3801f8, HMS Astute):
        "The post-cliff cascade at 100098DE lasts 84 samples (=420 s at 5 s/sample)
        before max_sensor drops below 35. The skip's termination condition is
        confirm_n=3 consecutive sub-room samples. At a coarser sample period (say
        30 s/sample), the same physical 420 s cascade would be ~14 samples, and 3
        consecutive sub-room might release the skip inside a fluctuating tail if T8
        re-overshoots briefly."

        The current ``confirm_n`` here is a sample-count (not seconds-based), for
        consistency with other candidates in this detector. If future CSVs are
        recorded at sample periods significantly different from 5 s, a follow-up
        mission could make ``confirm_n`` seconds-based (e.g. ``max(3, int(round(15.0
        / dt)))``) so the confirmation gate scales with physical time rather than
        sample count.
        """
        n = len(max_sensor)
        j = search_from
        # Fast-forward through any samples where ANY sensor is still above
        # room temperature.
        while j < n and float(max_sensor[j]) > self._room_temp_max:
            j += 1
        # Require a confirmed sub-room-temp run to avoid splitting on a single
        # noisy dip below the threshold.
        confirmed = 0
        while j < n and confirmed < self._confirm_n:
            if float(max_sensor[j]) <= self._room_temp_max:
                confirmed += 1
                j += 1
            else:
                confirmed = 0
                j += 1
        return j

    def _skip_plateau_tail(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        search_from: int,
        peak_temp: float,
    ) -> int:
        """Advance ``search_from`` past samples still in the lidded-bake tail.

        Used after a plateau-onset exit: the curve ended at oven-exit but the
        loaf remained above bake-active until the probe was removed (or the
        log ended).  Without this skip, the residual post-exit plateau would
        be treated as a second bake.  The skip is gated on ``peak_temp`` being
        well above bake-active so non-plateau endings (cool-to-ambient) are
        unaffected: their peak is behind and temps at ``search_from`` are
        already sub-bake-active.
        """
        n = len(temps)
        if search_from >= n:
            return search_from
        if peak_temp - self._bake_active_c < 10.0:
            return search_from
        # Advance while the core is still "in bake" — only stop when it cools
        # below bake-active or the log ends.
        j = search_from
        while j < n and float(temps[j]) >= self._bake_active_c:
            j += 1
        # Require a confirmed sub-bake-active run before resuming search to
        # avoid splitting on a single noisy dip.
        confirmed = 0
        while j < n and confirmed < self._confirm_n:
            if float(temps[j]) < self._bake_active_c:
                confirmed += 1
                j += 1
            else:
                break
        return j

    # ------------------------------------------------------------------
    # Timestamp validation
    # ------------------------------------------------------------------

    def _validate_timestamps(self, df: pd.DataFrame) -> None:
        if "Timestamp" not in df.columns:
            raise ValueError("DataFrame is missing required 'Timestamp' column")
        ts = df["Timestamp"].to_numpy(dtype=float, copy=False)
        if len(ts) < 2:
            return
        if np.any(np.diff(ts) < 0):
            raise ValueError("Timestamps must be monotonically non-decreasing")

    # ------------------------------------------------------------------
    # Start detection
    # ------------------------------------------------------------------

    def _detect_start(
        self,
        temps: np.ndarray,
        max_sensor: np.ndarray,
        pred_state: np.ndarray | None,
        search_from: int,
    ) -> int | None:
        """Return start index, or None if no further start is found.

        Method 1 (PredictionState transition) and method 2a (mid-bake first
        sample ≥ room_temp_max) operate on the core series ``temps``.  Method
        2b (cold-start fallback) scans ``max_sensor`` — the per-sample max
        across T1..T8 — so that oven entry is detected when the ambient-end
        sensor (typically T8) first crosses ``bake_active_c``, which happens
        100–200 samples (10–17 min) before the core sensor does on bakes where
        the probe is re-inserted into an already-hot oven (the bread dough
        insulates the core; the ambient sensor reacts to the oven air
        immediately).  When T1..T8 are not all present, ``max_sensor`` is the
        core-series fallback so synthetic-fixture semantics are unchanged
        (mission 2026-04-24_105032_1b3801f8).
        """
        n = len(temps)

        # Method 1: PredictionState transition 'Probe Not Inserted' → other.
        if pred_state is not None:
            for j in range(search_from, n - 1):
                if (
                    pred_state[j] == PROBE_NOT_INSERTED_STATE
                    and pred_state[j + 1] != PROBE_NOT_INSERTED_STATE
                ):
                    return j + 1

        # Method 2a: mid-bake start — the first sample already ≥ room_temp_max
        # (e.g. probe pre-inserted into a hot loaf).  Operates on the core
        # series to preserve fixture semantics where the log literally begins
        # mid-bake.
        if search_from == 0 and temps[0] >= self._room_temp_max:
            return 0

        # Method 2b: cold-start — first index where max(T1..T8) ≥ bake_active_c
        # with a sustained rise confirmed by the next (confirm_n - 1) samples
        # also ≥ bake_active_c.  Using max-sensor catches the ambient sensor's
        # sharp rise when the probe enters the oven, well before the core
        # crosses the same threshold.
        #
        # NC-2 COUPLING WARNING (NON-BLOCKING, mission 2026-04-24_105032_1b3801f8,
        # HMS Astute): method 2b and _skip_probe_pull_tail are tightly coupled and
        # must be refactored together:
        #
        #   - After a cliff exit, _skip_probe_pull_tail advances search_from past
        #     the full post-cliff cooldown cascade by waiting until max(T1..T8)
        #     drops below ROOM_TEMP_MAX with confirm_n consecutive confirmations.
        #   - Method 2b then uses max(T1..T8) >= bake_active_c to detect oven
        #     re-entry; it fires correctly because the skip has already consumed
        #     the hot cascade.
        #   - The two work as a pair: skip terminates when max < ROOM_TEMP_MAX;
        #     method 2b fires when max >= bake_active_c.
        #
        # Astute's probe_old_skip counterfactual (probe_old_skip.py) showed that
        # using the old core-only skip with the new max-sensor method 2b would
        # produce spurious second curves on 100098DE, BA3C_1759 (bakes 2 and 3),
        # and PWM.  Future refactors MUST preserve this coupling — changing either
        # the skip or method 2b without updating the other risks those regressions.
        #
        # NC-3 NOISE NOTE (NON-BLOCKING, mission 2026-04-24_105032_1b3801f8,
        # HMS Astute): at σ ≈ 0.5 °C ambient-sensor noise, one trial in 30 shifted
        # the bake-1 start from 13 (method 1, PredictionState) to 87 (method 2b),
        # likely because the duration/peak gate rejected the method-1 curve and the
        # outer loop re-entered _detect_start past idx 13.  Future work could add
        # a noise-relative threshold or a short rolling-smooth on max_sensor before
        # the first-crossing scan to reduce sensitivity to σ > 0.3 °C.
        for j in range(search_from, n):
            if max_sensor[j] < self._bake_active_c:
                continue
            look = min(self._confirm_n - 1, n - 1 - j)
            confirmed = all(
                max_sensor[j + k] >= self._bake_active_c for k in range(1, look + 1)
            )
            if confirmed:
                return j

        return None

    # ------------------------------------------------------------------
    # Peak + end detection (evidence aggregator)
    # ------------------------------------------------------------------

    def _detect_curve_end(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        start_idx: int,
        cooking_continuous: bool,
        expected_duration_s: float | None = None,
    ) -> tuple[int, int | None, bool, bool, bool, str | None]:
        """Return ``(end_idx, peak_idx, truncated, plateau_fired, cliff_fired,
        exit_kind)`` for a curve starting at ``start_idx``.

        The peak is computed incrementally (running max) so a taller peak
        belonging to a *later* curve never leaks into the current one.  Once
        exit candidates become active (after ``post_peak_grace`` samples past
        the running peak), we pick the earliest confirmed one — this is the
        "baseline" decision.  When ``expected_duration_s`` is supplied, the
        baseline is overridden by the highest-composite-scored candidate
        whose firing time falls inside the tolerance band around the expected
        end.  If no confirmed candidate sits inside that band the detector
        falls back to the baseline AND emits a ``logger.warning``.

        ``cooking_continuous``: when the log's ``PredictionState`` never
        reverts to 'Probe Not Inserted', brief dips below ``bake_active_c``
        are considered part of the same session; the cool-to-ambient
        confirmation window is extended by a large factor so only a truly
        long quiescent period exits the curve.

        ``plateau_fired`` is True when the winning candidate was the
        core-peak-plateau one; callers use it to skip the plateau tail when
        resuming the search for the next curve.

        ``cliff_fired`` is True when the winning candidate was the
        probe-pull cliff; callers use it to skip the hot cooldown tail so
        the start detector does not re-trigger on still-warm post-cliff samples.

        ``exit_kind`` names the winning candidate (string from
        ``_VALID_KINDS``, or ``None`` when the curve is truncated with no
        cliff fallback available).  Added in M3 HMS Agincourt as a
        diagnostic — consumers can log the transition history without
        re-deriving it.
        """
        n = len(temps)
        if start_idx >= n:
            return n - 1, None, True, False, False, None

        peak_idx = start_idx
        peak_temp = float(temps[start_idx])

        # When probe is continuously inserted, require ~1 hour of quiescence to
        # exit the curve (matches the real-CSV fixture convention — 1759 has a
        # 40-min sub-40 interlude that must NOT split the bake).
        cool_window = (
            self._long_cool_window_samples(timestamps)
            if cooking_continuous
            else self._confirm_n
        )

        # Stage 1 — scan for the earliest-wins baseline.  Preserves the
        # pre-M3 semantics byte-for-byte when no hint is supplied (see
        # below).
        baseline: tuple[int, str, bool, bool] | None = None
        for j in range(start_idx, n):
            if temps[j] > peak_temp:
                peak_temp = float(temps[j])
                peak_idx = j

            first_scan = peak_idx + self._post_peak_grace
            if j < first_scan:
                continue

            exit_idx, plateau_fired, cliff_fired, kind = (
                self._evaluate_exit_candidates(
                    temps, timestamps, j, peak_idx, peak_temp, cool_window
                )
            )
            if exit_idx is not None:
                baseline = (exit_idx, kind or "", plateau_fired, cliff_fired)
                break

        # Grace-window fallback: the cliff can fire AT peak_idx, which is inside
        # the post_peak_grace window.  If the log ends before the grace window
        # expires, the loop above never evaluates the cliff candidate.  Run it
        # once over the full array from peak_idx before declaring truncated.
        if baseline is None:
            cliff = self._candidate_probe_pull_cliff(
                temps, timestamps, peak_idx
            )
            if cliff is not None:
                baseline = (cliff, "probe_pull_cliff", False, True)

        if baseline is None:
            return n - 1, peak_idx, True, False, False, None

        # Stage 2 — no hint: return the baseline unchanged (identical to
        # pre-M3 behaviour; ``exit_kind`` is the only added field).
        if expected_duration_s is None:
            exit_idx, kind, plateau_fired, cliff_fired = baseline
            return (
                exit_idx,
                peak_idx,
                False,
                plateau_fired,
                cliff_fired,
                kind or None,
            )

        # Stage 3 — hint-driven refinement.
        refined = self._refine_end_with_hint(
            temps,
            timestamps,
            start_idx,
            peak_idx,
            cool_window,
            baseline,
            expected_duration_s,
        )
        r_idx, r_kind, r_plateau, r_cliff = refined

        # Re-derive peak within the refined [start_idx, r_idx] range.
        # If the hint extends the end beyond the baseline firing, the
        # running-max peak computed during stage 1 may pre-date a later
        # true peak and leak a below-MIN_PEAK_TEMP value into the outer
        # acceptance gate (red-cell A1, HMS Red Cell 2026-04-25, probe
        # reproduced on real_1000BA3C_1759 σ=0.5 seed 7: baseline peak
        # idx 5894 @ 36.6 °C would cause the merged curve to be dropped
        # even though the refined range contains idx 6183 @ 97.1 °C).
        refined_peak_idx = (
            start_idx + int(np.argmax(temps[start_idx : r_idx + 1]))
        )
        return (
            r_idx,
            refined_peak_idx,
            False,
            r_plateau,
            r_cliff,
            r_kind or None,
        )

    @staticmethod
    def _probe_cooking_continuous(pred_state: np.ndarray | None) -> bool:
        """Return True when PredictionState never reverts to
        PROBE_NOT_INSERTED_STATE after its first departure.

        WARNING — calibrated to a single CSV (real_1000BA3C_1759).
        That CSV's PredictionState transitions to 'Cooking' at idx 13 and never
        reverts — a suspected firmware-reporting quirk, not proof the probe was
        continuously inserted.  The heuristic exists solely to prevent the 40-min
        sub-40 °C interlude in that CSV from being treated as a curve boundary.

        Known risks:
        (a) Any future CSV with the same firmware-stuck signature but a different
            number of real bakes will have its bakes merged or split wrongly.
        (b) The fixture that drives this logic (real_1000BA3C_1759 bake-2) is
            explicitly tagged ambiguous=True — the heuristic encodes a best-guess
            on an ambiguous case.  Cross-CSV validation (3+ additional real logs)
            is needed before trusting this in production.
        """
        if pred_state is None:
            return False
        first_active = None
        for i, v in enumerate(pred_state):
            if v != PROBE_NOT_INSERTED_STATE:
                first_active = i
                break
        if first_active is None:
            return False
        return not any(v == PROBE_NOT_INSERTED_STATE for v in pred_state[first_active:])

    def _long_cool_window_samples(self, timestamps: np.ndarray) -> int:
        """Return the cool-to-ambient confirmation length (samples) used when
        the probe is continuously inserted.

        See _probe_cooking_continuous for calibration caveats — this value
        (3 600 s) is anchored to real_1000BA3C_1759's 40-min inter-bake quiescent
        period and may produce wrong splits on future CSVs.
        """
        long_cool_s = 3600.0  # ~1 hour of sustained sub-bake-active
        if len(timestamps) < 2:
            return max(self._confirm_n, 1)
        dt = float(np.median(np.diff(timestamps)))
        if dt <= 0:
            return max(self._confirm_n, 1)
        return max(int(round(long_cool_s / dt)), self._confirm_n)

    def _evaluate_exit_candidates(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        j: int,
        peak_idx: int,
        peak_temp: float,
        cool_window: int,
    ) -> tuple[int | None, bool, bool, str | None]:
        """Scan exit candidates up to sample ``j``; return
        ``(earliest confirmed, plateau_fired, cliff_fired, kind)``
        where ``kind`` names the winning candidate (or ``None`` when
        none fired).  The fired flags remain derived from ``kind`` and
        preserve their pre-M3 semantics: ``plateau_fired`` drives
        ``_skip_plateau_tail`` and ``cliff_fired`` drives
        ``_skip_probe_pull_tail`` after this curve is accepted.
        """
        first_scan = peak_idx + self._post_peak_grace
        upto = j + 1  # exclusive upper bound for sub-arrays

        earliest: int | None = None
        earliest_kind: str | None = None

        def _consider(idx: int | None, kind: str) -> None:
            nonlocal earliest, earliest_kind
            if idx is None:
                return
            if earliest is None or idx < earliest:
                earliest = idx
                earliest_kind = kind

        _consider(
            self._candidate_drop_rate(
                temps[:upto], timestamps[:upto], first_scan
            ),
            "drop_rate",
        )
        _consider(
            self._candidate_cool_to_ambient(
                temps[:upto], first_scan, cool_window
            ),
            "cool_to_ambient",
        )
        _consider(
            self._candidate_room_temp_plateau(
                temps[:upto], first_scan, cool_window
            ),
            "room_temp_plateau",
        )
        _consider(
            self._candidate_dip_with_rerise(
                temps[:upto], peak_idx, peak_temp
            ),
            "dip_with_rerise",
        )
        _consider(
            self._candidate_core_peak_plateau(
                temps[:upto], timestamps[:upto], peak_idx
            ),
            "core_peak_plateau",
        )
        # peak_idx+1 guard removed in mission 2026-04-24_090858_d46e235e: the
        # BA3C_1759 j=293 "multi-pull session" framing papered over a
        # mis-annotated fixture that should have been 3 bakes.  Scan from
        # peak_idx directly.
        _consider(
            self._candidate_probe_pull_cliff(
                temps[:upto], timestamps[:upto], peak_idx
            ),
            "probe_pull_cliff",
        )

        plateau_fired = earliest_kind == "core_peak_plateau"
        cliff_fired = earliest_kind == "probe_pull_cliff"
        return earliest, plateau_fired, cliff_fired, earliest_kind

    # ------------------------------------------------------------------
    # Hint-driven refinement (M3 HMS Agincourt)
    # ------------------------------------------------------------------

    def _refine_end_with_hint(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        start_idx: int,
        peak_idx: int,
        cool_window: int,
        baseline: tuple[int, str, bool, bool],
        expected_duration_s: float,
    ) -> tuple[int, str, bool, bool]:
        """Re-rank all confirmed candidates by composite sigmoid score
        within the tolerance band around ``start + expected_duration_s``.

        Falls back to ``baseline`` (earliest-wins) and emits a structured
        warning when no confirmed candidate sits in the band — the
        decision is NEVER silently moved to a non-candidate index.
        """
        band_width = max(
            expected_duration_s * self._duration_tolerance_frac,
            self._duration_min_tolerance_s,
        )
        t_start = float(timestamps[start_idx])
        t_expected_end = t_start + expected_duration_s
        t_lo = t_expected_end - band_width
        t_hi = t_expected_end + band_width

        candidates = self._collect_all_candidates(
            temps, timestamps, peak_idx, cool_window, baseline
        )

        in_band = [
            (idx, kind)
            for idx, kind in candidates
            if t_lo <= float(timestamps[idx]) <= t_hi
        ]

        if not in_band:
            b_idx, b_kind, b_plateau, b_cliff = baseline
            logger.warning(
                "expected_duration_s hint produced no candidate in tolerance "
                "band [%.1fs, %.1fs] (expected_end=%.1fs, start=%.1fs, "
                "hint=%.1fs); falling back to earliest-wins baseline "
                "kind=%s end_idx=%d",
                t_lo,
                t_hi,
                t_expected_end,
                t_start,
                expected_duration_s,
                b_kind,
                b_idx,
            )
            return baseline

        # Score each in-band candidate; ties broken by earlier idx, then
        # by kind lexical order for determinism.
        scored: list[tuple[float, int, str]] = []
        for idx, kind in in_band:
            score = score_end_candidate(
                temps,
                timestamps,
                start_idx,
                idx,
                expected_duration_s,
                self._config,
            )
            scored.append((score, idx, kind))
        scored.sort(key=lambda t: (-t[0], t[1], t[2]))

        _best_score, best_idx, best_kind = scored[0]
        plateau_fired = best_kind == "core_peak_plateau"
        cliff_fired = best_kind == "probe_pull_cliff"
        return best_idx, best_kind, plateau_fired, cliff_fired

    def _collect_all_candidates(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        peak_idx: int,
        cool_window: int,
        baseline: tuple[int, str, bool, bool],
    ) -> list[tuple[int, str]]:
        """Run every candidate over the full array; return ``(idx, kind)``
        pairs.  The baseline is always folded in — protects against the
        grace-window cliff fallback where the cliff fires at ``peak_idx``
        inside the post-peak grace window and is only observable via the
        dedicated fallback path.
        """
        first_scan = peak_idx + self._post_peak_grace
        peak_temp = float(temps[peak_idx])
        results: list[tuple[int, str]] = []

        def _collect(idx: int | None, kind: str) -> None:
            if idx is not None:
                results.append((idx, kind))

        _collect(
            self._candidate_drop_rate(temps, timestamps, first_scan),
            "drop_rate",
        )
        _collect(
            self._candidate_cool_to_ambient(
                temps, first_scan, cool_window
            ),
            "cool_to_ambient",
        )
        _collect(
            self._candidate_room_temp_plateau(
                temps, first_scan, cool_window
            ),
            "room_temp_plateau",
        )
        _collect(
            self._candidate_dip_with_rerise(temps, peak_idx, peak_temp),
            "dip_with_rerise",
        )
        _collect(
            self._candidate_core_peak_plateau(temps, timestamps, peak_idx),
            "core_peak_plateau",
        )
        _collect(
            self._candidate_probe_pull_cliff(temps, timestamps, peak_idx),
            "probe_pull_cliff",
        )

        # Ensure the baseline is represented — the scan above should
        # always find it, but the grace-window cliff fallback can land
        # a cliff at peak_idx that the scan still rejects (e.g. if
        # CLIFF_MIN_START_TEMP_C gating differs from the scan path).
        b_idx, b_kind, _, _ = baseline
        if b_kind and not any(
            idx == b_idx and kind == b_kind for idx, kind in results
        ):
            results.append((b_idx, b_kind))

        return results

    # ------------------------------------------------------------------
    # Start-refinement (M4 HMS Hood)
    # ------------------------------------------------------------------

    def _refine_start_with_hint(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        pred_state: np.ndarray | None,
        start_idx: int,
        end_idx: int,
        peak_idx: int,
        expected_duration_s: float,
        horizon: int,
    ) -> tuple[int, int]:
        """Possibly shift ``start_idx`` toward the expected-start window.

        Window = ``[end_time - expected*(1+tol), end_time - expected*(1-tol)]``
        (lower bound = earliest valid start, upper bound = latest).  When
        the native start sits inside the window, no shift occurs.  When
        outside, the detector proposes a shift capped by
        ``EXPECTED_DURATION_MAX_START_SHIFT_SECONDS`` samples and gated
        by ``score_start_candidate >= SIGMOID_FIT_MIN_R2``.

        Guards:
          * ``horizon`` — shift cannot move start earlier than the outer
            loop's ``search_from`` (protects against crossing a previous
            curve's tail — NC-1/NC-2 coupling with ``_skip_probe_pull_tail``).
          * ``PredictionState`` — if shift would cross a
            ``'Probe Not Inserted'`` marker the shift is aborted and a
            warning is emitted.

        Returns ``(refined_start_idx, refined_peak_idx)``.  Peak is
        re-derived over the refined range so that a start shift that
        extends the curve does not leak a below-``MIN_PEAK_TEMP`` peak.
        """
        n = len(timestamps)
        if n < 2 or end_idx <= start_idx:
            return start_idx, peak_idx

        dt = float(np.median(np.diff(timestamps)))
        if dt <= 0:
            return start_idx, peak_idx

        band_width = max(
            expected_duration_s * self._duration_tolerance_frac,
            self._duration_min_tolerance_s,
        )
        t_end = float(timestamps[end_idx])
        t_start_center = t_end - expected_duration_s
        t_start_lo = t_start_center - band_width
        t_start_hi = t_start_center + band_width
        t_native_start = float(timestamps[start_idx])

        # Already in window — no-op.
        if t_start_lo <= t_native_start <= t_start_hi:
            return start_idx, peak_idx

        max_shift_samples = max(
            int(round(self._duration_max_start_shift_s / dt)), 1
        )

        if t_native_start > t_start_hi:
            # Detector started too late; shift EARLIER toward window.
            target_idx = (
                int(np.searchsorted(timestamps, t_start_hi, side="right")) - 1
            )
            target_idx = max(target_idx, 0)
            shifted = max(
                target_idx, start_idx - max_shift_samples, int(horizon)
            )
            direction = "earlier"
        else:
            # Detector started too early; shift LATER toward window.
            target_idx = int(
                np.searchsorted(timestamps, t_start_lo, side="left")
            )
            target_idx = min(target_idx, end_idx - 1)
            shifted = min(target_idx, start_idx + max_shift_samples)
            direction = "later"

        if shifted == start_idx:
            return start_idx, peak_idx

        # PredictionState guard — abort if the proposed shift would
        # cross a 'Probe Not Inserted' marker.  NC-1/NC-2 coupling with
        # _skip_probe_pull_tail depends on this; a silent crossing
        # could re-include a cooldown-tail sample as "in the bake".
        if pred_state is not None:
            lo, hi = (
                (shifted, start_idx)
                if shifted < start_idx
                else (start_idx, shifted)
            )
            crossing_idxs = [
                i
                for i in range(lo, hi + 1)
                if pred_state[i] == PROBE_NOT_INSERTED_STATE
            ]
            if crossing_idxs:
                logger.warning(
                    "Start-refinement %s shift from %d to %d aborted: "
                    "would cross PredictionState='%s' at idx %s",
                    direction,
                    start_idx,
                    shifted,
                    PROBE_NOT_INSERTED_STATE,
                    crossing_idxs,
                )
                return start_idx, peak_idx

        # Sigmoid-shape gate.  Fit a 4-parameter logistic over the
        # ACTUAL [shifted, end_idx] window and gate on R² alone.
        # Rationale: for END refinement (M3) we care about *when* the
        # bake ends so the proximity term to the expected duration is
        # load-bearing.  For START refinement (M4) we already trust the
        # end (it came out of M3); we only want to know whether the
        # shifted window is a CLEAN S-curve.  Using the composite score
        # would penalise short bakes twice (proximity=0 when
        # actual < expected * (1 - tol)) and reject shifts that are
        # shape-wise fine.
        min_samples = int(self._config.get("SIGMOID_FIT_MIN_SAMPLES", 30))
        window_len = end_idx - shifted + 1
        if window_len >= min_samples:
            t_fit = timestamps[shifted : end_idx + 1] - timestamps[shifted]
            T_fit = temps[shifted : end_idx + 1]
            fit = fit_logistic(t_fit, T_fit)
            r2 = fit.r2 if fit.converged else 0.0
        else:
            r2 = 0.0
        min_r2 = float(self._config.get("SIGMOID_FIT_MIN_R2", 0.85))
        if r2 < min_r2:
            logger.warning(
                "Start-refinement %s shift from %d to %d rejected: "
                "sigmoid R² %.3f < SIGMOID_FIT_MIN_R2 %.3f",
                direction,
                start_idx,
                shifted,
                r2,
                min_r2,
            )
            return start_idx, peak_idx

        # Apply shift — re-derive peak over the refined range so a
        # longer curve cannot leak a below-MIN_PEAK_TEMP peak value
        # (same principle as M3 A1 fix for end-refinement).
        refined_peak_idx = shifted + int(
            np.argmax(temps[shifted : end_idx + 1])
        )
        logger.info(
            "Start refined %s: %d -> %d "
            "(expected_dur=%.1fs, shift_samples=%d, r2=%.3f)",
            direction,
            start_idx,
            shifted,
            expected_duration_s,
            shifted - start_idx,
            r2,
        )
        return shifted, refined_peak_idx

    @staticmethod
    def _min_opt(a: int | None, b: int | None) -> int | None:
        if a is None:
            return b
        if b is None:
            return a
        return min(a, b)

    def _candidate_drop_rate(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        first_scan: int,
    ) -> int | None:
        """Probe-removal: ``confirm_n`` consecutive samples all exceeding the
        windowed drop-rate threshold (°C/s).

        Exit point = sample before the first confirming drop.
        """
        j = find_confirmed_drop_start(
            temps, timestamps, first_scan, self._drop_rate_c_s, self._confirm_n
        )
        return None if j is None else j - 1

    def _candidate_cool_to_ambient(
        self, temps: np.ndarray, first_scan: int, confirm_n: int
    ) -> int | None:
        """Curve ended because the core cooled below ``bake_active_c``.

        Confirmed by ``confirm_n`` consecutive samples below the threshold.
        Exit point = the first sub-threshold sample that initiated the run.
        (Choosing the first-below rather than the last-above sample makes
        durations sample-period invariant: the crossover timestamp differs
        from the last-above timestamp by one sample period.)
        """
        n = len(temps)
        run = 0
        for j in range(first_scan, n):
            if temps[j] < self._bake_active_c:
                run += 1
                if run >= confirm_n:
                    # Start of the confirmed sub-threshold run.
                    return j - run + 1
            else:
                run = 0
        return None

    def _candidate_room_temp_plateau(
        self, temps: np.ndarray, first_scan: int, confirm_n: int
    ) -> int | None:
        """Extended room-temperature plateau.

        ``max(confirm_n, plateau_n_default)`` consecutive samples at or below
        ``room_temp_max`` anchor the end of cooldown.  Exit point = the first
        sub-bake-active sample leading into the cooldown ramp (matches the
        convention used by :meth:`_candidate_cool_to_ambient`).
        """
        n = len(temps)
        plateau_n = max(self._confirm_n * 2, confirm_n)
        run = 0
        for j in range(first_scan, n):
            if temps[j] <= self._room_temp_max:
                run += 1
                if run >= plateau_n:
                    plateau_start = j - run + 1
                    k = plateau_start
                    while k - 1 >= first_scan and temps[k - 1] < self._bake_active_c:
                        k -= 1
                    return k
            else:
                run = 0
        return None

    def _candidate_dip_with_rerise(
        self, temps: np.ndarray, peak_idx: int, peak_temp: float
    ) -> int | None:
        """Inflection between back-to-back bakes.

        Look for the smallest local minimum after ``peak_idx`` that is both
        (a) at least ``large_drop_c / 2`` below the peak, and (b) followed
        within a short window by a rise of ``start_rise_c``.  The local-min
        index is the curve end.
        """
        n = len(temps)
        dip_depth = self._large_drop_c / 2.0  # 20°C by default
        lookahead = max(self._confirm_n * 3, 8)

        for j in range(peak_idx + self._post_peak_grace, n - 1):
            # Local min check: temps[j] lower than immediate neighbours.
            if j > 0 and temps[j] > temps[j - 1]:
                continue
            if temps[j] >= temps[j + 1]:
                continue
            # Must be well above ambient (still a "hot" dip), not end of cooldown.
            if temps[j] <= self._room_temp_max + self._start_rise_c:
                continue
            # Must be at least dip_depth below peak.
            if peak_temp - temps[j] < dip_depth:
                continue
            # Look ahead for re-rise.
            end_look = min(j + lookahead, n - 1)
            rose = any(
                temps[k] - temps[j] >= self._start_rise_c
                for k in range(j + 1, end_look + 1)
            )
            if rose:
                return j
        return None

    def _candidate_core_peak_plateau(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        peak_idx: int,
    ) -> int | None:
        """Core-peak-plateau (mission HMS Warspite, 2026-04-23).

        Lidded bakes exit the oven without the sharp post-peak decline other
        candidates key on; instead the core rate-of-change flatlines because
        the external heat source is removed but the loaf's thermal mass under
        the lid holds the core near its peak.  Fires when the core rate stays
        below ``plateau_rate_c_s`` (°C/s, windowed) for at least
        ``plateau_confirm_s`` seconds and returns the first sample of the
        confirmed run — the plateau-onset, which physically corresponds to
        oven-exit.

        Two guards on the rise-to-peak distinguish lidded from non-lidded:
        a shallow rise (< 2 °C over 60 s before peak) excludes the dip-then-
        re-rise of `two_bakes_no_cool`; a steep rise (> 10 °C over 60 s)
        excludes the sharp peak of a typical unlidded bake whose core briefly
        pauses at peak before plummeting.
        """
        n = len(temps)
        if n < 2:
            return None
        dt = float(np.median(np.diff(timestamps)))
        if dt <= 0:
            return None

        window_n = max(int(round(self._plateau_rate_window_s / dt)), 2)
        confirm_n = max(int(round(self._plateau_confirm_s / dt)), self._confirm_n)
        # Rise-magnitude guard: fixed 60 s window in physical time.  Tighter
        # than confirm_s so the guard remains stable when confirm_s is tuned.
        rise_guard_n = max(int(round(60.0 / dt)), 2)

        if peak_idx < rise_guard_n:
            return None
        peak_temp = float(temps[peak_idx])
        rise_magnitude = peak_temp - float(temps[peak_idx - rise_guard_n])
        # Rise-magnitude guard separates lidded (rise60s ∈ [3.05, 3.55] across all
        # known fixtures) from non-lidded (rise60s ≤ 1.0 or ≥ 14.5 on real CSVs).
        # Safety margin: ≥ 1.05 °C from the lower bound and ≥ 6.45 °C from the upper.
        # Theoretical vulnerability (mission 2026-04-23_121616_b56f691b, HMS Ambush):
        # a slow-rising unlidded bake with rise60s ∈ [2, 10] AND a ≥ 60 s pause at
        # peak can spuriously fire plateau (probe 8 in the red-cell verdict confirmed
        # this with a synthetic rise60s ≈ 5.88 case).  In all 3 real unlidded CSVs the
        # post-peak sub-1 °C-below-peak duration is ≤ 5 s, making the confirm_n guard
        # the second line of defence; however that defence weakens at coarse sample
        # periods (see Note C in the verdict).  Mitigation: in a follow-up mission,
        # expand the real unlidded fixture set to cover rise60s ∈ [2, 14] before
        # tightening or widening this guard.
        if rise_magnitude < 2.0 or rise_magnitude > 10.0:
            return None

        run = 0
        # Scan from peak_idx directly — plateau must scan from peak_idx (not the
        # post-peak grace) to land the confirmed run within tolerance of synthetic
        # fixture boundaries.
        for j in range(peak_idx, n):
            if j < window_n:
                continue
            dt_window = timestamps[j] - timestamps[j - window_n]
            if dt_window <= 0:
                run = 0
                continue
            rate = (temps[j] - temps[j - window_n]) / dt_window
            if abs(rate) < self._plateau_rate_c_s:
                run += 1
                if run >= confirm_n:
                    return j - run + 1
            else:
                run = 0
        return None

    def _candidate_probe_pull_cliff(
        self,
        temps: np.ndarray,
        timestamps: np.ndarray,
        first_scan: int,
    ) -> int | None:
        """Single-sample probe-pull cliff (Stance B, mission 2026-04-24_070615_fee9ec8f).

        Fires at any post-peak sample where the single-sample drop ≥
        INSTANT_DROP_THRESHOLD_C, confirmed by CLIFF_MONOTONIC_CONFIRM_SAMPLES
        consecutive weakly-monotonic declining samples, AND the cliff-start
        temperature ≥ CLIFF_MIN_START_TEMP_C.  Fires universally on lidded and
        unlidded bakes — the cliff is always a probe-pull event and never
        ordinary cooldown.

        The ``peak_idx+1`` scan-start guard was removed in mission
        2026-04-24_090858_d46e235e because the BA3C_1759 j=293 "multi-pull
        session" framing was papering over a mis-annotated fixture that should
        have been 3 bakes.  The cliff now scans from ``first_scan`` (passed by
        the caller as ``peak_idx`` in the main loop, or ``peak_idx`` in the
        grace fallback).

        The CLIFF_MIN_START_TEMP_C=80 gate is retained: it prevents the
        candidate from firing during post-cliff cascade cooldown where VCT has
        already dropped below 80 °C.

        Exit point = sample BEFORE the cliff (the last in-bake reading).

        NOISE-FRAGILITY NOTE (HMS Ambush red-cell, mission
        2026-04-24_070615_fee9ec8f, Concern A — NON-BLOCKING):

        Post-mission 2026-04-24_090858_d46e235e clarification — prior mission's
        noise-fragility framing partially reflected a mis-annotated fixture:
        when 1759 was annotated as 2 bakes (with merged curves), cliff firings
        inside the merged region appeared as spurious extra curves and inflated
        the measured sensitivity.  With the corrected 3-bake ground truth, a
        cliff at j=293 is correct, not spurious.  The prior σ=0.15 °C
        "27–60% spurious rate" on 1759 does not apply post-reannotation;
        perturbation battery at mission 2026-04-24_090858_d46e235e measured
        0/30 wrong curve-count at σ=0.15 °C.

        The underlying concern remains unresolved: probe noise at σ=0.05–0.15 °C
        (manufacturer spec range) has not been characterised against production
        CSVs, and true fragility at those σ levels is still worth verifying on
        future multi-bake sessions with tighter inter-bake spacing.

        Suggested mitigations for a follow-up mission (do NOT implement here):
        1. Apply a 3-sample rolling smooth to ``temps`` before the cliff scan
           so noise cannot perturb the running-peak crossing point.
        2. Tighten INSTANT_DROP_THRESHOLD_C from 15 °C to 18–20 °C; note that
           wonder_white_10k_lidded has a 17.15 °C cliff — raising above 17 °C
           would lose that fixture.
        3. Require the cliff drop to be ≥ N × the local noise estimate
           (e.g. N=10, σ estimated over a rolling window) so the gate adapts
           to per-session noise rather than a fixed threshold.
        4. Order-invariant guard: ensure cliff detection is robust to the order
           in which multiple exit candidates are evaluated.
        """
        n = len(temps)
        confirm_n = self._cliff_confirm_n
        if n < 2:
            return None

        for j in range(first_scan, n - confirm_n - 1):
            # Cliff must start from a baking-temperature sample; drops from
            # already-ambient temps are cascade noise from an earlier event.
            if float(temps[j]) < self._cliff_min_start_temp_c:
                continue
            drop = float(temps[j]) - float(temps[j + 1])
            if drop < self._instant_drop_c:
                continue
            monotonic = True
            for k in range(1, confirm_n + 1):
                if float(temps[j + k + 1]) > float(temps[j + k]):
                    monotonic = False
                    break
            if not monotonic:
                continue
            return j
        return None
