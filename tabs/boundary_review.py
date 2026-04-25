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
  M10 HMS Vanguard — strip the redundant entry widgets (hint
    number_input, manual slider, Apply button) since box-select is
    now the sole input mechanism.  Loader hint API is untouched.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import streamlit as st

from src.visualization.boundary_review_plots import (
    plot_curve_detail,
    plot_raw_log_with_curves,
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_boundary_review_tab.py)
# ---------------------------------------------------------------------------


def boundary_state_label(curve: dict[str, Any]) -> str:
    """One-word UI badge for a curve: ``override`` or ``auto``.

    M10 HMS Vanguard simplified this — the hint widget is gone, so
    ``hint`` is no longer a reachable state from this tab.
    """
    if curve.get("exit_candidate_kind") == "manual_override":
        return "override"
    return "auto"


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

    # Top: full-log plot with detected windows overlaid.
    st.markdown("#### Raw CSV log")
    raw_fig = plot_raw_log_with_curves(loader.raw_data, curves)
    st.plotly_chart(
        raw_fig,
        use_container_width=True,
        key=f"raw_log_{current_file}",
    )

    # Curve selector.
    curve_labels = [
        f"Bake {c.get('curve_number', i + 1)}"
        for i, c in enumerate(curves)
    ]
    selected_label = st.radio(
        "Select bake to review",
        options=curve_labels,
        horizontal=True,
        key=f"boundary_review_select__{current_file}",
    )
    selected_idx = curve_labels.index(selected_label)
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
    badge_colour = "🟧" if state_label == "override" else "🟦"

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
            use_container_width=True,
            key=f"curve_detail_{current_file}_c{curve_number}",
            on_select="rerun",
            selection_mode="box",
        )
        # Convert a NEW box selection into a pinned boundary.  The
        # consumed-signature gate prevents re-applying the same box
        # across reruns triggered by other widgets.
        sel_range = extract_x_range_from_selection(select_event)
        if sel_range is not None:
            consumed_key = (
                f"detail_box_consumed__{current_file}__c{curve_number}"
            )
            sig = (round(sel_range[0], 4), round(sel_range[1], 4))
            if st.session_state.get(consumed_key) != sig:
                box_start_idx = time_minutes_to_idx(
                    raw_timestamps, sel_range[0]
                )
                box_end_idx = time_minutes_to_idx(
                    raw_timestamps, sel_range[1]
                )
                if box_start_idx < box_end_idx:
                    loader.set_curve_boundaries(
                        curve_index, box_start_idx, box_end_idx
                    )
                    st.session_state[consumed_key] = sig
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
                "Manual override pinned the boundary; detector input ignored."
            )

        # Reset to auto — single recovery button that clears the manual
        # override for this curve.  Box-select is the only way to re-pin.
        reset_clicked = st.button(
            "Reset to auto",
            key=f"reset_override__{current_file}__c{curve_number}",
            use_container_width=True,
        )
        if reset_clicked:
            loader.clear_curve_boundaries(curve_index)
            consumed_key = (
                f"detail_box_consumed__{current_file}__c{curve_number}"
            )
            if consumed_key in st.session_state:
                del st.session_state[consumed_key]
            st.rerun()
