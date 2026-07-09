"""Concept registry -- the soccer "answer engine" composite definitions.

Same pattern as domains/basketball_nba/concepts/concept_registry.py (read that
module's docstring for the full WEIGHT DERIVATION explanation, reproduced
below only where it differs for soccer). A scouting-style question ("who has
the best transition threat?") is answered by a CONCEPT: a small, documented
set of signals from domains/soccer/profiles/attribute_registry.py's REGISTRY
(every `attribute` below is verified to exist in REGISTRY -- see
test_answer_quality_soccer.py), combined with DERIVED weights. Soccer is
TEAM-entity only (kind="team" everywhere -- pass kind="team" to every
contracts.py call, the default is "player").

WEIGHT DERIVATION (same shape as MLB/tennis, not hand-tuned):
    base_weight = STATUS_RANK[row.status] * (row.n / (row.n + n0))
    norm_weight = base_weight / sum(base_weight over the concept's signals
                  actually present for that entity+window)
where n0 = the concept's own min_n (same rationale as MLB/tennis).

ORIENTATION -- soccer is the ODD ONE OUT vs MLB/tennis: its attribute_
registry.py declares an explicit `higher_is_better` flag PER ATTRIBUTE, and
build_profiles.add_percentile_rating() uses it to flip raw_value (basis =
raw_value if higher_is_better else -raw_value) BEFORE ranking into a
percentile. That means soccer's percentile column is builder-PRE-ORIENTED,
same convention as NBA's zone_def_* columns -- NOT like MLB/tennis's plain
rank. Verified empirically 2026-07-09 across all 25 attributes on data/cache/
profiles/soccer_team_profiles.parquet: corr(raw_value, percentile) is
NEGATIVE (-0.92 to -0.99) for every attribute whose registry entry declares
higher_is_better=False (defensive_solidity, defensive_counter_threat,
defensive_set_piece_threat, discipline_rate, foul_rate) and POSITIVE (+0.78
to +0.98) for every attribute declaring higher_is_better=True -- confirming
the builder's flip. CONSEQUENCE: every signal used below is
direction="higher_is_better" in concept terms (consume percentile as-is),
including the three "lower raw = better" defensive signals in 'solidity' --
do NOT re-invert them, that would double-flip an already-oriented column.

ENTITY-SPACE LANDMINE (read before touching this file): soccer ships ONE
profiles parquet (soccer_team_profiles.parquet) but TWO DISJOINT entity_id
spaces inside it, one per corpus:
  - corpus="statsbomb_event" (window="statsbomb_2015_2021"): entity_id is a
    numeric StatsBomb team id (e.g. 971). This is the English Women's Super
    League 2015-2021 sample -- 9 teams clear the 30-team_matches floor for
    the possession-chain attributes (counter_threat, buildup_quality,
    defensive_solidity, defensive_counter_threat, defensive_set_piece_
    threat, shots_per_possession, first/second_half_xg_share, formation_*).
  - corpus="footballdata_season" (window="footballdata_<season>", 2015-2025):
    entity_id is the club NAME STRING (e.g. "Bayern Munich"), a completely
    different set of European men's leagues, one row per team-season.
Verified 2026-07-09: these two id spaces NEVER overlap (no footballdata club
name matches a statsbomb numeric id, and there is no cross-reference table).
A concept that mixes a statsbomb-corpus signal with a footballdata-corpus
signal would score almost every entity on only ONE of the two signals --
silently degrading to a single-signal composite, not a real multi-signal
one. Every concept below therefore draws ALL its signals from ONE corpus.
The 3 built concepts all use the statsbomb corpus (9-team WSL population,
small but self-consistent); footballdata-only concepts (home_strength,
clean_sheet_rate, etc.) are left for a future pass, not attempted here.

SKIPPED CONCEPTS (documented, not silently dropped):
  - set_piece_threat: only ONE column measures a team's OWN attacking
    set-piece share (set_piece_threat itself, VALIDATED_CLAIM).
    defensive_set_piece_threat is the OPPONENT-conceded mirror -- already
    used inside 'solidity' as a defensive signal, not a second confirmation
    of attacking set-piece threat. No second attacking-side signal exists in
    the registry -- shipping this as a 1-column concept would be exactly the
    "disguised single column" trap the task warned against. SKIPPED.
  - press_intensity: NO pressing-related attribute exists anywhere in the
    registry. press_resistance is explicitly BLOCKED (see attribute_
    registry.BLOCKED_ATTRIBUTES) -- location isn't attacking-direction-
    normalized, so it was never built at all. Zero signals available, not
    just an insufficient count. SKIPPED.

Each concept entry: same shape as MLB/tennis (name, description, entity,
signals[{attribute, direction, weight_basis}], context_qualifiers,
failure_modes, min_n). min_n applies to the PRIMARY (first-listed) signal's
own n and is set from the live parquet's qualified-population n distribution
-- ~40th percentile of the primary signal's n among the 9 statsbomb-corpus
teams, audited 2026-07-09. The whole statsbomb corpus is small (400 matches,
9 teams clear the floor), so these floors sit only slightly above the
attribute's own build floor (30) -- unlike NBA/MLB/tennis's much larger
populations, there isn't much room to raise the bar further without
excluding most of the population.
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
# shrinkage midpoint fallback -- derive_weights uses the concept's own min_n
# as n0 (see module docstring); this constant only backstops a concept dict
# missing min_n (e.g. a synthetic test concept).
N0 = 200.0

CONCEPTS: dict[str, dict[str, Any]] = {
    "threat": {
        "name": "threat",
        "description": (
            "How dangerous this team's regular attacking play is -- sustained "
            "buildup xG output, confirmed against its output specifically in its "
            "own most-used starting formation."
        ),
        "entity": "team",
        "signals": [
            {
                "attribute": "buildup_quality", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: regular-play (non-counter, non-set-"
                    "piece) xG per possession -- the broadest read of a team's "
                    "sustained attacking output, independent of transition or "
                    "dead-ball routes (those are 'transition' and the skipped "
                    "set_piece_threat concept's territory)."
                ),
            },
            {
                "attribute": "formation_primary_xg", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: xG per possession restricted to matches played in "
                    "this team's own most-used detected starting formation -- "
                    "confirms the buildup read isn't an artifact of one unusual "
                    "tactical setup, though its qualified population is narrower "
                    "(needs >=10 matches in that formation)."
                ),
            },
        ],
        "context_qualifiers": [
            "Both signals draw from the SAME statsbomb_event corpus (400-match "
            "WSL 2015-2021 sample, 9 teams clear the 30-team_matches floor) -- "
            "this is a small, single-competition population, not a claim about "
            "attacking quality across all of football.",
            "buildup_quality is VALIDATED_CLAIM (re-verified against the claims "
            "store); formation_primary_xg is DESCRIPTIVE -- the status-rank x "
            "n-shrinkage formula weights the primary signal higher automatically.",
        ],
        "failure_modes": [
            "buildup_quality excludes counter and set-piece xG by construction -- "
            "a team that scores heavily off turnovers or dead balls can show "
            "mediocre 'threat' here despite being genuinely dangerous overall "
            "(see the separate 'transition' concept for that read).",
            "formation_primary_xg can be noisy for a team that only nominally "
            "sticks to one formation -- 10 matches is a thin in-formation sample; "
            "an entity missing this signal is still scored on buildup_quality "
            "alone (normalized weight redistributes to 1.0 on the one signal).",
            "min_n floor rationale: buildup_quality n counts TEAM MATCHES in the "
            "statsbomb corpus; 35 ~= the 40th percentile (q40=35.0, audited "
            "2026-07-09) of the corpus's only 9 qualified teams -- the corpus "
            "itself is small, so this floor sits only slightly above the "
            "attribute's own build floor (30).",
        ],
        "min_n": 35.0,
    },
    "solidity": {
        "name": "solidity",
        "description": (
            "How hard this team is to score against -- xG conceded per possession "
            "in regular play, confirmed against counter-defense and set-piece "
            "defense specifically."
        ),
        "entity": "team",
        "signals": [
            {
                "attribute": "defensive_solidity", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: xG conceded per opponent possession "
                    "in regular play -- the broadest 'how hard is this team to "
                    "score against' read, mirroring buildup_quality's construction "
                    "on the defensive end."
                ),
            },
            {
                "attribute": "defensive_counter_threat", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: xG conceded per opponent possession specifically "
                    "off counter-attacks against -- confirms the solidity read "
                    "holds up in transition defense, not just structured defending."
                ),
            },
            {
                "attribute": "defensive_set_piece_threat", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight: share of xG conceded that comes from "
                    "opponent set pieces -- a team can be excellent in open play "
                    "yet leaky at dead balls; this catches that gap without "
                    "dominating the composite."
                ),
            },
        ],
        "context_qualifiers": [
            "All three signals are DESCRIPTIVE and share the same statsbomb_event "
            "corpus/window as 'threat' -- same small single-competition caveat.",
            "Percentiles here are builder-pre-oriented (soccer's add_percentile_"
            "rating flips raw_value by the registry's own higher_is_better=False "
            "flag before ranking, verified 2026-07-09: corr(raw,pct) = -0.98/"
            "-0.93/-0.99 for these three RAW-lower-is-better attributes) -- every "
            "signal is consumed as higher_is_better here, do NOT re-invert.",
        ],
        "failure_modes": [
            "defensive_solidity, defensive_counter_threat, and defensive_set_"
            "piece_threat all derive from the same possession-level xG-conceded "
            "ingredient computed on different subsets -- not fully independent "
            "confirmations of defensive quality.",
            "A team that simply concedes few shots (low-event, deep-block style) "
            "can look solid here without genuinely suppressing shot quality when "
            "shots do occur -- this concept measures xG conceded, not shot volume.",
            "min_n floor rationale: same 9-team/34-37-n population as threat -- "
            "see that concept's rationale; 35 = q40 audited 2026-07-09.",
        ],
        "min_n": 35.0,
    },
    "transition": {
        "name": "transition",
        "description": (
            "How much of a counter-attacking threat this team is -- weighted by "
            "the ONE replicated mechanism in this registry, confirmed against a "
            "general attacking-directness proxy."
        ),
        "entity": "team",
        "signals": [
            {
                "attribute": "counter_threat", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: the ONE VALIDATED_MECHANISM "
                    "attribute in this registry -- the counter-attack xG premium "
                    "is independently REPLICATED (see domains.soccer.prereg_"
                    "possession_chains, hypothesis=counter_attack_xg_premium, "
                    "replication_verdict=REPLICATED). STATUS_RANK[VALIDATED_"
                    "MECHANISM]=4 vs 2 for the DESCRIPTIVE secondary signal -- "
                    "the status-rank x n-shrinkage formula gives this signal "
                    "roughly double the per-unit-n weight automatically, no "
                    "manual override needed (same status-driven weighting "
                    "precedent as tennis's pressure_serve concept)."
                ),
            },
            {
                "attribute": "shots_per_possession", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: shot attempts per possession -- a directness "
                    "proxy. Counter-attacking teams tend to convert fewer, faster "
                    "sequences into shots, so a high shots-per-possession rate is "
                    "corroborating context for a genuinely transition-oriented "
                    "attacking identity, not just a lucky small-sample counter-xG "
                    "read."
                ),
            },
        ],
        "context_qualifiers": [
            "counter_threat is the one VALIDATED_MECHANISM signal in this entire "
            "registry; shots_per_possession is DESCRIPTIVE and a general tempo "
            "proxy, not itself counter-specific -- it can be elevated by ANY "
            "fast, direct attacking style, not only counters.",
            "Same 9-team statsbomb corpus/window as threat and solidity.",
        ],
        "failure_modes": [
            "A team with a small number of highly efficient counters (high "
            "counter_threat) but generally slow, possession-heavy buildup (low "
            "shots_per_possession) shows a diluted composite despite a "
            "genuinely dangerous transition game -- the secondary signal is not "
            "a pure counter-attack measure.",
            "9-team population means the 'top' of this list is a large fraction "
            "of the entire qualified corpus, not a broad league-wide leaderboard.",
            "min_n floor rationale: same population as threat/solidity; "
            "35 = q40 audited 2026-07-09.",
        ],
        "min_n": 35.0,
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
    the lexically-latest window (mirrors NBA/MLB's convention -- soccer's
    footballdata_<season> windows sort correctly lexically, and every
    statsbomb-corpus attribute used here has exactly one window value, so no
    tennis-style year-extraction is needed)."""
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
    Same formula as domains/mlb/concepts/concept_registry.py's derive_weights --
    duplicated here (not imported cross-domain) so each sport adapter stays
    self-contained. See that module for the full docstring."""
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
