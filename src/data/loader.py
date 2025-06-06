"""Data loading and parsing utilities for thermal profile CSV files."""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, Union
import re
from datetime import datetime
import io


class ThermalProfileLoader:
    """Load and parse thermal profile CSV files from Combustion Inc. probes."""
    
    def __init__(self):
        self.metadata = {}
        self.data = None
        self.sensor_assignments = {}
        self.all_curves = []  # Store all detected curves
        self.current_curve_index = 0  # Track which curve is currently selected
        
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
        
        # Identify sensor roles and create temperature columns
        df = self._identify_sensor_roles(df)
        
        # Note: Curve extraction is now done separately in load_csv
        # to support multiple curves
        
        return df
    
    def _identify_sensor_roles(self, df: pd.DataFrame) -> pd.DataFrame:
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
        
        if all(col in df.columns for col in virtual_cols + assignment_cols):
            # Use the probe's intelligent sensor selection
            df['CoreTemperature'] = df['VirtualCoreTemperature']
            df['SurfaceTemperature'] = df['VirtualSurfaceTemperature']
            df['AmbientTemperature'] = df['VirtualAmbientTemperature']
            
            # Track most common sensor assignments for each role
            if len(df) > 0:
                self.sensor_assignments = {
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
                            self.sensor_assignments[f'{role}_info'] = {
                                'primary': primary,
                                'percentage': percentage,
                                'all_sensors': counts.to_dict()
                            }
            
            print(f"Using virtual sensor assignments from CSV:")
            print(f"  Core: {self.sensor_assignments.get('core', 'Unknown')} ({self.sensor_assignments.get('core_info', {}).get('percentage', 0):.1f}% of readings)")
            print(f"  Surface: {self.sensor_assignments.get('surface', 'Unknown')} ({self.sensor_assignments.get('surface_info', {}).get('percentage', 0):.1f}% of readings)")
            print(f"  Ambient: {self.sensor_assignments.get('ambient', 'Unknown')} ({self.sensor_assignments.get('ambient_info', {}).get('percentage', 0):.1f}% of readings)")
            
        else:
            # Method 2: Dynamic classification based on temperature patterns
            print("Virtual sensor data not available, using dynamic classification")
            df = self._classify_sensors_dynamically(df)
        
        # For backward compatibility, also create the old average columns
        # but mark them as deprecated
        if all(col in df.columns for col in ['T1', 'T2', 'T3', 'T4']):
            df['CoreAverage'] = df[['T1', 'T2', 'T3', 'T4']].mean(axis=1)
        if all(col in df.columns for col in ['T7', 'T8']):
            df['SurfaceAverage'] = df[['T7', 'T8']].mean(axis=1)
        
        return df
    
    def _classify_sensors_dynamically(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dynamically classify sensors based on temperature patterns.
        
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
        
        # Store assignments
        self.sensor_assignments = {
            'core': ', '.join(core_sensors),
            'surface': ', '.join(surface_sensors),
            'ambient': ', '.join(ambient_sensors),
            'method': 'dynamic_classification'
        }
        
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
    
    def _extract_all_baking_curves_old(self, df: pd.DataFrame) -> list:
        """
        Extract all baking curves from the dataset.
        
        Returns:
            List of dictionaries, each containing:
            - 'data': DataFrame for the curve
            - 'start_idx': Start index in original data
            - 'end_idx': End index in original data
            - 'start_time': Start timestamp
            - 'end_time': End timestamp
            - 'duration': Duration in minutes
            - 'max_temp': Maximum core temperature
            - 'curve_number': Curve number (1-based)
        """
        curves = []
        core_col = 'CoreTemperature' if 'CoreTemperature' in df.columns else 'CoreAverage'
        
        if core_col not in df.columns:
            print("Warning: No core temperature column found")
            return curves
        
        # Parameters for curve detection
        MIN_CURVE_DURATION = 60  # Minimum 5 minutes at 5-second intervals
        MIN_BAKING_TEMP = 80     # Minimum peak temperature for valid baking
        TEMP_RISE_THRESHOLD = 5  # Temperature rise to detect start
        TEMP_DROP_THRESHOLD = 20 # Temperature drop to detect curve separation
        COOLING_RATE_THRESHOLD = -1  # °C per minute
        
        # Find all potential curve starts and ends
        curve_segments = []
        i = 0
        
        while i < len(df):
            # Find start of next curve
            start_idx = None
            
            # Method 1: Use PredictionState if available
            if 'PredictionState' in df.columns:
                # Look for transition from "Probe Not Inserted" to other states
                for j in range(i, len(df)):
                    if (j > 0 and 
                        df.iloc[j-1]['PredictionState'] == 'Probe Not Inserted' and 
                        df.iloc[j]['PredictionState'] != 'Probe Not Inserted'):
                        start_idx = j
                        break
            
            # Method 2: Detect temperature rise
            if start_idx is None:
                for j in range(i, len(df) - 1):
                    if df[core_col].iloc[j+1] - df[core_col].iloc[j] > TEMP_RISE_THRESHOLD:
                        start_idx = j
                        break
            
            if start_idx is None:
                # No more curves found
                break
            
            # Find end of this curve
            # Look for peak and subsequent drop
            peak_idx = start_idx
            peak_temp = df[core_col].iloc[start_idx]
            
            for j in range(start_idx, len(df)):
                if df[core_col].iloc[j] > peak_temp:
                    peak_temp = df[core_col].iloc[j]
                    peak_idx = j
            
            # Find significant temperature drop after peak
            end_idx = None
            for j in range(peak_idx, len(df)):
                temp_drop = peak_temp - df[core_col].iloc[j]
                
                if temp_drop > TEMP_DROP_THRESHOLD:
                    # Validate with cooling rate if possible
                    if j < len(df) - 5:
                        cooling_rate = (df[core_col].iloc[j:j+5].diff().mean() * 12)  # Per minute
                        if cooling_rate < COOLING_RATE_THRESHOLD:
                            end_idx = j
                            break
                    else:
                        end_idx = j
                        break
            
            if end_idx is None:
                # No clear end found, use end of data
                end_idx = len(df) - 1
            
            # Validate and store curve segment
            curve_length = end_idx - start_idx + 1
            if curve_length >= MIN_CURVE_DURATION and peak_temp >= MIN_BAKING_TEMP:
                curve_segments.append({
                    'start_idx': start_idx,
                    'end_idx': end_idx,
                    'peak_temp': peak_temp,
                    'peak_idx': peak_idx
                })
            
            # Move to search for next curve
            i = end_idx + 1
        
        # Process each valid curve segment
        for idx, segment in enumerate(curve_segments):
            # Extract curve data
            curve_data = df.iloc[segment['start_idx']:segment['end_idx']+1].copy()
            
            # Reset timestamps
            curve_data['Timestamp'] = curve_data['Timestamp'] - curve_data['Timestamp'].iloc[0]
            curve_data['TimeMinutes'] = curve_data['Timestamp'] / 60.0
            
            # Reset index
            curve_data = curve_data.reset_index(drop=True)
            
            # Calculate curve metadata
            curve_info = {
                'data': curve_data,
                'start_idx': segment['start_idx'],
                'end_idx': segment['end_idx'],
                'start_time': df['Timestamp'].iloc[segment['start_idx']],
                'end_time': df['Timestamp'].iloc[segment['end_idx']],
                'duration': curve_data['TimeMinutes'].max(),
                'max_temp': segment['peak_temp'],
                'curve_number': idx + 1,
                'samples': len(curve_data)
            }
            
            curves.append(curve_info)
            
            print(f"\nCurve {idx + 1}:")
            print(f"  Duration: {curve_info['duration']:.1f} minutes")
            print(f"  Samples: {curve_info['samples']}")
            print(f"  Max temperature: {curve_info['max_temp']:.1f}°C")
            print(f"  Original timestamp range: {curve_info['start_time']:.1f}s - {curve_info['end_time']:.1f}s")
        
        if not curves:
            print("Warning: No valid baking curves found in data")
        else:
            print(f"\nTotal curves found: {len(curves)}")
        
        return curves
    
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
            
            # Find curve peak
            peak_idx = start_idx
            peak_temp = df.iloc[start_idx][core_col]
            
            for j in range(start_idx + 1, len(df)):
                if df.iloc[j][core_col] > peak_temp:
                    peak_temp = df.iloc[j][core_col]
                    peak_idx = j
            
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
                
                # End condition 3: Major temperature drop (>40°C) from peak
                if peak_temp - temp > 40 and j > peak_idx + 10:
                    # Verify this is a real drop, not noise
                    if j + 3 < len(df):
                        future_temps = df[core_col].iloc[j:j+3]
                        if future_temps.max() < temp + 5:  # Stays low
                            # Find the start of the rapid drop
                            for k in range(j, peak_idx, -1):
                                if k > 0:
                                    drop_rate = df.iloc[k-1][core_col] - df.iloc[k][core_col]
                                    if drop_rate > 10:  # 10°C drop in one interval
                                        end_idx = k - 1
                                        break
                            if end_idx is None:
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
        return self.data
    
    def get_current_curve_info(self) -> dict:
        """Get metadata about the current curve."""
        if self.all_curves and 0 <= self.current_curve_index < len(self.all_curves):
            return self.all_curves[self.current_curve_index]
        return None
    

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