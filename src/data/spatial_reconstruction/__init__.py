"""Spatial reconstruction package — replaces the discrete sensor-classification
heuristics in surface_sensor_detector.py and thermodynamic_sensor_classifier.py
with a 1D temperature-profile model T(x).

Public API:
- :func:`classify` — end-to-end role classifier; returns a SpatialAssignment.
- :class:`SpatialAssignment`, :class:`PositionalAssignment` — result types.
- :class:`ProfileFit`, :func:`extract_features`, :func:`compute_oven_proxy` —
  intermediate fit objects, exposed for testing and future Stefan model.
- :data:`PROBE_GEOMETRIES`, :func:`lookup_geometry` — probe geometry registry.
"""

from .classifier import classify, SpatialAssignment, PositionalAssignment
from .profile import ProfileFit, extract_features, compute_oven_proxy
from .geometry import PROBE_GEOMETRIES, lookup_geometry
from .piecewise import fit_piecewise
from .stefan import fit_stefan
from .temporal import classify_temporal, TemporalAssignment
from .comparison import (
    ModelComparison,
    benchmark_fixture,
    benchmark_all_cases,
    write_comparison_report,
)

__all__ = [
    "classify",
    "SpatialAssignment",
    "PositionalAssignment",
    "ProfileFit",
    "extract_features",
    "compute_oven_proxy",
    "PROBE_GEOMETRIES",
    "lookup_geometry",
    "fit_piecewise",
    "fit_stefan",
    "classify_temporal",
    "TemporalAssignment",
    "ModelComparison",
    "benchmark_fixture",
    "benchmark_all_cases",
    "write_comparison_report",
]
