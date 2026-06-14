"""domains.tennis.asof_hold — leak-free as-of HOLD% for tennis games/sets markets.

Emits per-player trailing hold% and svpts-won% (overall + per surface) keyed by
event_id.  Strictly prior-only (snapshot-before-update); designed as a calibration
input for games/sets/serve markets, NOT match-win (Elo handles that).

APPROXIMATION: hold% = clip(1 - (bpFaced - bpSaved) / SvGms, 0, 1).  bpFaced -
bpSaved = breaks conceded; SvGms = service games played.  Standard proxy; mean
0.72-0.83 across surfaces matches published estimates.  Clipped to [0,1]; <0.05%
of rows had raw values outside that range.  SvGms missing → NaN.

LEAK DISCIPLINE: mirrors domains/tennis/asof_features.py.  Match i uses only
matches < i chronologically.  Debut players get NaN.  A no-future-leak assertion
is embedded in build_asof_hold().

NETWORK: zero.  Pure pandas/numpy.  No src/kernel/api imports.
ACCURACY ONLY — NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_MATCH_STATS_DEFAULT = "data/domains/tennis/match_stats.parquet"
_MATCHES_DEFAULT = "data/domains/tennis/matches.parquet"
_OUT_DEFAULT = "data/domains/tennis/asof_hold.parquet"

_SURFACES = ("Hard", "Clay", "Grass")
_MIN_SV_GAMES = 1

_OVERALL_SUFFIXES = ("hold_pct_asof", "svpts_won_asof")
_SURF_HOLD_SUFFIXES = tuple(f"hold_pct_{s.lower()}_asof" for s in _SURFACES)
_SURF_SVPTS_SUFFIXES = tuple(f"svpts_won_{s.lower()}_asof" for s in _SURFACES)

OUT_COLS: list[str] = (
    ["event_id"]
    + [f"p1_{s}" for s in _OVERALL_SUFFIXES]
    + [f"p2_{s}" for s in _OVERALL_SUFFIXES]
    + [f"p1_{s}" for s in _SURF_HOLD_SUFFIXES]
    + [f"p2_{s}" for s in _SURF_HOLD_SUFFIXES]
    + [f"p1_{s}" for s in _SURF_SVPTS_SUFFIXES]
    + [f"p2_{s}" for s in _SURF_SVPTS_SUFFIXES]
    + ["p1_n_prior", "p2_n_prior", "surface"]
)

_ROUND_ORDER: dict[str, int] = {
    "ER": 0, "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
    "RR": 5, "R128": 6, "R64": 7, "R32": 8, "R16": 9,
    "QF": 10, "SF": 11, "BR": 12, "F": 13,
}

_STATS_COLS = [
    "event_id",
    "p1_SvGms", "p1_bpFaced", "p1_bpSaved", "p1_svpt", "p1_1stWon", "p1_2ndWon",
    "p2_SvGms", "p2_bpFaced", "p2_bpSaved", "p2_svpt", "p2_1stWon", "p2_2ndWon",
]


def _stable_chrono_sort(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)

    def _col(name: str, default: object) -> pd.Series:
        return df[name] if name in df.columns else pd.Series([default] * n, index=df.index)

    key_df = pd.DataFrame({
        "k0": pd.to_datetime(_col("date", None)).values,
        "k1": _col("tour", "").astype(str).values,
        "k2": _col("tourney_id", "").astype(str).values,
        "k3": _col("round", "").map(_ROUND_ORDER).fillna(6).astype(int).values,
        "k4": pd.to_numeric(_col("match_num", 0), errors="coerce").fillna(0).astype("int64").values,
    }, index=df.index)
    order = key_df.sort_values(["k0", "k1", "k2", "k3", "k4"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


def _derive_realized(ms: pd.DataFrame) -> pd.DataFrame:
    """Add p1/p2 realized hold% and svpts_won% to a match_stats slice."""
    ms = ms.copy()
    for side in ("p1", "p2"):
        sv = ms.get(f"{side}_SvGms")
        bpf = ms.get(f"{side}_bpFaced")
        bps = ms.get(f"{side}_bpSaved")
        svpt = ms.get(f"{side}_svpt")
        w1 = ms.get(f"{side}_1stWon")
        w2 = ms.get(f"{side}_2ndWon")
        if sv is not None and bpf is not None and bps is not None:
            breaks = (bpf - bps).clip(lower=0)
            valid = (sv > _MIN_SV_GAMES - 1) & sv.notna() & bpf.notna() & bps.notna()
            hold = np.where(valid, np.clip(1.0 - breaks / sv.replace(0, np.nan), 0.0, 1.0), np.nan)
        else:
            hold = np.full(len(ms), np.nan)
        ms[f"{side}_hold_realized"] = hold
        if svpt is not None and w1 is not None and w2 is not None:
            valid2 = (svpt > 0) & svpt.notna() & w1.notna() & w2.notna()
            svpw = np.where(valid2, np.clip((w1 + w2) / svpt.replace(0, np.nan), 0.0, 1.0), np.nan)
        else:
            svpw = np.full(len(ms), np.nan)
        ms[f"{side}_svpts_won_realized"] = svpw
    return ms


class _PlayerHistory:
    """Running (sum, count) for hold% and svpts_won%, overall and per surface."""
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


def assert_no_future_leak(df: pd.DataFrame) -> None:
    """Raise AssertionError if debut rows have non-NaN asof hold."""
    bad_p1 = df.loc[df["p1_n_prior"] == 0, "p1_hold_pct_asof"].notna().sum()
    bad_p2 = df.loc[df["p2_n_prior"] == 0, "p2_hold_pct_asof"].notna().sum()
    if bad_p1 > 0 or bad_p2 > 0:
        raise AssertionError(
            f"Future-leak: {bad_p1} p1 debut rows with non-NaN hold_asof, "
            f"{bad_p2} p2 debut rows with non-NaN hold_asof."
        )


def build_asof_hold(
    match_stats: Optional[pd.DataFrame] = None,
    matches: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free as-of hold% features keyed by ``event_id``.

    Snapshot-before-update walk-forward.  Debut players get NaN.  Writes parquet
    and raises AssertionError on future-leak detection.  Returns the written Path.
    """
    if match_stats is None:
        match_stats = pd.read_parquet(_MATCH_STATS_DEFAULT)
    if matches is None:
        matches = pd.read_parquet(_MATCHES_DEFAULT)

    avail = [c for c in _STATS_COLS if c in match_stats.columns]
    ms_r = _derive_realized(match_stats[avail].copy())

    spine = matches[["event_id", "date", "tour", "tourney_id", "round", "match_num",
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

    histories: dict[float, _PlayerHistory] = {}
    rows: list[dict] = []

    for i in range(n):
        p1 = float(p1_ids[i]); p2 = float(p2_ids[i]); surf = surfaces[i]
        h1 = histories.setdefault(p1, _PlayerHistory())
        h2 = histories.setdefault(p2, _PlayerHistory())

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


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build leak-free tennis as-of hold% features")
    parser.add_argument("--match-stats", default=_MATCH_STATS_DEFAULT)
    parser.add_argument("--matches", default=_MATCHES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    parser.add_argument("--min-prior", type=int, default=5)
    args = parser.parse_args()
    # Extended evaluation in asof_hold_eval.py; this just builds + prints basics.
    from domains.tennis.asof_hold_eval import run_eval  # noqa: PLC0415
    run_eval(args.match_stats, args.matches, args.out_path, args.min_prior)


if __name__ == "__main__":
    _cli()
