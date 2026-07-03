"""domains.tennis.asof_hold_wta -- WTA companion to asof_hold.py (ATP).

Leak-free per-player trailing hold% and svpts-won% (overall + per surface) for
the WTA tour, keyed by event_id.  Strictly prior-only (snapshot-before-update);
mirrors domains/tennis/asof_hold.py's exact algorithm, applied to the WTA spine.

WHY A SEPARATE MODULE: asof_hold.py's default inputs are matches.parquet (ATP
only, tour=="atp" exclusively -- verified 30,616/30,616 rows) and match_stats.parquet
filtered implicitly to ATP event_ids.  match_stats.parquet is actually a MIXED
ATP+WTA sidecar (28,696 WTA-tagged rows already on disk, built by
ingest_sackmann_matchstats.build_match_stats(tours=["atp","wta"])) but there is
no WTA spine inside matches.parquet to join it against.  The WTA spine instead
lives in wta_matches.parquet (11,270 rows, built by wta_corpus.py).  This module
is that missing join: wta_matches.parquet (spine) x match_stats.parquet's
"-wta-" event_id rows (stats) -> asof_hold_wta.parquet.

ZERO NEW NETWORK: both inputs are already on disk (data/domains/tennis/
wta_matches.parquet and match_stats.parquet).  Confirmed 100% event_id overlap
(11,270/11,270) with 90.2% non-null stat coverage (10,164/11,270) in a read-only
probe before writing this module.

APPROXIMATION: identical to asof_hold.py -- hold% = clip(1 - (bpFaced - bpSaved)
/ SvGms, 0, 1).  Clipped to [0,1].  SvGms missing -> NaN.

LEAK DISCIPLINE: match i uses only matches < i chronologically (same
(date, tour, tourney_id, round, match_num) stable sort as asof_hold.py, applied
to the WTA-only spine).  Debut players get NaN.  A no-future-leak assertion is
embedded in build_asof_hold_wta(), identical in form to assert_no_future_leak.

NETWORK: zero.  Pure pandas/numpy.  No src/kernel/api imports.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.tennis.asof_hold import (
    OUT_COLS,
    _ROUND_ORDER,
    _SURFACES,
    _derive_realized,
    _stable_chrono_sort,
    assert_no_future_leak,
)

_WTA_MATCHES_DEFAULT = "data/domains/tennis/wta_matches.parquet"
_MATCH_STATS_DEFAULT = "data/domains/tennis/match_stats.parquet"
_OUT_DEFAULT = "data/domains/tennis/asof_hold_wta.parquet"

_STATS_COLS = [
    "event_id",
    "p1_SvGms", "p1_bpFaced", "p1_bpSaved", "p1_svpt", "p1_1stWon", "p1_2ndWon",
    "p2_SvGms", "p2_bpFaced", "p2_bpSaved", "p2_svpt", "p2_1stWon", "p2_2ndWon",
]


def _filter_wta_stats(match_stats: pd.DataFrame) -> pd.DataFrame:
    """Return only the WTA-tagged rows of the mixed ATP+WTA match_stats sidecar.

    match_stats.parquet has no explicit 'tour' column; event_id is tagged
    "{date}-{tour}-..." (built by ingest_sackmann_matchstats), so the WTA rows
    are identified by "-wta-" in event_id -- the SAME tagging scheme used to
    build the event_id in wta_corpus._make_event_id and asof_hold_wta's spine.
    """
    mask = match_stats["event_id"].astype(str).str.contains("-wta-", regex=False)
    return match_stats.loc[mask].reset_index(drop=True)


def build_asof_hold_wta(
    match_stats: Optional[pd.DataFrame] = None,
    wta_matches: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free WTA as-of hold% features keyed by ``event_id``.

    Snapshot-before-update walk-forward, identical algorithm to
    asof_hold.build_asof_hold but sourced from the WTA spine + WTA-tagged stats
    subset.  Debut players get NaN.  Writes parquet and raises AssertionError on
    future-leak detection.  Returns the written Path.
    """
    if match_stats is None:
        match_stats = pd.read_parquet(_MATCH_STATS_DEFAULT)
    if wta_matches is None:
        wta_matches = pd.read_parquet(_WTA_MATCHES_DEFAULT)

    ms_wta = _filter_wta_stats(match_stats)
    avail = [c for c in _STATS_COLS if c in ms_wta.columns]
    ms_r = _derive_realized(ms_wta[avail].copy())

    spine = wta_matches[["event_id", "date", "tour", "tourney_id", "round", "match_num",
                          "p1_id", "p2_id", "surface"]].copy()
    joined = spine.merge(
        ms_r[["event_id", "p1_hold_realized", "p1_svpts_won_realized",
              "p2_hold_realized", "p2_svpts_won_realized"]],
        on="event_id", how="left",
    )
    joined = _stable_chrono_sort(joined)

    n = len(joined)
    p1_ids = pd.to_numeric(joined["p1_id"], errors="coerce").to_numpy()
    p2_ids = pd.to_numeric(joined["p2_id"], errors="coerce").to_numpy()
    surfaces = joined["surface"].fillna("Unknown").to_numpy(dtype=str)
    p1_hold = joined["p1_hold_realized"].to_numpy(dtype="float64")
    p2_hold = joined["p2_hold_realized"].to_numpy(dtype="float64")
    p1_svpts = joined["p1_svpts_won_realized"].to_numpy(dtype="float64")
    p2_svpts = joined["p2_svpts_won_realized"].to_numpy(dtype="float64")

    histories: dict[float, "_PlayerHistoryWta"] = {}
    rows: list[dict] = []

    for i in range(n):
        p1 = float(p1_ids[i]); p2 = float(p2_ids[i]); surf = surfaces[i]
        h1 = histories.setdefault(p1, _PlayerHistoryWta())
        h2 = histories.setdefault(p2, _PlayerHistoryWta())

        s1 = h1.snapshot(); s2 = h2.snapshot()
        row: dict = {
            "event_id": joined["event_id"].iloc[i],
            "p1_hold_pct_asof": s1["all_hold"], "p2_hold_pct_asof": s2["all_hold"],
            "p1_svpts_won_asof": s1["all_svpts"], "p2_svpts_won_asof": s2["all_svpts"],
            "p1_n_prior": h1.n_matches, "p2_n_prior": h2.n_matches, "surface": surf,
        }
        for s in _SURFACES:
            row[f"p1_hold_pct_{s.lower()}_asof"] = s1[f"{s}_hold"]
            row[f"p2_hold_pct_{s.lower()}_asof"] = s2[f"{s}_hold"]
            row[f"p1_svpts_won_{s.lower()}_asof"] = s1[f"{s}_svpts"]
            row[f"p2_svpts_won_{s.lower()}_asof"] = s2[f"{s}_svpts"]
        rows.append(row)

        h1.update(p1_hold[i], p1_svpts[i], surf)
        h2.update(p2_hold[i], p2_svpts[i], surf)

    result = pd.DataFrame(rows)[OUT_COLS].copy()
    result["p1_n_prior"] = result["p1_n_prior"].astype("int64")
    result["p2_n_prior"] = result["p2_n_prior"].astype("int64")

    assert_no_future_leak(result)

    dest = Path(out_path) if out_path is not None else Path(_OUT_DEFAULT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(result, preserve_index=False), dest)
    return dest


class _PlayerHistoryWta:
    """Running (sum, count) for hold% and svpts_won%, overall and per surface.

    Duplicated from asof_hold._PlayerHistory (that class is module-private,
    name-mangled by convention) rather than imported, to keep this module
    self-contained and independently testable; logic is byte-identical.
    """
    __slots__ = ("n_matches", "_sum", "_cnt")

    def __init__(self) -> None:
        self.n_matches: int = 0
        self._sum: dict[str, dict[str, float]] = {}
        self._cnt: dict[str, dict[str, int]] = {}

    def snapshot(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for key in ("all", *_SURFACES):
            s = self._sum.get(key, {}); c = self._cnt.get(key, {})
            for stat in ("hold", "svpts"):
                cnt = c.get(stat, 0)
                out[f"{key}_{stat}"] = s[stat] / cnt if cnt > 0 else np.nan
        return out

    def update(self, hold: float, svpts: float, surface: str) -> None:
        self.n_matches += 1
        for key in ("all", surface):
            s = self._sum.setdefault(key, {}); c = self._cnt.setdefault(key, {})
            if not np.isnan(hold):
                s["hold"] = s.get("hold", 0.0) + hold; c["hold"] = c.get("hold", 0) + 1
            if not np.isnan(svpts):
                s["svpts"] = s.get("svpts", 0.0) + svpts; c["svpts"] = c.get("svpts", 0) + 1


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build leak-free WTA as-of hold% features")
    parser.add_argument("--match-stats", default=_MATCH_STATS_DEFAULT)
    parser.add_argument("--wta-matches", default=_WTA_MATCHES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    parser.add_argument("--min-prior", type=int, default=5)
    args = parser.parse_args()
    from domains.tennis.asof_hold_wta_eval import run_eval  # noqa: PLC0415
    run_eval(args.match_stats, args.wta_matches, args.out_path, args.min_prior)


if __name__ == "__main__":
    _cli()
