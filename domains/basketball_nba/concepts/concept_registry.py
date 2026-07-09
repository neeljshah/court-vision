"""Concept registry -- the NBA "answer engine" composite definitions.

A scouting-style question ("who has the best gravity?") is NEVER answered by
ranking one raw attribute column. It is answered by a CONCEPT: a small,
documented set of signals from domains/basketball_nba/profiles/attribute_
registry.py (every `attribute` below is verified to exist in ATTRIBUTES --
see test_concept_registry.py), combined with DERIVED weights.

WEIGHT DERIVATION (not hand-tuned):
    base_weight = STATUS_RANK[row.status] * (row.n / (row.n + N0))
    norm_weight = base_weight / sum(base_weight over the concept's signals
                  actually present for that entity+window)
STATUS_RANK favors VALIDATED_MECHANISM > VALIDATED_CLAIM > DESCRIPTIVE >
PROVISIONAL (the same status ladder attribute_registry.py already declares).
The n-shrinkage (n/(n+N0)) down-weights thin samples without hard-excluding
them -- min_n below is the hard exclusion floor instead.

derive_weights() is the ONE place this formula lives; scripts/platformkit/
answers/contracts.py imports it rather than re-deriving weights per question
type, so every answer shape (superlative/comparison/explanation/fit) is
scored identically.

Each concept entry:
    name, description            -- what the concept means, in scouting prose
    signals: [{attribute, direction, weight_basis}]
        attribute      -- must be a key in attribute_registry.ATTRIBUTES
        direction       -- how to consume the parquet's `percentile` column.
                           The profile builders ALREADY orientation-normalize
                           percentiles wherever the attribute has a natural
                           better direction (verified empirically 2026-07-09:
                           corr(raw,pct) ~ -0.95 for zone_def_*_allowed_* --
                           lower eFG allowed = HIGHER percentile), so nearly
                           every signal is "higher_is_better" = consume as-is.
                           "lower_is_better" (contribution = 100-percentile)
                           is ONLY for an attribute whose percentile tracks
                           the raw value (builder saw no natural direction)
                           while the CONCEPT reads low-raw as good. Currently
                           exactly one: zone_assisted_share_rim
                           (corr(raw,pct) = +0.99; creation wants low).
        weight_basis    -- WHY this signal is included (prose, not a number
                           -- the number is derived, the rationale is not)
    context_qualifiers  -- when this composite should be read cautiously
    failure_modes       -- known specific ways the composite can mislead
    min_n               -- hard floor on the PRIMARY (first-listed) signal's
                           own `n` column; entities below it are excluded
                           before ranking, not zero-filled. Set to (or above)
                           that signal's own registry floor -- see
                           attribute_registry.py's floor dicts.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

STATUS_RANK: dict[str, int] = {
    "VALIDATED_MECHANISM": 4,
    "VALIDATED_CLAIM": 3,
    "DESCRIPTIVE": 2,
    "PROVISIONAL": 1,
}
# shrinkage midpoint: weight *= n/(n+N0) -- ponytail: one fixed constant for
# every concept/signal; revisit per-signal if a concept's real n distribution
# turns out wildly different from ~200 (e.g. clutch signals sit near n=30-60).
N0 = 200.0

CONCEPTS: dict[str, dict[str, Any]] = {
    "gravity": {
        "name": "gravity",
        "description": (
            "How much this player's mere presence lifts teammate shooting "
            "efficiency -- the defense has to account for him even off the ball."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "gravity", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: VALIDATED_CLAIM re-presentation of "
                    "the gravity_proxy claim family (teammate eFG on minus off court)."
                ),
            },
            {
                "attribute": "spacing_contribution", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: gravity's on-court mechanism should also widen actual "
                    "shot spacing for the lineup he is in; DESCRIPTIVE, not gate-tested."
                ),
            },
        ],
        "context_qualifiers": [
            "On/off splits are confounded by lineup context (who else is on/off "
            "with him), not a causal isolate of this player alone.",
            "Thin population: the lineup keystone this depends on covers only the "
            "196-game full-PBP subset (see docs/analytics/nba.md).",
        ],
        "failure_modes": [
            "A player who sits mostly during garbage time or blowouts can show an "
            "inflated on/off swing unrelated to defensive attention.",
            "Ball-dominant, low-gravity scorers can still post a positive swing "
            "purely from teammates getting more open reps while he creates.",
            "Empirically, raw gravity percentile near the attribute's own 300-min "
            "floor is dominated by noisy role-player outliers (verified against "
            "the live parquet, e.g. sub-400-minute players topping the bare "
            "column) -- min_n below is deliberately raised well past that floor.",
        ],
        "min_n": 1000.0,
    },
    "rim_protection": {
        "name": "rim_protection",
        "description": (
            "How much this player deters and suppresses opponent shot quality at "
            "the rim while he's on the floor."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "rim_pressure_def", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary: composite on/off swing in opponent rim-attempt-share "
                    "allowed, rim eFG allowed, and points-against/48, already "
                    "z-scored so higher = more deterrence."
                ),
            },
            {
                "attribute": "zone_def_rim_efg_allowed_on", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary raw context: the on-court rim eFG allowed level itself "
                    "(not just its swing), so a low-volume/high-swing outlier is "
                    "checked against the absolute number. Percentile is pre-oriented "
                    "by the builder (lower eFG allowed = higher pct; corr(raw,pct) "
                    "= -0.95) -- consume as-is, do NOT re-invert."
                ),
            },
            {
                "attribute": "zone_def_rim_share_allowed_on", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary raw context: how often opponents even get to the rim "
                    "with this player on-court -- shot-selection deterrence, not just "
                    "finishing deterrence. Percentile pre-oriented (corr = -0.97) -- "
                    "consume as-is, do NOT re-invert."
                ),
            },
            {
                "attribute": "dreb_pct", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight by construction (DESCRIPTIVE, opportunity "
                    "proxy): controlling the rim includes cleaning up the resulting miss."
                ),
            },
        ],
        "context_qualifiers": [
            "All signals here are DESCRIPTIVE -- none has passed a leak-free "
            "predictive gate yet; this ranks rim deterrence as measured, not as "
            "a proven signal of winning games.",
            "Team scheme (help/rotation rules) inflates or deflates an individual's "
            "on/off swing independent of his own rim defense.",
        ],
        "failure_modes": [
            "A helpside-only rim protector can look elite here while poor at "
            "closing out to shooters -- this concept does not measure that tradeoff.",
            "Small on/off sample bigs (near the 750-min floor) can show noisy swings.",
        ],
        "min_n": 750.0,
    },
    "creation": {
        "name": "creation",
        "description": (
            "How much of this player's own scoring he generates unassisted, plus "
            "his direct efficiency lift for teammates he assists."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "creation", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: eFG lift for teammates this player "
                    "assists, averaged across every scorer he feeds."
                ),
            },
            {
                "attribute": "usage_absorption", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: shot-share this player absorbs when a high-usage "
                    "teammate sits -- self-creation capacity, a different flavor of "
                    "'creation' than the primary assist-lift signal."
                ),
            },
            {
                "attribute": "zone_assisted_share_rim", "direction": "lower_is_better",
                "weight_basis": (
                    "Small-weight proxy: a LOW share of this player's own rim makes "
                    "being assisted implies he is getting there off his own dribble "
                    "rather than a feed -- a self-creation tell, not a direct measure."
                ),
            },
        ],
        "context_qualifiers": [
            "creation and usage_absorption are both DESCRIPTIVE; no gate has tested "
            "whether either predicts winning.",
            "zone_assisted_share_rim direction is context-specific to THIS concept -- "
            "its percentile tracks the raw value (corr = +0.99, the builder saw no "
            "natural direction) and only the self-creation read inverts it here; it "
            "is the ONLY lower_is_better signal in the whole registry.",
        ],
        "failure_modes": [
            "assist-network eFG lift conflates shot-selection/play-type effects with "
            "actual playmaking skill (e.g. easy dump-offs to a rim-runner).",
            "usage_absorption is undefined (excluded) for players with no shared "
            "minutes alongside a qualifying high-usage teammate.",
        ],
        "min_n": 20.0,
    },
    "playmaking": {
        "name": "playmaking",
        "description": (
            "How much this player elevates TEAMMATES' offense -- distinct from "
            "creation's self-creation lean, this weights the teammate-facing side."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "creation", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary: the same eFG-lift-for-assisted-teammates measure as "
                    "'creation', re-used here as the only teammate-uplift-shaped "
                    "signal on disk -- documented redundancy, not a hidden re-derivation."
                ),
            },
            {
                "attribute": "usage_absorption", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: redistributing shot creation to teammates when a "
                    "high-usage co-star sits is an organizational-playmaking-adjacent "
                    "role, weighted lower than the direct assist-lift signal."
                ),
            },
        ],
        "context_qualifiers": [
            "playmaking and creation currently draw on the same primary attribute "
            "(no per-player passing-volume/potential-assist table exists on disk); "
            "treat them as overlapping views, not independent confirmations.",
        ],
        "failure_modes": [
            "Cannot distinguish high-volume, low-difficulty passing from genuinely "
            "difficult live-dribble reads -- both show up the same way in eFG lift.",
        ],
        "min_n": 20.0,
    },
    "clutch": {
        "name": "clutch",
        "description": (
            "How this player performs in clutch time (Q4/OT, <=5min, <=10pt margin): "
            "efficiency, foul-drawing, and willingness to take the shot."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "clutch_efg", "direction": "higher_is_better",
                "weight_basis": "Primary: eFG% in the clutch window, the direct efficiency read.",
            },
            {
                "attribute": "clutch_ft_rate", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: drawing fouls under pressure is a real clutch skill "
                    "independent of made-shot efficiency."
                ),
            },
            {
                "attribute": "clutch_fga_per_game", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight: a volume/willingness proxy ('wants the "
                    "ball') -- not itself a quality signal, kept low-weight by the "
                    "n-shrinkage since clutch_fga floors around n=30 games."
                ),
            },
        ],
        "context_qualifiers": [
            "Clutch windows are small-sample by construction (single-quarter-scale "
            "possessions per season); read this as descriptive, not a stable trait.",
        ],
        "failure_modes": [
            "One hot or cold stretch of clutch games can dominate a season's "
            "clutch_efg given the low attempt counts.",
            "clutch_fga_per_game rewards shot volume regardless of shot quality.",
        ],
        "min_n": 30.0,
    },
    "motor": {
        "name": "motor",
        "description": (
            "Hustle/effort proxy: rebounding rate on both ends, defensive-rebound "
            "impact beyond his own box score, and total on-court workload."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "oreb_pct", "direction": "higher_is_better",
                "weight_basis": "Primary: offensive rebounding is the clearest single hustle proxy on disk.",
            },
            {
                "attribute": "dreb_pct", "direction": "higher_is_better",
                "weight_basis": "Primary co-signal: defensive rebounding, same hustle read on the other end.",
            },
            {
                "attribute": "team_dreb_pct_swing", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: this player's on/off swing in his TEAM's defensive-"
                    "rebound rate -- a boxout-adjacent impact his own DREB total misses."
                ),
            },
            {
                "attribute": "stint_minutes_load", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight: total on-court workload as a durability/"
                    "motor proxy -- volume, not quality, so kept low-weight."
                ),
            },
        ],
        "context_qualifiers": [
            "Box-derived rebounding rates reward opportunity (missed-shot volume "
            "while on-court) as much as true effort/positioning.",
        ],
        "failure_modes": [
            "A player on a bad defensive team can show inflated DREB opportunity "
            "(more opponent misses to rebound) without playing harder.",
            "team_dreb_pct_swing is DESCRIPTIVE and not itself gate-tested; it is "
            "the player-level expression of a mechanism that IS validated at team "
            "grain (lineup_continuity_avg_stint_s), not a validated player claim.",
        ],
        "min_n": 200.0,
    },
    "spacing": {
        "name": "spacing",
        "description": (
            "How much this player stretches the floor: his lineup-spacing impact "
            "plus the volume and efficiency of the threes that create it."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "spacing_contribution", "direction": "higher_is_better",
                "weight_basis": "Primary and definitional: mean lineup shot-spacing with him in minus lineups he is not in.",
            },
            {
                "attribute": "shot_zone_three_rate_per36", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: three-point volume is the raw material of gravity-"
                    "creating spacing threat."
                ),
            },
            {
                "attribute": "shot_zone_three_efg", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: volume alone is not a threat unless it is efficient "
                    "-- pairs with the rate signal so pure high-volume/low-accuracy "
                    "chuckers do not rank as elite spacers."
                ),
            },
        ],
        "context_qualifiers": [
            "spacing_contribution's membership computation is not independently "
            "re-derivable from a bare column (verifiable_by_design=False in the "
            "attribute registry) -- treat it as sourced, not re-audited here.",
        ],
        "failure_modes": [
            "A player who takes few but very efficient threes can under-rank versus "
            "a high-volume merely-average shooter on the rate signal alone.",
        ],
        "min_n": 200.0,
    },
    "versatility": {
        "name": "versatility",
        "description": (
            "How efficiently this player scores across every shot zone -- rim, "
            "paint, mid-range, corner three, above-the-break three -- rather than "
            "living off one shot type."
        ),
        "entity": "player",
        "signals": [
            {"attribute": "zone_efg_rim", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
            {"attribute": "zone_efg_paint", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
            {"attribute": "zone_efg_mid", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
            {"attribute": "zone_efg_corner3", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
            {"attribute": "zone_efg_above_break_3", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
        ],
        "context_qualifiers": [
            "This measures EFFICIENCY breadth, not attempt-volume breadth -- a "
            "player who only ever shoots corner threes but shoots them at 45% "
            "still needs attempts in the other four zones (each has its own "
            "25-attempt floor) to even appear here.",
            "Equal status/weight across zones is a deliberate design choice (no "
            "zone is scheme-privileged a priori), not a derived result.",
        ],
        "failure_modes": [
            "A team's offensive scheme can simply not generate certain zone looks "
            "for a player regardless of his actual skill there (deprioritized by "
            "coaching, not by ability).",
            "Small per-zone attempt counts near the 25-FGA floor are noisy eFG reads.",
        ],
        "min_n": 25.0,
    },
}


def get_concept(name: str) -> dict[str, Any]:
    c = CONCEPTS.get(name)
    if c is None:
        raise KeyError(f"unknown concept '{name}'. Available: {sorted(CONCEPTS)}")
    return c


def list_concepts() -> list[str]:
    return sorted(CONCEPTS)


def _latest_rows(df: pd.DataFrame, window: str | None) -> pd.DataFrame:
    """One row per (entity_id, attribute): the given window if present, else
    the lexically-latest window (mirrors ask.py's _pick_row convention)."""
    if window:
        w = df[df["window"] == window]
        if not w.empty:
            df = w
    return (
        df.sort_values("window")
        .groupby(["entity_id", "attribute"], as_index=False)
        .tail(1)
    )


def derive_weights(concept: dict[str, Any], profiles_df: pd.DataFrame,
                    window: str | None = None) -> pd.DataFrame:
    """Status-rank x n-shrinkage weights, normalized per entity, for one concept.

    Returns one row per (entity, signal actually present), columns:
        entity_id, entity_name, attribute, direction, window, raw_value,
        percentile, n, status, base_weight, norm_weight
    norm_weight sums to 1.0 within each entity_id across its present signals
    (entities missing every signal are simply absent from the output; entities
    missing SOME signals are still scored, normalized over what they have).
    """
    signals = concept["signals"]
    attrs = [s["attribute"] for s in signals]
    dirs = {s["attribute"]: s.get("direction", "higher_is_better") for s in signals}

    cols = ["entity_id", "entity_name", "window", "attribute", "raw_value",
            "percentile", "n", "status"]
    sub = profiles_df.loc[profiles_df["attribute"].isin(attrs), cols].copy()
    if sub.empty:
        return sub.assign(direction=pd.Series(dtype=object),
                           base_weight=pd.Series(dtype=float),
                           norm_weight=pd.Series(dtype=float))

    sub = _latest_rows(sub, window)
    sub["direction"] = sub["attribute"].map(dirs)
    status_rank = sub["status"].map(STATUS_RANK).fillna(1)
    sub["base_weight"] = status_rank * (sub["n"] / (sub["n"] + N0))

    totals = sub.groupby("entity_id")["base_weight"].transform("sum")
    sub["norm_weight"] = (sub["base_weight"] / totals.where(totals > 0, 1.0)).fillna(0.0)
    return sub.reset_index(drop=True)
