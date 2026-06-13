"""domains.mlb.atlas_style_trends — MLB style-season trends atlas generator.

Reads games.parquet and computes, per season (2010-2021):
  - League run-scoring environment (runs/game, high-scoring rate, home-win rate,
    one-run game rate, game count)
  - Team-style distribution by season using the same archetype classifiers as
    atlas_playstyles._ARCHETYPES (min 20 games/season so every franchise appears)

Emits Obsidian Markdown into vault/Sports/MLB/Trends/:
  - _Style_Trends_Overview.md   — season-by-season environment table + trends
  - style_trends_<season>.md    — one per season with metrics + style breakdown

Public API: build_style_trends(out_dir, corpus_dir) -> list[Path]

No individual player names.  No betting/edge language.  Real data only.

Import contract (F5-clean): stdlib + pathlib + pandas + domains.mlb.* +
scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List

import pandas as pd

from domains.mlb.atlas_playstyles import _ARCHETYPES  # reuse classifiers
from domains.mlb.atlas_style_trends_render import render_overview, render_season_note
from scripts.platformkit.atlas.obsidian_emit import write_note

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "domains" / "mlb"
_DEFAULT_OUT = _REPO_ROOT / "vault" / "Sports" / "MLB" / "Trends"

_MIN_SEASON_GAMES = 20  # per team per season (handles shortened 2020)

# Derived from _ARCHETYPES — keep in sync
_ARCHETYPE_SLUGS: List[str] = [slug for slug, *_ in _ARCHETYPES]
_ARCHETYPE_NAMES: Dict[str, str] = {slug: name for slug, name, *_ in _ARCHETYPES}
_ARCHETYPE_SHORT: Dict[str, str] = {
    "power_run_scoring": "Power",
    "pitching_run_prevention": "Pitching",
    "balanced_contender": "Balanced",
    "high_variance_offense": "Hi-Var",
    "low_scoring_grinder": "Grinder",
    "run_deficit_rebuilding": "Deficit",
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_games(corpus_dir: pathlib.Path) -> pd.DataFrame:
    p = corpus_dir / "games.parquet"
    if not p.exists():
        raise FileNotFoundError(f"games.parquet not found in {corpus_dir}")
    return pd.read_parquet(p)


# ---------------------------------------------------------------------------
# Environment metrics (game-level, per season)
# ---------------------------------------------------------------------------


def _compute_env(games: pd.DataFrame) -> pd.DataFrame:
    """Return per-season league environment DataFrame.

    Columns: season, runs_per_game, high_score_rate, home_win_rate,
             one_run_rate, n_games
    """
    g = games.copy()
    g["total_runs"] = g["home_runs"] + g["away_runs"]
    g["high_scoring"] = (g["total_runs"] >= 10).astype(int)
    g["one_run"] = ((g["home_runs"] - g["away_runs"]).abs() == 1).astype(int)

    env = (
        g.groupby("season")
        .agg(
            runs_per_game=("total_runs", "mean"),
            high_score_rate=("high_scoring", "mean"),
            home_win_rate=("target_home_win", "mean"),
            one_run_rate=("one_run", "mean"),
            n_games=("total_runs", "count"),
        )
        .reset_index()
        .sort_values("season")
    )
    return env


# ---------------------------------------------------------------------------
# Per-team-season stats + style classification
# ---------------------------------------------------------------------------


def _compute_style_dist(games: pd.DataFrame) -> pd.DataFrame:
    """Return per-season style prevalence DataFrame.

    For each season: fraction of qualifying teams (>= _MIN_SEASON_GAMES) that
    satisfy each archetype classifier.  Columns: season, n_teams, <slug>_pct...
    """
    rows: List[Dict[str, Any]] = []
    for _, g in games.iterrows():
        s = int(g["season"])
        ht, at = str(g["home_team"]), str(g["away_team"])
        hr, ar = float(g["home_runs"]), float(g["away_runs"])
        hw = int(g["target_home_win"])
        rows.append({"season": s, "team": ht, "rs": hr, "ra": ar, "win": hw})
        rows.append({"season": s, "team": at, "rs": ar, "ra": hr, "win": 1 - hw})

    d = pd.DataFrame(rows)
    d["is_high"] = (d["rs"] >= 6).astype(int)
    d["is_one_run"] = ((d["rs"] - d["ra"]).abs() == 1).astype(int)

    agg = (
        d.groupby(["season", "team"])
        .agg(
            n=("win", "count"),
            rs=("rs", "mean"),
            ra=("ra", "mean"),
            rs_std=("rs", "std"),
            wp=("win", "mean"),
            high_score_rate=("is_high", "mean"),
            one_run_rate=("is_one_run", "mean"),
        )
        .reset_index()
    )
    agg["rd"] = agg["rs"] - agg["ra"]
    agg = agg[agg["n"] >= _MIN_SEASON_GAMES].copy()

    for slug, _name, _desc, _sig, classifier in _ARCHETYPES:
        agg[slug] = agg.apply(classifier, axis=1).astype(int)

    dist_rows: List[Dict[str, Any]] = []
    for season, sdf in agg.groupby("season"):
        n_teams = len(sdf)
        row: Dict[str, Any] = {"season": int(season), "n_teams": n_teams}
        for slug in _ARCHETYPE_SLUGS:
            row[f"{slug}_pct"] = float(sdf[slug].mean() * 100)
        dist_rows.append(row)

    return pd.DataFrame(dist_rows).sort_values("season").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_style_trends(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
) -> List[pathlib.Path]:
    """Generate MLB style-season trend notes from the real corpus.

    Parameters
    ----------
    out_dir:
        Directory to write notes into.  Created if absent.
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
    seasons = sorted(int(s) for s in games["season"].unique())
    corpus_span = f"{min(seasons)}-{max(seasons)}" if seasons else "n/a"

    env = _compute_env(games)
    dist = _compute_style_dist(games)

    written: List[pathlib.Path] = []

    # --- Overview note ---
    env_rows = env.to_dict("records")
    dist_records = dist.to_dict("records")
    overview_content = render_overview(
        corpus_span=corpus_span,
        env_rows=env_rows,
        dist_rows=dist_records,
        archetype_slugs=_ARCHETYPE_SLUGS,
        archetype_short=_ARCHETYPE_SHORT,
        min_season_games=_MIN_SEASON_GAMES,
    )
    overview_path = out_dir / "_Style_Trends_Overview.md"
    write_note(overview_path, overview_content)
    written.append(overview_path)

    # --- Per-season notes ---
    for season in seasons:
        env_mask = env["season"] == season
        dist_mask = dist["season"] == season
        if not env_mask.any() or not dist_mask.any():
            continue
        er = env[env_mask].iloc[0]
        dr = dist[dist_mask].iloc[0]
        style_pcts = {slug: float(dr[f"{slug}_pct"]) for slug in _ARCHETYPE_SLUGS}
        content = render_season_note(
            season=season,
            corpus_span=corpus_span,
            runs_per_game=float(er["runs_per_game"]),
            high_score_rate=float(er["high_score_rate"]),
            home_win_rate=float(er["home_win_rate"]),
            one_run_rate=float(er["one_run_rate"]),
            n_games=int(er["n_games"]),
            style_pcts=style_pcts,
            archetype_names=_ARCHETYPE_NAMES,
            archetype_slugs=_ARCHETYPE_SLUGS,
            min_season_games=_MIN_SEASON_GAMES,
        )
        note_path = out_dir / f"style_trends_{season}.md"
        write_note(note_path, content)
        written.append(note_path)

    return written
