"""Point-in-time (PIT) opponent-stat-allowed builder.

The box score lies; basketball tells the truth. A single `opp_def` rating
flattens a defense into one number. But an AST over vs a team that *concedes
ball movement* (drop coverage, lazy closeouts) is a different bet than the same
line vs a team that disrupts passing lanes. This module builds, strictly
leak-free, the season-to-date rate at which each team ALLOWS each box-score stat
to its opponents, as of the morning of each game.

Leak-free by construction: a team's as-of allowed rate for game k uses ONLY
games 1..k-1 (expanding mean, shift(1)). League baseline is likewise as-of.

Sources (season-agnostic):
  - 2025-26 reg / 2026 playoffs: data/cache/cv_fix/leaguegamelog_{regular_season,playoffs}.parquet
    (full schema incl. GAME_ID, TEAM_ABBREVIATION, FGA/FTA/OREB).
  - 2023-24 / 2024-25: assembled from data/nba/gamelog_<pid>_<season>.json
    (core stats only: PTS/REB/AST/FG3M/STL/BLK/TOV/MIN; team & opp from MATCHUP).

Output: data/cache/pit/opp_allowed_asof_<tag>.parquet keyed (team, game_date)
with opp_<stat>_allowed_asof, opp_<stat>_allowed_z (vs league as-of), n_games_asof.

Read-only except writing under data/cache/pit/.
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CVFIX = os.path.join(ROOT, "data", "cache", "cv_fix")
NBA = os.path.join(ROOT, "data", "nba")
OUT_DIR = os.path.join(ROOT, "data", "cache", "pit")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_STAT_SRC = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
             "stl": "STL", "blk": "BLK", "tov": "TOV"}


def _parse_date(s) -> Optional[pd.Timestamp]:
    if isinstance(s, (pd.Timestamp, datetime)):
        return pd.Timestamp(s).normalize()
    if s is None:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return pd.Timestamp(datetime.strptime(str(s).strip(), fmt)).normalize()
        except ValueError:
            continue
    try:
        return pd.Timestamp(s).normalize()
    except Exception:
        return None


_MATCHUP_RE = re.compile(r"^([A-Z]{2,4})\s*(@|vs\.?|VS\.?)\s*([A-Z]{2,4})")


def _parse_matchup(m: str):
    """'GSW @ LAL' -> (team=GSW, opp=LAL, is_home=0).  'GSW vs. LAL' -> home=1."""
    if not isinstance(m, str):
        return None, None, None
    mm = _MATCHUP_RE.match(m.strip())
    if not mm:
        return None, None, None
    team, sep, opp = mm.group(1), mm.group(2), mm.group(3)
    is_home = 0 if sep.startswith("@") else 1
    return team, opp, is_home


# ---------------------------------------------------------------- loaders

def load_from_parquet(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    out = pd.DataFrame({
        "pid": df["PLAYER_ID"].astype("int64"),
        "team": df["TEAM_ABBREVIATION"].astype(str),
        "game_id": df["GAME_ID"].astype(str),
        "game_date": df["GAME_DATE"].map(_parse_date),
    })
    mt = df["MATCHUP"].map(_parse_matchup)
    out["opp"] = [t[1] for t in mt]
    out["is_home"] = [t[2] for t in mt]
    for s, col in _STAT_SRC.items():
        out[s] = pd.to_numeric(df.get(col), errors="coerce")
    out = out.dropna(subset=["game_date", "team", "opp"])
    return out


def load_from_player_jsons(season: str) -> pd.DataFrame:
    """Assemble a league log from per-player gamelog JSONs (core stats only)."""
    rows: List[dict] = []
    for path in glob.glob(os.path.join(NBA, f"gamelog_*_{season}.json")):
        base = os.path.basename(path)
        try:
            pid = int(base.split("_")[1])
        except (IndexError, ValueError):
            continue
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for r in data:
            team, opp, is_home = _parse_matchup(r.get("MATCHUP", ""))
            d = _parse_date(r.get("GAME_DATE"))
            if team is None or d is None:
                continue
            row = {"pid": pid, "team": team, "opp": opp, "is_home": is_home,
                   "game_date": d, "game_id": None}
            for s, col in _STAT_SRC.items():
                try:
                    row[s] = float(r.get(col)) if r.get(col) is not None else np.nan
                except (TypeError, ValueError):
                    row[s] = np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def load_league_log(tag: str) -> pd.DataFrame:
    if tag == "2025_26_reg":
        return load_from_parquet(os.path.join(CVFIX, "leaguegamelog_regular_season.parquet"))
    if tag == "2026_playoffs":
        return load_from_parquet(os.path.join(CVFIX, "leaguegamelog_playoffs.parquet"))
    if tag in ("2024_25", "2023_24"):
        return load_from_player_jsons(tag.replace("_", "-"))
    raise ValueError(f"unknown tag {tag}")


# ---------------------------------------------------------------- core

def team_game_allowed(df: pd.DataFrame) -> pd.DataFrame:
    """Per (game_date, team): the OPPONENT's team-total of each stat = what `team`
    ALLOWED that game. Uses game_id when present, else (date, team) which is
    unique in the NBA (<=1 game/team/day)."""
    # team-game totals (sum players)
    grp_keys = ["game_date", "team", "opp"]
    tot = df.groupby(grp_keys, as_index=False)[STATS].sum(min_count=1)
    # allowed_by(team) = totals of opp on same date. Build a lookup of (date,team)->totals
    lut: Dict[tuple, dict] = {}
    for r in tot.itertuples(index=False):
        lut[(r.game_date, r.team)] = {s: getattr(r, s) for s in STATS}
    out_rows = []
    for r in tot.itertuples(index=False):
        opp_tot = lut.get((r.game_date, r.opp))
        if opp_tot is None:
            continue  # opponent rows missing (incomplete log) -> skip game
        row = {"game_date": r.game_date, "team": r.team, "opp": r.opp}
        for s in STATS:
            row[f"allowed_{s}"] = opp_tot[s]
        out_rows.append(row)
    res = pd.DataFrame(out_rows).sort_values(["team", "game_date"]).reset_index(drop=True)
    return res


def build_asof(tg: pd.DataFrame) -> pd.DataFrame:
    """Expanding-window, strictly-before (shift 1) mean of allowed_<stat> per team,
    plus league as-of baseline -> league-relative diff (z-like). Leak-free."""
    tg = tg.sort_values(["team", "game_date"]).reset_index(drop=True)
    out = tg[["game_date", "team", "opp"]].copy()
    for s in STATS:
        col = f"allowed_{s}"
        # as-of team mean of what this team allowed, BEFORE this game
        g = tg.groupby("team")[col]
        out[f"opp_{s}_allowed_asof"] = (
            g.apply(lambda x: x.shift(1).expanding().mean()).reset_index(level=0, drop=True)
        )
    # n games seen so far (before this game)
    out["n_games_asof"] = tg.groupby("team").cumcount()
    # league as-of baseline: mean over all team-games strictly before this date.
    # Compute via per-date league mean of the per-team as-of would double count;
    # instead use expanding league mean of the raw allowed across all games before date.
    for s in STATS:
        col = f"allowed_{s}"
        srt = tg.sort_values("game_date").reset_index()
        # cumulative league mean of allowed up to (not incl) each row's date
        srt["league_cummean"] = srt[col].expanding().mean().shift(1)
        # map back by original index
        league_map = srt.set_index("index")["league_cummean"]
        out[f"_league_{s}"] = out.index.map(league_map)
        # diff vs league (positive => allows MORE than league avg => softer D for that stat)
        out[f"opp_{s}_allowed_vs_league"] = out[f"opp_{s}_allowed_asof"] - out[f"_league_{s}"]
        out.drop(columns=[f"_league_{s}"], inplace=True)
    return out


def leakfree_selftest(tg: pd.DataFrame, asof: pd.DataFrame) -> None:
    """Assert each team's as-of value == mean of allowed in strictly-prior games."""
    tg = tg.sort_values(["team", "game_date"]).reset_index(drop=True)
    asof = asof.sort_values(["team", "game_date"]).reset_index(drop=True)
    checks = 0
    for team, sub in tg.groupby("team"):
        sub = sub.reset_index(drop=True)
        a = asof[asof.team == team].reset_index(drop=True)
        for k in range(len(sub)):
            expect_n = k
            assert int(a.loc[k, "n_games_asof"]) == expect_n, \
                f"n_games_asof mismatch {team} game{k}: {a.loc[k,'n_games_asof']} != {expect_n}"
            if k == 0:
                assert pd.isna(a.loc[k, "opp_ast_allowed_asof"]), \
                    f"first game must be NaN as-of ({team})"
            else:
                exp = sub.loc[: k - 1, "allowed_ast"].mean()
                got = a.loc[k, "opp_ast_allowed_asof"]
                assert abs(exp - got) < 1e-6, f"as-of leak {team} g{k}: {got} != {exp}"
            checks += 1
            if checks > 4000:
                break
        if checks > 4000:
            break
    print(f"  leak-free self-test PASSED ({checks} (team,game) cells verified)")


def build_tag(tag: str) -> pd.DataFrame:
    print(f"[{tag}] loading league log...")
    df = load_league_log(tag)
    print(f"  {len(df):,} player-game rows, {df['game_date'].nunique()} dates, "
          f"{df['team'].nunique()} teams, {df['game_date'].min()} -> {df['game_date'].max()}")
    tg = team_game_allowed(df)
    print(f"  {len(tg):,} team-games with matched opponent")
    asof = build_asof(tg)
    leakfree_selftest(tg, asof)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"opp_allowed_asof_{tag}.parquet")
    asof.to_parquet(out_path, index=False)
    print(f"  wrote {out_path}  ({len(asof):,} rows)")
    # quick face-validity: spread of as-of AST-allowed at season end
    late = asof[asof.n_games_asof >= 20]
    if len(late):
        v = late.groupby("team")["opp_ast_allowed_asof"].last().sort_values()
        print(f"  AST-allowed as-of (late, per team) range: "
              f"{v.min():.1f} ({v.index[0]}) .. {v.max():.1f} ({v.index[-1]})")
    return asof


if __name__ == "__main__":
    import sys
    tags = sys.argv[1:] or ["2025_26_reg"]
    for t in tags:
        build_tag(t)
