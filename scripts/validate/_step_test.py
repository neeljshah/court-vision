print("Step 1: starting")
import glob, json, os, re, sys
from collections import defaultdict
from datetime import datetime
print("Step 2: stdlib done")

import numpy as np
print("Step 3: numpy done")

import xgboost as xgb
print("Step 4: xgboost done")

from sklearn.metrics import mean_absolute_error, r2_score
print("Step 5: sklearn done")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# Load one gamelog
pattern = os.path.join(_NBA_CACHE, "gamelog_full_*_2024-25.json")
files = glob.glob(pattern)
print(f"Step 6: found {len(files)} gamelog files")

# Load first model
m = xgb.XGBRegressor()
m.load_model(os.path.join(_MODEL_DIR, "props_pts.json"))
print("Step 7: model loaded")

print("All steps OK")
