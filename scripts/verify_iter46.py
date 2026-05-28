"""Quick verify script for iter-46 wiring."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.prop_pergame import (
    feature_columns, build_per_opp_rolling, _PER_OPP_ROLLING_KEYS
)

print("=== feature_columns per stat ===")
for s in ['pts', 'reb', 'ast', 'fg3m', 'stl', 'blk', 'tov']:
    cols = feature_columns(s)
    key = f'per_opp_{s}_l3'
    has = key in cols
    print(f"stat={s}: len={len(cols)} has_{key}={has}")

print("\n=== parquet loader ===")
loader = build_per_opp_rolling()
print(f"Loader entries: {len(loader):,}")

sample = loader.features(2544, '2024-11-01')
print(f"LeBron 2024-11-01: {sample}")

sample2 = loader.features(2544, '2099-01-01')
print(f"LeBron future date (expect None): {sample2}")
