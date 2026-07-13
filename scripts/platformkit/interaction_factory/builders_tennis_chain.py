"""Tennis serve-by-surface + tournament-fatigue CHAIN as-of attrs (Sonnet
build lane B9). Orthogonal to the existing tennis_match_asof pool (return/
serve rate stats out of asof_return.parquet/asof_features.parquet/
asof_setdetail.parquet) -- these 4 attrs are computed straight from
matches.parquet's own (date, surface, p1_id, p2_id, score) columns: rest and
tournament-chain LOAD, not serve/return quality.

Every attr is a strictly-PRIOR (as of match start) as-of value: for player P's
match on date D, only P's OWN matches with date < D feed the computation --
same-day matches never count as "prior" (no intra-day ordering signal exists
in the source, so this is the conservative, leak-free choice; a same-day
back-to-back is treated as "no prior data" rather than guessed at). The
current match's own result/score never enters its own row's attrs.

  days_since_last_match_diff   -- p1's days-since-own-last-match MINUS p2's
                                   (NaN diff if either has no prior match)
  matches_last_14d_diff        -- count of own matches in the trailing 14
                                   calendar days before D, p1 minus p2
  sets_played_last_14d_diff    -- sets played (score-string token count) in
                                   that same trailing-14d window, p1 minus p2
  surface_transition_flag_diff -- 1/0 whether ANY of those trailing-14d
                                   matches were on a DIFFERENT surface than
                                   today's, p1 minus p2 (in {-1, 0, 1})
"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
_TENNIS_MATCHES = REPO / "data" / "domains" / "tennis" / "matches.parquet"
_CHAIN_CORPUS = "tennis_matches_chain_asof"

CHAIN_WINDOW_DAYS = 14

_SET_TOKEN = re.compile(r"^\d+-\d+")  # e.g. "6-3" or "7-6(6)"; excludes bare "RET"/"W/O" tokens


def _n_sets(score: Any) -> int:
    if not isinstance(score, str) or not score:
        return 0
    return sum(1 for tok in score.split() if _SET_TOKEN.match(tok))


def _player_chain_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Long format: one row per (event_id, player_id) with that player's OWN
    strictly-prior chain features as of this match's date."""
    m = matches.copy()
    m["date"] = pd.to_datetime(m["date"])
    m["n_sets"] = m["score"].map(_n_sets)

    long = pd.concat([
        m[["event_id", "date", "surface", "n_sets", "p1_id"]].rename(columns={"p1_id": "player_id"}),
        m[["event_id", "date", "surface", "n_sets", "p2_id"]].rename(columns={"p2_id": "player_id"}),
    ], ignore_index=True)
    long = long.sort_values(["player_id", "date", "event_id"], kind="mergesort").reset_index(drop=True)

    out_days = np.full(len(long), np.nan)
    out_m14 = np.zeros(len(long))
    out_s14 = np.zeros(len(long))
    out_trans = np.zeros(len(long))

    for _, idx in long.groupby("player_id", sort=False).indices.items():
        idx = np.asarray(idx)
        dates = long["date"].values[idx]
        surfaces = long["surface"].values[idx]
        sets = long["n_sets"].values[idx].astype(float)
        cumsets = np.concatenate([[0.0], np.cumsum(sets)])

        cut = np.searchsorted(dates, dates, side="left")  # strictly-prior boundary (excludes same-day ties)
        window_start = np.searchsorted(dates, dates - np.timedelta64(CHAIN_WINDOW_DAYS, "D"), side="left")

        has_prior = cut > 0
        last_idx = np.clip(cut - 1, 0, None)
        days = (dates - dates[last_idx]) / np.timedelta64(1, "D")
        out_days[idx[has_prior]] = days[has_prior]

        m14 = cut - window_start
        out_m14[idx] = m14
        out_s14[idx] = cumsets[cut] - cumsets[window_start]

        for row_i in range(len(idx)):
            ws, we = window_start[row_i], cut[row_i]
            if we > ws:
                out_trans[idx[row_i]] = float(np.any(surfaces[ws:we] != surfaces[row_i]))

    long["days_since_last_match"] = out_days
    long["matches_last_14d"] = out_m14
    long["sets_played_last_14d"] = out_s14
    long["surface_transition_flag"] = out_trans
    return long[["event_id", "player_id", "days_since_last_match", "matches_last_14d",
                 "sets_played_last_14d", "surface_transition_flag"]]


_RAW_COLS = ["days_since_last_match", "matches_last_14d", "sets_played_last_14d", "surface_transition_flag"]
DIFF_ATTRS = [c + "_diff" for c in _RAW_COLS]


def build_tennis_chain_frame(matches: pd.DataFrame, attrs: List[str]) -> pd.DataFrame:
    """Match-grain frame: y, date (reserve axis), tourney_id (cluster), and
    the requested `asof__<attr>_diff` columns, p1 minus p2."""
    chain = _player_chain_features(matches)
    p1 = chain.rename(columns={c: "p1_" + c for c in _RAW_COLS}).rename(columns={"player_id": "p1_id"})
    p2 = chain.rename(columns={c: "p2_" + c for c in _RAW_COLS}).rename(columns={"player_id": "p2_id"})

    m = matches[["event_id", "date", "tourney_id", "winner", "p1_id", "p2_id"]].copy()
    m["date"] = pd.to_datetime(m["date"])
    m["y"] = (m["winner"] == 1).astype(float)
    m = m.merge(p1, on=["event_id", "p1_id"], how="left").merge(p2, on=["event_id", "p2_id"], how="left")

    for c in _RAW_COLS:
        diff = c + "_diff"
        if diff in attrs:
            m[diff] = m["p1_" + c] - m["p2_" + c]

    m = m.rename(columns={a: "asof__" + a for a in attrs if a in m.columns})
    keep = ["event_id", "date", "tourney_id", "y"] + [c for c in m.columns if c.startswith("asof__")]
    return m[keep].copy()


def _tennis_chain_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _TENNIS_MATCHES.exists():
        return None
    matches = pd.read_parquet(
        _TENNIS_MATCHES,
        columns=["event_id", "date", "surface", "score", "tourney_id", "winner", "p1_id", "p2_id"],
    )
    frame = build_tennis_chain_frame(matches, attrs)
    return {"frame": frame, "cluster": "tourney_id", "corpus": _CHAIN_CORPUS, "kind": "logit"}


def _tennis_chain_x_match_cross_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Cross vs the existing tennis_match_asof pool (return/serve stats),
    same match grain -- merge on event_id, mirrors the mlb cross-builder shape
    (builders_public_splits._mlb_public_splits_market_micro_cross_builder)."""
    from scripts.platformkit.interaction_factory import builders_task39b as _t39b

    if not _TENNIS_MATCHES.exists() or not (_t39b._TENNIS_RETURN.exists()
                                             and _t39b._TENNIS_FEATURES.exists()
                                             and _t39b._TENNIS_SETDETAIL.exists()):
        return None
    chain_attrs = [a for a in attrs if a in DIFF_ATTRS]
    match_attrs = [a for a in attrs if a not in DIFF_ATTRS]

    matches = pd.read_parquet(
        _TENNIS_MATCHES,
        columns=["event_id", "date", "surface", "score", "tourney_id", "winner", "p1_id", "p2_id"],
    )
    chain_frame = build_tennis_chain_frame(matches, chain_attrs)

    ret = pd.read_parquet(_t39b._TENNIS_RETURN)
    feats = pd.read_parquet(_t39b._TENNIS_FEATURES)
    setdetail = pd.read_parquet(_t39b._TENNIS_SETDETAIL)
    match_matches = matches[["event_id", "date", "tourney_id", "winner"]]
    match_frame = _t39b.build_tennis_match_frame(match_matches, ret, feats, match_attrs, setdetail=setdetail)

    # chain_frame already carries date + tourney_id; dropping them from the
    # match side prevents merge suffixes (_x/_y) that hid the cluster column
    # from the fit (the original 32-NT cause) and the reserve axis from the mask.
    merged = chain_frame.merge(
        match_frame.drop(columns=["y", "date", "tourney_id"], errors="ignore"),
        on="event_id", how="inner")
    return {"frame": merged, "cluster": "tourney_id", "corpus": _CHAIN_CORPUS + "_x_match", "kind": "logit"}


__all__ = [
    "build_tennis_chain_frame", "DIFF_ATTRS", "CHAIN_WINDOW_DAYS",
    "_tennis_chain_builder", "_tennis_chain_x_match_cross_builder",
]
