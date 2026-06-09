"""build_intel_game7.py — Full pregame simulation for WCF Game 7 (SAS @ OKC).

Series 3-3 -> Game 7 at OKC. This is a PREGAME REPORT SIMULATION that *fuses*
three signals into every player projection, then Monte-Carlo's the game:

  PTS mean  = 0.45*model_q50 + 0.30*series_avg + 0.25*tracking_implied
  other     = 0.60*model_q50 + 0.40*series_avg
  tracking_implied = (pts the player scored per matchup-minute vs THIS opponent's
                      coverage, from the CV defensive-matchup layer) * series min_pg

Team totals are series-anchored (fixes the summed-prop variance blow-up):
  team_mean = 0.5*sum(player_pts_mu) + 0.5*series_ppg  (+2 home court to OKC)
  total ~ correlated Normal(team_mean, sd=13)

Outputs -> data/cache/intel_game7/
"""
from __future__ import annotations
import glob, json
from pathlib import Path
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"C:\Users\neelj\nba-ai-system")
OUT = ROOT / "data" / "cache" / "intel_game7"
OUT.mkdir(parents=True, exist_ok=True)
I26 = ROOT / "data" / "cache" / "intel_2026-05-26"

PRED = ROOT / "data" / "cache" / "predictions_cache_game7.parquet"
SERIES = I26 / "wcf_player_series_avg_6g.csv"   # updated through Games 1-6
# Hobbled / limited for Game 7 (left hamstring: OUT G5, 10 min in G6) — excluded
# from headline props, tracked as a swing factor.
LIMITED = {"jalen williams"}
# 6-game team scoring (G1-6 finals): OKC 115/122/123/82/127/91, SAS 122/113/108/103/114/118
OKC_PPG_6, SAS_PPG_6 = 110.0, 113.0
DEFMATCH = I26 / "wcf_defensive_matchups.csv"
TEAMAGG = I26 / "wcf_team_series_agg.json"
INJURY = ROOT / "data" / "cache" / "injury_status_2026-05-29.json"
LINES_DIR = ROOT / "data" / "lines"

N = 10_000
SEED = 20260601
HOME = "OKC"
rng = np.random.default_rng(SEED)


def nkey(s):
    return str(s).lower().replace(".", "").replace("'", "").replace("-", " ").replace("  ", " ").strip()


def am_payout(o):
    return float("nan") if pd.isna(o) else (o / 100.0 if o >= 100 else 100.0 / abs(o))


def am_implied(o):
    return float("nan") if pd.isna(o) else (100.0 / (o + 100.0) if o >= 100 else abs(o) / (abs(o) + 100.0))


# ---- load preds
preds = pd.read_parquet(PRED)
preds["name_key"] = preds["player_name"].apply(nkey)

# ---- series averages
ser = pd.read_csv(SERIES); ser["name_key"] = ser["player_name"].apply(nkey)
col = {"pts": "pts_pg", "reb": "reb_pg", "ast": "ast_pg", "fg3m": "fg3m_pg", "stl": "stl_pg", "blk": "blk_pg", "tov": "tov_pg"}
series_map, minpg = {}, {}
for _, r in ser.iterrows():
    minpg[r["name_key"]] = float(r["min_pg"]) if pd.notna(r["min_pg"]) else 0.0
    for st, c in col.items():
        if c in r and pd.notna(r[c]):
            series_map[(r["name_key"], st)] = float(r[c])

# ---- TRACKING: matchup-efficiency overlay (bounded multiplier, NOT a volume estimate)
# minutes-weighted FG% the player shot vs the opponent's defenders, relative to a
# 0.47 baseline -> bounded scoring multiplier in [0.90, 1.10]. This is the honest
# way to fold the CV matchup layer in: it says "this coverage runs them hot/cold",
# it does NOT try to reconstruct total points from partial matchup minutes.
FG_BASE = 0.47
dm = pd.read_csv(DEFMATCH)
dm["off_key"] = dm["off_player_name"].apply(nkey)
track_mult, track_detail = {}, {}
for nk, grp in dm.groupby("off_key"):
    tot_min = grp["matchup_min"].sum()
    tot_fga = grp["fga_allowed"].sum()
    fgm = grp["fgm_allowed"].sum()
    if tot_min < 6 or tot_fga < 8:
        continue
    fg_allowed = float(fgm / tot_fga)
    mult = float(np.clip(1.0 + 0.6 * (fg_allowed - FG_BASE), 0.90, 1.10))
    track_mult[nk] = mult
    prim = grp.loc[grp["matchup_min"].idxmax()]
    track_detail[nk] = {
        "primary_def": prim["def_player_name"], "matchup_min": round(float(tot_min), 1),
        "fg_pct_allowed": round(fg_allowed, 3), "scoring_mult": round(mult, 3),
    }
json.dump(track_detail, open(OUT / "tracking_overlay.json", "w"), indent=2)

# ---- injuries
inj = json.load(open(INJURY))
out_players = {nkey(e["player_name"]) for e in inj.get("players", [])
               if e.get("team") in ("OKC", "SAS") and e["status"] == "OUT"}
out_players |= LIMITED   # treat hobbled Jalen Williams as off the prop board

# ---- fuse means
team_agg = json.load(open(TEAMAGG))
sims, mu_used, team_of, fusion_rows = {}, {}, {}, []
for _, row in preds.iterrows():
    nk, team, st = row["name_key"], row["team"], row["stat"]
    if nk in out_players:
        continue
    team_of[nk] = team
    q50 = float(row["q50"])
    sig = float(row["sigma"]) if row.get("sigma") and row["sigma"] > 0 else max(0.5, abs(q50) * 0.4)
    s_avg = series_map.get((nk, st), q50)
    if st == "pts":
        # PTS leans a bit more on observed series output (model runs conservative on stars)
        base = 0.45 * q50 + 0.55 * s_avg
        mult = track_mult.get(nk, 1.0)
        mu = base * mult
        if nk in track_mult:
            fusion_rows.append({"player": row["player_name"], "team": team,
                                "model_q50": round(q50, 1), "series_avg": round(s_avg, 1),
                                "base_blend": round(base, 1),
                                "track_mult": round(mult, 3),
                                "primary_def": track_detail[nk]["primary_def"],
                                "fg%_allowed": track_detail[nk]["fg_pct_allowed"],
                                "fused_mu": round(mu, 1)})
    else:
        mu = 0.60 * q50 + 0.40 * s_avg
    samp = np.clip(rng.normal(mu, sig, N), 0, None)
    sims[(nk, st)] = samp
    mu_used[(nk, st)] = mu

pd.DataFrame(fusion_rows).sort_values("fused_mu", ascending=False).to_csv(OUT / "pts_fusion.csv", index=False)

# ---- team totals: series-anchored, correlated
def sum_mu(team):
    return sum(mu_used[(nk, "pts")] for (nk, st) in mu_used if st == "pts" and team_of.get(nk) == team)

okc_ppg = OKC_PPG_6
sas_ppg = SAS_PPG_6
okc_mean = 0.5 * sum_mu("OKC") + 0.5 * okc_ppg + (2.0 if HOME == "OKC" else 0.0)
sas_mean = 0.5 * sum_mu("SAS") + 0.5 * sas_ppg + (2.0 if HOME == "SAS" else 0.0)
SD = 13.0
z = rng.multivariate_normal([0, 0], [[1, 0.15], [0.15, 1]], N)  # mild positive (pace) corr
okc_pts = okc_mean + SD * z[:, 0]
sas_pts = sas_mean + SD * z[:, 1]
total = okc_pts + sas_pts
okc_margin = okc_pts - sas_pts
okc_win = okc_margin > 0

game = {
    "matchup": "SAS @ OKC — GAME 7 (WCF, series 3-3)", "game_id": "0042500317",
    "home": "OKC", "away": "SAS", "venue": "Oklahoma City",
    "proj_okc_pts": round(float(okc_pts.mean()), 1), "proj_sas_pts": round(float(sas_pts.mean()), 1),
    "proj_total": round(float(total.mean()), 1), "proj_okc_margin": round(float(okc_margin.mean()), 1),
    "p_okc_win": round(float(okc_win.mean()), 4), "p_sas_win": round(float(1 - okc_win.mean()), 4),
    "total_sd": round(float(total.std()), 1),
    "p_total_over_210": round(float((total > 210).mean()), 4),
    "p_total_over_215": round(float((total > 215).mean()), 4),
    "p_total_over_220": round(float((total > 220).mean()), 4),
    "okc_mean_components": {"sum_player_mu": round(sum_mu("OKC"), 1), "series_ppg": okc_ppg, "home_court": 2.0},
    "sas_mean_components": {"sum_player_mu": round(sum_mu("SAS"), 1), "series_ppg": sas_ppg},
}
json.dump(game, open(OUT / "game_forecast.json", "w"), indent=2)

# ---- joints
def g(name, st):
    return sims.get((nkey(name), st))

J = {}
sga, sga_a = g("Shai Gilgeous-Alexander", "pts"), g("Shai Gilgeous-Alexander", "ast")
if sga is not None:
    J["P(SGA 30+ pts)"] = round(float((sga >= 30).mean()), 4)
    J["P(SGA 25+ pts & 6+ ast)"] = round(float(((sga >= 25) & (sga_a >= 6)).mean()), 4)
    J["P(SGA 30+ & OKC win)"] = round(float(((sga >= 30) & okc_win).mean()), 4)
wp, wr, wa, wb = (g("Victor Wembanyama", s) for s in ("pts", "reb", "ast", "blk"))
if wp is not None:
    J["P(Wemby 30+ pts)"] = round(float((wp >= 30).mean()), 4)
    J["P(Wemby double-double)"] = round(float(((wp >= 10) & (wr >= 10)).mean()), 4)
    J["P(Wemby 25+pts & 12+reb)"] = round(float(((wp >= 25) & (wr >= 12)).mean()), 4)
    J["P(Wemby 3+ blk)"] = round(float((wb >= 3).mean()), 4)
    J["P(Wemby DD & SAS win)"] = round(float(((wp >= 10) & (wr >= 10) & ~okc_win).mean()), 4)
jw = g("Jalen Williams", "pts")
if jw is not None:
    J["P(Jalen Williams 15+ pts)"] = round(float((jw >= 15).mean()), 4)
json.dump(J, open(OUT / "joint_events.json", "w"), indent=2)

# ---- EV vs most-recent available lines (G6 proxy — flagged provisional)
okcsas = set(preds["name_key"].unique())
rows = []
for fp in sorted(glob.glob(str(LINES_DIR / "2026-05-29_*.csv"))):
    book = Path(fp).stem.split("_", 1)[1]
    try:
        df = pd.read_csv(fp, engine="python", on_bad_lines="skip")
    except Exception:
        continue
    if not {"player_name", "stat", "line", "over_price", "under_price"}.issubset(df.columns):
        continue
    df = df.copy(); df["book"] = book; df["name_key"] = df["player_name"].apply(nkey)
    for c in ("over_price", "under_price", "line"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace("+", "", regex=False), errors="coerce")
    df = df[df["name_key"].isin(okcsas) & df["line"].notna()]
    rows.append(df[["book", "player_name", "name_key", "stat", "line", "over_price", "under_price"]])
all_lines = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

rec = []
for _, lr in all_lines.iterrows():
    key = (lr["name_key"], lr["stat"])
    if key not in sims or lr["name_key"] in out_players:
        continue
    s = sims[key]; line = float(lr["line"])
    p_over = min(max(float((s > line).mean()), .005), .995); p_under = 1 - p_over
    for side, price, p in [("OVER", lr["over_price"], p_over), ("UNDER", lr["under_price"], p_under)]:
        if pd.isna(price):
            continue
        payout = am_payout(price); ev = p * payout - (1 - p)
        rec.append({"player": lr["player_name"], "team": team_of.get(lr["name_key"], "?"),
                    "stat": lr["stat"], "book": lr["book"], "side": side, "line": line,
                    "fused_mu": round(mu_used[key], 2), "p_win": round(p, 4), "odds": int(price),
                    "implied": round(am_implied(price), 4), "ev_pct": round(ev * 100, 2)})
ev = pd.DataFrame(rec)
best = (ev[ev.ev_pct > 0].sort_values(["player", "stat", "ev_pct"], ascending=[True, True, False])
        .groupby(["player", "stat"], as_index=False).first().sort_values("ev_pct", ascending=False))
ev.to_csv(OUT / "prop_ev_all.csv", index=False)
best.to_csv(OUT / "prop_ev_best.csv", index=False)

# ---- console
print("\n=========== GAME 7 FORECAST (SAS @ OKC) ===========")
for k, v in game.items():
    if "components" not in k:
        print(f"  {k:20s} {v}")
print("\n=========== TRACKING-FUSED PTS (model+series blend x matchup mult) ===========")
fz = pd.DataFrame(fusion_rows).sort_values("fused_mu", ascending=False)
print(fz.to_string(index=False))
print("\n=========== JOINT EVENTS ===========")
for k, v in J.items():
    print(f"  {k:34s} {v}")
print(f"\nWrote -> {OUT}")
