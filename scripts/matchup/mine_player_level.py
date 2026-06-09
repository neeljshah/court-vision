"""
Mine the HEAD-TO-HEAD "player_level" matchup signal for NYK-vs-SAS.

SIGNAL: per-player scoring/efficiency vs the opponent. For the top ~5 players each
side, compute eFG and pts vs the opponent (from box/<gid>.json over the 4 H2H games)
vs their season eFG / season pts-per-game.

mechanic = off_xfg(player)  (per-player scoring efficiency on offense)

Matchup multiplier (RESIDUAL form, nets out team/player own quality):
    raw_player = (player stat vs THIS opp) / (player stat vs ALL OTHER opps)
Aggregate to a team-level multiplier (minutes/usage-weighted across the top-5),
then shrink HARD because n is tiny (4 games / player): K=12.

    shrunk = 1 + w*(raw-1),  w = n/(n+K)

WARNING: 4 games per player -> mostly noise. Report real=false unless a clear,
large, CONSISTENT effect across players.
"""
import os, json, glob
import numpy as np
import pandas as pd

ROOT = r"C:\Users\neelj\nba-ai-system"
BOXDIR = os.path.join(ROOT, "data", "cache", "team_system", "box")
TG = os.path.join(ROOT, "data", "cache", "team_system", "team_game.parquet")
OUTDIR = os.path.join(ROOT, "data", "cache", "team_system", "matchup")
os.makedirs(OUTDIR, exist_ok=True)

NYK_TRI, SAS_TRI = "NYK", "SAS"

# H2H game ids (NYK vs SAS), 4 games
tg = pd.read_parquet(TG)
h2h = tg[((tg.team == "NYK") & (tg.opp == "SAS"))]["gid"].unique().tolist()
H2H = set(h2h)
print("H2H gids:", sorted(H2H))

# poss for each (gid, team) for weighting
poss_map = {}
for _, r in tg.iterrows():
    poss_map[(r["gid"], r["team"])] = float(r["poss"])

# ----- parse every box json into per-player game rows -----
rows = []
for fp in glob.glob(os.path.join(BOXDIR, "*.json")):
    gid = os.path.splitext(os.path.basename(fp))[0]
    d = json.load(open(fp))
    g = d.get("game", d)
    for side in ("homeTeam", "awayTeam"):
        t = g[side]
        tri = t.get("teamTricode")
        opp_tri = g["awayTeam" if side == "homeTeam" else "homeTeam"].get("teamTricode")
        for p in t.get("players", []):
            st = p.get("statistics", {})
            fga = st.get("fieldGoalsAttempted", 0) or 0
            if not p.get("played", False) and fga == 0 and (st.get("points", 0) or 0) == 0:
                # didn't play
                continue
            rows.append(dict(
                gid=gid, team=tri, opp=opp_tri,
                pid=p.get("personId"), name=p.get("name"),
                fgm=st.get("fieldGoalsMade", 0) or 0,
                fga=fga,
                fg3m=st.get("threePointersMade", 0) or 0,
                pts=st.get("points", 0) or 0,
            ))
df = pd.DataFrame(rows)
df["efg_num"] = df["fgm"] + 0.5 * df["fg3m"]  # eFG numerator (per attempt)

# top-5 by total minutes? we only have player_rates mpg; use season FGA volume as proxy
# but better: use player_rates mpg ranking provided.
pr = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system", "player_rates.parquet"))

def top5(team):
    sub = pr[pr.team == team].sort_values("mpg", ascending=False).head(5)
    return list(zip(sub.pid.astype(str), sub.player, sub.mpg, sub.pts_pg))

TOP = {"NYK": top5("NYK"), "SAS": top5("SAS")}

def player_split(pid, team, opp):
    """Return (vs_opp stats, vs_others stats, n_vs_opp) for eFG and pts."""
    sub = df[(df.pid.astype(str) == str(pid)) & (df.team == team)]
    vo = sub[sub.opp == opp]
    vothers = sub[sub.opp != opp]
    def agg(s):
        fga = s.fga.sum()
        efg = (s.efg_num.sum() / fga) if fga > 0 else np.nan
        ppg = s.pts.mean() if len(s) else np.nan
        return efg, ppg, len(s)
    return agg(vo), agg(vothers), len(vo)

K = 12  # very hard shrink for player_level


def team_multiplier(team, opp):
    """Minutes-weighted aggregate of per-player matchup ratios.
    Returns raw_efg_mult, raw_pts_mult, combined off_xfg mult, n_games, detail."""
    detail = []
    w_efg_num = w_efg_den = 0.0   # weighted efg ratio
    w_pts_num = w_pts_den = 0.0
    n_games_opp = 0
    for pid, name, mpg, season_ppg in TOP[team]:
        (efg_o, ppg_o, n_o), (efg_x, ppg_x, n_x), n_vs = player_split(pid, team, opp)
        n_games_opp = max(n_games_opp, n_vs)
        if not (np.isfinite(efg_o) and np.isfinite(efg_x) and efg_x > 0):
            efg_ratio = np.nan
        else:
            efg_ratio = efg_o / efg_x
        if not (np.isfinite(ppg_o) and np.isfinite(ppg_x) and ppg_x > 0):
            pts_ratio = np.nan
        else:
            pts_ratio = ppg_o / ppg_x
        wt = float(mpg)  # weight by minutes (proxy for offensive share / importance)
        detail.append(dict(pid=pid, name=name, mpg=round(mpg, 1), n_vs_opp=n_vs,
                           efg_vs_opp=None if not np.isfinite(efg_o) else round(efg_o, 4),
                           efg_vs_others=None if not np.isfinite(efg_x) else round(efg_x, 4),
                           efg_ratio=None if not np.isfinite(efg_ratio) else round(efg_ratio, 4),
                           ppg_vs_opp=None if not np.isfinite(ppg_o) else round(ppg_o, 2),
                           ppg_vs_others=None if not np.isfinite(ppg_x) else round(ppg_x, 2),
                           pts_ratio=None if not np.isfinite(pts_ratio) else round(pts_ratio, 4)))
        if np.isfinite(efg_ratio):
            w_efg_num += wt * efg_ratio; w_efg_den += wt
        if np.isfinite(pts_ratio):
            w_pts_num += wt * pts_ratio; w_pts_den += wt
    raw_efg = w_efg_num / w_efg_den if w_efg_den > 0 else 1.0
    raw_pts = w_pts_num / w_pts_den if w_pts_den > 0 else 1.0
    # off_xfg mechanic = efficiency (eFG) lever primarily; we report both, combine = geometric-ish
    raw_off = raw_efg  # the mechanic is off_xfg -> efficiency
    return raw_efg, raw_pts, raw_off, n_games_opp, detail


def shrink(raw, n, K=K):
    w = n / (n + K)
    return 1 + w * (raw - 1.0)


print("\n=== NYK players vs SAS ===")
raw_efg_nyk, raw_pts_nyk, raw_off_nyk, n_nyk, det_nyk = team_multiplier("NYK", "SAS")
for d in det_nyk:
    print(f"  {d['name']:<20} n_vs={d['n_vs_opp']} eFG {d['efg_vs_opp']} vs {d['efg_vs_others']} -> {d['efg_ratio']}  | pts {d['ppg_vs_opp']} vs {d['ppg_vs_others']} -> {d['pts_ratio']}")
print(f"  TEAM raw eFG mult={raw_efg_nyk:.4f}  raw pts mult={raw_pts_nyk:.4f}  off_xfg(raw)={raw_off_nyk:.4f}  n_games={n_nyk}")

print("\n=== SAS players vs NYK ===")
raw_efg_sas, raw_pts_sas, raw_off_sas, n_sas, det_sas = team_multiplier("SAS", "NYK")
for d in det_sas:
    print(f"  {d['name']:<20} n_vs={d['n_vs_opp']} eFG {d['efg_vs_opp']} vs {d['efg_vs_others']} -> {d['efg_ratio']}  | pts {d['ppg_vs_opp']} vs {d['ppg_vs_others']} -> {d['pts_ratio']}")
print(f"  TEAM raw eFG mult={raw_efg_sas:.4f}  raw pts mult={raw_pts_sas:.4f}  off_xfg(raw)={raw_off_sas:.4f}  n_games={n_sas}")

n_games = 4
mult_nyk = shrink(raw_off_nyk, n_games)
mult_sas = shrink(raw_off_sas, n_games)
print(f"\nShrunk (K={K}, n={n_games}, w={n_games/(n_games+K):.3f}):")
print(f"  off_xfg mult NYK={mult_nyk:.4f}   SAS={mult_sas:.4f}")

# ---- net margin effect in pts/100 (NYK perspective) ----
# Sim already applies generic opp defense. The residual off_xfg multiplier scales a
# team's offensive efficiency. Approx: dOFF = (mult-1) * baseline_ortg_vs_opp.
# Use the vs-others ortg as the baseline the mult perturbs.
# NYK ortg ~125.1 vs others; SAS ortg ~123.7 vs others (per prompt).
ORTG_NYK = 125.1
ORTG_SAS = 123.7
# off_xfg ~ shooting efficiency; a 1% eFG-mult change moves ~ ortg by roughly the same %
# (FG pts are the bulk of points). Conservative: scale full ortg by the mult.
nyk_off_delta = (mult_nyk - 1.0) * ORTG_NYK
sas_off_delta = (mult_sas - 1.0) * ORTG_SAS
# NYK margin perspective: NYK's own offense up = +; SAS offense up = - for NYK
residual_pts_per100 = nyk_off_delta - sas_off_delta
print(f"\nNYK off delta = {nyk_off_delta:+.2f} pts/100 ; SAS off delta = {sas_off_delta:+.2f} pts/100")
print(f"NET residual (NYK margin) = {residual_pts_per100:+.2f} pts/100")

# ---- consistency check: how many of the per-player eFG ratios point same direction? ----
def consistency(det):
    rs = [d["efg_ratio"] for d in det if d["efg_ratio"] is not None]
    up = sum(1 for r in rs if r > 1.02)
    dn = sum(1 for r in rs if r < 0.98)
    return up, dn, len(rs), rs
cu = consistency(det_nyk); cs = consistency(det_sas)
print(f"\nConsistency NYK eFG ratios up/dn/n: {cu[0]}/{cu[1]}/{cu[2]}  values={[round(x,3) for x in cu[3]]}")
print(f"Consistency SAS eFG ratios up/dn/n: {cs[0]}/{cs[1]}/{cs[2]}  values={[round(x,3) for x in cs[3]]}")

out = dict(
    signal="player_level",
    mechanic="off_xfg(player)",
    mult_nyk=round(mult_nyk, 4),
    mult_sas=round(mult_sas, 4),
    raw_nyk=round(raw_off_nyk, 4),
    raw_sas=round(raw_off_sas, 4),
    raw_pts_nyk=round(raw_pts_nyk, 4),
    raw_pts_sas=round(raw_pts_sas, 4),
    n_games=n_games,
    K=K,
    residual_pts_per100=round(residual_pts_per100, 2),
    notes=(
        "Top-5-by-mpg per side; per-player eFG (fgm+0.5*fg3m)/fga vs SAS/NYK over 4 H2H "
        "games divided by same vs all other opponents, minutes-weighted to a team mult. "
        "off_xfg = efficiency (eFG) lever. 4 games/player = tiny -> shrunk HARD K=12 "
        "(w=0.25). DOUBLE-COUNT: this IS largely the generic opponent-defense the sim "
        "already applies per-shot (INTERIOR_D/PERIMETER_D) and via _matchup_mult; the "
        "residual-vs-others form removes the team's OWN quality but NOT the opponent's "
        "generic D, so most of any eFG-suppression vs this opp is ALREADY in the sim. "
        "Inconsistent across players + tiny n -> treat as noise."
    ),
    detail_nyk=det_nyk,
    detail_sas=det_sas,
)
outfp = os.path.join(OUTDIR, "player_level.json")
json.dump(out, open(outfp, "w"), indent=2)
print("\nwrote", outfp)
