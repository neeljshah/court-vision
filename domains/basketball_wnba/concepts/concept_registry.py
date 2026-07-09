"""Concept registry -- the WNBA "answer engine" composite definitions.

Same pattern as domains/basketball_nba/concepts/concept_registry.py (read
that module's docstring for the full WEIGHT DERIVATION explanation). A
scouting-style question ("who has the best versatility?") is answered by a
CONCEPT: a small, documented set of signals from domains/basketball_wnba/
profiles/attribute_registry.py's ATTRIBUTES (every `attribute` below is
verified to exist -- see test_answer_quality_wnba.py), combined with DERIVED
weights.

WEIGHT DERIVATION: identical formula to NBA (base_weight = STATUS_RANK *
n/(n+N0), N0=200 fixed -- WNBA's n columns don't span the pitch/BIP/PA-scale
denominator spread MLB/tennis do, so NBA's single global N0 is appropriate
here too, not a per-concept n0 like MLB/tennis).

ORIENTATION -- empirically audited 2026-07-09 across all 27 attributes
actually used across the registry on data/cache/profiles/
wnba_player_profiles.parquet: corr(raw_value, percentile) is POSITIVE
(+0.82 to +0.997) for EVERY attribute, confirming build_profiles._percentile_
and_rating() is a PLAIN rank of raw_value (no per-attribute higher_is_better
flag exists in this domain's schema -- unlike soccer's builder-side flip, see
that module's docstring). Direction below is decided purely by whether each
attribute's OWN formula already encodes "higher raw = good" -- true for
every signal used in the 3 built concepts (verified individually against
attribute_registry.py's `formula` field), so NO lower_is_better signal is
needed anywhere in this registry (same conclusion as tennis, different
reason: tennis had no naturally-inverted metric among its chosen signals,
WNBA's def_rim_*_delta columns are pre-SIGNED correctly at the formula level
-- off_value minus on_value -- so raw-high already means "tighter defense").

ROLE SCOPING -- none needed for the 3 built concepts: WNBA ships separate
wnba_player_profiles.parquet (kind="player") and wnba_lineup_profiles.parquet
(kind="lineup") files; every signal used below is entity="player", so no
lineup rows ever enter a player-grain composite.

DATA-COVERAGE LANDMINE (the reason rim_protection is SKIPPED, read before
re-attempting it): def_rim_efg_allowed_delta and def_rim_share_allowed_delta
structurally look like a 2-signal rim_protection concept (same shape as
NBA's). Empirically verified 2026-07-09: their source (data/cache/team_
system/lineups/zone_onoff_wnba_2026.parquet) covers only 50 of the 213
players in the season_2026 window -- a 4x narrower population than the plain
on_off_wnba_2026.parquet source (105 players) gravity/on_court_impact draw
from. Checked every recognizable starting big/wing against this attribute:
A'ja Wilson, Brittney Griner, Jonquel Jones, Aliyah Boston, Ezi Magbegor,
Breanna Stewart, and Alyssa Thomas ALL have zero rows (not below-floor, just
absent from the source file). The resulting top-5 (Luisa Geiselsoder, Kaila
Charles, Jovana Nogic, Kaitlyn Chen, Saniya Rivers) are role players, not
plausible elite rim protectors -- this fails the task's own explicit sanity
bar ("plausible elite bigs, A'ja Wilson-class") by construction, not from a
tunable floor. SKIPPED rather than shipped broken; the underlying zone_onoff
coverage gap is a data-pipeline issue, out of scope for this registry.

OTHER SKIPPED CONCEPTS (documented, not silently dropped):
  - motor / rebounding: WNBA has only ONE combined reb_per36 column (no
    oreb_pct/dreb_pct split like NBA, no team_dreb_pct_swing or stint_
    minutes_load equivalent) -- one column is a disguised single-signal
    concept. SKIPPED.
  - creation / playmaking: WNBA has no eFG-lift-for-assisted-teammates
    attribute (NBA's 'creation') and no usage_absorption equivalent.
    ast_per36 (raw assist volume) and assisted_share (how much of THIS
    player's own makes were assisted -- a self-creation-adjacent signal
    pointing the OPPOSITE semantic direction) are the only playmaking-
    adjacent columns on disk and do not confirm one shared concept.
    SKIPPED.
  - clutch: no clutch-window attribute exists anywhere in the 31-attribute
    registry (no clutch_efg/clutch_ft_rate/clutch_fga equivalents).
    SKIPPED -- zero signals available, not an insufficient count.

Each concept entry: same shape as NBA (name, description, entity,
signals[{attribute, direction, weight_basis}], context_qualifiers,
failure_modes, min_n). min_n applies to the PRIMARY (first-listed) signal's
own n and is set from the live parquet's qualified-population n distribution
-- ~40th percentile of the primary signal's n, audited 2026-07-09, at or
above the attribute's own build floor.
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
# shrinkage midpoint: weight *= n/(n+N0) -- same fixed-N0 rationale as NBA's
# registry (WNBA's on/off and zone-attempt denominators don't span the
# pitch/BIP/PA-scale spread that justified MLB/tennis's per-concept n0).
N0 = 200.0

CONCEPTS: dict[str, dict[str, Any]] = {
    "gravity": {
        "name": "gravity",
        "description": (
            "How much this player's mere presence lifts teammate shooting "
            "efficiency and overall team performance -- the defense has to "
            "account for her even off the ball."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "gravity", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: teammate eFG% lift on-court minus "
                    "off-court -- same mechanism/formula as domains.basketball_"
                    "nba's gravity concept, mirrored here. VALIDATED_CLAIM (re-"
                    "verified against the claims store, see attribute_registry.py)."
                ),
            },
            {
                "attribute": "on_court_impact", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: team net rating on-court minus off-court, from "
                    "the SAME on_off_wnba_2026.parquet source -- corroborates "
                    "that a player's presence has real team-level impact, not "
                    "just a teammate-shooting artifact."
                ),
            },
        ],
        "context_qualifiers": [
            "Both signals share the same on/off source file and the same "
            "lineup-context confound as NBA's gravity concept -- on/off splits "
            "are not a causal isolate of one player alone.",
            "2026 season only (168 games) -- WNBA's on/off minutes floors (200 "
            "teammate-FGA for gravity, 300 minutes for on_court_impact) are "
            "necessarily much smaller in absolute terms than NBA's 196-game "
            "full-PBP subset; treat this as more sample-limited than the NBA "
            "equivalent.",
        ],
        "failure_modes": [
            "Empirically verified 2026-07-09: gravity's raw single-signal top-5 "
            "(Flau'jae Johnson, Ariel Atkins, Natisha Hiedeman, Noemie Brochant, "
            "Olivia Nelson-Ododa) skews toward role players, NOT recognizable "
            "star bigs/wings -- known stars sit mid-pack (A'ja Wilson 68th pct, "
            "Breanna Stewart 47th pct, Caitlin Clark 71st pct). This mirrors "
            "NBA's own documented gravity failure mode ('dominated by noisy "
            "role-player outliers' near the floor) -- read this concept as a "
            "real but noisy measured swing, not a proxy for star status.",
            "on_court_impact rewards overall team performance while a player is "
            "on-court, which is confounded by which four teammates share the "
            "floor with her -- same lineup-context caveat as the primary signal.",
            "min_n floor rationale: gravity n counts min(teammate_fga_on, "
            "teammate_fga_off); 410 ~= the 40th percentile (q40=411.2, audited "
            "2026-07-09) of the 104 qualified players -- well above the "
            "attribute's own build floor (200).",
        ],
        "min_n": 410.0,
    },
    "spacing": {
        "name": "spacing",
        "description": (
            "How much this player stretches the floor: the volume and "
            "efficiency of the three-point attempts that create spacing, split "
            "by above-the-break and corner zones."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "zone_above_break_3_share", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: share of this player's total FGA "
                    "taken from above-the-break three -- the dominant floor-"
                    "stretching shot type by volume."
                ),
            },
            {
                "attribute": "zone_corner3_share", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: share of attempts from the corner three, the "
                    "more efficient but lower-volume floor-stretching zone -- "
                    "confirms the spacing read isn't purely above-the-break "
                    "volume."
                ),
            },
            {
                "attribute": "zone_above_break_3_efg", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary: efficiency on above-the-break attempts -- volume "
                    "alone is not a real spacing threat unless it is respected/"
                    "made at a real rate."
                ),
            },
            {
                "attribute": "zone_corner3_efg", "direction": "higher_is_better",
                "weight_basis": (
                    "Smallest weight: corner-three efficiency, pairing with the "
                    "corner volume signal the same way the above-the-break pair "
                    "does."
                ),
            },
        ],
        "context_qualifiers": [
            "Unlike NBA's spacing concept, WNBA has NO player-level lineup-"
            "spacing-contribution attribute -- WNBA's own 'spacing' attribute "
            "is LINEUP-grain only (a different entity space, see attribute_"
            "registry.py). This concept is a pure three-point volume/efficiency "
            "proxy, not a causal lineup-membership measure like NBA's spacing_"
            "contribution.",
            "This measures shot-selection + efficiency in the two three-point "
            "zones specifically, not attempt-volume breadth across all zones "
            "(see versatility for that read).",
        ],
        "failure_modes": [
            "corner3 signals have a much thinner qualified population (24 "
            "entities vs 105 for above-the-break) -- entities without a "
            "qualifying corner3 sample are still scored, just on the remaining "
            "signals (normalized weight redistributes).",
            "A player who simply never gets corner-three looks in her team's "
            "offense (system-dependent, not skill-dependent) is not penalized "
            "directly, only diluted to fewer signals.",
            "min_n floor rationale: zone_above_break_3_share n counts THREE-"
            "ZONE FGA; 38 ~= the 40th percentile (q40=38.6, audited 2026-07-09) "
            "of the qualified 105-player population -- close to the attribute's "
            "own build floor (20 attempts) given the shorter 168-game season.",
        ],
        "min_n": 38.0,
    },
    "versatility": {
        "name": "versatility",
        "description": (
            "How efficiently this player scores across every shot zone -- rim, "
            "paint, mid-range, corner three, above-the-break three -- rather "
            "than living off one shot type."
        ),
        "entity": "player",
        "signals": [
            {"attribute": "zone_rim_efg", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
            {"attribute": "zone_paint_efg", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
            {"attribute": "zone_mid_efg", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
            {"attribute": "zone_corner3_efg", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
            {"attribute": "zone_above_break_3_efg", "direction": "higher_is_better",
             "weight_basis": "Equal-weight ingredient by design: one of five zones this concept averages efficiency across, no zone privileged."},
        ],
        "context_qualifiers": [
            "This measures EFFICIENCY breadth, not attempt-volume breadth -- a "
            "player who only ever shoots at the rim but shoots it at 65% still "
            "needs attempts in the other four zones (each has its own 20-"
            "attempt floor) to even appear here.",
            "Equal status/weight across zones is a deliberate design choice (no "
            "zone is scheme-privileged a priori), not a derived result -- same "
            "precedent as NBA's versatility concept.",
        ],
        "failure_modes": [
            "A team's offensive scheme can simply not generate certain zone "
            "looks for a player regardless of her actual skill there "
            "(deprioritized by coaching, not by ability).",
            "Small per-zone attempt counts near the 20-FGA floor are noisy eFG "
            "reads, especially for the thinner zones (corner3: 24 qualified "
            "players, mid: 44) vs the deeper ones (rim: 123, above_break_3: 105).",
            "Empirically verified 2026-07-09: the primary zone_rim_efg signal's "
            "own top-5 (Kelsey Plum, Paige Bueckers, A'ja Wilson, Chennedy "
            "Carter, NaLyssa Smith) are recognizable, plausible efficient "
            "scorers -- unlike the gravity concept's noisier top-5, this "
            "concept's primary signal clears the sanity bar directly.",
            "min_n floor rationale: zone_rim_efg n counts RIM FGA; 39 ~= the "
            "40th percentile (q40=39.0, audited 2026-07-09) of the qualified "
            "123-player population -- just above the attribute's own build "
            "floor (20 attempts).",
        ],
        "min_n": 39.0,
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
    the lexically-latest window (mirrors NBA/MLB's convention -- every signal
    used here lives on the single 'season_2026' window, so no tennis-style
    year-extraction is needed)."""
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
    Identical formula to domains/basketball_nba/concepts/concept_registry.py's
    derive_weights -- duplicated here (not imported cross-domain) so each sport
    adapter stays self-contained. See that module for the full docstring."""
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
