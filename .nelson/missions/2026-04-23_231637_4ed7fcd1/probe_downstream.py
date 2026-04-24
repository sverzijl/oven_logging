"""Confirm whether `get_dynamic_sensor_names` propagates the physics-corrected core sensor.

If not, the user-visible label (plot legend, sensor role display) still shows the
firmware pick, even though the data (CoreTemperature column) is correct.
"""
import os
import sys

REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
sys.path.insert(0, REPO)
os.chdir(REPO)

from src.data.loader import ThermalProfileLoader
from tests.fixtures.curve_boundary_cases import _REAL_CSVS

from sensor_naming import get_dynamic_sensor_names


def inspect(name, path):
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=path)
    assignments = loader.get_sensor_assignments()
    print(f"\n=== {name} ===")
    print(f"  resolved_core = {loader.get_core_sensor(curve_index=0)}")
    print(f"  core_physics_corrected = {assignments.get('core_physics_corrected')}")
    print(f"  assignments['core'] = {assignments.get('core')}")
    core_info_all = assignments.get('core_info', {}).get('all_sensors', {})
    print(f"  core_info.all_sensors = {core_info_all}")
    names = get_dynamic_sensor_names(loader)
    print("  get_dynamic_sensor_names() results:")
    for s in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]:
        print(f"    {s}: {names.get(s, '<MISSING>')}")


if __name__ == "__main__":
    inspect("wonder_white", _REAL_CSVS["wonder_white_10k"])
    inspect("real_100098DE_1351", _REAL_CSVS["100098DE_1351"])
