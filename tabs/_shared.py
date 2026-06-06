"""Per-(file, curve) analyzer/report dedup helpers (#20).

Several tabs need the same heavyweight derived objects:

* ``ZoneAnalyzer`` — built in BOTH the Zone Analysis and Recommendations tabs.
* the S-curve optimization report — computed in BOTH the S-Curve Analysis and
  Recommendations tabs.

``st.tabs`` renders *every* tab body eagerly on each rerun (the inactive tabs
are merely hidden client-side), so without deduping these objects were rebuilt
two-or-more times per rerun. ``@st.cache_data`` is a poor fit here because the
inputs (the ``ThermalProfileLoader`` and the per-curve ``DataFrame``) are not
hashable. Instead we cache the result in ``st.session_state`` keyed by the
hashable identity of the current selection — ``(current_file,
current_curve_index, product_type)`` — and rebuild only when that key changes.

Sidebar widgets (curve switch, override apply, product change) already recreate
the analyzers in ``st.session_state``; this layer only memoises the *derived*
report/ZoneAnalyzer for the duration of a single selection.
"""

from __future__ import annotations

import streamlit as st

from src.analysis.zone_analysis import ZoneAnalyzer

_S_CURVE_REPORT_CACHE = "_s_curve_report_cache"
_ZONE_ANALYZER_CACHE = "_zone_analyzer_cache"


def _selection_key() -> tuple:
    """Hashable identity of the current (file, curve, product) selection."""
    return (
        st.session_state.get("current_file"),
        st.session_state.get("current_curve_index"),
        st.session_state.get("product_type", "white_pan"),
    )


def get_s_curve_report() -> dict:
    """Return the S-curve optimization report, building it at most once per
    selection. Threads the product selector (#8)."""
    key = _selection_key()
    cached = st.session_state.get(_S_CURVE_REPORT_CACHE)
    if cached is not None and cached[0] == key:
        return cached[1]

    product_type = st.session_state.get("product_type", "white_pan")
    report = st.session_state.s_curve_analyzer.generate_optimization_report(
        product_type=product_type
    )
    st.session_state[_S_CURVE_REPORT_CACHE] = (key, report)
    return report


def get_zone_analyzer() -> ZoneAnalyzer:
    """Return the ZoneAnalyzer for the current curve, building it at most once
    per selection."""
    key = _selection_key()
    cached = st.session_state.get(_ZONE_ANALYZER_CACHE)
    if cached is not None and cached[0] == key:
        return cached[1]

    analyzer = ZoneAnalyzer(
        st.session_state.data,
        st.session_state.metadata["sample_period_s"],
        st.session_state.loader,
    )
    st.session_state[_ZONE_ANALYZER_CACHE] = (key, analyzer)
    return analyzer
