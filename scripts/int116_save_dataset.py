"""Step 1 of INT-116: Load build_pergame_dataset, extract needed columns, save to parquet."""
from __future__ import annotations
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

print("[INT-116 SAVE] Loading build_pergame_dataset ...", flush=True)
from src.prediction.prop_pergame import build_pergame_dataset, feature_columns

rows, feat_cols = build_pergame_dataset(min_prior=0)
print(f"[INT-116 SAVE] Loaded {len(rows):,} rows", flush=True)

import pandas as pd
import numpy as np

all_feat_cols = feature_columns()

MLP_FEATURES = [
    "l5_min", "prev_min", "opp_def_pts", "rest_days", "is_b2b", "is_home",
    "bbref_usg_pct", "bbref_ts_pct", "ewma_pts", "ewma_reb", "ewma_ast",
    "miles_traveled", "days_since_last_game", "l5_pts", "l5_reb", "l5_ast",
]
TARGET_STATS = ["target_pts", "target_reb", "target_ast"]
KEEP_COLS = list(dict.fromkeys(all_feat_cols + MLP_FEATURES + TARGET_STATS + ["date"]))

print("[INT-116 SAVE] Building DataFrame ...", flush=True)
records = []
for row in rows:
    r = {}
    r["date"] = str(row.get("date", ""))
    for s in ["pts", "reb", "ast"]:
        r[f"target_{s}"] = float(row.get(f"target_{s}", 0.0) or 0.0)
    for fc in all_feat_cols:
        v = row.get(fc)
        r[fc] = float(v) if v is not None else 0.0
    for mf in MLP_FEATURES:
        if mf not in r:
            v = row.get(mf)
            r[mf] = float(v) if v is not None else 0.0
    records.append(r)

df = pd.DataFrame(records)
df = df.sort_values("date").reset_index(drop=True)
print(f"[INT-116 SAVE] DataFrame: {df.shape}", flush=True)

out_path = ROOT / "data" / "cache" / "int116_pergame_dataset.parquet"
df.to_parquet(str(out_path), index=False)
print(f"[INT-116 SAVE] Saved to {out_path}", flush=True)
print(f"[INT-116 SAVE] Columns: {df.columns.tolist()[:30]}", flush=True)
