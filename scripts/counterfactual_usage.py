"""L3 CAUSAL: Counterfactual usage / minute redistribution for WCF G7 (SAS @ OKC).

For each scenario we REDISTRIBUTE usage and minutes with explicit logic, then report:
  - shift in OKC team total
  - shift in OKC win-prob (delta)
  - the 3-4 most-affected player-prop medians

Scenarios:
  1. Jalen Williams ACTIVE (the #1 swing factor) - he is currently ruled OUT (hamstring).
  2. OKC blowout script - integrate over P(blowout)~0.28 (showcase prior).
  3. Hartenstein foul-trouble / out - who absorbs his minutes + Wemby coverage effect.

HONEST DATA vs PRIORS
---------------------
REAL (intel_2026-05-26/wcf_player_series_avg_6g.csv): per-player usg_pct, min_pg, pts_pg,
  reb_pg for every OKC player; JWill pre-injury series usg=29.65% / 18.2 min (gp=3).
REAL (possession_sim_v2.json): calibrated per-player pts medians (the showcase prop seeds).
REAL (ensemble_game7.json): OKC win 0.6089, total 214.2; (wemby/sga showcases): JWill-returns
  Wemby lever -1.21, Hartenstein-out Wemby lever +0.86.
PRIORS (LABELLED): usage->points elasticity (~0.9 pts per usg-point on fixed minutes is a
  documented prior), win-prob sensitivity to a returning 28%-usage two-way wing, blowout
  minute haircuts, and the foul-absorption split for Hartenstein's minutes.

Outputs data/cache/intel_game7/L3_counterfactual.json. New file only; touches no protected file.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEL = ROOT / "data" / "cache" / "intel_2026-05-26"
OUT_DIR = ROOT / "data" / "cache" / "intel_game7"
SERIES = INTEL / "wcf_player_series_avg_6g.csv"
SIM = OUT_DIR / "possession_sim_v2.json"
ENSEMBLE = OUT_DIR / "ensemble_game7.json"

OKC_ROTATION = {  # pid -> common name (G7 active rotation, JWill OUT in base)
    "1628983": "Shai Gilgeous-Alexander",
    "1631096": "Chet Holmgren",
    "1628392": "Isaiah Hartenstein",
    "1641717": "Cason Wallace",
    "1629652": "Luguentz Dort",
    "1642272": "Jared McCain",
    "1627936": "Alex Caruso",
    "1631119": "Jaylin Williams",
    "1630198": "Isaiah Joe",
    "1629026": "Kenrich Williams",
    "1628436": "Luke Kornet",  # note: Kornet is SAS in this dataset; excluded below
}
JWILL_ID = "1631114"

# PRIOR elasticities -----------------------------------------------------------
USG_TO_PTS = 0.90        # PRIOR: pts per +1 usg-point on fixed minutes (NBA usage elasticity)
MIN_TO_PTS_FACTOR = 1.0  # pts scale linearly with minutes at fixed per-min rate (mechanical)
# PRIOR: team total responds ~0.62 pts per net usage-point reallocated from bench-eff to
# starter-eff (efficiency gap), capped; a returning efficient wing nudges total up modestly.
TEAM_TOTAL_PER_EFF_USG = 0.62
# PRIOR: OKC win-prob sensitivity to JWill (a 28%-usage two-way all-NBA-3rd-team wing) return.
# Anchored to public market behavior: a healthy second star is worth ~3-4pp on the favorite.
JWILL_WINPROB_DELTA = 0.035   # PRIOR (+3.5pp)


def load_series():
    rows = {}
    with open(SERIES, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        idx = {c: i for i, c in enumerate(header)}
        for line in f:
            p = line.rstrip("\n").split(",")
            def g(col):
                v = p[idx[col]]
                return float(v) if v not in ("", None) else 0.0
            rows[p[idx["player_id"]]] = {
                "name": p[idx["player_name"]],
                "team": p[idx["team"]],
                "min_pg": g("min_pg"),
                "pts_pg": g("pts_pg"),
                "reb_pg": g("reb_pg"),
                "usg": g("usg_pct_pg"),
                "gp": g("gp"),
            }
    return rows


def sim_medians(sim):
    """REAL calibrated pts medians (showcase prop seeds) per pid."""
    out = {}
    for pid, d in sim["per_player"].items():
        pts = d["stats"]["pts"]
        out[pid] = pts.get("calibrated_p50", pts["p50"])
    return out


def main():
    series = load_series()
    sim = json.loads(SIM.read_text(encoding="utf-8"))
    ens = json.loads(ENSEMBLE.read_text(encoding="utf-8"))
    med = sim_medians(sim)

    base_total = ens["total_est"]          # 214.2 (full game, both teams)
    base_win = ens["okc_win_prob"]          # 0.6089
    # OKC scoring share of the total. OKC margin +2.71 on total 214.2 -> OKC ~108.5.
    okc_base_pts = round((base_total + ens["okc_margin_est"]) / 2.0, 1)

    scenarios = {}

    # ----------------------------------------------------------------------
    # SCENARIO 1: Jalen Williams ACTIVE (limited ~24 min)
    # ----------------------------------------------------------------------
    # JWill pre-injury series usg=29.65%, 18.2 min over gp=3 (limited). Healthy full role
    # is a ~28% usage wing. We give him 24 min at 26% usage (limited-return PRIOR).
    jwill_min = 24.0          # PRIOR (limited return)
    jwill_usg = 26.0          # PRIOR (slightly below full health 28%)
    # He pulls usage primarily OFF the bench-creation players who currently soak his absence:
    # McCain (promoted starter, 25.6%), Caruso (16.9%), Dort (10.4%). Redistribution weights
    # by who gained from his absence (PRIOR weights, sum=1).
    redistrib = {"1642272": 0.45, "1627936": 0.30, "1629652": 0.25}  # McCain/Caruso/Dort
    # Only a FRACTION of JWill's usage was absorbed by these three (the rest by SGA/Chet/floor).
    # PRIOR: ~55% of his 26% usage reverts off this trio; the rest unwinds elsewhere.
    REVERSION_FRAC = 0.55
    jwill_usg_added = jwill_usg * REVERSION_FRAC  # usage reclaimed from this trio
    affected = {}
    for pid, w in redistrib.items():
        usg_lost = jwill_usg_added * w * (jwill_min / 48.0)  # scaled by his share of game-minutes
        # minute compression: JWill's 24 min are spread across the WHOLE 9-man bench squeeze,
        # not concentrated on three players. PRIOR: ~30% of his minutes displace these three
        # (the rest comes from end-of-bench + tighter G7 rotation).
        min_lost = jwill_min * w * 0.30   # PRIOR: 30% of his minutes displace these three
        pts_from_usg = -usg_lost * USG_TO_PTS
        # per-min pts for the affected player
        ppm = (med.get(pid, series[pid]["pts_pg"])) / max(series[pid]["min_pg"], 1.0)
        pts_from_min = -min_lost * ppm
        delta = round(pts_from_usg + pts_from_min, 2)
        affected[series[pid]["name"]] = {
            "usg_pts_delta": round(pts_from_usg, 2),
            "min_pts_delta": round(pts_from_min, 2),
            "prop_median_delta": delta,
            "new_prop_median": round(med.get(pid, series[pid]["pts_pg"]) + delta, 2),
        }
    # SGA: JWill back relieves SGA creation burden slightly -> efficiency up, volume down a touch.
    sga_delta = round(-0.6, 2)  # PRIOR: small volume cede, near-neutral
    affected["Shai Gilgeous-Alexander"] = {
        "usg_pts_delta": sga_delta, "min_pts_delta": 0.0,
        "prop_median_delta": sga_delta,
        "new_prop_median": round(med["1628983"] + sga_delta, 2),
        "note": "creation burden shared; small volume cede, efficiency slightly up (near-neutral)",
    }
    # JWill himself: ~24 min at 26% usg, pre-injury efficiency (REAL series ts ~ above bench).
    jwill_proj = round(jwill_min * (jwill_usg / 100.0) * 1.05, 2)  # PRIOR pts from usg*min
    # TEAM TOTAL: a returning starter REPLACES minutes 1-for-1 -> the team total moves by the
    # EFFICIENCY DIFFERENTIAL (JWill's pts/min vs the displaced players' pts/min) over the
    # minutes he reclaims, NOT JWill_pts minus all displaced pts (that double-counts).
    jwill_ppm = jwill_proj / jwill_min
    displaced_min = sum(jwill_min * w * 0.30 for w in redistrib.values())  # minutes reclaimed from these three
    # weighted ppm of the players whose minutes JWill reclaims
    disp_ppm = 0.0
    for pid, w in redistrib.items():
        ppm = (med.get(pid, series[pid]["pts_pg"])) / max(series[pid]["min_pg"], 1.0)
        disp_ppm += w * ppm
    eff_total_delta = round((jwill_ppm - disp_ppm) * displaced_min, 2)  # starter-vs-bench eff gain
    okc_pts_delta = round(eff_total_delta + 0.6, 2)  # +small spacing/efficiency bump (PRIOR)
    scenarios["jwill_active"] = {
        "label": "Jalen Williams ACTIVE (#1 swing factor; limited ~24 min, ~26% usg)",
        "real_inputs": {
            "jwill_series_usg_pct": series.get(JWILL_ID, {}).get("usg", "n/a"),
            "jwill_series_min": series.get(JWILL_ID, {}).get("min_pg", "n/a"),
            "jwill_series_gp": series.get(JWILL_ID, {}).get("gp", "n/a"),
            "note_real": "29.65% usg / 18.2 min over gp=3 is REAL but limited; healthy role ~28% usg wing.",
        },
        "assumptions_prior": {"jwill_min": jwill_min, "jwill_usg_pct": jwill_usg,
                               "redistribution_weights": "McCain .45 / Caruso .30 / Dort .25"},
        "okc_team_total_delta": okc_pts_delta,
        "okc_total_new": round(base_total + okc_pts_delta, 1),
        "okc_winprob_delta": JWILL_WINPROB_DELTA,
        "okc_winprob_new": round(base_win + JWILL_WINPROB_DELTA, 4),
        "wemby_pts_lever": -1.21,
        "wemby_pts_lever_note": "from wemby showcase: JWill returns -> more pesky-wing coverage on Wemby",
        "most_affected_props": affected,
        "jwill_own_proj_pts_median_prior": jwill_proj,
    }

    # ----------------------------------------------------------------------
    # SCENARIO 2: OKC blowout script (integrate over P(blowout)=0.28)
    # ----------------------------------------------------------------------
    p_blow = sim_blowout_prior = 0.28  # PRIOR from wemby showcase scenario_mix_prior
    # In a blowout, starters lose Q4 minutes (~6-8 min), bench gains. PRIOR haircut.
    starter_min_cut = 7.0   # PRIOR
    starters = ["1628983", "1631096", "1642272", "1627936", "1641717"]  # SGA/Chet/McCain/Caruso/Wallace
    bench = ["1631119", "1630198", "1629026", "1630598"]
    blow_affected = {}
    for pid in starters:
        if pid not in series:
            continue
        ppm = (med.get(pid, series[pid]["pts_pg"])) / max(series[pid]["min_pg"], 1.0)
        # only realized in blowout branch; expected delta = P(blow) * conditional cut
        cond_delta = -starter_min_cut * ppm
        exp_delta = round(p_blow * cond_delta, 2)
        blow_affected[series[pid]["name"]] = {
            "conditional_blowout_delta": round(cond_delta, 2),
            "expected_delta_x_Pblow": exp_delta,
            "new_prop_median_expected": round(med.get(pid, series[pid]["pts_pg"]) + exp_delta, 2),
        }
    # team total: blowout slightly LOWERS total (clock management, subs) - PRIOR small.
    blow_total_cond = -4.5   # PRIOR conditional total reduction in a managed blowout
    blow_total_exp = round(p_blow * blow_total_cond, 2)
    scenarios["blowout_script"] = {
        "label": "OKC blowout script, integrated over P(blowout)",
        "P_blowout_prior": p_blow,
        "starter_min_cut_prior": starter_min_cut,
        "okc_team_total_delta_expected": blow_total_exp,
        "okc_team_total_delta_conditional": blow_total_cond,
        "okc_total_new_expected": round(base_total + blow_total_exp, 1),
        "okc_winprob_delta": "n/a (blowout is an OUTCOME branch, not an input; already in ensemble win 0.609)",
        "most_affected_props": blow_affected,
        "note": "Starter prop medians shaded DOWN by P(blow) x conditional Q4 haircut; bench (JaylinW/Joe/KenrichW) up.",
    }

    # ----------------------------------------------------------------------
    # SCENARIO 3: Hartenstein foul-trouble / OUT
    # ----------------------------------------------------------------------
    # Hartenstein 20.9 min / 17.5% usg / 8.5 pts, 8.3 reb (REAL). If out/foul-limited,
    # his ~21 min split: Holmgren slides to C (+6 min), Jaylin Williams (+8 min), Kornet n/a.
    hart_min = series["1628392"]["min_pg"]
    absorb = {"1631096": 6.0, "1631119": 9.0, "1629026": 5.0}  # Holmgren/JaylinW/KenrichW (PRIOR split)
    hart_affected = {}
    for pid, add_min in absorb.items():
        if pid not in series:
            continue
        ppm = (med.get(pid, series[pid]["pts_pg"])) / max(series[pid]["min_pg"], 1.0)
        rpm = series[pid]["reb_pg"] / max(series[pid]["min_pg"], 1.0)
        pts_delta = round(add_min * ppm, 2)
        reb_delta = round(add_min * rpm, 2)
        hart_affected[series[pid]["name"]] = {
            "added_min_prior": add_min,
            "pts_prop_median_delta": pts_delta,
            "reb_prop_median_delta": reb_delta,
            "new_pts_median": round(med.get(pid, series[pid]["pts_pg"]) + pts_delta, 2),
            "new_reb_median_vs_seriesavg": round(series[pid]["reb_pg"] + reb_delta, 2),
        }
    # Wemby coverage effect: Hartenstein out removes the 58%-allowed leak BUT OKC loses size
    # -> more switches. From wemby showcase lever = +0.86 net.
    # team total: losing Hartenstein's rim presence + rebounding modestly LOWERS OKC eff,
    # but Holmgren-at-C spaces floor -> near wash, slight down (PRIOR).
    hart_total_delta = -1.2  # PRIOR
    hart_winprob_delta = -0.025  # PRIOR: losing a starting C in G7 hurts the favorite ~2.5pp
    scenarios["hartenstein_out"] = {
        "label": "Hartenstein foul-trouble / OUT",
        "real_inputs": {"hart_min_pg": hart_min, "hart_usg": series["1628392"]["usg"],
                         "hart_reb_pg": series["1628392"]["reb_pg"]},
        "minute_absorption_prior": "Holmgren +6 (slides to C) / Jaylin Williams +9 / Kenrich Williams +5",
        "okc_team_total_delta": hart_total_delta,
        "okc_total_new": round(base_total + hart_total_delta, 1),
        "okc_winprob_delta": hart_winprob_delta,
        "okc_winprob_new": round(base_win + hart_winprob_delta, 4),
        "wemby_coverage_lever": 0.86,
        "wemby_coverage_note": "wemby showcase: removes 58%-allowed leak but +switch share -> net +0.86 to Wemby",
        "most_affected_props": hart_affected,
        "rebound_prop_note": "Holmgren & Kenrich rebound props get the biggest lift (Hartenstein's 8.3 reb/g redistributes).",
    }

    out = {
        "model": "L3 counterfactual usage / minute redistribution (WCF G7 SAS @ OKC)",
        "game": "WCF G7 SAS @ OKC 2026-05-30",
        "baseline_from_ensemble": {
            "okc_win_prob": base_win,
            "okc_margin_est": ens["okc_margin_est"],
            "total_est": base_total,
            "okc_implied_pts": okc_base_pts,
        },
        "scenarios": scenarios,
        "priors_labelled": [
            "USG_TO_PTS=0.90 pts/usg-point and TEAM_TOTAL_PER_EFF_USG=0.62 are league elasticity PRIORS.",
            "JWILL_WINPROB_DELTA=+3.5pp is a market-anchored PRIOR for a returning 28%-usage two-way wing.",
            "Redistribution weights, blowout minute haircut (7 min), and Hartenstein absorption split are PRIORS.",
            "JWill 29.65% usg / 18.2 min / gp=3 is REAL series data but a limited 3-game sample.",
            "Wemby levers (-1.21 JWill, +0.86 Hartenstein-out) are imported from the REAL-matchup wemby showcase.",
        ],
        "honest_blockers": [
            "Win-prob deltas are calibrated priors (no counterfactual classifier re-run with JWill toggled).",
            "Redistribution is a documented logic, not a re-simulated possession run.",
            "Kornet (1628436) appears as SAS in the 6g CSV; excluded from OKC absorption.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "L3_counterfactual.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # ---- console report ----
    print("=" * 78)
    print("L3 COUNTERFACTUAL USAGE / MINUTE REDISTRIBUTION  (WCF G7 SAS @ OKC)")
    print("=" * 78)
    print(f"Baseline ensemble: OKC win {base_win:.4f} | total {base_total} | OKC~{okc_base_pts} pts")
    print("-" * 78)
    s1 = scenarios["jwill_active"]
    print("[1] JWILL ACTIVE (#1 swing):")
    print(f"    OKC total {base_total} -> {s1['okc_total_new']} ({s1['okc_team_total_delta']:+.2f})"
          f" | winprob {base_win:.3f} -> {s1['okc_winprob_new']:.3f} ({s1['okc_winprob_delta']:+.3f})")
    print(f"    Wemby pts lever {s1['wemby_pts_lever']:+.2f}")
    for nm, a in s1["most_affected_props"].items():
        print(f"      {nm:<26} prop median {a['prop_median_delta']:+.2f} -> {a['new_prop_median']}")
    s2 = scenarios["blowout_script"]
    print(f"[2] BLOWOUT (P={s2['P_blowout_prior']}):")
    print(f"    OKC total expected {s2['okc_team_total_delta_expected']:+.2f} -> {s2['okc_total_new_expected']}"
          f" (conditional {s2['okc_team_total_delta_conditional']:+.1f})")
    for nm, a in s2["most_affected_props"].items():
        print(f"      {nm:<26} exp {a['expected_delta_x_Pblow']:+.2f} (cond {a['conditional_blowout_delta']:+.2f})")
    s3 = scenarios["hartenstein_out"]
    print("[3] HARTENSTEIN OUT/FOUL:")
    print(f"    OKC total {base_total} -> {s3['okc_total_new']} ({s3['okc_team_total_delta']:+.2f})"
          f" | winprob {base_win:.3f} -> {s3['okc_winprob_new']:.3f} ({s3['okc_winprob_delta']:+.3f})")
    print(f"    Wemby coverage lever {s3['wemby_coverage_lever']:+.2f}")
    for nm, a in s3["most_affected_props"].items():
        print(f"      {nm:<26} pts {a['pts_prop_median_delta']:+.2f} | reb {a['reb_prop_median_delta']:+.2f}"
              f" (-> {a['new_reb_median_vs_seriesavg']} reb)")
    print("-" * 78)
    print(f"WROTE {out_path}")


if __name__ == "__main__":
    main()
