"""domains.mlb.atlas_home_environment — Per-team home run-environment atlas.

Proxy disclaimer: numbers reflect roster quality AND park effects together.
We do not disentangle them — treat as a roster+park proxy, not pure park factor.

Public API::

    from pathlib import Path
    from domains.mlb.atlas_home_environment import build_home_environment
    paths = build_home_environment(out_dir, corpus_dir=Path("data/domains/mlb"))

Import contract (F5-clean): stdlib + pathlib + pandas + numpy +
scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import math
import pathlib
from typing import Any, Dict, List, Tuple

import numpy as np  # noqa: F401 (available for callers)
import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import frontmatter as _fm_dict, write_note

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "domains" / "mlb"
_DEFAULT_OUT = _REPO_ROOT / "vault" / "Sports" / "MLB" / "Home_Environment"
_MIN_HOME_GAMES = 100       # minimum home games to include a team
_HIGH_SCORE_THRESHOLD = 9   # total runs > this = "high-scoring game"


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _ff(v: float, d: int = 2) -> str:
    return "n/a" if (v is None or (isinstance(v, float) and math.isnan(v))) else f"{v:.{d}f}"

def _pct(v: float, d: int = 1) -> str:
    return "n/a" if (v is None or (isinstance(v, float) and math.isnan(v))) else f"{v*100:.{d}f}%"

def _sign(v: float) -> str:
    return "n/a" if (v is None or (isinstance(v, float) and math.isnan(v))) else (f"+{v:.2f}" if v >= 0 else f"{v:.2f}")


# ---------------------------------------------------------------------------
# Data loading + computation
# ---------------------------------------------------------------------------

def _load_games(corpus_dir: pathlib.Path) -> pd.DataFrame:
    p = corpus_dir / "games.parquet"
    if not p.exists():
        raise FileNotFoundError(f"games.parquet not found in {corpus_dir}")
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _compute_environments(games: pd.DataFrame) -> pd.DataFrame:
    """Return per-team home vs away run environment, sorted by home_total_rpg desc."""
    games = games.copy()
    games["total_runs"] = games["home_runs"] + games["away_runs"]
    games["high_scoring"] = (games["total_runs"] > _HIGH_SCORE_THRESHOLD).astype(int)

    home_agg = (
        games.groupby("home_team")
        .agg(
            home_games=("total_runs", "count"),
            home_total_rpg=("total_runs", "mean"),
            home_team_rpg=("home_runs", "mean"),
            home_allowed_rpg=("away_runs", "mean"),
            home_high_pct=("high_scoring", "mean"),
        )
        .reset_index()
        .rename(columns={"home_team": "team"})
    )

    away_agg = (
        games.groupby("away_team")
        .agg(
            away_games=("total_runs", "count"),
            away_total_rpg=("total_runs", "mean"),
            away_team_rpg=("away_runs", "mean"),
            away_allowed_rpg=("home_runs", "mean"),
            away_high_pct=("high_scoring", "mean"),
        )
        .reset_index()
        .rename(columns={"away_team": "team"})
    )

    merged = home_agg.merge(away_agg, on="team", how="inner")
    merged = merged[merged["home_games"] >= _MIN_HOME_GAMES].copy()
    merged["home_boost"] = merged["home_total_rpg"] - merged["away_total_rpg"]
    merged["high_scoring_boost"] = merged["home_high_pct"] - merged["away_high_pct"]
    merged["rank"] = merged["home_total_rpg"].rank(ascending=False, method="min").astype(int)
    merged = merged.sort_values("home_total_rpg", ascending=False).reset_index(drop=True)
    return merged


_TIER_BOUNDS: List[Tuple[float, str]] = [
    (10.5, "hitter-friendly (top)"),
    (9.5,  "above-average run environment"),
    (8.5,  "near-average run environment"),
    (7.5,  "below-average run environment"),
    (0.0,  "pitcher-friendly"),
]


def _tier(rpg: float) -> str:
    for bound, label in _TIER_BOUNDS:
        if rpg >= bound:
            return label
    return "pitcher-friendly"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_ranked_note(rows: pd.DataFrame, season_span: str) -> str:
    lines = [
        _fm_dict({
            "sport": "mlb", "note_type": "home_environment", "season_span": season_span,
            "teams": len(rows), "disclaimer": "roster+park proxy — not a pure park factor",
            "tags": ["sport/mlb", "home-environment", "run-environment"],
        }),
        "",
        "# MLB Home Run-Environment Rankings",
        "",
        "up:: [[_Index]]",
        "",
        f"Per-team home vs away run environment ({season_span}).  "
        "**Proxy disclaimer**: reflects roster quality *and* park effects — "
        "not disentangled.  Do not use as a pure park factor.",
        "",
        f"High-scoring game: total runs > {_HIGH_SCORE_THRESHOLD}. "
        f"Min home games: {_MIN_HOME_GAMES}.",
        "",
        "## Ranked Table",
        "",
        "| Rank | Team | Home RPG | Away RPG | Boost | High-Scoring Home% | Tier |",
        "|------|------|----------|----------|-------|--------------------|------|",
    ]
    for _, r in rows.iterrows():
        team_link = f"[[Teams/{r['team']}]]"
        lines.append(
            f"| {int(r['rank'])} | {team_link} | {_ff(r['home_total_rpg'])} "
            f"| {_ff(r['away_total_rpg'])} | {_sign(r['home_boost'])} "
            f"| {_pct(r['home_high_pct'])} | {_tier(r['home_total_rpg'])} |"
        )

    # Top 5 / bottom 5 callouts
    top5 = rows.head(5)
    bot5 = rows.tail(5)

    lines += [
        "",
        "## Top 5 — Highest Home Run Environments",
        "",
    ]
    for _, r in top5.iterrows():
        lines.append(
            f"- **[[Teams/{r['team']}]]** — {_ff(r['home_total_rpg'])} RPG at home "
            f"(away {_ff(r['away_total_rpg'])}, boost {_sign(r['home_boost'])}; "
            f"{_pct(r['home_high_pct'])} high-scoring home games)"
        )

    lines += [
        "",
        "## Bottom 5 — Lowest Home Run Environments",
        "",
    ]
    for _, r in bot5.iterrows():
        lines.append(
            f"- **[[Teams/{r['team']}]]** — {_ff(r['home_total_rpg'])} RPG at home "
            f"(away {_ff(r['away_total_rpg'])}, boost {_sign(r['home_boost'])}; "
            f"{_pct(r['home_high_pct'])} high-scoring home games)"
        )

    lines += [
        "",
        "## Methodology Notes",
        "",
        "- **Home total RPG**: average (home_runs + away_runs) per game played at home.",
        "- **Away total RPG**: average total runs per game when the team plays away.",
        "- **Boost**: home total RPG − away total RPG.  Positive = more scoring at home.",
        f"- **High-scoring%**: fraction of games with total runs > {_HIGH_SCORE_THRESHOLD}.",
        "- **Proxy disclaimer**: home run environment = roster quality + park effects.",
        "  We cannot separate them from this dataset alone.",
        "- Corpus: MLB 2010–2021, sportsbookreviewsonline archive.",
        "",
        "#sport/mlb #home-environment #run-environment",
    ]
    return "\n".join(lines) + "\n"


def _render_index(n_teams: int, season_span: str) -> str:
    lines = [
        _fm_dict({"sport": "mlb", "note_type": "home_environment_index",
                  "season_span": season_span, "tags": ["sport/mlb", "home-environment"]}),
        "",
        "# Home_Environment — Index",
        "",
        "up:: [[_Index]]",
        "",
        f"Home run-environment notes for {n_teams} MLB teams ({season_span}).",
        "",
        "| Note | Description |",
        "|------|-------------|",
        "| [[Home_Environment/MLB_Home_Environment_Rankings]] "
        "| All-team ranked table with home vs away RPG, boost, high-scoring split |",
        "",
        "#sport/mlb #home-environment",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_home_environment(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
) -> List[pathlib.Path]:
    """Build the MLB home run-environment atlas.  Raises FileNotFoundError if
    games.parquet is missing from corpus_dir.  Returns list[Path] of notes written."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    games = _load_games(pathlib.Path(corpus_dir))
    rows = _compute_environments(games)

    seasons = sorted(games["season"].dropna().unique().astype(int))
    season_span = f"{seasons[0]}–{seasons[-1]}" if seasons else "n/a"

    written: List[pathlib.Path] = []

    # Ranked note
    ranked_path = out_dir / "MLB_Home_Environment_Rankings.md"
    write_note(ranked_path, _render_ranked_note(rows, season_span))
    written.append(ranked_path)

    # Index note
    index_path = out_dir / "_Home_Environment_Index.md"
    write_note(index_path, _render_index(len(rows), season_span))
    written.append(index_path)

    return written
