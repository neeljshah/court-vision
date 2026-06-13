"""domains.mlb.atlas_style_matchups — MLB tactical style-vs-style matchup matrix.

For each corpus game, looks up both teams' primary playstyle (first archetype
matched by the ordered _ARCHETYPES list), then tallies style-A(home) vs
style-B(away) outcomes: home-win rate, avg total runs, high-scoring rate.
Emits Obsidian Markdown into vault/Sports/MLB/Style_Matchups/.

Public API: build_style_matchups(out_dir, corpus_dir) -> list[Path]

Import contract (F5-clean): stdlib + pathlib + pandas + domains.mlb.* +
scripts.platformkit.atlas.obsidian_emit only.
No individual player names. No edge/betting language.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Tuple

import pandas as pd

from domains.mlb.atlas_playstyles import (
    _ARCHETYPES,
    _load_games,
    _compute_team_stats,
    _classify,
)
from domains.mlb.atlas_style_matchups_render import (
    render_pair_note,
    render_style_matchups_index,
)
from scripts.platformkit.atlas.obsidian_emit import write_note

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "domains" / "mlb"
_DEFAULT_OUT = _REPO_ROOT / "vault" / "Sports" / "MLB" / "Style_Matchups"

_MIN_PAIR_GAMES = 50        # pairs below this threshold are omitted from notes
_HIGH_TOTAL_THRESH = 10.0  # game total >= 10 runs is "high-scoring"

# Ordered slug list — used to assign a team's primary style (first match wins)
_SLUG_ORDER: List[str] = [slug for slug, *_ in _ARCHETYPES]
# Slug -> human name lookup
_SLUG_NAME: Dict[str, str] = {slug: name for slug, name, *_ in _ARCHETYPES}


# ---------------------------------------------------------------------------
# Primary-style assignment
# ---------------------------------------------------------------------------


def _build_primary_style_map(
    stats: pd.DataFrame, assignment: Dict[str, List[str]]
) -> Dict[str, str]:
    """Return {team_code: primary_style_slug}.

    Primary style = first archetype in _SLUG_ORDER that lists the team.
    Teams not assigned to any archetype get style 'unclassified'.
    """
    primary: Dict[str, str] = {}
    for team in stats.index:
        for slug in _SLUG_ORDER:
            if team in assignment.get(slug, []):
                primary[team] = slug
                break
        else:
            primary[team] = "unclassified"
    return primary


# ---------------------------------------------------------------------------
# Pair tally
# ---------------------------------------------------------------------------


def _tally_pairs(
    games: pd.DataFrame,
    primary: Dict[str, str],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Tally outcomes by (home_style, away_style) pairs.

    Returns {(home_slug, away_slug): {n, home_wins, total_runs, high_total}}.
    Only teams present in *primary* (i.e. those that cleared MIN_GAMES) are
    included; games involving untracked teams are skipped.
    """
    tallies: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for _, row in games.iterrows():
        ht = str(row["home_team"])
        at = str(row["away_team"])
        hs = primary.get(ht)
        as_ = primary.get(at)
        if hs is None or as_ is None:
            continue
        key = (hs, as_)
        if key not in tallies:
            tallies[key] = {"n": 0, "home_wins": 0, "total_runs": 0.0, "high_total": 0}
        hw = int(row["target_home_win"])
        total = float(row["home_runs"]) + float(row["away_runs"])
        tallies[key]["n"] += 1
        tallies[key]["home_wins"] += hw
        tallies[key]["total_runs"] += total
        tallies[key]["high_total"] += int(total >= _HIGH_TOTAL_THRESH)
    return tallies


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_style_matchups(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
) -> List[pathlib.Path]:
    """Generate Obsidian style-vs-style matchup matrix notes from the real MLB corpus.

    Parameters
    ----------
    out_dir:
        Directory to write notes into. Created if absent.
    corpus_dir:
        Directory containing ``games.parquet``.

    Returns
    -------
    list[pathlib.Path]
        Absolute paths of every file written (idempotent).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    games = _load_games(corpus_dir)
    stats = _compute_team_stats(games)
    assignment = _classify(stats)
    primary = _build_primary_style_map(stats, assignment)

    seasons = sorted(int(s) for s in games["season"].unique())
    corpus_span = f"{min(seasons)}-{max(seasons)}" if seasons else "n/a"

    tallies = _tally_pairs(games, primary)

    written: List[pathlib.Path] = []
    qualifying_pairs: List[Dict[str, Any]] = []

    for (hs, as_), counts in sorted(tallies.items()):
        n = counts["n"]
        if n < _MIN_PAIR_GAMES:
            continue
        home_win_rate = counts["home_wins"] / n
        avg_total = counts["total_runs"] / n
        high_rate = counts["high_total"] / n

        content = render_pair_note(
            home_slug=hs,
            away_slug=as_,
            home_name=_SLUG_NAME.get(hs, hs),
            away_name=_SLUG_NAME.get(as_, as_),
            n=n,
            home_win_rate=home_win_rate,
            avg_total=avg_total,
            high_rate=high_rate,
            high_total_thresh=_HIGH_TOTAL_THRESH,
            corpus_span=corpus_span,
        )
        note_path = out_dir / f"{hs}__vs__{as_}.md"
        write_note(note_path, content)
        written.append(note_path)

        qualifying_pairs.append(
            {
                "home_slug": hs,
                "away_slug": as_,
                "n": n,
                "home_win_rate": home_win_rate,
                "avg_total": avg_total,
                "high_rate": high_rate,
            }
        )

    # Sort pairs by game count descending for the index table
    qualifying_pairs.sort(key=lambda r: r["n"], reverse=True)

    index_content = render_style_matchups_index(
        pair_rows=qualifying_pairs,
        corpus_span=corpus_span,
        n_pairs=len(qualifying_pairs),
        min_games=_MIN_PAIR_GAMES,
    )
    index_path = out_dir / "_Style_Matchups_Index.md"
    write_note(index_path, index_content)
    written.append(index_path)

    return written
