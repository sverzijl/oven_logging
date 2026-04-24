"""Red-cell empirical perturbation probes for HMS Ambush review."""
import os
import sys
import numpy as np
import pandas as pd

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO)

from src.data.loader import ThermalProfileLoader
from src.data.curve_boundary_detector import CurveBoundaryDetector
from config.constants import CURVE_DETECTION_CONFIG
from tests.fixtures.curve_boundary_cases import CASES


def _run(df):
    loader = ThermalProfileLoader()
    loader.metadata = {}
    loader.data = df
    return loader._extract_all_baking_curves(df.copy())


def which_candidate_fires(df, start_idx, peak_idx):
    """Instrument: run each candidate independently on a curve to see which fires first."""
    det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
    from src.data.column_helpers import resolve_core_temperature_series
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float, copy=True)
    timestamps = df["Timestamp"].to_numpy(dtype=float, copy=True)
    first_scan = peak_idx + det._post_peak_grace
    upto = len(temps)

    a = det._candidate_drop_rate(temps[:upto], timestamps[:upto], first_scan)
    b = det._candidate_cool_to_ambient(temps[:upto], first_scan, det._confirm_n)
    c = det._candidate_room_temp_plateau(temps[:upto], first_scan, det._confirm_n)
    pt = float(temps[peak_idx])
    d = det._candidate_dip_with_rerise(temps[:upto], peak_idx, pt)
    e = det._candidate_core_peak_plateau(temps[:upto], timestamps[:upto], peak_idx, first_scan)
    return {"drop_rate": a, "cool_to_ambient": b, "room_temp_plateau": c, "dip_with_rerise": d, "plateau": e}


def rise_magnitude_60s(df, peak_idx, period_hint=5.0):
    """Compute 60s-before-peak rise in °C for a fixture."""
    from src.data.column_helpers import resolve_core_temperature_series
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    ts = df["Timestamp"].to_numpy(dtype=float)
    if len(ts) < 2:
        return None
    dt = float(np.median(np.diff(ts)))
    n60 = max(int(round(60.0 / dt)), 2)
    if peak_idx < n60:
        return None
    return float(temps[peak_idx] - temps[peak_idx - n60])


def find_core_peak(df):
    from src.data.column_helpers import resolve_core_temperature_series
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    return int(np.argmax(temps)), float(np.max(temps))


print("=" * 80)
print("PROBE 1: Which candidate fires per fixture?")
print("=" * 80)
rows = []
for case in CASES:
    if case.get("raises"):
        continue
    df = case["df"]
    try:
        curves = _run(df)
    except Exception as e:
        rows.append((case["name"], "ERROR", str(e)[:60]))
        continue
    if not curves:
        rows.append((case["name"], "(no curves)", "-"))
        continue
    # For the first curve
    c0 = curves[0]
    start_idx = c0["start_idx"]
    # Find the peak within this curve
    from src.data.column_helpers import resolve_core_temperature_series
    sub = df.iloc[start_idx:c0["end_idx"] + 1]
    peak_rel = int(np.argmax(resolve_core_temperature_series(sub).to_numpy(dtype=float)))
    peak_idx = start_idx + peak_rel
    fires = which_candidate_fires(df, start_idx, peak_idx)
    # Find which one matches actual end_idx (within 3)
    winner = None
    for k, v in fires.items():
        if v is not None and abs(v - c0["end_idx"]) <= 3:
            winner = k
            break
    if winner is None:
        # Check if EOF
        if c0["end_idx"] == len(df) - 1:
            winner = "EOF"
        else:
            winner = "?"
    rows.append((case["name"], winner, f"end={c0['end_idx']}, n={len(curves)}, fires={fires}"))

for name, winner, rest in rows:
    print(f"  {name:50s} -> {winner:20s} | {rest}")

print()
print("=" * 80)
print("PROBE 2: Rise-magnitude (60s before peak) per fixture")
print("=" * 80)
for case in CASES:
    if case.get("raises"):
        continue
    df = case["df"]
    peak_idx, peak_temp = find_core_peak(df)
    rm = rise_magnitude_60s(df, peak_idx)
    in_window = (rm is not None and 2.0 <= rm <= 10.0)
    flag = " <-- passes 2..10 guard" if in_window else ""
    print(f"  {case['name']:50s} peak_idx={peak_idx:5d} T={peak_temp:6.1f}  rise60s={rm!s:>10}{flag}")

print()
print("=" * 80)
print("PROBE 3: Short-plateau (15s, 3 samples) spurious-fire test")
print("=" * 80)
# Copy lidded_bake_plateau_classic and make the plateau short
case = next(c for c in CASES if c["name"] == "lidded_bake_plateau_classic")
orig = case["df"].copy()
# Replace plateau (300..359 = 60 samples) with only 3 samples at peak, then continue gentle decline
# Original layout: rise 0..299, plateau 300..359, gentle 360..479, probe-rem 480..484, post 485..600
period = 5.0
t_plateau = 98.0
t_ambient = 22.0
rise = np.linspace(t_ambient, t_plateau, 300)
short_plateau = np.full(3, t_plateau)  # 15 seconds
# Gentle decline from 98 down for 120 samples at 0.25 °C/sample (= 0.05 °C/s)
gentle = np.linspace(t_plateau, t_plateau - 0.25 * 120, 120)
probe_removal = np.linspace(gentle[-1], gentle[-1] - 60, 5)
post = np.full(116, t_ambient)
vct = np.concatenate([rise, short_plateau, gentle, probe_removal, post])
ts = np.arange(len(vct), dtype=float) * period
df_short = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
# Expected: should NOT fire plateau at 300; should fire probe-removal at ~423 (end of gentle)
curves = _run(df_short)
print(f"  Short-plateau (15s) result: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, truncated={c.get('truncated')}")
print(f"  Original plateau-onset was 300. If end ~300: plateau candidate spuriously fired on short plateau.")

print()
print("=" * 80)
print("PROBE 4: Pre-peak spurious fire test - sharp drop AFTER peak on a lidded-like curve")
print("=" * 80)
# Build a curve where there's a flat stretch BEFORE the peak, to see if the 'scan from peak_idx' opens up pre-peak risk
# Actually the plateau candidate scans range(peak_idx, n), so pre-peak can't fire.
# But let's test: peak at idx 100, sharp drop at idx 105, does plateau fire on pre-peak flatness?
n_rise_slow = 50   # ambient->80
n_flat_pre = 30    # stay at 80 for 150s
n_final_rise = 20  # 80->95
n_post_peak_drop = 30  # sharp drop
rise_slow = np.linspace(22.0, 80.0, n_rise_slow)
flat = np.full(n_flat_pre, 80.0)
final = np.linspace(80.0, 95.0, n_final_rise)
drop = np.linspace(95.0, 22.0, n_post_peak_drop)
vct = np.concatenate([rise_slow, flat, final, drop])
ts = np.arange(len(vct), dtype=float) * 5.0
df_pp = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
peak_idx, peak_temp = find_core_peak(df_pp)
rm = rise_magnitude_60s(df_pp, peak_idx)
print(f"  pre-peak-flat curve: peak_idx={peak_idx}, peak_temp={peak_temp:.1f}, rise60s={rm:.2f}")
curves = _run(df_pp)
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, truncated={c.get('truncated')}")

print()
print("=" * 80)
print("PROBE 5: Multi-curve with lidded-then-unlidded (check _skip_plateau_tail)")
print("=" * 80)
# Bake 1 lidded: rise → plateau → gentle decline to 45 → sharp cool
# Bake 2 unlidded: rise → peak → sharp cool
period = 5.0
rise1 = np.linspace(22.0, 98.0, 100)
plateau1 = np.full(60, 98.0)           # lidded plateau
gentle1 = np.linspace(98.0, 45.0, 60)  # cooling under lid
cooldown1 = np.linspace(45.0, 22.0, 40)  # out of lid
gap = np.full(100, 22.0)               # in between at room temp
rise2 = np.linspace(22.0, 95.0, 80)
fall2 = np.linspace(95.0, 22.0, 40)
post = np.full(30, 22.0)
vct = np.concatenate([rise1, plateau1, gentle1, cooldown1, gap, rise2, fall2, post])
ts = np.arange(len(vct), dtype=float) * period
df_multi = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
curves = _run(df_multi)
print(f"  multi-curve lidded-then-unlidded: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max_temp={c['max_temp']:.1f}, truncated={c.get('truncated')}")
print(f"  Expected: 2 curves. Bake1 ends ~idx 100 (plateau onset). Bake2 starts ~idx 360.")

print()
print("=" * 80)
print("PROBE 6: Overlapping bakes (second starts before first cools) with _skip_plateau_tail")
print("=" * 80)
# If _skip_plateau_tail is greedy, could it eat a second bake's start?
# bake1: rise 0..99 to 98, plateau 100..159, at idx 160 ANOTHER rise starts
rise1 = np.linspace(22.0, 98.0, 100)
plateau1 = np.full(60, 98.0)           # ends at idx 159
# Now: another rise immediately (no cooldown). This mimics "probe stays hot" scenario
rise2 = np.linspace(98.0, 100.0, 30)   # slight rise
fall2 = np.linspace(100.0, 22.0, 50)
post = np.full(30, 22.0)
vct = np.concatenate([rise1, plateau1, rise2, fall2, post])
ts = np.arange(len(vct), dtype=float) * 5.0
df_over = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
curves = _run(df_over)
print(f"  overlapping (no cool gap): n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max_temp={c['max_temp']:.1f}, truncated={c.get('truncated')}")
print(f"  If _skip_plateau_tail is harmless for non-plateau: should vary by scenario.")

print()
print("=" * 80)
print("PROBE 7: Plateau window variation - what if plateau is exactly 15s (3 samples)?")
print("=" * 80)
# Key question: CORE_PEAK_PLATEAU_CONFIRM_SECONDS=20 means 4 samples at 5s each.
# What if plateau is only 3 samples (15s)?
period = 5.0
rise = np.linspace(22.0, 98.0, 300)
short_plat = np.full(3, 98.0)      # 15s plateau = 3 samples
decline = np.linspace(98.0, 22.0, 100)
post = np.full(50, 22.0)
vct = np.concatenate([rise, short_plat, decline, post])
ts = np.arange(len(vct), dtype=float) * period
df15 = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
curves = _run(df15)
print(f"  15s plateau: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.1f}, truncated={c.get('truncated')}")

# Similarly 20s plateau (exactly CONFIRM_SECONDS): does it fire?
rise = np.linspace(22.0, 98.0, 300)
plat20 = np.full(4, 98.0)          # 20s plateau = 4 samples = confirm_n
decline = np.linspace(98.0, 22.0, 100)
post = np.full(50, 22.0)
vct = np.concatenate([rise, plat20, decline, post])
ts = np.arange(len(vct), dtype=float) * period
df20 = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
curves = _run(df20)
print(f"  20s plateau: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.1f}, truncated={c.get('truncated')}")
