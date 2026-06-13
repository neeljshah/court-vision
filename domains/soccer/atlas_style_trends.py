"""domains.soccer.atlas_style_trends — Obsidian scheme-season trends generator.

Computes how tactical-scheme prevalence and scoring metrics shift by season
across the corpus.  Emits into out_dir (default vault/Sports/Soccer/Trends/):

  _Style_Trends_Overview.md   — multi-season overview with ASCII table of
                                scheme-share + scoring metrics by season
  <Season>_scheme_snapshot.md — one note per season with scheme distribution

All classification uses the same 7-scheme priority waterfall defined in
atlas_playstyles._SCHEMES / _classify so notes stay consistent with the team
playstyle atlas.

F5 compliance: imports ONLY stdlib + pandas + domains.soccer.*
No src.*, kernel.*, or sibling-domain imports.
All statistics are corpus-derived; no fabricated numbers, no edge/betting language.
Idempotent: re-running overwrites notes with identical content.
"""
from __future__ import annotations

import datetime
import pathlib
from typing import Dict, List

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import write_note
from domains.soccer.atlas_playstyles import _SCHEMES, _classify

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "soccer"
)
_DEFAULT_OUT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2]
    / "vault" / "Sports" / "Soccer" / "Trends"
)
_MIN_MATCHES_SEASON: int = 10  # minimum appearances in a season for classification


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
# Per-season computation
# ---------------------------------------------------------------------------


def _team_stats_for_slice(slice_df: pd.DataFrame, min_matches: int) -> pd.DataFrame:
    """Compute per-team stats for a subset of matches (one season)."""
    all_teams = sorted(
        set(slice_df["home_team"].tolist()) | set(slice_df["away_team"].tolist())
    )
    rows: List[Dict] = []
    for team in all_teams:
        hm = slice_df[slice_df["home_team"] == team]
        aw = slice_df[slice_df["away_team"] == team]
        n = len(hm) + len(aw)
        if n < min_matches:
            continue
        n_h, n_a = len(hm), len(aw)
        gf_h = float(hm["fthg"].sum())
        gf_a = float(aw["ftag"].sum())
        ga_h = float(hm["ftag"].sum())
        ga_a = float(aw["fthg"].sum())
        over = int(hm["target_over25"].sum()) + int(aw["target_over25"].sum())
        cs = int((hm["ftag"] == 0).sum()) + int((aw["fthg"] == 0).sum())
        btts = (
            int(((hm["fthg"] > 0) & (hm["ftag"] > 0)).sum())
            + int(((aw["ftag"] > 0) & (aw["fthg"] > 0)).sum())
        )
        wins = int((hm["ftr"] == "H").sum()) + int((aw["ftr"] == "A").sum())
        draws = int((hm["ftr"] == "D").sum()) + int((aw["ftr"] == "D").sum())
        gf_h_pg = gf_h / n_h if n_h else 0.0
        gf_a_pg = gf_a / n_a if n_a else 0.0
        rows.append({
            "team": team, "n": n,
            "gf_pg": (gf_h + gf_a) / n,
            "ga_pg": (ga_h + ga_a) / n,
            "over_pct": over / n,
            "cs_pct": cs / n,
            "btts_pct": btts / n,
            "draw_pct": draws / n,
            "win_pct": wins / n,
            "ppg": (wins * 3 + draws) / n,
            "home_adv": gf_h_pg - gf_a_pg,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _scheme_shares(team_stats: pd.DataFrame) -> Dict[str, float]:
    """Return {scheme_key: fraction} for teams in team_stats."""
    if team_stats.empty:
        return {s.key: 0.0 for s in _SCHEMES}
    counts: Dict[str, int] = {s.key: 0 for s in _SCHEMES}
    for _, row in team_stats.iterrows():
        key = _classify(row)
        counts[key] = counts.get(key, 0) + 1
    n_total = max(sum(counts.values()), 1)
    return {k: v / n_total for k, v in counts.items()}


def _season_scoring(season_df: pd.DataFrame) -> Dict:
    """Goals/game, over-2.5 rate, home-win rate for one season slice."""
    n = len(season_df)
    if n == 0:
        return {"goals_pg": 0.0, "over25_rate": 0.0, "home_win_rate": 0.0,
                "n_matches": 0}
    return {
        "goals_pg": round(float(season_df["total_goals"].sum()) / n, 3),
        "over25_rate": round(float(season_df["target_over25"].sum()) / n, 3),
        "home_win_rate": round(float((season_df["ftr"] == "H").sum()) / n, 3),
        "n_matches": n,
    }


def _compute_trends(df: pd.DataFrame, min_matches: int) -> List[Dict]:
    """Return one record per season with scheme shares + scoring metrics."""
    records: List[Dict] = []
    for season in sorted(df["season"].unique()):
        s_df = df[df["season"] == season]
        team_stats = _team_stats_for_slice(s_df, min_matches)
        shares = _scheme_shares(team_stats)
        scoring = _season_scoring(s_df)
        records.append({
            "season": int(season),
            "n_teams_classified": len(team_stats),
            **shares,
            **scoring,
        })
    return records


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_style_trends(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
    *,
    min_matches: int = _MIN_MATCHES_SEASON,
) -> List[pathlib.Path]:
    """Generate Obsidian scheme-season trend notes into *out_dir*.

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
        Paths of every written note (overview + one per season).
    """
    from domains.soccer.atlas_style_trends_render import (
        render_overview,
        render_season_snapshot,
    )

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _load_matches(corpus_dir)
    records = _compute_trends(df, min_matches)
    generated = datetime.date.today().isoformat()
    n_corpus = len(df)

    written: List[pathlib.Path] = []

    # Overview note
    overview_path = out_dir / "_Style_Trends_Overview.md"
    written.append(write_note(overview_path, render_overview(records, generated, n_corpus)))

    # Per-season snapshot notes
    for r in records:
        note_path = out_dir / f"{r['season']}_scheme_snapshot.md"
        written.append(write_note(note_path, render_season_snapshot(r, generated)))

    return written
