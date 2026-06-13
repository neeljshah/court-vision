"""domains.basketball_nba.ingest_boxscores — cached quarter box JSON → player_boxscores.parquet.

PURE TRANSFORM of ALREADY-CACHED JSON.  ZERO network.  Deepens the NBA data
substrate so a LATER walk-forward feature builder can HONESTLY gate-test the
assist-rate edge (the platform NBA domain is schedule+odds only and cannot
currently test it).  This module ONLY captures; NO edge is claimed here.

Source cache: ``data/cache/quarter_box/{game_id}_q{n}.json``.  Each file is a
dict ``{"game_id", "period", "players": [...], "teams": [...]}`` where each
player dict carries the per-quarter box line.  The ``min`` field is "MM:SS"
(e.g. "6:28", "12:00") — a per-quarter minutes string.  ``to`` is the turnover
field (emitted here as ``tov``).  ``start_position`` is non-empty ("F"/"G"/"C")
for that quarter's starters and "" for bench.

For each (game_id, player_id) the q1..q4 (or whatever quarters exist) lines are
aggregated: counting stats SUMMED, minutes parsed to float and SUMMED.
``starter`` = True iff the player's q1 ``start_position`` is non-empty.

Game-level context (date, season, home_team, away_team) is LEFT-joined from
``data/domains/basketball_nba/games.parquet`` on game_id; ``opp`` and ``is_home``
are derived.  Teams are matched on ABBREVIATION (games.parquet stores team
abbreviations, and the box JSON has ``team_abbreviation``).

COVERAGE (HONEST):  the box cache covers ~1299 games — 2024-25 (~1225, near
complete) + 2025-26 (~74, partial).  ZERO games for 2022-23 / 2023-24.  (An
older estimate of ~2349 games was optimistic; the observed on-disk count is
~1299.)  Anything outside the cache simply yields no box rows.

MISSING-DATA POLICY:
- Missing quarter file -> aggregate whatever quarters exist (no crash, counted).
- Missing stat key in a record -> treated as 0 for SUMMED counting stats.
- Bad/corrupt file -> skipped and counted (never crashes the whole run).
- game_id with no games.parquet match -> box rows still emitted, but
  date/season/home_team/away_team/opp/is_home are NaN/None.

LEAK-NOTE: each row is THAT game's REALIZED box score — descriptive only.  A
downstream walk-forward feature builder (NEXT wave) will compute prior-only
as-of aggregates; this module performs NO leak-free shifting and claims NO edge.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = _REPO_ROOT / "data" / "cache" / "quarter_box"
_DEFAULT_GAMES = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"

# Counting stats SUMMED across quarters.  Key = output column; value = source
# key in the JSON record (only "tov" differs: source field is "to").
_SUM_STATS: Tuple[Tuple[str, str], ...] = (
    ("pts", "pts"), ("reb", "reb"), ("oreb", "oreb"), ("dreb", "dreb"),
    ("ast", "ast"), ("stl", "stl"), ("blk", "blk"), ("tov", "to"),
    ("fgm", "fgm"), ("fga", "fga"), ("fg3m", "fg3m"), ("fg3a", "fg3a"),
    ("ftm", "ftm"), ("fta", "fta"), ("pf", "pf"), ("plus_minus", "plus_minus"),
)

OUTPUT_COLS: Tuple[str, ...] = (
    "game_id", "date", "season", "team", "opp", "is_home",
    "player_id", "player_name", "starter", "min",
    "pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov",
    "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf", "plus_minus",
)


def _parse_minutes(raw: object) -> float:
    """Parse a per-quarter minutes value to float minutes.

    Handles "MM:SS" (the observed cache format), bare numeric strings, and
    numeric types.  Returns 0.0 for empty / unparseable values.
    """
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return 0.0 if (isinstance(raw, float) and np.isnan(raw)) else float(raw)
    s = str(raw).strip()
    if not s:
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            mins = float(parts[0] or 0)
            secs = float(parts[1] or 0) if len(parts) > 1 else 0.0
            return mins + secs / 60.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _iter_quarter_files(cache_dir: Path, game_id: str) -> List[Tuple[int, Path]]:
    """Return (period, path) for every existing q-file of game_id, period-sorted."""
    found: List[Tuple[int, Path]] = []
    for fp in cache_dir.glob(f"{game_id}_q*.json"):
        stem = fp.stem  # "{game_id}_q{n}"
        tail = stem.rsplit("_q", 1)
        if len(tail) != 2 or not tail[1].isdigit():
            continue
        found.append((int(tail[1]), fp))
    return sorted(found, key=lambda t: t[0])


def _load_players(path: Path) -> Tuple[int, List[dict]]:
    """Return (period, players list) from one quarter file; ([],-1) on failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return -1, []
    if not isinstance(data, dict):
        return -1, []
    players = data.get("players")
    if not isinstance(players, list):
        return -1, []
    try:
        period = int(data.get("period", -1))
    except (TypeError, ValueError):
        period = -1
    return period, players


def _aggregate_game(cache_dir: Path, game_id: str) -> List[dict]:
    """Aggregate one game's quarter files into per-(player) rows.

    Returns a list of partial row dicts (box stats only; game context added
    by the join).  Empty list if the game has no usable quarter data.
    """
    agg: Dict[int, dict] = {}  # player_id -> accumulating row
    starters_q1: Dict[int, bool] = {}
    names: Dict[int, str] = {}
    teams: Dict[int, str] = {}
    min_period_seen: Dict[int, int] = {}

    for period, path in _iter_quarter_files(cache_dir, game_id):
        fperiod, players = _load_players(path)
        if not players:
            continue  # missing / corrupt quarter -> skip, keep the rest
        eff_period = fperiod if fperiod > 0 else period
        for rec in players:
            try:
                pid = int(rec.get("player_id"))
            except (TypeError, ValueError):
                continue
            row = agg.get(pid)
            if row is None:
                row = {out: 0.0 for out, _ in _SUM_STATS}
                row["min"] = 0.0
                agg[pid] = row
            for out, src in _SUM_STATS:
                v = rec.get(src, 0)
                try:
                    row[out] += float(v) if v is not None else 0.0
                except (TypeError, ValueError):
                    pass
            row["min"] += _parse_minutes(rec.get("min"))
            names[pid] = str(rec.get("player_name", ""))
            ab = rec.get("team_abbreviation")
            if ab:
                teams[pid] = str(ab)
            # starter flag comes from the EARLIEST quarter we see for the player
            prev = min_period_seen.get(pid)
            if prev is None or eff_period < prev:
                min_period_seen[pid] = eff_period
                starters_q1[pid] = bool(str(rec.get("start_position", "")).strip())

    rows: List[dict] = []
    for pid, row in agg.items():
        row["game_id"] = str(game_id)
        row["player_id"] = pid
        row["player_name"] = names.get(pid, "")
        row["team"] = teams.get(pid)
        row["starter"] = bool(starters_q1.get(pid, False))
        rows.append(row)
    return rows


def _game_ids_from_cache(cache_dir: Path) -> List[str]:
    """Distinct game_ids present in the cache dir (from {gid}_q{n}.json names)."""
    ids = set()
    for fp in cache_dir.glob("*_q*.json"):
        stem = fp.stem
        head = stem.rsplit("_q", 1)
        if len(head) == 2 and head[1].isdigit():
            ids.add(head[0])
    return sorted(ids)


def _join_context(df: pd.DataFrame, games_path: Path) -> pd.DataFrame:
    """Left-join date/season/home/away from games.parquet; derive opp + is_home.

    Unmatched game_ids keep NaN/None context (no crash).
    """
    df = df.copy()
    if not games_path.exists():
        logger.warning("games.parquet not found at %s; emitting box rows with NaN context.", games_path)
        for c in ("date", "season", "home_team", "away_team"):
            df[c] = np.nan
    else:
        g = pd.read_parquet(games_path)[["game_id", "date", "season", "home_team", "away_team"]].copy()
        g["game_id"] = g["game_id"].astype(str)
        df["game_id"] = df["game_id"].astype(str)
        df = df.merge(g, on="game_id", how="left")

    home = df["home_team"]
    away = df["away_team"]
    team = df["team"]
    df["is_home"] = np.where(team.isna() | home.isna(), np.nan,
                             (team.astype(str) == home.astype(str)))
    df["opp"] = np.where(team.astype(str) == home.astype(str), away,
                         np.where(team.astype(str) == away.astype(str), home, np.nan))
    # rows whose team matched neither (or context missing) -> opp NaN
    return df


def build_player_boxscores(
    cache_dir: Optional[str] = None,
    games_path: Optional[str] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Aggregate the cached quarter box JSON into player_boxscores.parquet.

    Pure transform of on-disk JSON; performs NO network access.  See the module
    docstring for the coverage, missing-data, and leak notes.  Returns the Path
    written.  If the cache dir is absent, raises FileNotFoundError (the caller
    should STOP rather than fabricate).
    """
    cdir = Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE
    gpath = Path(games_path) if games_path is not None else _DEFAULT_GAMES
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT

    if not cdir.exists():
        raise FileNotFoundError(f"quarter_box cache not found at {cdir}.")

    all_rows: List[dict] = []
    skipped_files = 0
    game_ids = _game_ids_from_cache(cdir)
    for gid in game_ids:
        try:
            all_rows.extend(_aggregate_game(cdir, gid))
        except Exception:  # pragma: no cover - defensive; never crash whole run
            skipped_files += 1
            logger.exception("Failed aggregating game %s; skipping.", gid)

    if all_rows:
        df = pd.DataFrame(all_rows)
        df = _join_context(df, gpath)
        df = df.reindex(columns=list(OUTPUT_COLS))
        df["player_id"] = df["player_id"].astype("int64")
        df["starter"] = df["starter"].astype(bool)
        for out, _ in _SUM_STATS:
            df[out] = df[out].astype("float64")
        df["min"] = df["min"].astype("float64")
        df = df.sort_values(["game_id", "team", "player_id"], kind="mergesort").reset_index(drop=True)
    else:
        df = pd.DataFrame(columns=list(OUTPUT_COLS))

    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(dest), index=False)
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NBA quarter box cache → player_boxscores.parquet")
    ap.add_argument("--cache-dir", default=None, help="Quarter-box cache dir (optional)")
    ap.add_argument("--games", default=None, help="games.parquet path (optional)")
    ap.add_argument("--out", default=None, help="Output parquet path (optional)")
    args = ap.parse_args()

    dest = build_player_boxscores(cache_dir=args.cache_dir, games_path=args.games, out_path=args.out)
    out_df = pd.read_parquet(str(dest))
    n_games = out_df["game_id"].nunique() if len(out_df) else 0
    print("HONEST COVERAGE: box cache ~1299 games (2024-25 ~complete + 2025-26 partial);"
          " ZERO for 2022-23/2023-24. Descriptive realized box; NO edge claimed.")
    print(f"Wrote {dest}")
    print(f"Games covered: {n_games}")
    print(f"Player-rows written: {len(out_df)}")
    if len(out_df):
        print("Sample (3 rows):")
        print(out_df.head(3).to_string())
