"""domains.soccer.asof_xg_proxy -- leak-free as-of EXPECTED-GOALS PROXY (shots-based).

A team's shot-based expected output -- attacking xG generated and defensive xG conceded
-- as a leak-free prior. This is a CRUDE SHOTS PROXY, NOT true xG: there is no
shot-location / shot-quality data on disk, so we approximate

    xg = K_SOT * shots_on_target + K_OFF * (shots - shots_on_target)

with corpus-rough conversion weights. It is DISTINCT from domains.soccer.finishing_asof
(which is the goals-MINUS-SoT-expectation finishing RESIDUAL, i.e. hot/cold finishing);
this is the expected-output LEVEL, for/against.

Built from match_stats.parquet ALONE (event_id, date, home/away shots + sot), keyed by
event_id (the proof base bundle's key). DOGFOODS scripts.platformkit.asof_common
(ExpandingMean per team; home/away slots share per-team state). Prior-only
(snapshot-before-update); debut -> NaN; no-future-leak assertion inherited.

NETWORK: zero. PURE pandas/numpy + asof_common. ASCII only.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED; "xg" here is an explicit PROXY label.
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

_MATCH_STATS_DEFAULT = "data/domains/soccer/match_stats.parquet"
_OUT_DEFAULT = "data/domains/soccer/asof_xg_proxy.parquet"

# Crude corpus-rough conversion weights (goals per shot-on-target / per off-target shot).
K_SOT = 0.33
K_OFF = 0.03
_METRICS = ("xg_for", "xg_against")


def _num(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype="float64")


def _xg(shots: np.ndarray, sot: np.ndarray) -> np.ndarray:
    """Shots-based expected-goals PROXY = K_SOT*SoT + K_OFF*(shots - SoT)."""
    off = np.clip(shots - sot, 0.0, None)
    return K_SOT * sot + K_OFF * off


def _derive_realized(ms: pd.DataFrame) -> pd.DataFrame:
    """Add home_/away_ realized xG-proxy for/against from the shot lines."""
    hs, hsot = _num(ms["home_shots"]), _num(ms["home_sot"])
    as_, asot = _num(ms["away_shots"]), _num(ms["away_sot"])
    home_xg = _xg(hs, hsot)
    away_xg = _xg(as_, asot)
    return pd.DataFrame({
        "event_id": ms["event_id"].astype(str).to_numpy(),
        "date": ms["date"].to_numpy(),
        "home_team": ms["home_team"].astype(str).to_numpy(),
        "away_team": ms["away_team"].astype(str).to_numpy(),
        "home_xg_for": home_xg, "home_xg_against": away_xg,
        "away_xg_for": away_xg, "away_xg_against": home_xg,
    })


def build_asof_xg_proxy(
    match_stats: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free as-of xG-proxy features keyed by event_id; write parquet."""
    if match_stats is None:
        match_stats = pd.read_parquet(_MATCH_STATS_DEFAULT)
    spine = _derive_realized(match_stats)

    result = pd.DataFrame({"event_id": spine["event_id"].to_numpy()})
    for i, m in enumerate(_METRICS):
        spec = AsofSpec(
            sort_keys=["date", "event_id"],
            slots=[("home_team", f"home_{m}", f"home_{m}"),
                   ("away_team", f"away_{m}", f"away_{m}")],
        )
        res = walk_forward_asof(spine, spec, ExpandingMean)
        cols = ["event_id", f"home_{m}_asof", f"away_{m}_asof"]
        if i == 0:
            res = res.rename(columns={f"home_{m}_n_prior": "home_n_prior",
                                      f"away_{m}_n_prior": "away_n_prior"})
            cols += ["home_n_prior", "away_n_prior"]
        result = result.merge(res[cols], on="event_id", how="left")
        result[f"diff_{m}_asof"] = result[f"home_{m}_asof"] - result[f"away_{m}_asof"]

    # xG supremacy = (xg_for - xg_against); the diff is the net expected-output dominance.
    result["home_xg_supremacy_asof"] = result["home_xg_for_asof"] - result["home_xg_against_asof"]
    result["away_xg_supremacy_asof"] = result["away_xg_for_asof"] - result["away_xg_against_asof"]
    result["diff_xg_supremacy_asof"] = (
        result["home_xg_supremacy_asof"] - result["away_xg_supremacy_asof"])

    dest = Path(out_path) if out_path is not None else Path(_OUT_DEFAULT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(result, preserve_index=False), dest)
    return dest


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build leak-free soccer as-of xG-proxy features")
    parser.add_argument("--match-stats", default=_MATCH_STATS_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    args = parser.parse_args()
    from domains.soccer.asof_xg_proxy_eval import run_eval  # noqa: PLC0415
    run_eval(args.match_stats, args.out_path)


if __name__ == "__main__":
    _cli()
