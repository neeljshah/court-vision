"""domains.mlb.atlas_seasons — Per-season standings dimension for the MLB memory graph.

Reads the real corpus (games.parquet) and emits one Obsidian Markdown note per
season plus a _Seasons_Index.md hub, all under out_dir/Seasons/.

Public API::

    from pathlib import Path
    from domains.mlb.atlas_seasons import build_seasons
    paths = build_seasons(Path("vault/Sports/MLB/Seasons"))

All numbers are derived from real corpus data — no fabricated stats.
No betting/edge language: descriptive standings only.
Records are honest corpus regular-season counts (no playoff data).

Import contract (F5-clean): stdlib + pathlib + pandas + domains.mlb.* +
scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Tuple

import pandas as pd

from domains.mlb.config import resolve_league
from domains.mlb.atlas_seasons_render import render_season, render_seasons_index
from scripts.platformkit.atlas.obsidian_emit import write_note

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "domains" / "mlb"
_DEFAULT_OUT = _REPO_ROOT / "vault" / "Sports" / "MLB" / "Seasons"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_games(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load games.parquet; raise FileNotFoundError if absent."""
    p = corpus_dir / "games.parquet"
    if not p.exists():
        raise FileNotFoundError(f"games.parquet not found in {corpus_dir}")
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Standings computation
# ---------------------------------------------------------------------------

# One standings row per (season, team):
# (rank, team_code, W, L, win_pct, RS_per_game, RA_per_game, run_diff)
_StandingRow = Tuple[int, str, int, int, float, float, float, float]


def _compute_season_standings(games: pd.DataFrame) -> pd.DataFrame:
    """Build per-(season, team) standings from the game-level corpus.

    Returns a DataFrame with columns:
      season, team, league, W, L, win_pct, RS, RA, run_diff
    where RS/RA are *per-game* averages (runs scored / allowed).

    Each game contributes two rows — one for the home team, one for the away.
    """
    rows: List[Dict[str, Any]] = []
    for _, g in games.iterrows():
        ht = str(g["home_team"])
        at = str(g["away_team"])
        hr = float(g["home_runs"])
        ar = float(g["away_runs"])
        hw = int(g["target_home_win"])
        season = int(g["season"])
        hl = str(g["home_league"])
        try:
            al = resolve_league(at, season)
        except KeyError:
            al = "UNK"

        rows.append(dict(
            season=season, team=ht, league=hl,
            runs_for=hr, runs_against=ar, win=hw,
        ))
        rows.append(dict(
            season=season, team=at, league=al,
            runs_for=ar, runs_against=hr, win=1 - hw,
        ))

    df = pd.DataFrame(rows)
    agg = (
        df.groupby(["season", "team"])
        .agg(
            W=("win", "sum"),
            games=("win", "count"),
            RS=("runs_for", "mean"),
            RA=("runs_against", "mean"),
            league=("league", "first"),
        )
        .reset_index()
    )
    agg["L"] = agg["games"] - agg["W"]
    agg["win_pct"] = agg["W"] / agg["games"]
    agg["run_diff"] = agg["RS"] - agg["RA"]
    agg = agg.drop(columns=["games"])
    return agg


def _season_league_standings(
    season_df: pd.DataFrame,
    league: str,
) -> List[_StandingRow]:
    """Return ranked standings rows for one league in one season."""
    lg = season_df[season_df["league"] == league].copy()
    if lg.empty:
        return []
    lg = lg.sort_values("win_pct", ascending=False).reset_index(drop=True)
    result: List[_StandingRow] = []
    for rank_0, (_, row) in enumerate(lg.iterrows()):
        result.append((
            rank_0 + 1,
            str(row["team"]),
            int(row["W"]),
            int(row["L"]),
            float(row["win_pct"]),
            float(row["RS"]),
            float(row["RA"]),
            float(row["run_diff"]),
        ))
    return result


def _best_team(rows: List[_StandingRow]) -> Tuple[str, float]:
    """Return (team_code, win_pct) for the #1-ranked team, or ('', nan)."""
    if not rows:
        return ("", float("nan"))
    r = rows[0]  # already sorted descending by win_pct
    return (r[1], r[4])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_seasons(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
) -> List[pathlib.Path]:
    """Generate per-season standing Obsidian notes from the real MLB corpus.

    Parameters
    ----------
    out_dir:
        Directory to write notes into (default: vault/Sports/MLB/Seasons/).
        Created if absent.  Both ``<Season>.md`` notes and
        ``_Seasons_Index.md`` land directly here.
    corpus_dir:
        Directory containing ``games.parquet``
        (default: data/domains/mlb).

    Returns
    -------
    list[pathlib.Path]
        Absolute paths of every file written (idempotent).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    games = _load_games(corpus_dir)
    standings_df = _compute_season_standings(games)
    seasons = sorted(games["season"].unique().tolist())

    written: List[pathlib.Path] = []
    season_summaries: List[Dict[str, Any]] = []

    for season in seasons:
        season_df = standings_df[standings_df["season"] == season]
        total_games = int((games["season"] == season).sum())

        nl_rows = _season_league_standings(season_df, "NL")
        al_rows = _season_league_standings(season_df, "AL")

        nl_best_team, nl_best_wp = _best_team(nl_rows)
        al_best_team, al_best_wp = _best_team(al_rows)

        content = render_season(
            season=season,
            total_games=total_games,
            nl_rows=nl_rows,
            al_rows=al_rows,
            nl_best=nl_best_team,
            al_best=al_best_team,
        )
        path = out_dir / f"{season}.md"
        write_note(path, content)
        written.append(path)

        season_summaries.append(dict(
            season=season,
            total_games=total_games,
            nl_best=nl_best_team,
            nl_best_wp=nl_best_wp,
            al_best=al_best_team,
            al_best_wp=al_best_wp,
        ))

    # --- Seasons index note ---
    index_content = render_seasons_index(
        seasons=seasons,
        season_summaries=season_summaries,
    )
    index_path = out_dir / "_Seasons_Index.md"
    write_note(index_path, index_content)
    written.append(index_path)

    return written
