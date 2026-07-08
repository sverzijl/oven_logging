"""Curve Boundary Review tab.

Operator workflow:

1. View the full raw CSV log with auto-detected bake windows overlaid.
2. Pick a curve to review via radio selector.
3. **Drag a horizontal box on the detail plot** to set start/end —
   the box's x-range pins the boundary directly (M9 HMS Lookout).
4. Reset to auto → clears the manual override for the selected curve.

Widget keys are scoped by ``(filename, curve_number)`` so swapping
the currently-viewed curve does not bleed widget state across curves.

History:
  M3 HMS Indomitable — initial tab (raw log + per-curve detail panel).
  M6 HMS Refit — minutes-based axis + live preview.
  M7 HMS Inspector — baseline snapshot + diff readout.
  M8 HMS Mercury — single range slider for manual override.
  M9 HMS Lookout — drag-to-box-select on the detail plot.
  M10 HMS Vanguard — strip the earlier entry widgets (hint
    number_input, manual slider, Apply button); at that point box-select
    was the sole input mechanism.  Loader hint API is untouched.
  M11 HMS Endeavour — drag-box on the raw log claims a user-added curve.
  M12 — re-add a per-curve "Actual bake time (min)" number_input + Apply
    button (detector curves only) that drives loader.set_expected_durations;
    box-select is now one of two input mechanisms alongside it.

Two input mechanisms coexist: drag-box (a hard pin / manual claim) and the
Actual-bake-time hint (steers auto-detection; box-pin wins over it).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import streamlit as st

from config.constants import CURVE_DETECTION_CONFIG
from src.data.sigmoid_refinement import band_half_width
from src.ui.expected_duration_widgets import (
    minutes_to_seconds,
    seconds_to_minutes,
)
from src.visualization.boundary_review_plots import (
    plot_curve_detail,
    plot_raw_log_with_curves,
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_boundary_review_tab.py)
# ---------------------------------------------------------------------------


def boundary_state_label(curve: dict[str, Any]) -> str:
    """One-word UI badge for a curve: ``override``, ``user_added``,
    ``snapped``, or ``auto``.

    M11 HMS Endeavour added the ``user_added`` state.
    M12 added ``snapped`` (end placed at the operator's stated bake time).
    """
    kind = curve.get("exit_candidate_kind")
    if kind == "manual_override":
        return "override"
    if kind == "user_added":
        return "user_added"
    if kind == "expected_time_snap":
        return "snapped"
    return "auto"


def describe_hint_outcome(
    curve: dict[str, Any], applied_hint_s: float | None
) -> str:
    """Classify how the actual-bake-time hint (if any) shaped this curve's end.

    Returns one of:
      * ``"override"``       — a manual box-pin is in force (the hint is inert).
      * ``"truncated_snap"`` — end snapped to the stated time but ran past the
        end of the log (curve truncated).
      * ``"snapped"``        — end snapped to the stated time (no natural exit
        in tolerance).
      * ``"matched_exit"``   — a hint is applied and the resulting duration is
        within tolerance of the stated time (a real oven-exit was used).
      * ``"hint_out_of_range"`` — a hint is applied but the stated time was
        outside the bake's hot region, so the detector kept its real end.
      * ``"hint_ineffective"`` — a hint is applied to a bake with no confirmed
        exit (truncated), so there was nothing to anchor it to.
      * ``"no_hint"``        — no hint applied (or a user-added curve).

    Pure + unit-tested so the tab stays declarative.  The match-vs-out-of-range
    split is derived from the achieved duration (the detector does not tag a
    fallback separately from a genuine in-band match).
    """
    kind = curve.get("exit_candidate_kind")
    if kind == "manual_override":
        return "override"
    if kind == "expected_time_snap":
        return "truncated_snap" if curve.get("truncated") else "snapped"
    if applied_hint_s is not None and kind is None:
        # Detector found no exit candidate to anchor the stated time (a
        # truncated bake with no confirmed end); the hint had no effect.
        return "hint_ineffective"
    if applied_hint_s is not None and kind not in (None, "user_added"):
        achieved_s = float(curve.get("end_time", 0.0)) - float(
            curve.get("start_time", 0.0)
        )
        band = band_half_width(applied_hint_s, CURVE_DETECTION_CONFIG)
        if abs(achieved_s - applied_hint_s) <= band:
            return "matched_exit"
        return "hint_out_of_range"
    return "no_hint"


def bake_time_session_key(filename: str, stable_kind: str, stable_key) -> str:
    """Session/widget key for the actual-bake-time input, scoped by the curve's
    STABLE identity (``loader._curve_stable_key``) rather than the volatile
    ``curve_number`` — so a stated time follows the physical bake across the
    re-sort/renumber that an add/remove of a manual curve triggers."""
    return f"expected_bake_minutes__{filename}__{stable_kind}{stable_key}"


def build_detector_hint_list(loader, filename: str, session_store) -> list | None:
    """Assemble ``expected_durations_s`` in the DETECTOR's coordinate system from
    the per-curve bake-time widgets.

    The detector consumes ``expected_durations_s`` POSITIONALLY against its
    DETECTED curves (user-added curves are appended AFTER detection and are
    invisible to it), so the hint list must be indexed by detector position, not
    by ``all_curves`` position — otherwise a user-added curve interleaved ahead
    of a hinted bake shifts every subsequent hint onto the wrong physical bake.
    Returns ``None`` when no detector curve carries a hint (byte-identical
    no-hint behaviour downstream).
    """
    detected = []  # (detector_pos, all_curves_index)
    for i in range(len(loader.all_curves or [])):
        stable_kind, stable_key = loader._curve_stable_key(i)
        if stable_kind == "detector":
            detected.append((int(stable_key), i))
    if not detected:
        return None
    hints = [None] * (max(pos for pos, _ in detected) + 1)
    any_hint = False
    for pos, _i in detected:
        secs = minutes_to_seconds(
            session_store.get(bake_time_session_key(filename, "detector", pos))
        )
        hints[pos] = secs
        if secs is not None:
            any_hint = True
    return hints if any_hint else None


def extract_x_range_from_selection(
    selection_event: Any,
) -> tuple[float, float] | None:
    """Parse Streamlit's ``st.plotly_chart(on_select=..., selection_mode="box")``
    return value into ``(lo, hi)`` in MINUTES (since the detail plot's
    x-axis is in minutes) — or ``None`` when no box selection is
    present.  Defensive against missing fields and reverse-drag boxes.
    """
    if selection_event is None:
        return None
    selection = None
    if isinstance(selection_event, dict):
        selection = selection_event.get("selection")
    else:
        selection = getattr(selection_event, "selection", None)
        if selection is None and hasattr(selection_event, "get"):
            try:
                selection = selection_event.get("selection")
            except Exception:
                selection = None
    if not selection:
        return None
    boxes = None
    if isinstance(selection, dict):
        boxes = selection.get("box")
    else:
        boxes = getattr(selection, "box", None)
    if not boxes:
        return None
    box = boxes[0]
    xs = box.get("x") if isinstance(box, dict) else getattr(box, "x", None)
    if xs is None or len(xs) < 2:
        return None
    lo = float(min(xs))
    hi = float(max(xs))
    if hi <= lo:
        return None
    return (lo, hi)


def consume_box_selection(
    select_event: Any, consumed_key: str, session_state
) -> tuple[float, float] | None:
    """Return a drag-box's ``(lo, hi)`` x-range (minutes) the FIRST time a given
    selection is seen, else ``None``.

    Records a rounded signature under ``consumed_key`` so the same box is not
    re-applied on reruns triggered by other widgets.  Single source of truth for
    the raw-log-claim and detail-pin box paths (they differ only in what they do
    with the returned range).
    """
    sel_range = extract_x_range_from_selection(select_event)
    if sel_range is None:
        return None
    sig = (round(sel_range[0], 4), round(sel_range[1], 4))
    if session_state.get(consumed_key) == sig:
        return None
    session_state[consumed_key] = sig
    return sel_range


def time_minutes_to_idx(timestamps_s, target_minutes: float) -> int:
    """Find the raw_data row index whose Timestamp is closest to
    ``target_minutes``.

    ``timestamps_s`` is the raw_data Timestamp column (seconds).
    Returns an int in ``[0, len(timestamps_s) - 1]``.
    """
    target_s = float(target_minutes) * 60.0
    arr = np.asarray(timestamps_s, dtype=float)
    if len(arr) == 0:
        return 0
    pos = int(np.searchsorted(arr, target_s, side="left"))
    pos = max(0, min(pos, len(arr) - 1))
    if pos > 0 and abs(arr[pos - 1] - target_s) < abs(arr[pos] - target_s):
        pos -= 1
    return pos


# ---------------------------------------------------------------------------
# Tab render
# ---------------------------------------------------------------------------


def render() -> None:
    """Render the Curve Boundary Review tab."""
    st.subheader("🔬 Curve Boundary Review")
    st.caption(
        "Inspect the raw CSV with auto-detected bake windows. Drag a "
        "horizontal box on the detail plot to pin a manual start/end "
        "for any bake."
    )

    loader = st.session_state.get("loader")
    current_file = st.session_state.get("current_file")
    if loader is None or current_file is None or loader.raw_data is None:
        st.info("Upload a CSV from the sidebar to begin.")
        return

    curves = list(loader.all_curves or [])
    if not curves:
        st.warning("No curves detected in this CSV.")
        return

    # Top: full-log plot with detected windows overlaid.  Drag-box
    # selection on this plot CLAIMS a new region as a user-added
    # curve (M11 HMS Endeavour) — useful when the detector missed
    # a low-peak bake or a region the operator knows is a bake.
    st.markdown("#### Raw CSV log")
    st.caption(
        "💡 **Drag a horizontal box on the raw log** to claim a region "
        "the detector missed as a new bake — boundaries auto-refine "
        "and you can fine-tune below."
    )
    raw_fig = plot_raw_log_with_curves(loader.raw_data, curves)
    raw_select_event = st.plotly_chart(
        raw_fig,
        width="stretch",
        key=f"raw_log_{current_file}",
        on_select="rerun",
        selection_mode="box",
    )
    raw_sel_range = consume_box_selection(
        raw_select_event, f"raw_box_consumed__{current_file}", st.session_state
    )
    if raw_sel_range is not None:
        raw_timestamps = loader.raw_data["Timestamp"].to_numpy(dtype=float)
        new_start = time_minutes_to_idx(raw_timestamps, raw_sel_range[0])
        new_end = time_minutes_to_idx(raw_timestamps, raw_sel_range[1])
        if new_start < new_end:
            try:
                new_pos = loader.add_manual_curve(new_start, new_end)
                # Keep the operator reviewing the bake they just claimed: the
                # add re-sorts/renumbers, so re-seed the review radio to the new
                # curve's post-sort "Bake N" label.
                if new_pos is not None and new_pos >= 0:
                    st.session_state[f"boundary_review_select__{current_file}"] = (
                        f"Bake {new_pos + 1}"
                    )
                st.rerun()
            except (ValueError, RuntimeError) as exc:
                st.error(f"Could not add curve: {exc}")

    # Curve selector.
    curve_labels = [
        f"Bake {c.get('curve_number', i + 1)}"
        for i, c in enumerate(curves)
    ]
    # Curves are renumbered on every re-extract (a manual-curve add/remove re-sorts
    # by start_idx), so a persisted "Bake N" radio value can drop out of the option
    # list. Streamlit raises if a widget's stored value is not in ``options``; drop a
    # stale value so the radio falls back to the first bake instead of crashing.
    radio_key = f"boundary_review_select__{current_file}"
    if st.session_state.get(radio_key) not in curve_labels:
        st.session_state.pop(radio_key, None)
    selected_label = st.radio(
        "Select bake to review",
        options=curve_labels,
        horizontal=True,
        key=radio_key,
    )
    selected_idx = (
        curve_labels.index(selected_label)
        if selected_label in curve_labels
        else 0
    )
    curve = curves[selected_idx]
    curve_number = int(curve.get("curve_number", selected_idx + 1))

    _render_detail_panel(loader, current_file, curve, selected_idx, curve_number)


def _render_detail_panel(
    loader,
    current_file: str,
    curve: dict[str, Any],
    curve_index: int,
    curve_number: int,
) -> None:
    state_label = boundary_state_label(curve)
    badge_colour = {
        "override": "🟧",
        "user_added": "🟪",
        "snapped": "🟩",
        "auto": "🟦",
    }.get(state_label, "🟦")

    st.markdown(
        f"#### Bake {curve_number} detail &nbsp; {badge_colour} `{state_label}`"
    )

    detected_start = int(curve["start_idx"])
    detected_end = int(curve["end_idx"])
    raw_timestamps = loader.raw_data["Timestamp"].to_numpy(dtype=float)
    detected_start_min = float(raw_timestamps[detected_start]) / 60.0
    detected_end_min = float(raw_timestamps[detected_end]) / 60.0

    # Baseline (no-hint, no-override) decision snapshot from M7
    # HMS Inspector — used to show the operator what auto-optimisation
    # OR a manual override moved.
    baseline_curves = getattr(loader, "baseline_curves", []) or []
    baseline_curve = (
        baseline_curves[curve_index]
        if curve_index < len(baseline_curves)
        else None
    )
    baseline_start = (
        int(baseline_curve["start_idx"]) if baseline_curve else detected_start
    )
    baseline_end = (
        int(baseline_curve["end_idx"]) if baseline_curve else detected_end
    )
    baseline_kind = (
        baseline_curve.get("exit_candidate_kind") if baseline_curve else None
    )
    boundary_shifted = (
        baseline_start != detected_start or baseline_end != detected_end
    )

    # Two-column layout: plot left, readout right.
    plot_col, ctrl_col = st.columns([3, 2], gap="medium")

    with plot_col:
        detail_fig = plot_curve_detail(
            loader.raw_data,
            curve,
            override_indices=(detected_start, detected_end)
            if state_label == "override"
            else None,
            baseline_indices=(baseline_start, baseline_end)
            if boundary_shifted
            else None,
        )
        st.caption(
            "💡 **Drag a horizontal box on the plot** to pin start/end "
            "directly. Use the modebar (top-right) for zoom/pan."
        )
        select_event = st.plotly_chart(
            detail_fig,
            width="stretch",
            key=f"curve_detail_{current_file}_c{curve_number}",
            on_select="rerun",
            selection_mode="box",
        )
        # Convert a NEW box selection into a pinned boundary.  The
        # consume_box_selection gate prevents re-applying the same box
        # across reruns triggered by other widgets.
        sel_range = consume_box_selection(
            select_event,
            f"detail_box_consumed__{current_file}__c{curve_number}",
            st.session_state,
        )
        if sel_range is not None:
            box_start_idx = time_minutes_to_idx(raw_timestamps, sel_range[0])
            box_end_idx = time_minutes_to_idx(raw_timestamps, sel_range[1])
            if box_start_idx < box_end_idx:
                loader.set_curve_boundaries(
                    curve_index, box_start_idx, box_end_idx
                )
                st.rerun()

    with ctrl_col:
        st.markdown("**Detected**")
        st.text(
            f"Start: {detected_start_min:.2f} min (idx {detected_start})\n"
            f"End:   {detected_end_min:.2f} min (idx {detected_end})\n"
            f"Duration: {curve.get('duration', 0.0):.1f} min\n"
            f"Peak: {curve.get('max_temp', 0.0):.1f} °C\n"
            f"Kind: {curve.get('exit_candidate_kind') or '—'}"
        )

        # --- Actual bake time hint (M12) ------------------------------------
        # Tell auto-select how long this bake took (measured from the detected
        # start); it snaps the end very close to that time, preferring a real
        # oven-exit within tolerance.  The bake-time hint only steers AUTO
        # detection, so it is offered for detector curves only — a user-added
        # curve was already placed by hand (adjust it by box-select).  Both the
        # widget key and the loader hint list are keyed by the curve's STABLE
        # detector position, so a stated time always follows/reaches the correct
        # physical bake even after an add/remove re-sorts the curves.
        stable_kind, stable_key = loader._curve_stable_key(curve_index)
        if stable_kind == "detector":
            detector_pos = int(stable_key)
            durations = getattr(loader, "expected_durations_s", None)
            applied_hint_s = (
                durations[detector_pos]
                if durations is not None and detector_pos < len(durations)
                else None
            )
            bake_time_key = bake_time_session_key(
                current_file, "detector", detector_pos
            )
            # Seed from a hint the loader already carries, but only on first
            # render for this curve so an operator edit is never clobbered.
            if bake_time_key not in st.session_state:
                st.session_state[bake_time_key] = (
                    seconds_to_minutes(applied_hint_s) if applied_hint_s else None
                )
            st.number_input(
                "Actual bake time (min)",
                min_value=0.0,
                step=0.5,
                key=bake_time_key,
                help=(
                    "How long this bake actually took, from the detected start. "
                    "Auto-select snaps the end very close to it (preferring a real "
                    "oven-exit within tolerance). Leave blank for pure auto-detection."
                ),
            )
            if st.button(
                "Apply bake time",
                key=f"apply_bake_time__{current_file}__d{detector_pos}",
                width="stretch",
            ):
                loader.set_expected_durations(
                    build_detector_hint_list(loader, current_file, st.session_state)
                )
                # A re-detection can move this curve's window, so clear the stale
                # detail box-select signature — the next drag then pins fresh.
                st.session_state.pop(
                    f"detail_box_consumed__{current_file}__c{curve_number}", None
                )
                st.rerun()

            # Hint outcome — tell the operator how their stated time was applied.
            outcome = describe_hint_outcome(curve, applied_hint_s)
            if outcome == "snapped":
                st.info(
                    "Boundary snapped to your stated bake time "
                    "(no natural oven-exit within tolerance)."
                )
            elif outcome == "matched_exit":
                st.success(
                    "Matched a real oven-exit within tolerance of your stated time."
                )
            elif outcome == "truncated_snap":
                st.warning(
                    "Stated bake time runs past the end of this log — boundary "
                    "clamped to the last sample (truncated)."
                )
            elif outcome == "hint_out_of_range":
                st.warning(
                    "Stated bake time is outside this bake's hot region — kept the "
                    "detector's end. Adjust the time, or pin the boundary by "
                    "dragging a box on the plot."
                )
            elif outcome == "hint_ineffective":
                st.warning(
                    "This bake has no detected oven-exit to anchor a stated time "
                    "(the log looks truncated). Pin the boundary by dragging a box "
                    "on the plot instead."
                )

        # Outcome readout — three states surfaced for operator clarity:
        #   - boundary shifted → show Δ vs the no-hint, no-override baseline
        #   - state = override → reassure the detector input is ignored
        #   - else → nothing extra (auto detection unchanged)
        if boundary_shifted:
            delta_start = detected_start - baseline_start
            delta_end = detected_end - baseline_end
            baseline_start_min = float(raw_timestamps[baseline_start]) / 60.0
            baseline_end_min = float(raw_timestamps[baseline_end]) / 60.0
            st.markdown("**Boundary shift**")
            st.text(
                f"Baseline: {baseline_start_min:.2f}→{baseline_end_min:.2f} min "
                f"(idx {baseline_start}→{baseline_end}, {baseline_kind or '—'})\n"
                f"Now:      {detected_start_min:.2f}→{detected_end_min:.2f} min "
                f"(idx {detected_start}→{detected_end}, "
                f"{curve.get('exit_candidate_kind') or '—'})\n"
                f"Δstart: {delta_start:+d}  Δend: {delta_end:+d} samples"
            )
        elif state_label == "override":
            st.info(
                "Manual box-pin is in force; detector input — including the "
                "Actual bake time — is ignored. Reset to auto to let the bake "
                "time drive the boundary."
            )
        elif state_label == "user_added":
            st.info(
                "User-added bake (the detector did not find this region). "
                "Drag a box on the detail plot to fine-tune; click "
                "'Remove this bake' to discard."
            )

        # Reset / Remove dispatch:
        #   - Detector curve with override → Reset to auto: clear override
        #   - User-added curve → Remove this bake: drop the user-claim
        #   - Plain detector curve → Reset is a no-op but still rendered
        is_user_added = state_label == "user_added"
        button_label = "Remove this bake" if is_user_added else "Reset to auto"
        button_key = (
            f"remove_added__{current_file}__c{curve_number}"
            if is_user_added
            else f"reset_override__{current_file}__c{curve_number}"
        )
        button_clicked = st.button(
            button_label,
            key=button_key,
            width="stretch",
        )
        if button_clicked:
            if is_user_added:
                loader.remove_manual_curve(curve_index)
            else:
                loader.clear_curve_boundaries(curve_index)
            # Clear any lingering box-select consumed signature so the
            # next drag pins fresh.
            consumed_key = (
                f"detail_box_consumed__{current_file}__c{curve_number}"
            )
            if consumed_key in st.session_state:
                del st.session_state[consumed_key]
            st.rerun()
