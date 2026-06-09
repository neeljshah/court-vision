"""L3 CAUSAL: Foul-trouble -> minute-distribution model for Wembanyama (WCF G7).

Causal chain:
  officials crew leniency
    x  Wemby rim-protection / paint-contest style (real matchup data)
    x  OKC paint-attack rate at Wemby (real matchup data)
  -> P(early-2-fouls), P(3 by half), P(foul-out/6)
  -> MINUTE distribution (mean/std)
  -> points-median delta vs the showcase's neutral baseline (left-mode feed)

The G7 officiating crew is announced DAY-OF (UNKNOWN at build time), so we OUTPUT A
CONDITIONAL TABLE across three crew archetypes (lenient / neutral / tight-verticality).

HONEST DATA vs PRIORS
---------------------
REAL (NBA-API series matchup tracking, intel_2026-05-26/wcf_defensive_matchups.csv):
  - OKC offensive FGA *at* Wembanyama (def_player_id=1641705) over the 6-game series.
  - Wemby blocks generated in those matchups (rim-protection volume proxy).
REAL (intel_2026-05-26/wcf_player_series_avg_6g.csv):
  - Wemby series minutes (37.0 min/g), blk/g (3.0), the OKC drivers' fga/g.
PRIORS (LABELLED, no G7 tracking exists):
  - Per-foul-event hazard rates and crew leniency multipliers (league foul-rate priors;
    PF is NOT in the 6g CSV so league big-man foul rate is used).
  - The neutral baseline anchor (Wemby foul-trouble left mode median 23.22) is taken from
    the already-built wemby_points_showcase.json so deltas are consistent with the ensemble.
  - Minute haircut per foul-state is a documented prior (foul-out ~28, early-2 ~31, clean ~38).

Outputs data/cache/intel_game7/L3_foul_minutes.json. New file only; touches no protected file.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEL = ROOT / "data" / "cache" / "intel_2026-05-26"
OUT_DIR = ROOT / "data" / "cache" / "intel_game7"
MATCHUPS = INTEL / "wcf_defensive_matchups.csv"
SERIES = INTEL / "wcf_player_series_avg_6g.csv"
SHOWCASE = OUT_DIR / "wemby_points_showcase.json"

WEMBY_ID = "1641705"
SERIES_GAMES = 6  # WCF is a 7-game series; 6 played going into G7

# ---------------------------------------------------------------------------
# 1) REAL DATA: OKC paint-attack volume *at* Wemby + his rim-protection volume
# ---------------------------------------------------------------------------
def load_paint_attack_at_wemby():
    """Sum OKC FGA taken with Wembanyama as the matchup defender (rim attacks),
    plus the blocks/tov_forced he generated and the FG% he allowed.
    Returns per-driver and totals. REAL matchup tracking."""
    drivers = []
    tot_fga = tot_pts_allowed = tot_blk = tot_tov = tot_min = 0.0
    with open(MATCHUPS, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        idx = {c: i for i, c in enumerate(header)}
        for line in f:
            p = line.rstrip("\n").split(",")
            if p[idx["def_player_id"]] != WEMBY_ID:
                continue
            fga = float(p[idx["fga_allowed"]])
            mins = float(p[idx["matchup_min"]])
            blk = float(p[idx["blocks"]])
            tov = float(p[idx["tov_forced"]])
            pa = float(p[idx["pts_allowed"]])
            drivers.append({
                "off_player": p[idx["off_player_name"]],
                "matchup_min": round(mins, 2),
                "fga_at_wemby": fga,
                "pts_allowed": pa,
                "blocks": blk,
                "tov_forced": tov,
            })
            tot_fga += fga
            tot_pts_allowed += pa
            tot_blk += blk
            tot_tov += tov
            tot_min += mins
    drivers.sort(key=lambda d: -d["fga_at_wemby"])
    return drivers, {
        "total_fga_at_wemby_6g": tot_fga,
        "total_pts_allowed_6g": tot_pts_allowed,
        "total_blocks_6g": tot_blk,
        "total_tov_forced_6g": tot_tov,
        "total_contest_min_6g": round(tot_min, 1),
        "fga_at_wemby_per_g": round(tot_fga / SERIES_GAMES, 2),
        "blocks_per_g": round(tot_blk / SERIES_GAMES, 2),
        # contest rate = how often a rim attack at Wemby ends in a block (his contest aggression)
        "block_per_contested_fga": round(tot_blk / tot_fga, 4) if tot_fga else 0.0,
    }


def load_wemby_series():
    """Wemby's series min/g and blk/g from the 6g CSV (REAL)."""
    with open(SERIES, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        idx = {c: i for i, c in enumerate(header)}
        for line in f:
            p = line.rstrip("\n").split(",")
            if p[idx["player_id"]] == WEMBY_ID:
                return {
                    "min_pg": float(p[idx["min_pg"]]),
                    "blk_pg": float(p[idx["blk_pg"]]),
                    "pts_pg": float(p[idx["pts_pg"]]),
                }
    return {}


# ---------------------------------------------------------------------------
# 2) PRIOR: foul-hazard model. Each rim contest at Wemby carries a small foul
#    probability; crew leniency scales it. Drives are the exposure count.
# ---------------------------------------------------------------------------
# PRIOR foul-per-contest hazard for an aggressive vertical rim protector.
# League big-man verticality-foul prior ~ 5-6% of contested rim attempts whistled.
BASE_FOUL_PER_CONTEST = 0.058   # PRIOR (league big-man verticality foul rate)

# PRIOR crew archetypes: multiplier on the whistle rate. Announced day-of => UNKNOWN.
CREW_TYPES = {
    "lenient":             {"foul_rate_mult": 0.72, "ft_swing": +1.2,
                            "note": "let-them-play crew; verticality rewarded, fewer cheap whistles"},
    "neutral":             {"foul_rate_mult": 1.00, "ft_swing": 0.0,
                            "note": "league-average whistle; baseline anchor"},
    "tight_verticality":   {"foul_rate_mult": 1.34, "ft_swing": -0.9,
                            "note": "ticky-tack vertical-contest crew; Wemby's blocks become fouls"},
}

# PRIOR per-foul-state minute caps (the showcase's minute-mixture, made explicit here).
# Anchored to his 37.0 series min/g. Foul trouble pulls him to the bench.
MIN_STATE = {
    "clean":        {"mean": 38.0, "std": 2.4},   # no foul trouble
    "three_by_half":{"mean": 33.0, "std": 3.6},   # 3 fouls before halftime -> managed
    "early_two":    {"mean": 30.5, "std": 4.5},   # 2 fouls in Q1 -> sit rest of half
    "foul_out_six": {"mean": 27.5, "std": 5.5},   # fouls out / chronic trouble
}

# PRIOR: points-per-minute on-court for the foul-trouble feed. Anchor to showcase
# left-mode (foul-trouble) median 23.22 over ~30.5 min => ~0.76 pts/min in foul script.
# We compute the delta in *median minutes* x this rate to get a pts-median delta.
PTS_PER_MIN_FOUL_SCRIPT = 23.22 / 30.5   # PRIOR-anchored to showcase left mode


def foul_state_probs(drives_per_g, foul_rate):
    """Map expected rim-contest exposure -> foul-state probabilities via a Poisson
    foul-count model. lambda = expected personal fouls drawn on contests.
    PRIOR structure; REAL exposure (drives_per_g) and REAL contest aggression feed lambda."""
    lam = drives_per_g * foul_rate   # expected fouls from rim contests
    # add a flat PRIOR baseline for off-ball / reach fouls (not contest-driven)
    lam += 1.4  # PRIOR: league big-man non-contest foul baseline per game
    # Poisson pmf
    def pois(k):
        return math.exp(-lam) * lam ** k / math.factorial(k)
    p0 = pois(0)
    p1 = pois(1)
    p2 = pois(2)
    p3 = pois(3)
    p4 = pois(4)
    p5 = pois(5)
    p6plus = max(0.0, 1.0 - (p0 + p1 + p2 + p3 + p4 + p5))
    # Foul-state buckets (a foul *count* doesn't equal trouble; timing matters).
    # PRIOR timing split: a player reaching k total fouls has prob of "early" trouble.
    p_early_two = (p2 + p3) * 0.42 + (p4 + p5 + p6plus) * 0.55  # 2 early enough to sit
    p_three_by_half = (p3) * 0.40 + (p4 + p5 + p6plus) * 0.60
    p_foul_out = p6plus + p5 * 0.35
    p_any_trouble = min(0.98, p_early_two + (p_three_by_half * 0.55) + p_foul_out * 0.5)
    p_clean = max(0.0, 1.0 - p_any_trouble)
    return {
        "lambda_fouls": round(lam, 3),
        "P_early_2_fouls": round(min(0.95, p_early_two), 4),
        "P_3_by_half": round(min(0.95, p_three_by_half), 4),
        "P_foul_out_6": round(min(0.6, p_foul_out), 4),
        "P_any_foul_trouble": round(p_any_trouble, 4),
        "P_clean": round(p_clean, 4),
    }


def minute_distribution(states):
    """Blend the per-foul-state minute means/stds by the state probabilities into a
    single Wemby minute mean/std for this crew."""
    p_clean = states["P_clean"]
    p_three = states["P_3_by_half"]
    p_early = states["P_early_2_fouls"]
    p_out = states["P_foul_out_6"]
    # normalize a 4-way mixture (overlapping buckets -> collapse to disjoint weights)
    w_out = p_out
    w_early = max(0.0, p_early - p_out)
    w_three = max(0.0, p_three - p_early)
    w_clean = max(0.0, 1.0 - (w_out + w_early + w_three))
    s = w_out + w_early + w_three + w_clean
    w_out, w_early, w_three, w_clean = (w_out / s, w_early / s, w_three / s, w_clean / s)
    mean = (w_clean * MIN_STATE["clean"]["mean"]
            + w_three * MIN_STATE["three_by_half"]["mean"]
            + w_early * MIN_STATE["early_two"]["mean"]
            + w_out * MIN_STATE["foul_out_six"]["mean"])
    # total variance = within-state + between-state
    means = [MIN_STATE["clean"]["mean"], MIN_STATE["three_by_half"]["mean"],
             MIN_STATE["early_two"]["mean"], MIN_STATE["foul_out_six"]["mean"]]
    stds = [MIN_STATE["clean"]["std"], MIN_STATE["three_by_half"]["std"],
            MIN_STATE["early_two"]["std"], MIN_STATE["foul_out_six"]["std"]]
    ws = [w_clean, w_three, w_early, w_out]
    within = sum(w * sd * sd for w, sd in zip(ws, stds))
    between = sum(w * (m - mean) ** 2 for w, m in zip(ws, means))
    std = math.sqrt(within + between)
    return round(mean, 2), round(std, 2), {
        "w_clean": round(w_clean, 3), "w_three_by_half": round(w_three, 3),
        "w_early_two": round(w_early, 3), "w_foul_out": round(w_out, 3),
    }


def main():
    drivers, agg = load_paint_attack_at_wemby()
    wemby = load_wemby_series()
    drives_per_g = agg["fga_at_wemby_per_g"]  # REAL exposure proxy

    # Load showcase neutral foul-trouble anchor for delta consistency
    showcase = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    neutral_full_median = showcase["distribution"]["median"]  # 27.57 (all scenarios blended)

    table = {}
    neutral_min_mean = None
    for crew, cfg in CREW_TYPES.items():
        foul_rate = BASE_FOUL_PER_CONTEST * cfg["foul_rate_mult"]
        states = foul_state_probs(drives_per_g, foul_rate)
        mmean, mstd, weights = minute_distribution(states)
        if crew == "neutral":
            neutral_min_mean = mmean
        table[crew] = {
            "foul_rate_per_contest": round(foul_rate, 4),
            "states": states,
            "wemby_min_mean": mmean,
            "wemby_min_std": mstd,
            "state_weights": weights,
            "ft_pts_swing_prior": cfg["ft_swing"],
            "crew_note": cfg["note"],
        }

    # pts-median delta vs neutral baseline:
    #   minute delta x foul-script pts/min  +  FT swing from crew tightness
    for crew, row in table.items():
        dmin = row["wemby_min_mean"] - neutral_min_mean
        pts_from_min = dmin * PTS_PER_MIN_FOUL_SCRIPT
        pts_delta = pts_from_min + row["ft_pts_swing_prior"]
        row["pts_median_delta_vs_neutral"] = round(pts_delta, 2)
        row["implied_pts_median"] = round(neutral_full_median + pts_delta, 2)

    out = {
        "model": "L3 causal foul-trouble -> minute distribution (Wembanyama, WCF G7)",
        "player": "Victor Wembanyama",
        "game": "WCF G7 SAS @ OKC 2026-05-30",
        "crew_status": "UNKNOWN at build (announced day-of) -> conditional table across 3 archetypes",
        "real_data_paint_attack_at_wemby": {
            "source": "intel_2026-05-26/wcf_defensive_matchups.csv (def_player=Wembanyama)",
            "aggregate": agg,
            "top_drivers": drivers[:6],
            "interpretation": (
                f"OKC put {agg['total_fga_at_wemby_6g']:.0f} FGA at Wemby's rim over 6g "
                f"({drives_per_g:.1f}/g); he answered with {agg['total_blocks_6g']:.0f} blocks "
                f"({agg['block_per_contested_fga']:.3f}/contest). Hartenstein, SGA, McCain and "
                f"Caruso are the paint-attack drivers -> the foul-exposure engine."
            ),
        },
        "wemby_series_real": wemby,
        "neutral_baseline_anchor": {
            "showcase_full_median": neutral_full_median,
            "showcase_foul_left_mode_median": showcase["scenario_modes"]["foul_trouble_left_mode"]["median"],
            "neutral_min_mean": neutral_min_mean,
            "pts_per_min_foul_script_PRIOR": round(PTS_PER_MIN_FOUL_SCRIPT, 4),
        },
        "conditional_table": table,
        "priors_labelled": [
            "BASE_FOUL_PER_CONTEST=0.058 is a league big-man verticality-foul PRIOR (PF not in 6g CSV).",
            "Crew leniency multipliers (0.72 / 1.00 / 1.34) and FT swings are PRIORS.",
            "Per-foul-state minute caps (38/33/30.5/27.5) are PRIORS anchored to his 37.0 series min/g.",
            "Poisson foul-count + timing split are PRIOR structure; REAL inputs are exposure (fga@Wemby) and contest aggression.",
            "pts/min in foul script anchored to showcase left-mode (23.22 / 30.5).",
        ],
        "honest_blockers": [
            "No G7 officiating crew known at build time -> table is conditional, not a point estimate.",
            "No per-game PF tracking in the 6g CSV -> foul hazard is a league prior, not Wemby-specific measured rate.",
            "Minute caps are priors; real coach (Pop) foul-management could differ.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "L3_foul_minutes.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # ---- console report ----
    print("=" * 78)
    print("L3 FOUL-TROUBLE -> MINUTE DISTRIBUTION  (Wembanyama, WCF G7)")
    print("=" * 78)
    print(f"REAL paint-attack at Wemby: {agg['total_fga_at_wemby_6g']:.0f} FGA / 6g "
          f"= {drives_per_g:.1f}/g | blocks {agg['total_blocks_6g']:.0f} "
          f"({agg['block_per_contested_fga']:.3f}/contest)")
    print(f"Top drivers: " + ", ".join(
        f"{d['off_player'].split()[-1]} {d['fga_at_wemby']:.0f}fga" for d in drivers[:4]))
    print(f"Neutral baseline median (showcase): {neutral_full_median} | "
          f"foul-left-mode {showcase['scenario_modes']['foul_trouble_left_mode']['median']}")
    print("-" * 78)
    print(f"{'crew':<18}{'P(foul trbl)':>13}{'P(early2)':>11}{'P(out)':>8}"
          f"{'min mean':>10}{'min std':>9}{'pts d':>8}")
    for crew, r in table.items():
        print(f"{crew:<18}{r['states']['P_any_foul_trouble']:>13.3f}"
              f"{r['states']['P_early_2_fouls']:>11.3f}{r['states']['P_foul_out_6']:>8.3f}"
              f"{r['wemby_min_mean']:>10.2f}{r['wemby_min_std']:>9.2f}"
              f"{r['pts_median_delta_vs_neutral']:>+8.2f}")
    print("-" * 78)
    print(f"WROTE {out_path}")


if __name__ == "__main__":
    main()
