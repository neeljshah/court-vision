"""scripts.platformkit.pm_trading.pm_close_capture -- resolve + apply closing lines for
settled Kalshi/Polymarket (paper_pm) bets so the PM channel becomes CLV-measurable.

THE GAP: pm_game_placer records open PM rows and they settle win/loss, but NOTHING ever
ran close_capture.capture_close -> every paper_pm settled row carried clv_pct=None
(n_clv=0 on our best-realized channel). The resolver existed; it was just never invoked,
and the rows lacked event_id (now stamped by the placer). This sweep closes the loop:
for each settled PM row with an event_id and no CONFIRMED close yet, resolve the Kalshi
settled price (close_capture) and, when it is a real (non-proxy) close, fill CLV via
clv_ledger.settle_closing_line and append the settled twin.

HONEST RAILS: PAPER measurement only -- NO placement, NO $ field, NO edge claim, NO flag
flip, NO real-money action. ONLY confirmed (is_proxy=False) Kalshi closes are stamped as
true_close; an open/inferred market is NOT written (never a fabricated close). Idempotent:
a row already carrying a real close is skipped. Injectable capture_fn/kalshi_fetch for
offline tests; public fns never raise.

INVARIANTS: scripts/platformkit only; ASCII; <=300 LOC.
Per-file test: scripts/platformkit/pm_trading/test_pm_close_capture.py
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("pm_close_capture")

_CHANNEL = "paper_pm"


def _default_capture(row: Dict[str, Any], *, kalshi_fetch: Any = None) -> Any:
    """Default close resolver = close_capture.capture_close. Returns CloseResult|None."""
    try:
        from scripts.platformkit.pm_trading.close_capture import capture_close
        return capture_close(row, kalshi_fetch=kalshi_fetch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_close_capture resolver failed: %s", exc)
        return None


def _resolved_keys(rows: List[Dict[str, Any]]) -> set:
    """bet_ids that already carry a CONFIRMED SAME-VENUE (kalshi/poly) close ->
    skip (idempotent).

    ROOT CAUSE FIX (2026-07-08b): grade_paper.grade_one settles a paper_pm row's
    win/loss from the final score and, on the way, may ALSO resolve a close via
    its own venue-blind line_store lookup -- stamping clv_is_proxy=False even
    when that close came from a DIFFERENT book than the one the bet was taken on
    (a cross-venue close, now labelled close_source='cross_venue_fallback' by
    grade_one). Treating clv_is_proxy=False alone as "resolved" permanently
    blocked this sweep from ever attempting the REAL same-venue Kalshi close --
    every row settled this way was skipped forever. Now a row only counts as
    resolved when its close_source/close_venue actually names the PM venue
    (same token convention as clv_result_reconciler._is_same_venue_close); a
    row EXPLICITLY tagged close_source='cross_venue_fallback' (grade_one's
    new stamp) stays a target so a genuine Kalshi close still has a chance to
    overwrite it going forward. FORWARD-ONLY: a row with NEITHER field set at
    all (settled before this fix shipped, or Level-1 book genuinely unknown)
    is left alone as resolved -- never reconsidered -- so old rows stay
    labelled basis rather than churning the bounded max_rows budget every
    tick and starving genuinely new targets out of their turn.
    """
    out: set = set()
    for r in rows:
        if not (r.get("bet_id") and r.get("clv_pct") is not None
                and not r.get("clv_is_proxy", False)):
            continue
        cs, cv = r.get("close_source"), r.get("close_venue")
        if cs is None and cv is None:
            out.add(r.get("bet_id"))       # legacy/unknown-book -> forward-only, leave
            continue
        src = str(cs or cv or "").lower()
        if "kalshi" in src or "poly" in src:
            out.add(r.get("bet_id"))       # genuinely same-venue -> resolved
    return out


def _targets(rows: List[Dict[str, Any]], resolved: set) -> List[Dict[str, Any]]:
    """Settled PM rows with an event_id and no confirmed close yet, one per bet_id."""
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("channel") != _CHANNEL or r.get("status") != "settled":
            continue
        if not r.get("event_id"):
            continue
        bid = r.get("bet_id")
        if not bid or bid in resolved or bid in seen:
            continue
        seen.add(bid)
        out.append(r)
    return out


def sweep_closes(
    ledger_path: Optional[Path] = None,
    *,
    capture_fn: Optional[Callable[..., Any]] = None,
    kalshi_fetch: Any = None,
    max_rows: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Resolve + apply confirmed Kalshi closes to settled PM rows. Returns counts.

    Idempotent + non-fabricating: only a real (is_proxy=False) close is written (as
    clv_status='true_close'); a still-open / inferred market is counted, never stamped.
    dry_run=True resolves every target (real network calls unless kalshi_fetch is
    injected) but never calls append_settlement -- read-only, for verification.
    Never raises."""
    from scripts.platformkit import clv_ledger as _clv
    path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    try:
        rows = _clv.load_ledger(path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_close_capture load failed: %s", exc)
        return {"n_targets": 0, "n_captured": 0, "n_no_close": 0, "n_proxy": 0,
                "executed": False, "edge_claimed": False}

    cap = capture_fn or _default_capture
    targets = _targets(rows, _resolved_keys(rows))
    if max_rows is not None:
        targets = targets[:max_rows]

    n_cap = n_noclose = n_proxy = n_same_venue = 0
    for r in targets:
        try:
            res = cap(r, kalshi_fetch=kalshi_fetch)
        except Exception as exc:  # noqa: BLE001
            logger.debug("pm_close_capture capture raised: %s", exc)
            res = None
        if res is None:
            n_noclose += 1
            continue
        src = str(getattr(res, "close_source", "") or
                  getattr(res, "close_venue", "") or "").lower()
        if "kalshi" in src or "poly" in src:
            n_same_venue += 1  # join-key now matches: a real venue quote (proxy or not)
        if getattr(res, "is_proxy", True):
            n_proxy += 1                  # open/inferred -> NOT a close; never stamped
            continue
        if dry_run:
            n_cap += 1                    # would resolve; read-only, no ledger write
            continue
        try:
            settled = _clv.settle_closing_line(
                r, float(res.close_home_dec), float(res.close_away_dec))
        except Exception as exc:  # noqa: BLE001
            logger.debug("pm_close_capture settle_closing_line raised: %s", exc)
            n_noclose += 1
            continue
        settled["clv_is_proxy"] = False
        settled["clv_status"] = "true_close"
        settled["close_source"] = getattr(res, "close_source", "kalshi")
        try:
            _clv.append_settlement(settled, path=path)
            n_cap += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("pm_close_capture append failed: %s", exc)
            n_noclose += 1

    return {
        "n_targets": len(targets), "n_captured": n_cap,
        "n_no_close": n_noclose, "n_proxy": n_proxy,
        "n_same_venue": n_same_venue, "dry_run": dry_run,
        "executed": False, "edge_claimed": False,
        "honest_note": ("Confirmed (settled) Kalshi closes only -> clv_status=true_close; "
                        "open/inferred markets are NOT stamped (never fabricated). PAPER "
                        "measurement; no placement, no $ field, no edge claim."),
    }


def _main() -> int:  # pragma: no cover
    import argparse
    import json
    ap = argparse.ArgumentParser(description="PM close-capture sweep (paper only).")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve closes but never write to the ledger")
    ap.add_argument("--max-rows", type=int, default=None)
    a = ap.parse_args()
    out = sweep_closes(max_rows=a.max_rows, dry_run=a.dry_run)
    print(json.dumps({k: out[k] for k in (
        "n_targets", "n_captured", "n_no_close", "n_proxy",
        "n_same_venue", "dry_run")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["sweep_closes"]
