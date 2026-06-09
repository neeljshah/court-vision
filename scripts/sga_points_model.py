"""
sga_points_model.py — the OTHER half of the duel.
Shai Gilgeous-Alexander points for WCF G7 as a structured distribution.

Grounded in real matchup tracking: Castle (primary, 46.7% allowed) + Vassell (29.4% LOCKDOWN)
have held SGA to 24.3/g on 52.7% TS across the series (vs his ~32 PPG / ~63% TS season norm).
The 27.5 line prices a bounce-back toward his season mean; the matchup data says the wall persists.
SGA differs from Wemby: guard => low foul-out risk, high FT floor (8.5 FTA/g) => higher floor, thinner left tail.
"""
import json, numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "intel_game7"
RNG = np.random.default_rng(20260530)
N = 200_000

SERIES_PTS, SERIES_MIN = 24.333, 37.006
BASE_RATE = SERIES_PTS / SERIES_MIN          # 0.658 pts/floor-min (SAS-suppressed)

# REAL coverage (wcf_defensive_matchups.csv, SGA as offense):
COVERAGE = {
    "castle_primary":  {"mult": (0.98, 0.14), "share_g7": 0.50},  # 46.7% allowed (the wall, large n)
    "vassell_lockdown":{"mult": (0.74, 0.12), "share_g7": 0.20},  # 29.4% allowed (shutdown)
    "wing_switch":     {"mult": (1.12, 0.20), "share_g7": 0.22},  # Harper/Champagnie/Bryant -> supernova path
    "wemby_switch":    {"mult": (1.02, 0.20), "share_g7": 0.08},  # SGA hunts Wemby; length held 33% but FTs
}
FT_FLOOR = (6.6, 2.2)   # ~8.5 FTA * ~0.78 => high, low-variance points floor (raises the left side)

P_FOUL, P_BLOWOUT = 0.06, 0.28        # guard: low foul-out risk; blowout-managed risk same as series
MIN_FOUL   = (33.0, 3.0)
MIN_BLOWOUT= (33.5, 3.0)
MIN_COMP   = (38.5, 2.0)
G7_INTENSITY = (1.00, 0.06)           # series line already reflects playoff intensity; no extra haircut
SHOT_NOISE_SD = 5.2                   # real series swing was 32(G5)->15(G6); wide

def draw_minutes(n, p_foul=P_FOUL, p_blowout=P_BLOWOUT, rng=RNG):
    u = rng.random(n); m = np.empty(n)
    foul = u < p_foul; blow = (u >= p_foul) & (u < p_foul + p_blowout); comp = u >= p_foul + p_blowout
    m[foul] = rng.normal(*MIN_FOUL, foul.sum()); m[blow] = rng.normal(*MIN_BLOWOUT, blow.sum()); m[comp] = rng.normal(*MIN_COMP, comp.sum())
    return np.clip(m, 14, 46), np.where(foul, 0, np.where(blow, 1, 2))

def draw_cov(n, shares=None, rng=RNG):
    shares = shares or {k: v["share_g7"] for k, v in COVERAGE.items()}
    keys = list(shares); s = np.array([shares[k] for k in keys]); s /= s.sum()
    pick = rng.choice(len(keys), size=n, p=s); mult = np.empty(n)
    for i, k in enumerate(keys):
        mu, sd = COVERAGE[k]["mult"]; sel = pick == i; mult[sel] = rng.normal(mu, sd, sel.sum())
    return np.clip(mult, 0.45, 2.0)

def simulate(n=N, p_foul=P_FOUL, p_blowout=P_BLOWOUT, shares=None, base=BASE_RATE, intensity=G7_INTENSITY, rng=RNG, fixed=None):
    fixed = fixed or {}
    mins, state = draw_minutes(n, p_foul, p_blowout, rng)
    if "minutes" in fixed: mins = np.full(n, fixed["minutes"]); state = np.full(n, 2)
    cov = draw_cov(n, shares, rng)
    if "coverage" in fixed: cov = np.full(n, fixed["coverage"])
    inten = rng.normal(*intensity, n)
    if "intensity" in fixed: inten = np.full(n, fixed["intensity"])
    ft = np.clip(rng.normal(*FT_FLOOR, n), 0, None)
    if "ft" in fixed: ft = np.full(n, FT_FLOOR[0])
    noise = rng.normal(0, SHOT_NOISE_SD, n)
    if "noise" in fixed: noise = np.zeros(n)
    field = mins * base * cov * inten * 0.74   # ~74% of his pts are field (rest FTs, modeled separately)
    return np.clip(field + ft + noise, 0, None), state

def describe(p):
    return {"mean": round(float(p.mean()),2), "median": round(float(np.median(p)),2), "std": round(float(p.std()),2),
            "p10": round(float(np.percentile(p,10)),1), "p25": round(float(np.percentile(p,25)),1),
            "p50": round(float(np.percentile(p,50)),1), "p75": round(float(np.percentile(p,75)),1),
            "p90": round(float(np.percentile(p,90)),1),
            "P(over_27.5)": round(float((p>27.5).mean()),3), "P(over_26.5)": round(float((p>26.5).mean()),3),
            "P(>=30)": round(float((p>=30).mean()),3), "P(>=20)": round(float((p>=20).mean()),3)}

def main():
    pts, state = simulate(); d = describe(pts)
    modes = {"foul/managed_left": describe(pts[state==0]), "blowout_managed": describe(pts[state==1]), "competitive": describe(pts[state==2])}
    var_total = float(pts.var()); means = {"minutes":36.8,"coverage":0.96,"intensity":0.965,"ft":FT_FLOOR[0],"noise":0.0}; contrib={}
    for dd in ["minutes","coverage","intensity","ft","noise"]:
        p2,_ = simulate(fixed={dd: means[dd]}); contrib[dd]=max(0.0, var_total-float(p2.var()))
    tot=sum(contrib.values()) or 1.0
    vdec={k:{"pct":round(100*contrib[k]/tot,1)} for k in sorted(contrib,key=contrib.get,reverse=True)}
    bm=d["median"]; levers={}
    p,_=simulate(shares={"castle_primary":0.62,"vassell_lockdown":0.28,"wing_switch":0.08,"wemby_switch":0.02})
    levers["sas_locks_in_castle+vassell"]={"delta_median":round(describe(p)["median"]-bm,2),"note":"SAS doubles down on the wall -> SGA suppressed further"}
    p,_=simulate(p_blowout=0.55); levers["blowout_likely"]={"delta_median":round(describe(p)["median"]-bm,2),"note":"managed Q4 minutes"}
    p,_=simulate(shares={"castle_primary":0.38,"vassell_lockdown":0.12,"wing_switch":0.38,"wemby_switch":0.12})
    levers["sas_in_foul_trouble"]={"delta_median":round(describe(p)["median"]-bm,2),"note":"if Castle/Vassell foul-limited -> weaker coverage -> SGA up"}
    out={"player":"Shai Gilgeous-Alexander","game":"WCF G7","line_market":27.5,"alt_line":26.5,"n_sims":N,
         "distribution":d,"scenario_modes":modes,"variance_decomposition_ranked":vdec,
         "coverage_model_real_data":{k:{"share_g7":v["share_g7"],"eff_mult":v["mult"][0]} for k,v in COVERAGE.items()},
         "counterfactual_levers":levers,
         "honest_notes":["Anchored to series 24.3 pts/37 min (SAS-suppressed). Books' 27.5 prices regression to his ~32 season mean; matchup data says the Castle/Vassell wall persists -> lean UNDER.",
                         "Coverage shares/effs from real matchup tracking; minute/foul priors documented."]}
    (CACHE/"sga_points_showcase.json").write_text(json.dumps(out,indent=2))
    print("=== SGA POINTS — WCF G7 ===")
    print(f"median {d['median']}  mean {d['mean']}  std {d['std']}  line 27.5 (alt 26.5)")
    print(f"p10 {d['p10']} / p50 {d['p50']} / p90 {d['p90']}   P(over 27.5)={d['P(over_27.5)']}  P(over 26.5)={d['P(over_26.5)']}  P(>=30)={d['P(>=30)']}")
    print("modes:", {k:v['median'] for k,v in modes.items()})
    print("variance:", {k:v['pct'] for k,v in vdec.items()})
    print("levers:", {k:v['delta_median'] for k,v in levers.items()})
    print("WROTE", CACHE/"sga_points_showcase.json")

if __name__=="__main__": main()
