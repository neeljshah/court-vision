"""scripts.platformkit.bestbets.prop_settler -- settle OPEN player-prop paper bets from
the REAL post-game stat outcome (player over/under a line), so props REALIZE units P&L.

THE GAP: props_paper_placer records OPEN prop rows (market_type=prop), but the game-moneyline
settler (grade_paper) correctly SKIPS them -- so without this they sit PENDING forever and
never contribute to the bankroll. This settler grades a prop on its OWN stat outcome.

HONEST CONTRACT (mirrors grade_paper):
  * Settles ONLY when the realized stat is reliably resolved (realized_fn returns a finite
    value); any failure / game-not-final / player-not-found -> None -> row stays PENDING,
    NEVER a fabricated outcome. Append-only + settle_key => idempotent.
  * A prop has NO true closing-line feed -> CLV is genuinely unavailable: clv_pct=None,
    clv_status="no_close", beat_close=None (never an inferred proxy that fabricates
    confidence). The bet still scores a win/loss in UNITS at the taken price.
  * UNITS only (unit_result at the taken decimal); executed=False; no $/pnl/roi field.
  * Resolution is INJECTABLE (realized_fn) so the core is pure + offline-testable; the
    default MLB resolver lives in prop_settler_mlb (best-effort keyless boxscore).

RAILS: build only under scripts/platformkit/; ASCII; <=300 LOC; public fns NEVER raise.
Per-file test: scripts/platformkit/bestbets/test_prop_settler.py
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.clv_settle_write import write_settlement as _write_settlement
from scripts.platformkit.grade_paper import _settle_key, _unit_result

logger = logging.getLogger(__name__)


def _prop_side(row: Dict[str, Any]) -> Optional[str]:
    """The over/under side of a prop row. Prefers prop_side; falls back to the binary
    leg encoding (side: home=over, away=under). None when neither is usable."""
    ps = str(row.get("prop_side") or "").strip().lower()
    if ps in ("over", "under"):
        return ps
    leg = str(row.get("side") or "").strip().lower()
    if leg == "home":
        return "over"
    if leg == "away":
        return "under"
    return None


def prop_outcome(prop_side: str, line: Any, realized: Any) -> Optional[str]:
    """win / loss / push for an over/under prop, or None when ungradable.

    over wins when realized > line; under wins when realized < line; equal -> push.
    None when side/line/realized cannot be coerced (never a fabricated result).
    """
    side = str(prop_side or "").strip().lower()
    if side not in ("over", "under"):
        return None
    try:
        ln = float(line)
        rv = float(realized)
    except (TypeError, ValueError):
        return None
    if ln != ln or rv != rv:  # NaN
        return None
    if rv == ln:
        return "push"
    over_hit = rv > ln
    if side == "over":
        return "win" if over_hit else "loss"
    return "win" if not over_hit else "loss"


def settle_prop_row(row: Dict[str, Any], realized: float, *,
                    close_fn: Optional[Callable[[Dict[str, Any]],
                                                Optional[Dict[str, Any]]]] = None,
                    ) -> Optional[Dict[str, Any]]:
    """SETTLED twin of an open prop *row* given its realized stat value, or None when
    ungradable. UNITS only. CLV: if *close_fn* supplies a captured two-way closing
    price (over_dec/under_dec) for this prop, compute a TRUE-close CLV; otherwise CLV
    is genuinely unavailable -> clv_status='no_close' (never a fabricated proxy)."""
    side = _prop_side(row)
    outcome = prop_outcome(side, row.get("line"), realized)
    if side is None or outcome is None:
        return None
    try:
        taken_decimal = float(row["taken_decimal"])
    except (TypeError, ValueError, KeyError):
        return None
    stake_units = float(row.get("stake_units", 1.0) or 1.0)
    settled = dict(row)
    settled["status"] = "settled"
    settled["settled_at"] = _clv._now_iso()
    settled["graded"] = True
    settled["outcome"] = outcome
    settled["realized_stat"] = round(float(realized), 6)
    settled["unit_result"] = _unit_result(outcome, taken_decimal, stake_units)
    settled["executed"] = False
    _apply_prop_clv(settled, side, taken_decimal, close_fn, row)
    settled["settle_key"] = _settle_key(row)
    settled["bet_id"] = row.get("bet_id") or _clv.bet_id(row)
    return settled


def _apply_prop_clv(settled: Dict[str, Any], side: str, taken_decimal: float,
                    close_fn: Optional[Callable[[Dict[str, Any]],
                                                Optional[Dict[str, Any]]]],
                    row: Dict[str, Any]) -> None:
    """Fill CLV fields from a captured prop close (Over->home, Under->away), or mark
    no_close. Any error falls back to no_close -- never fabricates a close."""
    close = None
    if close_fn is not None:
        try:
            close = close_fn(row)
        except Exception:  # noqa: BLE001 -- a close lookup must not block settlement
            close = None
    if close:
        try:
            over_dec = float(close["over_dec"])
            under_dec = float(close["under_dec"])
            side_hw = "home" if str(side).lower() == "over" else "away"
            clv = _clv.compute_clv(side_hw, taken_decimal, over_dec, under_dec)
            settled["closing_decimal_home"] = over_dec   # Over
            settled["closing_decimal_away"] = under_dec  # Under
            settled["fair_close_prob"] = clv["fair_close"]
            settled["taken_implied_prob"] = clv["taken_p"]
            settled["clv_pct"] = clv["clv_pct"]
            settled["beat_close"] = clv["beat_close"]
            settled["clv_is_proxy"] = False
            settled["clv_status"] = "true_close"
            settled["clv_note"] = ("prop closing two-way from %s"
                                   % (close.get("source") or "book"))
            # D2 fix: stamp close_source (mirrors grade_paper.grade_one's contract)
            # so settlement_correctness_audit.close_source_coverage counts this row
            # as a real book close instead of "missing_key" (this settler previously
            # never wrote the key at all -- a second, undocumented bypass of the
            # close_source stamp that grade_one always applies).
            settled["close_source"] = str(close.get("source") or "book")
            return
        except (KeyError, TypeError, ValueError):
            pass  # fall through to no_close -- never half-write a fabricated CLV
    settled["clv_pct"] = None
    settled["beat_close"] = None
    settled["clv_status"] = "no_close"
    settled["clv_note"] = "player prop: no closing line; CLV unavailable (win/loss only)"
    # Same D2 fix: no close known -> stamp "none_available" (grade_one's Level-5
    # sentinel) rather than leaving the key absent, so a reader can tell "stamp
    # attempted, no close" apart from a pre-fix row where the key never existed.
    settled["close_source"] = "none_available"


def _open_prop_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows
            if r.get("status") == "open" and str(r.get("market_type")) == "prop"]


def _default_close_fn(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Captured prop closing two-way for *row* from prop_close_store, or None.

    Lazy import keeps the settler usable even if the clv package is absent; any
    error -> None (the row stays no_close, never a fabricated close)."""
    try:
        from scripts.platformkit.clv.prop_close_store import close_for_row
        return close_for_row(row)
    except Exception:  # noqa: BLE001
        return None


def settle_open_props(
    ledger_path: Optional[Path] = None,
    *,
    realized_fn: Optional[Callable[[Dict[str, Any]], Optional[float]]] = None,
    close_fn: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Settle every OPEN prop bet whose realized stat *realized_fn* can resolve.

    Idempotent: a prop already settled (matching settle_key / bet_id) is skipped. A prop
    whose realized stat is unavailable (game not final / player not found / network) stays
    PENDING -- never fabricated. *realized_fn* is injectable for tests; the default uses
    prop_settler_mlb.mlb_realized_stat (MLB only; other sports stay pending). *close_fn*
    supplies the captured prop closing two-way for CLV (default: prop_close_store);
    absent a captured close, a prop stays clv_status='no_close'. Never raises.
    """
    ledger_path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    rows = _clv.load_ledger(ledger_path)
    open_props = _open_prop_rows(rows)
    settled_rows = [r for r in rows if r.get("status") == "settled"]
    already = {r.get("settle_key") for r in settled_rows if r.get("settle_key")}
    already |= {r.get("bet_id") for r in settled_rows if r.get("bet_id")}

    if realized_fn is None:
        realized_fn = _default_realized_fn
    if close_fn is None:
        close_fn = _default_close_fn

    seen: set = set()
    settled_now: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    for row in open_props:
        key = _settle_key(row)
        if key in already:
            continue
        try:
            realized = realized_fn(row)
        except Exception as exc:  # noqa: BLE001 -- a resolver must never crash the sweep
            logger.debug("prop_settler: realized_fn raised: %s", exc)
            realized = None
        if realized is None:
            pending.append({"market": row.get("market"), "sport": row.get("sport"),
                            "reason": "realized stat unavailable (not final / unresolved)"})
            continue
        settled = settle_prop_row(row, float(realized), close_fn=close_fn)
        if settled is None:
            pending.append({"market": row.get("market"), "sport": row.get("sport"),
                            "reason": "ungradable row (bad side/line/price)"})
            continue
        _write_settlement(settled, path=ledger_path, _seen=seen)
        already.add(key)
        if settled.get("bet_id"):
            already.add(settled["bet_id"])
        settled_now.append({"market": settled.get("market"), "sport": settled.get("sport"),
                            "outcome": settled["outcome"],
                            "realized_stat": settled["realized_stat"],
                            "unit_result": settled.get("unit_result")})

    return {
        "n_open_props": len(open_props),
        "n_settled_now": len(settled_now),
        "n_pending": len(pending),
        "settled": settled_now,
        "pending": pending,
        "executed": False,
        "edge_claimed": False,
        "honest_note": ("Player props settled on the REAL stat outcome (UNITS at the taken "
                        "price). CLV unavailable for props (no close). real-money DENY."),
    }


def _default_realized_fn(row: Dict[str, Any]) -> Optional[float]:
    """Default per-sport realized-stat resolver: MLB via prop_settler_mlb; soccer / WC via
    prop_settler_soccer (keyless ESPN: goals/assists/cards full, shots/saves leader-only,
    SOT unresolvable). Other sports stay PENDING (None) until a resolver exists. Never raises."""
    sport = str(row.get("sport") or "").strip().lower()
    try:
        if sport == "mlb":
            from scripts.platformkit.bestbets.prop_settler_mlb import mlb_realized_stat
            return mlb_realized_stat(row)
        if sport in ("soccer_intl", "soccer"):
            from scripts.platformkit.bestbets.prop_settler_soccer import soccer_realized_stat
            return soccer_realized_stat(row)
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_settler: %s resolver failed: %s", sport, exc)
        return None
    return None  # other sports: no resolver yet -> honest PENDING


def _main() -> int:  # pragma: no cover
    import json
    out = settle_open_props()
    print(json.dumps({k: out[k] for k in (
        "n_open_props", "n_settled_now", "n_pending")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["prop_outcome", "settle_prop_row", "settle_open_props"]
