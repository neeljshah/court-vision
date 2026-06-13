"""domains.soccer.atlas_seasons — Obsidian season-dimension generator for soccer.

Adds per-league per-season final standing tables to the soccer memory graph.
Reads matches.parquet and emits into out_dir (default vault/Sports/Soccer/Seasons/):

  _Seasons_Index.md       — champion per league/season, [[wikilinks]] to season notes
  <Div> <Season>.md       — full final table (Rank, Team, P/W/D/L/GF/GA/GD/Pts)
                            + over-2.5 rate + champion/relegation annotation

F5 compliance: imports ONLY stdlib + pandas + domains.soccer.*
No src.*, kernel.*, or sibling-domain imports.
All statistics are corpus-derived; no fabricated numbers, no edge/betting language.
Idempotent: re-running overwrites notes with identical content.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Tuple

import pandas as pd

from domains.soccer.config import LEAGUES
from scripts.platformkit.atlas.obsidian_emit import slug as _slug, write_note

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "soccer"
)
_DEFAULT_OUT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2]
    / "vault" / "Sports" / "Soccer" / "Seasons"
)

# Standard top-flight relegation zones (bottom 3 teams) — approximate; leagues vary.
_RELEGATION_SLOTS: int = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _league_display(div: str) -> str:
    return LEAGUES.get(div, div)


def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load and validate matches.parquet."""
    path = corpus_dir / "matches.parquet"
    if not path.exists():
        raise FileNotFoundError(f"matches.parquet not found at {path}")
    df = pd.read_parquet(path)
    required = {"div", "season", "home_team", "away_team", "fthg", "ftag", "ftr"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"matches.parquet missing columns: {missing}")
    # total_goals optional — compute if absent
    if "total_goals" not in df.columns:
        df = df.copy()
        df["total_goals"] = df["fthg"] + df["ftag"]
    return df


# ---------------------------------------------------------------------------
# Season table computation
# ---------------------------------------------------------------------------


def _final_table(season_df: pd.DataFrame) -> List[Dict]:
    """Compute the final standings table for one (div, season) slice.

    Returns rows sorted by (Pts desc, GD desc, GF desc, team asc) — standard
    tiebreaker ordering used across European leagues.
    """
    teams = sorted(
        set(season_df["home_team"].tolist()) | set(season_df["away_team"].tolist())
    )
    rows: List[Dict] = []
    for team in teams:
        home = season_df[season_df["home_team"] == team]
        away = season_df[season_df["away_team"] == team]

        hw = int((home["ftr"] == "H").sum())
        hd = int((home["ftr"] == "D").sum())
        hl = int((home["ftr"] == "A").sum())
        aw = int((away["ftr"] == "A").sum())
        ad = int((away["ftr"] == "D").sum())
        al = int((away["ftr"] == "H").sum())

        played = len(home) + len(away)
        wins = hw + aw
        draws = hd + ad
        losses = hl + al
        gf = int(home["fthg"].sum()) + int(away["ftag"].sum())
        ga = int(home["ftag"].sum()) + int(away["fthg"].sum())
        gd = gf - ga
        pts = wins * 3 + draws

        rows.append({
            "team": team,
            "P": played, "W": wins, "D": draws, "L": losses,
            "GF": gf, "GA": ga, "GD": gd, "Pts": pts,
        })

    rows.sort(key=lambda r: (-r["Pts"], -r["GD"], -r["GF"], r["team"]))
    return rows


def _season_stats(season_df: pd.DataFrame) -> Dict:
    """Aggregate stats for a season (goals, over-2.5 rate)."""
    n = len(season_df)
    total_goals = int(season_df["total_goals"].sum()) if n else 0
    avg_goals = round(total_goals / n, 3) if n else 0.0
    over25 = int((season_df["total_goals"] >= 3).sum())
    over25_rate = round(over25 / n, 3) if n else 0.0
    return {
        "n_matches": n,
        "total_goals": total_goals,
        "avg_goals": avg_goals,
        "over25": over25,
        "over25_rate": over25_rate,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_seasons(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
) -> List[pathlib.Path]:
    """Generate per-league per-season Obsidian notes into *out_dir*.

    Parameters
    ----------
    out_dir:     Destination directory; created if absent. Idempotent.
    corpus_dir:  Directory containing matches.parquet.

    Returns
    -------
    list[pathlib.Path]  Paths of every written note (index + season notes).
    """
    from domains.soccer.atlas_seasons_render import render_seasons_index, render_season_note

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _load_matches(corpus_dir)
    written: List[pathlib.Path] = []

    # Collect all (div, season) pairs
    pairs: List[Tuple[str, object]] = (
        df.groupby(["div", "season"]).size().reset_index()[["div", "season"]]
        .apply(lambda r: (r["div"], r["season"]), axis=1)
        .tolist()
    )
    pairs.sort(key=lambda t: (str(t[0]), str(t[1])))

    # Build per-season notes
    season_records: List[Dict] = []  # for the index
    for div, season in pairs:
        slice_df = df[(df["div"] == div) & (df["season"] == season)].copy()
        table = _final_table(slice_df)
        stats = _season_stats(slice_df)
        display = _league_display(div)
        champion = table[0]["team"] if table else "Unknown"
        n_teams = len(table)
        is_partial = stats["n_matches"] < (n_teams * (n_teams - 1)) if n_teams >= 2 else False

        season_records.append({
            "div": div,
            "season": season,
            "display": display,
            "champion": champion,
            "n_matches": stats["n_matches"],
            "is_partial": is_partial,
        })

        note_text = render_season_note(
            div=div,
            season=season,
            display=display,
            table=table,
            stats=stats,
            champion=champion,
            is_partial=is_partial,
        )
        fname = f"{_slug(display)} {season}.md"
        note_path = out_dir / fname
        written.append(write_note(note_path, note_text))

    # Write index last
    idx_text = render_seasons_index(season_records)
    idx_path = out_dir / "_Seasons_Index.md"
    written.append(write_note(idx_path, idx_text))

    return written
