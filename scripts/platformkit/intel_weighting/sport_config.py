"""sport_config -- per-sport games-table loaders for the relevance gate.

Extends the gate beyond nba/mlb to soccer (draws) and tennis (player entity).
Every loader normalizes its raw parquet to the SAME shape relevance_gate
consumes: home_team, away_team, season, game_id, date, WIN_COL.

Soccer draws: reuses the EXACT H/D/A -> 1.0/0.5/0.0 fractional home-result
convention the cross-sport benchmark uses (generic_rating.py _default_loader,
kind='score') -- a binary home-win Brier would silently discard draws, so we
do not invent one. Brier/log-loss are proper scoring rules for any target in
[0,1]; a 0.5 "draw" label is a valid soft outcome, not a hack.

MLB: games.parquet's season coverage stops 2021-11-02, but the new
mlb_bullpen_fatigue_chains claim windows are year_2022..2026 -- games.parquet
has zero overlap with any prior-season lookup those windows could feed. Use
games_current.parquet (2022-2026) instead, the only MLB games table that
actually overlaps a year-windowed claim family.

soccer_intl (national-team/World-Cup corpus, data/domains/soccer_intl --
DIFFERENT from the soccer club corpus above): results.parquet has no
pre-built season/game_id/win column, so _load_soccer_intl derives them here
(season = calendar year of date; win via the same H/D/A -> 1.0/0.5/0.0
fractional convention `_load_soccer` already uses).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]

WIN_COL = "target_home_win"      # normalized outcome col for mlb/soccer/tennis
_GAMES_WIN_COL: Dict[str, str] = {"nba": "home_win", "mlb": WIN_COL,
                                   "soccer": WIN_COL, "tennis": WIN_COL,
                                   "soccer_intl": WIN_COL}
# split -> eval_season like '2025-26' (prior = '2024-25'); plain -> '2026' (prior = '2025')
SEASON_STYLE: Dict[str, str] = {"nba": "split", "mlb": "plain", "soccer": "plain",
                                 "tennis": "plain", "soccer_intl": "plain"}
_FTR_SCORE = {"H": 1.0, "D": 0.5, "A": 0.0}
_REF_SENTINEL = "_NONE_"          # absent from any z dict -> z.get(sentinel, 0) = 0


def _load_nba() -> pd.DataFrame:
    return pd.read_parquet(REPO_ROOT / "data/domains/basketball_nba/games.parquet")


def _load_mlb() -> pd.DataFrame:
    df = pd.read_parquet(REPO_ROOT / "data/domains/mlb/games_current.parquet")
    return df.rename(columns={"event_id": "game_id"})[
        ["home_team", "away_team", "season", "game_id", "date", WIN_COL]]


def _load_soccer() -> pd.DataFrame:
    df = pd.read_parquet(REPO_ROOT / "data/domains/soccer/matches.parquet")
    df = df.assign(**{WIN_COL: df["ftr"].map(_FTR_SCORE)})
    return df.rename(columns={"event_id": "game_id"})[
        ["home_team", "away_team", "season", "game_id", "date", WIN_COL]]


def _load_tennis() -> pd.DataFrame:
    df = pd.read_parquet(REPO_ROOT / "data/domains/tennis/matches.parquet")
    season = pd.to_datetime(df["date"]).dt.year.astype(str)
    win = (df["winner"].astype(int) == 1).astype(float)
    return pd.DataFrame({
        "home_team": df["p1_id"].astype(str), "away_team": df["p2_id"].astype(str),
        "season": season, "game_id": df["event_id"].astype(str), "date": df["date"],
        WIN_COL: win,
    })


def _load_soccer_intl() -> pd.DataFrame:
    df = pd.read_parquet(REPO_ROOT / "data/domains/soccer_intl/results.parquet")
    df = df.assign(
        season=pd.to_datetime(df["date"]).dt.year.astype(str),
        game_id=df.index.astype(str),
        **{WIN_COL: (df["home_score"] > df["away_score"]).astype(float)
                     + 0.5 * (df["home_score"] == df["away_score"]).astype(float)},
    )
    return df[["home_team", "away_team", "season", "game_id", "date", WIN_COL]]


_LOADERS: Dict[str, Callable[[], pd.DataFrame]] = {
    "nba": _load_nba, "mlb": _load_mlb, "soccer": _load_soccer, "tennis": _load_tennis,
    "soccer_intl": _load_soccer_intl,
}


def win_col(sport: str) -> str:
    return _GAMES_WIN_COL[sport]


def load_games(sport: str) -> pd.DataFrame:
    """Ordered-by-date games/matches table, normalized columns (see module doc)."""
    return _LOADERS[sport]().sort_values("date").reset_index(drop=True)


def prior_season_str(eval_season: str, sport: str) -> str:
    style = SEASON_STYLE.get(sport, "split")
    if style == "plain":
        return str(int(eval_season) - 1)
    start = int(eval_season.split("-")[0])
    return f"{start - 1:04d}-{start % 100:02d}"


def soccer_referee_view(games_df: pd.DataFrame, match_stats_path: Optional[Path] = None) -> pd.DataFrame:
    """Referee entity mapping: run_gate's fdiff = z.get(home) - z.get(away)
    formula assumes two competing sides, but a referee is not a side -- there
    is no home/away sign to a referee's foul-rate z-score. Substitute the
    assigned referee for home_team and a sentinel (absent from any z dict,
    so z.get(sentinel, 0)=0) for away_team; fdiff then collapses to the raw
    z(referee), unsigned, exactly as intended. run_gate/_fit are untouched --
    only the team columns fed into them are swapped for this one call.
    """
    path = match_stats_path or REPO_ROOT / "data/domains/soccer/match_stats.parquet"
    ref = pd.read_parquet(path, columns=["event_id", "referee"])
    ref = ref.rename(columns={"event_id": "game_id"})
    ref["game_id"] = ref["game_id"].astype(str)
    view = games_df.merge(ref, on="game_id", how="left")
    view["home_team"] = view["referee"].fillna(_REF_SENTINEL)
    view["away_team"] = _REF_SENTINEL
    return view.drop(columns=["referee"])


if __name__ == "__main__":  # tiny self-check, no network/heavy deps
    for sport in ("nba", "mlb", "soccer", "tennis", "soccer_intl"):
        df = load_games(sport)
        assert {"home_team", "away_team", "season", "game_id", "date", win_col(sport)} <= set(df.columns), sport
        assert df[win_col(sport)].between(0, 1).all(), sport
    assert prior_season_str("2025-26", "nba") == "2024-25"
    assert prior_season_str("2026", "mlb") == "2025"
    print("OK sport_config self-check passed")
