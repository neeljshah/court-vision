"""domains.mlb.profiles.ingredients_batter -- one builder function per BATTER
attribute in attribute_registry.ATTRIBUTES. Each takes the season's savant
pitch-level frame(s) and returns a tidy per-batter frame with columns
`entity_id`, `raw_value`, `n` (floor denominator -- min(cell_n) for a
2-cell split, matching nba_player_interaction_claims.py's precedent), and
`ingredients` (dict of named scalars, json.dumps'd by build_profiles.py).

Zero reimplementation: platoon_same_hand / is_breaking reused from
domains.mlb.prereg.mlb_hypotheses; is_risp/two_outs/is_groundball reused
from domains.mlb.prereg.mlb_savant_2024 (the exact ingredients the
REPLICATED base-out x contact and platoon x pitch-type mechanisms were
tested on). pull_tendency reuses prereg_shift_unblocked's spray formula.

LANDMINE (flagged in the brief): a groupby().agg() on an empty slice can
silently produce 0.0 via nansum -- every builder below groups on real
integer 0/1 indicator columns via .sum()/.size() (never nansum over a
reindexed/all-NaN slice), so an entity with zero rows in a cell is simply
ABSENT from that groupby, not a fabricated 0.0 (build_profiles.py's outer
merge naturally leaves it NaN, which the floor then excludes).
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.prereg.mlb_hypotheses import _NEG_EVENTS, _POS_EVENTS
from domains.mlb.prereg_shift_unblocked import classify_pulled, spray_angle_deg

_K_EVENTS = {"strikeout", "strikeout_double_play"}
_BB_EVENTS = {"walk", "intent_walk"}
_SWING_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"}


def _two_cell(df: pd.DataFrame, group_col: str, value_col: str, cell_a, cell_b,
              name_a: str, n_name_a: str, name_b: str, n_name_b: str) -> pd.DataFrame:
    """Shared shape: per-entity rate in cell_a minus rate in cell_b, n=min(n_a, n_b).
    Column names for both the rate and its n are caller-supplied explicitly (no
    string-splitting inference) so they land exactly matching each attribute's
    declared `ingredients` keys in attribute_registry.py."""
    g = df.groupby(["entity_id", group_col])[value_col].agg(rate="mean", n="size").reset_index()
    wide = g.pivot(index="entity_id", columns=group_col, values=["rate", "n"])
    out = pd.DataFrame(index=wide.index)
    out[name_a] = wide[("rate", cell_a)]
    out[n_name_a] = wide[("n", cell_a)]
    out[name_b] = wide[("rate", cell_b)]
    out[n_name_b] = wide[("n", cell_b)]
    return out.dropna(subset=[name_a, name_b]).reset_index()


def build_platoon_resilience(pitches: pd.DataFrame) -> pd.DataFrame:
    term = pitches[pitches["events"].notna()].copy()
    term = term[term["events"].isin(_POS_EVENTS | _NEG_EVENTS)]
    term["reaches_base"] = term["events"].isin(_POS_EVENTS).astype(int)
    term["entity_id"] = term["batter"]
    term["hand_cell"] = (term["p_throws"] == term["stand"]).map({True: "same", False: "opp"})
    wide = _two_cell(term, "hand_cell", "reaches_base", "same", "opp",
                      "reaches_base_same_hand", "n_same_hand", "reaches_base_opp_hand", "n_opp_hand")
    wide["raw_value"] = wide["reaches_base_same_hand"] - wide["reaches_base_opp_hand"]
    wide["n"] = wide[["n_same_hand", "n_opp_hand"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "reaches_base_same_hand": round(float(r.reaches_base_same_hand), 4), "n_same_hand": int(r.n_same_hand),
        "reaches_base_opp_hand": round(float(r.reaches_base_opp_hand), 4), "n_opp_hand": int(r.n_opp_hand),
    }, axis=1)
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


def build_pull_tendency(hitcoords: pd.DataFrame) -> pd.DataFrame:
    bip = hitcoords.dropna(subset=["hc_x", "hc_y", "stand"]).copy()
    bip["is_pull"] = classify_pulled(spray_angle_deg(bip["hc_x"], bip["hc_y"]), bip["stand"]).astype(int)
    g = bip.groupby("batter")["is_pull"].agg(pull_share="mean", n="size").reset_index()
    g = g.rename(columns={"batter": "entity_id"})
    g["raw_value"] = g["pull_share"]
    g["ingredients"] = g.apply(lambda r: {
        "pull_share": round(float(r.pull_share), 4), "n_batted_balls": int(r.n)}, axis=1)
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_contact_quality(hitcoords: pd.DataFrame) -> pd.DataFrame:
    bip = hitcoords.dropna(subset=["launch_speed_angle"]).copy()
    bip["is_barrel"] = (bip["launch_speed_angle"] == 6).astype(int)
    g = bip.groupby("batter")["is_barrel"].agg(barrel_share="mean", n="size").reset_index()
    g = g.rename(columns={"batter": "entity_id"})
    g["raw_value"] = g["barrel_share"]
    g["ingredients"] = g.apply(lambda r: {
        "barrel_share": round(float(r.barrel_share), 4), "n_batted_balls": int(r.n)}, axis=1)
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_discipline_by_count(pitches: pd.DataFrame) -> pd.DataFrame:
    p = pitches.copy()
    p["entity_id"] = p["batter"]
    p["is_swing"] = p["description"].isin(_SWING_DESCRIPTIONS).astype(int)
    p["leverage_cell"] = (p["strikes"] > p["balls"]).map({True: "ahead", False: "behind"})
    wide = _two_cell(p, "leverage_cell", "is_swing", "behind", "ahead",
                      "swing_rate_behind", "n_behind", "swing_rate_ahead", "n_ahead")
    wide["raw_value"] = wide["swing_rate_behind"] - wide["swing_rate_ahead"]
    wide["n"] = wide[["n_behind", "n_ahead"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "swing_rate_behind": round(float(r.swing_rate_behind), 4), "n_behind": int(r.n_behind),
        "swing_rate_ahead": round(float(r.swing_rate_ahead), 4), "n_ahead": int(r.n_ahead),
    }, axis=1)
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


def build_clutch_baseout(pitches: pd.DataFrame) -> pd.DataFrame:
    bip = pitches[(pitches["type"] == "X") & pitches["bb_type"].notna()
                  & (pitches["bb_type"] != "None")].copy()
    bip["entity_id"] = bip["batter"]
    bip["is_groundball"] = (bip["bb_type"] == "ground_ball").astype(int)
    bip["risp_cell"] = (bip["on_2b"].notna() | bip["on_3b"].notna()).map({True: "risp", False: "no_risp"})
    wide = _two_cell(bip, "risp_cell", "is_groundball", "risp", "no_risp",
                      "gb_rate_risp", "n_risp", "gb_rate_no_risp", "n_no_risp")
    wide["raw_value"] = wide["gb_rate_risp"] - wide["gb_rate_no_risp"]
    wide["n"] = wide[["n_risp", "n_no_risp"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "gb_rate_risp": round(float(r.gb_rate_risp), 4), "n_risp": int(r.n_risp),
        "gb_rate_no_risp": round(float(r.gb_rate_no_risp), 4), "n_no_risp": int(r.n_no_risp),
    }, axis=1)
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


def build_K_avoidance(pitches: pd.DataFrame) -> pd.DataFrame:
    term = pitches[pitches["events"].notna()].copy()
    term["is_k"] = term["events"].isin(_K_EVENTS).astype(int)
    g = term.groupby("batter")["is_k"].agg(k_rate="mean", n="size").reset_index()
    g = g.rename(columns={"batter": "entity_id"})
    g["raw_value"] = 1.0 - g["k_rate"]
    g["ingredients"] = g.apply(lambda r: {
        "k_rate": round(float(r.k_rate), 4), "n_pa": int(r.n)}, axis=1)
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_BB_rate(pitches: pd.DataFrame) -> pd.DataFrame:
    term = pitches[pitches["events"].notna()].copy()
    term["is_bb"] = term["events"].isin(_BB_EVENTS).astype(int)
    g = term.groupby("batter")["is_bb"].agg(bb_rate="mean", n="size").reset_index()
    g = g.rename(columns={"batter": "entity_id"})
    g["raw_value"] = g["bb_rate"]
    g["ingredients"] = g.apply(lambda r: {
        "bb_rate": round(float(r.bb_rate), 4), "n_pa": int(r.n)}, axis=1)
    return g[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {
    "platoon_resilience": build_platoon_resilience,
    "pull_tendency": build_pull_tendency,
    "contact_quality": build_contact_quality,
    "discipline_by_count": build_discipline_by_count,
    "clutch_baseout": build_clutch_baseout,
    "K_avoidance": build_K_avoidance,
    "BB_rate": build_BB_rate,
}
