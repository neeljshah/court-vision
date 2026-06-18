"""domains.basketball_nba.player_props -- a FIRST leak-free player-prop pricer built on the
existing local box-score corpus (data/domains/basketball_nba/player_boxscores.parquet,
~27.8k player-game rows: pts/reb/ast/stl/blk/fg3m/tov + min, dated).

For a target player + date + line it returns, using ONLY games strictly BEFORE the date:
  * rolling L5 / L10 / L20 HIT-RATE vs the line (empirical P(stat > line)),
  * a simple mean/sigma Gaussian projection -> P(over) (recency-weighted L10 mean, sample sd),
  * a blended P(over) (Gaussian projection, with the hit-rates reported alongside).

Supports derived markets: PRA (pts+reb+ast), PR, PA, RA, and double-double. Leak contract:
every number for date D uses only rows with date < D -> no future leakage. Honest: this is a
recency baseline, NOT the production prop stack; calibration/coverage, no $ edge claimed.

INVARIANTS: never edit src/ or kernel/; build under domains/; <=300 LOC; no $ edge claimed.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

_BOX = Path("data/domains/basketball_nba/player_boxscores.parquet")

# base stats present per row, plus derived combos computed on the fly
_BASE = ("pts", "reb", "ast", "stl", "blk", "fg3m", "tov", "fgm", "fga")
_DERIVED = {"pra": ("pts", "reb", "ast"), "pr": ("pts", "reb"),
            "pa": ("pts", "ast"), "ra": ("reb", "ast")}
# minimum sigma floor per stat so a low-variance window never prices an absurd over/under
_SIGMA_FLOOR = {"pts": 4.0, "reb": 2.0, "ast": 1.5, "stl": 1.0, "blk": 1.0,
                "fg3m": 1.0, "tov": 1.2, "pra": 5.0, "pr": 4.0, "pa": 4.0, "ra": 2.5}


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@lru_cache(maxsize=1)
def load_box(path: str = str(_BOX)) -> pd.DataFrame:
    """Load the player box corpus, sorted by date. Cached."""
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _stat_series(df: pd.DataFrame, stat: str) -> pd.Series:
    stat = stat.lower()
    if stat in _DERIVED:
        return sum(df[c] for c in _DERIVED[stat])
    if stat not in _BASE:
        raise ValueError(f"unknown stat '{stat}'")
    return df[stat]


def _player_history(df: pd.DataFrame, player: str, before_date) -> pd.DataFrame:
    """Rows for `player` (id int or name str) strictly BEFORE before_date -> leak-free."""
    cut = pd.to_datetime(before_date)
    if isinstance(player, int) or (isinstance(player, str) and player.isdigit()):
        m = df["player_id"] == int(player)
    else:
        m = df["player_name"].str.lower() == str(player).lower()
    hist = df[m & (df["date"] < cut)]
    return hist.sort_values("date")


def _hit_rate(vals: np.ndarray, line: float, window: int) -> Optional[float]:
    w = vals[-window:]
    if len(w) == 0:
        return None
    return float(np.mean(w > line))


def price_prop(player, stat: str, line: float, date,
               df: Optional[pd.DataFrame] = None) -> Dict:
    """Leak-free P(over) for `player` `stat` vs `line` as of `date`.

    Returns rolling L5/L10/L20 empirical hit-rates plus a recency-weighted Gaussian
    projection P(over). Uses only games strictly before `date`. Returns a graceful
    'insufficient_history' status (never raises) when too few prior games exist.
    """
    df = load_box() if df is None else df
    stat = stat.lower()
    hist = _player_history(df, player, date)
    if len(hist) < 3:
        return {"market": "player_prop", "player": str(player), "stat": stat,
                "line": float(line), "date": str(pd.to_datetime(date).date()),
                "status": "insufficient_history", "n_games": int(len(hist)),
                "p_over": None}
    vals = _stat_series(hist, stat).to_numpy(float)
    l5 = _hit_rate(vals, line, 5)
    l10 = _hit_rate(vals, line, 10)
    l20 = _hit_rate(vals, line, 20)
    # recency-weighted mean over the last up-to-15 games (linear weights, newest heaviest)
    w = vals[-15:]
    weights = np.arange(1, len(w) + 1, dtype=float)
    mean = float(np.average(w, weights=weights))
    sd = float(np.std(vals[-15:], ddof=1)) if len(vals) >= 2 else 0.0
    sd = max(sd, _SIGMA_FLOOR.get(stat, 1.0))
    p_over = 1.0 - _phi((line - mean) / sd)
    return {"market": "player_prop", "player": str(player), "stat": stat,
            "line": float(line), "date": str(pd.to_datetime(date).date()),
            "status": "ok", "n_games": int(len(hist)),
            "proj_mean": round(mean, 2), "proj_sigma": round(sd, 2),
            "p_over": round(p_over, 4), "p_under": round(1.0 - p_over, 4),
            "hit_rate_l5": None if l5 is None else round(l5, 3),
            "hit_rate_l10": None if l10 is None else round(l10, 3),
            "hit_rate_l20": None if l20 is None else round(l20, 3),
            "note": ("recency-weighted Gaussian projection + empirical rolling hit-rates; "
                     "leak-free (games before the date only); calibration baseline, no $ edge")}


def price_double_double(player, date, df: Optional[pd.DataFrame] = None) -> Dict:
    """Leak-free P(double-double): >=10 in at least two of pts/reb/ast.

    Empirical frequency over the last up-to-20 prior games (a calibrated base-rate read,
    not an independence assumption across the three marginals).
    """
    df = load_box() if df is None else df
    hist = _player_history(df, player, date)
    if len(hist) < 3:
        return {"market": "double_double", "player": str(player),
                "date": str(pd.to_datetime(date).date()),
                "status": "insufficient_history", "n_games": int(len(hist)),
                "p_dd": None}
    h = hist.tail(20)
    cats = (h["pts"] >= 10).astype(int) + (h["reb"] >= 10).astype(int) + \
           (h["ast"] >= 10).astype(int)
    p_dd = float(np.mean(cats >= 2))
    return {"market": "double_double", "player": str(player),
            "date": str(pd.to_datetime(date).date()), "status": "ok",
            "n_games": int(len(hist)), "p_dd": round(p_dd, 4),
            "note": "empirical DD base-rate over last <=20 prior games; leak-free, no $ edge"}


def price_player_card(player, date, lines: Optional[Dict[str, float]] = None,
                      df: Optional[pd.DataFrame] = None) -> Dict:
    """Full prop card for a player as of `date`: pts/reb/ast/fg3m/pra + double-double.

    `lines` maps stat -> line; missing stats default to the player's prior mean rounded to
    the nearest 0.5 minus 0.5 (a near-coinflip line) so the card is always populated.
    """
    df = load_box() if df is None else df
    lines = lines or {}
    card: Dict = {"player": str(player), "date": str(pd.to_datetime(date).date()),
                  "props": {}}
    hist = _player_history(df, player, date)
    for stat in ("pts", "reb", "ast", "fg3m", "pra"):
        if stat in lines:
            ln = lines[stat]
        elif len(hist) >= 3:
            m = float(_stat_series(hist.tail(15), stat).mean())
            ln = round(m * 2) / 2.0 - 0.5
        else:
            ln = 0.5
        card["props"][stat] = price_prop(player, stat, ln, date, df=df)
    card["double_double"] = price_double_double(player, date, df=df)
    return card


def top_scorers(team: str, date, df: Optional[pd.DataFrame] = None,
                k: int = 8) -> List[str]:
    """The k players with the most prior minutes for `team` before `date` (for slate cards)."""
    df = load_box() if df is None else df
    cut = pd.to_datetime(date)
    sub = df[(df["team"].str.upper() == team.upper()) & (df["date"] < cut)]
    if sub.empty:
        return []
    mins = sub.groupby("player_name")["min"].sum().sort_values(ascending=False)
    return list(mins.head(k).index)


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Leak-free NBA player-prop pricer (baseline).")
    ap.add_argument("--player", default="Jayson Tatum")
    ap.add_argument("--stat", default="pts")
    ap.add_argument("--line", type=float, default=27.5)
    ap.add_argument("--date", default="2025-04-01")
    ap.add_argument("--card", action="store_true", help="print a full prop card")
    args = ap.parse_args(argv)
    if args.card:
        print(json.dumps(price_player_card(args.player, args.date), indent=2))
    else:
        print(json.dumps(price_prop(args.player, args.stat, args.line, args.date), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
