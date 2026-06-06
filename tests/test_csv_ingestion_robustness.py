"""CSV ingestion robustness tests (fix/deep-review, Finding 7 + 8).

Covers the consolidated metadata parser and the small-probe (<8 sensor)
ingestion path:

* Trailing commas on Probe S/N / Created / Sample Period are stripped on
  EVERY value (the double-comma header artefact some exports produce).
* A non-integer (float-formatted) Sample Period falls back to the documented
  5000 ms default instead of raising.
* A degree-sign byte encoded as cp1252/latin-1 (not UTF-8) decodes cleanly
  from both a buffer and a file path.
* A file with fewer than 8 sensors does not KeyError in get_sensor_data and
  the inferred sensor names are clamped to columns actually present.
"""

from __future__ import annotations

import io
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader  # noqa: E402


# A 10-line metadata header with trailing commas (double-comma artefact) on
# Probe S/N and Created, plus a degree sign in one of the header values, then
# a small data table.
def _header_with_trailing_commas(sample_period: str = "5000") -> str:
    return (
        "Combustion Inc. Probe Data\n"
        "App: iOS Prod app 2.1.1\n"
        "CSV version: 4\n"
        "Probe S/N: 100098DE,\n"
        "Probe FW version: v1.5.4\n"
        "Probe HW revision: v1.1-A1\n"
        "Framework: iOS\n"
        f"Sample Period: {sample_period},\n"
        "Created: 2025-05-30 13:51:07,\n"
        "Note: ambient 22°C\n"
        "Timestamp,T1,T2,T3,T4,T5,T6,T7,T8,VirtualCoreTemperature\n"
        "0.000,22.0,22.1,22.2,22.3,22.4,22.5,22.6,22.7,22.0\n"
        "5.000,23.0,23.1,23.2,23.3,23.4,23.5,23.6,23.7,23.0\n"
    )


class TestTrailingCommaStripping:
    """Finding 7a: trailing commas corrupt Probe S/N and Created."""

    def test_probe_sn_and_created_stripped_from_content(self):
        loader = ThermalProfileLoader()
        md = loader._parse_metadata_from_content(_header_with_trailing_commas())
        assert md["Probe S/N"] == "100098DE"
        assert md["Created"] == "2025-05-30 13:51:07"
        assert md["sample_period_ms"] == 5000
        # created_datetime must parse despite the comma having been on the line.
        assert md["created_datetime"] is not None
        assert md["created_datetime"].strftime("%H:%M") == "13:51"


class TestSamplePeriodFallback:
    """Finding 7b: non-int Sample Period must fall back to 5000, not raise."""

    def test_float_sample_period_does_not_raise(self):
        loader = ThermalProfileLoader()
        md = loader._parse_metadata_from_content(
            _header_with_trailing_commas(sample_period="5000.0")
        )
        # int(float("5000.0")) == 5000
        assert md["sample_period_ms"] == 5000

    def test_garbage_sample_period_falls_back_to_5000(self):
        loader = ThermalProfileLoader()
        md = loader._parse_metadata_from_content(
            _header_with_trailing_commas(sample_period="not-a-number")
        )
        assert md["sample_period_ms"] == 5000
        assert md["sample_period_s"] == 5.0


class TestEncodingRobustness:
    """Finding 7c: hard-coded UTF-8 decode crashes on cp1252/latin-1."""

    def test_cp1252_buffer_with_degree_sign_parses(self):
        loader = ThermalProfileLoader()
        content = _header_with_trailing_commas()
        raw = content.encode("cp1252")  # degree sign is 0xB0, invalid UTF-8
        buf = io.BytesIO(raw)
        data, md = loader.load_csv(file_buffer=buf)
        assert md["Probe S/N"] == "100098DE"
        assert data is not None

    def test_cp1252_file_path_with_degree_sign_parses(self, tmp_path):
        loader = ThermalProfileLoader()
        content = _header_with_trailing_commas()
        p = tmp_path / "cp1252_probe.csv"
        p.write_bytes(content.encode("cp1252"))
        data, md = loader.load_csv(file_path=str(p))
        assert md["Probe S/N"] == "100098DE"
        assert md["created_datetime"] is not None
        assert data is not None


class TestConsolidatedParserParity:
    """Finding 7 DRY: the file-path and content entry points must agree, and
    the consolidated helper must exist."""

    def test_parse_metadata_lines_helper_exists(self):
        loader = ThermalProfileLoader()
        assert hasattr(loader, "_parse_metadata_lines")

    def test_buffer_parser_removed(self):
        loader = ThermalProfileLoader()
        assert not hasattr(loader, "_parse_metadata_from_buffer")

    def test_file_path_and_content_parsers_agree(self, tmp_path):
        loader = ThermalProfileLoader()
        content = _header_with_trailing_commas()
        p = tmp_path / "probe.csv"
        p.write_text(content, encoding="utf-8")
        md_path = loader._parse_metadata(str(p))
        md_content = loader._parse_metadata_from_content(content)
        for key in ("Probe S/N", "Created", "sample_period_ms"):
            assert md_path[key] == md_content[key]


def _small_probe_df(n_sensors: int = 6, n: int = 120) -> pd.DataFrame:
    """Build a cleaned-style df with only n_sensors temperature columns."""
    data = {
        "Timestamp": np.arange(n) * 5.0,
        "TimeMinutes": np.arange(n) * 5.0 / 60.0,
    }
    for i in range(1, n_sensors + 1):
        data[f"T{i}"] = np.linspace(25, 95, n)
    data["VirtualCoreTemperature"] = data["T1"]
    data["CoreTemperature"] = data["T1"]
    return pd.DataFrame(data)


class TestFewerThanEightSensors:
    """Finding 8: <8-sensor files must not KeyError in get_sensor_data."""

    def test_get_sensor_data_does_not_keyerror_with_six_sensors(self):
        loader = ThermalProfileLoader()
        df = _small_probe_df(n_sensors=6)
        loader.data = df
        out = loader.get_sensor_data()
        # Returns only columns that actually exist — no phantom T7/T8.
        assert "T7" not in out.columns
        assert "T8" not in out.columns
        assert {"Timestamp", "TimeMinutes", "T1", "T6"}.issubset(out.columns)

    def test_get_sensor_data_includes_present_sensors_only(self):
        loader = ThermalProfileLoader()
        df = _small_probe_df(n_sensors=4)
        loader.data = df
        out = loader.get_sensor_data()
        present = [c for c in out.columns if len(c) == 2 and c[0] == "T" and c[1].isdigit()]
        assert set(present) == {"T1", "T2", "T3", "T4"}
