"""2025-26 (additive, same-store) sibling of context_shooting_claims.py.

Split into its own file so context_shooting_claims.py's 2024-25 rows stay
byte-stable and that module's LOC stays at its existing 300 cap. Reuses
every shared helper (snapshot builders, claim assembler, name lookup) from
that module; only the season and its own season-scoped snapshot names
differ. No atlas ingredient involved here at all (pure boxscore
groupby/diff arithmetic), so no degraded/approx variant is needed --
player_boxscores.parquet covers 2025-26 fully.

CLI: python -m domains.basketball_nba.context_shooting_claims_2025_26
  (regenerates the WHOLE store: 2024-25 unchanged rows + 2025-26 additive rows)
"""
from __future__ import annotations

from typing import Any

from domains.basketball_nba.context_shooting_claims import (
    _CLAIMS_OUT,
    _assemble_claim,
    _load_season_rows,
    _name_lookup,
    _write_snapshot,
    build_all_claims as build_2024_25_claims,
    build_rest_split_snapshot,
    build_team_context_snapshot,
    write_claims,
)

SEASON = "2025-26"


def build_team_context_claim(rows, names) -> dict[str, Any]:
    snap = build_team_context_snapshot(rows)
    keep = ["player_id", "team", "fg3_pct_vs_team_context", "player_fg3a", "team_other_fg3a"]
    write_cols = snap[keep].dropna(subset=["fg3_pct_vs_team_context"])
    path = _write_snapshot(write_cols, f"fg3_pct_vs_team_context_{SEASON.replace('-', '_')}")
    return _assemble_claim(
        write_cols, path, "fg3_pct_vs_team_context",
        {"player_fg3a": 100, "team_other_fg3a": 500}, names,
        "Which qualifying NBA players shoot 3s better than their own team's "
        f"shooting environment ({SEASON})?",
        ["fg3_pct_vs_team_context = player 3P% MINUS his team-excluding-player 3P% "
         "(the literal 'good shooter on a bad shooting team' number); positive means "
         "he shoots better than his own team's other players.",
         "One row PER (player, team) STINT within the season -- a player traded "
         "mid-season gets a SEPARATE value for each team, never blended across two "
         "different shooting environments."],
        has_team=True, season=SEASON,
    )


def build_team_share_claim(rows, names) -> dict[str, Any]:
    snap = build_team_context_snapshot(rows)
    keep = ["player_id", "team", "fg3a_share_of_team", "player_fg3a"]
    write_cols = snap[keep].dropna(subset=["fg3a_share_of_team"])
    path = _write_snapshot(write_cols, f"fg3a_share_of_team_{SEASON.replace('-', '_')}")
    return _assemble_claim(
        write_cols, path, "fg3a_share_of_team", {"player_fg3a": 100}, names,
        "Which qualifying NBA players take the largest share of their team's "
        f"3-point attempts while on the roster ({SEASON})?",
        ["fg3a_share_of_team = player's total 3PA divided by his team's total 3PA, "
         "for the games he was actually on that team (volume/role context, not "
         "efficiency).",
         "One row PER (player, team) STINT within the season -- see "
         "fg3_pct_vs_team_context's caveat for the same trade-handling rule."],
        has_team=True, season=SEASON,
    )


def build_rest_split_claim(rows, names) -> dict[str, Any]:
    snap = build_rest_split_snapshot(rows)
    keep = ["player_id", "fg3_pct_rest_split", "b2b_fg3a", "rest_fg3a"]
    write_cols = snap[keep].dropna(subset=["fg3_pct_rest_split"])
    path = _write_snapshot(write_cols, f"fg3_pct_rest_split_{SEASON.replace('-', '_')}")
    return _assemble_claim(
        write_cols, path, "fg3_pct_rest_split",
        {"b2b_fg3a": 30, "rest_fg3a": 30}, names,
        "Which qualifying NBA players shoot a different 3P% on the second night of "
        f"a back-to-back vs 2+ days rest ({SEASON})?",
        ["fg3_pct_rest_split = B2B 3P% MINUS 2+ rest-day 3P% (built straight off "
         "player_boxscores.parquet's own game-log `date` column -- no separate "
         "game-level table needed, no CORPUS_ABSENT case applies). Positive = "
         "shoots better on a back-to-back; sign is descriptive only, no direction "
         "of causation or edge implied.",
         "B2B = exactly a 1-day gap since that player's own PRIOR game this "
         "season; rest = 2+ day gap; a player's first game of the season has no "
         "prior gap and is excluded from both sides."],
        has_team=False, season=SEASON,
    )


def build_season_claims() -> list[dict[str, Any]]:
    """The 3 nba_context_shooting_* claims for 2025-26 only (additive rows)."""
    rows = _load_season_rows(SEASON)
    names = _name_lookup(rows)
    claims = [
        build_team_context_claim(rows, names),
        build_team_share_claim(rows, names),
        build_rest_split_claim(rows, names),
    ]
    claims.sort(key=lambda c: c["claim_id"])
    return claims


def build_all_claims() -> list[dict[str, Any]]:
    """2024-25 (unchanged, via the original module) + 2025-26 (additive)."""
    return build_2024_25_claims() + build_season_claims()


def main() -> int:
    claims = build_all_claims()
    out_path = write_claims(claims, _CLAIMS_OUT)
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
