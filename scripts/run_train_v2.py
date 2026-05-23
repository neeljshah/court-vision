"""Quick training runner for LiveWinProbV2."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.prediction.live_win_prob_v2 import LiveWinProbV2

m = LiveWinProbV2()
metrics = m.train()
print("=== TRAINING METRICS ===")
print(json.dumps(metrics, indent=2))
