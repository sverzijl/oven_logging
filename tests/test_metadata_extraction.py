"""Tests for metadata extraction and probe naming functionality."""

import pytest
import pandas as pd
from datetime import datetime
from io import StringIO
from src.data.loader import ThermalProfileLoader
from src.analysis.curve_comparison import CurveComparison


class TestMetadataExtraction:
    """Test metadata extraction from CSV files."""
    
    def test_parse_metadata_from_csv(self):
        """Test parsing metadata from CSV header."""
        csv_content = """Combustion Inc. Probe Data
App: iOS Prod app 2.1.1
CSV version: 4
Probe S/N: 100098DE
Probe FW version: v1.5.4
Probe HW revision: v1.1-A1
Framework: iOS
Sample Period: 5000
Created: 2025-05-30 13:51:07

Timestamp,SessionID,SequenceNumber,T1,T2,T3,T4,T5,T6,T7,T8,VirtualCoreTemperature,VirtualSurfaceTemperature,VirtualAmbientTemperature,EstimatedCoreTemperature,PredictionSetPoint,VirtualCoreSensor,VirtualSurfaceSensor,VirtualAmbientSensor,PredictionState,PredictionMode,PredictionType,PredictionValueSeconds
0.000,961742059,0,22.85,22.85,22.85,22.85,23.20,23.35,23.25,23.20,22.85,22.85,23.35,22.80,0.00,T1,T4,T6,Probe Not Inserted,None,None,131071
5.000,961742059,1,22.85,23.35,23.75,24.35,23.80,24.10,23.90,23.80,22.85,24.35,24.10,22.80,0.00,T1,T4,T6,Probe Not Inserted,None,None,131071
"""
        
        loader = ThermalProfileLoader()
        metadata = loader._parse_metadata_from_content(csv_content)
        
        assert metadata['Probe S/N'] == '100098DE'
        assert metadata['Created'] == '2025-05-30 13:51:07'
        assert metadata['sample_period_ms'] == 5000
        assert metadata['sample_period_s'] == 5.0
        assert isinstance(metadata['created_datetime'], datetime)
        assert metadata['created_datetime'].strftime('%H:%M') == '13:51'
        
    def test_short_curve_name_generation(self):
        """Test generation of short curve names."""
        # Test with metadata
        curve1 = {
            'filename': 'ProbeData_100098DE_2025-05-30 13_51_07.csv',
            'metadata': {
                'Probe S/N': '100098DE',
                'created_datetime': datetime(2025, 5, 30, 13, 51, 7)
            },
            'file_curve_index': 0
        }
        
        # Test without metadata (filename parsing)
        curve2 = {
            'filename': 'ProbeData_1000BA3C_2025-05-30 09_46_16.csv',
            'metadata': {},
            'file_curve_index': 0
        }
        
        # Test multi-curve file
        curve3 = {
            'filename': 'ProbeData_1000F3C1_2025-05-23 09_11_59.csv',
            'metadata': {
                'Probe S/N': '1000F3C1',
                'created_datetime': datetime(2025, 5, 23, 9, 11, 59)
            },
            'file_curve_index': 1
        }
        
        # Create comparison with mock curves
        comparison = CurveComparison([
            {'curve_data': {'data': pd.DataFrame()}, 'sensor_roles': {}, 
             'metadata': curve1['metadata'], 'filename': curve1['filename'], 
             'file_curve_index': curve1['file_curve_index']},
            {'curve_data': {'data': pd.DataFrame()}, 'sensor_roles': {}, 
             'metadata': curve2['metadata'], 'filename': curve2['filename'],
             'file_curve_index': curve2['file_curve_index']}
        ])
        
        # Test short names
        short_name1 = comparison._get_short_curve_name(curve1, 0)
        assert short_name1 == '98DE_13:51'
        
        short_name2 = comparison._get_short_curve_name(curve2, 1)
        assert short_name2 == 'BA3C_09:46'
        
        # Test multi-curve naming
        comparison_multi = CurveComparison([
            {'curve_data': {'data': pd.DataFrame()}, 'sensor_roles': {}, 
             'metadata': curve3['metadata'], 'filename': curve3['filename'], 
             'file_curve_index': 0},
            {'curve_data': {'data': pd.DataFrame()}, 'sensor_roles': {}, 
             'metadata': curve3['metadata'], 'filename': curve3['filename'],
             'file_curve_index': 1}
        ])
        
        # Update curves to simulate multi-curve file
        comparison_multi.curves = [
            {'filename': curve3['filename'], 'file_curve_index': 0, 'metadata': curve3['metadata']},
            {'filename': curve3['filename'], 'file_curve_index': 1, 'metadata': curve3['metadata']}
        ]
        
        short_name3 = comparison_multi._get_short_curve_name(
            {'filename': curve3['filename'], 'file_curve_index': 0, 'metadata': curve3['metadata']}, 
            0
        )
        short_name4 = comparison_multi._get_short_curve_name(
            {'filename': curve3['filename'], 'file_curve_index': 1, 'metadata': curve3['metadata']}, 
            1
        )
        
        # Should have curve numbers for multi-curve files
        assert '_C1' in short_name3 or '_C2' in short_name3
        
    def test_fallback_naming(self):
        """Test fallback naming when metadata is unavailable."""
        curve_no_metadata = {
            'filename': 'unknown_format.csv',
            'metadata': {},
            'file_curve_index': 0
        }
        
        comparison = CurveComparison([
            {'curve_data': {'data': pd.DataFrame()}, 'sensor_roles': {}, 
             'metadata': {}, 'filename': 'unknown_format.csv', 
             'file_curve_index': 0}
        ])
        
        short_name = comparison._get_short_curve_name(curve_no_metadata, 0)
        assert short_name == 'Probe 1'