"""Central helpers for selecting the canonical column name when a DataFrame
may carry either the new standardised columns (e.g. CoreTemperature) or the
legacy averaged columns (e.g. CoreAverage).

Single source of truth for this decision - all code that previously inlined
the present-wins ternary (picking CoreTemperature when present, else
CoreAverage) must route through :func:`get_core_temperature_column`.
"""
import pandas as pd


def get_core_temperature_column(df: pd.DataFrame) -> str:
    """Return the column name to read core temperature from.

    Present-wins: if both ``CoreTemperature`` and ``CoreAverage`` are present,
    ``CoreTemperature`` takes precedence to preserve physics corrections and
    manual overrides that the legacy averaged column does not track.
    """
    if 'CoreTemperature' in df.columns:
        return 'CoreTemperature'
    if 'CoreAverage' in df.columns:
        return 'CoreAverage'
    raise KeyError(
        "Neither 'CoreTemperature' nor 'CoreAverage' column present in DataFrame"
    )
