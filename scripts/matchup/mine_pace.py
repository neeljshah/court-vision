"""Mine the NYK-SAS head-to-head PACE matchup signal.

SIGNAL = game pace (possessions) in the matchup vs the average of the two
teams' season paces. Is the NYK-SAS game faster/slower than expected?

Raw multiplier for a team = (team's game-pace vs THIS opp) / (team's game-pace
vs ALL OTHER opps), poss-weighted. Pace is a SHARED property of the game, so we
report one shared value (mult_nyk == mult_sas).
"""
import json
import os
import pandas as pd

REPO = r"C:\Users\neelj\nba-ai-system"
TG = os.path.join(REPO, "data", "cache", "team_system", "team_game.parquet")
OUT_DIR = os.path.join(REPO, "data", "cache", "team_system", "matchup")
OUT = os.path.join(OUT_DIR, "pace.json")

NYK, SAS = "NYK", "SAS"
K = 6  # shrink constant (team-level)

df = pd.read_parquet(TG)

# Game pace = average of the two teams' possessions for that game.
# In team_game each row already has poss (own) and opp_poss. Use the game-level
# pace = mean(poss, opp_poss) so it is symmetric and is the SAME number both teams see.
df["game_pace"] = (df["poss"] + df["opp_poss"]) / 2.0


def team_pace_split(team, opp):
    """Return (pace vs THIS opp, pace vs ALL OTHERS, n_vs_opp, weights)."""
    t = df[df["team"] == team].copy()
    vs = t[t["opp"] == opp]
    others = t[t["opp"] != opp]
    # poss-weighted mean of game_pace. Weight by the team's own possessions in
    # each game (the natural exposure weight).
    def wmean(sub):
        w = sub["poss"]
        return (sub["game_pace"] * w).sum() / w.sum()
    return wmean(vs), wmean(others), len(vs), vs


nyk_vs, nyk_oth, nyk_n, nyk_vs_df = team_pace_split(NYK, SAS)
sas_vs, sas_oth, sas_n, sas_vs_df = team_pace_split(SAS, NYK)

raw_nyk = nyk_vs / nyk_oth
raw_sas = sas_vs / sas_oth

n_games = nyk_n  # H2H game count (same for both)
w = n_games / (n_games + K)

shrunk_nyk = 1 + w * (raw_nyk - 1)
shrunk_sas = 1 + w * (raw_sas - 1)

# Pace is a shared game property -> report ONE shared shrunk multiplier.
# Average the two teams' raw deviations then shrink (they should be ~equal since
# game_pace is symmetric, but each is divided by a different "vs-others" base).
raw_shared = (raw_nyk + raw_sas) / 2.0
shrunk_shared = 1 + w * (raw_shared - 1)

# ---- Net margin effect in pts/100 (NYK perspective) ----
# Pace changes POSSESSIONS, not efficiency. A neutral pace change scales both
# teams' point totals equally; per-100 EFFICIENCY (and thus per-100 margin) is
# INVARIANT to pace. So the pace signal's residual effect on margin-per-100 is ~0
# by construction. The only way pace moves margin is variance (more poss = lower
# variance for the favorite), which is NOT a pts/100 mean effect.
# NYK per-100 net edge vs SAS (from season splits): use to size what a pace tilt
# would do to TOTAL points, but the per-100 margin residual is ~0.
nyk_net_per100 = 124.8 - 116.6  # league net (info only)
residual_pts_per100 = 0.0  # pace does not move per-100 margin mean

# raw game paces for reporting
season_nyk_pace = (df[df["team"] == NYK]["game_pace"] * df[df["team"] == NYK]["poss"]).sum() / df[df["team"] == NYK]["poss"].sum()
season_sas_pace = (df[df["team"] == SAS]["game_pace"] * df[df["team"] == SAS]["poss"]).sum() / df[df["team"] == SAS]["poss"].sum()
expected_pace = (season_nyk_pace + season_sas_pace) / 2.0
h2h_pace = (nyk_vs_df["game_pace"] * nyk_vs_df["poss"]).sum() / nyk_vs_df["poss"].sum()

print("=== NYK-SAS PACE MATCHUP SIGNAL ===")
print(f"NYK season game-pace (poss-wtd): {season_nyk_pace:.2f}")
print(f"SAS season game-pace (poss-wtd): {season_sas_pace:.2f}")
print(f"Expected H2H pace (avg of two):  {expected_pace:.2f}")
print(f"Actual H2H pace (4 games):       {h2h_pace:.2f}")
print()
print(f"NYK: vs SAS {nyk_vs:.2f} / vs others {nyk_oth:.2f} -> raw {raw_nyk:.4f}")
print(f"SAS: vs NYK {sas_vs:.2f} / vs others {sas_oth:.2f} -> raw {raw_sas:.4f}")
print(f"n_games (H2H): {n_games}, shrink w = {n_games}/({n_games}+{K}) = {w:.4f}")
print()
print(f"raw_shared:    {raw_shared:.4f}")
print(f"shrunk_shared: {shrunk_shared:.4f}  (mult_nyk == mult_sas)")
print(f"shrunk_nyk:    {shrunk_nyk:.4f}")
print(f"shrunk_sas:    {shrunk_sas:.4f}")
print()
print("Per-game H2H paces:")
for _, r in nyk_vs_df.sort_values("date").iterrows():
    print(f"  {r['date']} {r['kind']:7s} vs {r['opp']}: game_pace {r['game_pace']:.1f} (NYK {r['poss']:.1f} / SAS {r['opp_poss']:.1f})")
print()
print(f"residual_pts_per100 (NYK persp): {residual_pts_per100} (pace is per-100 margin-neutral)")

os.makedirs(OUT_DIR, exist_ok=True)
result = {
    "signal": "pace",
    "mechanic": "pace",
    "mult_nyk": round(shrunk_shared, 4),
    "mult_sas": round(shrunk_shared, 4),
    "raw_nyk": round(raw_nyk, 4),
    "raw_sas": round(raw_sas, 4),
    "n_games": int(n_games),
    "residual_pts_per100": residual_pts_per100,
    "notes": (
        f"Shared game-pace signal. Expected pace {expected_pace:.1f} (avg of NYK "
        f"{season_nyk_pace:.1f} & SAS {season_sas_pace:.1f} season), actual H2H "
        f"{h2h_pace:.1f} over {n_games} games. raw_nyk={raw_nyk:.3f} raw_sas={raw_sas:.3f}, "
        f"shrunk shared={shrunk_shared:.3f} (K={K}, w={w:.2f}). Pace changes "
        f"POSSESSION COUNT not per-100 efficiency, so residual_pts_per100=0 "
        f"(margin-per-100 is pace-invariant); it scales TOTAL points/variance only. "
        f"Leak-safe (pace is symmetric box-score outcome, no future info). NO "
        f"double-count with the sim's generic opponent-DEFENSE (that suppresses xFG/"
        f"shot quality; pace is a separate orthogonal mechanic = number of trips). "
        f"On 4 games the deviation is small and noise-dominated; shrunk toward 1."
    ),
}
with open(OUT, "w") as f:
    json.dump(result, f, indent=2)
print(f"\nWROTE {OUT}")
print(json.dumps(result, indent=2))
