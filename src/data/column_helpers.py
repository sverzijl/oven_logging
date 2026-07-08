"""Central helpers for selecting the canonical column name when a DataFrame
may carry either the new standardised columns (e.g. CoreTemperature) or the
legacy averaged columns (e.g. CoreAverage).

Single source of truth for this decision - all code that previously inlined
the present-wins ternary (picking CoreTemperature when present, else
CoreAverage) must route through :func:`get_core_temperature_column`.
"""
import pandas as pd

_T1_T4 = ['T1', 'T2', 'T3', 'T4']


def get_core_temperature_column(df: pd.DataFrame) -> str:
    """Return the column name to read core temperature from.

    Present-wins: if both ``CoreTemperature`` and ``CoreAverage`` are present,
    ``CoreTemperature`` takes precedence to preserve physics corrections and
    manual overrides that the legacy averaged column does not track.

    DELIBERATELY different precedence from :func:`resolve_core_temperature_series`
    — do NOT "unify" the two.  This helper serves the **analysis / visualization**
    stage, which reads the *standardised* ``CoreTemperature`` column produced
    AFTER sensor-role classification + manual overrides, so it must prefer it.
    :func:`resolve_core_temperature_series` serves the **detection** stage, which
    runs on the *raw firmware* ``VirtualCoreTemperature`` channel BEFORE any
    role identification exists, so it prefers that.  They are two correct answers
    for two different pipeline stages.
    """
    if 'CoreTemperature' in df.columns:
        return 'CoreTemperature'
    if 'CoreAverage' in df.columns:
        return 'CoreAverage'
    raise KeyError(
        "Neither 'CoreTemperature' nor 'CoreAverage' column present in DataFrame"
    )


def resolve_core_temperature_series(df: pd.DataFrame) -> pd.Series:
    """Return a core-temperature Series, resolving the full fallback chain.

    Precedence: ``VirtualCoreTemperature`` → ``CoreTemperature`` → ``CoreAverage``
    → mean of ``T1``..``T4``.  Raises :class:`KeyError` when no fallback is
    available.  Centralises the pattern that was previously inlined at several
    call sites in ``loader.py``.

    DELIBERATELY prefers the raw firmware ``VirtualCoreTemperature`` channel —
    this is the **detection**-stage resolver (curve-boundary detector +
    ``build_curve_descriptor``), which must read the raw channel BEFORE
    sensor-role classification / overrides exist.  Contrast
    :func:`get_core_temperature_column`, the analysis-stage helper that prefers
    the standardised ``CoreTemperature``.  Do NOT "unify" their precedence — see
    that function's docstring.
    """
    if 'VirtualCoreTemperature' in df.columns:
        return df['VirtualCoreTemperature']
    if 'CoreTemperature' in df.columns:
        return df['CoreTemperature']
    if 'CoreAverage' in df.columns:
        return df['CoreAverage']
    if all(col in df.columns for col in _T1_T4):
        return df[_T1_T4].mean(axis=1)
    raise KeyError(
        "No core-temperature source available: need one of "
        "VirtualCoreTemperature, CoreTemperature, CoreAverage, or T1..T4"
    )
