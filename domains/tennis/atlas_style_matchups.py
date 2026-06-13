"""domains.tennis.atlas_style_matchups — Style-vs-style (archetype) matchup matrix.

Assigns each player in the real corpus to the SAME archetype as atlas_playstyles.py
(reusing _compute_stats + _assign_archetypes logic), tallies archetype-A vs
archetype-B outcomes across all matches, and emits Obsidian notes to:

    vault/Sports/Tennis/Style_Matchups/
        _Style_Matchups_Index.md
        <ArchetypeA>_vs_<ArchetypeB>.md   (pairs with ≥ MIN_PAIR_MEETINGS matches)

F5-clean: stdlib + numpy + pandas + domains.tennis.* only.
No edge / betting language. No individual player names in emitted notes.
Sackmann data CC BY-NC-SA — private research use only.

Public API
----------
build_style_matchups(out_dir, corpus_dir=<repo>/data/domains/tennis)
    -> list[pathlib.Path]
"""
from __future__ import annotations

import pathlib
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.tennis.atlas_playstyle_specs import (
    ARCHETYPES, ArchetypeSpec,
    ALL_COURT_MAX_SPREAD, CLAY_SPECIALIST_DELTA, GS_DELTA,
    GRASS_SPECIALIST_DELTA, HARD_SPECIALIST_DELTA, HEIGHT_BIG_SERVER,
)
from domains.tennis.atlas_playstyles import _compute_stats, _ok

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_CORPUS: pathlib.Path = _REPO_ROOT / "data" / "domains" / "tennis"
DEFAULT_OUT: pathlib.Path = _REPO_ROOT / "vault" / "Sports" / "Tennis" / "Style_Matchups"

MIN_PAIR_MEETINGS: int = 30  # minimum archetype-pair meetings to emit a note


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_corpus(corpus_dir: pathlib.Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    matches = pd.read_parquet(corpus_dir / "matches.parquet").copy()
    matches["date"] = matches["date"].astype(str)
    pp = corpus_dir / "players.parquet"
    players = (
        pd.read_parquet(pp) if pp.exists()
        else pd.DataFrame(columns=["player_id", "full_name", "hand", "height"])
    )
    return matches, players


# ---------------------------------------------------------------------------
# Archetype assignment: player_id -> slug (mirrors _assign_archetypes exactly)
# ---------------------------------------------------------------------------

def _assign_player_archetypes(stats: pd.DataFrame) -> Dict[int, str]:
    """Return {player_id: archetype_slug} using the same priority rules as atlas_playstyles."""
    if stats.empty:
        return {}
    median_ov = stats["ov_wr"].median()
    result: Dict[int, str] = {}

    for _, r in stats.iterrows():
        pid = int(r["player_id"])
        ov = float(r["ov_wr"])
        hw = r.get("hard_wr"); cw = r.get("clay_wr"); gw = r.get("grass_wr")
        b5 = r.get("bo5_wr"); b3 = r.get("bo3_wr")
        ht = r.get("height"); hand = str(r.get("hand", "U"))

        if _ok(cw) and float(cw) - ov >= CLAY_SPECIALIST_DELTA and (  # type: ignore[arg-type]
                not _ok(hw) or float(cw) > float(hw)) and (  # type: ignore[arg-type]
                not _ok(gw) or float(cw) > float(gw)):  # type: ignore[arg-type]
            slug = "Clay_Court_Specialist"
        elif _ok(ht) and float(ht) >= HEIGHT_BIG_SERVER and (  # type: ignore[arg-type]
                (_ok(hw) and float(hw) - ov >= HARD_SPECIALIST_DELTA) or  # type: ignore[arg-type]
                (_ok(gw) and _ok(cw) and float(gw) > float(cw))):  # type: ignore[arg-type]
            slug = "Fast_Court_Big_Server"
        elif hand == "L":
            slug = "Left_Handed_Specialist"
        elif _ok(b5) and _ok(b3) and float(b5) - float(b3) >= GS_DELTA:  # type: ignore[arg-type]
            slug = "Grand_Slam_Performer"
        elif _ok(hw) and float(hw) - ov >= HARD_SPECIALIST_DELTA and (  # type: ignore[arg-type]
                not _ok(cw) or float(hw) > float(cw)):  # type: ignore[arg-type]
            slug = "Hard_Court_Specialist"
        elif _ok(gw) and float(gw) - ov >= GRASS_SPECIALIST_DELTA and (  # type: ignore[arg-type]
                not _ok(cw) or float(gw) > float(cw)):  # type: ignore[arg-type]
            slug = "Grass_Court_Specialist"
        else:
            wrs = [x for x in [hw, cw, gw] if _ok(x)]
            if (len(wrs) == 3 and (max(wrs) - min(wrs)) < ALL_COURT_MAX_SPREAD  # type: ignore[type-var]
                    and ov >= median_ov):
                slug = "All_Court_Baseliner"
            else:
                slug = "Journeyman"

        result[pid] = slug

    return result


# ---------------------------------------------------------------------------
# Tally archetype-pair outcomes
# ---------------------------------------------------------------------------

def _canonical_pair(slug_a: str, slug_b: str) -> Tuple[str, str]:
    """Lexicographically ordered pair so slug_A ≤ slug_B."""
    return (slug_a, slug_b) if slug_a <= slug_b else (slug_b, slug_a)


def _tally_matchups(
    matches: pd.DataFrame,
    pid_to_slug: Dict[int, str],
) -> Dict[Tuple[str, str], Dict]:
    """Tally wins for each (slug_A, slug_B) pair across all corpus matches.

    Returns dict: pair -> {total, wins_a, surfaces: {surf: {total, wins_a}}}.
    A-side is always the lexicographically first slug in the canonical pair.
    """
    tallies: Dict[Tuple[str, str], Dict] = defaultdict(
        lambda: {"total": 0, "wins_a": 0,
                 "surfaces": defaultdict(lambda: {"total": 0, "wins_a": 0})}
    )
    for _, row in matches.iterrows():
        try:
            p1_id = int(row["p1_id"]); p2_id = int(row["p2_id"])
        except (TypeError, ValueError, KeyError):
            continue
        if p1_id not in pid_to_slug or p2_id not in pid_to_slug:
            continue
        slug1 = pid_to_slug[p1_id]; slug2 = pid_to_slug[p2_id]
        pair = _canonical_pair(slug1, slug2)
        a_is_p1 = slug1 == pair[0] if slug1 != slug2 else True
        winner = int(row["winner"])
        a_won = (winner == 1 and a_is_p1) or (winner == 2 and not a_is_p1)
        surf = str(row.get("surface", "Unknown"))
        tallies[pair]["total"] += 1
        tallies[pair]["wins_a"] += int(a_won)
        tallies[pair]["surfaces"][surf]["total"] += 1
        tallies[pair]["surfaces"][surf]["wins_a"] += int(a_won)
    return dict(tallies)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _slug_map() -> Dict[str, ArchetypeSpec]:
    return {s.slug: s for s in ARCHETYPES}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_style_matchups(
    out_dir: pathlib.Path,
    corpus_dir: Optional[pathlib.Path] = None,
    *,
    _matches_df: Optional[pd.DataFrame] = None,
    _players_df: Optional[pd.DataFrame] = None,
) -> List[pathlib.Path]:
    """Build the style-vs-style matchup matrix and emit Obsidian notes.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted. Created if missing.
    corpus_dir:
        Path to data/domains/tennis/. Defaults to repo-relative default.
    _matches_df / _players_df:
        Optional DataFrame overrides for unit tests (no filesystem reads).

    Returns
    -------
    list[pathlib.Path]
        All written note files (pair notes + index, index last).
    """
    from domains.tennis.atlas_style_matchups_render import render_pair_note, render_index

    if corpus_dir is None:
        corpus_dir = DEFAULT_CORPUS
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if _matches_df is not None:
        matches = _matches_df.copy()
        players = _players_df if _players_df is not None else pd.DataFrame(
            columns=["player_id", "full_name", "hand", "height"]
        )
    else:
        matches, players = _load_corpus(pathlib.Path(corpus_dir))

    matches["date"] = matches["date"].astype(str)

    stats = _compute_stats(matches, players)
    pid_to_slug = _assign_player_archetypes(stats)
    tallies = _tally_matchups(matches, pid_to_slug)

    sm = _slug_map()
    qualified: List[Tuple[Tuple[str, str], Dict]] = [
        (pair, tally) for pair, tally in tallies.items()
        if tally["total"] >= MIN_PAIR_MEETINGS and pair[0] in sm and pair[1] in sm
    ]

    written: List[pathlib.Path] = [
        render_pair_note(pair, tally, out_dir, sm)
        for pair, tally in qualified
    ]
    written.append(render_index(
        qualified,
        total_matches=len(matches),
        total_players=len(pid_to_slug),
        min_pair_meetings=MIN_PAIR_MEETINGS,
        out_dir=out_dir,
        slug_map=sm,
    ))
    return written
