#!/usr/bin/env python3
"""Test zone comparison visualization to debug stacked vs grouped bars issue."""

import pandas as pd
import plotly.graph_objects as go
from src.visualization.plots import ThermalPlotter

# Create test data similar to what CurveComparison would produce
test_data = pd.DataFrame({
    'Curve': ['ProbeData_1000BA3C_2025-05-30 17_59_37 (2)', 'ProbeData_100098DE_2025-05-30 13_51_07'],
    'Yeast Kill': [0.8, 1.2],
    'Starch Gelatinization': [5.2, 4.8],
    'Protein Denaturation': [4.8, 5.1],
    'Crust Formation': [16.8, 15.2],
    'Maillard Reaction': [17.9, 16.5],
    'Caramelization': [0.0, 1.1],
    'Target Core Temperature': [11.2, 10.8]
})

print("Test data:")
print(test_data)
print()

# Create plotter and generate visualization
plotter = ThermalPlotter()
fig = plotter.plot_zone_duration_comparison(test_data)

# Check the figure structure
print("Figure data traces:", len(fig.data))
print("Barmode in layout:", fig.layout.barmode)
print()

# Print trace info
for i, trace in enumerate(fig.data):
    print(f"Trace {i}: {trace.name}")
    print(f"  X values: {trace.x}")
    print(f"  Y values: {trace.y}")
    print()

# Save to HTML for visual inspection
fig.write_html("zone_comparison_test.html")
print("Saved visualization to zone_comparison_test.html")