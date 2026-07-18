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

ATTACK ZONES (declared BEFORE running -- full geometry + rationale lives in
ingredients_pitcher_zones.py, the module that implements it; this is pure
metadata so only the boundary SUMMARY is restated here): heart/shadow/chase/
waste, a signed distance to the nearest strike-zone-rectangle edge (reused
verbatim from prereg_shift_framing.classify_borderline) bucketed at
+-0.25ft (SHADOW_FT, framing's own declared edge-shell half-width) and
+1.00ft (CHASE_FT, declared before running) beyond the true zone edge.
Statcast-standard-adjacent, not a literal replica of Statcast's unpublished
exact cutoffs. See ingredients_pitcher_zones/ingredients_batter_zones.py
(63 -> 110 total attributes).
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
    "chase_rate": {
        "description": "Overall swing rate on out-of-zone (Statcast zone>=11) pitches -- flat "
                        "aggregate version of the chase_vs_{cls} pitch-class splits below (added "
                        "for the two_strike_chase_rate_rises knowledge-ledger mechanism's factory "
                        "mapping, domains/mlb/knowledge/validation_ledger.jsonl).",
        "entity": "batter",
        "ingredients": ["chase_rate", "n_out_of_zone"],
        "formula": "mean(is_swing), zone>=11",
        "status": "DESCRIPTIVE",
        "floor": 50,
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
    "edge_zone_rate": {
        "description": "Share of all pitches thrown landing in the raw Statcast edge zone (zone "
                        "11-14, the four just-outside-the-corners cells) -- added for the "
                        "edge_zone_widens_with_two_strikes knowledge-ledger mechanism's factory "
                        "mapping (domains/mlb/knowledge/validation_ledger.jsonl); a plain zone>=11 "
                        "aggregate, not the custom heart/shadow/chase/waste geometry above.",
        "entity": "pitcher",
        "ingredients": ["edge_zone_rate", "n_pitches"],
        "formula": "mean(zone in [11,12,13,14])",
        "status": "DESCRIPTIVE",
        "floor": 100,
        "weight_ledger_family": "descriptive",
    },
    "release_spin_rate": {
        "description": "Mean release spin rate (rpm) across all pitches thrown -- added for the "
                        "spin_rate_deception knowledge-ledger mechanism's factory mapping "
                        "(domains/mlb/knowledge/validation_ledger.jsonl); a flat aggregate, not "
                        "restricted to breaking pitches like the ledger's own OLS receipt.",
        "entity": "pitcher",
        "ingredients": ["release_spin_rate", "n_pitches"],
        "formula": "mean(release_spin_rate)",
        "status": "DESCRIPTIVE",
        "floor": 100,
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

# ------------------------------------------------------------------ grid attributes
# Explosion from the flat 14 above: pitch-class (fastball/breaking/offspeed,
# see ingredients_pitcher_grid.classify_pitch_class) x count-state /
# situational grids. Every cell below is its OWN attribute (own floor, own
# percentile population) -- generated by loop to avoid 49 hand-typed near-
# duplicate dict literals, not a change in the registry's semantics (still
# pure metadata, still one entry per shipped attribute). ALL DESCRIPTIVE:
# these are finer-grained decompositions of ideas near a replicated
# mechanism (e.g. mix_by_leverage's ahead/not-ahead pitch-mix), not
# themselves individually replication-tested -- mix_by_leverage above stays
# the ONE attribute that earned VALIDATED_MECHANISM.
_COUNT_STATES = ("ahead", "even", "behind")
PITCH_CLASSES = ("fastball", "breaking", "offspeed")


def _grid_pitcher_attributes() -> dict[str, dict[str, Any]]:
    attrs: dict[str, dict[str, Any]] = {}
    for cls in PITCH_CLASSES:
        for state in _COUNT_STATES:
            attrs[f"mix_{cls}_{state}"] = {
                "description": f"Share of pitches that are {cls}-class, restricted to counts where "
                                f"the pitcher is {state} (count-leverage x pitch-mix grid cell).",
                "entity": "pitcher",
                "ingredients": [f"share_{cls}_{state}", "n_total_pitches"],
                "formula": f"n_{cls} / n_total, count_state={state}",
                "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
            }
        attrs[f"whiff_by_class_{cls}"] = {
            "description": f"Swing-and-miss rate among swings against {cls}-class pitches.",
            "entity": "pitcher", "ingredients": ["whiff_rate", "n_swings"],
            "formula": f"n_miss / n_swings, pitch_class={cls}",
            "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
        }
        attrs[f"called_strike_by_class_{cls}"] = {
            "description": f"Called-strike rate among taken (ball/called_strike) {cls}-class pitches.",
            "entity": "pitcher", "ingredients": ["called_strike_rate", "n_taken"],
            "formula": f"n_called_strike / n_taken, pitch_class={cls}",
            "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
        }
        attrs[f"xwoba_against_by_class_{cls}"] = {
            "description": f"xwOBA allowed on balls in play against {cls}-class pitches.",
            "entity": "pitcher", "ingredients": ["xwoba_against", "n_bip"],
            "formula": f"mean(estimated_woba_using_speedangle), pitch_class={cls}, type==X",
            "status": "DESCRIPTIVE", "floor": 30, "weight_ledger_family": "descriptive",
        }
        attrs[f"velo_mean_{cls}"] = {
            "description": f"Mean release speed (mph) on {cls}-class pitches.",
            "entity": "pitcher", "ingredients": ["velo_mean", "n_pitches"],
            "formula": f"mean(release_speed), pitch_class={cls}",
            "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
        }
        attrs[f"velo_std_{cls}"] = {
            "description": f"Std dev of release speed (mph) on {cls}-class pitches (consistency proxy).",
            "entity": "pitcher", "ingredients": ["velo_std", "n_pitches"],
            "formula": f"std(release_speed), pitch_class={cls}",
            "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
        }
    attrs["first_pitch_strike_rate"] = {
        "description": "Strike rate on 0-0 (first pitch of PA) counts.",
        "entity": "pitcher", "ingredients": ["fps_rate", "n_first_pitches"],
        "formula": "mean(type in [S, X]), balls==0 and strikes==0",
        "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
    }
    attrs["putaway_rate"] = {
        "description": "Strikeout conversion rate on PAs that reached a 2-strike count.",
        "entity": "pitcher", "ingredients": ["putaway_rate", "n_two_strike_pa"],
        "formula": "n_strikeout / n_pa_reaching_2_strikes",
        "status": "DESCRIPTIVE", "floor": 60, "weight_ledger_family": "descriptive",
    }
    attrs["velo_decline_in_game"] = {
        "description": "Release-speed delta: pitches 76+ this game minus the first 25 (in-game fatigue "
                        "proxy -- DESCRIPTIVE by design, velo x TTO was KILLED as a mechanism, see "
                        "TTO_durability above).",
        "entity": "pitcher",
        "ingredients": ["velo_first25", "n_first25", "velo_after75", "n_after75"],
        "formula": "velo_after75 - velo_first25",
        "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
    }
    attrs["command_edge_share"] = {
        "description": "Share of taken pitches classified borderline (zone-edge shell, reused from "
                        "prereg_shift_framing.classify_borderline -- zero reimplementation).",
        "entity": "pitcher", "ingredients": ["edge_share", "n_taken"],
        "formula": "mean(classify_borderline(taken))",
        "status": "DESCRIPTIVE", "floor": 200, "weight_ledger_family": "descriptive",
    }
    attrs["command_edge_share_behind"] = {
        "description": "Same as command_edge_share, restricted to counts where the pitcher is behind "
                        "(balls > strikes) -- command under pressure.",
        "entity": "pitcher", "ingredients": ["edge_share", "n_taken_behind"],
        "formula": "mean(classify_borderline(taken)), balls>strikes",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
    }
    return attrs


def _grid_batter_attributes() -> dict[str, dict[str, Any]]:
    attrs: dict[str, dict[str, Any]] = {}
    for cls in PITCH_CLASSES:
        attrs[f"whiff_vs_{cls}"] = {
            "description": f"Swing-and-miss rate among swings against {cls}-class pitches.",
            "entity": "batter", "ingredients": ["whiff_rate", "n_swings"],
            "formula": f"n_miss / n_swings, pitch_class={cls}",
            "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        }
        attrs[f"xwoba_contact_vs_{cls}"] = {
            "description": f"xwOBA on contact (balls in play) against {cls}-class pitches.",
            "entity": "batter", "ingredients": ["xwoba_on_contact", "n_bip"],
            "formula": f"mean(estimated_woba_using_speedangle), pitch_class={cls}, type==X",
            "status": "DESCRIPTIVE", "floor": 20, "weight_ledger_family": "descriptive",
        }
        attrs[f"chase_vs_{cls}"] = {
            "description": f"Swing rate on out-of-zone (zone>=11) {cls}-class pitches (chase rate).",
            "entity": "batter", "ingredients": ["chase_rate", "n_out_of_zone"],
            "formula": f"mean(is_swing), pitch_class={cls}, zone>=11",
            "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        }
    for state, desc in (("ahead", "batter ahead in count (balls>strikes)"),
                         ("behind", "batter behind in count (strikes>balls)"),
                         ("two_strike", "PA ended at 2 strikes")):
        attrs[f"xwoba_{state}"] = {
            "description": f"xwOBA on PAs ending with the count {desc}.",
            "entity": "batter", "ingredients": ["xwoba", "n_pa"],
            "formula": f"mean(estimated_woba_using_speedangle), count_state={state}",
            "status": "DESCRIPTIVE", "floor": 60, "weight_ledger_family": "descriptive",
        }
    attrs["first_pitch_swing_rate"] = {
        "description": "Swing rate on 0-0 (first pitch of PA) counts.",
        "entity": "batter", "ingredients": ["swing_rate", "n_first_pitches"],
        "formula": "mean(is_swing), balls==0 and strikes==0",
        "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
    }
    for bb, label in (("gb", "ground-ball"), ("ld", "line-drive"), ("fb", "fly-ball")):
        attrs[f"{bb}_share_batter"] = {
            "description": f"{label.capitalize()} share of batted balls (bb_type).",
            "entity": "batter", "ingredients": [f"{bb}_share", "n_bip"],
            "formula": f"n_{bb} / n_bip",
            "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        }
    attrs["hard_contact_share"] = {
        "description": "Hard-hit share of batted balls (launch_speed_angle in {5,6} -- broader than "
                        "contact_quality's barrels-only ==6).",
        "entity": "batter", "ingredients": ["hard_contact_share", "n_batted_balls"],
        "formula": "mean(launch_speed_angle in [5, 6])",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
    }
    attrs["spray_entropy"] = {
        "description": "Shannon entropy of the pull/center/oppo spray-angle distribution (spray "
                        "unpredictability; reuses spray_angle_deg from prereg_shift_unblocked).",
        "entity": "batter", "ingredients": ["entropy", "n_batted_balls"],
        "formula": "-sum(p * ln(p)) over {pull, center, oppo}",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
    }
    attrs["risp_xwoba_delta"] = {
        "description": "xwOBA delta: PAs with a runner in scoring position minus PAs without.",
        "entity": "batter", "ingredients": ["xwoba_risp", "n_risp", "xwoba_no_risp", "n_no_risp"],
        "formula": "xwoba_risp - xwoba_no_risp",
        "status": "DESCRIPTIVE", "floor": 30, "weight_ledger_family": "descriptive",
    }
    attrs["inning_late_xwoba_delta"] = {
        "description": "xwOBA delta: innings 7+ minus innings 1-6.",
        "entity": "batter", "ingredients": ["xwoba_late", "n_late", "xwoba_early", "n_early"],
        "formula": "xwoba_late - xwoba_early",
        "status": "DESCRIPTIVE", "floor": 60, "weight_ledger_family": "descriptive",
    }
    return attrs


ATTRIBUTES.update(_grid_pitcher_attributes())
ATTRIBUTES.update(_grid_batter_attributes())

# ------------------------------------------------------------------ attack-zone grid attributes
# heart/shadow/chase/waste region x metric (see module docstring ATTACK
# ZONES for the boundary declaration). ATTACK_ZONES redeclared locally (not
# imported) -- same "pure metadata, no data logic" discipline as PITCH_CLASSES
# above; the actual geometry lives in ingredients_pitcher_zones.py.
ATTACK_ZONES = ("heart", "shadow", "chase", "waste")


def _grid_zone_pitcher_attributes() -> dict[str, dict[str, Any]]:
    attrs: dict[str, dict[str, Any]] = {}
    for z in ATTACK_ZONES:
        attrs[f"region_pitch_share_{z}"] = {
            "description": f"Share of all pitches thrown that land in the {z.upper()} attack zone.",
            "entity": "pitcher", "ingredients": [f"share_{z}", "n_total_pitches"],
            "formula": f"n_{z} / n_total_pitches",
            "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
        }
        attrs[f"region_whiff_rate_{z}"] = {
            "description": f"Swing-and-miss rate among swings against pitches in the {z.upper()} zone.",
            "entity": "pitcher", "ingredients": ["whiff_rate", "n_swings"],
            "formula": f"n_miss / n_swings, attack_zone={z}",
            "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
        }
        attrs[f"region_called_strike_rate_{z}"] = {
            "description": f"Called-strike rate among taken pitches in the {z.upper()} zone.",
            "entity": "pitcher", "ingredients": ["called_strike_rate", "n_taken"],
            "formula": f"n_called_strike / n_taken, attack_zone={z}",
            "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
        }
        attrs[f"region_xwoba_against_{z}"] = {
            "description": f"xwOBA allowed on balls in play in the {z.upper()} zone.",
            "entity": "pitcher", "ingredients": ["xwoba_against", "n_bip"],
            "formula": f"mean(estimated_woba_using_speedangle), attack_zone={z}, type==X",
            "status": "DESCRIPTIVE", "floor": 30, "weight_ledger_family": "descriptive",
        }
        for cls in PITCH_CLASSES:
            attrs[f"region_mix_{z}_{cls}"] = {
                "description": f"Share of {z.upper()}-zone pitches that are {cls}-class.",
                "entity": "pitcher", "ingredients": [f"share_{cls}", "n_region_pitches"],
                "formula": f"n_{cls} / n_region_pitches, attack_zone={z}",
                "status": "DESCRIPTIVE", "floor": 100, "weight_ledger_family": "descriptive",
            }
    attrs["chase_induce_rate_ahead"] = {
        "description": "Batter swing rate on CHASE-zone pitches, restricted to counts where the "
                        "pitcher is ahead (strikes>balls) -- pitcher's chase-inducing ability with "
                        "the count advantage.",
        "entity": "pitcher", "ingredients": ["chase_induce_rate", "n_chase_ahead"],
        "formula": "mean(is_swing), attack_zone=chase, strikes>balls",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
    }
    attrs["heart_share_behind"] = {
        "description": "Share of pitches landing in the HEART zone, restricted to counts where the "
                        "pitcher is behind (balls>strikes) -- damage-exposure proxy.",
        "entity": "pitcher", "ingredients": ["heart_share", "n_pitches_behind"],
        "formula": "mean(attack_zone==heart), balls>strikes",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
    }
    return attrs


def _grid_zone_batter_attributes() -> dict[str, dict[str, Any]]:
    attrs: dict[str, dict[str, Any]] = {}
    for z in ATTACK_ZONES:
        attrs[f"region_swing_rate_{z}"] = {
            "description": f"Swing rate on pitches in the {z.upper()} attack zone.",
            "entity": "batter", "ingredients": ["swing_rate", "n_region_pitches"],
            "formula": f"mean(is_swing), attack_zone={z}",
            "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        }
        attrs[f"region_whiff_vs_{z}"] = {
            "description": f"Swing-and-miss rate among swings against pitches in the {z.upper()} zone.",
            "entity": "batter", "ingredients": ["whiff_rate", "n_swings"],
            "formula": f"n_miss / n_swings, attack_zone={z}",
            "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        }
        attrs[f"region_xwoba_contact_{z}"] = {
            "description": f"xwOBA on contact (balls in play) in the {z.upper()} zone.",
            "entity": "batter", "ingredients": ["xwoba_on_contact", "n_bip"],
            "formula": f"mean(estimated_woba_using_speedangle), attack_zone={z}, type==X",
            "status": "DESCRIPTIVE", "floor": 20, "weight_ledger_family": "descriptive",
        }
    attrs["shadow_take_rate"] = {
        "description": "1 - swing rate on SHADOW-zone (borderline) pitches -- discipline: how often "
                        "a batter lays off the zone edge.",
        "entity": "batter", "ingredients": ["take_rate", "n_shadow_pitches"],
        "formula": "1 - mean(is_swing), attack_zone=shadow",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
    }
    for cls in PITCH_CLASSES:
        attrs[f"chase_rate_by_class_{cls}"] = {
            "description": f"Swing rate on CHASE-zone {cls}-class pitches.",
            "entity": "batter", "ingredients": ["chase_rate", "n_chase_pitches"],
            "formula": f"mean(is_swing), attack_zone=chase, pitch_class={cls}",
            "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        }
    attrs["heart_damage_xwoba"] = {
        "description": "xwOBA on contact restricted to the HEART zone -- damage exposure on the "
                        "easiest pitches to drive.",
        "entity": "batter", "ingredients": ["xwoba_on_heart_contact", "n_bip"],
        "formula": "mean(estimated_woba_using_speedangle), attack_zone=heart, type==X",
        "status": "DESCRIPTIVE", "floor": 20, "weight_ledger_family": "descriptive",
    }
    return attrs


ATTRIBUTES.update(_grid_zone_pitcher_attributes())
ATTRIBUTES.update(_grid_zone_batter_attributes())

# ------------------------------------------------------------------ leaderboard attributes
# Bat-tracking (batter) + outs-above-average/catch-probability (fielder) --
# 2024+ Statcast LEADERBOARD data (bat-tracking didn't exist before 2024; see
# scripts/platformkit/data_frontier/savant_bat_tracking.py for the puller +
# column semantics). Builder signature differs on purpose: these are keyed by
# YEAR and read a per-year leaderboard CSV directly, not the season pitch-frame
# every other builder above takes -- see ingredients_leaderboard.py and
# build_profiles.py's separate LEADERBOARD_YEARS loop. raw_value is Savant's
# OWN pre-aggregated leaderboard column, never re-derived from pitch data.


def _leaderboard_attributes() -> dict[str, dict[str, Any]]:
    attrs: dict[str, dict[str, Any]] = {}
    attrs["swing_speed"] = {
        "description": "Average bat speed (mph) across all competitive swings this season "
                        "(Statcast bat-tracking leaderboard, avg_bat_speed).",
        "entity": "batter",
        "ingredients": ["avg_bat_speed", "swings_competitive"],
        "formula": "avg_bat_speed (Savant leaderboard value)",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        "family": "bat_tracking",
    }
    attrs["squared_up_rate"] = {
        "description": "Share of competitive swings classified 'squared up' (Savant's own "
                        "bat-speed/exit-velo efficiency classification).",
        "entity": "batter",
        "ingredients": ["squared_up_per_swing", "swings_competitive"],
        "formula": "squared_up_per_swing (Savant leaderboard value)",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        "family": "bat_tracking",
    }
    attrs["blast_rate"] = {
        "description": "Share of competitive swings classified a 'blast' (Savant's combined "
                        "bat-speed + squared-up damage-swing rate).",
        "entity": "batter",
        "ingredients": ["blast_per_swing", "swings_competitive"],
        "formula": "blast_per_swing (Savant leaderboard value)",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        "family": "bat_tracking",
    }
    attrs["sword_rate"] = {
        "description": "Swords per competitive swing (Savant's fooled-so-badly-the-bat-nearly-"
                        "hits-the-ground indicator; higher = fooled more often, not a value "
                        "judgment -- purely descriptive).",
        "entity": "batter",
        "ingredients": ["swords", "swings_competitive"],
        "formula": "n_swords / swings_competitive",
        "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
        "family": "bat_tracking",
    }
    attrs["range_oaa"] = {
        "description": "Outs Above Average (range/positioning defensive runs saved, Savant's own "
                        "outs_above_average leaderboard value). n is cross-joined from the "
                        "catch_probability leaderboard's total chances (that CSV has no chances "
                        "column of its own) -- documented cross-file join, not fabricated.",
        "entity": "fielder",
        "ingredients": ["outs_above_average", "n_chances_catch_prob"],
        "formula": "outs_above_average (Savant leaderboard value)",
        "status": "DESCRIPTIVE", "floor": 20, "weight_ledger_family": "descriptive",
        "family": "fielding_oaa",
    }
    attrs["difficult_play_conversion"] = {
        "description": "Out-conversion rate on 1-star (Savant's toughest, <10%-catch-probability) "
                        "batted balls -- highlight-reel defensive range, distinct from aggregate OAA.",
        "entity": "fielder",
        "ingredients": ["n_fieldout_1stars", "n_opp_1stars"],
        "formula": "n_fieldout_1stars / n_opp_1stars",
        "status": "DESCRIPTIVE", "floor": 10, "weight_ledger_family": "descriptive",
        "family": "fielding_oaa",
    }
    return attrs


# ---------------------------------------------------------------------------
# CROSS-GAME CARRYOVER as-of family (C4 lane, depth-frontier item 4): the SP's
# own prior-start realized load (pitch count + rest days), LAG-1 -- domains/
# mlb/carryover_asof.py. entity="pitcher" (MLB's ENTITIES has no "team" value;
# these are genuinely pitcher-level quantities before the interaction_factory
# aggregates them to a team-game diff, see builders_carryover.py). Tagged
# `family` for future auto-discovery consistency with the NBA carryover_asof
# family, though mlb_carryover_self_cross itself declares a plain attribute
# pool (see generator.py) rather than an entity/family pool.
ATTRIBUTES["sp_prior_pitch_count_asof"] = {
    "description": "Starting pitcher's own immediately-PRIOR start's pitch count "
                    "(LAG-1, not a rolling mean) -- a fatigue-carryover proxy.",
    "entity": "pitcher",
    "family": "carryover_asof",
    "ingredients": ["n_pitches_prior_start", "game_date"],
    "formula": "LAG-1 (immediately-prior start) pitch count for this pitcher",
    "status": "DESCRIPTIVE", "floor": 10, "weight_ledger_family": "descriptive",
}
ATTRIBUTES["sp_rest_days_asof"] = {
    "description": "Days between this start and the starting pitcher's own prior start.",
    "entity": "pitcher",
    "family": "carryover_asof",
    "ingredients": ["game_date", "game_date_prior_start"],
    "formula": "this_start_date - prior_start_date, in days",
    "status": "DESCRIPTIVE", "floor": 10, "weight_ledger_family": "descriptive",
}

ATTRIBUTES.update(_leaderboard_attributes())

# ------------------------------------------------------------------ batted-ball quality (Family 1, 2026-07-18)
# Raw contact-quality metrics missing from the original 14 -- see
# domains/mlb/profiles/ingredients_batted_ball.py for the builders + the
# verified-against-real-data numbers (avg EV 88.3, hard-hit share 0.390,
# barrel share 0.078, league BABIP 0.290 on 2024 savant_hitcoords). All BIP
# (type=='X') except babip, which uses the events column directly.
ATTRIBUTES["avg_exit_velocity"] = {
    "description": "Average exit velocity (mph) on batted balls (BIP, type=='X').",
    "entity": "batter",
    "ingredients": ["avg_exit_velocity", "n_batted_balls"],
    "formula": "mean(launch_speed), type=='X'",
    "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
}
ATTRIBUTES["hard_hit_rate"] = {
    "description": "Share of batted balls (BIP) hit at exit velocity >= 95 mph.",
    "entity": "batter",
    "ingredients": ["hard_hit_rate", "n_batted_balls"],
    "formula": "mean(launch_speed >= 95), type=='X'",
    "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
}
ATTRIBUTES["barrel_rate"] = {
    "description": "Barrel share of batted balls (Statcast launch_speed_angle==6 -- "
                    "the SAME code contact_quality already uses, exposed under a "
                    "second, token-matchable name; see ingredients_batted_ball.py).",
    "entity": "batter",
    "ingredients": ["barrel_rate", "n_batted_balls"],
    "formula": "mean(launch_speed_angle == 6)",
    "status": "DESCRIPTIVE", "floor": 50, "weight_ledger_family": "descriptive",
}
ATTRIBUTES["babip"] = {
    "description": "Batting average on balls in play: (H - HR) / (AB - K - HR + SF), "
                    "AB excludes walk/HBP/sac events (standard MLB at-bat definition).",
    "entity": "batter",
    "ingredients": ["n_h", "n_hr", "n_k", "n_sf", "n_ab"],
    "formula": "(n_h - n_hr) / (n_ab - n_k - n_hr + n_sf)",
    "status": "DESCRIPTIVE",
    "floor": 100,  # self-declared AB floor, no spec number given
    "weight_ledger_family": "descriptive",
}

ENTITIES = ("batter", "pitcher", "catcher", "fielder")
STATUSES = ("VALIDATED_MECHANISM", "VALIDATED_CLAIM", "DESCRIPTIVE")


def attributes_for(entity: str) -> list[str]:
    return [name for name, spec in ATTRIBUTES.items() if spec["entity"] == entity]
