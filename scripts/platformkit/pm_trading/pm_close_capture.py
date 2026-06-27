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
    """bet_ids that already carry a CONFIRMED (non-proxy) close -> skip (idempotent)."""
    out: set = set()
    for r in rows:
        if (r.get("clv_pct") is not None and not r.get("clv_is_proxy", False)
                and r.get("bet_id")):
            out.add(r.get("bet_id"))
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
) -> Dict[str, Any]:
    """Resolve + apply confirmed Kalshi closes to settled PM rows. Returns counts.

    Idempotent + non-fabricating: only a real (is_proxy=False) close is written (as
    clv_status='true_close'); a still-open / inferred market is counted, never stamped.
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

    n_cap = n_noclose = n_proxy = 0
    for r in targets:
        try:
            res = cap(r, kalshi_fetch=kalshi_fetch)
        except Exception as exc:  # noqa: BLE001
            logger.debug("pm_close_capture capture raised: %s", exc)
            res = None
        if res is None:
            n_noclose += 1
            continue
        if getattr(res, "is_proxy", True):
            n_proxy += 1                  # open/inferred -> NOT a close; never stamped
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
        "executed": False, "edge_claimed": False,
        "honest_note": ("Confirmed (settled) Kalshi closes only -> clv_status=true_close; "
                        "open/inferred markets are NOT stamped (never fabricated). PAPER "
                        "measurement; no placement, no $ field, no edge claim."),
    }


def _main() -> int:  # pragma: no cover
    import json
    out = sweep_closes()
    print(json.dumps({k: out[k] for k in (
        "n_targets", "n_captured", "n_no_close", "n_proxy")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["sweep_closes"]
