"""Contract test for the future ``get_core_temperature_column`` helper.

Captain Diligent (T6) will extract this helper to eliminate the
``CoreTemperature`` / ``CoreAverage`` present-wins idiom that is duplicated
across 21 call sites. The helper does not exist yet, so this test MUST FAIL
on HEAD with ``ImportError`` / ``ModuleNotFoundError`` and start passing
once the helper lands at ``src/data/column_helpers.py``.

Contract (locks in the existing 21-site behaviour):
    * DF with ``CoreTemperature`` only -> returns ``'CoreTemperature'``.
    * DF with ``CoreAverage`` only -> returns ``'CoreAverage'``.
    * DF with both -> returns ``'CoreTemperature'`` (present wins).
    * DF with neither -> raises ``KeyError`` naming both candidates.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.column_helpers import get_core_temperature_column  # noqa: E402


@pytest.mark.parametrize(
    "columns,expected",
    [
        (['CoreTemperature', 'T1'], 'CoreTemperature'),
        (['CoreAverage', 'T1'], 'CoreAverage'),
        (['CoreTemperature', 'CoreAverage', 'T1'], 'CoreTemperature'),
    ],
    ids=["core_temperature_only", "core_average_only", "both_present_wins"],
)
def test_get_core_temperature_column_returns_expected(columns, expected):
    df = pd.DataFrame({c: [1.0, 2.0, 3.0] for c in columns})
    assert get_core_temperature_column(df) == expected


def test_get_core_temperature_column_raises_when_neither_present():
    df = pd.DataFrame({'T1': [1.0, 2.0, 3.0]})
    with pytest.raises(KeyError) as excinfo:
        get_core_temperature_column(df)
    # Error must name both candidates so callers know what's missing.
    msg = str(excinfo.value)
    assert 'CoreTemperature' in msg
    assert 'CoreAverage' in msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
