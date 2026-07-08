"""domains.mlb.prereg.mlb_hypotheses -- the 10 MLB coach-mechanism hypotheses
preregistered in docs/research/coach_composition_architecture_2026_07_08.md
section (d), run at the ATOMIC unit named in the doc, on statcast_fuller
2022+2023 (data/cache/statcast/statcast_fuller__{2022,2023}.parquet -- the
same corpus catcher_framing_index.py / acquire_statcast_fuller.py load).

METHOD, no invention beyond what the doc names:
  1. PREMISE-CHECK. 5 of 10 need a column this corpus does not have (no
     launch_angle, no base-runner state, no leverage index, no sprint_speed,
     and -- confirmed by catcher_framing_index.py's own CORRECTNESS FIX --
     no isolatable called-strike code, so "framing" itself is not
     computable) -- BLOCKED-on-premise, not tested, doc names no proxy.
  2. The 5 with data present get an interaction logistic fit; the
     interaction term's p-value is compared to alpha_fwer(K), K = hypotheses
     actually TESTED this run.

Descriptive/measurement only. edge_claimed hard-wired False (stats_common).
NETWORK: zero. CLI: python -m domains.mlb.prereg.mlb_hypotheses
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from domains.mlb.prereg.stats_common import (
    LEDGER_PATH, alpha_fwer, append_ledger, blocked_row, fit_interaction, tested_row,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_STATCAST_DIR = REPO_ROOT / "data" / "cache" / "statcast"
SEASONS = (2022, 2023)
SPORT = "mlb"

# Fastball family (SI/FC/FA/FF); everything else (breaking + offspeed) is is_breaking.
FASTBALL_TYPES = {"FF", "SI", "FC", "FA"}
# PA-terminal outcomes: reaches base (batter success) vs recorded out; ambiguous rows
# (truncated_pa, catcher_interf) are dropped rather than force-labeled either way.
_POS_EVENTS = {"single", "double", "triple", "home_run", "walk", "intent_walk", "hit_by_pitch"}
_NEG_EVENTS = {"field_out", "strikeout", "force_out", "grounded_into_double_play", "sac_fly",
               "field_error", "double_play", "fielders_choice", "fielders_choice_out",
               "strikeout_double_play", "sac_bunt"}
_BIP_HIT_EVENTS = {"single", "double", "triple"}  # BABIP numerator (HR excluded, standard convention)
_BIP_OUT_EVENTS = {"field_out", "force_out", "grounded_into_double_play", "sac_fly",
                   "field_error", "double_play", "fielders_choice", "fielders_choice_out"}

BLOCKED_REASONS: Dict[str, str] = {
    "bullpen fatigue-chain x leverage": "no leverage_index / win-probability column and no "
        "base-runner state to derive one (see base-out block below); doc names no coarse "
        "late-inning+close-score proxy -- not inventing one.",
    "launch-angle tightness x park factor": "no launch_angle column on statcast_fuller (only "
        "launch_speed present); doc names no proxy for launch angle.",
    "catcher framing x pitch location (edge)": "framing is NOT computable on this corpus -- "
        "catcher_framing_index.py's own CORRECTNESS FIX: type=='S' bundles called-strike + "
        "swinging-strike + foul with no isolating code, so a called-strike framing rate cannot "
        "be built; doc names no accepted substitute metric.",
    "base-out state x contact type (GB/FB)": "no base-runner columns (on_1b/on_2b/on_3b absent "
        "from statcast_fuller) -- a known, previously-documented corpus limit.",
    "sprint-speed x infield-alignment": "no sprint_speed column on statcast_fuller; doc names "
        "no proxy for baserunning speed.",
}


def load_statcast(seasons=SEASONS) -> pd.DataFrame:
    frames = [pd.read_parquet(_STATCAST_DIR / f"statcast_fuller__{s}.parquet") for s in seasons]
    return pd.concat(frames, ignore_index=True)


def pitcher_entropy(df: pd.DataFrame) -> pd.DataFrame:
    """h1: season-long (both seasons pooled, in-sample descriptor -- same
    documented limit as shooter_zone_efg elsewhere in this codebase) Shannon
    entropy of a pitcher's pitch-type mix, computed over ALL pitches
    (repertoire diversity), not just PA-terminal ones."""
    valid = df[df["pitch_type"].notna()]
    counts = valid.groupby(["pitcher", "pitch_type"]).size().reset_index(name="n")
    counts["p"] = counts["n"] / counts.groupby("pitcher")["n"].transform("sum")
    counts["entropy_contrib"] = -(counts["p"] * np.log(counts["p"]))
    return counts.groupby("pitcher")["entropy_contrib"].sum().reset_index(name="pitch_entropy")


def add_reaches_base(df: pd.DataFrame) -> pd.DataFrame:
    """One row per PA (the terminal pitch, `events` non-null); ambiguous
    events (truncated_pa/catcher_interf) dropped, never force-labeled."""
    term = df[df["events"].notna()].copy()
    term = term[term["events"].isin(_POS_EVENTS | _NEG_EVENTS)]
    term["reaches_base"] = term["events"].isin(_POS_EVENTS).astype(int)
    return term


def add_tto(term: pd.DataFrame) -> pd.DataFrame:
    """Times-through-order = this batter's Nth PA vs this pitcher, THIS GAME
    (standard TTO definition); tto3 = 1 for the 3rd-or-later time through."""
    term = term.sort_values(["game_pk", "pitcher", "batter", "at_bat_number"]).copy()
    term["tto"] = term.groupby(["game_pk", "pitcher", "batter"]).cumcount() + 1
    term["tto3"] = (term["tto"] >= 3).astype(int)
    return term


def build_h1_pitchmix_tto(df: pd.DataFrame) -> pd.DataFrame:
    ent = pitcher_entropy(df)
    term = add_tto(add_reaches_base(df)).merge(ent, on="pitcher", how="inner")
    return term[["reaches_base", "pitch_entropy", "tto3"]].dropna()


def build_h2_alignment_stand_babip(df: pd.DataFrame) -> pd.DataFrame:
    bip = df[(df["type"] == "X") & (df["events"].isin(_BIP_HIT_EVENTS | _BIP_OUT_EVENTS))].copy()
    bip["outcome_hit"] = bip["events"].isin(_BIP_HIT_EVENTS).astype(int)
    bip["is_shift"] = (bip["if_fielding_alignment"] == "Infield shift").astype(int)
    bip["is_right"] = (bip["stand"] == "R").astype(int)
    return bip[["outcome_hit", "is_shift", "is_right"]].dropna()


def build_h4_platoon_pitchtype(df: pd.DataFrame) -> pd.DataFrame:
    term = add_reaches_base(df)
    term["platoon_same_hand"] = (term["p_throws"] == term["stand"]).astype(int)
    term["is_breaking"] = (~term["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    return term[["reaches_base", "platoon_same_hand", "is_breaking"]].dropna()


def build_h5_count_pitchmix(df: pd.DataFrame) -> pd.DataFrame:
    """`type` (S/B/X) is the only pitch-result code on this corpus (no
    swing/take column) -- consistent with the catcher_framing_index.py
    precedent, is_strike is restricted to non-in-play pitches (type in S/B)."""
    x = df[df["type"].isin(["S", "B"]) & df["pitch_type"].notna()].copy()
    x["is_strike"] = (x["type"] == "S").astype(int)
    x["pitcher_ahead"] = (x["strikes"] > x["balls"]).astype(int)
    x["is_breaking"] = (~x["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    return x[["is_strike", "pitcher_ahead", "is_breaking"]].dropna()


def build_h8_velo_tto(df: pd.DataFrame) -> pd.DataFrame:
    term = add_tto(add_reaches_base(df))
    avg_velo = df.groupby("pitcher")["release_speed"].mean().rename("avg_velo")
    term = term.merge(avg_velo, on="pitcher", how="inner")
    term["above_avg_velo"] = (term["release_speed"] > term["avg_velo"]).astype(int)
    return term[["reaches_base", "above_avg_velo", "tto3"]].dropna()


def run() -> tuple[list, int]:
    df = load_statcast()
    rows = [blocked_row(name, SPORT, "n/a", reason) for name, reason in BLOCKED_REASONS.items()]

    k = 5  # #1,#2,#4,#5,#8 -- the only ones with data present this census
    alpha = alpha_fwer(k)

    fit1 = fit_interaction(build_h1_pitchmix_tto(df), "reaches_base ~ pitch_entropy * tto3", kind="logit")
    rows.append(tested_row("pitch-mix diversity x times-through-order (TTO)", SPORT, "PA", fit1, alpha))

    fit2 = fit_interaction(build_h2_alignment_stand_babip(df), "outcome_hit ~ is_shift * is_right", kind="logit")
    rows.append(tested_row("fielding alignment (shift) x batter stand x BABIP", SPORT, "batted ball", fit2, alpha))

    fit4 = fit_interaction(build_h4_platoon_pitchtype(df), "reaches_base ~ platoon_same_hand * is_breaking", kind="logit")
    rows.append(tested_row("platoon (P-hand x B-stand) x pitch type", SPORT, "PA", fit4, alpha))

    fit5 = fit_interaction(build_h5_count_pitchmix(df), "is_strike ~ pitcher_ahead * is_breaking", kind="logit")
    rows.append(tested_row("count leverage (ahead/behind) x pitch-mix", SPORT, "pitch", fit5, alpha))

    fit8 = fit_interaction(build_h8_velo_tto(df), "reaches_base ~ above_avg_velo * tto3", kind="logit")
    rows.append(tested_row("starter velo-band x TTO", SPORT, "PA", fit8, alpha))

    return rows, k


def main() -> int:
    rows, k = run()
    print(f"K tested (MLB)={k} alpha_fwer={alpha_fwer(k):.6f}")
    for r in rows:
        print(f"  [{r['verdict']:>16}] {r['hypothesis']}: n={r['n']} effect={r['effect']} p={r['p']}")
    append_ledger(rows)
    print(f"appended {len(rows)} rows -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
