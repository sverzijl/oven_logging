"""Figure-hash baseline capture for refactor parity checks.

Drives ``ThermalPlotter.plot_temperature_profile`` for every root-level
``ProbeData_*.csv`` across every curve the loader detects, serializes each
Plotly figure via ``fig.to_json()``, and SHA-256 hashes the result. The hash
file at ``figure-hashes.json`` is the reference that Captains Resolute (T4)
and Dreadnought (T7) re-run post-refactor to prove figures are byte-identical
to HEAD.

Run from the oven_logging repo root:

    python .nelson/missions/2026-04-23_071618_4b7f0acb/baseline/capture_baseline.py
"""

import glob
import hashlib
import json
import os
import sys
from datetime import datetime, timezone


THIS_FILE = os.path.abspath(__file__)
BASELINE_DIR = os.path.dirname(THIS_FILE)
MISSION_DIR = os.path.dirname(BASELINE_DIR)
NELSON_DIR = os.path.dirname(os.path.dirname(MISSION_DIR))
REPO_ROOT = os.path.dirname(NELSON_DIR)

sys.path.insert(0, REPO_ROOT)

from src.data.loader import ThermalProfileLoader  # noqa: E402
from src.visualization.plots import ThermalPlotter  # noqa: E402


def _hash_figure(fig) -> str:
    payload = fig.to_json()
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def capture(output_path: str) -> dict:
    plotter = ThermalPlotter()
    fixtures_glob = os.path.join(REPO_ROOT, 'ProbeData_*.csv')
    fixture_paths = sorted(glob.glob(fixtures_glob))
    assert fixture_paths, f"no fixtures matched {fixtures_glob}"

    results = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'repo_root': REPO_ROOT,
        'fixtures': {},
    }

    for fixture_path in fixture_paths:
        fixture_name = os.path.basename(fixture_path)
        loader = ThermalProfileLoader()
        loader.load_csv(file_path=fixture_path)
        curve_count = loader.get_curve_count()
        entry = {'curve_count': curve_count}

        if curve_count <= 1:
            data = loader.data
            fig = plotter.plot_temperature_profile(data)
            entry['temperature_profile_sha256'] = _hash_figure(fig)
        else:
            per_curve = {}
            for ci in range(curve_count):
                data = loader.set_current_curve(ci)
                fig = plotter.plot_temperature_profile(data)
                per_curve[f'curve_{ci}'] = {
                    'temperature_profile_sha256': _hash_figure(fig),
                }
            entry['curves'] = per_curve

        results['fixtures'][fixture_name] = entry

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, sort_keys=True)

    return results


if __name__ == '__main__':
    out_path = os.path.join(BASELINE_DIR, 'figure-hashes.json')
    summary = capture(out_path)
    print(f"wrote baseline to {out_path}")
    print(f"fixtures hashed: {len(summary['fixtures'])}")
    for name, entry in summary['fixtures'].items():
        if 'temperature_profile_sha256' in entry:
            print(f"  {name}: {entry['temperature_profile_sha256'][:12]}... "
                  f"(curves={entry['curve_count']})")
        else:
            for curve_key, curve_entry in entry['curves'].items():
                print(f"  {name} [{curve_key}]: "
                      f"{curve_entry['temperature_profile_sha256'][:12]}...")
