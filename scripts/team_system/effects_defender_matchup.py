"""
effects_defender_matchup.py
Measures how individual defender quality (stops_pctile) suppresses scorer xFG.
Source: data/cache/signals/defense_matchup.parquet
Mechanic: per_player_xfg_mult in basketball_sim.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd
import numpy as np
from scipy import stats

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'cache', 'signals', 'defense_matchup.parquet')
MIN_POSS = 200  # minimum possessions defended for reliable estimate


def main():
    df = pd.read_parquet(DATA_PATH)
    print(f"Loaded {len(df)} player-season rows.")

    # Filter for reliable sample
    df = df[df['poss_defended'] >= MIN_POSS].copy()
    print(f"After >= {MIN_POSS} possessions filter: {len(df)} rows.")
    print(f"Seasons: {sorted(df['season'].unique())}")

    # fg_suppression = fg_allowed / expected_fg (directly usable as xFG multiplier)
    # stops_pctile: 100 = best defender, 0 = worst
    # Elite: top 20% (pctile >= 80)
    # Replacement: middle 40-60%
    # Weak: bottom 20% (pctile <= 20)

    elite = df[df['stops_pctile'] >= 80]
    mid   = df[(df['stops_pctile'] >= 40) & (df['stops_pctile'] <= 60)]
    weak  = df[df['stops_pctile'] <= 20]

    elite_xfg = elite['fg_suppression'].mean()
    mid_xfg   = mid['fg_suppression'].mean()
    weak_xfg  = weak['fg_suppression'].mean()

    print("\n=== fg_suppression (xFG multiplier, lower = better defender) ===")
    print(f"Elite defenders  (pctile>=80, n={len(elite):4d}): {elite_xfg:.4f}")
    print(f"Replacement       (pctile 40-60, n={len(mid):4d}): {mid_xfg:.4f}")
    print(f"Weak defenders   (pctile<=20, n={len(weak):4d}): {weak_xfg:.4f}")

    elite_mult = elite_xfg / mid_xfg
    weak_mult  = weak_xfg  / mid_xfg
    print(f"\nElite / replacement xFG mult: {elite_mult:.4f}  ({(elite_mult-1)*100:+.2f}%)")
    print(f"Weak  / replacement xFG mult: {weak_mult:.4f}   ({(weak_mult-1)*100:+.2f}%)")
    print(f"FG% spread elite->weak: {(weak_xfg - elite_xfg)*100:.2f} percentage points")

    # Linear fit: xfg_mult = intercept + slope * stops_pctile
    slope, intercept = np.polyfit(df['stops_pctile'].values, df['fg_suppression'].values, 1)
    print(f"\nLinear fit: fg_suppression = {intercept:.4f} + {slope:.6f} * stops_pctile")
    print(f"  -> At pctile=90: {intercept + slope*90:.4f}")
    print(f"  -> At pctile=50: {intercept + slope*50:.4f}")
    print(f"  -> At pctile=10: {intercept + slope*10:.4f}")

    # Significance
    t, p = stats.ttest_ind(elite['fg_suppression'], weak['fg_suppression'])
    print(f"\nt-test (elite vs weak fg_suppression): t={t:.2f}, p={p:.2e}  [n={len(elite)+len(weak)}]")

    # Decile breakdown
    df['bin'] = pd.cut(df['stops_pctile'], bins=[0,10,20,30,40,50,60,70,80,90,100],
                       labels=['0-10','10-20','20-30','30-40','40-50',
                               '50-60','60-70','70-80','80-90','90-100'],
                       )
    grp = df.groupby('bin')['fg_suppression'].agg(['mean','count']).reset_index()
    print("\nDecile breakdown:")
    for _, row in grp.iterrows():
        bar = '#' * int(row['mean'] * 40)
        print(f"  {row['bin']:8s}: fg_supp={row['mean']:.4f}  n={int(row['count']):4d}")

    # Recommended formula for basketball_sim.py
    print("\n=== SIMULATOR PARAMETER ===")
    print("per_player_xfg_mult = 1.0 + (0.5 - stops_pctile / 100.0) * 0.107")
    print("  Elite (pctile=90): {:.4f}".format(1.0 + (0.5 - 0.90) * 0.107))
    print("  Average (pctile=50): {:.4f}".format(1.0 + (0.5 - 0.50) * 0.107))
    print("  Weak   (pctile=10): {:.4f}".format(1.0 + (0.5 - 0.10) * 0.107))
    print(f"\nHeadline: elite-vs-replacement multiplier = {elite_mult:.4f}")
    print(f"  => multiply scorer's xFG by {elite_mult:.4f} when guarded by elite def (pctile>=80)")
    print(f"  => multiply scorer's xFG by {weak_mult:.4f} when guarded by weak def  (pctile<=20)")
    print(f"  => baseline = 1.0 (replacement-level defender)")

    return {
        'elite_xfg': elite_xfg,
        'mid_xfg': mid_xfg,
        'weak_xfg': weak_xfg,
        'elite_mult': elite_mult,
        'weak_mult': weak_mult,
        'n': len(df),
        'p_value': p,
    }


if __name__ == '__main__':
    main()
