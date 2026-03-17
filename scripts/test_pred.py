import sys
sys.path.insert(0, "C:/Users/neelj/nba-ai-system")
from src.prediction.game_prediction import predict_game, predict_today
import json

r = predict_game("GSW", "BOS", "2024-25")
print("GSW vs BOS prediction:")
for k, v in r.items():
    if k != "features":
        print(f"  {k}: {v}")

print("\nToday:")
games = predict_today("2024-25")
for g in games:
    print(f"  {g['away_team']} @ {g['home_team']}  win_prob={g['home_win_prob']:.3f}  spread={g['spread_est']:+.1f}  total={g['total_est']:.1f}  [{g['confidence']}]")
if not games:
    print("  (no games scheduled today)")
