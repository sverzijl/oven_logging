"""Shared core-confidence UI helpers (M29).

Two pure helpers — no Streamlit imports — so every tab and the sidebar route
their core-confidence messaging through one source of truth:

* :func:`core_confidence_banner_text` — maps a ``(confidence, reason)`` pair
  (from ``loader.get_core_confidence``) to a ``(level, message)`` pair the
  Streamlit caller dispatches to ``st.warning`` / ``st.caption``. Consumed by
  the Temperature Profile, S-Curve, and Spatial Evolution tabs.
* :func:`bake_metadata_status_line` — maps the loader's active core method to
  an ``(active_model, detail)`` pair for the sidebar Bake Metadata expander,
  declaring which model is feeding the *current* core trace.

Centralising the predicate avoids the per-tab re-derivation the M18 plan
flagged: the ``low_extrapolated`` label was previously only inside the
classifier's diagnostic ``fit_quality`` dict and never reached the UI.
"""

from __future__ import annotations

from typing import Optional


def core_confidence_banner_text(
    confidence: Optional[str], reason: Optional[str]
) -> tuple:
    """Map a core-confidence label to a ``(level, message)`` banner pair.

    ``level`` is one of:

    * ``"warning"`` — ``confidence == "low"``. The message invites the
      operator to supply bake metadata so Method 4's geometric core engages.
    * ``"caption"`` — ``confidence == "medium"`` (a boundary estimate).
    * ``None`` — ``confidence == "high"`` (or unknown): no banner.

    The classifier collapses Method 1's ``low_extrapolated`` to the plain
    ``"low"`` enum (the qualifier survives in ``reason``), so the predicate
    matches ``"low"`` here, not the qualified string.
    """
    if confidence == "low":
        message = "⚠️ Core temperature confidence: **low**."
        if reason:
            message += f" {reason}"
        message += (
            "\n\nEnter *Loaf thickness* and *Probe insertion depth* in the "
            "sidebar's **Bake Metadata** expander to engage the geometric-core "
            "model (Method 4) for a deterministic core position."
        )
        return ("warning", message)
    if confidence == "medium":
        detail = reason or "boundary estimate"
        return ("caption", f"Core temperature confidence: medium — {detail}")
    return (None, None)


# Active-model tag -> Streamlit render kind for the sidebar status line.
STATUS_RENDER_KIND = {
    "manual_override": "info",
    "method_4": "success",
    "method_4_degraded": "warning",
    "method_1_high": "caption",
    "method_1_medium": "caption",
    "method_1_low": "warning",
    "fallback": "caption",
}


def bake_metadata_status_line(loader, curve_idx: int) -> tuple:
    """Return ``(active_model, detail)`` for the sidebar status line.

    ``active_model`` is a key of :data:`STATUS_RENDER_KIND` and ``detail`` is
    the human-readable justification (reused from ``loader.get_core_confidence``
    so the sidebar and the tab banners never disagree). The mapping from the
    loader's :meth:`~src.data.loader.ThermalProfileLoader.active_core_method`
    tag:

    * ``"override"``         -> ``"manual_override"``
    * ``"method4"``          -> ``"method_4"``         (geometric core in-probe)
    * ``"method4_degraded"`` -> ``"method_4_degraded"`` (core past probe tip)
    * ``"classifier"``       -> ``"method_1_{high,medium,low}"`` by confidence
    * ``"fallback"``         -> ``"fallback"``
    """
    tag = loader.active_core_method(curve_idx)
    confidence, reason = loader.get_core_confidence(curve_idx)

    if tag == "override":
        return ("manual_override", reason)
    if tag == "method4":
        return ("method_4", reason)
    if tag == "method4_degraded":
        return ("method_4_degraded", reason)
    if tag == "classifier":
        if confidence == "low":
            return ("method_1_low", reason)
        if confidence == "medium":
            return ("method_1_medium", reason)
        return ("method_1_high", reason)
    return ("fallback", reason)
