"""pack_manifest.py -- the ALLOWLIST for the shareable CourtVision data-pack.

This is an explicit ALLOWLIST (paths + globs), never a blocklist: only what is
named here can ever enter the pack. The FORBIDDEN rules below are a second,
fail-closed safety net -- a correctly-built pack never trips them; if one fires
it means a glob over-matched and the build MUST stop.

What ships: DESCRIPTIVE intelligence only -- validated claim families, profiles,
and the small derived/aggregate domain parquets the MCP resolvers read directly.

What never ships: betting ledgers / CLV / paper trades (data/frontend), scraped
odds (odds.parquet, line_history, odds_api, book_depth), the working vault, the
registry, and the multi-GB per-entity pointer stores (dropped by MAX_FILE_MB;
they degrade honestly to no_data).
"""
from __future__ import annotations

import re

# --- ALLOWLIST -------------------------------------------------------------
# Each entry: (root relative to repo, [glob patterns under that root]).
# Globs are non-recursive (a flat dir of family files), except EXPLICIT_FILES.
ALLOW_GLOBS: list[tuple[str, list[str]]] = [
    # Validated claim families: data jsonl + its index + its validation report,
    # plus the small aggregate snapshot parquets some families point at.
    ("data/cache/intel_claims", ["*.jsonl", "*.index.jsonl",
                                  "*_validation.json", "*.parquet"]),
    # Long-format player/team/lineup profiles (all sports incl. wnba).
    ("data/cache/profiles", ["*_profiles.parquet"]),
    # The single descriptive system map (present-only).
    ("data/cache/analytics_verify", ["system_map.json"]),
]

# Explicit derived/aggregate domain parquets the resolvers read directly
# (schedule, boxscores, matches, results, playstyles, injuries facts, referee
# foul rates). Raw scraped odds.parquet is deliberately NOT listed.
EXPLICIT_FILES: list[str] = [
    "data/domains/basketball_nba/espn_boxscores.parquet",
    "data/domains/basketball_nba/games.parquet",
    "data/domains/basketball_nba/linescores.parquet",
    "data/domains/basketball_nba/player_boxscores.parquet",
    "data/domains/mlb/edge_facts_injuries.parquet",
    "data/domains/mlb/games.parquet",
    "data/domains/mlb/games_current.parquet",
    "data/domains/mlb/player_gamelogs.parquet",
    "data/domains/mlb/probables.parquet",
    "data/domains/soccer/match_stats.parquet",
    "data/domains/soccer/matches.parquet",
    "data/domains/soccer_intl/results.parquet",
    "data/domains/tennis/asof_return.parquet",
    "data/domains/tennis/asof_setdetail.parquet",
    "data/domains/tennis/atlas_playstyles.parquet",
    "data/domains/tennis/matches.parquet",
    "data/domains/tennis/players.parquet",
    "data/domains/kbo/kbo_results.parquet",
    "data/domains/npb/npb_results.parquet",
    "data/domains/wnba/referee_crew_foul_rate.parquet",
]

# Intel-claims family stems carrying these substrings are dropped SILENTLY and
# degrade to no_data. "ledger" = descriptive analytics ledgers the honesty rail
# excludes by name from a shareable pack.
INTEL_EXCLUDE_SUBSTR: tuple[str, ...] = ("ledger",)

# Per-file ceiling. Drops the multi-GB per-entity pointer stores
# (nba_player_box_rate, mlb_batter_rate, mlb_pitcher_rate, ...) so the pack
# stays laptop-friendly; their families degrade to no_data.
MAX_FILE_MB: int = 50

# --- FORBIDDEN (fail-closed safety net; a good manifest never trips it) -----
# rel-path substrings that mark a private/betting/scraped-odds store.
FORBIDDEN_PATH_SUBSTR: tuple[str, ...] = (
    "/frontend/", "/line_history/", "/odds_api/", "/book_depth/",
    "/registry/", "/vault/", ".bot_state", "/clv/", "/paper/",
)
# rel-path suffixes never allowed (raw scraped odds).
FORBIDDEN_PATH_ENDS: tuple[str, ...] = ("odds.parquet",)
# basename substrings that mark a betting/paper artifact.
FORBIDDEN_NAME_SUBSTR: tuple[str, ...] = ("_clv", "clv_", "_paper", "paper_",
                                          "_pnl", "bankroll")
# secret-like KEYS/text in file content (mirrors export_snapshot.py).
SECRET_PATTERN = re.compile(r"(api[_-]?key|secret|password|bearer|access[_-]?token)",
                            re.IGNORECASE)
# content scan only for text files (parquet is binary aggregate data).
TEXT_SUFFIXES: tuple[str, ...] = (".json", ".jsonl", ".txt", ".md", ".csv")


def forbidden_reason(rel_path: str) -> str | None:
    """Return a reason string if rel_path violates a FORBIDDEN path/name rule,
    else None. Content is checked separately (needs the bytes)."""
    p = "/" + rel_path.replace("\\", "/").lstrip("/")
    for sub in FORBIDDEN_PATH_SUBSTR:
        if sub in p:
            return f"forbidden path segment {sub!r}"
    for end in FORBIDDEN_PATH_ENDS:
        if p.endswith(end):
            return f"forbidden suffix {end!r}"
    base = p.rsplit("/", 1)[-1].lower()
    for sub in FORBIDDEN_NAME_SUBSTR:
        if sub in base:
            return f"forbidden name token {sub!r}"
    return None
