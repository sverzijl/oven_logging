"""Single source of truth for the curve selection / session view.

Why this module exists
----------------------
Every analysis tab renders from session-state snapshots — ``st.session_state.data``
(the current curve's DataFrame slice), ``st.session_state.analyzer`` /
``s_curve_analyzer``, the flat ``st.session_state.all_curves`` list, and the
``tabs/_shared`` derived caches. Those snapshots were historically rebuilt only by
a handful of sidebar code paths (file load, curve switch, file removal, override /
metadata apply).

The Curve Boundary Review tab, however, mutates the loader directly
(``set_curve_boundaries`` / ``add_manual_curve`` / ``remove_manual_curve`` /
``clear_curve_boundaries``). Each of those REBINDS ``loader.all_curves`` to a fresh
list of fresh per-curve DataFrames (see ``loader._reapply_boundary_state``). Because
the boundary tab is the only consumer that reads ``loader.all_curves`` live, it was
the only pane that updated; every other tab kept rendering the detached snapshot and
went stale. That was the reported bug.

Rather than re-copy the loader into the snapshots after every mutation (and hope no
future tab forgets to), this module DERIVES the whole view from the live loaders
once per rerun. ``app.py`` calls :func:`rebuild_registry` at the top of every rerun,
so any loader mutation followed by ``st.rerun()`` propagates everywhere for free.

Two invariants make the derive correct:

* **Selection is an identity, not an index.** A boundary edit / manual-curve add
  re-sorts curves by ``start_idx`` and renumbers them, so a persisted integer index
  would silently alias a *different physical curve*. We persist
  ``(filename, loader._curve_stable_key(idx))`` and resolve it against the rebuilt
  list each rerun; only when that identity has vanished (its curve was removed) do we
  clamp to a neighbour.

* **Analyzers rebuild on a content-addressed signature.** The signature folds the
  current curve's boundaries *and* its sensor-role picks *and* its bake metadata, so
  a boundary edit, a sensor override, or a metadata change all invalidate the derived
  objects — while a no-op rerun rebuilds nothing (preserving the #20 dedup).

Other files' loaders are only READ here (``loader.all_curves``); they are never
re-extracted, so multi-file sessions stay cheap.
"""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from src.analysis.s_curve_analysis import SCurveAnalyzer
from src.analysis.thermal_analysis import ThermalAnalyzer

# Persisted selection identity: ``(filename, stable_key)`` where ``stable_key`` is
# ``loader._curve_stable_key(within_file_idx)`` — a value that survives the
# re-sort/renumber a boundary mutation triggers.
SELECTED_KEY = "selected_curve_key"
# Last-built derived signature, so analyzers are recreated only on a real change.
_SIG_KEY = "_registry_derived_sig"

# Session-state keys of the per-selection derived caches owned by ``tabs/_shared``.
# They are referenced here as bare strings ON PURPOSE: this module lives in the
# ``src/ui`` layer and is imported during ``app.py`` startup (via ``sidebar``), so it
# must NOT import ``tabs`` — doing so forces the whole tabs layer (and its heavy
# transitive imports) to initialise mid-startup, which broke the Streamlit Cloud
# cold start with an ImportError. ``test_curve_registry`` asserts these stay in sync
# with the canonical constants in ``tabs/_shared``.
_SHARED_DERIVED_CACHE_KEYS = ("_s_curve_report_cache", "_zone_analyzer_cache")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_curve(filename: str, within_idx: int) -> None:
    """Record an explicit selection intent (sidebar selectbox / initial load).

    Stores the selection by STABLE IDENTITY and re-derives the view. Use this when
    the user (or the load path) deliberately re-targets the analysis to a specific
    curve — as opposed to :func:`rebuild_registry`, which preserves the existing
    selection across a loader mutation.
    """
    files = st.session_state.get("files") or {}
    file_info = files.get(filename)
    if file_info is None:
        rebuild_registry()
        return
    loader = file_info["loader"]
    st.session_state[SELECTED_KEY] = (filename, _stable_key(loader, within_idx))
    rebuild_registry()


def rebuild_registry() -> None:
    """Re-derive the full session view from the live loaders. Idempotent.

    Safe to call on every rerun. Rebuilds the flat ``all_curves`` list, resolves the
    persisted selection by identity, re-points ``data`` / ``loader`` / ``metadata`` /
    indices at the resolved curve's FRESH slice, and rebuilds the analyzers +
    invalidates the ``_shared`` caches only when the content signature changed.
    """
    files = st.session_state.get("files") or {}
    if not files:
        _reset_to_empty()
        return

    flat = _build_flat_curves(files)
    st.session_state.all_curves = flat
    if not flat:
        _reset_to_empty()
        return

    gi = _resolve_selection(flat)
    if gi is None:
        # Identity vanished (or never set) — clamp the prior global position.
        old = st.session_state.get("global_curve_index", 0) or 0
        gi = max(0, min(int(old), len(flat) - 1))

    wrapper = flat[gi]
    filename = wrapper["filename"]
    within = wrapper["file_curve_index"]
    loader = wrapper["loader"]
    metadata = wrapper["metadata"]

    # Re-persist the identity so it tracks the resolved physical curve (e.g. after a
    # clamp lands on a neighbour, or a reorder moved it).
    st.session_state[SELECTED_KEY] = (filename, loader._curve_stable_key(within))
    st.session_state.global_curve_index = gi
    st.session_state.current_file = filename
    st.session_state.loader = loader
    st.session_state.metadata = metadata
    st.session_state.current_curve_index = within
    # set_current_curve has the side effect of pointing loader.data + the deprecated
    # loader.sensor_assignments at ``within`` — keep loader and session in agreement.
    loader.set_current_curve(within)
    st.session_state.data = loader.all_curves[within]["data"]

    sig = _derived_signature(loader, filename, within)
    if sig != st.session_state.get(_SIG_KEY):
        st.session_state.analyzer = ThermalAnalyzer(
            st.session_state.data, metadata, loader
        )
        st.session_state.s_curve_analyzer = SCurveAnalyzer(
            st.session_state.data, metadata, loader
        )
        _invalidate_derived_caches()
        st.session_state[_SIG_KEY] = sig


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _invalidate_derived_caches() -> None:
    """Drop the memoised S-curve report + ZoneAnalyzer so they rebuild from the
    fresh slice on next access. Pops the ``tabs/_shared`` cache keys directly to
    avoid importing the tabs layer from here (see ``_SHARED_DERIVED_CACHE_KEYS``)."""
    for key in _SHARED_DERIVED_CACHE_KEYS:
        st.session_state.pop(key, None)


def _stable_key(loader: Any, within_idx: int) -> Optional[tuple]:
    """``loader._curve_stable_key`` with a bounds guard (returns None if empty)."""
    curves = getattr(loader, "all_curves", None) or []
    if not curves:
        return None
    idx = max(0, min(int(within_idx), len(curves) - 1))
    return loader._curve_stable_key(idx)


def _build_flat_curves(files: dict) -> list[dict]:
    """Flat, cross-file curve list built FRESH from each loader's live all_curves.

    Also refreshes ``file_info['curves']`` to the live list so legacy readers (the
    sidebar file/curve labels) stay consistent. This is a reference assignment — it
    does NOT re-extract any loader.
    """
    flat: list[dict] = []
    for filename, file_info in files.items():
        loader = file_info["loader"]
        metadata = file_info["metadata"]
        curves = getattr(loader, "all_curves", None) or []
        file_info["curves"] = curves
        for i, curve in enumerate(curves):
            flat.append(
                {
                    "filename": filename,
                    "file_curve_index": i,
                    "curve_data": curve,
                    "loader": loader,
                    "metadata": metadata,
                }
            )
    return flat


def _resolve_selection(flat: list[dict]) -> Optional[int]:
    """Return the flat index whose stable identity matches the persisted selection,
    or ``None`` when the selection is unset or its identity no longer exists.
    """
    sel = st.session_state.get(SELECTED_KEY)
    if not sel:
        return None
    filename, stable_key = sel
    for gi, wrapper in enumerate(flat):
        if wrapper["filename"] != filename:
            continue
        loader = wrapper["loader"]
        if loader._curve_stable_key(wrapper["file_curve_index"]) == stable_key:
            return gi
    return None


def _derived_signature(loader: Any, filename: str, within: int) -> tuple:
    """Content-addressed signature of the current curve's derived inputs.

    Folds boundaries (start/end/samples), the resolved sensor-role picks, and the
    bake metadata. Any change invalidates the analyzers + ``_shared`` caches; a
    no-op rerun yields an identical signature so nothing heavy is rebuilt.
    """
    curve = loader.all_curves[within]
    parts: list[Any] = [
        filename,
        loader._curve_stable_key(within),
        curve.get("start_idx"),
        curve.get("end_idx"),
        curve.get("samples"),
    ]
    # Sensor-role picks (reflect manual overrides + classifier) and bake metadata.
    # Guarded: a role getter may legitimately return None / raise on a degenerate
    # curve, in which case the boundary parts above still make the signature change
    # on any re-slice.
    try:
        parts.append(loader.get_core_sensor(within))
        parts.append(loader.get_surface_sensor(within))
        ambient = loader.get_ambient_sensors(within)
        parts.append(tuple(ambient) if ambient else None)
        parts.append(loader.get_lid_sensor(within))
    except Exception:  # noqa: BLE001 — signature must never crash the render
        pass
    try:
        meta = loader.get_bake_metadata(within) or {}
        parts.append(tuple(sorted((str(k), _hashable(v)) for k, v in meta.items())))
    except Exception:  # noqa: BLE001
        pass
    return tuple(parts)


def _hashable(value: Any) -> Any:
    """Coerce a metadata value into something hashable for the signature tuple."""
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((str(k), _hashable(v)) for k, v in value.items()))
    return value


def _reset_to_empty() -> None:
    """Reset to the welcome-screen state (mirrors the sidebar file-removal reset)."""
    st.session_state.data = None
    st.session_state.metadata = None
    st.session_state.analyzer = None
    st.session_state.s_curve_analyzer = None
    st.session_state.loader = None
    st.session_state.current_curve_index = 0
    st.session_state.global_curve_index = 0
    st.session_state.current_file = None
    st.session_state.all_curves = []
    st.session_state[SELECTED_KEY] = None
    st.session_state[_SIG_KEY] = None
    _invalidate_derived_caches()
