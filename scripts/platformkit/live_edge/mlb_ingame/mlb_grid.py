"""scripts.platformkit.live_edge.mlb_ingame.mlb_grid -- MLB in-game situation
ontology as DATA, tagged onto historical GUMBO tick rows.

PREMISE CHECK (2026-07-14, fresh read before mining): data/domains/mlb/
gumbo_live/<game_pk>.jsonl holds 122 games / 43,491 poll-tick rows, 6 dates
(2026-07-07..2026-07-12). Each row IS a real base-out/count snapshot: balls,
strikes, outs, on_first/second/third (+ base_state 0-7, base_label), inning,
half, score_home, score_away, batter_id, pitcher_id, game_pk. This is a
POLLED snapshot feed (re-polled every ~15-25s, not a discrete PBP event
stream) -- consecutive identical rows are deduped here to recover PA-grain
state TRANSITIONS. 3,724 rows lack `captured_at` (older poll format) but
carry `ts` (YYYYMMDD_HHMMSS) as an equivalent capture time; both are used.

This is a genuinely different mechanism class from the CLOSED NBA
situational-conditioning track (team/player scoring-RATE conditioning) and
from MLB's corpus-accrual-blocked market_micro/weather/public_splits cells
(frozen by the all-star break) -- base-out state, count, TTO, and
inning/leverage are IN-GAME states with no scoring-rate assumption baked in,
and this reads completed-game historical PBP, not live market rows.

Grid axes (all in-game -- scope.context.in_game_only=true):
  base_state    -- the 8 base configurations (0=empty .. 7=loaded), straight
                   from GUMBO's own base_state int.
  count_bucket  -- "B{balls}S{strikes}" (12 buckets incl. B3S2 etc).
  period_band   -- f"{half}_{inning_band}" where inning_band buckets 1-3/
                   4-6/7-8/9+ (9+ collapses extras).
  margin_bucket -- BATTING team's own margin (away bats Top, home bats
                   Bottom), bucketed trailing_big(<=-5)/trailing(-4..-1)/
                   tied(0)/leading(1..4)/leading_big(>=5).
  tto           -- times-through-order for the CURRENT pitcher: counts
                   distinct batter-transitions faced by that (game_pk,
                   pitcher_id) so far, /9, capped "3+".
  leverage_band -- SIMPLIFIED heuristic (NOT a fitted win-expectancy index --
                   none exists on disk for this corpus): high = inning>=7 and
                   |margin|<=2; med = inning>=5 and |margin|<=4; else low.
                   Declared as a heuristic in every claim's evidence so it is
                   never mistaken for a calibrated leverage index.

Team-grain: game_pk_bridge/ (game_pk -> team names) covers only ONE date
(2026-07-03, outside this corpus's 07-07..07-12 span) -- team-grain pooling
is DATA-LIMITED here, not attempted; pooling instead runs league -> pitcher
(mlb_mine.py), which needs no team join.

Reserve discipline: no literal "season" column at this grain (mid-season
ticks only); reserve = TRAILING 25% of rows by capture date, stable sort --
identical rule to scripts/platformkit/interaction_factory/reserve.py's
date-axis branch (the omni fit path), copied here rather than imported
(that module is outside this lane's OWNS/IMPORT allowlist).
"""
from __future__ import annotations

import glob
import json
import pathlib

import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
GUMBO_DIR = REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live"

STATE_COLS = ["game_pk", "inning", "half", "outs", "balls", "strikes",
              "on_first", "on_second", "on_third", "score_home", "score_away",
              "batter_id", "pitcher_id", "base_state", "base_label"]

GROUP_COLS = ["base_state", "count_bucket", "period_band", "margin_bucket",
              "tto", "leverage_band"]


def _row_date(rec: dict) -> str:
    if rec.get("captured_at"):
        return str(rec["captured_at"])[:10]
    ts = rec.get("ts")
    if ts and len(ts) >= 8:
        return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
    return "unknown"


def load_ticks(source=None) -> pd.DataFrame:
    """Read every gumbo_live/<game_pk>.jsonl tick row into one frame."""
    if isinstance(source, pd.DataFrame):
        return source.copy()
    files = sorted(glob.glob(str((source or GUMBO_DIR) / "*.jsonl"))) if source else \
        sorted(glob.glob(str(GUMBO_DIR / "*.jsonl")))
    recs = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                d["date"] = _row_date(d)
                recs.append(d)
    if not recs:
        return pd.DataFrame(columns=STATE_COLS + ["date"])
    return pd.DataFrame(recs)


def dedupe_transitions(df: pd.DataFrame) -> pd.DataFrame:
    """Poll-tick feed re-polls the same state repeatedly; keep only rows
    where the full game state actually changed vs. the previous row for that
    game_pk (chronological order). Recovers PA/pitch-grain transitions."""
    d = df.sort_values(["game_pk", "date"], kind="mergesort").reset_index(drop=True)
    key_cols = ["inning", "half", "outs", "balls", "strikes", "on_first",
                "on_second", "on_third", "score_home", "score_away", "batter_id"]
    same_game = d["game_pk"] == d["game_pk"].shift(1)
    changed = np.zeros(len(d), dtype=bool)
    for c in key_cols:
        changed |= (d[c] != d[c].shift(1)).to_numpy()
    keep = (~same_game.to_numpy()) | changed
    return d[keep].reset_index(drop=True)


def split_discovery_reserve(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trailing 25% of rows by `date`, stable sort -- identical rule to the
    omni fit path's date-axis reserve (interaction_factory/reserve.py)."""
    ordered = df.sort_values("date", kind="mergesort").reset_index(drop=True)
    cut = int(len(ordered) * 0.75)
    return ordered.iloc[:cut].reset_index(drop=True), ordered.iloc[cut:].reset_index(drop=True)


def _count_bucket(balls: pd.Series, strikes: pd.Series) -> pd.Series:
    return "B" + balls.astype(int).astype(str) + "S" + strikes.astype(int).astype(str)


def _period_band(inning: pd.Series, half: pd.Series) -> pd.Series:
    band = np.select([inning <= 3, inning <= 6, inning <= 8], ["1-3", "4-6", "7-8"], default="9+")
    return half.astype(str) + "_" + band


def _margin_bucket(score_home, score_away, half) -> pd.Series:
    bat_margin = np.where(half == "Top", score_away - score_home, score_home - score_away)
    conditions = [bat_margin <= -5, (bat_margin >= -4) & (bat_margin <= -1),
                  bat_margin == 0, (bat_margin >= 1) & (bat_margin <= 4), bat_margin >= 5]
    labels = ["trailing_big", "trailing", "tied", "leading", "leading_big"]
    return pd.Series(np.select(conditions, labels, default="unknown"), index=score_home.index)


def _tto(df: pd.DataFrame) -> pd.Series:
    """Times through the order for the pitcher currently on the mound: count
    distinct batter-transitions faced by (game_pk, pitcher_id) so far."""
    new_batter = (df["batter_id"] != df.groupby(["game_pk", "pitcher_id"])["batter_id"].shift(1))
    pa_idx = new_batter.groupby([df["game_pk"], df["pitcher_id"]]).cumsum()
    tto_num = ((pa_idx - 1) // 9 + 1).clip(upper=3)
    return tto_num.map({1: "1st", 2: "2nd", 3: "3rd+"}).astype(object)


def _leverage_band(inning: pd.Series, margin_bucket: pd.Series) -> pd.Series:
    absm = margin_bucket.map({"tied": 0, "leading": 2, "trailing": 2,
                               "leading_big": 6, "trailing_big": 6, "unknown": 99}).astype(int)
    high = (inning >= 7) & (absm <= 2)
    med = (~high) & (inning >= 5) & (absm <= 4)
    return pd.Series(np.select([high, med], ["high", "med"], default="low"), index=inning.index)


def tag_situations(df: pd.DataFrame) -> pd.DataFrame:
    """Attach every grid axis to a deduped tick-transition frame."""
    out = df.copy()
    out["count_bucket"] = _count_bucket(out["balls"], out["strikes"])
    out["period_band"] = _period_band(out["inning"], out["half"])
    out["margin_bucket"] = _margin_bucket(out["score_home"], out["score_away"], out["half"])
    out["tto"] = _tto(out)
    out["leverage_band"] = _leverage_band(out["inning"], out["margin_bucket"])
    return out


def enumerate_cells(tagged_df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    cols = group_cols or GROUP_COLS
    grp = tagged_df.groupby(cols, observed=True).size().reset_index(name="n")
    return grp


__all__ = [
    "REPO_ROOT", "GUMBO_DIR", "GROUP_COLS", "load_ticks", "dedupe_transitions",
    "split_discovery_reserve", "tag_situations", "enumerate_cells",
]
