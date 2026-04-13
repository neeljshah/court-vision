"""Quick test: run game_orchestrator for NYK vs CLE with real players."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.prediction.game_orchestrator import predict_game

# Jalen Brunson=1628973, Karl-Anthony Towns=1626157, Donovan Mitchell=1628378, Darius Garland=1630162
pids = ["1628973", "1626157", "1628378", "1630162"]
r = predict_game("NYK", "CLE", season="2025-26", player_ids=pids, save=False)
summary = {k: v for k, v in r.items() if k not in ("props", "edges")}
print(json.dumps(summary, indent=2, default=str))
print(f"\nProps modeled: {len(r['props'])} players")
for p in r["props"]:
    preds = {k: round(v, 1) for k, v in p.get("predictions", {}).items()}
    print(f"  {p.get('player_name','?')}: {preds}  suppressed={p.get('suppressed')}")
print(f"\nEdge plays: {len(r['edges'])}")
for e in r["edges"][:5]:
    print(f"  {e['player_name']} {e['stat']} {e['direction']} | edge={e['edge_pct']:.1%}")
