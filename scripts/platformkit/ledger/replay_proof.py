"""Skeptic reproduction of the track-record numbers (blueprint X3 PART B).

A skeptic runs this on the COMMITTED fixture ledger (tests/fixtures/ledger/ledger_demo.csv)
and recomputes Brier / ECE / DM-vs-close deterministically in < 30s. The fixture is the
PUBLIC proof; the live vault/_TrackRecord/ ledger is the private compounding asset.

It prints a VALIDATION_PENDING note: a live-ledger OOS-vs-close result is a HUMAN-RUN step
on a real corpus -- this proof reproduces the FIXTURE numbers, it does NOT fabricate a
real-data win. Reports Brier / ECE / DM only -- never a probability authored here, never $.
"""
from __future__ import annotations
import pathlib
import time
from typing import Optional

import numpy as np
import pandas as pd

try:  # package import when run as `-m scripts.platformkit.ledger...`
    from scripts.platformkit.ledger import metrics
except ImportError:  # direct-script / sys.path-injected (per-file test) fallback
    import metrics

_REPO = pathlib.Path(__file__).resolve().parents[3]
_FIXTURE = _REPO / "tests" / "fixtures" / "ledger" / "ledger_demo.csv"


def _load_fixture(path: Optional[pathlib.Path] = None) -> pd.DataFrame:
    p = path or _FIXTURE
    df = pd.read_csv(p)
    return df[df["outcome"].notna()].reset_index(drop=True)


def replay_proof(path: Optional[pathlib.Path] = None) -> dict:
    """Recompute calibration on the fixture and return a stable, printable summary."""
    df = _load_fixture(path)
    out = {"n_rows": int(len(df)), "by_sport": {}}
    for sport, g in df.groupby("sport"):
        market = g["market"].iloc[0]
        rep = metrics.compute_calibration(df, sport=sport, market=market)
        p = g["calibrated_prob"].to_numpy(float)
        y = g["outcome"].to_numpy(float)
        entry = {"n": int(len(g)), "market": market,
                 "brier": round(metrics.brier(p, y), 6),
                 "ece": round(metrics.ece(p, y), 6),
                 "verdict": rep.get("verdict")}
        mkt = g[g["devig_close_prob"].notna()]
        if len(mkt):
            cids = mkt["game_id"]
            dm = metrics.dm_vs_close(mkt["calibrated_prob"].to_numpy(float),
                                     mkt["devig_close_prob"].to_numpy(float),
                                     mkt["outcome"].to_numpy(float), cids)
            entry["market_brier"] = round(metrics.brier(
                mkt["devig_close_prob"].to_numpy(float),
                mkt["outcome"].to_numpy(float)), 6)
            entry["dm_p_value"] = round(dm["p_value"], 6)
        out["by_sport"][sport] = entry
    return out


def main(path: Optional[pathlib.Path] = None) -> int:
    t0 = time.time()
    out = replay_proof(path)
    dt = time.time() - t0
    print("=== ledger replay_proof (committed fixture) ===")
    print(f"fixture rows (graded): {out['n_rows']}")
    for sport, e in sorted(out["by_sport"].items()):
        mb = e.get("market_brier")
        dmp = e.get("dm_p_value")
        extra = ""
        if mb is not None:
            extra = f"  market_brier={mb:.4f}  dm_p={dmp:.4f}"
        print(f"  {sport:7s} [{e['market']}] n={e['n']:3d}  "
              f"brier={e['brier']:.4f}  ece={e['ece']:.4f}  {e['verdict']}{extra}")
    print(f"reproduced in {dt:.2f}s")
    print("VALIDATION_PENDING: live-ledger OOS-vs-close is a HUMAN-RUN step on a real "
          "corpus; this proof reproduces the FIXTURE only -- no real-data win is claimed. "
          "edge_claimed=False; honest match/REJECT is the success.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
