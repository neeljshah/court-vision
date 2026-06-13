"""domains.soccer.atlas_scheme_transitions — Scheme-transition matrix atlas generator.

Classifies each team's tactical scheme PER SEASON (using the same priority-waterfall
as atlas_playstyles._classify), then tallies consecutive-season scheme(t)→scheme(t+1)
transitions across all teams in the corpus.

Emits into out_dir (default vault/Sports/Soccer/Scheme_Transitions/):

  _Scheme_Transitions_Index.md   — hub: summary counts, notable transitions, up-links
  Transition_Matrix.md           — ASCII table of P(to|from) with raw counts
  Stickiness.md                  — per-scheme "stays same scheme next season" rate
  Notable_Transitions.md         — largest off-diagonal flows

F5 compliance: imports ONLY stdlib + pandas + domains.soccer.*
No src.*, kernel.*, or sibling-domain imports.
All statistics are corpus-derived; no fabricated numbers, no edge/betting language.
Idempotent: re-running overwrites notes with identical content.

Renderers live in domains.soccer.atlas_scheme_transitions_render (≤300 LOC).
"""
from __future__ import annotations

import datetime
import pathlib
from collections import defaultdict
from typing import Dict, List, Tuple

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import write_note
from domains.soccer.atlas_playstyles import _SCHEMES, _classify
from domains.soccer.atlas_style_trends import _team_stats_for_slice

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "soccer"
)
_DEFAULT_OUT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2]
    / "vault" / "Sports" / "Soccer" / "Scheme_Transitions"
)
_MIN_MATCHES_SEASON: int = 10  # minimum appearances within a season for classification

_SCHEME_KEYS: List[str] = [s.key for s in _SCHEMES]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    path = corpus_dir / "matches.parquet"
    if not path.exists():
        raise FileNotFoundError(f"matches.parquet not found at {path}")
    df = pd.read_parquet(path)
    required = {"season", "div", "home_team", "away_team",
                "fthg", "ftag", "total_goals", "target_over25", "ftr"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"matches.parquet missing columns: {missing}")
    return df


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def _classify_teams_per_season(
    df: pd.DataFrame, min_matches: int
) -> Dict[int, Dict[str, str]]:
    """Return {season: {team: scheme_key}} for every qualified team-season pair."""
    result: Dict[int, Dict[str, str]] = {}
    for season in sorted(df["season"].unique()):
        s_df = df[df["season"] == season]
        team_stats = _team_stats_for_slice(s_df, min_matches)
        if team_stats.empty:
            result[int(season)] = {}
            continue
        season_map: Dict[str, str] = {}
        for _, row in team_stats.iterrows():
            season_map[str(row["team"])] = _classify(row)
        result[int(season)] = season_map
    return result


def _build_transition_counts(
    season_scheme_map: Dict[int, Dict[str, str]]
) -> Dict[str, Dict[str, int]]:
    """Tally scheme(t)→scheme(t+1) over all consecutive season pairs.

    Returns counts[from_scheme][to_scheme] = int.
    """
    counts: Dict[str, Dict[str, int]] = {
        k: {k2: 0 for k2 in _SCHEME_KEYS} for k in _SCHEME_KEYS
    }
    seasons = sorted(season_scheme_map.keys())
    for i in range(len(seasons) - 1):
        s_t = seasons[i]
        s_t1 = seasons[i + 1]
        map_t = season_scheme_map[s_t]
        map_t1 = season_scheme_map[s_t1]
        for team, scheme_from in map_t.items():
            if team in map_t1:
                scheme_to = map_t1[team]
                counts[scheme_from][scheme_to] += 1
    return counts


def _transition_probabilities(
    counts: Dict[str, Dict[str, int]]
) -> Dict[str, Dict[str, float]]:
    """Convert raw counts to row-normalised probabilities (P(to|from))."""
    probs: Dict[str, Dict[str, float]] = {}
    for from_key, to_counts in counts.items():
        row_total = sum(to_counts.values())
        if row_total == 0:
            probs[from_key] = {k: 0.0 for k in _SCHEME_KEYS}
        else:
            probs[from_key] = {k: v / row_total for k, v in to_counts.items()}
    return probs


def _stickiness(
    counts: Dict[str, Dict[str, int]]
) -> List[Tuple[str, float, int, int]]:
    """Return [(scheme_key, stick_rate, n_stays, n_total)] sorted desc by stick_rate."""
    rows: List[Tuple[str, float, int, int]] = []
    for key in _SCHEME_KEYS:
        to_counts = counts[key]
        total = sum(to_counts.values())
        stays = to_counts.get(key, 0)
        rate = stays / total if total > 0 else 0.0
        rows.append((key, rate, stays, total))
    return sorted(rows, key=lambda r: r[1], reverse=True)


def _notable_transitions(
    counts: Dict[str, Dict[str, int]],
    probs: Dict[str, Dict[str, float]],
    top_n: int = 5,
) -> List[Tuple[str, str, int, float]]:
    """Return top off-diagonal transitions by count: (from, to, count, prob)."""
    moves: List[Tuple[str, str, int, float]] = []
    for from_key in _SCHEME_KEYS:
        for to_key in _SCHEME_KEYS:
            if from_key == to_key:
                continue
            cnt = counts[from_key][to_key]
            if cnt > 0:
                moves.append((from_key, to_key, cnt, probs[from_key][to_key]))
    moves.sort(key=lambda r: r[2], reverse=True)
    return moves[:top_n]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_scheme_transitions(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
    *,
    min_matches: int = _MIN_MATCHES_SEASON,
) -> List[pathlib.Path]:
    """Generate Obsidian scheme-transition notes into *out_dir*.

    Parameters
    ----------
    out_dir:
        Destination directory; created if absent.  Idempotent.
    corpus_dir:
        Directory containing matches.parquet.
    min_matches:
        Minimum appearances within a season for a team to receive a
        scheme classification (default 10).

    Returns
    -------
    list[pathlib.Path]
        Paths of every written note (index + matrix + stickiness + notable).
    """
    from domains.soccer.atlas_scheme_transitions_render import (
        render_index,
        render_transition_matrix,
        render_stickiness,
        render_notable_transitions,
    )

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _load_matches(corpus_dir)
    n_corpus = len(df)
    seasons = sorted(df["season"].unique())
    generated = datetime.date.today().isoformat()

    season_scheme_map = _classify_teams_per_season(df, min_matches)
    counts = _build_transition_counts(season_scheme_map)
    probs = _transition_probabilities(counts)
    sticky = _stickiness(counts)
    notable = _notable_transitions(counts, probs)

    n_transitions = sum(
        v for row in counts.values() for v in row.values()
    )
    n_seasons = len(seasons)

    written: List[pathlib.Path] = []

    # Index
    idx_path = out_dir / "_Scheme_Transitions_Index.md"
    written.append(write_note(
        idx_path,
        render_index(sticky, notable, n_corpus, n_transitions, n_seasons, seasons, generated),
    ))

    # Transition matrix
    mat_path = out_dir / "Transition_Matrix.md"
    written.append(write_note(
        mat_path,
        render_transition_matrix(counts, probs, n_transitions, generated),
    ))

    # Stickiness
    stick_path = out_dir / "Stickiness.md"
    written.append(write_note(
        stick_path,
        render_stickiness(sticky, n_transitions, generated),
    ))

    # Notable transitions
    notable_path = out_dir / "Notable_Transitions.md"
    written.append(write_note(
        notable_path,
        render_notable_transitions(notable, counts, probs, generated),
    ))

    return written
