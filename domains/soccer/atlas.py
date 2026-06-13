"""domains.soccer.atlas — Obsidian intelligence-atlas generator for soccer.

Reads the football-data.co.uk corpus (matches.parquet) and emits a linked
Obsidian note graph into *out_dir*:

  _Index.md         — hub: corpus span, league table, top teams
  Teams/<Team>.md   — one note per team with >=30 corpus appearances
  Leagues/<Div>.md  — one note per league division

F5 compliance: imports ONLY stdlib + pandas + domains.soccer.*
No src.*, kernel.*, or sibling-domain imports.
All statistics are corpus-derived — no fabricated numbers, no edge language.
"""
from __future__ import annotations

import pathlib
from collections import Counter
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.soccer.config import LEAGUES  # div → display name
from scripts.platformkit.atlas.obsidian_emit import slug as _slug, write_note

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "soccer"
)
_MIN_MATCHES: int = 30       # minimum appearances for a team note
_TOP_TEAMS_PER_LEAGUE: int = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load and validate matches.parquet."""
    path = corpus_dir / "matches.parquet"
    if not path.exists():
        raise FileNotFoundError(f"matches.parquet not found at {path}")
    df = pd.read_parquet(path)
    required = {"date", "season", "div", "home_team", "away_team",
                "fthg", "ftag", "total_goals", "target_over25", "ftr"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"matches.parquet missing columns: {missing}")
    df["date"] = pd.to_datetime(df["date"])
    return df


def _league_display(div: str) -> str:
    return LEAGUES.get(div, div)


# ---------------------------------------------------------------------------
# Per-team statistics
# ---------------------------------------------------------------------------


def _team_stats(df: pd.DataFrame, team: str) -> Dict:
    """Return a dict of corpus statistics for *team*."""
    home = df[df["home_team"] == team]
    away = df[df["away_team"] == team]
    n_home, n_away = len(home), len(away)
    n_total = n_home + n_away

    hw = int((home["ftr"] == "H").sum()); hd = int((home["ftr"] == "D").sum())
    aw = int((away["ftr"] == "A").sum()); ad = int((away["ftr"] == "D").sum())
    wins = hw + aw; draws = hd + ad; losses = n_total - wins - draws
    pts = wins * 3 + draws

    gf_home = float(home["fthg"].sum()); ga_home = float(home["ftag"].sum())
    gf_away = float(away["ftag"].sum()); ga_away = float(away["fthg"].sum())

    over_total = int(home["target_over25"].sum()) + int(away["target_over25"].sum())
    cs = int((home["ftag"] == 0).sum()) + int((away["fthg"] == 0).sum())
    btts = (int(((home["fthg"] > 0) & (home["ftag"] > 0)).sum()) +
            int(((away["ftag"] > 0) & (away["fthg"] > 0)).sum()))

    mask = df["home_team"].eq(team) | df["away_team"].eq(team)
    all_divs = sorted(set(home["div"].tolist()) | set(away["div"].tolist()))
    seasons = sorted(df[mask]["season"].unique().tolist())

    recent_season = max(seasons) if seasons else None
    if recent_season is not None:
        rec = df[mask & (df["season"] == recent_season)]
        rh = rec[rec["home_team"] == team]; ra = rec[rec["away_team"] == team]
        r_w = int((rh["ftr"] == "H").sum()) + int((ra["ftr"] == "A").sum())
        r_d = int((rh["ftr"] == "D").sum()) + int((ra["ftr"] == "D").sum())
        rn = len(rec); r_pts = r_w * 3 + r_d; r_l = rn - r_w - r_d
    else:
        rn = r_w = r_d = r_l = r_pts = 0

    top_opps = [t for t, _ in Counter(
        home["away_team"].tolist() + away["home_team"].tolist()
    ).most_common(6)]

    def _safe(num: float, den: int) -> float:
        return round(num / den, 3) if den else 0.0

    return {
        "team": team, "n_total": n_total, "n_home": n_home, "n_away": n_away,
        "wins": wins, "draws": draws, "losses": losses, "pts": pts,
        "ppg": _safe(pts, n_total),
        "gf_pg": _safe(gf_home + gf_away, n_total),
        "ga_pg": _safe(ga_home + ga_away, n_total),
        "gf_home_pg": _safe(gf_home, n_home), "ga_home_pg": _safe(ga_home, n_home),
        "gf_away_pg": _safe(gf_away, n_away), "ga_away_pg": _safe(ga_away, n_away),
        "over25_pct": _safe(over_total, n_total),
        "cs_pct": _safe(cs, n_total), "btts_pct": _safe(btts, n_total),
        "divs": all_divs, "seasons": seasons, "recent_season": recent_season,
        "recent_n": rn, "recent_wins": r_w, "recent_draws": r_d,
        "recent_losses": r_l, "recent_pts": r_pts, "top_opponents": top_opps,
    }


# ---------------------------------------------------------------------------
# Per-league statistics
# ---------------------------------------------------------------------------


def _league_stats(df: pd.DataFrame, div: str) -> Dict:
    """Return corpus stats for one division code."""
    sub = df[df["div"] == div]
    n = len(sub)
    seasons = sorted(sub["season"].unique().tolist())

    team_ppg: List[Tuple[str, float]] = []
    for t in set(sub["home_team"].unique()) | set(sub["away_team"].unique()):
        th = sub[sub["home_team"] == t]; ta = sub[sub["away_team"] == t]
        m = len(th) + len(ta)
        if m < 10:
            continue
        w = int((th["ftr"] == "H").sum()) + int((ta["ftr"] == "A").sum())
        d = int((th["ftr"] == "D").sum()) + int((ta["ftr"] == "D").sum())
        team_ppg.append((t, round((w * 3 + d) / m, 3)))

    return {
        "div": div, "display": _league_display(div), "n_matches": n,
        "avg_goals": round(float(sub["total_goals"].mean()) if n else 0.0, 3),
        "over25_rate": round(float(sub["target_over25"].mean()) if n else 0.0, 3),
        "home_win_pct": round(float((sub["ftr"] == "H").mean()) if n else 0.0, 3),
        "draw_pct": round(float((sub["ftr"] == "D").mean()) if n else 0.0, 3),
        "away_win_pct": round(float((sub["ftr"] == "A").mean()) if n else 0.0, 3),
        "seasons": seasons,
        "top_teams": sorted(team_ppg, key=lambda x: -x[1])[:_TOP_TEAMS_PER_LEAGUE],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_atlas(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
    *,
    min_matches: int = _MIN_MATCHES,
) -> List[pathlib.Path]:
    """Generate the Obsidian soccer intelligence-atlas into *out_dir*.

    Parameters
    ----------
    out_dir:     Destination directory; created if absent. Idempotent.
    corpus_dir:  Contains matches.parquet. Defaults to data/domains/soccer/.
    min_matches: Minimum appearances for a team note (default 30).

    Returns
    -------
    list[pathlib.Path]  Paths of every written note.
    """
    from domains.soccer.atlas_render import render_index, render_team, render_league

    out_dir = pathlib.Path(out_dir)
    (out_dir / "Teams").mkdir(parents=True, exist_ok=True)
    (out_dir / "Leagues").mkdir(parents=True, exist_ok=True)

    df = _load_matches(corpus_dir)
    divs = sorted(df["div"].unique().tolist())
    league_rows = [_league_stats(df, d) for d in divs]

    all_teams = sorted(set(df["home_team"].tolist()) | set(df["away_team"].tolist()))
    team_stats_list = []
    for t in all_teams:
        n = int((df["home_team"] == t).sum()) + int((df["away_team"] == t).sum())
        if n >= min_matches:
            team_stats_list.append(_team_stats(df, t))
    team_stats_list.sort(key=lambda x: -x["ppg"])

    team_slugs: Dict[str, str] = {s["team"]: _slug(s["team"]) for s in team_stats_list}
    written: List[pathlib.Path] = []

    # Index
    idx = out_dir / "_Index.md"
    written.append(write_note(idx, render_index(df, league_rows, team_stats_list[:20])))

    # Team notes
    for s in team_stats_list:
        p = out_dir / "Teams" / f"{_slug(s['team'])}.md"
        written.append(write_note(p, render_team(s)))

    # League notes
    for ls in league_rows:
        p = out_dir / "Leagues" / f"{_slug(ls['display'])}.md"
        written.append(write_note(p, render_league(ls, team_slugs)))

    return written
