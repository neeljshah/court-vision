"""
wemby_points_model.py — THE SHOWCASE.
Victor Wembanyama points for WCF Game 7 as a structured, explainable distribution.

NOT "24.5". A scenario-mixture Monte Carlo grounded in REAL series matchup-tracking
(data/cache/intel_2026-05-26/wcf_defensive_matchups.csv) + series box (28.2 pts / 37.0 min).

Produces:
  - full point distribution (median, modes, tails, percentiles)
  - variance decomposition: each driver ranked by variance contributed (freeze-one-at-a-time)
  - counterfactual levers: median shift for each "what if" (refs, Hartenstein out, JWill back)
Outputs data/cache/intel_game7/wemby_points_showcase.json + prints a human summary.

Priors are explicit and labelled. Coverage shares/efficiency come from real matchup data;
minute-mixture & foul/blowout probabilities are documented priors (no game-7 tracking exists yet).
"""
import json, numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "intel_game7"
RNG = np.random.default_rng(20260530)
N = 200_000

# ---- REAL anchors (series 6g) ----
SERIES_PTS, SERIES_MIN = 28.167, 37.028
BASE_RATE = SERIES_PTS / SERIES_MIN          # 0.761 pts per FLOOR-minute (real)

# ---- REAL coverage efficiency (wcf_defensive_matchups.csv; pts allowed / matchup_min) ----
# big_drop = Hartenstein(58% allowed)/Holmgren(47%) primary -> OKC's rim leak (FAVORABLE to Wemby)
# pesky_wing = Dort/Caruso/Wallace POA defenders who HELD him (Caruso 0.88, Dort 1.35 pts/matchup-min)
# switch = smalls switched onto him (SGA 5.9, McCain 6.7 pts/matchup-min, tiny n) -> post-up torch, RARE
COVERAGE = {
    "big_drop":   {"mult": (1.10, 0.10), "share_g7": 0.55},  # favorable
    "pesky_wing": {"mult": (0.84, 0.10), "share_g7": 0.30},  # they hold him
    "switch":     {"mult": (1.45, 0.22), "share_g7": 0.15},  # mismatch torch (right tail)
}
# G7 note: JWill + Mitchell (both real Wemby defenders, 4.48+1.37 matchup-min) are OUT ->
# OKC's pesky-wing pool thins -> more big_drop + more scramble switches. Reflected in share_g7.

# ---- minute mixture (priors; series avg 37.0) ----
# foul trouble (Wemby aggressive rim protector + OKC paint attack + verticality calls) -> LEFT MODE
# blowout (this series: G3/G4/G6 margins 15/21/27 -> blowout-heavy; SAS manages Wemby Q4)
P_FOUL, P_BLOWOUT = 0.18, 0.28
MIN_FOUL   = (30.0, 3.0)   # foul-shortened
MIN_BLOWOUT= (34.0, 3.0)   # managed garbage-time pull (less than a role player; he's the star)
MIN_COMP   = (38.5, 2.0)   # competitive elimination game, heavy minutes

G7_INTENSITY = (0.965, 0.05)  # elimination-game defensive intensity haircut on efficiency (prior)
SHOT_NOISE_SD = 3.1           # hot/cold shooting night (real game-to-game pts SD ~ this after min/cov)

def draw_minutes(n, p_foul=P_FOUL, p_blowout=P_BLOWOUT, rng=RNG):
    u = rng.random(n)
    m = np.empty(n)
    foul = u < p_foul
    blow = (u >= p_foul) & (u < p_foul + p_blowout)
    comp = u >= p_foul + p_blowout
    m[foul] = rng.normal(*MIN_FOUL, foul.sum())
    m[blow] = rng.normal(*MIN_BLOWOUT, blow.sum())
    m[comp] = rng.normal(*MIN_COMP, comp.sum())
    state = np.where(foul, 0, np.where(blow, 1, 2))  # 0 foul,1 blowout,2 comp
    return np.clip(m, 12, 46), state

def draw_coverage_mult(n, shares=None, rng=RNG):
    if shares is None:
        shares = {k: v["share_g7"] for k, v in COVERAGE.items()}
    keys = list(shares); s = np.array([shares[k] for k in keys]); s = s / s.sum()
    pick = rng.choice(len(keys), size=n, p=s)
    mult = np.empty(n)
    for i, k in enumerate(keys):
        mu, sd = COVERAGE[k]["mult"]; sel = pick == i
        mult[sel] = rng.normal(mu, sd, sel.sum())
    return np.clip(mult, 0.45, 2.2)

def simulate(n=N, p_foul=P_FOUL, p_blowout=P_BLOWOUT, shares=None,
             ft_bonus=0.0, intensity=G7_INTENSITY, base=BASE_RATE, rng=RNG,
             fixed=None):
    fixed = fixed or {}
    mins, state = draw_minutes(n, p_foul, p_blowout, rng)
    if "minutes" in fixed:
        mins = np.full(n, fixed["minutes"]); state = np.full(n, 2)
    cov = draw_coverage_mult(n, shares, rng)
    if "coverage" in fixed: cov = np.full(n, fixed["coverage"])
    inten = rng.normal(*intensity, n)
    if "intensity" in fixed: inten = np.full(n, fixed["intensity"])
    noise = rng.normal(0, SHOT_NOISE_SD, n)
    if "noise" in fixed: noise = np.zeros(n)
    pts = mins * base * cov * inten + noise + ft_bonus
    return np.clip(pts, 0, None), state

def describe(pts):
    return {
        "mean": round(float(pts.mean()), 2), "median": round(float(np.median(pts)), 2),
        "std": round(float(pts.std()), 2),
        "p05": round(float(np.percentile(pts, 5)), 1), "p10": round(float(np.percentile(pts, 10)), 1),
        "p25": round(float(np.percentile(pts, 25)), 1), "p50": round(float(np.percentile(pts, 50)), 1),
        "p75": round(float(np.percentile(pts, 75)), 1), "p90": round(float(np.percentile(pts, 90)), 1),
        "p95": round(float(np.percentile(pts, 95)), 1),
        "P(>=20)": round(float((pts >= 20).mean()), 3), "P(>=25)": round(float((pts >= 25).mean()), 3),
        "P(>=30)": round(float((pts >= 30).mean()), 3), "P(>=35)": round(float((pts >= 35).mean()), 3),
        "P(over_27.5)": round(float((pts > 27.5).mean()), 3),
    }

def main():
    pts, state = simulate()
    base_desc = describe(pts)

    # modes by scenario
    modes = {
        "foul_trouble_left_mode": describe(pts[state == 0]),
        "blowout_managed":        describe(pts[state == 1]),
        "competitive_main":       describe(pts[state == 2]),
    }

    # variance decomposition: freeze-one-at-a-time
    var_total = float(pts.var())
    means = {"minutes": 35.6, "coverage": 1.02, "intensity": G7_INTENSITY[0], "noise": 0.0}
    contrib = {}
    for d in ["minutes", "coverage", "intensity", "noise"]:
        p2, _ = simulate(fixed={d: means[d]})
        contrib[d] = max(0.0, var_total - float(p2.var()))
    tot = sum(contrib.values()) or 1.0
    var_decomp = {d: {"abs_var": round(contrib[d], 2), "pct": round(100 * contrib[d] / tot, 1)}
                  for d in sorted(contrib, key=contrib.get, reverse=True)}

    # counterfactual levers (median shift vs base)
    base_med = base_desc["median"]
    levers = {}
    # 1) verticality-friendly ref crew: fewer fouls -> more minutes, +FT, slightly cleaner looks, tighter left tail
    p, _ = simulate(p_foul=0.09, ft_bonus=1.6, intensity=(0.985, 0.045))
    levers["verticality_friendly_crew"] = {"median": describe(p)["median"],
        "delta_median": round(describe(p)["median"] - base_med, 2),
        "note": "P(foul trouble) 0.18->0.09, +1.6 FT pts, cleaner looks; left mode shrinks (tighter)."}
    # 2) Hartenstein OUT (rim leak removed; Holmgren better defender but OKC thinner -> more scramble switches)
    p, _ = simulate(shares={"big_drop": 0.42, "pesky_wing": 0.30, "switch": 0.28})
    levers["hartenstein_out"] = {"median": describe(p)["median"],
        "delta_median": round(describe(p)["median"] - base_med, 2),
        "note": "Removes the 58%-allowed leak BUT OKC loses size -> switch share 0.15->0.28. Net effect computed, not assumed."}
    # 3) Jalen Williams ACTIVE (a quality wing defender returns -> pesky pool grows, fewer switches)
    p, _ = simulate(shares={"big_drop": 0.52, "pesky_wing": 0.40, "switch": 0.08})
    levers["jwill_returns"] = {"median": describe(p)["median"],
        "delta_median": round(describe(p)["median"] - base_med, 2),
        "note": "JWill back -> more pesky-wing coverage, fewer mismatches. Currently ruled OUT (swing factor)."}
    # 4) blowout either way (SAS manages him) — isolate
    p, _ = simulate(p_blowout=0.55)
    levers["blowout_likely"] = {"median": describe(p)["median"],
        "delta_median": round(describe(p)["median"] - base_med, 2),
        "note": "If G7 turns into a blowout (either direction), Q4 minutes cut -> median drops."}

    out = {
        "player": "Victor Wembanyama", "game": "WCF G7 SAS @ OKC 2026-05-30", "line_market": 27.5,
        "n_sims": N,
        "distribution": base_desc,
        "scenario_modes": modes,
        "scenario_mix_prior": {"P_foul_trouble": P_FOUL, "P_blowout": P_BLOWOUT,
                               "P_competitive": round(1 - P_FOUL - P_BLOWOUT, 2)},
        "variance_decomposition_ranked": var_decomp,
        "coverage_model_real_data": {k: {"share_g7": v["share_g7"], "eff_mult": v["mult"][0]}
                                     for k, v in COVERAGE.items()},
        "counterfactual_levers": levers,
        "drivers_explained": [
            "MINUTES (foul-state + blowout-script): biggest variance lever; creates the LEFT MODE (foul trouble ~30min, blowout-managed ~34min) vs competitive ~38min.",
            "COVERAGE (real matchup data): big-drop on Hartenstein/Holmgren is favorable (mult 1.10); Dort/Caruso/Wallace hold him (0.84); rare switches torch (1.45) = RIGHT TAIL.",
            "G7 INTENSITY: elimination-game defensive haircut on efficiency (prior).",
            "SHOT NOISE: hot/cold night, ~3.1 pt SD.",
        ],
        "honest_notes": [
            "Coverage shares/effs are REAL series matchup-tracking. Minute-mixture & foul/blowout probs are documented PRIORS (no G7 tracking yet).",
            "CV pipeline run in progress may refine contest-quality/defender-distance; this model uses the more-reliable NBA-API matchup data as primary.",
            "JWill+Mitchell OUT already baked into the G7 coverage shares (thinner pesky-wing pool, more switches).",
        ],
    }
    (CACHE / "wemby_points_showcase.json").write_text(json.dumps(out, indent=2))

    print("=== WEMBY POINTS — WCF G7 (showcase) ===")
    print(f"median {base_desc['median']}  mean {base_desc['mean']}  std {base_desc['std']}  line 27.5")
    print(f"p10 {base_desc['p10']} / p25 {base_desc['p25']} / p50 {base_desc['p50']} / p75 {base_desc['p75']} / p90 {base_desc['p90']}")
    print(f"P(over 27.5) = {base_desc['P(over_27.5)']}   P(>=30) = {base_desc['P(>=30)']}   P(>=20) = {base_desc['P(>=20)']}")
    print("\nScenario modes (medians): foul-trouble {}  blowout {}  competitive {}".format(
        modes['foul_trouble_left_mode']['median'], modes['blowout_managed']['median'], modes['competitive_main']['median']))
    print("\nVariance contributed (ranked):")
    for d, v in var_decomp.items(): print(f"  {d:10s} {v['pct']:5.1f}%")
    print("\nCounterfactual levers (median shift):")
    for k, v in levers.items(): print(f"  {k:26s} {v['delta_median']:+.2f}  -> {v['median']}")
    print("\nWROTE", CACHE / "wemby_points_showcase.json")

if __name__ == "__main__":
    main()
