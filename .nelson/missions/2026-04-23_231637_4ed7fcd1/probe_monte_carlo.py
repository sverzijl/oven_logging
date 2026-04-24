"""Monte Carlo: what is the noise-floor combined-rank gap for 'identical' sensors?

Iron Duke claims gap tops out at 3 across 200 RNG seeds on a 4-internal-sensor
σ=0.5 °C fixture. Reproduce that distribution and check the 95th/99th/max.
"""
import os
import sys
import numpy as np
import pandas as pd

REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
sys.path.insert(0, REPO)
os.chdir(REPO)

from src.data.thermodynamic_sensor_classifier import identify_core_sensor_combined_rank


def bake_curve(n=600, period=5.0, t_base=30.0, t_peak=100.0,
               n_pre=10, rise_samples=200, plateau=60, cool_rate=0.05):
    """A single canonical internal-sensor bake curve — identical physics."""
    pre = np.full(n_pre, t_base)
    rise = np.linspace(t_base, t_peak, rise_samples)
    plat = np.full(plateau, t_peak)
    remaining = n - n_pre - rise_samples - plateau
    drop_per = cool_rate * period
    cur = t_peak
    cooldown = []
    for _ in range(remaining):
        cur = max(t_base, cur - drop_per)
        cooldown.append(cur)
    full = np.concatenate([pre, rise, plat, np.array(cooldown)])
    if len(full) < n:
        full = np.concatenate([full, np.full(n - len(full), t_base)])
    return full[:n]


def run_trial(seed, sigma, n_sensors=4, n=600, period=5.0):
    """Build n_sensors identical-physics curves + gaussian noise σ=sigma, measure gap.

    Returns (winner, firmware_sensor, diagnostics_dict, gap_from_second_place).
    """
    rng = np.random.default_rng(seed)
    base = bake_curve(n=n, period=period)
    ts = np.arange(n, dtype=float) * period
    df = pd.DataFrame({"Timestamp": ts})
    sensor_names = [f"T{i}" for i in range(1, n_sensors + 1)]
    for s in sensor_names:
        df[s] = base + rng.normal(0.0, sigma, n)
    winner, diag = identify_core_sensor_combined_rank(df, sensor_names)
    if winner is None:
        return None, None, None, None
    scores = {s: diag[s]["combined_score"] for s in sensor_names}
    sorted_scores = sorted(scores.values())
    # gap between winner and runner-up
    gap_to_second = sorted_scores[1] - sorted_scores[0]
    # gap between winner and WORST (largest): this is what the classifier
    # compares against 'firmware' in the integration path — if firmware
    # happens to pick the worst-scoring sensor the gap could be huge.
    gap_to_worst = sorted_scores[-1] - sorted_scores[0]
    return winner, scores, gap_to_second, gap_to_worst


def main():
    # 1. 4-internal-sensor σ=0.5 (Iron Duke's config)
    print("=" * 72)
    print("Monte Carlo: 4 sensors, σ=0.5°C, 200 seeds (Iron Duke's config)")
    print("=" * 72)
    gaps_2nd = []
    gaps_worst = []
    for seed in range(200):
        _, _, g2, gw = run_trial(seed, sigma=0.5, n_sensors=4)
        if g2 is not None:
            gaps_2nd.append(g2)
            gaps_worst.append(gw)
    g2_arr = np.array(gaps_2nd)
    gw_arr = np.array(gaps_worst)
    print(f"  gap-to-runner-up:  min {g2_arr.min()}  median {np.median(g2_arr)}  "
          f"p95 {np.percentile(g2_arr, 95)}  p99 {np.percentile(g2_arr, 99)}  max {g2_arr.max()}")
    print(f"  gap-to-worst-sibling:  min {gw_arr.min()}  median {np.median(gw_arr)}  "
          f"p95 {np.percentile(gw_arr, 95)}  p99 {np.percentile(gw_arr, 99)}  max {gw_arr.max()}")
    print(f"  #seeds where gap-to-worst ≥ 4: "
          f"{int((gw_arr >= 4).sum())}/{len(gw_arr)}")
    print(f"  #seeds where gap-to-worst ≥ 5: "
          f"{int((gw_arr >= 5).sum())}/{len(gw_arr)}")
    print(f"  #seeds where gap-to-worst ≥ 7: "
          f"{int((gw_arr >= 7).sum())}/{len(gw_arr)}")

    # 2. 8-sensor σ=0.5 — matches the integration-path fixture (T1..T8 all ranked)
    print()
    print("=" * 72)
    print("Monte Carlo: 8 sensors, σ=0.5°C, 200 seeds (production-path config)")
    print("=" * 72)
    gaps_2nd = []
    gaps_worst = []
    for seed in range(200):
        _, _, g2, gw = run_trial(seed, sigma=0.5, n_sensors=8)
        if g2 is not None:
            gaps_2nd.append(g2)
            gaps_worst.append(gw)
    g2_arr = np.array(gaps_2nd)
    gw_arr = np.array(gaps_worst)
    print(f"  gap-to-runner-up:  min {g2_arr.min()}  median {np.median(g2_arr)}  "
          f"p95 {np.percentile(g2_arr, 95)}  p99 {np.percentile(g2_arr, 99)}  max {g2_arr.max()}")
    print(f"  gap-to-worst-sibling:  min {gw_arr.min()}  median {np.median(gw_arr)}  "
          f"p95 {np.percentile(gw_arr, 95)}  p99 {np.percentile(gw_arr, 99)}  max {gw_arr.max()}")
    print(f"  #seeds where gap-to-worst ≥ 4: "
          f"{int((gw_arr >= 4).sum())}/{len(gw_arr)}")
    print(f"  #seeds where gap-to-worst ≥ 5: "
          f"{int((gw_arr >= 5).sum())}/{len(gw_arr)}")
    print(f"  #seeds where gap-to-worst ≥ 7: "
          f"{int((gw_arr >= 7).sum())}/{len(gw_arr)}")

    # 3. Higher σ
    for sigma in [1.0, 2.0]:
        print()
        print("=" * 72)
        print(f"Monte Carlo: 8 sensors, σ={sigma}°C, 200 seeds")
        print("=" * 72)
        gaps_worst = []
        for seed in range(200):
            _, _, _, gw = run_trial(seed, sigma=sigma, n_sensors=8)
            if gw is not None:
                gaps_worst.append(gw)
        gw_arr = np.array(gaps_worst)
        print(f"  gap-to-worst:  min {gw_arr.min()}  median {np.median(gw_arr)}  "
              f"p95 {np.percentile(gw_arr, 95)}  p99 {np.percentile(gw_arr, 99)}  max {gw_arr.max()}")
        print(f"  #seeds where gap-to-worst ≥ 4: "
              f"{int((gw_arr >= 4).sum())}/{len(gw_arr)}")


if __name__ == "__main__":
    main()
