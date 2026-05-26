"""Quick inspect for probe_R15_tonight_slate output."""
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(PROJECT_DIR, "data", "cache",
                       "probe_R15_tonight_slate_bets.json")) as f:
    d = json.load(f)

ks = "kelly_stake_$1000"
print("Total exposure:", d["total_recommended_exposure_$"])
print("Expected EV:", d["expected_value_$"])
print("Expected std:", d["expected_std_$"])
print()
print("=== RANKED BETS (capped, final selected) ===")
for i, b in enumerate(d["ranked_bets"], 1):
    print(f"{i:2d}. {b['player']:25s} {b['stat']:5s} {b['side']:5s} "
          f"{b['book']:3s} line={b['line']:5.1f} "
          f"model_q50={b['model_q50']:6.2f} odds={b['odds']:+5d} "
          f"edge={b['edge_pct']:+6.2f}% kelly={b['kelly_pct_used']:5.2f}% "
          f"stake={b[ks]:6.2f} sigma={b['sigma_deviation']:+.2f}")

print()
print("=== TOP 25 ALL POSITIVE BETS BY EV (PRE-CAP) ===")
for i, b in enumerate(d["all_positive_bets_unfiltered"][:25], 1):
    print(f"{i:2d}. {b['player']:25s} {b['stat']:5s} {b['side']:5s} "
          f"{b['book']:3s} line={b['line']:5.1f} "
          f"model={b['model_q50']:6.2f} odds={b['odds']:+5d} "
          f"ev/$={b['ev_per_dollar']:+6.3f} edge={b['edge_pct']:+6.2f}% "
          f"sigma={b['sigma_deviation']:+.2f}")

print()
print("=== MIDDLES ===")
for m in d["arbitrage_middles"]:
    print(m)

print()
print("=== HIGH CONFIDENCE ===")
for b in d["highest_confidence_bets"]:
    print(f"{b['player']:25s} {b['stat']:5s} {b['side']:5s} {b['book']:3s} "
          f"line={b['line']:5.1f} model={b['model_q50']:.2f} "
          f"sigma={b['sigma_deviation']:+.2f} edge={b['edge_pct']:+.2f}% "
          f"stake={b[ks]:.2f}")
