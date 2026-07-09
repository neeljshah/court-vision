"""Concept registry -- the MLB "answer engine" composite definitions.

Same pattern as domains/basketball_nba/concepts/concept_registry.py (read that
module's docstring for the full WEIGHT DERIVATION explanation; reproduced
below only where it differs for MLB). A scouting-style question ("who has the
best stuff?") is answered by a CONCEPT: a small, documented set of signals
from domains/mlb/profiles/attribute_registry.py (every `attribute` below is
verified to exist in ATTRIBUTES -- see test_answer_quality_mlb.py), combined
with DERIVED weights.

WEIGHT DERIVATION (same shape as the NBA registry, not hand-tuned):
    base_weight = STATUS_RANK[row.status] * (row.n / (row.n + n0))
    norm_weight = base_weight / sum(base_weight over the concept's signals
                  actually present for that entity+window)
where n0 = the concept's own min_n (NOT the NBA registry's global 200): MLB
attribute n columns live on wildly different denominators (pitches ~1000s,
swings/taken-pitches ~100s-1000s, balls-in-play ~10s-100s, PA ~100s), so one
global shrinkage midpoint is miscalibrated across concepts -- 200 over-shrinks
BIP-scale signals and under-shrinks pitch-scale ones. Tying the midpoint to
the concept's own exclusion floor keeps shrinkage on the same denominator
scale the floor was chosen on.
KNOWN LIMIT (documented, not hidden): shrinkage renormalizes WITHIN an
entity, so an entity whose ONLY present signal is thin still gets
norm_weight=1.0 on it -- shrinkage reweights signals against each other; it
cannot penalize a composite overall. min_n on the primary signal is the one
real defense against a small-sample entity topping a ranking. That is why
the floors below are set from the live parquet's qualified-population n
distribution (~40th percentile of the primary signal's n among entities that
have it, audited 2026-07-09), NOT from the attribute registry's own
per-attribute build floors -- those exist to make a number computable at
all, not to make a leaderboard rank trustworthy. Concretely: the build
floors admitted a 206-taken-pitch reliever as the #1 'command' arm; the
distribution-based floors below exclude sub-half-season pitch samples.

ORIENTATION -- this is the ONE thing that differs from NBA and is the reason
every direction flag below is deliberate, not copy-pasted: empirically
audited 2026-07-09 across all 106 attributes on data/cache/profiles/
mlb_player_profiles.parquet, corr(raw_value, percentile) is POSITIVE
(+0.85 to +0.99) for EVERY attribute with no exception found. Unlike the NBA
profile builder, the MLB builder does NOT pre-orient percentiles by natural
"better direction" -- percentile is always a plain rank of raw_value, high
raw = high percentile, full stop. That means direction here is decided purely
by concept semantics (does a HIGH raw value mean good, for THIS concept?),
never by "the builder already inverted it for me". Every attribute below
whose raw semantics run the "wrong" way for its concept (e.g. xwOBA allowed
-- lower is better pitching) is flagged lower_is_better; nothing here should
be assumed pre-oriented the way NBA's zone_def_* columns are.

ROLE SCOPING -- MLB ships ONE profiles parquet (mlb_player_profiles.parquet,
kind="player"), not separate pitcher/batter/catcher files. Role scoping is
NOT a separate filter step; it falls out of which attributes exist for which
entity_id, because attribute_registry.py's per-attribute `entity` field
(pitcher/batter/catcher) determines which entities the builder ever computes
a row for. Verified empirically: of 816 entities with pitcher-only
attributes and 449 with batter-only attributes, exactly ONE entity_id
(Shohei Ohtani, a genuine two-way player) has both -- that is correct
behavior, not a scoping bug. A "best stuff" query (all-pitcher signals) can
therefore never surface a pure batter; a "best power" query (all-batter
signals) can never surface a pure pitcher.

Each concept entry: same shape as the NBA registry (name, description,
entity, signals[{attribute, direction, weight_basis}], context_qualifiers,
failure_modes, min_n). min_n applies to the PRIMARY signal's n and is set
from the live parquet's qualified-population distribution (see WEIGHT
DERIVATION above), always at or above the attribute's own build floor.
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
    "stuff": {
        "name": "stuff",
        "description": (
            "How nasty this pitcher's raw arsenal is -- swing-and-miss ability, "
            "velocity, and chase-inducing deception, independent of location."
        ),
        "entity": "pitcher",
        "signals": [
            {
                "attribute": "whiff_rate", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: swing-and-miss rate among swings -- "
                    "the most direct 'how hard is this to hit' read on disk."
                ),
            },
            {
                "attribute": "velo_band", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: mean release speed. Raw velocity is the classic "
                    "'stuff' proxy scouts lead with, independent of whether it's located."
                ),
            },
            {
                "attribute": "putaway_rate", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: strikeout conversion once a PA reaches 2 strikes -- "
                    "can this pitcher finish hitters off with his out-pitch."
                ),
            },
            {
                "attribute": "chase_induce_rate_ahead", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight: swing rate induced on CHASE-zone pitches "
                    "when ahead in the count -- deception/shape getting hitters to bite "
                    "outside the zone, a different flavor of 'nasty' than raw whiffs."
                ),
            },
        ],
        "context_qualifiers": [
            "All four signals are DESCRIPTIVE -- none has passed a leak-free "
            "predictive gate; this ranks raw stuff as measured, not as a proven "
            "signal of run prevention.",
            "Percentiles here are NOT builder-pre-oriented (unlike NBA's zone_def_* "
            "columns) -- every signal in this concept is higher_is_better because raw "
            "high genuinely means better stuff, verified via corr(raw,pct)~+0.96-0.99.",
        ],
        "failure_modes": [
            "A max-effort reliever with a small, cherry-picked high-leverage sample "
            "can out-rank a durable starter with a larger, more representative sample.",
            "whiff_rate and putaway_rate both reward swing-and-miss outcomes and can "
            "double-count the same underlying skill rather than confirming it independently.",
            "min_n floor rationale: whiff_rate n counts SWINGS (not pitches); 300 ~= the 40th percentile (q40=308, audited 2026-07-09) of qualified-pitcher swing counts -- roughly a 650+ pitch half-season. The attribute's own build floor (100 swings) admitted ~160-swing fringe relievers into the top-5.",
        ],
        "min_n": 300.0,
    },
    "command": {
        "name": "command",
        "description": (
            "How well this pitcher locates -- working the strike-zone edge, getting "
            "ahead early, and avoiding the plate's heart when behind in the count."
        ),
        "entity": "pitcher",
        "signals": [
            {
                "attribute": "command_edge_share", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: share of taken pitches landing in the "
                    "zone-edge shell -- the most direct 'hits his spots' read on disk."
                ),
            },
            {
                "attribute": "first_pitch_strike_rate", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: getting ahead 0-1 is a command outcome as much as a "
                    "strategy choice -- consistently landing pitch one for a strike."
                ),
            },
            {
                "attribute": "command_edge_share_behind", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: the same edge-share read restricted to counts where the "
                    "pitcher is behind -- command under pressure, not just command overall."
                ),
            },
            {
                "attribute": "heart_share_behind", "direction": "lower_is_better",
                "weight_basis": (
                    "Tertiary, small weight: share of pitches landing in the HEART zone "
                    "when behind in the count -- a HIGH share here means grooving mistake "
                    "pitches under pressure, the direct inverse of good command; raw-high "
                    "is bad for this concept even though the builder never inverted the "
                    "column itself (corr(raw,pct)=+0.96, plain rank -- see module docstring)."
                ),
            },
        ],
        "context_qualifiers": [
            "All four signals are DESCRIPTIVE -- no gate has tested whether any of "
            "these predicts run prevention or winning.",
            "heart_share_behind is the ONE lower_is_better signal in this concept -- "
            "its raw value tracks its percentile directly (no builder pre-orientation), "
            "so consuming it as-is would score 'grooves more meatballs under pressure' "
            "as good command; only the inversion here is concept-specific.",
        ],
        "failure_modes": [
            "A pitcher who simply nibbles (avoids the zone entirely) can inflate "
            "edge-share without genuinely locating -- this concept does not separate "
            "intentional waste pitches from missed spots.",
            "command_edge_share and command_edge_share_behind reuse the same underlying "
            "borderline-pitch classifier and are not independent confirmations of skill.",
            "min_n floor rationale: command_edge_share n counts TAKEN pitches; 430 = the 40th percentile of qualified-pitcher taken-pitch counts (audited 2026-07-09) -- roughly a 900+ pitch half-season. The attribute's own build floor (200) admitted a 206-taken-pitch reliever as the #1 command arm.",
        ],
        "min_n": 430.0,
    },
    "discipline": {
        "name": "discipline",
        "description": (
            "How well this batter controls the strike zone -- drawing walks, avoiding "
            "strikeouts, laying off borderline pitches, and not chasing off-speed stuff."
        ),
        "entity": "batter",
        "signals": [
            {
                "attribute": "BB_rate", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: walk rate per plate appearance -- the "
                    "clearest single plate-discipline outcome on disk."
                ),
            },
            {
                "attribute": "K_avoidance", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: 1 - strikeout rate. Avoiding strikeouts is a discipline "
                    "and bat-control read distinct from, but correlated with, walk rate."
                ),
            },
            {
                "attribute": "shadow_take_rate", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: 1 - swing rate on borderline (SHADOW-zone) pitches -- "
                    "how often this batter lays off the pitches an umpire could call "
                    "either way, a purer zone-judgment read than the outcome-based signals."
                ),
            },
            {
                "attribute": "chase_vs_breaking", "direction": "lower_is_better",
                "weight_basis": (
                    "Tertiary, small weight: swing rate on out-of-zone breaking-ball "
                    "pitches -- chasing breaking stuff out of the zone is a classic "
                    "discipline tell; raw-high chase rate is bad for this concept."
                ),
            },
        ],
        "context_qualifiers": [
            "All four signals are DESCRIPTIVE -- no gate has tested whether any of "
            "these predicts on-base outcomes at the game level beyond their own "
            "definition (BB_rate is close to definitionally on-base-adjacent).",
            "chase_vs_breaking is the ONE lower_is_better signal in this concept -- "
            "its raw value tracks its percentile directly (no builder pre-orientation, "
            "see module docstring), so only the concept-level inversion makes chasing "
            "less score as more disciplined.",
        ],
        "failure_modes": [
            "A passive hitter who takes hittable strikes purely to run up the count "
            "can look disciplined here without actually having good zone judgment.",
            "BB_rate and K_avoidance both partly reflect a team's pitching-matchup "
            "quality, not just the batter's own skill.",
            "min_n floor rationale: BB_rate n counts PA; 350 ~= the 40th percentile (q40=352, audited 2026-07-09) of qualified-batter PA counts -- a bit over a half-season of everyday PAs.",
        ],
        "min_n": 350.0,
    },
    "power": {
        "name": "power",
        "description": (
            "How much authority this batter puts on contact -- barrel rate, hard-hit "
            "rate, and the resulting damage on the easiest pitches to drive."
        ),
        "entity": "batter",
        "signals": [
            {
                "attribute": "contact_quality", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: barrel share of batted balls (Statcast's "
                    "own public barrel code) -- the cleanest single power proxy on disk."
                ),
            },
            {
                "attribute": "hard_contact_share", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: hard-hit share, broader than barrels-only -- volume "
                    "context so a small-sample barrel outlier isn't mistaken for power."
                ),
            },
            {
                "attribute": "heart_damage_xwoba", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: xwOBA on contact restricted to the HEART zone -- damage "
                    "done on the easiest pitches to drive, a results-based power check "
                    "against the two quality-of-contact signals above."
                ),
            },
        ],
        "context_qualifiers": [
            "All three signals are DESCRIPTIVE -- no gate has tested whether any of "
            "these predicts winning; this ranks measured power, not a proven edge.",
            "Every signal here is higher_is_better because raw-high genuinely means "
            "more power for this concept -- no inversion needed (see module docstring "
            "on the plain-rank orientation of every MLB attribute).",
        ],
        "failure_modes": [
            "contact_quality and hard_contact_share share the same launch_speed_angle "
            "ingredient and are not fully independent confirmations of raw power.",
            "A batter who rarely sees heart-zone pitches (good pitch recognition against "
            "him) has a thinner heart_damage_xwoba sample near its 20-BIP floor.",
            "min_n floor rationale: contact_quality n counts BATTED BALLS; 170 ~= the 40th percentile (q40=169, audited 2026-07-09) of qualified-batter batted-ball counts.",
        ],
        "min_n": 170.0,
    },
    "clutch": {
        "name": "clutch",
        "description": (
            "How this batter performs in higher-leverage spots: with a runner in "
            "scoring position, late in games, and once the count reaches two strikes."
        ),
        "entity": "batter",
        "signals": [
            {
                "attribute": "risp_xwoba_delta", "direction": "higher_is_better",
                "weight_basis": (
                    "Primary and definitional: xwOBA delta with a runner in scoring "
                    "position vs without -- the most direct 'performs when it matters' read."
                ),
            },
            {
                "attribute": "inning_late_xwoba_delta", "direction": "higher_is_better",
                "weight_basis": (
                    "Secondary: xwOBA delta innings 7+ minus innings 1-6 -- late-game "
                    "performance, a different leverage axis than RISP alone."
                ),
            },
            {
                "attribute": "xwoba_two_strike", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight: xwOBA on PAs that reach a 2-strike count -- "
                    "holding up offensively once the pitcher has the individual-PA edge."
                ),
            },
        ],
        "context_qualifiers": [
            "Clutch windows are small-sample by construction (RISP/late-inning PAs are "
            "a fraction of total PAs per season); read this as descriptive, not a stable "
            "trait -- same caution as the NBA registry's clutch concept.",
            "All three signals are DESCRIPTIVE deltas/splits with no replicated causal "
            "mechanism behind them (see attribute_registry.py's TTO_durability precedent "
            "for why a nearby mechanism failing replication keeps a split DESCRIPTIVE).",
        ],
        "failure_modes": [
            "One hot or cold stretch of high-leverage PAs can dominate a season's delta "
            "given the low attempt counts near each signal's own floor.",
            "risp_xwoba_delta and inning_late_xwoba_delta can both be inflated or "
            "deflated by opposing-pitcher quality in those specific situational PAs, "
            "not just the batter's own clutch skill.",
            "min_n floor rationale: risp_xwoba_delta n counts RISP PA (min of the two split cells); 70 ~= the 40th percentile (q40=74, audited 2026-07-09) of qualified-batter RISP-PA counts -- the build floor (30) let an n=30 batter tie for #2.",
        ],
        "min_n": 70.0,
    },
    "contact_control": {
        "name": "contact_control",
        "description": (
            "How well this pitcher suppresses damage on contact -- limiting xwOBA "
            "allowed across pitch classes and in the zone's most hittable region, plus "
            "inducing groundballs over more damaging air contact."
        ),
        "entity": "pitcher",
        "signals": [
            {
                "attribute": "xwoba_against_by_class_fastball", "direction": "lower_is_better",
                "weight_basis": (
                    "Primary and definitional: xwOBA allowed on balls in play against "
                    "fastball-class pitches -- fastballs are the highest-volume pitch "
                    "class, so this is the broadest single damage-suppression read."
                ),
            },
            {
                "attribute": "xwoba_against_by_class_breaking", "direction": "lower_is_better",
                "weight_basis": (
                    "Secondary: the same xwOBA-allowed read restricted to breaking-ball "
                    "contact -- confirms damage suppression isn't fastball-specific."
                ),
            },
            {
                "attribute": "region_xwoba_against_heart", "direction": "lower_is_better",
                "weight_basis": (
                    "Secondary: xwOBA allowed restricted to the HEART attack zone -- "
                    "damage suppression specifically on the easiest pitches to drive, "
                    "independent of pitch class."
                ),
            },
            {
                "attribute": "gb_tendency", "direction": "higher_is_better",
                "weight_basis": (
                    "Tertiary, small weight: groundball share of balls in play -- "
                    "groundballs are lower-xwOBA-on-average contact than air contact, "
                    "a shape-based proxy alongside the three direct xwOBA-allowed reads."
                ),
            },
        ],
        "context_qualifiers": [
            "All four signals are DESCRIPTIVE -- no gate has tested whether any of "
            "these predicts run prevention beyond their own definition.",
            "Three of the four signals here are lower_is_better -- xwOBA-allowed raw "
            "value tracks its percentile directly (no builder pre-orientation, see "
            "module docstring), so lower raw xwOBA allowed must be inverted (100-pct) "
            "to score as good contact control; only gb_tendency stays higher_is_better.",
        ],
        "failure_modes": [
            "The three xwOBA-allowed signals share the same estimated_woba_using_"
            "speedangle ingredient and are not fully independent confirmations.",
            "A pitcher who induces weak fly balls (also low-damage) is not credited "
            "here the way a groundball pitcher is -- gb_tendency only rewards one "
            "specific weak-contact shape.",
            "min_n floor rationale: xwoba_against_by_class_fastball n counts fastball BALLS IN PLAY; 70 ~= the 40th percentile (q40=72, audited 2026-07-09) of qualified-pitcher fastball-BIP counts -- the build floor (30) put three ~35-BIP relievers in the top-3.",
        ],
        "min_n": 70.0,
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
    # n0 = the concept's own min_n: shrinkage midpoint on the same denominator
    # scale as the exclusion floor (see module docstring WEIGHT DERIVATION).
    n0 = float(concept.get("min_n") or N0)
    sub["base_weight"] = status_rank * (sub["n"] / (sub["n"] + n0))

    totals = sub.groupby("entity_id")["base_weight"].transform("sum")
    sub["norm_weight"] = (sub["base_weight"] / totals.where(totals > 0, 1.0)).fillna(0.0)
    return sub.reset_index(drop=True)
