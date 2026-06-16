"""Freshness X1 -- the VINTAGE LEAK GUARD (the load-bearing correctness module).

The freshness lever lives or dies on vintage alignment: a delta may inform a prediction
ONLY if it was known strictly before tip-off (extracted_at < asof_ts). This module is the
sole read path the sim/backtest is meant to call. It is deliberately distinct from
domains/basketball_nba/asof_*.py -- those are box-feature (stat) readers; this one is the
injury/lineup freshness VINTAGE guard keyed on a full extracted_at timestamp.

Stdlib only. No DB dependency: the reader operates on a list of delta dicts so it is trivially
testable; the production wiring passes rows queried from SQLite ordered however -- the reader
re-sorts and supersedes internally so order in is irrelevant.
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Sequence, Set, Tuple


def _date_of(iso_ts: str) -> str:
    return datetime.fromisoformat(iso_ts).date().isoformat()


def as_of_out_ids(team_id: str, asof_ts: str, deltas: Sequence[dict],
                  statuses: Tuple[str, ...] = ("OUT",)) -> Set[str]:
    """Player_ids whose LATEST status (as-of asof_ts) is in `statuses`.

    VINTAGE GUARD -- NEVER returns a row with extracted_at >= asof_ts. For each player we
    keep only the most recent row strictly before asof_ts (supersede logic: a noon
    QUESTIONABLE is overridden by a pre-tip OUT, and vice versa). Rows on a different
    game_date or a different team are ignored.

    asof_ts at backtest time = tip_off_utc (or the prediction timestamp); in production it is
    utcnow(). This filter is the difference between a freshness edge and a leak.
    """
    asof = datetime.fromisoformat(asof_ts)
    asof_date = _date_of(asof_ts)
    latest: Dict[str, Tuple[datetime, str]] = {}
    for d in deltas:
        if str(d.get("team_id")) != str(team_id):
            continue
        if d.get("game_date") != asof_date:
            continue
        ext = datetime.fromisoformat(d["extracted_at"])
        if ext >= asof:                       # THE GUARD: strictly-before only
            continue
        pid = d["player_id"]
        prev = latest.get(pid)
        if prev is None or ext > prev[0]:
            latest[pid] = (ext, d["status"])
    return {pid for pid, (_, st) in latest.items() if st in statuses}


def assert_vintage(delta: dict, asof_ts: str) -> None:
    """LEAK GUARD assertion: the row may inform the prediction only if known before asof.

    A planted-late row (extracted_at >= asof_ts) MUST trip this. Used by tests and by
    partition_for_eval on every forward-captured row.
    """
    extracted = datetime.fromisoformat(delta["extracted_at"])
    asof = datetime.fromisoformat(asof_ts)
    assert extracted < asof, (
        f"LEAK: extracted_at {delta['extracted_at']} >= asof {asof_ts} "
        f"for {delta.get('player_id')}"
    )


def partition_for_eval(deltas: Sequence[dict], tip_off_iso: str
                       ) -> Tuple[List[dict], List[dict]]:
    """Split into (leak_free, fallback_proxy).

    leak_free: forward-captured rows with extracted_at < tip -- the ONLY rows allowed in the
               headline 'shipped + validated' calibration verdict. Each is vintage-asserted.
    fallback_proxy: rows flagged is_fallback_proxy=True -- reconstructed from post-game truth
               (selection conditioned on realized DNP). Metrics on these are OPTIMISTIC UPPER
               BOUNDS, never leak-free wins. (See proxy_quarantine.label_metric.)
    """
    leak_free: List[dict] = []
    proxy: List[dict] = []
    for d in deltas:
        if d.get("is_fallback_proxy"):
            proxy.append(d)
            continue
        assert_vintage(d, tip_off_iso)        # forward rows MUST pass the vintage guard
        leak_free.append(d)
    return leak_free, proxy
