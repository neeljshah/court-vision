"""scripts.platformkit.omni.k_refresh_job -- S15.K2 nightly incremental K
refresh (Claude-free). Recomputes ONLY player-level coverage cells for
players who played YESTERDAY, reusing k_sweep_nba's own Welch/BH/claim
functions (import-only -- this module never re-derives that math).

STEP 0 premise check (2026-07-13): k_sweep_nba's own sweep source
(data/cache/intel_claims/nba_player_box_rate__career_to_date_snapshot.parquet,
max date 2026-04-12 as of this write) is a STATIC cache -- grepping scripts/
+ src/ finds only k_sweep_nba.py reading it; no builder in this repo
refreshes it nightly, and no fresher per-player box store exists on disk
today. This job therefore reads the SAME store k_sweep_nba uses (a `source`
override exists for tests only) and is HONEST about the common case right
now: the cache's last game is 2026-04-12 and today is deep NBA off-season, so
every real invocation until a fresher box store lands (or the 2026-27 season
starts) is a no-op heartbeat, never a silent skip.

RECOMPUTE SCOPE: only PLAYER-level cells (k_coverage's own grain, ACTIVE
players only -- k_coverage.load_matrix's own roster) for players with >=1
row dated yesterday, across k_sweep_nba.CONDITIONS. League- and archetype-
level rows are k_sweep_nba's full-sweep concern, not a k_coverage cell, so
this incremental job skips them.

INVARIANTS: pandas via k_sweep_nba import only. <=300 LOC. ASCII stdout.
Never writes data/registry/. No $/edge claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_omni_k_refresh_job.py -q
"""
from __future__ import annotations

import pathlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.io_atomic import append_jsonl_atomic
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni import k_sweep_nba as ksn

_HEARTBEAT_PATH = pathlib.Path("data/omni/k/k_refresh_heartbeat.jsonl")


def _yesterday(today: Optional[date] = None) -> date:
    return (today or datetime.now(timezone.utc).date()) - timedelta(days=1)


def _log_heartbeat(path: pathlib.Path, row: Dict[str, Any]) -> None:
    stamped = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **row}
    append_jsonl_atomic(path, stamped)


def _touched_player_ids(df: pd.DataFrame, day: date) -> List[int]:
    hits = df.loc[df["date"].dt.date == day, "player_id"]
    return sorted(hits.unique().tolist())


def _mine_touched(df: pd.DataFrame, condition: str, touched_ids: List[int]) -> List[dict]:
    """Player-level Welch cells for *touched_ids* only, reusing k_sweep_nba's
    own condition-label + Welch-split functions (no re-derivation)."""
    side_a, side_b, label_a, label_b = ksn._condition_labels(df, condition)  # noqa: SLF001
    sub = df.copy()
    sub["side"] = pd.NA
    sub.loc[side_a, "side"] = label_a
    sub.loc[side_b, "side"] = label_b
    sub = sub[sub["side"].notna() & sub["player_id"].isin(touched_ids)]
    out = []
    for pid, g in sub.groupby("player_id"):
        a_vals = g.loc[g["side"] == label_a, ksn._STAT]  # noqa: SLF001
        b_vals = g.loc[g["side"] == label_b, ksn._STAT]  # noqa: SLF001
        n_a, n_b = len(a_vals), len(b_vals)
        if n_a < ksn.MIN_SIDE_N or n_b < ksn.MIN_SIDE_N:
            out.append({"level": "player", "key": int(pid), "condition": condition,
                        "insufficient": True, "n_a": n_a, "n_b": n_b})
            continue
        res = ksn._welch_split(a_vals, b_vals)  # noqa: SLF001
        if res:
            out.append({"level": "player", "key": int(pid), "condition": condition, **res})
    return out


def run_k_refresh(base_dir=None, source=None, today: Optional[date] = None,
                   heartbeat_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """Nightly incremental K refresh. Recomputes touched (yesterday-played,
    active-roster) players' cells only; off-season/no-games nights (the
    common case right now) log a heartbeat and no-op."""
    hb_path = pathlib.Path(heartbeat_path) if heartbeat_path is not None else _HEARTBEAT_PATH
    yday = _yesterday(today)
    df = ksn._load_sweep_frame(source)  # noqa: SLF001 -- reuse, not re-derive
    raw_touched = _touched_player_ids(df, yday)
    if not raw_touched:
        row = {"status": "no_games", "date": str(yday), "touched_players": 0}
        _log_heartbeat(hb_path, row)
        return row

    active_ids = set(kc.load_matrix(base_dir)["player_id"])
    touched_ids = [p for p in raw_touched if p in active_ids]
    if not touched_ids:
        row = {"status": "no_active_touched", "date": str(yday),
               "touched_players_raw": len(raw_touched), "touched_players": 0}
        _log_heartbeat(hb_path, row)
        return row

    max_date = df["date"].max()
    data_asof = max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else None
    existing_ids = set(cl.query(sport="nba", base_dir=base_dir)["claim_id"])

    cells: List[dict] = []
    for condition in ksn.CONDITIONS:
        cells.extend(_mine_touched(df, condition, touched_ids))

    tested = [c for c in cells if "p" in c]
    for c, adj in zip(tested, ksn.bh_adjust([c["p"] for c in tested])):
        c["p_adj"] = adj

    claims_added, escalations, player_status = 0, 0, {}
    for cell in cells:
        claim, escalate = ksn._claim_for_cell(cell, data_asof)  # noqa: SLF001
        claim_id = cl.make_claim_id(claim["statement"], claim["scope"])
        if claim_id not in existing_ids:
            cl.add_claim(claim, base_dir=base_dir)
            existing_ids.add(claim_id)
            claims_added += 1
        if escalate:
            escalations += 1
        status = "ESCALATED" if escalate else ("INSUFFICIENT_DATA" if cell.get("insufficient") else "MINED")
        player_status.setdefault(cell["key"], []).append(status)

    for pid, statuses in player_status.items():
        best = max(statuses, key=lambda s: ksn._STATUS_PRIORITY[s])  # noqa: SLF001
        kc.update_cell(pid, ksn._DIMENSION, best, len(statuses), base_dir=base_dir)  # noqa: SLF001

    metrics = kc.k5_metrics(base_dir=base_dir)
    row = {
        "status": "ran", "date": str(yday), "touched_players": len(touched_ids),
        "cells_recomputed": len(cells), "claims_added": claims_added,
        "escalations": escalations, "coverage_pct_overall": metrics.get("coverage_pct_overall"),
    }
    _log_heartbeat(hb_path, row)
    return row


if __name__ == "__main__":
    print(f"[k_refresh_job] {run_k_refresh()}")


__all__ = ["run_k_refresh"]
