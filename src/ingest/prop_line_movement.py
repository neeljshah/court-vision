"""prop_line_movement.py — leak-safe per-player PROP line-movement features.

Exposes the already-captured intraday sportsbook PROP lines in ``data/lines/``
(``<YYYY-MM-DD>_<book>.csv`` with columns
``captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time``)
as a leak-safe model feature: for a given (player, stat, game-date) and an
``asof`` capture timestamp, summarise how the OVER/UNDER line for that prop has
MOVED across captures that occurred STRICTLY BEFORE ``asof``.

Why this is a feature and not a leak
------------------------------------
The prop CSVs hold many capture timestamps per day (DK ~10, Pinnacle ~270 on a
typical slate). Line drift between the open and a chosen as-of moment encodes
sharp/steam money that the market has already priced — information available
pre-tip. Crucially we ONLY ever read captures with ``captured_at < asof`` and we
NEVER read the closing/last line as a training feature unless the caller passes
``asof`` = the moment a bet would be placed. The default ``asof`` is the EARLIEST
useful cutoff (first capture) so that, with no asof supplied, the feature is the
neutral "no movement seen yet" vector — never the close.

This complements the GAME-level spread/total movement already wired in
``src/prediction/player_props.py`` (pinnacle_line_move / action_steam_flag).
That path moves the team spread; THIS path moves the per-PLAYER prop line, which
is not otherwise exposed to the prop model.

Leak posture (enforced by tests/test_prop_line_movement.py):
  * features at ``asof`` are invariant to deleting any capture row with
    ``captured_at >= asof`` (truncation-invariance);
  * only the named (date, stat, player) prop is read — no cross-game/as-of-today
    aggregate;
  * returns the neutral all-zero vector when fewer than 2 pre-asof captures
    exist, so absence of data never injects signal.
"""
from __future__ import annotations

import glob
import os
from typing import Optional

import pandas as pd

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LINES_DIR = os.path.join(_PROJECT_DIR, "data", "lines")

# Canonical CSV columns we rely on. Files in data/lines/ occasionally concat
# two schemas (extra book_selection_id_* columns) -> read tolerantly.
_REQUIRED = ["captured_at", "book", "player_name", "stat", "line", "over_price", "under_price"]

_NEUTRAL: dict = {
    "prop_line_open": 0.0,        # first pre-asof line seen (0.0 = unknown)
    "prop_line_latest": 0.0,      # last pre-asof line seen
    "prop_line_move": 0.0,        # latest - open (signed drift toward over)
    "prop_line_move_abs": 0.0,    # |drift|
    "prop_over_price_move": 0.0,  # latest over_price - open over_price (american)
    "prop_n_captures": 0.0,       # how many pre-asof captures informed this
    "prop_line_moved_flag": 0.0,  # 1.0 if line changed at all pre-asof
}


def _read_lines_csv(path: str) -> Optional[pd.DataFrame]:
    """Read a possibly-ragged lines CSV, keeping only the canonical columns."""
    try:
        df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    except Exception:
        return None
    if df.empty or not set(_REQUIRED).issubset(df.columns):
        return None
    df = df[_REQUIRED].copy()
    df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True, errors="coerce")
    df["line"] = pd.to_numeric(df["line"], errors="coerce")
    df["over_price"] = pd.to_numeric(df["over_price"], errors="coerce")
    df = df.dropna(subset=["captured_at", "line"])
    df["player_name_lower"] = df["player_name"].astype(str).str.strip().str.lower()
    df["stat"] = df["stat"].astype(str).str.strip().str.lower()
    return df


def _load_date(game_date: str, book: Optional[str] = None) -> pd.DataFrame:
    """Concat all per-book capture CSVs for ``game_date`` (YYYY-MM-DD)."""
    pat = os.path.join(_LINES_DIR, f"{game_date}_*.csv")
    frames = []
    for path in sorted(glob.glob(pat)):
        if path.endswith(".stale"):
            continue
        if book is not None and f"_{book}.csv" not in os.path.basename(path):
            continue
        df = _read_lines_csv(path)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=list(_NEUTRAL))
    return pd.concat(frames, ignore_index=True)


def get_prop_line_movement(
    player_name: str,
    stat: str,
    game_date: str,
    asof: Optional[str] = None,
    book: Optional[str] = None,
) -> dict:
    """Leak-safe per-player prop line-movement features.

    Args:
        player_name: e.g. "Shai Gilgeous-Alexander" (case-insensitive).
        stat:        one of pts/reb/ast/fg3m/stl/blk/tov (case-insensitive).
        game_date:   slate date "YYYY-MM-DD" (matches the data/lines filename).
        asof:        ISO timestamp; ONLY captures strictly before this are read.
                     ``None`` -> use the EARLIEST capture as cutoff, i.e. the
                     neutral "nothing has moved yet" vector (never the close).
        book:        restrict to one book (e.g. "dk", "pin"); ``None`` = all books.

    Returns:
        dict of the keys in ``_NEUTRAL``. Neutral (all-zero) when <2 usable
        pre-asof captures exist.
    """
    out = dict(_NEUTRAL)
    df = _load_date(game_date, book=book)
    if df.empty:
        return out

    name = str(player_name).strip().lower()
    st = str(stat).strip().lower()
    sub = df[(df["player_name_lower"] == name) & (df["stat"] == st)]
    if sub.empty:
        return out

    if asof is not None:
        cutoff = pd.to_datetime(asof, utc=True, errors="coerce")
        if pd.notna(cutoff):
            sub = sub[sub["captured_at"] < cutoff]
    else:
        # neutral default: cutoff at the earliest capture -> nothing visible yet
        return out

    if len(sub) < 2:
        # 0 or 1 capture seen -> no movement is observable yet
        if len(sub) == 1:
            out["prop_line_open"] = float(sub.iloc[0]["line"])
            out["prop_line_latest"] = float(sub.iloc[0]["line"])
            out["prop_n_captures"] = 1.0
        return out

    sub = sub.sort_values("captured_at")
    first = sub.iloc[0]
    last = sub.iloc[-1]
    open_line = float(first["line"])
    latest_line = float(last["line"])
    move = latest_line - open_line

    op_first = first.get("over_price")
    op_last = last.get("over_price")
    op_move = 0.0
    if pd.notna(op_first) and pd.notna(op_last):
        op_move = float(op_last) - float(op_first)

    out.update(
        {
            "prop_line_open": open_line,
            "prop_line_latest": latest_line,
            "prop_line_move": move,
            "prop_line_move_abs": abs(move),
            "prop_over_price_move": op_move,
            "prop_n_captures": float(len(sub)),
            "prop_line_moved_flag": 1.0 if move != 0.0 else 0.0,
        }
    )
    return out


def feature_keys() -> list:
    """Stable ordered feature-key list for downstream vectorisation."""
    return list(_NEUTRAL)
