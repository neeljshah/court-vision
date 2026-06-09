"""
player_points_models.py — generalize the Wemby/SGA structured-distribution method to
EVERY WCF Game 7 rotation player.

Same engine as scripts/wemby_points_model.py + scripts/sga_points_model.py (DO NOT edit those):
a 200k-draw scenario-mixture Monte Carlo for points =
    minutes-mixture (foul / blowout / competitive)
  x coverage-multiplier mixture (from REAL wcf_defensive_matchups.csv)
  x G7 intensity
  + role-aware FT floor
  + shot-noise.

For each player we:
  1. ANCHOR the base rate on REAL series box (wcf_player_series_avg_6g.csv): base = pts_pg / min_pg.
  2. Build the COVERAGE mixture from REAL matchup tracking: filter the CSV to off_player_id == target,
     take each defender's pts_allowed / matchup_min, normalise vs the player's own series pts/min to get an
     efficiency MULTIPLIER, and weight by G7-projected matchup share (defender matchup_min, with OUT
     defenders -- Jalen Williams, Ajay Mitchell -- removed and their share redistributed).
  3. Apply a ROLE profile (priors, explicitly labelled):
       - guards/wings: low foul-out risk, FT floor (SGA-style)
       - bigs: foul-trouble LEFT mode + rebound-linked minutes (Wemby/Holmgren-style)
  4. McCain SPECIAL CASE: he is NOW A STARTER (promoted after Jalen Williams OUT). His 6-game series
     avg (25.8 min, bench role) UNDER-states his G7 role. We BUMP his minutes + usage prior and FLAG it;
     the base series model is blind to this role change.

Honest labelling: coverage shares/efficiencies = REAL data; minute/foul/blowout/intensity = documented PRIORS.

Cross-checks each median vs possession_sim_v2.json calibrated p50 and the series avg; if wildly off we
note it. Writes data/cache/intel_game7/all_player_showcases.json + prints a compact table.
"""
import csv, json
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEL = ROOT / "data" / "cache" / "intel_2026-05-26"
CACHE = ROOT / "data" / "cache" / "intel_game7"
MATCHUPS_CSV = INTEL / "wcf_defensive_matchups.csv"
SERIES_CSV = INTEL / "wcf_player_series_avg_6g.csv"
SIM_JSON = CACHE / "possession_sim_v2.json"

RNG_SEED = 20260530
N = 200_000

# Players ruled OUT for G7 -> remove from every coverage pool, redistribute their matchup share.
OUT_DEFENDERS = {"1631114", "1642349"}  # Jalen Williams, Ajay Mitchell

# ---- target rotation players (excl Wemby+SGA, already shipped) ----
# role: "guard" (low foul risk + FT floor), "wing" (low foul, modest FT), "big" (foul-left-mode + reb-linked min)
TARGETS = {
    # OKC
    "1631096": {"role": "big",   "name": "Chet Holmgren"},
    "1642272": {"role": "guard", "name": "Jared McCain", "starter_promotion": True},
    "1627936": {"role": "wing",  "name": "Alex Caruso"},
    "1629652": {"role": "wing",  "name": "Luguentz Dort"},
    "1641717": {"role": "guard", "name": "Cason Wallace"},
    "1628392": {"role": "big",   "name": "Isaiah Hartenstein"},
    "1631119": {"role": "big",   "name": "Jaylin Williams"},
    "1630598": {"role": "wing",  "name": "Aaron Wiggins"},
    "1630198": {"role": "guard", "name": "Isaiah Joe"},
    "1629026": {"role": "wing",  "name": "Kenrich Williams"},
    # SAS
    "1642264": {"role": "guard", "name": "Stephon Castle"},
    "1628368": {"role": "guard", "name": "De'Aaron Fox"},
    "1642844": {"role": "guard", "name": "Dylan Harper"},
    "1630577": {"role": "wing",  "name": "Julian Champagnie"},
    "1630170": {"role": "wing",  "name": "Devin Vassell"},
    "1629640": {"role": "wing",  "name": "Keldon Johnson"},
    "1628436": {"role": "big",   "name": "Luke Kornet"},
    "203084":  {"role": "wing",  "name": "Harrison Barnes"},
}

# ---- ROLE priors (LABELLED PRIORS; no G7 tracking exists yet) ----
# p_foul: probability of a foul-shortened night.  p_blowout: managed/garbage-time pull.
# min_*: (mean, sd) minute draws per scenario.  ft_floor: (mean, sd) points from the FT line (low-variance floor).
# noise_sd: hot/cold shooting swing.  intensity: G7 defensive-intensity efficiency haircut.
ROLE_PRIORS = {
    "guard": dict(p_foul=0.06, p_blowout=0.28,
                  min_foul=(28.0, 3.5), min_blowout=(30.0, 3.5), min_comp=(35.0, 3.0),
                  ft_share=0.18, noise_frac=0.42, intensity=(0.985, 0.05)),
    "wing":  dict(p_foul=0.09, p_blowout=0.30,
                  min_foul=(20.0, 4.0), min_blowout=(22.0, 4.0), min_comp=(27.0, 3.5),
                  ft_share=0.10, noise_frac=0.50, intensity=(0.975, 0.05)),
    "big":   dict(p_foul=0.20, p_blowout=0.28,
                  min_foul=(20.0, 4.0), min_blowout=(24.0, 4.0), min_comp=(30.0, 3.5),
                  ft_share=0.14, noise_frac=0.46, intensity=(0.965, 0.05)),
}

# clamp bounds on the coverage multiplier so a tiny-n torch/0 doesn't blow up the dist
COV_CLAMP = (0.45, 2.2)


def load_series():
    rows = {}
    with open(SERIES_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows[r["player_id"]] = r
    return rows


def load_matchups():
    rows = []
    with open(MATCHUPS_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def build_coverage(pid, base_rate, matchups):
    """REAL coverage mixture for one offensive player.

    For each defender who guarded `pid`: efficiency = (pts_allowed/matchup_min) / base_rate.
    That ratio is how much MORE/LESS the player scored per minute against that defender vs his
    series average -> a coverage multiplier. Weight (share) = defender matchup_min.
    OUT defenders dropped; their share redistributes proportionally to the survivors.
    Tiny-sample matchups (<1.2 matchup_min) folded into a single 'scramble/other' bucket so a
    1-possession 0 or torch doesn't dominate.
    """
    mine = [r for r in matchups if r["off_player_id"] == pid]
    buckets = []  # (def_name, mult, share_min, matchup_min)
    scramble_min = 0.0
    scramble_pts = 0.0
    for r in mine:
        did = r["def_player_id"]
        mm = f(r["matchup_min"])
        pa = f(r["pts_allowed"])
        if mm <= 0:
            continue
        if did in OUT_DEFENDERS:
            continue  # defender unavailable G7
        per_min = pa / mm
        mult = per_min / base_rate if base_rate > 0 else 1.0
        if mm < 1.2:  # tiny sample -> pool into scramble
            scramble_min += mm
            scramble_pts += pa
            continue
        buckets.append({
            "def_name": r["def_player_name"], "def_id": did,
            "mult": float(np.clip(mult, *COV_CLAMP)),
            "share_min": mm, "matchup_min": round(mm, 2),
            "per_min": round(per_min, 3),
        })
    if scramble_min > 0:
        sper = scramble_pts / scramble_min
        smult = float(np.clip(sper / base_rate if base_rate > 0 else 1.0, *COV_CLAMP))
        buckets.append({"def_name": "scramble/other", "def_id": "agg",
                        "mult": smult, "share_min": scramble_min,
                        "matchup_min": round(scramble_min, 2), "per_min": round(sper, 3)})
    if not buckets:  # no matchup data at all -> neutral coverage
        buckets = [{"def_name": "no_data", "def_id": "na", "mult": 1.0,
                    "share_min": 1.0, "matchup_min": 0.0, "per_min": base_rate}]
    tot = sum(b["share_min"] for b in buckets)
    for b in buckets:
        b["share"] = b["share_min"] / tot
    # RE-CENTER: the series base_rate is the absolute anchor (real). Coverage should only REDISTRIBUTE
    # scoring across defenders relative to that anchor, so force the share-weighted mean multiplier to 1.0.
    # (raw pts_allowed/matchup_min vs base_rate drifts because matchup-min scoring != per-floor-min scoring.)
    wmean = sum(b["mult"] * b["share"] for b in buckets)
    if wmean > 0:
        for b in buckets:
            b["mult"] = float(np.clip(b["mult"] / wmean, *COV_CLAMP))
    # multiplier sd: wider for low-min buckets (less certain), narrower for well-sampled
    for b in buckets:
        b["sd"] = round(float(np.clip(0.22 - 0.10 * min(b["matchup_min"], 12) / 12, 0.10, 0.22)), 3)
    return buckets


def draw_minutes(n, pr, rng, fixed_min=None):
    if fixed_min is not None:
        return np.full(n, fixed_min), np.full(n, 2)
    u = rng.random(n)
    m = np.empty(n)
    foul = u < pr["p_foul"]
    blow = (u >= pr["p_foul"]) & (u < pr["p_foul"] + pr["p_blowout"])
    comp = u >= pr["p_foul"] + pr["p_blowout"]
    m[foul] = rng.normal(*pr["min_foul"], foul.sum())
    m[blow] = rng.normal(*pr["min_blowout"], blow.sum())
    m[comp] = rng.normal(*pr["min_comp"], comp.sum())
    state = np.where(foul, 0, np.where(blow, 1, 2))
    return np.clip(m, 4, 46), state


def draw_coverage(n, buckets, rng, fixed_cov=None):
    if fixed_cov is not None:
        return np.full(n, fixed_cov)
    shares = np.array([b["share"] for b in buckets])
    shares = shares / shares.sum()
    pick = rng.choice(len(buckets), size=n, p=shares)
    mult = np.empty(n)
    for i, b in enumerate(buckets):
        sel = pick == i
        mult[sel] = rng.normal(b["mult"], b["sd"], sel.sum())
    return np.clip(mult, *COV_CLAMP)


def simulate(pr, buckets, base_rate, ft_floor, noise_sd, n=N, rng=None,
             fixed=None, p_foul=None, p_blowout=None, shares_override=None):
    fixed = fixed or {}
    rng = rng or np.random.default_rng(RNG_SEED)
    prx = dict(pr)
    if p_foul is not None:
        prx["p_foul"] = p_foul
    if p_blowout is not None:
        prx["p_blowout"] = p_blowout
    bk = buckets
    if shares_override is not None:
        bk = [dict(b) for b in buckets]
        for b in bk:
            b["share"] = shares_override.get(b["def_id"], b["share"])

    mins, state = draw_minutes(n, prx, rng, fixed_min=fixed.get("minutes"))
    cov = draw_coverage(n, bk, rng, fixed_cov=fixed.get("coverage"))
    if "intensity" in fixed:
        inten = np.full(n, fixed["intensity"])
    else:
        inten = rng.normal(*pr["intensity"], n)
    if "ft" in fixed:
        ft = np.full(n, ft_floor[0])
    else:
        ft = np.clip(rng.normal(*ft_floor, n), 0, None)
    if "noise" in fixed:
        noise = np.zeros(n)
    else:
        noise = rng.normal(0, noise_sd, n)

    field_share = 1.0 - pr["ft_share"]
    field = mins * base_rate * cov * inten * field_share
    return np.clip(field + ft + noise, 0, None), state


def describe(p):
    return {
        "mean": round(float(p.mean()), 2), "median": round(float(np.median(p)), 2),
        "std": round(float(p.std()), 2),
        "p10": round(float(np.percentile(p, 10)), 1), "p25": round(float(np.percentile(p, 25)), 1),
        "p50": round(float(np.percentile(p, 50)), 1), "p75": round(float(np.percentile(p, 75)), 1),
        "p90": round(float(np.percentile(p, 90)), 1),
    }


def run_player(pid, cfg, series, matchups, sim_cal):
    rng = np.random.default_rng(RNG_SEED)
    s = series.get(pid, {})
    name = cfg["name"]
    role = cfg["role"]
    pr = dict(ROLE_PRIORS[role])

    min_pg = f(s.get("min_pg"))
    pts_pg = f(s.get("pts_pg"))
    fta_pg = f(s.get("fta_pg"))
    usg = f(s.get("usg_pct_pg"))
    base_rate = (pts_pg / min_pg) if min_pg > 0 else 0.0

    flags = []
    role_change = False

    # ---- minute priors ANCHORED to series min_pg (LABELLED PRIORS for the spread shape only) ----
    # competitive ~= series min (slightly up for elimination game), blowout/foul = managed pulls below it.
    proj_min = min_pg
    if cfg.get("starter_promotion"):
        # ---- McCain starter-promotion correction (LABELLED) ----
        # 6g avg (25.8 min, bench) understates G7 starter role after Jalen Williams ruled OUT.
        role_change = True
        proj_min = 33.0  # starter-load prior
        base_rate *= 1.06  # usage bump: starters get more on-ball reps
        flags.append("STARTER_PROMOTION: 6g avg (25.8min, bench) understates G7 starter role; "
                     "projected minutes bumped 25.8->33.0 + base_rate +6% (usage). Series model is "
                     "blind to this role change.")
    pr["min_comp"] = (round(proj_min + 1.5, 1), round(max(2.0, proj_min * 0.09), 1))
    pr["min_blowout"] = (round(proj_min * 0.82, 1), round(max(2.0, proj_min * 0.10), 1))
    pr["min_foul"] = (round(proj_min * 0.70, 1), round(max(2.5, proj_min * 0.12), 1))

    # FT floor from series fta (role ft_share governs how much of points are modeled as FT)
    ft_pts = fta_pg * 0.80  # ~80% FT shooting prior
    ft_floor = (max(ft_pts * 0.5, 0.0), max(ft_pts * 0.30, 0.4))  # mean ~ half of FT pts as a floor, sd
    # noise sd scales with the player's scoring volume (bigger scorers = bigger swings)
    noise_sd = max(pr["noise_frac"] * (pts_pg ** 0.5) * 1.25, 1.2)

    # coverage is re-centered to mean 1.0 inside build_coverage, so the base_rate arg only sets the
    # raw ratio scale (cancels on re-centering); pass the series base rate for readability.
    buckets = build_coverage(pid, (pts_pg / min_pg) if min_pg > 0 else 1.0, matchups)

    pts, state = simulate(pr, buckets, base_rate, ft_floor, noise_sd, rng=rng)
    d = describe(pts)

    # scenario modes
    modes = {
        "foul_left_mode": describe(pts[state == 0]) if (state == 0).any() else None,
        "blowout_managed": describe(pts[state == 1]) if (state == 1).any() else None,
        "competitive": describe(pts[state == 2]) if (state == 2).any() else None,
    }

    # variance decomposition (freeze-one-at-a-time)
    var_total = float(pts.var())
    means = {
        "minutes": float(np.mean([(pr["min_foul"][0]) * pr["p_foul"]
                                  + (pr["min_blowout"][0]) * pr["p_blowout"]
                                  + (pr["min_comp"][0]) * (1 - pr["p_foul"] - pr["p_blowout"])])),
        "coverage": float(sum(b["mult"] * b["share"] for b in buckets)),
        "intensity": pr["intensity"][0],
        "ft": ft_floor[0],
        "noise": 0.0,
    }
    contrib = {}
    for dd in ["minutes", "coverage", "intensity", "ft", "noise"]:
        p2, _ = simulate(pr, buckets, base_rate, ft_floor, noise_sd,
                         rng=np.random.default_rng(RNG_SEED), fixed={dd: means[dd]})
        contrib[dd] = max(0.0, var_total - float(p2.var()))
    tot = sum(contrib.values()) or 1.0
    vdec = {k: round(100 * contrib[k] / tot, 1) for k in sorted(contrib, key=contrib.get, reverse=True)}
    top_driver = next(iter(vdec))

    # counterfactual levers
    bm = d["median"]
    levers = {}
    p, _ = simulate(pr, buckets, base_rate, ft_floor, noise_sd,
                    rng=np.random.default_rng(RNG_SEED), p_blowout=0.55)
    levers["blowout_likely"] = {"delta_median": round(describe(p)["median"] - bm, 2),
                                "note": "G7 turns into a blowout (either direction) -> managed Q4 minutes."}
    # higher-usage / more-minutes lever (role expands)
    pr_up = dict(pr)
    pr_up["min_comp"] = (pr["min_comp"][0] + 4, pr["min_comp"][1])
    p, _ = simulate(pr_up, buckets, base_rate * 1.05, ft_floor, noise_sd,
                    rng=np.random.default_rng(RNG_SEED), p_blowout=0.15)
    levers["role_expands"] = {"delta_median": round(describe(p)["median"] - bm, 2),
                              "note": "competitive elimination game -> +4 min & +5% usage; foul/blowout pull minimized."}

    # cross-checks
    cal = sim_cal.get(pid)
    notes = []
    prior_correction = None
    if cal is not None:
        diff = round(d["median"] - cal, 1)
        notes.append(f"sim_cal_p50={cal} (delta {diff:+})")
        if abs(diff) > max(0.30 * max(cal, 1), 5):
            prior_correction = f"median {d['median']} far from sim_cal {cal}; flagged for review"
    notes.append(f"series_pts_pg={round(pts_pg,1)} min_pg={round(min_pg,1)} base_rate={round(base_rate,3)}")

    # confidence: by series minutes
    low_conf = min_pg < 10.0
    confidence = "LOW (deep bench, <10 min/g)" if low_conf else (
        "MED" if min_pg < 16 else "HIGH")

    return {
        "player": name, "player_id": pid, "role": role, "confidence": confidence,
        "series_anchor": {"min_pg": round(min_pg, 1), "pts_pg": round(pts_pg, 1),
                          "fta_pg": round(fta_pg, 1), "usg_pct": round(usg, 1),
                          "base_rate_pts_per_min": round(base_rate, 3)},
        "distribution": d,
        "p10": d["p10"], "p50": d["median"], "p90": d["p90"], "median": d["median"],
        "scenario_modes": modes,
        "variance_decomposition_pct": vdec,
        "top_variance_driver": top_driver,
        "coverage_model_real_data": [
            {"def": b["def_name"], "matchup_min": b["matchup_min"], "eff_mult": round(b["mult"], 2),
             "share": round(b["share"], 3)} for b in
            sorted(buckets, key=lambda x: -x["share"])[:6]
        ],
        "counterfactual_levers": levers,
        "role_change_flagged": role_change,
        "flags": flags,
        "cross_checks": notes,
        "prior_correction": prior_correction,
    }


def main():
    series = load_series()
    matchups = load_matchups()
    sim = json.load(open(SIM_JSON))
    sim_cal = {}
    for pid, v in sim.get("per_player", {}).items():
        pts = v.get("stats", {}).get("pts", {})
        sim_cal[pid] = pts.get("calibrated_p50", pts.get("p50"))

    results = {}
    for pid, cfg in TARGETS.items():
        results[pid] = run_player(pid, cfg, series, matchups, sim_cal)

    out = {
        "game": "WCF Game 7 — SAS @ OKC 2026-05-30",
        "method": "scenario-mixture Monte Carlo (minutes x REAL-coverage x intensity + FT floor + noise), "
                  "generalized from wemby_points_model.py / sga_points_model.py",
        "n_sims": N,
        "honest_notes": [
            "Coverage shares/efficiencies = REAL wcf_defensive_matchups.csv (pts_allowed/matchup_min vs each "
            "player's own series base rate). Minute/foul/blowout/intensity/FT = LABELLED PRIORS (no G7 tracking).",
            "OUT for G7: Jalen Williams + Ajay Mitchell — removed from every coverage pool, share redistributed.",
            "McCain is now a STARTER (Jalen Williams OUT): his 6g bench avg understates role -> minutes + usage "
            "prior bumped and explicitly flagged (role_change_flagged=true). Base series model is blind to this.",
            "Confidence = series min_pg: <10 LOW (deep bench), 10-16 MED, >=16 HIGH.",
            "Each median cross-checked vs possession_sim_v2.json calibrated p50 + series avg.",
        ],
        "players": results,
    }
    (CACHE / "all_player_showcases.json").write_text(json.dumps(out, indent=2))

    # compact table
    order = sorted(results.values(), key=lambda r: -r["median"])
    print("=== WCF G7 ROTATION POINTS — STRUCTURED DISTRIBUTIONS ===")
    print(f"{'player':22} {'role':6} {'med':>5} {'p10':>5} {'p90':>5}  {'driver':10} {'conf':6} flag")
    for r in order:
        flag = "ROLE!" if r["role_change_flagged"] else ""
        print(f"{r['player']:22} {r['role']:6} {r['median']:5.1f} {r['p10']:5.1f} {r['p90']:5.1f}  "
              f"{r['top_variance_driver']:10} {r['confidence'][:5]:6} {flag}")
    print("\nWROTE", CACHE / "all_player_showcases.json")


if __name__ == "__main__":
    main()
