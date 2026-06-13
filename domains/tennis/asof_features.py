"""domains.tennis.asof_features — leak-free walk-forward AS-OF serve/return form.

WHAT: ``build_asof_features`` joins the W59 ``match_stats.parquet`` sidecar
(per-match serve/return rates, keyed ``event_id``) to the main ``matches.parquet``
(``event_id``, ``date``, ``p1_id``, ``p2_id``) and, for EACH match in chronological
order, records each player's PRIOR-ONLY trailing serve/return form — the expanding
mean of their rates over their STRICTLY-PRIOR matches (where the player may have
occupied EITHER the p1 or p2 slot).  Output is keyed 1:1 by ``event_id``.

⚠️ LEAK NOTE: the feature for match *i* uses ONLY matches with ``date < match i``'s
date for each player (snapshot-BEFORE-update).  We walk forward; for each match we
(1) read each player's accumulated history, (2) emit the trailing means, and THEN
(3) push this match's own rates into that player's history.  A match's own stats
NEVER touch its own row — that would be a label leak (a match's serve stats are
descriptive facts of the match itself).  When a player has zero prior matches we
emit NaN (no fabricated prior).  This deepens the data substrate / calibration; it
makes NO market-edge claim.

NETWORK: ZERO.  Pure pandas/numpy transform.  F5-clean: stdlib + numpy/pandas only;
no ``src.*`` / ``kernel.*`` / ``domains.nba`` imports.

LICENSE: derived from Sackmann CC BY-NC-SA — private research only; never tracked.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Default IO paths (relative to repo root).
_MATCH_STATS_DEFAULT = "data/domains/tennis/match_stats.parquet"
_MATCHES_DEFAULT = "data/domains/tennis/matches.parquet"
_OUT_DEFAULT = "data/domains/tennis/asof_features.parquet"

# The five per-match serve/return rates we carry forward as trailing form.
# (sidecar column suffix, output asof suffix)
_RATE_MAP: tuple[tuple[str, str], ...] = (
    ("ace_rate", "ace_rate_asof"),
    ("1st_in_pct", "1st_in_asof"),
    ("1st_win_pct", "1st_win_asof"),
    ("2nd_win_pct", "2nd_win_asof"),
    ("bp_saved_pct", "bp_saved_asof"),
)

# Output asof suffixes in canonical order (used for schema + diffs).
_ASOF_SUFFIXES: tuple[str, ...] = tuple(out for _, out in _RATE_MAP)

OUT_COLS: list[str] = (
    ["event_id"]
    + [f"p1_{s}" for s in _ASOF_SUFFIXES]
    + [f"p2_{s}" for s in _ASOF_SUFFIXES]
    + [f"diff_{s}" for s in _ASOF_SUFFIXES]
    + ["p1_n_prior", "p2_n_prior"]
)

# Tiebreaker columns for a stable chronological sort (mirrors elo_core._sort_key).
_ROUND_ORDER: dict[str, int] = {
    "ER": 0, "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
    "RR": 5, "R128": 6, "R64": 7, "R32": 8, "R16": 9,
    "QF": 10, "SF": 11, "BR": 12, "F": 13,
}


def _stable_chrono_sort(matches: pd.DataFrame) -> pd.DataFrame:
    """Sort matches by date, then the same secondary keys elo_core pins.

    Primary: ``date``.  Secondary (when present): ``tour``, ``tourney_id``,
    ``round`` (mapped to its bracket order, unknown -> mid value 6), ``match_num``.
    Uses a stable mergesort so equal-key rows keep their original relative order.
    """
    df = matches.copy()
    n = len(df)

    def _col(name: str, default: object) -> pd.Series:
        if name in df.columns:
            return df[name]
        return pd.Series([default] * n, index=df.index)

    date_key = pd.to_datetime(_col("date", None)).astype("datetime64[ns]")
    tour_key = _col("tour", "").astype(str)
    tourney_key = _col("tourney_id", "").astype(str)
    round_key = _col("round", "").map(_ROUND_ORDER).fillna(6).astype(int)
    mn_key = pd.to_numeric(_col("match_num", 0), errors="coerce").fillna(0).astype("int64")

    key_df = pd.DataFrame(
        {
            "k0": date_key.values,
            "k1": tour_key.values,
            "k2": tourney_key.values,
            "k3": round_key.values,
            "k4": mn_key.values,
        },
        index=df.index,
    )
    order = key_df.sort_values(["k0", "k1", "k2", "k3", "k4"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


def build_asof_features(
    match_stats: Optional[pd.DataFrame] = None,
    matches: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free trailing serve/return AS-OF features, keyed ``event_id``.

    Parameters
    ----------
    match_stats:
        The W59 sidecar DataFrame (one row per ``event_id`` with ``p1_*`` / ``p2_*``
        per-match rates).  If ``None``, read from the default parquet path.
    matches:
        The main matches DataFrame (``event_id``, ``date``, ``p1_id``, ``p2_id`` and
        optional sort tiebreakers).  If ``None``, read from the default parquet path.
    out_path:
        Destination parquet path.  If ``None``, write to the default path.  The
        returned ``Path`` is always the file actually written.

    Returns
    -------
    Path
        The written parquet path.

    LEAK-FREE GUARANTEE: for each match, the emitted ``*_asof`` value is the expanding
    mean of that player's rates over matches with ``date`` strictly before this match's
    date (snapshot taken BEFORE this match's own rates are added to the history).  A
    player with no prior matches gets NaN.  Diffs are ``p1_asof - p2_asof`` (NaN if
    either side is NaN).  No edge is claimed.
    """
    if match_stats is None:
        match_stats = pd.read_parquet(_MATCH_STATS_DEFAULT)
    if matches is None:
        matches = pd.read_parquet(_MATCHES_DEFAULT)

    # Join the sidecar rates onto the matches spine (event_id 1:1).  We keep every
    # matches row even if the sidecar lacks it (left join) -> such rows get NaN rates.
    spine_cols = [c for c in matches.columns]
    spine = matches[spine_cols].copy()
    rate_cols = [f"{side}_{suf}" for side in ("p1", "p2") for suf, _ in _RATE_MAP]
    stats_keep = ["event_id"] + [c for c in rate_cols if c in match_stats.columns]
    joined = spine.merge(match_stats[stats_keep], on="event_id", how="left")

    joined = _stable_chrono_sort(joined)

    n = len(joined)
    p1_ids = pd.to_numeric(joined["p1_id"], errors="coerce").to_numpy()
    p2_ids = pd.to_numeric(joined["p2_id"], errors="coerce").to_numpy()

    # Pre-extract each player's per-match rate arrays for both slots.
    p1_rates = {suf: joined.get(f"p1_{suf}", pd.Series([np.nan] * n)).to_numpy(dtype="float64")
                for suf, _ in _RATE_MAP}
    p2_rates = {suf: joined.get(f"p2_{suf}", pd.Series([np.nan] * n)).to_numpy(dtype="float64")
                for suf, _ in _RATE_MAP}

    # Per-player running history indexed by player_id: for each rate a running
    # (sum, count) so the trailing mean = sum/count over PRIOR matches only.
    # count is per-rate because an individual rate may be NaN for some matches.
    hist_sum: dict[float, dict[str, float]] = {}
    hist_cnt: dict[float, dict[str, int]] = {}
    hist_matches: dict[float, int] = {}  # total prior matches for the player (n_prior)

    out: dict[str, list[float]] = {c: [] for c in OUT_COLS if c != "event_id"}
    event_ids: list[str] = list(joined["event_id"].astype(str).values)

    def _player_asof(pid: float) -> dict[str, float]:
        """Trailing means for a player's PRIOR matches; NaN where no prior value."""
        sums = hist_sum.get(pid)
        cnts = hist_cnt.get(pid)
        res: dict[str, float] = {}
        for suf, _ in _RATE_MAP:
            if cnts is None or cnts.get(suf, 0) == 0:
                res[suf] = np.nan
            else:
                res[suf] = sums[suf] / cnts[suf]
        return res

    def _update(pid: float, rates: dict[str, float], idx: int) -> None:
        """Push this match's rates into the player's history (after the snapshot)."""
        if np.isnan(pid):
            return
        s = hist_sum.setdefault(pid, {})
        c = hist_cnt.setdefault(pid, {})
        for suf, _ in _RATE_MAP:
            v = rates[suf][idx]
            if not np.isnan(v):
                s[suf] = s.get(suf, 0.0) + float(v)
                c[suf] = c.get(suf, 0) + 1
        hist_matches[pid] = hist_matches.get(pid, 0) + 1

    for i in range(n):
        p1 = p1_ids[i]
        p2 = p2_ids[i]

        # ---- SNAPSHOT BEFORE UPDATE (leak-free) ----
        a1 = _player_asof(p1)
        a2 = _player_asof(p2)
        n1 = hist_matches.get(p1, 0)
        n2 = hist_matches.get(p2, 0)

        for suf, outsuf in _RATE_MAP:
            v1 = a1[suf]
            v2 = a2[suf]
            out[f"p1_{outsuf}"].append(v1)
            out[f"p2_{outsuf}"].append(v2)
            # Diff is p1 - p2 (NaN if either side NaN, which subtraction yields).
            out[f"diff_{outsuf}"].append(v1 - v2)
        out["p1_n_prior"].append(n1)
        out["p2_n_prior"].append(n2)

        # ---- UPDATE HISTORIES with this match's values ----
        _update(p1, p1_rates, i)
        _update(p2, p2_rates, i)

    result = pd.DataFrame({"event_id": event_ids})
    for c in OUT_COLS:
        if c == "event_id":
            continue
        result[c] = out[c]
    result["p1_n_prior"] = result["p1_n_prior"].astype("int64")
    result["p2_n_prior"] = result["p2_n_prior"].astype("int64")
    result = result[OUT_COLS].copy()

    dest = Path(out_path) if out_path is not None else Path(_OUT_DEFAULT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(result, preserve_index=False), dest)
    return dest


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build leak-free tennis AS-OF serve/return form")
    parser.add_argument("--match-stats", default=_MATCH_STATS_DEFAULT)
    parser.add_argument("--matches", default=_MATCHES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    args = parser.parse_args()

    ms = pd.read_parquet(args.match_stats)
    mt = pd.read_parquet(args.matches)
    dest = build_asof_features(match_stats=ms, matches=mt, out_path=args.out_path)
    df = pd.read_parquet(dest)

    both_prior = ((df["p1_n_prior"] >= 1) & (df["p2_n_prior"] >= 1)).mean() * 100.0
    print(f"asof_features: {len(df)} rows written -> {dest}")
    print(f"coverage (both players >=1 prior): {both_prior:.1f}%")
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(df.head(3).to_string())


if __name__ == "__main__":
    _cli()
