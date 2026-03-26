"""Quick perf test: process first 20 players only."""
import glob, json, os, re, sys, time
from datetime import datetime
import numpy as np
import xgboost as xgb
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_CUTOFF = datetime(2025, 2, 1)

def _parse_date(s):
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None

# Load model and check what it expects
mod = xgb.XGBRegressor()
mod.load_model(os.path.join(_MODEL_DIR, "props_pts.json"))
booster = mod.get_booster()
feat_names = booster.feature_names
n_feat = booster.num_features()
print(f"Model feature_names: {feat_names}")
print(f"Model num_features:  {n_feat}")
