"""Data loading and parsing utilities for thermal profile CSV files."""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, Union, List
import re
from datetime import datetime
import io

_log = logging.getLogger(__name__)
from config.constants import (
    CURVE_DETECTION_CONFIG,
    INTERNAL_SENSOR_CONFIG,
    SENSOR_LIST,
)
from src.data.sensor_assignment_manager import SensorAssignmentManager
from src.data.column_helpers import (
    get_core_temperature_column,
    resolve_core_temperature_series,
)
from src.data.curve_boundary_detector import CurveBoundaryDetector
from src.data.spatial_reconstruction import classify, lookup_geometry


class ThermalProfileLoader:
    """Load and parse thermal profile CSV files from Combustion Inc. probes."""

    def __init__(self):
        self.metadata = {}
        self.data = None
        self.sensor_assignments = {}  # Deprecated - kept for backward compatibility
        self.curve_sensor_assignments = {}  # New: per-curve sensor assignments
        self.all_curves = []  # Store all detected curves
        self.current_curve_index = 0  # Track which curve is currently selected
        self._sensor_overrides = {}  # Store sensor overrides per curve {curve_index: {'core': [...], 'surface': [...], 'ambient': [...]}}
        self._sensor_manager = SensorAssignmentManager(self)
        # Optional per-curve expected-duration hint (M5 HMS Dauntless).
        # None = no hint; list[float | None] = positional per-curve hints,
        # matched to detected curves by order.  Consumed by
        # ``_extract_all_baking_curves`` which forwards to
        # ``CurveBoundaryDetector.extract_curves(expected_durations_s=...)``.
        # UI layer (M6 Spartan) sets this via ``set_expected_durations``
        # to get cache-invalidation for free.
        self.expected_durations_s: list[float | None] | None = None
        # Full pre-curve-extraction DataFrame (M1 HMS Ardent, mission
        # 2026-04-24_233307_c5744e63).  Today ``self.data`` is overwritten
        # with the first curve's slice immediately after extraction;
        # ``raw_data`` keeps the full log so the Curve Boundary Review
        # tab (M3) can plot it with detected windows overlaid.
        # Also fixes a latent bug: ``set_expected_durations`` previously
        # re-ran detection on ``self.data`` (the first curve only),
        # silently dropping bakes 2+ on multi-bake CSVs.  Re-detection
        # now uses ``self.raw_data``.
        self.raw_data: pd.DataFrame | None = None
        # Manual per-curve boundary overrides (M1 HMS Ardent).
        # Keyed by curve_index; value is ``(start_idx, end_idx)`` in the
        # raw_data index space.  When present, the override takes
        # precedence over the detector AND the hint refinement.
        self._boundary_overrides: dict[int, tuple[int, int]] = {}
        # User-claimed regions that the detector missed (M11 HMS
        # Endeavour, mission 2026-04-25_111859_56ebe5ee).  Each tuple
        # is ``(start_idx, end_idx)`` in the raw_data index space.
        # The Boundary Review tab populates this via
        # ``add_manual_curve``; the boundaries are auto-refined on
        # the sub-slice and the resulting curve appears in
        # ``all_curves`` tagged with ``_user_added_idx`` (its position
        # in this list).  ``set_curve_boundaries`` on a user-added
        # curve updates THIS list rather than ``_boundary_overrides``.
        self._added_curves: list[tuple[int, int]] = []
        # Snapshot of the detector's no-hint, no-override decision
        # taken at ``load_csv`` time (M7 HMS Inspector, mission
        # 2026-04-25_092326_ec2fbd6e).  The Boundary Review tab uses
        # this to show the operator what the auto-optimisation moved.
        # Subsequent set_expected_durations / set_curve_boundaries
        # calls leave it untouched.
        self.baseline_curves: list = []
        # Per-curve bake metadata (M18 HMS Vigilant — Method 4 stub).
        # Keyed by curve_index. Recognised keys (all optional):
        #   - loaf_thickness_mm: float
        #   - insertion_depth_mm: float (probe tip below loaf top surface)
        #   - oven_setpoint_C: float
        #   - lid_state: 'unknown' | 'open' | 'lidded' | 'tin'
        #   - steam_phase_minutes: float
        # When ``loaf_thickness_mm`` and ``insertion_depth_mm`` are both
        # present, ``get_geometric_core_position_mm_from_tip`` computes
        # ``insertion_depth_mm - loaf_thickness_mm/2`` (positive = core above
        # the probe tip, between T1 and T8 -> interpolation; negative = core
        # past/below the tip -> degraded to T1), and
        # ``get_core_temperature_series`` uses linear interpolation between
        # adjacent T-sensors at that geometric position. When metadata is
        # absent, the classifier path (Method 1 relaxed clamp) is used
        # unchanged.
        self._bake_metadata: dict[int, dict] = {}
        # Per-curve memoised IsothermalAssignment (M30 Spatial Evolution tab).
        # Keyed by curve_index; populated lazily by ``isothermal_assignment``
        # and invalidated by the override / boundary / manual-curve mutators.
        self._isothermal_cache: dict = {}

    def load_csv(self, file_path: str = None, file_buffer=None) -> Tuple[pd.DataFrame, Dict]:
        """
        Load a thermal profile CSV file.
        
        Args:
            file_path: Path to the CSV file (optional)
            file_buffer: File buffer object (optional)
            
        Returns:
            Tuple of (data DataFrame, metadata dict)
        """
        # Read the metadata from header lines
        if file_buffer is not None:
            # Convert to string buffer if needed
            if hasattr(file_buffer, 'read'):
                # Read all content
                content = file_buffer.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8')
                
                # Parse metadata from content
                self.metadata = self._parse_metadata_from_content(content)
                
                # Create StringIO for pandas
                content_buffer = io.StringIO(content)
                self.data = pd.read_csv(content_buffer, skiprows=10)
            else:
                raise ValueError("Invalid file buffer provided")
        else:
            self.metadata = self._parse_metadata(file_path)
            # Read the actual data
            self.data = pd.read_csv(file_path, skiprows=10)
        
        # Clean and validate the data
        self.data = self._clean_data(self.data)

        # Preserve the full pre-curve-extraction DataFrame for the
        # Curve Boundary Review tab (M1 HMS Ardent).  ``copy()`` so
        # downstream tab code mutating ``self.data`` cannot leak back.
        self.raw_data = self.data.copy()

        # Extract all baking curves
        self.all_curves = self._extract_all_baking_curves(self.data)

        # Snapshot the detector's no-hint, no-override decision so the
        # Boundary Review tab can show what auto-optimisation moved
        # later (M7 HMS Inspector).  At this point neither
        # expected_durations_s nor _boundary_overrides are populated,
        # so all_curves IS the baseline by definition.
        self.baseline_curves = [self._copy_curve_dict(c) for c in self.all_curves]

        # Set the first curve as default if any curves found
        if self.all_curves:
            self.data = self.all_curves[0]['data']
            self.current_curve_index = 0

        return self.data, self.metadata

    @staticmethod
    def _copy_curve_dict(curve: dict) -> dict:
        """Return an independent copy of a curve descriptor for the
        baseline snapshot.  The ``data`` slice is duplicated so a tab
        mutating it cannot bleed into ``all_curves``; other fields are
        primitives (int/float/bool/str) and copy by value.
        """
        out = dict(curve)
        if "data" in out and out["data"] is not None:
            out["data"] = out["data"].copy()
        return out
    
    def _parse_metadata(self, file_path: str) -> Dict:
        """Parse metadata from the CSV header."""
        metadata = {}
        
        with open(file_path, 'r') as f:
            lines = f.readlines()[:10]
            
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()
                
        # Parse specific fields
        if 'Sample Period' in metadata:
            # Strip trailing commas from the value
            sample_period_str = metadata['Sample Period'].rstrip(',')
            metadata['sample_period_ms'] = int(sample_period_str)
            metadata['sample_period_s'] = metadata['sample_period_ms'] / 1000.0
            
        if 'Created' in metadata:
            try:
                metadata['created_datetime'] = datetime.strptime(
                    metadata['Created'], 
                    '%Y-%m-%d %H:%M:%S'
                )
            except:
                metadata['created_datetime'] = None
                
        return metadata
    
    def _parse_metadata_from_content(self, content: str) -> Dict:
        """Parse metadata from file content string."""
        metadata = {}
        
        # Split into lines and get first 10
        lines = content.split('\n')[:10]
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()
                
        # Parse specific fields
        if 'Sample Period' in metadata:
            # Strip trailing commas from the value
            sample_period_str = metadata['Sample Period'].rstrip(',')
            metadata['sample_period_ms'] = int(sample_period_str)
            metadata['sample_period_s'] = metadata['sample_period_ms'] / 1000.0
            
        if 'Created' in metadata:
            try:
                metadata['created_datetime'] = datetime.strptime(
                    metadata['Created'], 
                    '%Y-%m-%d %H:%M:%S'
                )
            except:
                metadata['created_datetime'] = None
                
        return metadata
    
    def _parse_metadata_from_buffer(self, file_buffer) -> Dict:
        """Parse metadata from a file buffer."""
        metadata = {}
        
        # Read the file content as string
        content = file_buffer.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        # Split into lines and get first 10
        lines = content.split('\n')[:10]
        
        # Reset buffer position for later use
        file_buffer.seek(0)
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()
                
        # Parse specific fields
        if 'Sample Period' in metadata:
            # Strip trailing commas from the value
            sample_period_str = metadata['Sample Period'].rstrip(',')
            metadata['sample_period_ms'] = int(sample_period_str)
            metadata['sample_period_s'] = metadata['sample_period_ms'] / 1000.0
            
        if 'Created' in metadata:
            try:
                metadata['created_datetime'] = datetime.strptime(
                    metadata['Created'], 
                    '%Y-%m-%d %H:%M:%S'
                )
            except:
                metadata['created_datetime'] = None
                
        return metadata
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and validate the data."""
        # Ensure numeric columns are float
        numeric_columns = ['Timestamp', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8',
                          'VirtualCoreTemperature', 'VirtualSurfaceTemperature', 
                          'VirtualAmbientTemperature', 'EstimatedCoreTemperature']
        
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Add time in minutes
        df['TimeMinutes'] = df['Timestamp'] / 60.0
        
        # Note: Sensor identification is now done per-curve in _extract_all_baking_curves
        # This ensures each curve gets its own sensor assignments
        
        # However, we need basic temperature columns for curve extraction
        # These will be overwritten with proper sensor identification per curve
        if 'CoreTemperature' not in df.columns:
            try:
                df['CoreTemperature'] = resolve_core_temperature_series(df)
            except KeyError:
                if 'T1' in df.columns:
                    df['CoreTemperature'] = df['T1']
        
        return df
    
    def _validate_and_fix_sensor_assignments(self, core_sensors: List[str], 
                                               surface_sensors: List[str], 
                                               ambient_sensors: List[str]) -> Tuple[List[str], List[str], List[str]]:
        """Validate and fix sensor assignments to ensure they follow probe physics.
        
        Returns:
            Tuple of (core_sensors, surface_sensors, ambient_sensors) after validation
        """
        # Convert to sensor numbers for easier processing
        def to_nums(sensors):
            return sorted([int(s[1]) for s in sensors if s.startswith('T')])
        
        def to_sensors(nums):
            return [f'T{n}' for n in nums]
        
        core_nums = to_nums(core_sensors)
        surface_nums = to_nums(surface_sensors)
        ambient_nums = to_nums(ambient_sensors)
        
        # Fix overlaps - surface gets priority as it's the interface
        if surface_nums:
            surface_num = surface_nums[0]  # Should only be one
            core_nums = [n for n in core_nums if n < surface_num]
            ambient_nums = [n for n in ambient_nums if n > surface_num]
        
        # Ensure consecutive sensors
        if core_nums:
            min_core = min(core_nums)
            max_core = max(core_nums)
            core_nums = list(range(min_core, max_core + 1))
        
        if ambient_nums:
            min_ambient = min(ambient_nums)
            max_ambient = max(ambient_nums)
            ambient_nums = list(range(min_ambient, max_ambient + 1))
        
        # If no surface sensor but we have core and ambient, place surface between them
        if not surface_nums and core_nums and ambient_nums:
            max_core = max(core_nums)
            min_ambient = min(ambient_nums)
            if max_core + 1 < min_ambient:
                surface_nums = [max_core + 1]
        
        # Ensure surface is single sensor
        if len(surface_nums) > 1:
            # Take the sensor closest to ambient
            surface_nums = [max(surface_nums)]
        
        return (to_sensors(core_nums), 
                to_sensors(surface_nums), 
                to_sensors(ambient_nums))
    
    def _identify_sensor_roles_for_curve(self, df: pd.DataFrame, curve_index: int) -> pd.DataFrame:
        """Identify per-role sensors for ``df`` via the spatial reconstructor.

        After M3a HMS Royal Sovereign this is a single call to
        :func:`src.data.spatial_reconstruction.classify`; the legacy
        firmware-mode-pick + physics-correction layering is gone. The
        classifier IS the source of truth.
        """
        sample_period_ms = self.metadata.get('sample_period_ms', 5000)
        probe_geometry = lookup_geometry(
            probe_sn=self.metadata.get('Probe S/N'),
            probe_model=self.metadata.get('Probe HW revision'),
        )
        try:
            assignment = classify(
                df,
                sample_period_ms=sample_period_ms,
                probe_geometry=probe_geometry,
            )
            self.curve_sensor_assignments[curve_index] = (
                self._spatial_assignment_to_dict(assignment)
            )
        except Exception as exc:
            # Defensive: never crash curve extraction on a classifier failure.
            _log.warning(
                "Curve %d: spatial classifier failed (%s); using degraded "
                "fallback assignments.", curve_index + 1, exc,
            )
            self.curve_sensor_assignments[curve_index] = {
                'core': None,
                'surface': None,
                'ambient': [],
                'lid': None,
                'firmware_diagnostic': None,
                'core_position_normalised': None,
                'surface_position_normalised': None,
                'ambient_position_normalised': [],
                'lid_position_normalised': None,
                'model_used': 'piecewise',
                'assignment': None,
            }
        # Backward-compat alias for the deprecated single-curve view.
        self.sensor_assignments = self.curve_sensor_assignments[curve_index]

        # Backward-compat averages stay for legacy consumers (e.g. plots
        # that pre-date the standardised columns).
        if all(col in df.columns for col in ['T1', 'T2', 'T3', 'T4']):
            df['CoreAverage'] = df[['T1', 'T2', 'T3', 'T4']].mean(axis=1)
        if all(col in df.columns for col in ['T7', 'T8']):
            df['SurfaceAverage'] = df[['T7', 'T8']].mean(axis=1)

        # Drive the standardised columns from the new assignment.
        self._apply_standard_columns(df, curve_index)
        return df

    def _spatial_assignment_to_dict(self, assignment) -> dict:
        """Flatten a :class:`SpatialAssignment` into the curve-assignment dict
        shape consumed by ``curve_sensor_assignments[curve_index]``.

        Keys (M3a contract):
        * ``core``: nearest sensor for the core role (str or None).
        * ``surface``: nearest sensor for the surface role (str or None).
        * ``ambient``: list of nearest sensors for the ambient role.
        * ``lid``: nearest sensor for lid role (str or None).
        * ``firmware_diagnostic``: dict of firmware mode picks (diagnostic only).
        * ``*_position_normalised``: inferred per-role positions in [0, 1] for
          downstream visualisation.
        * ``model_used``: name of the spatial model used.
        * ``assignment``: the full SpatialAssignment object (for getters).
        """
        return {
            'core': assignment.core,
            'surface': assignment.surface,
            'ambient': list(assignment.ambient),
            'lid': assignment.lid,
            'firmware_diagnostic': assignment.firmware_diagnostic,
            'core_position_normalised': (
                assignment.core_assignment.position_normalised
                if assignment.core_assignment is not None
                else None
            ),
            'surface_position_normalised': (
                assignment.surface_assignment.position_normalised
                if assignment.surface_assignment is not None
                else None
            ),
            'ambient_position_normalised': [
                p.position_normalised for p in assignment.ambient_assignments
            ],
            'lid_position_normalised': (
                assignment.lid_assignment.position_normalised
                if assignment.lid_assignment is not None
                else None
            ),
            'model_used': assignment.model_used,
            'assignment': assignment,
        }

    def get_sensor_assignments(self) -> dict:
        """
        Get the sensor role assignments for the current curve.
        
        Returns:
            dict: Dictionary with 'core', 'surface', 'ambient' keys containing sensor identifiers
        """
        # Return assignments for current curve
        if hasattr(self, 'curve_sensor_assignments') and self.current_curve_index in self.curve_sensor_assignments:
            return self.curve_sensor_assignments[self.current_curve_index]
        # Fallback to deprecated sensor_assignments
        return getattr(self, 'sensor_assignments', {})
    
    def set_expected_durations(
        self, durations_s: list[float | None] | None
    ) -> None:
        """Set the per-curve expected-duration hint and re-run detection.

        Introduced by flotilla mission M5 HMS Dauntless.  Mirrors the
        cache-invalidation semantics of :meth:`set_sensor_override`: when
        cached data is present, running this method triggers a fresh
        ``_extract_all_baking_curves`` pass so analytics downstream see
        the refined curves.

        Args:
            durations_s: ``None`` clears the hint.  A list of seconds (or
                ``None`` entries for per-curve skips, e.g. truncated
                bakes) is matched positionally to detected curves.
        """
        self.expected_durations_s = durations_s
        # Re-run detection on the full raw log, NOT on self.data which
        # has been overwritten with the first curve's slice (M1 HMS
        # Ardent fixed this latent bug — pre-fix, multi-bake CSVs lost
        # bakes 2+ on every set_expected_durations call).
        source = self.raw_data if self.raw_data is not None else self.data
        if source is not None and len(source) > 0:
            self.all_curves = self._extract_all_baking_curves(source.copy())
            if self.all_curves:
                # Preserve current_curve_index when valid; otherwise reset.
                if self.current_curve_index >= len(self.all_curves):
                    self.current_curve_index = 0
            # Curve list re-detected — drop stale isothermal assignments.
            self._invalidate_isothermal_cache()

    def set_curve_boundaries(
        self, curve_index: int, start_idx: int, end_idx: int
    ) -> None:
        """Pin curve ``curve_index`` to ``[start_idx, end_idx]`` in the
        raw-log index space, regardless of detector decision or hint.

        Introduced by flotilla mission M1 HMS Ardent (branch
        ``refactor/curve-boundary-review``).  Used by the Curve Boundary
        Review tab (M3) so the operator can pin a boundary when the
        detector + hint can't reach the desired window.

        Validation:
        - ``curve_index`` must be a current detected-curve index.
        - ``start_idx`` and ``end_idx`` must lie inside ``raw_data``.
        - ``start_idx < end_idx``.

        Re-applies overrides via a fresh re-detection so all derived
        fields (``samples``, ``duration``, ``max_temp``, etc.) reflect
        the pinned slice.  ``exit_candidate_kind`` becomes
        ``"manual_override"`` for the pinned curve.
        """
        if not self.all_curves or curve_index < 0 or curve_index >= len(self.all_curves):
            raise IndexError(
                f"curve_index {curve_index} outside detected range "
                f"[0, {len(self.all_curves) - 1}]"
            )
        n = len(self.raw_data) if self.raw_data is not None else 0
        if not (0 <= start_idx < n) or not (0 <= end_idx < n):
            raise ValueError(
                f"start_idx={start_idx} and end_idx={end_idx} must lie in "
                f"[0, {n - 1}]"
            )
        if start_idx >= end_idx:
            raise ValueError(
                f"start_idx={start_idx} must be less than end_idx={end_idx}"
            )

        # M11 HMS Endeavour: dispatch by curve type.
        target = self.all_curves[curve_index]
        added_idx = target.get("_user_added_idx")
        if added_idx is not None and 0 <= added_idx < len(self._added_curves):
            # User-added curve — update its entry in ``_added_curves``
            # so the same curve (identified by its position in that
            # list) gets re-refined with the new range on next extract.
            self._added_curves[added_idx] = (int(start_idx), int(end_idx))
        else:
            # Detector curve — translate the all_curves position back
            # to the detector position (the position before any
            # user-added curves were appended) so the override key
            # stays stable as user-added curves come and go.
            detector_pos = sum(
                1
                for c in self.all_curves[: curve_index + 1]
                if c.get("_user_added_idx") is None
            ) - 1
            self._boundary_overrides[detector_pos] = (
                int(start_idx),
                int(end_idx),
            )
        self._reapply_boundary_state()

    def clear_curve_boundaries(self, curve_index: int) -> None:
        """Remove the manual override for ``curve_index`` (no-op if absent)."""
        if curve_index in self._boundary_overrides:
            del self._boundary_overrides[curve_index]
            self._reapply_boundary_state()

    def _reapply_boundary_state(self) -> None:
        """Re-run detection on raw_data and apply manual overrides on top."""
        if self.raw_data is None or len(self.raw_data) == 0:
            return
        self.all_curves = self._extract_all_baking_curves(self.raw_data.copy())
        if self.all_curves and self.current_curve_index >= len(self.all_curves):
            self.current_curve_index = 0
        # Curve list re-indexed — every cached isothermal assignment is stale.
        self._invalidate_isothermal_cache()

    def set_sensor_override(self, curve_index: int, role: str, sensor):
        """Allow user to override sensor assignments for a specific curve.

        Args:
            curve_index: Index of the curve
            role: ``'core'``, ``'surface'``, ``'ambient'``, or ``'lid'``
            sensor:
                - For ``'core'`` and ``'surface'``: a single sensor name (str), e.g. ``'T2'``.
                - For ``'ambient'``: a list of sensor names (or a single str for
                  backward compatibility); the AmbientTemperature column will be
                  the row-wise mean across these sensors.
                - For ``'lid'``: a single sensor name (str), or ``None`` to
                  explicitly clear a previously-set lid override (drops the
                  ``LidTemperature`` column).

        Raises:
            ValueError: if the resulting role-to-sensor mapping violates the
                physical topology of the probe (see
                :meth:`_validate_override_topology`).
        """
        if role not in ('core', 'surface', 'ambient', 'lid'):
            raise ValueError(
                f"Unknown override role {role!r}; expected one of "
                "'core', 'surface', 'ambient', 'lid'."
            )

        # Build the prospective override dict and topology-check before mutating.
        existing = self._sensor_overrides.get(curve_index, {})
        prospective = dict(existing)
        prospective[role] = sensor
        self._validate_override_topology(prospective)

        # Topology OK — commit the mutation.
        if curve_index not in self._sensor_overrides:
            self._sensor_overrides[curve_index] = {}
        self._sensor_overrides[curve_index][role] = sensor

        # Regenerate standard columns for this curve if it's the current one,
        # AND for the per-curve DataFrame in all_curves so LidTemperature is
        # written/dropped consistently.
        df_curve = self._curve_dataframe(curve_index)
        if df_curve is not None:
            self._apply_standard_columns(df_curve, curve_index)
        if curve_index == self.current_curve_index:
            self._regenerate_standard_columns()
        # The override changes the classifier's core/surface picks, so any
        # cached isothermal assignment for this curve is stale.
        self._invalidate_isothermal_cache(curve_index)

    @staticmethod
    def _sensor_index(name) -> Optional[int]:
        """Return the int index for ``'T<n>'`` sensor names, else ``None``."""
        if not isinstance(name, str) or len(name) < 2 or name[0] != 'T':
            return None
        try:
            return int(name[1:])
        except ValueError:
            return None

    @classmethod
    def _validate_override_topology(cls, overrides: Dict) -> None:
        """Enforce probe topology on a prospective override dict.

        Topology rule (numbers refer to the integer suffix of T1..T8):

            core_idx < surface_idx <= min(ambient_idx) <=
            max(ambient_idx) <= lid_idx

        Constraints involving roles NOT present in ``overrides`` are skipped
        (partial overrides are valid mid-edit).

        **Through-loaf exception**: when the operator inserts the probe so it
        passes through the loaf and emerges out the far side, ambient sensors
        appear on BOTH ends of the probe (e.g. T1 in oven air below, T8 in oven
        air above) and the surface sensor sits between them.  We accept this
        when:

          * ambient sensor indices form two non-empty contiguous groups
            (lower group is a prefix starting at T1, upper group is a suffix
            ending at the highest used T-index, no ambient indices between
            them); and
          * surface_idx lies strictly between max(lower group) and min(upper group).

        Raises ``ValueError`` with a role-named message on the first
        violation found.
        """
        # Filter to recognised roles whose value translates to at least one
        # sensor name. ``lid=None`` is the explicit-clear sentinel and skips
        # validation of the lid relation.
        core = overrides.get('core')
        surface = overrides.get('surface')
        ambient_raw = overrides.get('ambient')
        lid = overrides.get('lid')

        core_idx = cls._sensor_index(core) if core else None
        surface_idx = cls._sensor_index(surface) if surface else None
        if isinstance(ambient_raw, str):
            ambient_list = [ambient_raw]
        elif ambient_raw is None:
            ambient_list = []
        else:
            ambient_list = list(ambient_raw)
        ambient_idxs = sorted(
            i for i in (cls._sensor_index(s) for s in ambient_list) if i is not None
        )
        lid_idx = cls._sensor_index(lid) if lid else None

        # Core vs Surface
        if core_idx is not None and surface_idx is not None:
            if core_idx == surface_idx:
                raise ValueError(
                    "Override topology: core and surface sensors must differ "
                    f"(both set to T{core_idx})."
                )
            if core_idx >= surface_idx:
                raise ValueError(
                    "Override topology: core sensor must be deeper "
                    f"(lower index) than surface sensor "
                    f"(got core=T{core_idx}, surface=T{surface_idx})."
                )

        # Ambient vs Surface (with through-loaf exception)
        if surface_idx is not None and ambient_idxs:
            min_amb = ambient_idxs[0]
            max_amb = ambient_idxs[-1]
            if min_amb < surface_idx:
                # Possible through-loaf: lower group must be a contiguous prefix
                # starting at T1, upper group must be a contiguous suffix; the
                # surface index sits strictly between the two groups.
                lower = [i for i in ambient_idxs if i < surface_idx]
                upper = [i for i in ambient_idxs if i > surface_idx]
                # surface itself is never in ambient — earlier core/surface
                # check already forbids overlap with core; ambient overlapping
                # surface should also fail:
                if surface_idx in ambient_idxs:
                    raise ValueError(
                        "Override topology: ambient list may not include the "
                        f"surface sensor (T{surface_idx})."
                    )
                lower_is_prefix = (
                    bool(lower)
                    and lower[0] == 1
                    and lower == list(range(lower[0], lower[-1] + 1))
                )
                upper_is_contiguous = (
                    bool(upper)
                    and upper == list(range(upper[0], upper[-1] + 1))
                )
                if not (lower_is_prefix and upper_is_contiguous):
                    raise ValueError(
                        "Override topology: ambient sensors must lie at or above "
                        f"the surface sensor (got ambient={ambient_list}, "
                        f"surface=T{surface_idx}). Through-loaf exception "
                        "requires the lower group to start at T1 and the upper "
                        "group to be contiguous on the far side."
                    )
                # Through-loaf accepted.

        # Lid vs Ambient
        if lid_idx is not None and ambient_idxs:
            if lid_idx < ambient_idxs[-1]:
                raise ValueError(
                    "Override topology: lid sensor index must be >= max(ambient) "
                    f"(got lid=T{lid_idx}, max ambient=T{ambient_idxs[-1]})."
                )

        # Lid vs Surface (when no ambient override is present)
        if lid_idx is not None and surface_idx is not None and not ambient_idxs:
            if lid_idx <= surface_idx:
                raise ValueError(
                    "Override topology: lid sensor must be above the surface "
                    f"(got lid=T{lid_idx}, surface=T{surface_idx})."
                )

    def clear_sensor_overrides(self, curve_index: int):
        """Clear all user overrides for a curve, reverting to automatic detection."""
        if curve_index in self._sensor_overrides:
            del self._sensor_overrides[curve_index]

        # Regenerate columns if this is the current curve
        df_curve = self._curve_dataframe(curve_index)
        if df_curve is not None:
            self._apply_standard_columns(df_curve, curve_index)
        if curve_index == self.current_curve_index:
            self._regenerate_standard_columns()
        self._invalidate_isothermal_cache(curve_index)

    # ------------------------------------------------------------------
    # M18 HMS Vigilant — Method 4: bake metadata + geometric core
    # ------------------------------------------------------------------
    # Probe geometry: T1-T8 span 95 mm; spacing 13.571 mm; T1 at probe tip.
    PROBE_SPAN_MM: float = 95.0
    SENSOR_SPACING_MM: float = 95.0 / 7.0  # ≈ 13.571 mm

    def set_bake_metadata(self, curve_index: int, metadata: dict) -> None:
        """Store partial or full bake metadata for ``curve_index``.

        Recognised keys (all optional):
          - ``loaf_thickness_mm``: float — total loaf height (tin bottom to top crust).
          - ``insertion_depth_mm``: float — probe tip below loaf top surface.
          - ``oven_setpoint_C``: float — oven setpoint.
          - ``lid_state``: ``'unknown' | 'open' | 'lidded' | 'tin'``.
          - ``steam_phase_minutes``: float — steam phase duration.

        When both ``loaf_thickness_mm`` and ``insertion_depth_mm`` are
        provided, :meth:`get_geometric_core_position_mm_from_tip` returns
        the geometric core position relative to the probe tip and
        :meth:`get_core_temperature_series` uses spatial interpolation
        between the bracketing T-sensors at that position.
        """
        self._bake_metadata[curve_index] = dict(metadata)

    def clear_bake_metadata(self, curve_index: int) -> None:
        """Drop all stored bake metadata for ``curve_index`` (no-op if absent)."""
        self._bake_metadata.pop(curve_index, None)

    def get_bake_metadata(self, curve_index: Optional[int] = None) -> dict:
        """Return a *copy* of the stored bake metadata for ``curve_index``.

        Defaults to the current curve. Returns ``{}`` when no metadata has
        been set for the curve.
        """
        if curve_index is None:
            curve_index = self.current_curve_index
        return dict(self._bake_metadata.get(curve_index, {}))

    def get_geometric_core_position_mm_from_tip(
        self, curve_index: Optional[int] = None
    ) -> Optional[float]:
        """Return the geometric core position relative to the probe tip.

        Formula::

            geometric_core_depth_below_top = loaf_thickness_mm / 2
            pos_mm_above_tip = insertion_depth_mm - geometric_core_depth_below_top

        Sign convention (matches :meth:`_geometric_core_series` and the
        sidebar status display — positive = interpolation, negative =
        degraded extrapolation):
          - **Positive** ⇒ the geometric core sits *above* the probe tip,
            i.e. between T1 (tip) and T8 (stem) along the probe — interpolation
            between adjacent T-sensors yields a high-accuracy core series.
            At ``pos_mm = 0`` the core lands exactly on T1; at ``pos_mm = 95``
            it lands on T8.
          - **Negative** ⇒ the geometric core is *past/below* the probe tip
            (the probe is too shallow; the true core is deeper into the loaf
            than T1 reaches) — extrapolation territory for thermal-only
            methods (the structural ~5.7 °C floor confirmed across the M21
            inverse-problem flotilla). The series degrades to T1 in this case.

        Returns ``None`` when either of the required metadata fields is
        missing (the classifier's Method 1 fallback engages instead).
        """
        meta = self.get_bake_metadata(curve_index)
        L = meta.get("loaf_thickness_mm")
        D = meta.get("insertion_depth_mm")
        if L is None or D is None:
            return None
        return float(D) - float(L) / 2.0

    def _geometric_core_series(
        self, curve_index: int
    ) -> Optional[pd.Series]:
        """Build the per-timestep core series at the geometric core position.

        Returns ``None`` when bake metadata is incomplete or the per-curve
        DataFrame does not carry the bracketing T-sensor columns.

        Coordinate convention (M18 HMS Vigilant):
          - The probe is inserted top-down: T1 sits at the probe TIP (the
            deepest point in the loaf), T8 sits at the probe STEM end
            (closest to the loaf top surface). Adjacent sensors are spaced
            by ``SENSOR_SPACING_MM`` ≈ 13.571 mm; the full span is 95 mm.
          - ``insertion_depth_mm`` = how far below the loaf top the probe
            tip (T1) sits.
          - ``geometric_core_depth_below_top`` = ``loaf_thickness_mm / 2``
            (the loaf's central plane).
          - ``pos_mm = insertion_depth_mm - core_depth_below_top``:
              * ``pos_mm > 0`` ⇒ the core sits ABOVE the probe tip
                (between T1 and T8 along the probe stem). At ``pos_mm = 0``
                the core lands exactly on T1; at ``pos_mm = 95`` it lands
                exactly on T8.
              * ``pos_mm < 0`` ⇒ the core sits BELOW the probe tip
                (probe is too shallow; geometric core is in the loaf
                BELOW T1 with no in-dough sensor coverage). We hold T1's
                series in this degraded case — Method 1's relaxed
                parabolic clamp is not invoked here because the user
                supplied a hard geometric measurement; the position
                ``pos_mm`` is reported (negative) but the temperature
                series degrades to T1.
        """
        pos_mm = self.get_geometric_core_position_mm_from_tip(curve_index)
        if pos_mm is None:
            return None
        df = self._curve_dataframe(curve_index)
        if df is None:
            return None
        # Past-the-tip degenerate case (pos_mm < 0): hold T1's series.
        if pos_mm < 0.0:
            if "T1" in df.columns:
                return df["T1"].reset_index(drop=True)
            return None
        # Clamp to probe span so the bracketing sensors stay inside [T1, T8].
        offset_from_t1 = float(pos_mm)
        if offset_from_t1 > self.PROBE_SPAN_MM:
            offset_from_t1 = self.PROBE_SPAN_MM
        # Bracketing sensor indices (1-based: T1..T8). ``idx_lower`` is the
        # 0-based offset of the lower-T-numbered sensor in the bracket; e.g.
        # ``idx_lower=0`` → bracket is (T1, T2).
        idx_lower = int(offset_from_t1 // self.SENSOR_SPACING_MM)
        if idx_lower >= 7:
            idx_lower = 6
        sensor_lo = f"T{idx_lower + 1}"
        sensor_hi = f"T{idx_lower + 2}"
        if sensor_lo not in df.columns or sensor_hi not in df.columns:
            return None
        frac = (offset_from_t1 - idx_lower * self.SENSOR_SPACING_MM) / self.SENSOR_SPACING_MM
        if frac < 0.0:
            frac = 0.0
        elif frac > 1.0:
            frac = 1.0
        series = (1.0 - frac) * df[sensor_lo] + frac * df[sensor_hi]
        return series.reset_index(drop=True)

    # ------------------------------------------------------------------
    # M30 Spatial Evolution — memoised isothermal-front assignment
    # ------------------------------------------------------------------
    def isothermal_assignment(self, curve_index: Optional[int] = None):
        """Return the memoised :class:`IsothermalAssignment` for a curve.

        Wraps :func:`src.data.spatial_reconstruction.track_isothermal`, which
        traces the 60/80/100/110 °C isotherm positions through the dough over
        time (the 100 °C front is the latent-heat / Stefan moisture-front
        proxy). The result is cached per ``curve_index`` because
        ``track_isothermal`` runs the full-bake classifier once (~1-2 s on a
        single bake) and the UI re-renders on every unrelated widget change.

        The cache is invalidated by the sensor-override mutators
        (:meth:`set_sensor_override`, :meth:`clear_sensor_overrides`) for the
        affected curve, and cleared wholesale by the boundary / manual-curve
        mutators (:meth:`set_curve_boundaries`, :meth:`clear_curve_boundaries`,
        :meth:`add_manual_curve`, :meth:`remove_manual_curve`) because those
        re-index the curve list.

        Returns ``None`` when the curve has no DataFrame.
        """
        if curve_index is None:
            curve_index = self.current_curve_index
        cache = self._isothermal_cache
        if curve_index in cache:
            return cache[curve_index]
        df = self._curve_dataframe(curve_index)
        if df is None:
            return None
        # Local import keeps the spatial_reconstruction package off the
        # loader's import-time critical path (and avoids any import cycle).
        from src.data.spatial_reconstruction import track_isothermal

        sample_period_ms = 5000
        if isinstance(self.metadata, dict):
            sample_period_ms = int(self.metadata.get("sample_period_ms", 5000))
        result = track_isothermal(df, sample_period_ms=sample_period_ms)
        cache[curve_index] = result
        return result

    def _invalidate_isothermal_cache(self, curve_index: Optional[int] = None) -> None:
        """Drop cached isothermal assignments.

        ``curve_index=None`` clears the whole cache (used when the curve list
        is re-indexed); otherwise only the named curve's entry is dropped.
        """
        if curve_index is None:
            self._isothermal_cache.clear()
        else:
            self._isothermal_cache.pop(curve_index, None)

    def get_core_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as core (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # Check for user override first
        if curve_index in self._sensor_overrides and 'core' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['core']
            
        # Otherwise return automatic detection
        return self._get_automatic_core_sensors(curve_index)
    
    def get_surface_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as surface (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # Check for user override first
        if curve_index in self._sensor_overrides and 'surface' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['surface']
            
        # Otherwise return automatic detection
        return self._get_automatic_surface_sensors(curve_index)
    
    def get_ambient_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as ambient (with override support).

        After M3a HMS Royal Sovereign the canonical source is
        ``assignment.ambient_assignments`` from the spatial classifier.
        Manual ambient overrides win; if a surface-only override is in place
        (no explicit ambient override), we pass through the classifier's
        ambient list — geometry topology is the classifier's job.
        """
        if curve_index is None:
            curve_index = self.current_curve_index

        # Manual ambient override (single sensor or list).
        overrides = self._sensor_overrides.get(curve_index, {})
        ambient_override = overrides.get('ambient')
        if ambient_override:
            if isinstance(ambient_override, str):
                return [ambient_override]
            return list(ambient_override)

        # Classifier source of truth.
        return self._get_automatic_ambient_sensors(curve_index)
    
    def get_core_sensor(self, curve_index: Optional[int] = None) -> Optional[str]:
        """Get the single core sensor (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # Check for user override first
        if curve_index in self._sensor_overrides and 'core' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['core']
            
        # Otherwise return primary sensor from automatic detection
        auto_sensors = self._get_automatic_core_sensors(curve_index)
        return auto_sensors[0] if auto_sensors else None
    
    def get_surface_sensor(self, curve_index: Optional[int] = None) -> Optional[str]:
        """Get the single surface sensor (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # Check for user override first
        if curve_index in self._sensor_overrides and 'surface' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['surface']
            
        # Otherwise return primary sensor from automatic detection
        auto_sensors = self._get_automatic_surface_sensors(curve_index)
        return auto_sensors[0] if auto_sensors else None
    
    def get_internal_sensors(self, curve_index: Optional[int] = None, data: Optional[pd.DataFrame] = None) -> List[str]:
        """
        Get all sensors below the surface sensor that represent internal crumb temperature.
        
        Sensors are filtered based on maximum temperature to exclude those that are
        likely in the crust (>100°C + margin).
        
        Args:
            curve_index: Which curve to analyze (default: current curve)
            data: Optional data frame to use for temperature analysis. If not provided,
                  uses the current curve data from self.data
                  
        Returns:
            List of sensor names that represent internal crumb
        """
        surface_sensor = self.get_surface_sensor(curve_index)
        if not surface_sensor or len(surface_sensor) < 2:
            return []
            
        surface_num = int(surface_sensor[1])
        
        # Step 1: Get all sensors below surface (current logic)
        candidate_sensors = []
        for i in range(1, surface_num):
            sensor = f'T{i}'
            if sensor in self.data.columns:
                candidate_sensors.append(sensor)
        
        # If no data provided for filtering, return all candidates (backward compatibility)
        if data is None:
            # Try to get data for the current curve
            if hasattr(self, 'all_curves') and 0 <= (curve_index or self.current_curve_index) < len(self.all_curves):
                data = self.all_curves[curve_index or self.current_curve_index]['data']
            else:
                # No data available for temperature filtering, return all candidates
                return candidate_sensors
        
        # Step 2: Filter by temperature criteria
        internal_sensors = []
        temp_threshold = INTERNAL_SENSOR_CONFIG['TEMP_THRESHOLD']
        use_time_filter = INTERNAL_SENSOR_CONFIG['USE_TIME_BASED_FILTERING']
        time_threshold = INTERNAL_SENSOR_CONFIG['TIME_THRESHOLD']
        
        for sensor in candidate_sensors:
            if sensor not in data.columns:
                continue
                
            sensor_data = data[sensor]
            max_temp = sensor_data.max()
            
            # Check maximum temperature criterion
            if max_temp <= temp_threshold:
                internal_sensors.append(sensor)
            elif use_time_filter:
                # Additional time-based criterion
                time_above_100 = (sensor_data > 100).sum() / len(sensor_data)
                if time_above_100 <= time_threshold:
                    internal_sensors.append(sensor)
        
        # Step 3: Ensure core sensor is always included
        if INTERNAL_SENSOR_CONFIG['ALWAYS_INCLUDE_CORE']:
            core_sensor = self.get_core_sensor(curve_index)
            if core_sensor and core_sensor not in internal_sensors and core_sensor in candidate_sensors:
                internal_sensors.append(core_sensor)
                # Sort to maintain order
                internal_sensors.sort(key=lambda s: int(s[1]))
        
        return internal_sensors
    
    def get_core_column(self, curve_index: Optional[int] = None) -> str:
        """Get the column name to use for core temperature analysis."""
        # Always use standardized column name
        return 'CoreTemperature'
    
    def get_surface_column(self, curve_index: Optional[int] = None) -> str:
        """Get the column name to use for surface temperature analysis."""
        # Always use standardized column name
        return 'SurfaceTemperature'
    
    def get_ambient_column(self, curve_index: Optional[int] = None) -> Optional[str]:
        """Get the column name to use for ambient temperature analysis."""
        # Check if we have ambient sensors
        ambient_sensors = self.get_ambient_sensors(curve_index)
        if ambient_sensors:
            return 'AmbientTemperature'
        return None

    def get_lid_sensor(self, curve_index: Optional[int] = None) -> Optional[str]:
        """Return the nearest sensor for the lid role.

        Manual override (``_sensor_overrides[curve_index]['lid']``) wins; else
        the classifier's ``assignment.lid`` is returned; else ``None``.
        Introduced by M3a HMS Royal Sovereign.
        """
        if curve_index is None:
            curve_index = self.current_curve_index
        overrides = self._sensor_overrides.get(curve_index, {})
        if 'lid' in overrides:
            return overrides['lid']
        return self.curve_sensor_assignments.get(curve_index, {}).get('lid')

    def _resolve_core(
        self,
        curve_index: int,
        df: Optional[pd.DataFrame],
    ) -> tuple:
        """Resolve the active core series AND which method produced it.

        Single source of truth for the override → Method 4 → classifier
        layering *decision*, shared by :meth:`_resolve_core_series` (which
        wants the series), :meth:`get_core_confidence` (which wants the
        confidence), and ``src.ui.core_confidence_banner._bake_metadata_status_line``
        (which wants the active-model label). Keeping the decision in one
        place means the trace, the banner, and the sidebar status can never
        disagree about which model is feeding the core curve.

        Returns ``(series, method_tag)`` where ``series`` is
        ``reset_index(drop=True)`` (or ``None`` when no layer produces one)
        and ``method_tag`` is one of:

          * ``"override"``         — manual sensor override on the core role.
          * ``"method4"``          — geometric core in-probe (``pos_mm >= 0``;
            spatial interpolation between the bracketing T-sensors).
          * ``"method4_degraded"`` — geometric core past/below the probe tip
            (``pos_mm < 0``; the series is held at T1, lower accuracy).
          * ``"classifier"``       — Method 1 classifier assignment.
          * ``"fallback"``         — no layer produced a series (``None``).
        """
        overrides = self._sensor_overrides.get(curve_index, {})
        if 'core' in overrides and df is not None:
            sensor = overrides['core']
            if sensor in df.columns:
                return df[sensor].reset_index(drop=True), "override"
        # Method 4 — geometric core from bake metadata.
        geom_series = self._geometric_core_series(curve_index)
        if geom_series is not None:
            pos_mm = self.get_geometric_core_position_mm_from_tip(curve_index)
            tag = "method4_degraded" if (pos_mm is not None and pos_mm < 0.0) else "method4"
            return geom_series, tag
        assignment = self.curve_sensor_assignments.get(curve_index, {}).get(
            'assignment'
        )
        if assignment is not None and assignment.core_assignment is not None:
            return assignment.core_assignment.temperature_series.reset_index(
                drop=True
            ), "classifier"
        return None, "fallback"

    def _resolve_core_series(
        self,
        curve_index: int,
        df: Optional[pd.DataFrame],
    ) -> Optional[pd.Series]:
        """Apply the override → Method 4 → classifier core-series layering.

        Thin wrapper over :meth:`_resolve_core` that discards the method tag.
        Shared by :meth:`get_core_temperature_series` (the public reader) and
        :meth:`_apply_standard_columns` (the canonical writer that produces
        ``df['CoreTemperature']``). The two paths previously disagreed when
        bake metadata was set — the reader honoured Method 4, the writer
        ignored it — so every Streamlit tab and analyser reading the column
        saw stale Method 1 output. M26 HMS Bellerophon consolidated the
        decision; M29 lifts it into :meth:`_resolve_core` so the confidence
        and sidebar surfaces reuse the same branch order.

        Returns the series with ``reset_index(drop=True)`` so callers can
        rely on positional alignment with ``df``. Returns ``None`` when
        none of the three layers produces a result; the caller is then
        responsible for any legacy fallback (the reader returns
        ``df['CoreTemperature']`` if present; the writer invokes
        :func:`resolve_core_temperature_series`).
        """
        series, _ = self._resolve_core(curve_index, df)
        return series

    def get_core_temperature_series(
        self, curve_index: Optional[int] = None
    ) -> Optional[pd.Series]:
        """Return the interpolated core-temperature series.

        Layering (M18 HMS Vigilant; consolidated by M26 HMS Bellerophon):
          1. **Manual sensor override** wins (``_sensor_overrides[i]['core']``).
          2. **Bake metadata (Method 4)** — when ``loaf_thickness_mm`` AND
             ``insertion_depth_mm`` are both set, the geometric core position
             determines the spatial interpolation point and a per-timestep
             series is built by linear interpolation between the bracketing
             T-sensors.
          3. **Classifier (Method 1)** — relaxed parabolic clamp; returns
             ``assignment.core_assignment.temperature_series``.
          4. **Final fallback** — the standardised ``CoreTemperature`` column.

        Layers 1-3 delegate to :meth:`_resolve_core_series`; the legacy
        ``df['CoreTemperature']`` final fallback remains here so the public
        API behaviour is byte-identical to the pre-M26 reader.
        """
        if curve_index is None:
            curve_index = self.current_curve_index
        df = self._curve_dataframe(curve_index)
        series = self._resolve_core_series(curve_index, df)
        if series is not None:
            return series
        # Final fallback: use whatever CoreTemperature is set to.
        if df is not None and 'CoreTemperature' in df.columns:
            return df['CoreTemperature'].reset_index(drop=True)
        return None

    def get_core_confidence(
        self, curve_index: Optional[int] = None
    ) -> tuple:
        """Return ``(confidence, reason)`` for the core-temperature series.

        ``confidence`` is one of ``"high"`` / ``"medium"`` / ``"low"`` and
        drives the banner colour; ``reason`` is the human-readable
        justification (banner copy / tooltip). The layering mirrors
        :meth:`get_core_temperature_series` exactly — both read the active
        method from :meth:`_resolve_core`:

          1. **Manual override** → ``("high", "manual override: core = T{n}")``.
          2. **Bake metadata (Method 4), core in-probe** (``pos_mm >= 0``) →
             ``("high", "geometric core at {pos_mm:.1f} mm from tip via bake metadata")``.
             **Method 4 trumps Method 1's confidence** here: a deterministic
             operator-supplied geometry is high-confidence even when the
             classifier extrapolated and reported ``"low"``.
          3. **Bake metadata (Method 4), core past tip** (``pos_mm < 0``) →
             ``("low", "geometric core sits below probe tip; series degraded to T1")``.
          4. **Classifier (Method 1)** →
             ``(core_assignment.confidence, core_assignment.reason)``.
          5. **Final fallback** →
             ``("low", "no classifier assignment; using legacy CoreTemperature column")``.
        """
        if curve_index is None:
            curve_index = self.current_curve_index
        df = self._curve_dataframe(curve_index)
        _, tag = self._resolve_core(curve_index, df)

        if tag == "override":
            sensor = self._sensor_overrides.get(curve_index, {}).get('core')
            return "high", f"manual override: core = {sensor}"
        if tag == "method4":
            pos_mm = self.get_geometric_core_position_mm_from_tip(curve_index)
            pos_txt = f"{pos_mm:.1f}" if pos_mm is not None else "?"
            return (
                "high",
                f"geometric core at {pos_txt} mm from tip via bake metadata",
            )
        if tag == "method4_degraded":
            return (
                "low",
                "geometric core sits below probe tip; series degraded to T1",
            )
        if tag == "classifier":
            assignment = self.curve_sensor_assignments.get(curve_index, {}).get(
                'assignment'
            )
            core = assignment.core_assignment
            return (
                getattr(core, "confidence", "medium") or "medium",
                getattr(core, "reason", "") or "",
            )
        return (
            "low",
            "no classifier assignment; using legacy CoreTemperature column",
        )

    def active_core_method(self, curve_index: Optional[int] = None) -> str:
        """Return the method tag feeding the core series for ``curve_index``.

        One of ``"override"`` / ``"method4"`` / ``"method4_degraded"`` /
        ``"classifier"`` / ``"fallback"`` (see :meth:`_resolve_core`). Public
        so UI surfaces (the sidebar Bake Metadata status line) can label the
        active model without reaching into loader internals.
        """
        if curve_index is None:
            curve_index = self.current_curve_index
        df = self._curve_dataframe(curve_index)
        _, tag = self._resolve_core(curve_index, df)
        return tag

    def get_surface_temperature_series(
        self, curve_index: Optional[int] = None
    ) -> Optional[pd.Series]:
        """Return the interpolated surface-temperature series, or ``None``."""
        if curve_index is None:
            curve_index = self.current_curve_index
        overrides = self._sensor_overrides.get(curve_index, {})
        df = self._curve_dataframe(curve_index)
        if 'surface' in overrides and df is not None:
            sensor = overrides['surface']
            if sensor in df.columns:
                return df[sensor].reset_index(drop=True)
        assignment = self.curve_sensor_assignments.get(curve_index, {}).get(
            'assignment'
        )
        if assignment is not None and assignment.surface_assignment is not None:
            return assignment.surface_assignment.temperature_series.reset_index(
                drop=True
            )
        if df is not None and 'SurfaceTemperature' in df.columns:
            return df['SurfaceTemperature'].reset_index(drop=True)
        return None

    def get_ambient_temperature_series(
        self, curve_index: Optional[int] = None
    ) -> Optional[pd.Series]:
        """Return the mean of ambient sensor series, or ``None``."""
        if curve_index is None:
            curve_index = self.current_curve_index
        df = self._curve_dataframe(curve_index)
        if df is None:
            return None
        sensors = self.get_ambient_sensors(curve_index)
        available = [s for s in sensors if s in df.columns]
        if available:
            return df[available].mean(axis=1).reset_index(drop=True)
        if 'AmbientTemperature' in df.columns:
            return df['AmbientTemperature'].reset_index(drop=True)
        return None

    def get_lid_temperature_series(
        self, curve_index: Optional[int] = None
    ) -> Optional[pd.Series]:
        """Return the lid temperature series, or ``None`` when no lid contact."""
        if curve_index is None:
            curve_index = self.current_curve_index
        overrides = self._sensor_overrides.get(curve_index, {})
        df = self._curve_dataframe(curve_index)
        if 'lid' in overrides and df is not None:
            sensor = overrides['lid']
            if sensor and sensor in df.columns:
                return df[sensor].reset_index(drop=True)
        assignment = self.curve_sensor_assignments.get(curve_index, {}).get(
            'assignment'
        )
        if assignment is not None and assignment.lid_assignment is not None:
            return assignment.lid_assignment.temperature_series.reset_index(
                drop=True
            )
        return None

    def _curve_dataframe(self, curve_index: int) -> Optional[pd.DataFrame]:
        """Return the per-curve DataFrame, or fall back to ``self.data``."""
        if 0 <= curve_index < len(self.all_curves):
            return self.all_curves[curve_index].get('data')
        return self.data

    def get_sensor_assignments_with_overrides(self, curve_index: Optional[int] = None) -> Dict:
        """Get sensor assignments including override status."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        assignments = self.get_sensor_assignments().copy()
        
        # Add current sensor assignments
        assignments['core_sensor'] = self.get_core_sensor(curve_index)
        assignments['surface_sensor'] = self.get_surface_sensor(curve_index)
        assignments['internal_sensors'] = self.get_internal_sensors(curve_index)
        assignments['ambient_sensors'] = self.get_ambient_sensors(curve_index)
        
        # For backward compatibility with UI
        assignments['core_sensors'] = [assignments['core_sensor']] if assignments['core_sensor'] else []
        assignments['surface_sensors'] = [assignments['surface_sensor']] if assignments['surface_sensor'] else []
        
        # Check for overrides
        if curve_index in self._sensor_overrides:
            assignments['has_overrides'] = True
            assignments['overrides'] = self._sensor_overrides[curve_index]
        else:
            assignments['has_overrides'] = False
            
        return assignments
    
    def _extract_all_baking_curves(self, df: pd.DataFrame) -> list:
        """Extract baking curves via :class:`CurveBoundaryDetector`.

        Thin adapter: boundary detection is delegated to the pure detector; this
        method layers per-curve sensor-role identification on top of each curve
        returned (the detector is domain-agnostic and does not know about role
        assignment).  The input DataFrame is not mutated.

        When ``self.expected_durations_s`` is set (M5 HMS Dauntless), the
        hint list is forwarded to the detector's ``expected_durations_s``
        kwarg.  A list whose length mismatches the detected curve count
        is accepted — the detector consumes hints positionally and
        ignores entries beyond ``len(detected_curves)`` — but a warning
        is logged so operators can diagnose a mis-entered hint.
        """
        detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
        curves = detector.extract_curves(
            df, expected_durations_s=self.expected_durations_s
        )

        if (
            self.expected_durations_s is not None
            and len(self.expected_durations_s) != len(curves)
        ):
            _log.warning(
                "expected_durations_s length mismatch: %d hint(s) supplied "
                "but %d curve(s) detected; extra hints are ignored, missing "
                "hints fall through to no-hint refinement.",
                len(self.expected_durations_s),
                len(curves),
            )

        # Apply per-curve manual boundary overrides (M1 HMS Ardent).
        # ``_boundary_overrides`` is keyed by DETECTOR position (the
        # index in ``curves`` returned by the detector, before any
        # user-added curves are appended).  This stays stable across
        # M11 HMS Endeavour user-claim insertions which only append.
        if self._boundary_overrides:
            curves = self._apply_boundary_overrides(df, curves)

        # Append user-claimed curves (M11 HMS Endeavour).  Each
        # ``_added_curves`` entry is a ``(start, end)`` operator-drawn
        # range; we auto-refine via the detector on the sub-slice and
        # tag the result with ``_user_added_idx`` so downstream code
        # can distinguish user-added from detector output.
        for added_idx, (added_start, added_end) in enumerate(self._added_curves):
            refined_start, refined_end = self._refine_user_added_region(
                df, added_start, added_end
            )
            curves.append(
                self._build_user_added_curve_dict(
                    df, refined_start, refined_end, added_idx
                )
            )

        # Sort by start_idx so chronological order is preserved across
        # detector + user-added curves; renumber curve_number to match.
        curves.sort(key=lambda c: c["start_idx"])
        for i, c in enumerate(curves):
            c["curve_number"] = i + 1

        # Note: sensor-role identification runs AFTER boundary overrides
        # AND user-added insertion so role detection uses the final
        # post-sort slice.
        for curve_index, curve in enumerate(curves):
            curve["data"] = self._identify_sensor_roles_for_curve(
                curve["data"], curve_index
            )
            _log.debug(
                "Curve %d: duration=%.1f min  samples=%d  max_temp=%.1f°C  "
                "ts_range=%.1fs-%.1fs",
                curve_index + 1,
                curve["duration"],
                curve["samples"],
                curve["max_temp"],
                curve["start_time"],
                curve["end_time"],
            )

        if not curves:
            _log.warning("No valid baking curves found in data")
        else:
            _log.debug("Total curves found: %d", len(curves))
        return curves

    def _apply_boundary_overrides(
        self, df: pd.DataFrame, curves: list
    ) -> list:
        """Replace each overridden curve's slice + derived fields with
        the manually-pinned ``(start_idx, end_idx)`` from
        ``self._boundary_overrides``.  Curves without an override are
        returned unchanged.  Introduced by M1 HMS Ardent.
        """
        timestamps_full = df["Timestamp"].to_numpy(dtype=float)
        for curve_index, (start_idx, end_idx) in self._boundary_overrides.items():
            if curve_index < 0 or curve_index >= len(curves):
                # Stale override (curve count changed since override was set).
                continue
            curve_data = df.iloc[start_idx : end_idx + 1].copy()
            curve_data["Timestamp"] = (
                curve_data["Timestamp"] - curve_data["Timestamp"].iloc[0]
            )
            curve_data["TimeMinutes"] = curve_data["Timestamp"] / 60.0
            curve_data = curve_data.reset_index(drop=True)
            # Rebuild every derived field from the pinned slice so
            # downstream analytics see a consistent view.
            core_col = "CoreTemperature" if "CoreTemperature" in curve_data.columns else "VirtualCoreTemperature"
            peak_temp = float(curve_data[core_col].max()) if core_col in curve_data.columns else 0.0
            curves[curve_index] = {
                "data": curve_data,
                "start_idx": int(start_idx),
                "end_idx": int(end_idx),
                "start_time": float(timestamps_full[start_idx]),
                "end_time": float(timestamps_full[end_idx]),
                "duration": float(curve_data["TimeMinutes"].max()),
                "max_temp": peak_temp,
                "curve_number": curve_index + 1,
                "samples": len(curve_data),
                "truncated": False,
                "exit_candidate_kind": "manual_override",
            }
        return curves

    def _build_user_added_curve_dict(
        self, df: pd.DataFrame, start_idx: int, end_idx: int, added_idx: int
    ) -> dict:
        """Build a curve descriptor dict for a user-claimed region
        (M11 HMS Endeavour).  Mirrors :meth:`_apply_boundary_overrides`'s
        dict shape but tags the curve with ``_user_added_idx`` and
        ``exit_candidate_kind="user_added"`` so the UI can render it
        distinctly and ``set_curve_boundaries`` can dispatch updates
        back into ``self._added_curves``.
        """
        timestamps_full = df["Timestamp"].to_numpy(dtype=float)
        curve_data = df.iloc[start_idx : end_idx + 1].copy()
        curve_data["Timestamp"] = (
            curve_data["Timestamp"] - curve_data["Timestamp"].iloc[0]
        )
        curve_data["TimeMinutes"] = curve_data["Timestamp"] / 60.0
        curve_data = curve_data.reset_index(drop=True)
        core_col = (
            "CoreTemperature"
            if "CoreTemperature" in curve_data.columns
            else "VirtualCoreTemperature"
        )
        peak_temp = (
            float(curve_data[core_col].max())
            if core_col in curve_data.columns
            else 0.0
        )
        return {
            "data": curve_data,
            "start_idx": int(start_idx),
            "end_idx": int(end_idx),
            "start_time": float(timestamps_full[start_idx]),
            "end_time": float(timestamps_full[end_idx]),
            "duration": float(curve_data["TimeMinutes"].max()),
            "max_temp": peak_temp,
            "curve_number": -1,  # filled in by the sort + renumber loop
            "samples": len(curve_data),
            "truncated": False,
            "exit_candidate_kind": "user_added",
            "_user_added_idx": int(added_idx),
        }

    def _refine_user_added_region(
        self, df: pd.DataFrame, start_idx: int, end_idx: int
    ) -> tuple[int, int]:
        """Auto-refine a user-claimed (start, end) region by running
        the detector on the sub-slice.  Falls back to a BAKE_ACTIVE_C
        trim if the detector finds no curve, and finally to the
        operator's range as-is.

        Translates the detector's sub-slice positional indices back
        into raw_data positional indices by adding ``start_idx``.
        Introduced by M11 HMS Endeavour.
        """
        n_raw = len(df)
        if start_idx < 0 or end_idx >= n_raw or start_idx >= end_idx:
            return (start_idx, end_idx)

        sub = df.iloc[start_idx : end_idx + 1].reset_index(drop=True)

        # First try: run the detector on the sub-slice.  If it finds a
        # curve (passes MIN_PEAK_TEMP + MIN_CURVE_DURATION_SECONDS
        # gates), use those refined boundaries.
        try:
            detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
            sub_curves = detector.extract_curves(sub)
        except Exception:  # pragma: no cover  (defensive)
            sub_curves = []
        if sub_curves:
            sub_start = int(sub_curves[0]["start_idx"]) + start_idx
            sub_end = int(sub_curves[0]["end_idx"]) + start_idx
            if sub_start < sub_end:
                return (sub_start, sub_end)

        # Fallback: trim leading and trailing samples below
        # BAKE_ACTIVE_C so a coarse user drag still snaps to roughly
        # the bake's active region.
        bake_active = float(
            CURVE_DETECTION_CONFIG.get("BAKE_ACTIVE_THRESHOLD_C", 40.0)
        )
        core_col = (
            "CoreTemperature"
            if "CoreTemperature" in sub.columns
            else "VirtualCoreTemperature"
        )
        if core_col in sub.columns:
            temps = sub[core_col].to_numpy(dtype=float)
            s_local = 0
            while s_local < len(temps) and temps[s_local] < bake_active:
                s_local += 1
            e_local = len(temps) - 1
            while e_local > s_local and temps[e_local] < bake_active:
                e_local -= 1
            if s_local < e_local:
                return (start_idx + s_local, start_idx + e_local)

        # Final fallback: accept the operator's range verbatim.
        return (start_idx, end_idx)

    def add_manual_curve(self, start_idx: int, end_idx: int) -> int:
        """Claim a region the detector missed as a curve, refining the
        boundaries against the detector / BAKE_ACTIVE_C threshold.

        Returns the new curve's position in ``self.all_curves`` after
        the sort.  Introduced by M11 HMS Endeavour.

        Raises:
          ValueError — if the range is inverted or out of bounds.
        """
        if self.raw_data is None or len(self.raw_data) == 0:
            raise RuntimeError(
                "raw_data is empty; load a CSV before claiming a curve."
            )
        n = len(self.raw_data)
        if not (0 <= start_idx < n) or not (0 <= end_idx < n):
            raise ValueError(
                f"start_idx={start_idx} and end_idx={end_idx} must lie in "
                f"[0, {n - 1}]."
            )
        if start_idx >= end_idx:
            raise ValueError(
                f"start_idx={start_idx} must be less than end_idx={end_idx}."
            )

        added_idx = len(self._added_curves)
        self._added_curves.append((int(start_idx), int(end_idx)))
        self._reapply_boundary_state()

        # Find the user-added curve in the post-sort all_curves list
        # via its ``_user_added_idx`` tag.
        for i, c in enumerate(self.all_curves):
            if c.get("_user_added_idx") == added_idx:
                return i
        return -1

    def remove_manual_curve(self, curve_index: int) -> None:
        """Remove a user-added curve.  No-op if ``curve_index`` points
        at a detector curve.  Introduced by M11 HMS Endeavour.
        """
        if not (0 <= curve_index < len(self.all_curves)):
            return
        target = self.all_curves[curve_index]
        added_idx = target.get("_user_added_idx")
        if added_idx is None:
            return
        # Drop the entry; subsequent _user_added_idx values shift
        # down on the next re-extract because the list index changes.
        if 0 <= added_idx < len(self._added_curves):
            del self._added_curves[added_idx]
            self._reapply_boundary_state()

    def get_sensor_data(self) -> pd.DataFrame:
        """Get only the temperature sensor columns."""
        sensor_cols = ['Timestamp', 'TimeMinutes', 'T1', 'T2', 'T3', 'T4', 
                      'T5', 'T6', 'T7', 'T8']
        return self.data[sensor_cols]
    
    def get_analysis_data(self) -> pd.DataFrame:
        """Get data formatted for analysis."""
        return self.data
    
    def get_all_curves(self) -> list:
        """Get all detected baking curves."""
        return self.all_curves
    
    def get_curve_count(self) -> int:
        """Get the number of detected curves."""
        return len(self.all_curves)
    
    def set_current_curve(self, curve_index: int) -> pd.DataFrame:
        """Set the current curve for analysis."""
        if 0 <= curve_index < len(self.all_curves):
            self.current_curve_index = curve_index
            self.data = self.all_curves[curve_index]['data']
            
            # Load curve-specific sensor assignments into deprecated sensor_assignments
            # for backward compatibility
            if curve_index in self.curve_sensor_assignments:
                self.sensor_assignments = self.curve_sensor_assignments[curve_index]
        return self.data
    
    def get_current_curve_info(self) -> dict:
        """Get metadata about the current curve."""
        if self.all_curves and 0 <= self.current_curve_index < len(self.all_curves):
            return self.all_curves[self.current_curve_index]
        return None
    
    def _validate_sensor_assignments(self, df: pd.DataFrame) -> None:
        return self._sensor_manager.validate_sensor_assignments(df)

    def _get_automatic_core_sensors(self, curve_index: int) -> List[str]:
        return self._sensor_manager.get_automatic_core_sensors(curve_index)

    def _get_automatic_surface_sensors(self, curve_index: int) -> List[str]:
        return self._sensor_manager.get_automatic_surface_sensors(curve_index)

    def _get_automatic_ambient_sensors(self, curve_index: int) -> List[str]:
        return self._sensor_manager.get_automatic_ambient_sensors(curve_index)
    
    def _apply_standard_columns(self, df: pd.DataFrame, curve_index: int) -> None:
        """Single canonical writer of the standardised temperature columns.

        Layering (M3a HMS Royal Sovereign):
          - Manual override (``_sensor_overrides[curve_index][role]``) wins.
          - Otherwise the spatial classifier's ``temperature_series`` (interpolated
            at the inferred position) is used.
          - Final firmware/legacy fallback only when no classifier output exists.

        ``LidTemperature`` is written ONLY when the classifier reports a lid
        contact (or the user has set a manual lid override). When neither is
        present, any pre-existing ``LidTemperature`` column is dropped — the
        column is present-or-absent, never NaN.
        """
        if df is None:
            return

        curve_assignments = self.curve_sensor_assignments.get(curve_index, {})
        overrides = self._sensor_overrides.get(curve_index, {})
        assignment = curve_assignments.get('assignment')

        # --- CoreTemperature -------------------------------------------------
        # Layer override → Method 4 → classifier through the shared helper
        # (M26 HMS Bellerophon DRY contract); legacy ``resolve_core_temperature_series``
        # remains as the final fallback when no layer produces a series.
        core_series = self._resolve_core_series(curve_index, df)
        if core_series is not None:
            df['CoreTemperature'] = self._align_series(core_series, df)
        else:
            try:
                df['CoreTemperature'] = resolve_core_temperature_series(df)
            except KeyError:
                pass

        # --- SurfaceTemperature ----------------------------------------------
        surface_override = overrides.get('surface')
        if surface_override and surface_override in df.columns:
            df['SurfaceTemperature'] = df[surface_override]
        elif (
            assignment is not None
            and assignment.surface_assignment is not None
        ):
            df['SurfaceTemperature'] = self._align_series(
                assignment.surface_assignment.temperature_series, df
            )
        elif 'VirtualSurfaceTemperature' in df.columns:
            df['SurfaceTemperature'] = df['VirtualSurfaceTemperature']
        elif 'SurfaceAverage' in df.columns:
            df['SurfaceTemperature'] = df['SurfaceAverage']
        elif all(col in df.columns for col in ['T7', 'T8']):
            df['SurfaceTemperature'] = df[['T7', 'T8']].mean(axis=1)

        # --- AmbientTemperature ----------------------------------------------
        ambient_override = overrides.get('ambient')
        if ambient_override:
            # Override may be a single sensor or a list.
            if isinstance(ambient_override, str):
                amb_list = [ambient_override]
            else:
                amb_list = list(ambient_override)
            available = [s for s in amb_list if s in df.columns]
            if available:
                df['AmbientTemperature'] = df[available].mean(axis=1)
            elif 'VirtualAmbientTemperature' in df.columns:
                df['AmbientTemperature'] = df['VirtualAmbientTemperature']
            elif 'T8' in df.columns:
                df['AmbientTemperature'] = df['T8']
        elif assignment is not None and assignment.ambient_assignments:
            # Mean across all classifier-identified ambient sensors.
            sensors = [a.nearest_sensor for a in assignment.ambient_assignments
                       if a.nearest_sensor in df.columns]
            if sensors:
                df['AmbientTemperature'] = df[sensors].mean(axis=1)
            elif 'VirtualAmbientTemperature' in df.columns:
                df['AmbientTemperature'] = df['VirtualAmbientTemperature']
            elif 'T8' in df.columns:
                df['AmbientTemperature'] = df['T8']
        elif surface_override:
            # Surface override implies geometry changed — recompute ambient.
            ambient_sensors = self.get_ambient_sensors(curve_index)
            available_ambient = [s for s in ambient_sensors if s in df.columns]
            if available_ambient:
                df['AmbientTemperature'] = df[available_ambient].max(axis=1)
            elif 'VirtualAmbientTemperature' in df.columns:
                df['AmbientTemperature'] = df['VirtualAmbientTemperature']
            elif 'T8' in df.columns:
                df['AmbientTemperature'] = df['T8']
        elif 'VirtualAmbientTemperature' in df.columns:
            df['AmbientTemperature'] = df['VirtualAmbientTemperature']
        elif 'T8' in df.columns:
            df['AmbientTemperature'] = df['T8']

        # --- LidTemperature (M3a, M3b) ---------------------------------------
        # Manual override priority:
        #   - 'lid' key explicitly None -> operator cleared lid; drop column.
        #   - 'lid' key set to a sensor name -> write df[sensor].
        #   - 'lid' key absent             -> fall through to classifier.
        # Classifier writes only when assignment.lid_assignment is non-None.
        # Otherwise drop a stale column.
        if 'lid' in overrides:
            lid_override = overrides['lid']
            if lid_override is None:
                if 'LidTemperature' in df.columns:
                    df.drop(columns=['LidTemperature'], inplace=True)
            elif lid_override in df.columns:
                df['LidTemperature'] = df[lid_override]
        elif assignment is not None and assignment.lid_assignment is not None:
            df['LidTemperature'] = self._align_series(
                assignment.lid_assignment.temperature_series, df
            )
        elif 'LidTemperature' in df.columns:
            # Stale column from a prior curve / manual planting — drop.
            df.drop(columns=['LidTemperature'], inplace=True)

    @staticmethod
    def _align_series(series: pd.Series, df: pd.DataFrame) -> pd.Series:
        """Return ``series`` reshaped to ``df``'s row count, defensively.

        Classifier-emitted temperature series are sliced from the same
        DataFrame the loader passed in, so equal-length is the common path.
        When length differs (e.g. classifier auto-segmented a long raw CSV),
        we reindex by position; mismatched lengths return the original
        series so the caller still gets a usable Series.
        """
        if len(series) == len(df):
            return series.reset_index(drop=True)
        return series.reset_index(drop=True)

    def _regenerate_standard_columns(self):
        """Regenerate standardized temperature columns based on current sensor assignments."""
        if self.data is None:
            return
        self._apply_standard_columns(self.data, self.current_curve_index)

    def _generate_standard_columns_for_df(self, df: pd.DataFrame):
        """Generate standardized temperature columns for a dataframe during initial load."""
        # Resolve curve_index by identity against all_curves so a freshly
        # extracted curve's physics flag is honoured.
        curve_index = self.current_curve_index
        for idx, info in enumerate(getattr(self, 'all_curves', []) or []):
            if info.get('data') is df:
                curve_index = idx
                break
        self._apply_standard_columns(df, curve_index)
    

def validate_thermal_data(df: pd.DataFrame) -> Tuple[bool, list]:
    """
    Validate thermal profile data.
    
    Returns:
        Tuple of (is_valid, list of issues)
    """
    issues = []
    
    # Check required columns
    required_cols = ['Timestamp'] + list(SENSOR_LIST)
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"Missing required columns: {missing_cols}")
    
    # Check for NaN values only in existing columns
    existing_cols = [col for col in required_cols if col in df.columns]
    if existing_cols:
        nan_counts = df[existing_cols].isna().sum()
        if nan_counts.any():
            issues.append(f"Found NaN values: {nan_counts[nan_counts > 0].to_dict()}")
    
    # Check temperature ranges
    temp_cols = list(SENSOR_LIST)
    for col in temp_cols:
        if col in df.columns:
            min_temp = df[col].min()
            max_temp = df[col].max()
            if min_temp < -50 or max_temp > 300:
                issues.append(f"{col} has unrealistic temperatures: {min_temp:.1f}°C to {max_temp:.1f}°C")
    
    # Check time monotonicity
    if not df['Timestamp'].is_monotonic_increasing:
        issues.append("Timestamp is not monotonically increasing")
    
    return len(issues) == 0, issues