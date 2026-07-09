"""Concept registry -- the tennis "answer engine" composite definitions.

Same pattern as domains/basketball_nba/concepts/concept_registry.py (read
that module's docstring for the full WEIGHT DERIVATION explanation,
reproduced below only where it differs for tennis). A scouting-style
question ("who has the best serve weapon?") is answered by a CONCEPT: a
small, documented set of signals from domains/tennis/profiles/
attribute_registry.py (every `attribute` below is verified to exist in
ATTRIBUTES -- see test_answer_quality_tennis.py), combined with DERIVED
weights.

WEIGHT DERIVATION (same shape as NBA/MLB, not hand-tuned):
    base_weight = STATUS_RANK[row.status] * (row.n / (row.n + n0))
    norm_weight = base_weight / sum(base_weight over the concept's signals
                  actually present for that entity+window)
where n0 = the concept's own min_n (same rationale as MLB: tennis n columns
span wildly different denominators -- charting POINTS (~1000s), matches
(~10s-100s), break points/game points faced (~100s-1000s) -- one global
shrinkage midpoint would be miscalibrated across concepts).

ORIENTATION -- empirically audited 2026-07-09, corr(raw_value, percentile)
across all 72 tennis attributes on data/cache/profiles/
tennis_player_profiles.parquet: POSITIVE (+0.87 to +0.99) for EVERY
attribute with no exception found (same conclusion as MLB, unlike NBA's
pre-oriented zone_def_* columns). Percentile is always a plain rank of
raw_value; direction below is decided purely by concept semantics, never by
"the builder already inverted it for me". None of the signals used in these
4 concepts need a lower_is_better flag -- every one is a "raw-high genuinely
means good for this concept" read (serve win rates, return win rates, a
break-point-save delta, a recovery-hold delta). Verified: no chosen signal
is a rate whose raw-high reading would be bad (e.g. double-fault rate was
considered and deliberately excluded from every concept below for exactly
that reason -- it would need a lower_is_better flag and adds no signal not
already carried by the win-rate attributes).

WINDOW SELECTION -- tennis mixes THREE window-naming conventions in the same
parquet (verified 2026-07-09):
    1. bare 4-digit years ("1969".."2026") on charting-derived attributes
       (serve_dominance, return_strength, momentum_*, serve_by_set_*, etc),
       ALWAYS alongside one extra "career_to_2026" row for the same entity.
    2. "year_YYYY"-prefixed windows (2015-2025) on the window_<metric>
       attributes -- the registry's own PREDICTIONS-FACING per-year rows.
    3. single-window-only attributes: "career_to_2026" (pressure_serve,
       opp_tier_*, surface_splits_*) or "last10" (form_*) -- no year choice.
Per the task spec, concept queries default to the LATEST YEAR window, not
career: _latest_rows() below extracts a year from either bare or "year_"-
prefixed windows and keeps the max year per (entity_id, attribute); only
falls back to whatever single non-year window exists (career_to_2026 /
last10) when an attribute has no year-windowed rows at all. This means
"best return game" reflects CURRENT form, not career-peak reputation --
verified against Novak Djokovic: his return_strength career_to_2026 row
sits at the 66th percentile, but his latest available year (2025) sits at
only the 42nd -- the default deliberately surfaces the latter.

ROLE SCOPING -- none needed. Every tennis attribute's `entity` field in
attribute_registry.py is "player" (no pitcher/batter-style split); one
profiles parquet, one kind.

SKIPPED CONCEPT (documented, not silently dropped): tiebreak_nerve. The
only two tiebreak-specific attributes are tiebreak_points_won_share (both
serve+return roles) and tiebreak_serve_win_rate (the server-perspective
SUBSET of the same points) -- not independent confirmations of a skill,
same "disguised single column" trap MLB's framing_craft was skipped for.
No third tiebreak-specific signal exists in the 72-attribute registry.

Each concept entry: same shape as NBA/MLB (name, description, entity,
signals[{attribute, direction, weight_basis}], context_qualifiers,
failure_modes, min_n). min_n applies to the PRIMARY (first-listed) signal's
n and is set from the live parquet's qualified-population n distribution at
the DEFAULT (latest-year) window selection -- ~40th percentile of the
primary signal's n among entities that have it, audited 2026-07-09 -- same
"build floor makes a number computable, concept floor makes a leaderboard
trustworthy" rationale as MLB's d5fd8c6b fix, applied from the start here.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

STATUS_RANK: dict[str, int] = {
    "VALIDATED_MECHANISM": 4,
    "VALIDATED_CLAIM": 3,
    "DESCRIPTIVE": 2,
    "PROVISIONAL": 1,
}
# shrinkage midpoint fallback -- derive_weights uses the concept's own min_n
# as n0 (see module docstring); this constant only backstops a concept dict
# missing min_n (e.g. a synthetic test concept).
N0 = 200.0

CONCEPTS: dict[str, dict[str, Any]] = {
    "serve_weapon": {
        "name": "serve_weapon",
        "description": (
            "How much of a weapon this player's serve is -- overall hold-adjacent "
            "strength, raw ace-hitting power, first-serve point conversion, and "
            "whether the weapon survives the more vulnerable second delivery."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "serve_dominance", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: mean of charting service-point win "
                    "rate and the match-aggregate serve-strength ingredient -- the "
                    "broadest single 'how good is this serve' read on disk."
                ),
            },
            {
                "attribute": "match_agg_ace_rate_Overall", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: raw ace rate across all surfaces -- the classic "
                    "'weapon' proxy scouts lead with, independent of whether points "
                    "are ultimately won."
                ),
            },
            {
                "attribute": "match_agg_first_serve_win_Overall", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: first-serve point win rate -- direct conversion of "
                    "the weapon into won points, not just aces."
                ),
            },
            {
                "attribute": "second_serve_reliability", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight: second-serve point win rate -- does the "
                    "weapon hold up once the free first-serve swing is gone."
                ),
            },
        ],
        "context_qualifiers": [
            "All four signals are DESCRIPTIVE -- none has passed a leak-free "
            "predictive gate; this ranks raw serve strength as measured, not a "
            "proven signal of match outcomes.",
            "Percentiles are NOT builder-pre-oriented (verified: corr(raw,pct) "
            "+0.87 to +0.99 across all 72 tennis attributes) -- every signal here "
            "is higher_is_better because raw-high genuinely means a bigger serve.",
            "Window defaults to each entity's own latest available year, not "
            "career -- a player charted only in an early season will be scored on "
            "that season, not their career peak (see module docstring).",
        ],
        "failure_modes": [
            "Charting coverage is uneven across players and years: a legitimately "
            "huge server whose only charted year is thin (e.g. John Isner: single "
            "charted year 2018, n=1010) falls below the floor and is silently "
            "omitted rather than scored on a stale or fabricated number.",
            "match_agg_ace_rate_Overall and match_agg_first_serve_win_Overall both "
            "come from the same match_stats source and are not fully independent "
            "confirmations of serve quality.",
            "min_n floor rationale: serve_dominance n counts charting SERVICE "
            "POINTS; 1380 ~= the 40th percentile (q40=1376.6, audited 2026-07-09) "
            "of qualified players' n at their own latest-year window -- well above "
            "the attribute's own build floor (charting_svc_n=1000).",
        ],
        "min_n": 1380.0,
    },
    "return_game": {
        "name": "return_game",
        "description": (
            "How strong this player's return of serve is -- overall return "
            "point-win strength, aggregate return points won, and return "
            "performance specifically against top-tier (top-20-ranked) servers."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "return_strength", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: mean of charting return-point win "
                    "rate and the match-aggregate return-strength ingredient -- the "
                    "broadest single 'how good is this return' read on disk."
                ),
            },
            {
                "attribute": "match_agg_return_pts_won_Overall", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: aggregate return-points-won rate across all "
                    "surfaces -- a match_stats-sourced confirmation of the return "
                    "read, independent of the charting corpus."
                ),
            },
            {
                "attribute": "opp_tier_return_pts_won_top20", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: return points won restricted to matches against "
                    "top-20-ranked opponents -- tests the return game against the "
                    "best servers, not just an easier average field."
                ),
            },
        ],
        "context_qualifiers": [
            "All three signals are DESCRIPTIVE -- no gate has tested whether these "
            "predict match outcomes beyond their own definition.",
            "Every signal here is higher_is_better -- no inversion needed (see "
            "module docstring on the plain-rank orientation of every tennis "
            "attribute).",
            "Window defaults to each entity's own latest available year: this "
            "surfaces CURRENT return form, not career-peak reputation (verified "
            "against Novak Djokovic -- career percentile 66, latest-year 42; see "
            "module docstring).",
        ],
        "failure_modes": [
            "opp_tier_return_pts_won_top20 has a much smaller qualified population "
            "than the other two signals (fewer players face 15+ top-20 opponents) "
            "-- its shrinkage weight is naturally smaller for thin-sample entities, "
            "but it can still be entirely absent for a player who has never faced "
            "enough top-20 opponents, silently dropping to a 2-signal composite.",
            "return_strength and match_agg_return_pts_won_Overall both ultimately "
            "measure 'points won on return' and are not fully independent "
            "confirmations of the same underlying skill.",
            "min_n floor rationale: return_strength n counts charting RETURN "
            "POINTS; 1380 ~= the 40th percentile (q40=1376.2, audited 2026-07-09) "
            "of qualified players' n at their own latest-year window -- above the "
            "attribute's own build floor (charting_return_n=1000).",
        ],
        "min_n": 1380.0,
    },
    "pressure_resilience": {
        "name": "pressure_resilience",
        "description": (
            "How this player performs at the highest-leverage moments within a "
            "match -- serving under break-point pressure (the one VALIDATED "
            "mechanism in this registry), converting their own game points, "
            "recovering after being broken, and holding up serving in tiebreaks."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "pressure_serve", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: bp_save_rate minus the player's own "
                    "baseline serve-win rate -- the ONLY VALIDATED_MECHANISM "
                    "attribute in the registry (independently REPLICATED sign/"
                    "significance across slam_points and charting_points 2016+, "
                    "see attribute_registry.py). STATUS_RANK[VALIDATED_MECHANISM]=4 "
                    "vs 2 for the other three DESCRIPTIVE signals here -- the "
                    "status-rank x n-shrinkage formula gives this signal roughly "
                    "double the per-unit-n weight of the others automatically, no "
                    "manual override needed."
                ),
            },
            {
                "attribute": "game_point_conversion", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: win-rate delta on the player's OWN game point vs "
                    "their baseline serve-win rate -- the mirror of pressure_serve "
                    "at a different pressure moment (closing out a game, not "
                    "saving a break), computed descriptively rather than via the "
                    "replicated mechanism path."
                ),
            },
            {
                "attribute": "momentum_bounceback", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: hold-rate delta in the service game immediately "
                    "after being broken, vs baseline -- a different pressure axis "
                    "(recovering from adversity mid-match, not a single point)."
                ),
            },
            {
                "attribute": "tiebreak_serve_win_rate", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight: server win rate on tiebreak points -- "
                    "holding up serve in the match's most concentrated pressure "
                    "stretch."
                ),
            },
        ],
        "context_qualifiers": [
            "pressure_serve is the one VALIDATED_MECHANISM signal in this entire "
            "registry (all other tennis and NBA/MLB concept signals are "
            "DESCRIPTIVE) -- its replication is about the SIGN/SIGNIFICANCE of "
            "the break-point-serve-dip effect, not a claim this composite predicts "
            "match outcomes.",
            "The other three signals are DESCRIPTIVE deltas/splits with no "
            "replicated mechanism behind them -- same caution as NBA/MLB's clutch "
            "concepts (small-sample-by-construction leverage windows).",
            "Every signal here is higher_is_better -- no inversion needed.",
        ],
        "failure_modes": [
            "All four signals are delta/split metrics computed on small "
            "leverage-restricted subsets of a player's points -- one hot or cold "
            "stretch of break points, game points, or tiebreaks can dominate given "
            "the low attempt counts near each signal's own floor.",
            "pressure_serve and game_point_conversion are structurally mirror-"
            "image formulas (delta vs baseline at two different score states) and "
            "are not fully independent confirmations of a single 'clutch' trait.",
            "min_n floor rationale: pressure_serve n counts BREAK POINTS FACED; "
            "330 ~= the 40th percentile (q40=330.4, audited 2026-07-09) of "
            "qualified players' n -- above the attribute's own build floor "
            "(n_bp_faced=200).",
        ],
        "min_n": 330.0,
    },
    "stamina": {
        "name": "stamina",
        "description": (
            "How well this player's serve holds up as a match runs deep -- serve "
            "win rate once the match reaches set 3 or later, confirmed against "
            "set-2 performance."
        ),
        "entity": "player",
        "signals": [
            {
                "attribute": "serve_by_set_set3plus", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: server win rate on points played in "
                    "set 3 or later -- the direct 'still serving well deep into the "
                    "match' read, the freshest available late-match state."
                ),
            },
            {
                "attribute": "serve_by_set_set2", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: server win rate in set 2 -- mid-match context "
                    "confirming the set-3+ read isn't a single-set fluke."
                ),
            },
        ],
        "context_qualifiers": [
            "Deliberately 2 signals, not 3: set-1 win rate was considered and "
            "excluded on purpose. Averaging it in would reward overall serve "
            "strength rather than isolating deep-match durability -- this concept "
            "does not compute a DECLINE (set1 minus set3plus); it measures the "
            "absolute level of late-match serve performance.",
            "Both signals are DESCRIPTIVE -- no gate has tested whether either "
            "predicts winning long matches beyond its own definition.",
            "Every signal here is higher_is_better -- no inversion needed.",
        ],
        "failure_modes": [
            "A player who simply has a great serve everywhere will score well "
            "here without necessarily being MORE resilient late than early -- this "
            "concept cannot distinguish 'fades less' from 'is just good at serving'.",
            "serve_by_set_set3plus and serve_by_set_set2 share the same underlying "
            "set-bucket-points ingredient and are not fully independent "
            "confirmations.",
            "min_n floor rationale: serve_by_set_set3plus n counts SET-3+ SERVE "
            "POINTS; 210 ~= the 40th percentile (q40=208.0, audited 2026-07-09) of "
            "qualified players' n -- above the attribute's own build floor (n=150).",
        ],
        "min_n": 210.0,
    },
}


def get_concept(name: str) -> dict[str, Any]:
    c = CONCEPTS.get(name)
    if c is None:
        raise KeyError(f"unknown concept '{name}'. Available: {sorted(CONCEPTS)}")
    return c


def list_concepts() -> list[str]:
    return sorted(CONCEPTS)


_YEAR_RE = re.compile(r"^(?:year_)?(\d{4})$")


def _year_of(window) -> int | None:
    """Extract a calendar year from either window convention tennis uses
    (bare "2024" or prefixed "year_2024"); None for career_to_2026/last10."""
    m = _YEAR_RE.match(str(window))
    return int(m.group(1)) if m else None


def _latest_rows(df: pd.DataFrame, window: str | None) -> pd.DataFrame:
    """One row per (entity_id, attribute): the given window if present, else
    each entity's own LATEST YEAR (max of bare-year/year_-prefixed windows);
    falls back to whatever single non-year window exists (career_to_2026 /
    last10) only for attributes with no year-windowed rows at all. See module
    docstring WINDOW SELECTION for why this differs from NBA/MLB's plain
    lexical-sort convention."""
    if window:
        w = df[df["window"] == window]
        if not w.empty:
            df = w
            return df.sort_values("window").groupby(
                ["entity_id", "attribute"], as_index=False).tail(1)

    df = df.copy()
    df["_year"] = df["window"].map(_year_of)
    key = ["entity_id", "attribute"]
    has_year = df.groupby(key)["_year"].transform(lambda s: s.notna().any())
    year_rows = df[has_year & df["_year"].notna()]
    nonyear_rows = df[~has_year]
    year_latest = (year_rows.sort_values("_year")
                   .groupby(key, as_index=False).tail(1))
    nonyear_latest = (nonyear_rows.sort_values("window")
                       .groupby(key, as_index=False).tail(1))
    out = pd.concat([year_latest, nonyear_latest], ignore_index=True)
    return out.drop(columns="_year")


def derive_weights(concept: dict[str, Any], profiles_df: pd.DataFrame,
                    window: str | None = None) -> pd.DataFrame:
    """Status-rank x n-shrinkage weights, normalized per entity, for one concept.
    Same formula as domains/basketball_nba/concepts/concept_registry.py's
    derive_weights -- duplicated here (not imported cross-domain) so each sport
    adapter stays self-contained. Uses tennis's own _latest_rows (latest-year
    default, not plain lexical sort -- see module docstring)."""
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
    # n0 = the concept's own min_n: shrinkage midpoint on the same denominator
    # scale as the exclusion floor (see module docstring WEIGHT DERIVATION).
    n0 = float(concept.get("min_n") or N0)
    sub["base_weight"] = status_rank * (sub["n"] / (sub["n"] + n0))

    totals = sub.groupby("entity_id")["base_weight"].transform("sum")
    sub["norm_weight"] = (sub["base_weight"] / totals.where(totals > 0, 1.0)).fillna(0.0)
    return sub.reset_index(drop=True)
