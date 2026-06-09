"""build_intel_2026-05-30.py — Intelligence + Monte Carlo engine for WCF Game 6.

OKC @ SAS, tips 2026-05-30 ~8:10pm ET (game_id 0042500316). Series 2-2 thru G4.

Pipeline:
  1. Load per-player q50 + per-stat sigma  (predictions_cache_2026-05-29.parquet)
  2. Shrink q50 toward 4-game WCF series average (model 0.6 / series 0.4)
  3. Monte Carlo 10,000 sims with a shared per-team game-script factor so player
     points are correlated -> realistic team-total + win-prob distribution
  4. Joint / parlay events (SGA, Wemby, team totals, win)
  5. EV + 1/4-Kelly vs every posted line across 7 books (injury-filtered)

Writes data/cache/intel_2026-05-30/  +  prints a console summary.
"""
from __future__ import annotations
import glob
import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

warnings.filterwarnings("ignore")

ROOT = Path(r"C:\Users\neelj\nba-ai-system")
OUT = ROOT / "data" / "cache" / "intel_2026-05-30"
OUT.mkdir(parents=True, exist_ok=True)

PRED = ROOT / "data" / "cache" / "predictions_cache_2026-05-29.parquet"
LINES_DIR = ROOT / "data" / "lines"
INJURY = ROOT / "data" / "cache" / "injury_status_2026-05-29.json"
SERIES = ROOT / "data" / "cache" / "intel_2026-05-26" / "wcf_player_series_avg.csv"
TEAMAGG = ROOT / "data" / "cache" / "intel_2026-05-26" / "wcf_team_series_agg.json"

N_SIMS = 10_000
SHRINK_MODEL = 0.60
SHRINK_SERIES = 0.40
SEED = 20260530
BANKROLL = 10_000.0
KELLY_FRACTION = 0.25
KELLY_CAP = 0.04
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

rng = np.random.default_rng(SEED)


def nkey(s: str) -> str:
    return (str(s).lower().replace(".", "").replace("'", "")
            .replace("-", " ").replace("  ", " ").strip())


def am_to_payout(o: float) -> float:
    if pd.isna(o):
        return float("nan")
    return o / 100.0 if o >= 100 else 100.0 / abs(o)


def am_to_implied(o: float) -> float:
    if pd.isna(o):
        return float("nan")
    return 100.0 / (o + 100.0) if o >= 100 else abs(o) / (abs(o) + 100.0)


# ---------------------------------------------------------------- load preds
preds = pd.read_parquet(PRED)
preds["name_key"] = preds["player_name"].apply(nkey)

# series average map  (player_name, stat) -> series pg
ser = pd.read_csv(SERIES)
ser["name_key"] = ser["player_name"].apply(nkey)
col = {"pts": "pts_pg", "reb": "reb_pg", "ast": "ast_pg", "fg3m": "fg3m_pg",
       "stl": "stl_pg", "blk": "blk_pg", "tov": "tov_pg"}
series_map: dict[tuple[str, str], float] = {}
for _, r in ser.iterrows():
    for st, c in col.items():
        if c in r and pd.notna(r[c]):
            series_map[(r["name_key"], st)] = float(r[c])

# ---------------------------------------------------------------- injuries
inj = json.load(open(INJURY))
out_players, quest_players = set(), {}
for e in inj.get("players", []):
    if e.get("team") in ("OKC", "SAS"):
        k = nkey(e["player_name"])
        if e["status"] == "OUT":
            out_players.add(k)
        elif e["status"] in ("DOUBTFUL", "QUESTIONABLE"):
            quest_players[k] = e["status"]
print(f"OKC/SAS OUT: {sorted(out_players)}")
print(f"OKC/SAS Q/D: {quest_players}")

# ---------------------------------------------------------------- simulate
# shared team game-script factor -> correlation across a team's players
team_factor = {
    "OKC": rng.normal(1.0, 0.085, N_SIMS),
    "SAS": rng.normal(1.0, 0.085, N_SIMS),
}
sims: dict[tuple[str, str], np.ndarray] = {}
mu_used: dict[tuple[str, str], float] = {}
team_of: dict[str, str] = {}

for _, row in preds.iterrows():
    nk, team, st = row["name_key"], row["team"], row["stat"]
    if nk in out_players:
        continue
    team_of[nk] = team
    q50 = float(row["q50"])
    sig = float(row["sigma"]) if row.get("sigma") and row["sigma"] > 0 else max(0.5, abs(q50) * 0.4)
    mu = SHRINK_MODEL * q50 + SHRINK_SERIES * series_map.get((nk, st), q50)
    # idiosyncratic noise + a slice of shared team script (only for scoring-ish)
    tf = team_factor[team] if st in ("pts", "fg3m", "ast") else 1.0
    samp = rng.normal(mu, sig, N_SIMS) * tf
    sims[(nk, st)] = np.clip(samp, 0, None)
    mu_used[(nk, st)] = mu

# ---------------------------------------------------------------- team totals
def team_pts(team: str) -> np.ndarray:
    tot = np.zeros(N_SIMS)
    for (nk, st), arr in sims.items():
        if st == "pts" and team_of.get(nk) == team:
            tot += arr
    return tot

okc_pts, sas_pts = team_pts("OKC"), team_pts("SAS")
total = okc_pts + sas_pts
sas_margin = sas_pts - okc_pts          # SAS home
sas_win = sas_margin > 0

game = {
    "matchup": "OKC @ SAS (Game 6, WCF)", "game_id": "0042500316",
    "tip": "2026-05-30 ~8:10pm ET", "home": "SAS", "away": "OKC",
    "proj_sas_pts": round(float(sas_pts.mean()), 1),
    "proj_okc_pts": round(float(okc_pts.mean()), 1),
    "proj_total": round(float(total.mean()), 1),
    "proj_sas_margin": round(float(sas_margin.mean()), 1),
    "p_sas_win": round(float(sas_win.mean()), 4),
    "p_okc_win": round(float(1 - sas_win.mean()), 4),
    "total_sd": round(float(total.std()), 1),
    "p_total_over_210": round(float((total > 210).mean()), 4),
    "p_total_over_215": round(float((total > 215).mean()), 4),
    "p_total_over_220": round(float((total > 220).mean()), 4),
    "p_sas_cover_-1.5": round(float((sas_margin > 1.5).mean()), 4),
    "p_okc_cover_+1.5": round(float((sas_margin < 1.5).mean()), 4),
    "note": ("Team totals = sum of simulated player PTS w/ shared per-team game-script "
             "factor (sd 8.5%). Pregame player q50 shrunk 0.6/0.4 toward 4-game WCF "
             "series avg. SAS_pts excludes OUT players."),
}
json.dump(game, open(OUT / "game_forecast.json", "w"), indent=2)

# ---------------------------------------------------------------- joint events
def g(name, st):
    return sims.get((nkey(name), st))

joints = {}
sga = g("Shai Gilgeous-Alexander", "pts")
if sga is not None:
    joints["P(SGA 30+ pts)"] = round(float((sga >= 30).mean()), 4)
    joints["P(SGA 25+ pts)"] = round(float((sga >= 25).mean()), 4)
    sga_a = g("Shai Gilgeous-Alexander", "ast")
    joints["P(SGA 25+pts & 6+ast)"] = round(float(((sga >= 25) & (sga_a >= 6)).mean()), 4)
    joints["P(SGA 30+ & OKC win)"] = round(float(((sga >= 30) & ~sas_win).mean()), 4)
wp, wr, wa = g("Victor Wembanyama", "pts"), g("Victor Wembanyama", "reb"), g("Victor Wembanyama", "ast")
wb = g("Victor Wembanyama", "blk")
if wp is not None:
    joints["P(Wemby 30+ pts)"] = round(float((wp >= 30).mean()), 4)
    joints["P(Wemby double-double 10/10)"] = round(float(((wp >= 10) & (wr >= 10)).mean()), 4)
    joints["P(Wemby 25+pts & 12+reb)"] = round(float(((wp >= 25) & (wr >= 12)).mean()), 4)
    joints["P(Wemby triple-double)"] = round(float(((wp >= 10) & (wr >= 10) & (wa >= 10)).mean()), 4)
    if wb is not None:
        joints["P(Wemby 3+ blk)"] = round(float((wb >= 3).mean()), 4)
        joints["P(Wemby 25+pts & 3+blk & SAS win)"] = round(
            float(((wp >= 25) & (wb >= 3) & sas_win).mean()), 4)
fox = g("De'Aaron Fox", "pts")
if fox is not None:
    joints["P(Fox 20+ pts)"] = round(float((fox >= 20).mean()), 4)
json.dump(joints, open(OUT / "joint_events.json", "w"), indent=2)

# ---------------------------------------------------------------- lines + EV
okcsas = set(preds["name_key"].unique())
rows = []
for fp in sorted(glob.glob(str(LINES_DIR / "2026-05-29_*.csv"))):
    book = Path(fp).stem.split("_", 1)[1]
    try:
        df = pd.read_csv(fp, engine="python", on_bad_lines="skip")
    except Exception as e:
        print(f"skip {fp}: {e}"); continue
    need = {"player_name", "stat", "line", "over_price", "under_price"}
    if not need.issubset(df.columns):
        continue
    df = df.copy()
    df["book"] = book
    df["name_key"] = df["player_name"].apply(nkey)
    for c in ("over_price", "under_price", "line"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace("+", "", regex=False), errors="coerce")
    df = df[df["name_key"].isin(okcsas) & df["line"].notna()]
    rows.append(df[["book", "player_name", "name_key", "stat", "line", "over_price", "under_price"]])
all_lines = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

records = []
for _, lr in all_lines.iterrows():
    key = (lr["name_key"], lr["stat"])
    if key not in sims or lr["name_key"] in out_players:
        continue
    s = sims[key]
    line = float(lr["line"])
    p_over = float((s > line).mean())
    p_over = min(max(p_over, 0.005), 0.995)
    p_under = 1.0 - p_over
    for side, price, p in [("OVER", lr["over_price"], p_over), ("UNDER", lr["under_price"], p_under)]:
        if pd.isna(price):
            continue
        payout = am_to_payout(price)
        ev = p * payout - (1 - p)
        kelly = max(0.0, min(KELLY_CAP, (ev / payout if payout > 0 else 0.0) * KELLY_FRACTION))
        records.append({
            "player": lr["player_name"], "team": team_of.get(lr["name_key"], "?"),
            "stat": lr["stat"], "book": lr["book"], "side": side, "line": line,
            "model_mu": round(mu_used[key], 2), "p_win": round(p, 4),
            "odds": int(price), "implied": round(am_to_implied(price), 4),
            "ev_pct": round(ev * 100, 2), "kelly_pct": round(kelly * 100, 3),
            "stake": round(BANKROLL * kelly, 2),
            "q_flag": lr["name_key"] in quest_players,
        })
ev = pd.DataFrame(records)
pos = ev[ev["ev_pct"] > 0].sort_values("ev_pct", ascending=False).reset_index(drop=True)
best = (pos.sort_values(["player", "stat", "ev_pct"], ascending=[True, True, False])
        .groupby(["player", "stat"], as_index=False).first()
        .sort_values("ev_pct", ascending=False).reset_index(drop=True))
ev.to_csv(OUT / "prop_ev_all.csv", index=False)
best.to_csv(OUT / "prop_ev_best_per_prop.csv", index=False)
pos.head(30).to_csv(OUT / "prop_ev_top.csv", index=False)

# ---------------------------------------------------------------- console
print("\n================ GAME FORECAST ================")
for k, v in game.items():
    if k != "note":
        print(f"  {k:22s} {v}")
print("\n================ JOINT EVENTS =================")
for k, v in joints.items():
    print(f"  {k:34s} {v}")
print(f"\n========= TOP 15 PROP EDGES (best book/side, n_books={all_lines['book'].nunique()}) =========")
cols = ["player", "stat", "side", "line", "model_mu", "p_win", "odds", "ev_pct", "kelly_pct", "stake", "book", "q_flag"]
print(best.head(15)[cols].to_string(index=False))
print(f"\nWrote artifacts -> {OUT}")
