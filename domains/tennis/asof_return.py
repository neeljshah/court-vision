"""domains.tennis.asof_return -- leak-free as-of RETURN-game features (surface-split).

The serve side already has domains.tennis.asof_hold (hold% / svpts-won, per surface).
RETURN is the distinct, missing dimension: how a player performs against the
OPPONENT's serve. Derived from the SAME match_stats sidecar by reading the opponent's
serve line:

  p1 return-points-won  = 1 - (p2_1stWon + p2_2ndWon) / p2_svpt
  p1 break%             = clip((p2_bpFaced - p2_bpSaved) / p2_SvGms, 0, 1)
  (and symmetric for p2 from p1's serve line)

Emits per-player trailing as-of return-won% and break% (overall + per surface) keyed
by event_id, plus the p1-p2 diffs the gate tests. DOGFOODS the shared walk-forward
primitive scripts.platformkit.asof_common: per-surface buckets use the NaN-mask trick
(obs = value on that surface else NaN) so one ExpandingMean reproduces asof_hold's
per-surface semantics. Strictly prior-only (snapshot-before-update); debut -> NaN; a
no-future-leak assertion is inherited from asof_common.

NETWORK: zero. PURE pandas/numpy + asof_common + read-only asof_hold reuse.
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

from scripts.platformkit.asof_common import AsofSpec, ExpandingMean, walk_forward_asof
from domains.tennis.asof_hold import _STATS_COLS, _stable_chrono_sort

_MATCH_STATS_DEFAULT = "data/domains/tennis/match_stats.parquet"
_MATCHES_DEFAULT = "data/domains/tennis/matches.parquet"
_OUT_DEFAULT = "data/domains/tennis/asof_return.parquet"

_SURFACES = ("Hard", "Clay", "Grass")
_METRICS = ("return_won", "break_pct")
_SORT_KEYS = ("date", "tour", "tourney_id", "round", "match_num")


def _derive_realized_return(ms: pd.DataFrame) -> pd.DataFrame:
    """Add p1/p2 realized return-won% and break% (computed from the OPPONENT serve line)."""
    ms = ms.copy()
    # p1 returns against p2's serve, and vice-versa.
    for me, opp in (("p1", "p2"), ("p2", "p1")):
        svpt = ms.get(f"{opp}_svpt")
        w1 = ms.get(f"{opp}_1stWon")
        w2 = ms.get(f"{opp}_2ndWon")
        svg = ms.get(f"{opp}_SvGms")
        bpf = ms.get(f"{opp}_bpFaced")
        bps = ms.get(f"{opp}_bpSaved")
        if svpt is not None and w1 is not None and w2 is not None:
            valid = (svpt > 0) & svpt.notna() & w1.notna() & w2.notna()
            rw = np.where(valid, np.clip(1.0 - (w1 + w2) / svpt.replace(0, np.nan), 0.0, 1.0), np.nan)
        else:
            rw = np.full(len(ms), np.nan)
        ms[f"{me}_return_won_realized"] = rw
        if svg is not None and bpf is not None and bps is not None:
            breaks = (bpf - bps).clip(lower=0)
            valid2 = (svg > 0) & svg.notna() & bpf.notna() & bps.notna()
            bp = np.where(valid2, np.clip(breaks / svg.replace(0, np.nan), 0.0, 1.0), np.nan)
        else:
            bp = np.full(len(ms), np.nan)
        ms[f"{me}_break_pct_realized"] = bp
    return ms


def _surface_masked(values: np.ndarray, surfaces: np.ndarray, surf: str) -> np.ndarray:
    """Return values where surface matches ``surf`` else NaN (the per-surface bucket trick)."""
    out = values.astype("float64").copy()
    out[surfaces != surf] = np.nan
    return out


def build_asof_return(
    match_stats: Optional[pd.DataFrame] = None,
    matches: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free as-of return features keyed by event_id; write parquet, return Path."""
    if match_stats is None:
        match_stats = pd.read_parquet(_MATCH_STATS_DEFAULT)
    if matches is None:
        matches = pd.read_parquet(_MATCHES_DEFAULT)

    avail = [c for c in _STATS_COLS if c in match_stats.columns]
    ms_r = _derive_realized_return(match_stats[avail].copy())

    spine = matches[["event_id", "date", "tour", "tourney_id", "round", "match_num",
                     "p1_id", "p2_id", "surface"]].copy()
    realized_cols = [f"{s}_{m}_realized" for s in ("p1", "p2") for m in _METRICS]
    spine = spine.merge(ms_r[["event_id", *realized_cols]], on="event_id", how="left")
    spine = _stable_chrono_sort(spine)  # domain chrono order...
    spine["p1_id"] = pd.to_numeric(spine["p1_id"], errors="coerce")
    spine["p2_id"] = pd.to_numeric(spine["p2_id"], errors="coerce")
    surfaces = spine["surface"].fillna("Unknown").to_numpy(dtype=str)

    # ...then asof_common sorts by date only; mergesort stability preserves the order.
    result = pd.DataFrame({"event_id": spine["event_id"].to_numpy()})

    for metric in _METRICS:
        # Overall pass: both slots share per-player ExpandingMean (state keyed by id).
        spec = AsofSpec(
            sort_keys=["date"],
            slots=[("p1_id", f"p1_{metric}_realized", f"p1_{metric}"),
                   ("p2_id", f"p2_{metric}_realized", f"p2_{metric}")],
        )
        overall = walk_forward_asof(spine, spec, ExpandingMean)
        keep = ["event_id", f"p1_{metric}_asof", f"p2_{metric}_asof",
                f"p1_{metric}_n_prior", f"p2_{metric}_n_prior"]
        result = result.merge(overall[keep], on="event_id", how="left")
        result[f"diff_{metric}_asof"] = (
            result[f"p1_{metric}_asof"] - result[f"p2_{metric}_asof"])

        # Per-surface buckets via the NaN-mask trick (obs on that surface else NaN).
        for surf in _SURFACES:
            sl = surf.lower()
            sw = spine.copy()
            for side in ("p1", "p2"):
                sw[f"{side}_{metric}_{surf}"] = _surface_masked(
                    sw[f"{side}_{metric}_realized"].to_numpy(dtype="float64"), surfaces, surf)
            sspec = AsofSpec(
                sort_keys=["date"],
                slots=[("p1_id", f"p1_{metric}_{surf}", f"p1_{metric}_{sl}"),
                       ("p2_id", f"p2_{metric}_{surf}", f"p2_{metric}_{sl}")],
            )
            sres = walk_forward_asof(sw, sspec, ExpandingMean)
            keep_s = ["event_id", f"p1_{metric}_{sl}_asof", f"p2_{metric}_{sl}_asof"]
            result = result.merge(sres[keep_s], on="event_id", how="left")

    result = result.merge(spine[["event_id", "surface"]], on="event_id", how="left")

    dest = Path(out_path) if out_path is not None else Path(_OUT_DEFAULT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(result, preserve_index=False), dest)
    return dest


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build leak-free tennis as-of RETURN features")
    parser.add_argument("--match-stats", default=_MATCH_STATS_DEFAULT)
    parser.add_argument("--matches", default=_MATCHES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    args = parser.parse_args()
    from domains.tennis.asof_return_eval import run_eval  # noqa: PLC0415
    run_eval(args.match_stats, args.matches, args.out_path)


if __name__ == "__main__":
    _cli()
