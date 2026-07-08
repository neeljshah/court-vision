"""Tidy-prep: raw Kalshi orderbook snapshots (data/cache/depth_history/<sport>/
*.jsonl -- yes_bids/yes_asks + depth_totals per ticker per snapshot) -> one
row per (sport, ticker, ts) book-imbalance observation, written to
data/domains/cross_sport_market/depth_imbalance.parquet.

This is census-rank-8's "cross_sport_market depth_imbalance_descriptors"
source. `obs_id` = ticker + "_" + ts is unique by construction (verified this
session: 0 duplicates across all 6 sports' captures) so the factory's
count_distinct(floor_col) floor never undercounts.

NOTE: a "favorite vs underdog" ticker sub-bucket (mid-price >= 0.5) was tried
this session and dropped -- on the real data EVERY row's mid-price is < 0.5
(100% "underdog" by that split, checked directly), so it does not actually
partition anything; entity_key stays plain `sport` instead of a bucket that
looks finer but carries zero real information (ponytail: don't add a split
that doesn't split).

DESCRIPTIVE ONLY: imbalance = (bid_depth - ask_depth)/(bid_depth+ask_depth)
from Kalshi's own resting-order totals at capture time. No forecast, no $
figure -- edge_claimed:false enforced downstream by claims_factory.py.

CLI: python -m scripts.platformkit.quant.depth_imbalance_prep
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa

from scripts.platformkit.intel_validation.basketball_claims_io import atomic_write_parquet

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPTH_HISTORY_DIR = REPO_ROOT / "data" / "cache" / "depth_history"
OUT_PATH = REPO_ROOT / "data" / "domains" / "cross_sport_market" / "depth_imbalance.parquet"
_SPORTS = ("kbo", "mlb", "npb", "soccer_intl", "tennis", "wnba")  # nba: no captures this window


def _load_sport_raw(sport: str) -> pd.DataFrame:
    rows = []
    for fn in sorted(glob.glob(str(DEPTH_HISTORY_DIR / sport / "*.jsonl"))):
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    return pd.DataFrame(rows)


def _prep_sport(sport: str) -> pd.DataFrame:
    df = _load_sport_raw(sport)
    if df.empty or "depth_totals" not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=["ticker", "ts", "depth_totals"])
    totals = df["depth_totals"].apply(pd.Series)
    df["yes_bid_total"] = totals.get("yes_bid_total")
    df["yes_ask_total"] = totals.get("yes_ask_total")
    df = df.dropna(subset=["yes_bid_total", "yes_ask_total"])
    denom = df["yes_bid_total"] + df["yes_ask_total"]
    df = df[denom > 0].copy()
    df["imbalance"] = (df["yes_bid_total"] - df["yes_ask_total"]) / denom[denom > 0]
    df["bid_heavy_flag"] = (df["imbalance"] > 0).astype(int)
    df["obs_id"] = df["ticker"].astype(str) + "_" + df["ts"].astype(str)
    return df[["sport", "ticker", "ts", "yes_bid_total", "yes_ask_total", "imbalance", "bid_heavy_flag", "obs_id"]]


def build(out_path: Path | None = None) -> dict:
    out_path = out_path or OUT_PATH
    parts = [p for s in _SPORTS if not (p := _prep_sport(s)).empty]
    combined = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    atomic_write_parquet(pa.Table.from_pandas(combined, preserve_index=False), out_path)
    coverage = combined.groupby("sport").size().to_dict() if not combined.empty else {}
    return {"out_path": str(out_path), "n_rows": len(combined), "coverage_by_sport": coverage}


def main() -> int:
    summary = build()
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
