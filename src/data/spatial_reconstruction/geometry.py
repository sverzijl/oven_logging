"""Probe geometry registry for spatial reconstruction.

A Combustion Inc. probe carries 8 sensors (T1..T8) along its length. The
spatial reconstructor needs each sensor's position along the probe so it can
fit a temperature profile T(x). Today only the *uniform* fallback is
populated — when a probe S/N or model is recognised in the future, that entry
can be added here without touching the call-sites.

Positions are stored in [0, 1] normalised coordinates. Absolute mm spacing is
recorded as ``None`` until the Combustion datasheet is in hand for a given
probe model; the piecewise fit only needs the normalised positions, so the
absolute scale is not currently load-bearing.
"""

from __future__ import annotations

from typing import Optional


PROBE_GEOMETRIES = {
    "default_uniform": {
        # Eight sensors equally spaced; T1 at 0, T8 at 1, step = 1/7.
        # This matches the canonical SENSOR_LIST ordering (T1 at probe tip).
        "sensor_positions_normalised": tuple(i / 7 for i in range(8)),
        "sensor_positions_mm": None,
    },
    # Future entries (populate when the Combustion datasheet is confirmed):
    # "CPT-101": { ... }
}


def lookup_geometry(
    probe_sn: Optional[str] = None,
    probe_model: Optional[str] = None,
) -> dict:
    """Return the probe geometry record for a given probe.

    Resolution order (M2a — only the fallback is populated):
    1. ``probe_model`` keyword match into ``PROBE_GEOMETRIES``.
    2. ``probe_sn`` prefix lookup (no S/N → model mapping in M2a).
    3. ``default_uniform`` fallback.

    Returns a ``dict`` with at least ``sensor_positions_normalised`` (an
    8-tuple in [0, 1]) and ``sensor_positions_mm`` (``None`` when unknown).
    """
    if probe_model and probe_model in PROBE_GEOMETRIES:
        return PROBE_GEOMETRIES[probe_model]
    # Future: S/N → model mapping. For M2a always falls through.
    return PROBE_GEOMETRIES["default_uniform"]
