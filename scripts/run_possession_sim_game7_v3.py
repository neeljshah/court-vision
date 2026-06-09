"""
run_possession_sim_game7_v3.py — WCF Game 7 SAS @ OKC possession Monte Carlo (v3).

v3 upgrade over v2: USAGE-AWARE ASSIST ATTRIBUTION.
  v2 heuristic: ast = 30% of a player's OWN made shots, credited to a RANDOM teammate.
    -> every player ends ~0.7-0.8 ast regardless of role (SGA == Biyombo). Wrong.
  v3 learned: per-team, total assists = sum over shooters of (made_FG * P(assisted|shooter)),
    then distributed to teammates weighted by each teammate's empirical ast-share
    (assist_rates.json, built from 510 PBP games). SGA/Castle/Fox get the assists;
    finishers (Holmgren, Dort, Wemby) get few. This matches real playmaker structure.

  Reuses v2 seed recipe, pace, OREB, and pts calibration EXACTLY for comparability.
  pts/reb/stl/blk distributions are IDENTICAL to v2 (same RNG seed=42, same sim) —
  ONLY the assist channel is replaced, so any ast improvement is isolated and honest.

Output: data/cache/intel_game7/possession_sim_v3.json  (NEVER overwrites v2)
Models: data/models/sim_subsModels_v3/assist_rates.json
"""
from __future__ import annotations
import json, os, re, sys
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.simulation.game_simulator import GameSimulator, GameSimResult
import src.simulation.game_simulator as _sim_module

# Reuse v2 roster/seed/config by importing its module-level constants + seed builder.
import importlib.util
_spec = importlib.util.spec_from_file_location("v2runner", ROOT / "scripts" / "run_possession_sim_game7.py")

# ── Rosters / config (mirror v2 exactly) ──────────────────────────────────────
OKC_LINEUP = ["1628983","1631096","1628392","1641717","1629652","1642272",
              "1627936","1629026","1631119","1630198","1630598"]
SAS_LINEUP = ["1641705","1628368","1642264","1630170","1642844","1629640",
              "1628436","203084","1630577","202687"]
PLAYER_DISPLAY = {
    "1628983":"Shai Gilgeous-Alexander","1631096":"Chet Holmgren","1628392":"Isaiah Hartenstein",
    "1641717":"Cason Wallace","1629652":"Luguentz Dort","1642272":"Jared McCain",
    "1627936":"Alex Caruso","1629026":"Kenrich Williams","1631119":"Jaylin Williams",
    "1630198":"Isaiah Joe","1630598":"Aaron Wiggins","1641705":"Victor Wembanyama",
    "1628368":"De'Aaron Fox","1642264":"Stephon Castle","1630170":"Devin Vassell",
    "1642844":"Dylan Harper","1629640":"Keldon Johnson","1628436":"Luke Kornet",
    "203084":"Harrison Barnes","1630577":"Julian Champagnie","202687":"Bismack Biyombo",
}
OKC_TEAM_STATS = {"pace":97.7,"off_rtg":108.0,"def_rtg":109.0,"oreb_pct":0.30}
SAS_TEAM_STATS = {"pace":97.7,"off_rtg":109.0,"def_rtg":108.0,"oreb_pct":0.33}
PROP_LINES = {"1628983":{"pts":27.5},"1641705":{"pts":27.5,"reb":13.5,"blk":3.5},
              "1628368":{"pts":15.5},"1631096":{"reb":8.5},"1642264":{"pts":17.5},"1642844":{"pts":9.5}}
KEY_PLAYERS = ["1628983","1641705","1631096","1642264","1628368","1642272","1642844"]
REPORT_STATS = ["pts","reb","ast"]
CALIB_FACTOR = 1.1702

# ── v2 seed builder (reuse its data loaders) ──────────────────────────────────
def _norm_name(name): return re.sub(r"[^a-z0-9 ]","",str(name).lower()).strip()

def load_season_avgs():
    raw = json.load(open(ROOT/"data"/"nba"/"player_avgs_2025-26.json"))
    by_id={}; by_name={}
    for nk,data in raw.items():
        pid=str(int(data.get("player_id",0)))
        if pid and pid!="0": by_id[pid]=data
        by_name[_norm_name(nk)]=data
    return by_id,by_name

def load_playoff_avgs():
    df=pd.read_csv(ROOT/"data"/"cache"/"intel_2026-05-26"/"wcf_player_series_avg_6g.csv")
    return {str(int(r["player_id"])): r.to_dict() for _,r in df.iterrows()}

SEASON_BY_ID,SEASON_BY_NAME = load_season_avgs()
PLAYOFF_BY_ID = load_playoff_avgs()

def build_blended_seed(pid):
    defaults={"pts":10.0,"reb":4.0,"ast":2.0,"fg3m":0.8,"stl":0.7,"blk":0.3,"tov":1.5,
              "min":22.0,"fga":7.0,"fg_pct":0.45,"ft_pct":0.77,"fta":2.0,"fg3_pct":0.35,"usage_rate":0.20}
    seed=dict(defaults)
    sd=SEASON_BY_ID.get(pid)
    if sd is not None:
        for k in ["pts","reb","ast","tov","fg3m","stl","blk","min","fg_pct","fg3_pct","ft_pct","fta"]:
            v=sd.get(k)
            if v is not None: seed[k]=float(v)
        if seed["fg_pct"]>0: seed["fga"]=max(seed["pts"]/seed["fg_pct"]*0.5,3.0)
        seed["usage_rate"]=min(seed["pts"]/max(seed["min"],1.0)*22.0/110.0,0.40)
    po=PLAYOFF_BY_ID.get(pid)
    if po is not None:
        pmap={"pts_pg":"pts","reb_pg":"reb","ast_pg":"ast","tov_pg":"tov","fg3m_pg":"fg3m",
              "stl_pg":"stl","blk_pg":"blk","min_pg":"min","fga_pg":"fga","fta_pg":"fta"}
        povals={}
        for s,dn in pmap.items():
            v=po.get(s)
            if v is not None and not (isinstance(v,float) and np.isnan(v)): povals[dn]=float(v)
        usg=po.get("usg_pct_pg")
        if usg is not None and not (isinstance(usg,float) and np.isnan(usg)): povals["usage_rate"]=float(usg)/100.0
        if sd is not None:
            for k,v in povals.items():
                if k in seed: seed[k]=0.5*seed[k]+0.5*v
        else:
            for k,v in povals.items(): seed[k]=v
    seed["player_id"]=pid
    return seed

def _patched_load_player_seed(player_id, season):
    return build_blended_seed(str(player_id))

_sim_module._load_player_seed = _patched_load_player_seed
OREB_RATE=(OKC_TEAM_STATS["oreb_pct"]+SAS_TEAM_STATS["oreb_pct"])/2.0
_sim_module._OREB_RATE = OREB_RATE
PACE=(OKC_TEAM_STATS["pace"]+SAS_TEAM_STATS["pace"])/2.0
N_SIMS=10_000

# ── v3 ASSIST MODEL ───────────────────────────────────────────────────────────
ASSIST_RATES = json.load(open(ROOT/"data"/"models"/"sim_subsModels_v3"/"assist_rates.json"))
SUBS_META    = json.load(open(ROOT/"data"/"models"/"sim_subsModels_v3"/"meta.json"))
LEAGUE_ASSISTED_SHARE = SUBS_META["league_assisted_share"]

def _ast_key(pid):
    """Map player_id -> normalized last-name key used in assist_rates.json."""
    nm = PLAYER_DISPLAY.get(pid, "")
    if not nm: return None
    return _norm_name(nm).split()[-1] if nm else None

def player_assisted_share(pid):
    k=_ast_key(pid); r=ASSIST_RATES.get(k) if k else None
    if r and r.get("made_pg",0)>0: return float(r["assisted_share"])
    return LEAGUE_ASSISTED_SHARE

def player_ast_weight(pid):
    """Empirical assists-generated-per-game = the teammate's share weight for credit."""
    k=_ast_key(pid); r=ASSIST_RATES.get(k) if k else None
    if r: return max(float(r.get("ast_pg",0.0)), 0.0)
    return 0.0

def recompute_assists(result: GameSimResult, lineup, n_sims, rng):
    """
    Replace v2's flat-random assist credit with a usage-aware empirical model.

    For each sim, per team:
      assists_generated[shooter] = Binomial(made_FG[shooter], assisted_share[shooter])
      total team assists = sum over shooters
      distribute total to teammates weighted by ast_weight (empirical ast/g);
        a player cannot assist their own basket -> exclude self from credit pool
        proportionally per assisting bucket.
    Implemented per-shooter: each shooter's assisted makes are credited to OTHER teammates
      by ast_weight (so a made FG by SGA can be assisted by Hartenstein etc.).
    Returns dict pid -> ast array (n_sims,).
    """
    # made-FG proxy per player per sim: derive from pts (each made FG = 2 or 3).
    # We have fg3m array; approx made = round((pts - 3*fg3m)/2) + fg3m  (clip >=0)
    made = {}
    for pid in lineup:
        ps = result.player_stats.get(pid, {})
        pts = ps.get("pts", np.zeros(n_sims))
        fg3 = ps.get("fg3m", np.zeros(n_sims))
        two_made = np.clip((pts - 3.0*fg3) / 2.0, 0, None)
        made[pid] = np.round(two_made + fg3).astype(int)

    # assist weights (exclude self per shooter)
    weights = {pid: player_ast_weight(pid) for pid in lineup}
    ashare  = {pid: player_assisted_share(pid) for pid in lineup}

    ast_out = {pid: np.zeros(n_sims) for pid in lineup}
    for shooter in lineup:
        m = made[shooter]                      # (n_sims,)
        # assisted makes for this shooter
        assisted = rng.binomial(m, ashare[shooter])   # (n_sims,)
        # teammate credit pool (exclude shooter)
        teammates = [p for p in lineup if p != shooter]
        w = np.array([weights[p] for p in teammates], dtype=float)
        if w.sum() <= 0:
            w = np.ones(len(teammates))
        w = w / w.sum()
        # distribute each sim's assisted count via multinomial
        # vectorize: for each sim draw multinomial(assisted[s], w)
        # np.random multinomial needs per-n call; do grouped by unique assisted counts for speed
        uniq = np.unique(assisted)
        alloc = np.zeros((len(teammates), n_sims))
        for cnt in uniq:
            if cnt == 0: continue
            idx = np.where(assisted == cnt)[0]
            draws = rng.multinomial(cnt, w, size=len(idx))   # (len(idx), n_teammates)
            alloc[:, idx] = draws.T
        for ti, tp in enumerate(teammates):
            ast_out[tp] += alloc[ti]
    return ast_out

# ── Run sim (identical to v2) ────────────────────────────────────────────────
print(f"Running {N_SIMS:,} sims (v3, usage-aware assists)...")
sim = GameSimulator(season="2025-26")
result = sim.simulate_game(home_lineup=OKC_LINEUP, away_lineup=SAS_LINEUP,
                           n_sims=N_SIMS, cv_features={}, pace_override=PACE)

# Recompute assists per team with the learned model (fresh rng, deterministic)
rng = np.random.default_rng(seed=2026)
ast_home = recompute_assists(result, OKC_LINEUP, N_SIMS, rng)
ast_away = recompute_assists(result, SAS_LINEUP, N_SIMS, rng)
new_ast = {**ast_home, **ast_away}
for pid, arr in new_ast.items():
    if pid in result.player_stats:
        result.player_stats[pid]["ast"] = np.clip(arr, 0, 18)

# ── Build output (mirror v2 structure) ───────────────────────────────────────
def arr_stats(a):
    return {"mean":round(float(np.mean(a)),3),"std":round(float(np.std(a)),3),
            "p10":round(float(np.percentile(a,10)),3),"p50":round(float(np.median(a)),3),
            "p90":round(float(np.percentile(a,90)),3)}

spread_arr=result.spread_distribution; total_arr=result.total_distribution
calib_total=total_arr*CALIB_FACTOR
total_stats=arr_stats(total_arr)
total_stats.update({"calibrated_mean":round(float(np.mean(calib_total)),1),
    "calibrated_std":round(float(np.std(calib_total)),1),
    "calibrated_p10":round(float(np.percentile(calib_total,10)),1),
    "calibrated_p50":round(float(np.median(calib_total)),1),
    "calibrated_p90":round(float(np.percentile(calib_total,90)),1)})

PLAYER_SEED_PTS={pid: float(build_blended_seed(pid)["pts"]) for pid in KEY_PLAYERS}
def ppcf(pid,raw):
    sp=PLAYER_SEED_PTS.get(pid)
    if sp is None or raw<0.5: return CALIB_FACTOR
    return sp/raw

per_player={}; ppc_factors={}
for pid in KEY_PLAYERS:
    ps=result.player_stats.get(pid,{})
    if not ps: continue
    entry={}
    for stat in REPORT_STATS:
        arr=ps.get(stat)
        if arr is None or len(arr)==0: continue
        rs=arr_stats(arr)
        if stat=="pts":
            f=ppcf(pid,rs["mean"]); ppc_factors[pid]=round(f,4)
            cs=arr_stats(arr*f)
            rs.update({"calibrated_mean":cs["mean"],"calibrated_std":cs["std"],
                       "calibrated_p10":cs["p10"],"calibrated_p50":cs["p50"],"calibrated_p90":cs["p90"]})
        entry[stat]=rs
    per_player[pid]={"name":PLAYER_DISPLAY.get(pid,pid),"stats":entry,
                     "seed_pts":PLAYER_SEED_PTS.get(pid),"per_player_calib_factor":ppc_factors.get(pid)}

prop_results={}
for pid,lines in PROP_LINES.items():
    prop_results[pid]={"name":PLAYER_DISPLAY.get(pid,pid),"props":{}}
    ps=result.player_stats.get(pid,{})
    for stat,line in lines.items():
        arr=ps.get(stat)
        if arr is None or len(arr)==0:
            entry={"line":line,"p_over":0.5,"p_under":0.5,"p_over_calibrated":0.5,"note":"no data"}
        else:
            p_over=float(np.mean(arr>line))
            if stat=="pts":
                f=ppc_factors.get(pid,CALIB_FACTOR); poc=float(np.mean(arr*f>line))
                note=f"calib factor={f:.3f} (seed {PLAYER_SEED_PTS.get(pid,0):.1f} / raw {np.mean(arr):.1f})"
            else:
                poc=p_over; note=None
            entry={"line":line,"p_over":round(p_over,4),"p_under":round(1.0-p_over,4),"p_over_calibrated":round(poc,4)}
            if stat=="blk": entry["note"]="blk from per-min Poisson model; no pts-calibration applied"
            elif note: entry["note"]=note
        prop_results[pid]["props"][stat]=entry

output={
    "engine_used":"src/simulation/game_simulator.py — GameSimulator (Block F) + v3 usage-aware assist model",
    "version":"v3",
    "v3_changes":"Replaced flat-30%-random assist heuristic with empirical usage-aware assist attribution (sim_subsModels_v3/assist_rates.json from 510 PBP games). pts/reb/stl/blk identical to v2.",
    "seed_recipe":"0.5 * player_avgs_2025-26.json + 0.5 * wcf_player_series_avg_6g.csv (players in 6g file); season-only otherwise",
    "game":"WCF Game 7: SAS @ OKC, 2026-05-30, OKC home","n_sims":N_SIMS,"home":"OKC","away":"SAS",
    "home_lineup":OKC_LINEUP,"away_lineup":SAS_LINEUP,
    "home_win_prob":round(result.home_win_prob,4),"away_win_prob":round(1.0-result.home_win_prob,4),
    "total":total_stats,"spread":arr_stats(spread_arr),
    "spread_prob":{"okc_minus_3":round(result.spread_probability(-3.0),4),"okc_minus_5":round(result.spread_probability(-5.0),4),
                   "okc_plus_3":round(result.spread_probability(3.0),4),"okc_plus_5":round(result.spread_probability(5.0),4)},
    "total_prob":{"over_205":round(result.total_probability(205.0,over=True),4),
                  "over_210":round(result.total_probability(210.0,over=True),4),
                  "over_215":round(result.total_probability(215.0,over=True),4)},
    "per_player":per_player,"prop_lines":prop_results,
    "assist_model":{
        "source":"data/models/sim_subsModels_v3/assist_rates.json (510 PBP games, 539 players)",
        "method":"per-shooter Binomial(made_FG, P(assisted|shooter)) credited to teammates by empirical ast/g weight",
        "league_assisted_share":LEAGUE_ASSISTED_SHARE,
    },
    "team_stats_provided":{"OKC":OKC_TEAM_STATS,"SAS":SAS_TEAM_STATS},
    "calibration":{"factor":CALIB_FACTOR,
        "rationale":"Same 1.1702x pts factor as v2 for comparability. Assist channel now learned, not calibrated."},
}
OUT=ROOT/"data"/"cache"/"intel_game7"/"possession_sim_v3.json"
json.dump(output, open(OUT,"w"), indent=2,
          default=lambda x: float(x) if isinstance(x,(np.floating,np.integer)) else x)
print(f"Saved {OUT}")
print("\n=== v3 per-player AST (key players) ===")
for pid in KEY_PLAYERS:
    a=result.player_stats.get(pid,{}).get("ast")
    if a is not None:
        print(f"  {PLAYER_DISPLAY[pid]:26s} ast mean={a.mean():.2f} p50={np.median(a):.0f} p90={np.percentile(a,90):.0f}")
