"""
Blowout winner vs loser breakdown + FGA share analysis.
"""
import json, os, re
import numpy as np
import pandas as pd
from scipy import stats

BOX_DIR  = "C:/Users/neelj/nba-ai-system/data/cache/team_system/box"
TG_PATH  = "C:/Users/neelj/nba-ai-system/data/cache/team_system/team_game.parquet"
BLOWOUT_THRESH = 15
CLOSE_THRESH   = 5


def parse_min(min_str):
    if not min_str:
        return 0.0
    m = re.match(r"PT(\d+)M([\d.]+)S", str(min_str))
    if m:
        return int(m.group(1)) + float(m.group(2)) / 60.0
    try:
        return float(min_str)
    except Exception:
        return 0.0


tg = pd.read_parquet(TG_PATH)
tg["margin"] = tg["pts"] - tg["opp_pts"]
game_margins = {}
for _, row in tg.iterrows():
    gid = str(row["gid"]).zfill(10)
    game_margins.setdefault(gid, {})[row["team"]] = row["margin"]

player_rows = []
for fname in sorted(os.listdir(BOX_DIR)):
    if not fname.endswith(".json"):
        continue
    gid = fname.replace(".json", "")
    margins = game_margins.get(gid, {})
    path = os.path.join(BOX_DIR, fname)
    with open(path) as f:
        game = json.load(f)["game"]
    for team_key in ["homeTeam", "awayTeam"]:
        team = game[team_key]
        tc = team["teamTricode"]
        margin = margins.get(tc)
        if margin is None:
            continue
        for p in team["players"]:
            starter = p.get("starter", "0")
            st = p["statistics"]
            mins = parse_min(st.get("minutes", ""))
            fga  = st.get("fieldGoalsAttempted", 0)
            player_rows.append({
                "gid": gid, "team": tc,
                "starter": int(starter == "1"),
                "margin": margin,
                "abs_margin": abs(margin),
                "min": mins, "fga": fga,
                "is_winner": int(margin > 0)
            })

pf = pd.DataFrame(player_rows)
pf_s = pf[pf["starter"] == 1]

pb = pf_s[pf_s["abs_margin"] >= BLOWOUT_THRESH]
pc = pf_s[pf_s["abs_margin"] <= CLOSE_THRESH]
pb_win  = pb[pb["is_winner"] == 1]
pb_loss = pb[pb["is_winner"] == 0]

print("=== WINNER vs LOSER breakdown in blowouts (per-starter) ===")
for label, grp in [("Blowout WINNERS", pb_win), ("Blowout LOSERS", pb_loss), ("Close all", pc)]:
    print(f"  {label:<20}  min={grp['min'].mean():.2f}  FGA={grp['fga'].mean():.2f}  n={len(grp)}")
print()
print("Starter min multiplier: winner/close =", round(pb_win["min"].mean() / pc["min"].mean(), 4))
print("Starter min multiplier: loser/close  =", round(pb_loss["min"].mean() / pc["min"].mean(), 4))
print("Starter FGA multiplier: winner/close =", round(pb_win["fga"].mean() / pc["fga"].mean(), 4))
print("Starter FGA multiplier: loser/close  =", round(pb_loss["fga"].mean() / pc["fga"].mean(), 4))

# Bench side
pf_b = pf[pf["starter"] == 0]
pbb = pf_b[pf_b["abs_margin"] >= BLOWOUT_THRESH]
pbc = pf_b[pf_b["abs_margin"] <= CLOSE_THRESH]
pbb_win = pbb[pbb["is_winner"] == 1]
pbb_loss = pbb[pbb["is_winner"] == 0]

print()
print("=== BENCH breakdown (players who played > 0 min) ===")
for label, grp in [("Blowout WINNERS", pbb_win), ("Blowout LOSERS", pbb_loss), ("Close all", pbc)]:
    g = grp[grp["min"] > 0]
    print(f"  {label:<20}  min={g['min'].mean():.2f}  FGA={g['fga'].mean():.2f}  active_n={len(g)}")

# Team-level FGA share
team_rows = []
for (gid, tc), grp in pf.groupby(["gid", "team"]):
    margin = grp["margin"].iloc[0]
    abs_margin = abs(margin)
    is_winner = int(margin > 0)
    s_fga = grp[grp["starter"] == 1]["fga"].sum()
    b_fga = grp[grp["starter"] == 0]["fga"].sum()
    s_min = grp[grp["starter"] == 1]["min"].sum()
    b_min = grp[grp["starter"] == 0]["min"].sum()
    total_fga = s_fga + b_fga
    team_rows.append({
        "gid": gid, "team": tc, "margin": margin, "abs_margin": abs_margin,
        "is_winner": is_winner, "starter_fga": s_fga, "bench_fga": b_fga,
        "starter_min": s_min, "bench_min": b_min,
        "starter_fga_share": s_fga / total_fga if total_fga > 0 else np.nan
    })

tf = pd.DataFrame(team_rows)
bw = tf[(tf["abs_margin"] >= BLOWOUT_THRESH) & (tf["is_winner"] == 1)]
bl = tf[(tf["abs_margin"] >= BLOWOUT_THRESH) & (tf["is_winner"] == 0)]
cl = tf[tf["abs_margin"] <= CLOSE_THRESH]

print()
print("=== TEAM starter FGA SHARE ===")
print(f"  Blowout winner  starter FGA share: {bw['starter_fga_share'].mean():.4f}")
print(f"  Blowout loser   starter FGA share: {bl['starter_fga_share'].mean():.4f}")
print(f"  Blowout both    starter FGA share: {tf[tf['abs_margin']>=15]['starter_fga_share'].mean():.4f}")
print(f"  Close all       starter FGA share: {cl['starter_fga_share'].mean():.4f}")

print()
print("=== MARGINAL THRESHOLDS: how effect changes at different cutoffs ===")
for thresh in [10, 15, 18, 20, 25]:
    blow_sub = pf_s[pf_s["abs_margin"] >= thresh]
    if len(blow_sub) < 30:
        continue
    mult_min = blow_sub["min"].mean() / pc["min"].mean()
    mult_fga = blow_sub["fga"].mean() / pc["fga"].mean()
    n = len(blow_sub)
    print(f"  margin>={thresh}: n={n}  min_mult={mult_min:.4f}  fga_mult={mult_fga:.4f}")
