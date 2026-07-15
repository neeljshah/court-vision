"""scripts.platformkit.paper.settle_sweep -- retry + terminate stale open paper
positions (EXECUTION_BACKLOG.md lever 7).

Settlers already exist per channel/market (grade_paper_asof.backfill_as_of for
game moneyline incl. kbo/npb; bestbets.prop_settler.settle_open_props for mlb/
soccer/soccer_intl props; ingame.ingame_paper_settle.settle_open for the
paper_ingame channel) but nothing SWEEPS the aged backlog through them on a
schedule, and none of them has a terminal state for a row that can NEVER route.
This module only IMPORTS those settlers -- it never reimplements outcome/CLV
logic. The supervised daemon entry (heartbeat + --interval loop) lives in the
sibling settle_sweep_daemon.py (LOC-rail split, same precedent as grade_paper.py
/ grade_paper_asof.py / grade_paper_one.py).

IDENTITY: a clv_ledger.record_bet row carries bet_id; an in-game (channel=
"paper_ingame") row carries only edge_key -- and its SETTLED twin carries
BOTH (clv_settle_write back-fills a minted bet_id). _identities() reads every
key present -- never invents one -- so pairing ("never double-settle") holds
for both conventions and across the mixed-key twin case.

VOID rows use status="settled" + outcome=VOID_OUTCOME (NOT the literal string
"VOID_UNRESOLVABLE" as the status) -- a deliberate, verified deviation: see
docs/research/execution-quality/settle_sweep_findings.md for the full trace of
why (paper_trail.clv_summary's n_open counts status != "settled", so any other
status double-counts the bet as still-open). clv_pct=None/clv_is_proxy=False/
clv_status="no_close" reuse the existing no-close sentinel (already excluded
from clv_ledger.clv_summary, paper_trail.clv_summary, circuit_breaker.
rolling_clv); ``graded`` stays unset so grade_paper_summary never sees it.
unit_result=0.0 = stake returned. VOID is reserved for two narrow classes only
(malformed_identity, no_settler_wired_for_sport_market) -- never a heuristic
guess; everything else stays a reported, un-voided "settler ran, no data yet".

PAPER / UNITS only. No $ figure. <=300 LOC; ASCII; no secrets; no $-edge.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/paper/test_settle_sweep.py -q
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit import clv_ledger as _clv

logger = logging.getLogger(__name__)

MIN_AGE_DAYS = 7.0  # mirrors the lever's own "older than 7 days" framing
_PROP_RESOLVER_SPORTS = ("mlb", "soccer", "soccer_intl")
VOID_OUTCOME = "VOID_UNRESOLVABLE"

REASON_MALFORMED = "malformed_identity"
REASON_NO_RESOLVER = "no_settler_wired_for_sport_market"
REASON_ROUTE_ML = "route_game_ml_backfill"
REASON_ROUTE_PROP = "route_prop_settler"
REASON_ROUTE_INGAME = "route_ingame_paper_settle"
_VOID_ELIGIBLE = (REASON_MALFORMED, REASON_NO_RESOLVER)


def _age_days(row: Dict[str, Any], now: datetime) -> Optional[float]:
    ts = str(row.get("ts") or "")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return None


def _age_bucket(days: Optional[float]) -> Optional[str]:
    """None below MIN_AGE_DAYS (not part of this backlog); else 7-14d/14-30d/>30d."""
    if days is None or days < MIN_AGE_DAYS:
        return None
    if days < 14:
        return "7-14d"
    if days < 30:
        return "14-30d"
    return ">30d"


def _identities(row: Dict[str, Any]) -> List[str]:
    """EVERY identity key a row carries: bet_id (clv_ledger rows), edge_key
    (in-game rows), settle_key. ALL of them, not the first -- a settled
    in-game twin carries BOTH a minted bet_id (clv_settle_write back-fills it)
    AND the edge_key its open row is keyed by; matching only one side's first
    key would miss the pair and overcount the open backlog (proven on the
    real ledger 2026-07-15: 377 phantom 'open' in-game rows m27 had already
    settled). Never invents an id for a row that never had one."""
    return [str(row[k]) for k in ("bet_id", "edge_key", "settle_key")
            if row.get(k)]


def _resolved_ids(rows: List[Dict[str, Any]]) -> set:
    """Identities with a terminal twin: status=="settled" (a real settlement OR
    our own VOID twin) or graded=True (mirrors ingame_paper_settle.
    _settled_edge_keys' own check)."""
    ids: set = set()
    for r in rows:
        if str(r.get("status")) == "settled" or r.get("graded"):
            ids.update(_identities(r))
    return ids


def _market_type_of(row: Dict[str, Any]) -> str:
    return str(row.get("market_type") or row.get("market") or "moneyline").strip()


def _has_identity_anchor(row: Dict[str, Any]) -> bool:
    return bool(str(row.get("matchup") or "").strip()
                or str(row.get("event_id") or "").strip()
                or str(row.get("game_id") or "").strip())


def _classify(row: Dict[str, Any]) -> Tuple[str, bool]:
    """(reason, void_eligible) -- see module docstring for the two narrow VOID
    classes; everything else routes to an existing settler, never voided just
    for not having resolved yet."""
    sport = str(row.get("sport") or "").strip().lower()
    if not sport or not _has_identity_anchor(row):
        return REASON_MALFORMED, True
    if str(row.get("channel") or "") == "paper_ingame":
        return REASON_ROUTE_INGAME, False
    mt = _market_type_of(row).lower()
    if mt == "prop" or mt.startswith("prop"):
        if sport not in _PROP_RESOLVER_SPORTS:
            return REASON_NO_RESOLVER, True
        return REASON_ROUTE_PROP, False
    return REASON_ROUTE_ML, False


def _aged_open_rows(rows: List[Dict[str, Any]], now: Optional[datetime] = None
                    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(genuinely_open, aged) -- genuinely_open excludes rows with a terminal
    twin under their own identity; aged additionally requires age >= MIN_AGE_DAYS."""
    now = now or datetime.now(timezone.utc)
    resolved = _resolved_ids(rows)
    genuinely_open = [r for r in rows if str(r.get("status")) == "open"
                      and not any(i in resolved for i in _identities(r))]
    aged = [r for r in genuinely_open if _age_bucket(_age_days(r, now)) is not None]
    return genuinely_open, aged


def inventory(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Honest breakdown of the aged (>=7d) genuinely-open backlog: by sport,
    market_type, channel, age bucket, likely-stuck reason. Read-only."""
    path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    rows = _clv.load_ledger(path)
    now = datetime.now(timezone.utc)
    genuinely_open, aged = _aged_open_rows(rows, now)
    return {
        "n_total_rows": len(rows),
        "n_open_naive": sum(1 for r in rows if str(r.get("status")) == "open"),
        "n_genuinely_open": len(genuinely_open),
        "n_aged_ge_7d": len(aged),
        "by_age_bucket": dict(Counter(_age_bucket(_age_days(r, now)) for r in aged)),
        "by_sport": dict(Counter(str(r.get("sport") or "unknown") for r in aged)),
        "by_market_type": dict(Counter(_market_type_of(r) for r in aged)),
        "by_channel": dict(Counter(str(r.get("channel") or "none") for r in aged)),
        "by_stuck_reason": dict(Counter(_classify(r)[0] for r in aged)),
        "honest_note": ("genuinely-open = no settled/graded twin exists under the "
                        "row's own bet_id/edge_key identity (never a naive "
                        "status==open grep). Read-only; no settler invoked."),
    }


def _void_twin(row: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Terminal twin: status="settled" (not the literal VOID_UNRESOLVABLE
    string) -- see module docstring's VOID rows note."""
    twin = dict(row)
    twin["status"] = "settled"
    twin["settled_at"] = _clv._now_iso()
    twin["outcome"] = VOID_OUTCOME
    twin["void_reason"] = reason
    twin["clv_pct"] = None
    twin["beat_close"] = None
    twin["clv_is_proxy"] = False
    twin["clv_status"] = "no_close"
    twin["clv_note"] = ("settle_sweep: provably unresolvable via existing settlers "
                        "(%s); stake returned, excluded from CLV/grade aggregates"
                        % reason)
    twin["unit_result"] = 0.0  # stake returned -- never a fabricated win/loss
    twin["executed"] = False
    twin["edge_claimed"] = False
    return twin


def _try_backfill_as_of(ledger_path: Path) -> Dict[str, Any]:
    try:
        from scripts.platformkit.grade_paper_asof import backfill_as_of
        return backfill_as_of(ledger_path)
    except Exception as exc:  # noqa: BLE001 -- settler may be mid-edit elsewhere
        logger.warning("settle_sweep: backfill_as_of unavailable: %s", exc)
        return {"error": str(exc)}


def _try_settle_open_props(ledger_path: Path) -> Dict[str, Any]:
    try:
        from scripts.platformkit.bestbets.prop_settler import settle_open_props
        return settle_open_props(ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("settle_sweep: settle_open_props unavailable: %s", exc)
        return {"error": str(exc)}


def _try_ingame_settle_open(ledger_path: Path) -> Dict[str, Any]:
    try:
        from scripts.platformkit.ingame.ingame_paper_settle import settle_open
        return settle_open(ledger_path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("settle_sweep: ingame settle_open unavailable: %s", exc)
        return {"error": str(exc)}


def sweep(ledger_path: Optional[Path] = None, write: bool = False) -> Dict[str, Any]:
    """Retry the aged backlog through the existing settlers; VOID what can never
    route. write=False (default): pure classification preview, no settler call,
    no ledger write. write=True: calls the real settlers (each idempotent) then
    VOIDs any row still open afterwards that is provably unroutable."""
    path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    rows = _clv.load_ledger(path)
    _, aged = _aged_open_rows(rows)
    routed = Counter(_classify(r)[0] for r in aged)
    if not write:
        return {
            "write": False, "n_aged_considered": len(aged),
            "routed_counts": dict(routed),
            "n_would_void_candidates": sum(
                1 for r in aged if _classify(r)[0] in _VOID_ELIGIBLE),
            "honest_note": ("dry run: routing classified only, no settler "
                            "invoked, no ledger write"),
        }

    settler_results: Dict[str, Any] = {}
    if routed.get(REASON_ROUTE_ML):
        settler_results["game_ml_backfill"] = _try_backfill_as_of(path)
    if routed.get(REASON_ROUTE_PROP):
        settler_results["prop_settler"] = _try_settle_open_props(path)
    if routed.get(REASON_ROUTE_INGAME):
        settler_results["ingame_paper_settle"] = _try_ingame_settle_open(path)

    rows2 = _clv.load_ledger(path)
    _, still_aged = _aged_open_rows(rows2)
    voided = 0
    left_open: Counter = Counter()
    for row in still_aged:
        reason, void_eligible = _classify(row)
        if void_eligible:
            _clv.append_settlement(_void_twin(row, reason), path=path)
            voided += 1
        else:
            left_open[reason] += 1

    return {
        "write": True,
        "n_aged_before": len(aged),
        "routed_counts": dict(routed),
        "settler_results": settler_results,
        "n_settled_now": len(aged) - len(still_aged),
        "n_voided": voided,
        "n_left_open": len(still_aged) - voided,
        "left_open_by_reason": dict(left_open),
        "executed": False,
        "edge_claimed": False,
        "honest_note": ("settled_now = resolved by an existing settler this pass; "
                        "voided = provably unresolvable (see VOID rows note); "
                        "left_open = settler ran, event/stat genuinely not "
                        "resolvable yet."),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Settlement sweep (M43): retry the aged (>=7d) open paper "
                    "backlog via existing settlers; VOID what can never route.")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    ledger = Path(a.ledger) if a.ledger else None
    doc = sweep(ledger, write=a.write) if a.sweep else inventory(ledger)
    print(json.dumps(doc, indent=2, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["inventory", "sweep", "VOID_OUTCOME", "REASON_MALFORMED",
           "REASON_NO_RESOLVER", "REASON_ROUTE_ML", "REASON_ROUTE_PROP",
           "REASON_ROUTE_INGAME"]
