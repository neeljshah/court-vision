"""compose_profile(player) -> multi-axis SHOOTER TRAIT PROFILE, honestly assembled.

A shooter is a VECTOR of traits, never one re-weighted scalar (the platform's
one-conclusion composer rule: absurd conclusions get DOMAIN fixes, never
re-weighting). Luka Doncic is the canonical case: mediocre fg3_pct but extreme
self-created shot difficulty, huge volume, real gravity. So this composer
NEVER combines axes into a score -- each axis is reported with its own value,
rank, and percentile(s), citing its own VERIFIED claim; the profile is the
honest assembly plus a plain-language trait line derived ONLY from declared
percentile bands (BANDS below is config data, never tuned).

Percentiles are presentation math over VERIFIED claim rankings:
    pct = 100 * (pool_n - rank) / (pool_n - 1)        (rank 1 -> 100.0)
reported BOTH within the claim's own full pool (pct_pool) and within the
fg3m>=82 NBA-official qualification subset (pct_qualified) -- membership
comes from the fg3_pct claim's ranking, itself a VERIFIED claim.

Fail-closed: missing qualified-pool claim, or a player found on NO axis,
returns UNANSWERABLE. A single axis missing a row for the player is reported
per-axis as not_in_pool (below that claim's floor, or absent), never guessed.

CLI:
    python -m scripts.platformkit.intel_query.compose_profile "Luka Doncic"
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from scripts.platformkit.intel_query.ask import (
    _ascii_name,
    _claim_evidence,
    load_verified_claims,
    pairs_for_claim_stores,
)

# The ONLY stores this composer reads -- loaded via pairs_for_claim_stores so
# a bare load_verified_claims() never whole-loads the GB-scale bulk rate
# stores (live MemoryError, 2026-07-07).
_PROFILE_STORES: tuple[str, ...] = (
    "nba_shooter_profile_claims.jsonl",
    "nba_shooting_claims.jsonl",
    "nba_canonical_shooter_claims.jsonl",
    "nba_context_shooting_claims.jsonl",
)

QUALIFIED_POOL_CLAIM_ID = "nba_shooter_profile_fg3_pct_qualified_2024-25"


@dataclass(frozen=True)
class _Axis:
    axis: str
    group: str  # volume | efficiency | difficulty | gravity | context
    claim_id: str


# Every axis is an EXISTING VERIFIED claim (only fg3_pct is new, produced by
# intel_validation/nba_shooter_profile_claims.py). No axis is ever combined
# with another -- the vector IS the answer.
AXES: tuple[_Axis, ...] = (
    _Axis("fg3a_per_game", "volume", "nba_fg3a_per_game_top50_2024-25"),
    _Axis("fg3a_share_of_team", "volume", "nba_fg3a_share_of_team_2024-25"),
    _Axis("fg3_pct", "efficiency", QUALIFIED_POOL_CLAIM_ID),
    _Axis("ts_pct", "efficiency", "nba_ts_pct_top50_2024-25"),
    _Axis("canonical_composite", "efficiency", "nba_canonical_shooter_leaderboard_full_season_2024_25"),
    _Axis("pullup_combined_freq", "difficulty", "nba_pullup_combined_freq_top50_2024-25"),
    _Axis("unassisted_share_3pm", "difficulty", "nba_unassisted_share_3pm_top50_2024-25"),
    _Axis("late_clock_shots_pg", "difficulty", "nba_late_clock_shots_pg_top50_2024-25"),
    _Axis("gravity_score", "gravity", "nba_gravity_score_top50_2024-25"),
    _Axis("fg3_pct_rest_split", "context", "nba_fg3_pct_rest_split_2024-25"),
)

# Honest gaps found in the data survey -- reported, never faked with a proxy.
UNBUILT_AXES: tuple[dict[str, str], ...] = (
    {
        "axis": "avg_shot_distance / deep3_share",
        "reason": (
            "no 2024-25 per-shot location parquet exists locally: "
            "atlas_player_shot_profile.parquet's 'zones' field is a DEFER stub "
            "(needs an NBA ShotChartDetail fetch); not fabricated from box data"
        ),
    },
    {
        "axis": "on_off_gravity (teammate efficiency with player on vs off)",
        "reason": (
            "no lineup on/off parquet is ingested; the gravity axis instead cites "
            "the VERIFIED modeled atlas gravity_score claim (see its caveats) -- "
            "a modeled composite, NOT an on/off measurement"
        ),
    },
)

# Declared percentile -> word bands (config DATA, never tuned/fitted).
BANDS: tuple[tuple[float, str], ...] = ((90.0, "elite"), (70.0, "high"), (40.0, "mid"), (0.0, "low"))

TRAIT_LINE_RULE = (
    "trait_line concatenates band words from the declared BANDS table applied to "
    "four named axes: volume=fg3a_per_game, efficiency=fg3_pct (if the player is in "
    "the fg3m>=82 qualified pool, else ts_pct), self-creation=unassisted_share_3pm, "
    "gravity=gravity_score. The percentile used is pct_qualified when the player "
    "qualifies, else pct_pool. An axis with no row for the player reads 'unknown'. "
    "Axes are NEVER combined, weighted, or averaged into one score."
)


def percentile_from_rank(rank: int, pool_n: int) -> float:
    """Rank 1 -> 100.0, last -> 0.0; declared presentation math, no tuning."""
    if pool_n <= 1:
        return 100.0
    return round(100.0 * (pool_n - rank) / (pool_n - 1), 1)


def band_word(pct: float | None) -> str:
    if pct is None:
        return "unknown"
    for threshold, word in BANDS:
        if pct >= threshold:
            return word
    return BANDS[-1][1]


def _axis_entry(axis: _Axis, claim: dict[str, Any] | None, name_key: str,
                qualified_ids: set[int]) -> dict[str, Any]:
    """One axis of the vector: value/rank/percentiles from ONE claim's rows."""
    if claim is None:
        return {"axis": axis.axis, "group": axis.group, "claim_id": axis.claim_id,
                "status": "claim_not_verified"}
    rows = sorted(claim.get("ranking", []), key=lambda r: r.get("rank", 0))
    hit = next(
        (r for r in rows
         if _ascii_name(str(r.get("player_name", ""))).strip().lower() == name_key),
        None,
    )
    if hit is None:
        return {"axis": axis.axis, "group": axis.group, "claim_id": axis.claim_id,
                "status": "not_in_pool",
                "note": "absent from this claim's ranking (below its floor or no data)"}
    pool_n = len(rows)
    entry: dict[str, Any] = {
        "axis": axis.axis, "group": axis.group, "claim_id": axis.claim_id,
        "status": "ok", "value": hit.get("value"), "rank": hit.get("rank"),
        "pool_n": pool_n, "pct_pool": percentile_from_rank(int(hit["rank"]), pool_n),
    }
    q_rows = [r for r in rows if r.get("player_id") in qualified_ids]
    q_hit_idx = next(
        (i for i, r in enumerate(q_rows, start=1) if r.get("player_id") == hit.get("player_id")),
        None,
    )
    if q_hit_idx is None:
        entry["pct_qualified"] = None
        entry["pct_qualified_note"] = "player not in the fg3m>=82 qualified pool"
    else:
        entry["pct_qualified"] = percentile_from_rank(q_hit_idx, len(q_rows))
        entry["pool_qualified_n"] = len(q_rows)
    return entry


def _pct_for_band(entries: dict[str, dict[str, Any]], axis_name: str, qualifies: bool) -> float | None:
    e = entries.get(axis_name)
    if not e or e.get("status") != "ok":
        return None
    if qualifies and e.get("pct_qualified") is not None:
        return e["pct_qualified"]
    return e.get("pct_pool")


def compose_profile(player: str) -> dict[str, Any]:
    """The trait VECTOR for `player` -- see module docstring for the contract."""
    verified = load_verified_claims(pairs_for_claim_stores(_PROFILE_STORES))
    qual_claim = verified.get(QUALIFIED_POOL_CLAIM_ID)
    if qual_claim is None:
        return {"status": "UNANSWERABLE", "player": _ascii_name(player),
                "missing": [f"qualified-pool claim not VERIFIED/available: {QUALIFIED_POOL_CLAIM_ID}"],
                "edge_claimed": False}
    qualified_ids = {r.get("player_id") for r in qual_claim.get("ranking", [])}
    name_key = _ascii_name(player).strip().lower()

    entries: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, Any]] = []
    player_id: int | None = None
    for axis in AXES:
        claim = verified.get(axis.claim_id)
        entry = _axis_entry(axis, claim, name_key, qualified_ids)
        entries[axis.axis] = entry
        if claim is not None:
            evidence.append(_claim_evidence(claim))
        if entry.get("status") == "ok" and player_id is None:
            rows = claim.get("ranking", [])
            hit = next(r for r in rows
                       if _ascii_name(str(r.get("player_name", ""))).strip().lower() == name_key)
            player_id = hit.get("player_id")

    if player_id is None:
        return {"status": "UNANSWERABLE", "player": _ascii_name(player),
                "missing": ["player found on NO verified axis claim (name mismatch, "
                             "or below every claim's floor)"],
                "edge_claimed": False}

    qualifies = player_id in qualified_ids
    # Durability/sample: raw sample sizes from the canonical composite claim's
    # own rows (games=n, fg3m, fg3a) -- a sample DESCRIPTION, not a ranked trait.
    durability: dict[str, Any] = {"status": "not_in_pool"}
    canonical = verified.get("nba_canonical_shooter_leaderboard_full_season_2024_25")
    if canonical is not None:
        c_hit = next(
            (r for r in canonical.get("ranking", [])
             if _ascii_name(str(r.get("player_name", ""))).strip().lower() == name_key),
            None,
        )
        if c_hit is not None:
            durability = {"status": "ok", "games": c_hit.get("n"),
                          "fg3m": c_hit.get("fg3m"), "fg3a": c_hit.get("fg3a"),
                          "claim_id": "nba_canonical_shooter_leaderboard_full_season_2024_25"}

    words = {
        "volume": band_word(_pct_for_band(entries, "fg3a_per_game", qualifies)),
        "efficiency": band_word(
            _pct_for_band(entries, "fg3_pct", qualifies) if qualifies
            else _pct_for_band(entries, "ts_pct", qualifies)
        ),
        "self_creation": band_word(_pct_for_band(entries, "unassisted_share_3pm", qualifies)),
        "gravity": band_word(_pct_for_band(entries, "gravity_score", qualifies)),
    }
    trait_line = (
        f"{words['volume']}-volume, {words['efficiency']}-efficiency shooter; "
        f"self-creation {words['self_creation']}, gravity {words['gravity']}"
    )

    return {
        "status": "OK",
        "player": _ascii_name(player),
        "player_id": player_id,
        "qualifies_fg3m82": qualifies,
        "axes": [entries[a.axis] for a in AXES],
        "durability": durability,
        "trait_line": trait_line,
        "trait_line_rule": TRAIT_LINE_RULE,
        "bands": list(BANDS),
        "unbuilt_axes": list(UNBUILT_AXES),
        "note": (
            "DESCRIPTIVE trait vector assembled from VERIFIED claims only -- axes are "
            "never combined into one score; no forecasting/market claim."
        ),
        "evidence": evidence,
        "edge_claimed": False,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="multi-axis shooter trait profile from VERIFIED claims")
    parser.add_argument("player")
    args = parser.parse_args(argv)
    result = compose_profile(args.player)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
