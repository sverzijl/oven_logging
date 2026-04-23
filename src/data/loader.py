"""Data loading and parsing utilities for thermal profile CSV files."""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, Union, List
import re
from datetime import datetime
import io
from config.constants import INTERNAL_SENSOR_CONFIG


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
        
        # Extract all baking curves
        self.all_curves = self._extract_all_baking_curves(self.data)
        
        # Set the first curve as default if any curves found
        if self.all_curves:
            self.data = self.all_curves[0]['data']
            self.current_curve_index = 0
        
        return self.data, self.metadata
    
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
            if 'VirtualCoreTemperature' in df.columns:
                df['CoreTemperature'] = df['VirtualCoreTemperature']
            elif all(col in df.columns for col in ['T1', 'T2', 'T3', 'T4']):
                df['CoreTemperature'] = df[['T1', 'T2', 'T3', 'T4']].mean(axis=1)
            elif 'T1' in df.columns:
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
        """
        Identify which sensors represent core, surface, and ambient temperatures.
        
        Uses the probe's built-in virtual sensor assignments when available,
        or falls back to dynamic classification based on temperature patterns.
        """
        # Method 1: Use virtual sensor assignments from CSV (preferred)
        virtual_cols = ['VirtualCoreTemperature', 'VirtualSurfaceTemperature', 
                       'VirtualAmbientTemperature']
        assignment_cols = ['VirtualCoreSensor', 'VirtualSurfaceSensor', 
                          'VirtualAmbientSensor']
        
        used_virtual_path = all(col in df.columns for col in virtual_cols + assignment_cols)
        if used_virtual_path:
            # Track most common sensor assignments for each role
            if len(df) > 0:
                curve_assignments = {
                    'core': df['VirtualCoreSensor'].mode().iloc[0] if not df['VirtualCoreSensor'].mode().empty else 'Unknown',
                    'surface': df['VirtualSurfaceSensor'].mode().iloc[0] if not df['VirtualSurfaceSensor'].mode().empty else 'Unknown',
                    'ambient': df['VirtualAmbientSensor'].mode().iloc[0] if not df['VirtualAmbientSensor'].mode().empty else 'Unknown'
                }
                
                # Add assignment frequency info
                for role, col in zip(['core', 'surface', 'ambient'], assignment_cols):
                    if col in df.columns:
                        counts = df[col].value_counts()
                        if len(counts) > 0:
                            primary = counts.index[0]
                            percentage = (counts.iloc[0] / len(df)) * 100
                            curve_assignments[f'{role}_info'] = {
                                'primary': primary,
                                'percentage': percentage,
                                'all_sensors': counts.to_dict()
                            }
                
                # Store per-curve
                self.curve_sensor_assignments[curve_index] = curve_assignments
                
                # Also update deprecated sensor_assignments for backward compatibility
                self.sensor_assignments = curve_assignments
            
            print(f"Curve {curve_index + 1}: Using virtual sensor assignments from CSV:")
            print(f"  Core: {curve_assignments.get('core', 'Unknown')} ({curve_assignments.get('core_info', {}).get('percentage', 0):.1f}% of readings)")
            print(f"  Surface: {curve_assignments.get('surface', 'Unknown')} ({curve_assignments.get('surface_info', {}).get('percentage', 0):.1f}% of readings)")
            print(f"  Ambient: {curve_assignments.get('ambient', 'Unknown')} ({curve_assignments.get('ambient_info', {}).get('percentage', 0):.1f}% of readings)")
            
            # Validate assignments using thermodynamic principles
            self._validate_sensor_assignments(df)
            
            # Apply physics-based surface sensor correction if enabled
            from config.constants import SURFACE_DETECTION_CONFIG
            if SURFACE_DETECTION_CONFIG['USE_PHYSICS_BASED_DETECTION']:
                df = self._apply_physics_based_surface_correction(df, curve_index)
            
        else:
            # Method 2: Enhanced dynamic classification using thermodynamic principles
            print(f"Curve {curve_index + 1}: Virtual sensor data not available, using thermodynamic classification")
            df = self._classify_sensors_dynamically(df, curve_index)
        
        # For backward compatibility, also create the old average columns
        # but mark them as deprecated
        if all(col in df.columns for col in ['T1', 'T2', 'T3', 'T4']):
            df['CoreAverage'] = df[['T1', 'T2', 'T3', 'T4']].mean(axis=1)
        if all(col in df.columns for col in ['T7', 'T8']):
            df['SurfaceAverage'] = df[['T7', 'T8']].mean(axis=1)
        
        # Generate standardized columns via the single canonical writer.
        # Only run on the virtual-path branch: the dynamic-classification branch
        # below already wrote Core/Surface/Ambient from thermodynamically-chosen
        # sensors and has no Virtual* columns to fall back on, so re-running the
        # helper there would wipe its assignment.
        if used_virtual_path:
            self._apply_standard_columns(df, curve_index)

        return df
    
    def _apply_physics_based_surface_correction(self, df: pd.DataFrame, curve_index: int) -> pd.DataFrame:
        """Apply physics-based surface sensor correction to fix firmware misidentification."""
        from ..data.surface_sensor_detector import identify_surface_sensor_advanced
        from config.constants import SURFACE_DETECTION_CONFIG
        
        # Get sample period from metadata
        sample_period_ms = self.metadata.get('sample_period_ms', 5000)
        
        # Run detection algorithm
        result = identify_surface_sensor_advanced(df, sample_period_ms)
        
        if result and result['confidence'] >= SURFACE_DETECTION_CONFIG['CONFIDENCE_THRESHOLD']:
            # Store original firmware selection for comparison
            curve_assignments = self.curve_sensor_assignments.get(curve_index, {})
            firmware_surface_sensor = curve_assignments.get('surface', 'Unknown')
            firmware_surface_max_temp = df['VirtualSurfaceTemperature'].max() if 'VirtualSurfaceTemperature' in df.columns else 0
            
            # Apply correction
            surface_sensor = result['sensor']
            df['SurfaceTemperature'] = df[surface_sensor]
            df['PhysicsBasedSurfaceDetection'] = True
            
            # Update sensor assignments for this curve
            curve_assignments['surface'] = surface_sensor
            curve_assignments['surface_detection'] = result
            curve_assignments['physics_corrected'] = True
            curve_assignments['firmware_surface_sensor'] = firmware_surface_sensor
            curve_assignments['firmware_surface_max_temp'] = firmware_surface_max_temp
            self.curve_sensor_assignments[curve_index] = curve_assignments
            
            # Update deprecated sensor_assignments for backward compatibility
            self.sensor_assignments = curve_assignments
            
            # Log the correction if enabled
            if SURFACE_DETECTION_CONFIG['LOG_CORRECTIONS']:
                print(f"\n✅ Curve {curve_index + 1}: Physics-based surface sensor correction applied:")
                print(f"   Firmware selected: {firmware_surface_sensor} (max {firmware_surface_max_temp:.1f}°C)")
                print(f"   Corrected to: {surface_sensor} (max {result['max_temp']:.1f}°C)")
                print(f"   Confidence: {result['confidence']}%")
                print(f"   Reasoning: {result['reasoning']}")
                print(f"   Browning time: {result['browning_time']:.1f} minutes")
        else:
            # Mark that physics detection was attempted but not applied
            df['PhysicsBasedSurfaceDetection'] = False
            curve_assignments = self.curve_sensor_assignments.get(curve_index, {})
            curve_assignments['physics_corrected'] = False
            self.curve_sensor_assignments[curve_index] = curve_assignments
            
            # Update deprecated sensor_assignments
            self.sensor_assignments = curve_assignments
            
            if result:
                print(f"\n⚠️  Curve {curve_index + 1}: Physics-based detection confidence too low ({result.get('confidence', 0)}%)")
            else:
                print(f"\n⚠️  Curve {curve_index + 1}: Physics-based surface detection failed - using firmware selection")
        
        return df
    
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
    
    def set_sensor_override(self, curve_index: int, role: str, sensor: str):
        """
        Allow user to override sensor assignments for a specific curve.
        
        Args:
            curve_index: Index of the curve
            role: 'core', 'surface', or 'ambient'
            sensor: Single sensor name (e.g., 'T2')
        """
        if curve_index not in self._sensor_overrides:
            self._sensor_overrides[curve_index] = {}
        self._sensor_overrides[curve_index][role] = sensor
        
        # Regenerate standard columns for this curve if it's the current one
        if curve_index == self.current_curve_index:
            self._regenerate_standard_columns()
    
    def clear_sensor_overrides(self, curve_index: int):
        """Clear all user overrides for a curve, reverting to automatic detection."""
        if curve_index in self._sensor_overrides:
            del self._sensor_overrides[curve_index]
            
        # Regenerate columns if this is the current curve
        if curve_index == self.current_curve_index:
            self._regenerate_standard_columns()
    
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
        """Get list of physical sensors identified as ambient (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # If we have overrides, infer ambient sensors based on surface position
        if curve_index in self._sensor_overrides and 'surface' in self._sensor_overrides[curve_index]:
            surface_sensor = self._sensor_overrides[curve_index]['surface']
            if surface_sensor and len(surface_sensor) >= 2:
                surface_num = int(surface_sensor[1])
                # Return all sensors with numbers greater than surface
                ambient_sensors = []
                for i in range(surface_num + 1, 9):  # T1-T8, so max is 8
                    sensor = f'T{i}'
                    if sensor in self.data.columns:
                        ambient_sensors.append(sensor)
                return ambient_sensors
            
        # Otherwise return automatic detection
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
    
    def _classify_sensors_dynamically(self, df: pd.DataFrame, curve_index: int) -> pd.DataFrame:
        """
        Dynamically classify sensors using thermodynamic principles.
        
        This is a fallback method when virtual sensor data is not available.
        """
        sensor_cols = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
        available_sensors = [col for col in sensor_cols if col in df.columns]
        
        if len(available_sensors) < 3:
            print("Warning: Not enough sensors for dynamic classification")
            # Fall back to old hardcoded method
            if all(col in df.columns for col in ['T1', 'T2', 'T3', 'T4']):
                df['CoreTemperature'] = df[['T1', 'T2', 'T3', 'T4']].mean(axis=1)
            if all(col in df.columns for col in ['T7', 'T8']):
                df['SurfaceTemperature'] = df[['T7', 'T8']].mean(axis=1)
            df['AmbientTemperature'] = df[available_sensors].max(axis=1) if available_sensors else 0
            return df
        
        # Try thermodynamic classification first
        try:
            from ..data.thermodynamic_sensor_classifier import ThermodynamicSensorClassifier
            classifier = ThermodynamicSensorClassifier(df, available_sensors)
            assignments = classifier.classify_sensors()
            
            # Use thermodynamic assignments
            core_sensors = assignments.get('core', [])
            surface_sensors = assignments.get('surface', [])
            ambient_sensors = assignments.get('ambient', [])
            
            # Calculate temperatures based on classification
            df['CoreTemperature'] = df[core_sensors].mean(axis=1) if core_sensors else df[available_sensors[:2]].mean(axis=1)
            df['SurfaceTemperature'] = df[surface_sensors].mean(axis=1) if surface_sensors else df[available_sensors[2:4]].mean(axis=1)
            df['AmbientTemperature'] = df[ambient_sensors].mean(axis=1) if ambient_sensors else df[available_sensors[-2:]].mean(axis=1)
            
            # Store assignments per curve
            curve_assignments = {
                'core': core_sensors[0] if core_sensors else 'Unknown',
                'surface': surface_sensors[0] if surface_sensors else 'Unknown', 
                'ambient': ambient_sensors[0] if ambient_sensors else 'Unknown',
                'method': 'thermodynamic_classification'
            }
            self.curve_sensor_assignments[curve_index] = curve_assignments
            
            # Update deprecated sensor_assignments
            self.sensor_assignments = curve_assignments
            
            print(f"Thermodynamic sensor classification:")
            for role, sensors in assignments.items():
                print(f"  {role.upper()}: {', '.join(sensors)}")
            
            return df
            
        except Exception as e:
            print(f"Thermodynamic classification failed: {e}")
            print("Falling back to simple temperature-based classification")
        
        # Calculate statistics for each sensor
        sensor_stats = {}
        for sensor in available_sensors:
            sensor_stats[sensor] = {
                'mean': df[sensor].mean(),
                'max': df[sensor].max(),
                'range': df[sensor].max() - df[sensor].min(),
                'std': df[sensor].std()
            }
        
        # Sort sensors by maximum temperature (core < surface < ambient)
        sorted_sensors = sorted(sensor_stats.items(), key=lambda x: x[1]['max'])
        
        # Assign roles based on temperature characteristics
        # Lowest max temp sensors are likely core
        core_sensors = [s[0] for s in sorted_sensors[:2]]  # 2 coolest sensors
        # Highest max temp sensors are likely ambient
        ambient_sensors = [s[0] for s in sorted_sensors[-2:]]  # 2 hottest sensors
        # Middle sensors are likely surface
        surface_sensors = [s[0] for s in sorted_sensors[2:-2]]  # Middle sensors
        
        # If we don't have enough surface sensors, use some from the edges
        if len(surface_sensors) < 2:
            surface_sensors = [s[0] for s in sorted_sensors[2:4]]
        
        print(f"Dynamic sensor classification based on temperature patterns:")
        print(f"  Core sensors: {core_sensors} (coolest)")
        print(f"  Surface sensors: {surface_sensors} (intermediate)")
        print(f"  Ambient sensors: {ambient_sensors} (hottest)")
        
        # Calculate temperatures based on classification
        df['CoreTemperature'] = df[core_sensors].mean(axis=1)
        df['SurfaceTemperature'] = df[surface_sensors].mean(axis=1) if surface_sensors else df[core_sensors].mean(axis=1) * 1.1
        df['AmbientTemperature'] = df[ambient_sensors].mean(axis=1)
        
        # Store assignments per curve
        curve_assignments = {
            'core': ', '.join(core_sensors),
            'surface': ', '.join(surface_sensors),
            'ambient': ', '.join(ambient_sensors),
            'method': 'dynamic_classification'
        }
        self.curve_sensor_assignments[curve_index] = curve_assignments
        
        # Update deprecated sensor_assignments
        self.sensor_assignments = curve_assignments
        
        return df
    
    def _extract_baking_curve(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract the actual baking curve from the full dataset.
        
        The baking curve starts when the probe is inserted (or temperature rises rapidly)
        and ends when the product is removed from the oven (temperature drops rapidly).
        
        NOTE: This method is deprecated and only extracts the first curve.
        Use extract_all_baking_curves() for multiple curve support.
        """
        # Extract all curves and return the first one
        curves = self._extract_all_baking_curves(df)
        if curves:
            return curves[0]['data']
        else:
            # No valid curves found, return original data
            return df
    
    def _extract_all_baking_curves(self, df: pd.DataFrame) -> list:
        """
        Improved curve extraction that better handles cases where probe
        doesn't cool to room temperature between bakes.
        
        Key improvements:
        1. Distinguishes between normal negative delta (in oven) vs probe removal
        2. Uses temperature trajectory to identify curve boundaries
        3. Detects room temperature plateaus between curves
        """
        curves = []
        core_col = 'CoreTemperature' if 'CoreTemperature' in df.columns else 'CoreAverage'
        
        if core_col not in df.columns:
            print("Warning: No core temperature column found")
            return curves
        
        # Add ambient column if available
        ambient_col = None
        if 'VirtualAmbientTemperature' in df.columns:
            ambient_col = 'VirtualAmbientTemperature'
        elif 'AmbientTemperature' in df.columns:
            ambient_col = 'AmbientTemperature'
        
        # Calculate temperature metrics
        df['temp_change'] = df[core_col].diff()
        df['temp_smooth'] = df[core_col].rolling(window=5, center=True).mean().fillna(df[core_col])
        
        # Parameters
        MIN_CURVE_DURATION = 60  # 5 minutes
        MIN_PEAK_TEMP = 80
        ROOM_TEMP_MAX = 35  # Maximum temperature considered "room temperature"
        
        i = 0
        while i < len(df):
            # Find curve start
            start_idx = None
            
            # Method 1: PredictionState change
            if 'PredictionState' in df.columns:
                for j in range(i, len(df) - 1):
                    if (df.iloc[j]['PredictionState'] == 'Probe Not Inserted' and 
                        df.iloc[j+1]['PredictionState'] != 'Probe Not Inserted'):
                        start_idx = j + 1
                        break
            
            # Method 2: Rapid temperature rise from low temperature
            if start_idx is None:
                for j in range(i, len(df) - 1):
                    current_temp = df.iloc[j][core_col]
                    next_temp = df.iloc[j+1][core_col]
                    
                    # Temperature rise from below 40°C
                    if current_temp < 40 and next_temp - current_temp > 5:
                        start_idx = j
                        break
                    
                    # Or sustained rise after room temperature period
                    if j >= 5:
                        recent_avg = df[core_col].iloc[j-5:j].mean()
                        if recent_avg < ROOM_TEMP_MAX and current_temp > recent_avg + 3:
                            start_idx = j - 5
                            break
            
            if start_idx is None:
                break
            
            # Find curve peak - stop searching if we hit room temperature
            peak_idx = start_idx
            peak_temp = df.iloc[start_idx][core_col]
            room_temp_count = 0
            
            for j in range(start_idx + 1, len(df)):
                current_temp = df.iloc[j][core_col]
                
                # Update peak if we find a higher temperature
                if current_temp > peak_temp:
                    peak_temp = current_temp
                    peak_idx = j
                    room_temp_count = 0
                
                # If we've found a peak and temperature drops to room temp, stop searching
                if peak_temp > 70 and current_temp < ROOM_TEMP_MAX:
                    room_temp_count += 1
                    # If temp stays at room temp for 20+ samples (100+ seconds), we're done
                    if room_temp_count >= 20:
                        break
                else:
                    room_temp_count = 0
                
                # Also stop if we see a massive drop (probe removal)
                if j > start_idx + 20 and peak_temp > 70:
                    if peak_temp - current_temp > 40:
                        break
            
            # Find curve end - more sophisticated detection
            end_idx = None
            
            # Only start looking for end after reaching 70°C
            search_start = peak_idx
            for j in range(start_idx, peak_idx):
                if df.iloc[j][core_col] > 70:
                    search_start = j
                    break
            
            # Look for curve end indicators
            for j in range(search_start + 1, len(df)):
                temp = df.iloc[j][core_col]
                
                # End condition 1: Rapid cooling to room temperature
                if j >= search_start + 20:  # At least 100 seconds after search start
                    # Check if we've cooled to near room temperature
                    if temp < ROOM_TEMP_MAX and peak_temp - temp > 50:
                        # Verify it stays low (not just a measurement glitch)
                        if j + 5 < len(df):
                            future_temps = df[core_col].iloc[j:j+5]
                            if future_temps.max() < ROOM_TEMP_MAX + 5:
                                end_idx = j
                                break
                
                # End condition 2: Extended stable period at room temperature
                if j >= search_start + 60:  # At least 5 minutes after search start
                    window_size = 20  # 100 seconds
                    if j >= window_size:
                        recent_temps = df['temp_smooth'].iloc[j-window_size:j+1]
                        temp_std = recent_temps.std()
                        temp_mean = recent_temps.mean()
                        
                        # Stable at room temperature
                        if temp_std < 2 and 18 < temp_mean < ROOM_TEMP_MAX:
                            # Find where the rapid cooling started
                            for k in range(j - window_size, search_start, -1):
                                if df.iloc[k][core_col] > temp_mean + 20:
                                    end_idx = k + 1
                                    break
                            if end_idx is None:
                                end_idx = j - window_size
                            break
                
                # End condition 3: Rapid temperature drop indicating probe removal
                # Check for extreme drop rate that indicates probe removal
                # Changed: Allow detection immediately after peak (was j > peak_idx + 10)
                if j > peak_idx:  # Any time after peak
                    # First check for instant massive drops (probe removal signature)
                    if j > 0:
                        instant_drop = df.iloc[j-1][core_col] - df.iloc[j][core_col]
                        # If temperature drops >15°C in one sample (5 seconds), it's definitely probe removal
                        if instant_drop > 15:
                            end_idx = j - 1
                            break
                    
                    # Also check drop rate over last few samples
                    lookback = min(5, j - search_start)
                    if lookback > 0:
                        recent_drop = df.iloc[j-lookback][core_col] - temp
                        time_span = df.iloc[j]['Timestamp'] - df.iloc[j-lookback]['Timestamp']
                        if time_span > 0:
                            drop_rate_per_sec = recent_drop / time_span
                            
                            # If temperature drops more than 2°C/second (120°C/min), it's probe removal
                            if drop_rate_per_sec > 2.0:
                                # Find exactly where the rapid drop started
                                for k in range(j, max(j-lookback-5, peak_idx), -1):
                                    if k > 0:
                                        instant_drop = df.iloc[k-1][core_col] - df.iloc[k][core_col]
                                        # Drops > 15°C in one 5-second interval clearly indicate probe removal
                                        if instant_drop > 15:
                                            end_idx = k - 1
                                            break
                                        # Or sustained high drop rate
                                        elif instant_drop > 5 and k < j:
                                            end_idx = k
                                            break
                                if end_idx is None:
                                    end_idx = j - 1
                                break
                
                # End condition 4: Major temperature drop (>40°C) from peak with verification
                if peak_temp - temp > 40 and j > peak_idx + 10:
                    # Verify this is a real drop, not noise
                    if j + 3 < len(df):
                        future_temps = df[core_col].iloc[j:j+3]
                        if future_temps.max() < temp + 5:  # Stays low
                            end_idx = j
                            break
            
            if end_idx is None:
                end_idx = len(df) - 1
            
            # Validate and store curve
            duration = end_idx - start_idx + 1
            if duration >= MIN_CURVE_DURATION and peak_temp >= MIN_PEAK_TEMP:
                # Create curve data
                curve_data = df.iloc[start_idx:end_idx+1].copy()
                
                # Reset timestamps
                curve_data['Timestamp'] = curve_data['Timestamp'] - curve_data['Timestamp'].iloc[0]
                curve_data['TimeMinutes'] = curve_data['Timestamp'] / 60.0
                
                # Reset index
                curve_data = curve_data.reset_index(drop=True)
                
                # Identify sensor roles for this specific curve
                curve_index = len(curves)  # Current curve index (0-based)
                curve_data = self._identify_sensor_roles_for_curve(curve_data, curve_index)
                
                # Store curve info
                curve_info = {
                    'data': curve_data,
                    'start_idx': start_idx,
                    'end_idx': end_idx,
                    'start_time': df['Timestamp'].iloc[start_idx],
                    'end_time': df['Timestamp'].iloc[end_idx],
                    'duration': curve_data['TimeMinutes'].max(),
                    'max_temp': peak_temp,
                    'curve_number': len(curves) + 1,
                    'samples': len(curve_data)
                }
                
                curves.append(curve_info)
                
                print(f"\nCurve {len(curves)}:")
                print(f"  Duration: {curve_info['duration']:.1f} minutes")
                print(f"  Samples: {curve_info['samples']}")
                print(f"  Max temperature: {curve_info['max_temp']:.1f}°C")
                print(f"  Original timestamp range: {curve_info['start_time']:.1f}s - {curve_info['end_time']:.1f}s")
            
            # Move past this curve
            i = end_idx + 1
        
        if not curves:
            print("Warning: No valid baking curves found in data")
        else:
            print(f"\nTotal curves found: {len(curves)}")
        
        return curves
    
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
        """
        Validate sensor assignments using thermodynamic principles.
        Issues warnings if assignments seem incorrect.
        """
        # Get temperature columns
        temp_cols = [col for col in df.columns if col.startswith('T') and col[1:].isdigit()]
        if len(temp_cols) < 3:
            return
        
        # Calculate average temperatures for assigned sensors
        role_temps = {}
        for role in ['core', 'surface', 'ambient']:
            sensor = self.sensor_assignments.get(role)
            if sensor and sensor in temp_cols:
                role_temps[role] = {
                    'sensor': sensor,
                    'mean': df[sensor].mean(),
                    'max': df[sensor].max()
                }
        
        warnings = []
        
        # Check temperature ordering (core < surface < ambient)
        if 'core' in role_temps and 'surface' in role_temps:
            if role_temps['core']['mean'] > role_temps['surface']['mean']:
                warnings.append(f"⚠️  Core sensor ({role_temps['core']['sensor']}) has higher average temperature than surface sensor ({role_temps['surface']['sensor']})")
        
        if 'surface' in role_temps and 'ambient' in role_temps:
            if role_temps['surface']['mean'] > role_temps['ambient']['mean']:
                warnings.append(f"⚠️  Surface sensor ({role_temps['surface']['sensor']}) has higher average temperature than ambient sensor ({role_temps['ambient']['sensor']})")
        
        # Check heating rates in first 5 minutes
        mask = df['TimeMinutes'] <= 5.0
        if mask.sum() > 2:
            for role, expected_range in [('core', (0.2, 3)), ('surface', (2, 15)), ('ambient', (10, 50))]:
                if role in role_temps:
                    sensor = role_temps[role]['sensor']
                    temps = df.loc[mask, sensor]
                    times = df.loc[mask, 'TimeMinutes']
                    if len(temps) > 2:
                        coeffs = np.polyfit(times, temps, 1)
                        heat_rate = coeffs[0]
                        min_rate, max_rate = expected_range
                        if heat_rate < min_rate or heat_rate > max_rate:
                            warnings.append(f"⚠️  {role.capitalize()} sensor ({sensor}) has unusual heating rate: {heat_rate:.1f}°C/min (expected {min_rate}-{max_rate}°C/min)")
        
        # Check for sensor assignment consistency
        for role, info in [('core', 'core_info'), ('surface', 'surface_info'), ('ambient', 'ambient_info')]:
            if info in self.sensor_assignments:
                percentage = self.sensor_assignments[info].get('percentage', 100)
                if percentage < 80:
                    warnings.append(f"⚠️  {role.capitalize()} sensor assignment changes frequently ({percentage:.1f}% consistency) - probe may not be properly inserted")
        
        # Print warnings if any
        if warnings:
            print("\nSensor Assignment Validation Warnings:")
            for warning in warnings:
                print(f"  {warning}")
            
            # Run thermodynamic classification for comparison
            try:
                from ..data.thermodynamic_sensor_classifier import ThermodynamicSensorClassifier
                classifier = ThermodynamicSensorClassifier(df, temp_cols)
                thermo_assignments = classifier.classify_sensors()
                
                print("\n  Alternative thermodynamic classification suggests:")
                for role, sensors in thermo_assignments.items():
                    print(f"    {role.upper()}: {', '.join(sensors)}")
            except Exception as e:
                # Silently fail if thermodynamic classifier not available
                pass
    
    def _get_automatic_core_sensors(self, curve_index: int) -> List[str]:
        """Get automatically detected core sensors for a specific curve."""
        # Use curve-specific sensor assignments if available
        if hasattr(self, 'curve_sensor_assignments') and curve_index in self.curve_sensor_assignments:
            curve_assignments = self.curve_sensor_assignments[curve_index]
            # Parse core sensor assignment
            core_assignment = curve_assignments.get('core', '')
            if 'core_info' in curve_assignments:
                # Use all sensors from core_info if available
                all_sensors = curve_assignments['core_info'].get('all_sensors', {})
                return list(all_sensors.keys())
            elif core_assignment and core_assignment != 'Unknown':
                # Parse comma-separated list
                return [s.strip() for s in core_assignment.split(',')]
        
        # Fallback to position-based heuristic
        # Core sensors are the innermost consecutive sensors
        return ['T1', 'T2', 'T3', 'T4']
    
    def _get_automatic_surface_sensors(self, curve_index: int) -> List[str]:
        """Get automatically detected surface sensors for a specific curve."""
        # Use curve-specific sensor assignments if available
        if hasattr(self, 'curve_sensor_assignments') and curve_index in self.curve_sensor_assignments:
            curve_assignments = self.curve_sensor_assignments[curve_index]
            # Use primary surface sensor assignment
            surface_assignment = curve_assignments.get('surface', '')
            if surface_assignment and surface_assignment != 'Unknown':
                # Return as list for compatibility
                return [surface_assignment]
        
        # Fallback to position-based heuristic
        # Surface is a single sensor at the interface (between core and ambient)
        return ['T7']
    
    def _get_automatic_ambient_sensors(self, curve_index: int) -> List[str]:
        """Get automatically detected ambient sensors for a specific curve."""
        # Use curve-specific sensor assignments if available
        if hasattr(self, 'curve_sensor_assignments') and curve_index in self.curve_sensor_assignments:
            curve_assignments = self.curve_sensor_assignments[curve_index]
            # Use primary ambient sensor assignment
            ambient_assignment = curve_assignments.get('ambient', '')
            if ambient_assignment and ambient_assignment != 'Unknown':
                # Return as list (ambient could be multiple sensors above surface)
                return [ambient_assignment]
        
        # Fallback - ambient is the outermost sensor(s)
        return ['T8']
    
    def _apply_standard_columns(self, df: pd.DataFrame, curve_index: int) -> None:
        """Single canonical writer of CoreTemperature / SurfaceTemperature / AmbientTemperature.

        Layering (matches CLAUDE.md):
          1. Virtual* firmware channels (or *Average / raw-T fallbacks).
          2. Physics-based surface correction — preserved when
             curve_sensor_assignments[curve_index]['physics_corrected'] is True.
          3. Manual overrides from self._sensor_overrides[curve_index] — win
             over physics correction (the UI rule: user > physics > firmware).
        """
        if df is None:
            return

        curve_assignments = self.curve_sensor_assignments.get(curve_index, {})
        overrides = self._sensor_overrides.get(curve_index, {})

        # --- CoreTemperature ---
        core_override = overrides.get('core')
        if core_override and core_override in df.columns:
            df['CoreTemperature'] = df[core_override]
        elif 'VirtualCoreTemperature' in df.columns:
            df['CoreTemperature'] = df['VirtualCoreTemperature']
        elif 'CoreAverage' in df.columns:
            df['CoreTemperature'] = df['CoreAverage']
        elif all(col in df.columns for col in ['T1', 'T2', 'T3', 'T4']):
            df['CoreTemperature'] = df[['T1', 'T2', 'T3', 'T4']].mean(axis=1)

        # --- SurfaceTemperature ---
        # Override wins; else physics-corrected sensor wins; else firmware virtual.
        surface_override = overrides.get('surface')
        physics_surface = (
            curve_assignments.get('surface')
            if curve_assignments.get('physics_corrected')
            else None
        )
        if surface_override and surface_override in df.columns:
            df['SurfaceTemperature'] = df[surface_override]
        elif physics_surface and physics_surface in df.columns:
            df['SurfaceTemperature'] = df[physics_surface]
        elif 'VirtualSurfaceTemperature' in df.columns:
            df['SurfaceTemperature'] = df['VirtualSurfaceTemperature']
        elif 'SurfaceAverage' in df.columns:
            df['SurfaceTemperature'] = df['SurfaceAverage']
        elif all(col in df.columns for col in ['T7', 'T8']):
            df['SurfaceTemperature'] = df[['T7', 'T8']].mean(axis=1)

        # --- AmbientTemperature ---
        # A surface override implies the probe geometry changed, so recompute
        # ambient from the inferred ambient sensors rather than the firmware pick.
        if surface_override:
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
    required_cols = ['Timestamp', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
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
    temp_cols = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
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