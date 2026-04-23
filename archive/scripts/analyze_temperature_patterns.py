#!/usr/bin/env python3
"""Analyze temperature patterns in probe data to identify curve boundaries."""

import pandas as pd
import numpy as np

def analyze_temperature_patterns(file_path):
    """Analyze temperature data to identify potential curve boundaries."""
    
    # Read the CSV file, skipping header rows
    df = pd.read_csv(file_path, skiprows=10)
    
    print(f"Total data points: {len(df)}")
    print(f"Time range: {df['Timestamp'].min():.1f}s to {df['Timestamp'].max():.1f}s")
    print(f"Duration: {(df['Timestamp'].max() - df['Timestamp'].min()) / 60:.1f} minutes\n")
    
    # Analyze PredictionState transitions
    print("PredictionState Transitions:")
    state_changes = df[df['PredictionState'] != df['PredictionState'].shift(1)]
    for idx, row in state_changes.iterrows():
        print(f"  Time {row['Timestamp']:.1f}s (row {idx+12}): {row['PredictionState']}")
    
    # Analyze VirtualCoreTemperature patterns
    print("\nCore Temperature Analysis:")
    df['CoreTempChange'] = df['VirtualCoreTemperature'].diff()
    df['CoreTempChangeRate'] = df['CoreTempChange'] * 12  # Per minute (5s intervals)
    
    # Find maximum core temperature
    max_idx = df['VirtualCoreTemperature'].idxmax()
    max_temp = df.loc[max_idx, 'VirtualCoreTemperature']
    max_time = df.loc[max_idx, 'Timestamp']
    print(f"  Peak temperature: {max_temp:.2f}°C at {max_time:.1f}s (row {max_idx+12})")
    
    # Look for significant temperature drops (>10°C)
    print("\nSignificant Temperature Drops (>10°C):")
    large_drops = df[df['CoreTempChange'] < -10]
    for idx, row in large_drops.iterrows():
        prev_temp = df.loc[idx-1, 'VirtualCoreTemperature']
        curr_temp = row['VirtualCoreTemperature']
        print(f"  Time {row['Timestamp']:.1f}s (row {idx+12}): {prev_temp:.1f}°C → {curr_temp:.1f}°C (drop of {abs(row['CoreTempChange']):.1f}°C)")
    
    # Look for rapid temperature rises (>5°C in 5s)
    print("\nRapid Temperature Rises (>5°C in 5s):")
    rapid_rises = df[df['CoreTempChange'] > 5]
    for idx, row in rapid_rises.iterrows():
        prev_temp = df.loc[idx-1, 'VirtualCoreTemperature'] if idx > 0 else 0
        curr_temp = row['VirtualCoreTemperature']
        print(f"  Time {row['Timestamp']:.1f}s (row {idx+12}): {prev_temp:.1f}°C → {curr_temp:.1f}°C (rise of {row['CoreTempChange']:.1f}°C)")
    
    # Analyze temperature after the major drop
    if len(large_drops) > 0:
        drop_idx = large_drops.index[0]
        print(f"\nTemperature behavior after major drop at {df.loc[drop_idx, 'Timestamp']:.1f}s:")
        
        # Check if temperature rises again after the drop
        post_drop_data = df[df.index > drop_idx]
        if len(post_drop_data) > 0:
            min_after_drop = post_drop_data['VirtualCoreTemperature'].min()
            min_idx = post_drop_data['VirtualCoreTemperature'].idxmin()
            print(f"  Minimum temperature after drop: {min_after_drop:.1f}°C at {df.loc[min_idx, 'Timestamp']:.1f}s")
            
            # Check for temperature rises after the minimum
            post_min_data = df[df.index > min_idx]
            if len(post_min_data) > 0:
                subsequent_rises = post_min_data[post_min_data['CoreTempChange'] > 2]
                if len(subsequent_rises) > 0:
                    print("  Subsequent temperature rises found:")
                    for idx, row in subsequent_rises.iterrows():
                        print(f"    Time {row['Timestamp']:.1f}s: +{row['CoreTempChange']:.1f}°C")
                else:
                    print("  No significant temperature rises after the drop - likely end of baking")
    
    # Calculate average temperatures in different phases
    print("\nTemperature Phases:")
    not_inserted = df[df['PredictionState'] == 'Probe Not Inserted']
    if len(not_inserted) > 0:
        print(f"  Probe Not Inserted: avg {not_inserted['VirtualCoreTemperature'].mean():.1f}°C")
    
    inserted = df[df['PredictionState'] == 'Probe Inserted']
    if len(inserted) > 0:
        print(f"  Probe Inserted: avg {inserted['VirtualCoreTemperature'].mean():.1f}°C")
    
    cooking = df[df['PredictionState'] == 'Cooking']
    if len(cooking) > 0:
        print(f"  Cooking: avg {cooking['VirtualCoreTemperature'].mean():.1f}°C, max {cooking['VirtualCoreTemperature'].max():.1f}°C")
    
    return df

if __name__ == "__main__":
    file_path = "/home/sverzijl/combustion_display/ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
    df = analyze_temperature_patterns(file_path)