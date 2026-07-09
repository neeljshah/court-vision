"""domains.mlb.profiles.attribute_registry -- the ATTRIBUTES catalog: one
entry per batter/pitcher/catcher attribute the engine ships, PURE METADATA
(no data logic -- build_profiles.py's _BUILDERS dict is the actual dispatch,
kept separate so this file stays JSON-serializable-ish and independently
testable for registry integrity).

STATUS values (per attribute, honest -- see docs/JOB_EVIDENCE_PACKET.md):
  VALIDATED_MECHANISM -- built on a REPLICATED prereg ledger mechanism
      (data/cache/intel_claims/prereg_hypothesis_ledger.jsonl verdict=
      REPLICATED): platoon (P-hand x B-stand) x pitch type, count leverage
      (ahead/behind) x pitch-mix, base-out state x contact type (GB/FB).
  VALIDATED_CLAIM -- backed by a green (validated) claims store: catcher
      framing (mlb_framing_claims.jsonl via claims_shift_framing.py).
  DESCRIPTIVE -- a real, honestly-labeled split/rate with NO replicated
      causal mechanism behind it (either untested, or the closest mechanism
      was tested and did NOT replicate -- see TTO_durability below).

FLOOR is a single int applied to each builder's own `n` column (for split
metrics n = min of the two compared cell counts, matching the
nba_player_interaction_claims.py precedent) -- one uniform floor rule for
all 14 attributes, no per-attribute special-casing in build_profiles.py.

RATING_2K: rating_2k = 25 + percentile*0.74, percentile in [0,100] (rank-pct
within the qualified population for that attribute+window) -> a 25-99
presentation-only band, same spirit as 2K/franchise-mode overalls. NEVER a
predictive or market-facing number (edge_claimed=False everywhere upstream).
"""
from __future__ import annotations

from typing import Any

RATING_FLOOR = 25.0
RATING_SPAN = 0.74  # rating_2k = RATING_FLOOR + percentile[0..100] * RATING_SPAN


def rating_2k(percentile: float) -> float:
    """percentile in [0, 100] -> a 25..99 presentation rating. Pure math,
    no clamping needed: percentile is itself already bounded [0, 100]."""
    return RATING_FLOOR + percentile * RATING_SPAN


# weight_ledger_family ties an attribute back to the MOAT claim->prediction
# weighting ledger family it belongs to (replicated mechanism name, slugged,
# or "descriptive" for attributes with no backing mechanism/claim family yet).
ATTRIBUTES: dict[str, dict[str, Any]] = {
    # ---------------------------------------------------------------- batter
    "platoon_resilience": {
        "description": "Batter's on-base-rate delta facing a same-handed pitcher "
                        "vs an opposite-handed pitcher (less negative = more resilient).",
        "entity": "batter",
        "ingredients": ["reaches_base_same_hand", "n_same_hand", "reaches_base_opp_hand", "n_opp_hand"],
        "formula": "reaches_base_same_hand - reaches_base_opp_hand",
        "status": "VALIDATED_MECHANISM",
        "floor": 100,  # min(n_same_hand, n_opp_hand) >= 100 PA/hand, matches platoon_split_index.py precedent
        "weight_ledger_family": "platoon_pitch_type",
    },
    "pull_tendency": {
        "description": "Share of batted balls pulled (spray-angle classification, "
                        "reused from prereg_shift_unblocked.py's declared formula).",
        "entity": "batter",
        "ingredients": ["pull_share", "n_batted_balls"],
        "formula": "mean(is_pull)",
        "status": "DESCRIPTIVE",
        "floor": 50,  # batted balls w/ hc_x/hc_y this season; matches claims_shift_framing SHIFT_VULN_FLOOR precedent
        "weight_ledger_family": "descriptive",
    },
    "contact_quality": {
        "description": "Barrel share of batted balls (launch_speed_angle==6, "
                        "Statcast's own public barrel code, not re-derived here).",
        "entity": "batter",
        "ingredients": ["barrel_share", "n_batted_balls"],
        "formula": "mean(launch_speed_angle == 6)",
        "status": "DESCRIPTIVE",
        "floor": 50,
        "weight_ledger_family": "descriptive",
    },
    "discipline_by_count": {
        "description": "Swing-rate delta: pitcher-behind counts minus pitcher-ahead counts "
                        "(higher = chases more when the count favors the pitcher less).",
        "entity": "batter",
        "ingredients": ["swing_rate_behind", "n_behind", "swing_rate_ahead", "n_ahead"],
        "formula": "swing_rate_behind - swing_rate_ahead",
        "status": "DESCRIPTIVE",
        "floor": 100,
        "weight_ledger_family": "descriptive",
    },
    "clutch_baseout": {
        "description": "Ground-ball-rate delta with a runner in scoring position vs not "
                        "(base-out x contact-type mechanism, batter side).",
        "entity": "batter",
        "ingredients": ["gb_rate_risp", "n_risp", "gb_rate_no_risp", "n_no_risp"],
        "formula": "gb_rate_risp - gb_rate_no_risp",
        "status": "VALIDATED_MECHANISM",
        "floor": 30,
        "weight_ledger_family": "base_out_contact",
    },
    "K_avoidance": {
        "description": "1 - strikeout rate per plate appearance.",
        "entity": "batter",
        "ingredients": ["k_rate", "n_pa"],
        "formula": "1 - k_rate",
        "status": "DESCRIPTIVE",
        "floor": 200,  # PA/batter-season, task-declared batter floor
        "weight_ledger_family": "descriptive",
    },
    "BB_rate": {
        "description": "Walk rate per plate appearance (walk + intent_walk events).",
        "entity": "batter",
        "ingredients": ["bb_rate", "n_pa"],
        "formula": "n_bb / n_pa",
        "status": "DESCRIPTIVE",
        "floor": 200,
        "weight_ledger_family": "descriptive",
    },
    # --------------------------------------------------------------- pitcher
    "mix_by_leverage": {
        "description": "Breaking-pitch-share delta: pitcher-ahead counts minus pitcher-not-ahead "
                        "counts (count-leverage x pitch-mix mechanism).",
        "entity": "pitcher",
        "ingredients": ["breaking_share_ahead", "n_ahead", "breaking_share_not_ahead", "n_not_ahead"],
        "formula": "breaking_share_ahead - breaking_share_not_ahead",
        "status": "VALIDATED_MECHANISM",
        "floor": 100,
        "weight_ledger_family": "count_leverage_mix",
    },
    "velo_band": {
        "description": "Mean release speed (mph) across all pitches thrown this season.",
        "entity": "pitcher",
        "ingredients": ["velo_mean", "velo_std", "n_pitches"],
        "formula": "mean(release_speed)",
        "status": "DESCRIPTIVE",
        "floor": 500,  # pitches/pitcher-season, task-declared pitcher floor
        "weight_ledger_family": "descriptive",
    },
    "TTO_durability": {
        "description": "xwOBA-against delta: third-time-through-the-order minus first time "
                        "through. DESCRIPTIVE by design -- the closest mechanism (starter "
                        "velo-band x TTO) was tested and FAILED_REPLICATION on savant_full__2024 "
                        "(prereg_hypothesis_ledger.jsonl); this is a plain split, no causal claim.",
        "entity": "pitcher",
        "ingredients": ["woba_tto1", "n_tto1", "woba_tto3plus", "n_tto3plus"],
        "formula": "woba_tto3plus - woba_tto1",
        "status": "DESCRIPTIVE",
        "floor": 60,  # PA/bucket, matches mlb_tto_claims.py MIN_PA_PER_BUCKET precedent
        "weight_ledger_family": "descriptive",
    },
    "platoon_split": {
        "description": "On-base-rate-allowed delta: vs right-handed batters minus vs "
                        "left-handed batters.",
        "entity": "pitcher",
        "ingredients": ["reaches_base_vs_r", "n_vs_r", "reaches_base_vs_l", "n_vs_l"],
        "formula": "reaches_base_vs_r - reaches_base_vs_l",
        "status": "DESCRIPTIVE",
        "floor": 100,
        "weight_ledger_family": "descriptive",
    },
    "whiff_rate": {
        "description": "Swing-and-miss rate among swings (description-coded: "
                        "swinging_strike[_blocked] / all swing outcomes).",
        "entity": "pitcher",
        "ingredients": ["whiff_rate", "n_swings"],
        "formula": "n_miss / n_swings",
        "status": "DESCRIPTIVE",
        "floor": 100,  # swings/pitcher-season (metric's own denominator)
        "weight_ledger_family": "descriptive",
    },
    "gb_tendency": {
        "description": "Ground-ball share of balls in play allowed (bb_type from hitcoords corpus).",
        "entity": "pitcher",
        "ingredients": ["gb_share", "n_bip"],
        "formula": "mean(bb_type == 'ground_ball')",
        "status": "DESCRIPTIVE",
        "floor": 50,
        "weight_ledger_family": "descriptive",
    },
    # --------------------------------------------------------------- catcher
    "framing": {
        "description": "Borderline called-strike rate (edge-shell takes), reused from "
                        "prereg_shift_framing.py / claims_shift_framing.py's VALIDATED_CLAIM "
                        "machinery -- zero reimplementation.",
        "entity": "catcher",
        "ingredients": ["borderline_strike_rate", "n_borderline_takes"],
        "formula": "mean(is_strike)",
        "status": "VALIDATED_CLAIM",
        "floor": 500,  # CATCHER_FLOOR, reused constant from prereg_shift_framing.py
        "weight_ledger_family": "framing",
    },
}

ENTITIES = ("batter", "pitcher", "catcher")
STATUSES = ("VALIDATED_MECHANISM", "VALIDATED_CLAIM", "DESCRIPTIVE")


def attributes_for(entity: str) -> list[str]:
    return [name for name, spec in ATTRIBUTES.items() if spec["entity"] == entity]
