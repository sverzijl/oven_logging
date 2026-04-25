"""Curve Boundary Review tab (M3 HMS Indomitable).

Operator workflow:

1. View the full raw CSV log with auto-detected bake windows overlaid.
2. Pick a curve to review via radio selector.
3. Edit its expected bake time → triggers M3/M4 hint refinement
   (no new logic — see ``loader.set_expected_durations``).
4. Or pin a manual start/end override → bypasses the detector
   entirely for that curve (see ``loader.set_curve_boundaries``).
5. Reset to auto → clears both override and hint for the curve.

Widget keys are scoped by ``(filename, curve_number)`` so swapping the
currently-viewed curve does not bleed widget state across curves.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import streamlit as st

from config.constants import CURVE_DETECTION_CONFIG
from src.ui.expected_duration_widgets import (
    build_hint_list_from_session,
    seconds_to_minutes,
    session_key_for_curve,
)
from src.visualization.boundary_review_plots import (
    plot_curve_detail,
    plot_raw_log_with_curves,
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_boundary_review_tab.py)
# ---------------------------------------------------------------------------


def manual_start_key(filename: str, curve_number: int) -> str:
    """Streamlit widget key for the manual-start-index input."""
    return f"manual_start_idx__{filename}__c{int(curve_number)}"


def manual_end_key(filename: str, curve_number: int) -> str:
    """Streamlit widget key for the manual-end-index input."""
    return f"manual_end_idx__{filename}__c{int(curve_number)}"


def compute_hint_window_seconds(
    *,
    end_time_s: float,
    hint_seconds: float | None,
    tolerance_frac: float,
    min_tolerance_seconds: float = 60.0,
) -> tuple[float, float] | None:
    """Return ``(lo, hi)`` for the hint-window vrect, or ``None`` when
    no hint is in effect.

    Mirrors the detector's tolerance-band calculation in M3 so the plot
    band matches the actual auto-optimisation window.
    """
    if hint_seconds is None or hint_seconds <= 0.0:
        return None
    band = max(hint_seconds * tolerance_frac, min_tolerance_seconds)
    centre = float(end_time_s) - float(hint_seconds)
    return (centre - band, centre + band)


def boundary_state_label(
    curve: dict[str, Any], hint_active: bool = False
) -> str:
    """One-word UI badge for a curve: ``override`` / ``hint`` / ``auto``."""
    kind = curve.get("exit_candidate_kind")
    if kind == "manual_override":
        return "override"
    if hint_active:
        return "hint"
    return "auto"


def time_minutes_to_idx(timestamps_s, target_minutes: float) -> int:
    """Find the raw_data row index whose Timestamp is closest to
    ``target_minutes``.  Used to convert operator-entered manual
    override times (in minutes) back to sample indices for the
    loader's ``set_curve_boundaries`` API.

    ``timestamps_s`` is the raw_data Timestamp column (seconds).
    Returns an int in ``[0, len(timestamps_s) - 1]``.
    """
    target_s = float(target_minutes) * 60.0
    arr = np.asarray(timestamps_s, dtype=float)
    if len(arr) == 0:
        return 0
    pos = int(np.searchsorted(arr, target_s, side="left"))
    pos = max(0, min(pos, len(arr) - 1))
    # searchsorted gives the LEFT insertion point; check whether the
    # neighbour to the left is actually closer.
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
        "See the raw CSV with auto-detected bake windows. Adjust a "
        "bake's expected duration to refine the boundary, or pin a "
        "manual start/end if the auto-optimisation can't reach the "
        "boundary you want."
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

    # ------------------------------------------------------------------
    # Top: full-log plot with detected windows overlaid
    # ------------------------------------------------------------------
    st.markdown("#### Raw CSV log")
    raw_fig = plot_raw_log_with_curves(loader.raw_data, curves)
    st.plotly_chart(
        raw_fig,
        use_container_width=True,
        key=f"raw_log_{current_file}",
    )

    # ------------------------------------------------------------------
    # Curve selector
    # ------------------------------------------------------------------
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
    hint_key = session_key_for_curve(current_file, curve_number)
    hint_minutes_raw = st.session_state.get(hint_key)
    hint_minutes = float(hint_minutes_raw) if hint_minutes_raw else 0.0
    hint_seconds = hint_minutes * 60.0 if hint_minutes > 0.0 else None
    hint_active = hint_seconds is not None

    state_label = boundary_state_label(curve, hint_active=hint_active)
    badge_colour = {
        "auto": "🟦",
        "hint": "🟩",
        "override": "🟧",
    }.get(state_label, "⬜")

    st.markdown(
        f"#### Bake {curve_number} detail &nbsp; {badge_colour} `{state_label}`"
    )

    detected_start = int(curve["start_idx"])
    detected_end = int(curve["end_idx"])
    raw_timestamps = loader.raw_data["Timestamp"].to_numpy(dtype=float)
    n_raw = len(raw_timestamps)
    log_max_minutes = float(raw_timestamps[-1]) / 60.0 if n_raw > 0 else 0.0

    # Manual override values from session — stored in MINUTES so the
    # operator can read them off the time-axis plot (M6 HMS Refit).
    # Defaults: detector's start/end timestamps converted to minutes.
    ms_key = manual_start_key(current_file, curve_number)
    me_key = manual_end_key(current_file, curve_number)
    detected_start_min = float(raw_timestamps[detected_start]) / 60.0
    detected_end_min = float(raw_timestamps[detected_end]) / 60.0
    manual_start_min = float(st.session_state.get(ms_key, detected_start_min))
    manual_end_min = float(st.session_state.get(me_key, detected_end_min))

    # Convert MINUTES → IDX for the live-preview vlines and the eventual
    # loader call.
    preview_start_idx = time_minutes_to_idx(raw_timestamps, manual_start_min)
    preview_end_idx = time_minutes_to_idx(raw_timestamps, manual_end_min)

    # Live preview: show override vlines whenever the operator's typed
    # values differ from the detector's decision, even before they hit
    # Apply.  Once applied, ``state_label == "override"`` keeps them
    # visible (now reflecting the pinned curve dict).
    show_override_overlay = (
        state_label == "override"
        or preview_start_idx != detected_start
        or preview_end_idx != detected_end
    )

    # ------------------------------------------------------------------
    # Two-column layout: plot left, controls right
    # ------------------------------------------------------------------
    plot_col, ctrl_col = st.columns([3, 2], gap="medium")

    with plot_col:
        hint_window = compute_hint_window_seconds(
            end_time_s=float(raw_timestamps[detected_end]),
            hint_seconds=hint_seconds,
            tolerance_frac=float(
                CURVE_DETECTION_CONFIG.get("EXPECTED_DURATION_TOLERANCE_FRAC", 0.15)
            ),
            min_tolerance_seconds=float(
                CURVE_DETECTION_CONFIG.get(
                    "EXPECTED_DURATION_MIN_TOLERANCE_SECONDS", 60.0
                )
            ),
        )
        override_indices = (
            (preview_start_idx, preview_end_idx)
            if show_override_overlay
            else None
        )
        detail_fig = plot_curve_detail(
            loader.raw_data,
            curve,
            hint_window_s=hint_window,
            override_indices=override_indices,
        )
        st.plotly_chart(
            detail_fig,
            use_container_width=True,
            key=f"curve_detail_{current_file}_c{curve_number}",
        )

    with ctrl_col:
        st.markdown("**Detected**")
        st.text(
            f"Start: {detected_start_min:.2f} min (idx {detected_start})\n"
            f"End:   {detected_end_min:.2f} min (idx {detected_end})\n"
            f"Duration: {curve.get('duration', 0.0):.1f} min\n"
            f"Peak: {curve.get('max_temp', 0.0):.1f} °C\n"
            f"Kind: {curve.get('exit_candidate_kind') or '—'}"
        )

        st.markdown("**Hint**")
        st.number_input(
            "Expected bake time (min)",
            key=hint_key,
            min_value=0.0,
            max_value=240.0,
            step=0.5,
            value=hint_minutes,
            help=(
                "Optional. When set, the detector arbitrates end candidates "
                "within ±15 % of the hinted duration. Set to 0 to disable."
            ),
        )

        st.markdown("**Manual override**")
        st.caption(
            f"Hover the plot to read off times. Current preview: "
            f"idx {preview_start_idx} → {preview_end_idx} "
            f"({preview_end_idx - preview_start_idx} samples)."
        )
        new_manual_start_min = st.number_input(
            "Start time (min)",
            key=ms_key,
            min_value=0.0,
            max_value=log_max_minutes,
            step=0.1,
            value=manual_start_min,
            help="Drag-free manual start. Snaps to nearest sample on Apply.",
        )
        new_manual_end_min = st.number_input(
            "End time (min)",
            key=me_key,
            min_value=0.0,
            max_value=log_max_minutes,
            step=0.1,
            value=manual_end_min,
            help="Drag-free manual end. Snaps to nearest sample on Apply.",
        )

        apply_col, reset_col = st.columns(2)
        with apply_col:
            apply_clicked = st.button(
                "Apply override",
                key=f"apply_override__{current_file}__c{curve_number}",
                type="primary",
                use_container_width=True,
            )
        with reset_col:
            reset_clicked = st.button(
                "Reset to auto",
                key=f"reset_override__{current_file}__c{curve_number}",
                use_container_width=True,
            )

        if apply_clicked:
            apply_start_idx = time_minutes_to_idx(
                raw_timestamps, new_manual_start_min
            )
            apply_end_idx = time_minutes_to_idx(
                raw_timestamps, new_manual_end_min
            )
            if apply_start_idx >= apply_end_idx:
                st.error("Start time must be before end time.")
            else:
                loader.set_curve_boundaries(
                    curve_index, apply_start_idx, apply_end_idx
                )
                st.rerun()

        if reset_clicked:
            loader.clear_curve_boundaries(curve_index)
            # Clear hint widget too — Reset to auto means BOTH off.
            if hint_key in st.session_state:
                del st.session_state[hint_key]
            # Clear manual time widgets so defaults reapply on rerun.
            if ms_key in st.session_state:
                del st.session_state[ms_key]
            if me_key in st.session_state:
                del st.session_state[me_key]
            # Also drop the hint from the loader if no other curve carries one.
            other_hints = build_hint_list_from_session(
                filename=current_file,
                n_curves=len(loader.all_curves),
                session_store=st.session_state,
            )
            if loader.expected_durations_s != other_hints:
                loader.set_expected_durations(other_hints)
            st.rerun()

    # ------------------------------------------------------------------
    # Hint plumbing — runs every render so widget edits flow to the loader
    # ------------------------------------------------------------------
    hint_list = build_hint_list_from_session(
        filename=current_file,
        n_curves=len(loader.all_curves),
        session_store=st.session_state,
    )
    if loader.expected_durations_s != hint_list:
        loader.set_expected_durations(hint_list)
        st.rerun()
