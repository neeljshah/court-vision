import sys, json
sys.path.insert(0, "C:/Users/neelj/nba-ai-system")
from src.prediction.player_props import predict_props

players = [
    ("LeBron James", "GSW"),
    ("Stephen Curry", "LAL"),
    ("Nikola Jokic", "BOS"),
]
for name, opp in players:
    r = predict_props(name, opp, season="2024-25")
    print(f"{name} vs {opp}: PTS={r['pts']}  REB={r['reb']}  AST={r['ast']}  [{r['confidence']}]")
