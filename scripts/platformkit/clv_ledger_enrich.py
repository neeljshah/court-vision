"""scripts.platformkit.clv_ledger_enrich -- READ-ONLY enrichment pass on CLV ledger rows.

Gap-fills: tier, flat_unit, quarter_kelly, venue, market_id, AND CLV fields
(clv_pct, beat_close, clv_status) computed from closing line stored on the row.

W5-clv-ledger-stamp: settled rows with clv_pct=null get CLV re-derived at READ
TIME when closing_decimal_home/away (or close_home/away_price) are present.
A row with no usable closing line stays clv_status='no_close' -- never a 0-fill.

CONTRACT:
  * READ-ONLY -- never mutates or re-appends the append-only ledger.
  * UNITS only. No $ / dollar / roi / profit field added.
  * Honest: fields that cannot be recovered are left as None (never guessed).
  * <=300 LOC; ASCII; no secrets; no network.

Usage::
    from scripts.platformkit.clv_ledger_enrich import enrich_rows, enrich_row
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# --- policy EV floors (degrade gracefully if pm_trading unavailable) ----------
_EV_FLOOR_A: float = 0.08
_EV_FLOOR_B: float = 0.04
_EV_FLOOR_C: float = 0.02
_EV_PROXY_PENALTY: float = 0.01

try:
    from scripts.platformkit.pm_trading.policy import (
        EV_FLOOR_A as _EV_FLOOR_A,
        EV_FLOOR_B as _EV_FLOOR_B,
        EV_FLOOR_C as _EV_FLOOR_C,
        EV_PROXY_PENALTY as _EV_PROXY_PENALTY,
    )
except Exception:  # noqa: BLE001
    pass

# CLV compute reuse (vetted Shin devig inside clv_ledger.compute_clv).
try:
    from scripts.platformkit.clv_close_lookup import lookup_close_legs as _lookup_close_legs
except Exception:  # noqa: BLE001 -- optional history bridge; absence = old behavior
    _lookup_close_legs = None  # type: ignore[assignment]

# LANE-5 additive fallback: Kalshi-ticker-keyed close-proxy from captured in-play
# ticks (kx_ticker_close.py), consulted ONLY when the ESPN-numeric-game_id path
# above returns None -- see _compute_clv_fields. Absence of this module leaves
# the ESPN path byte-identical (old behavior).
try:
    from scripts.platformkit.clv.kx_close_fallback import (
        lookup_close_legs_kx as _lookup_close_legs_kx,
    )
except Exception:  # noqa: BLE001 -- optional bridge; absence = old behavior
    _lookup_close_legs_kx = None  # type: ignore[assignment]

try:
    from scripts.platformkit.clv_ledger import compute_clv as _compute_clv
    _CLV_OK = True
except Exception:  # noqa: BLE001
    _compute_clv = None  # type: ignore[assignment]
    _CLV_OK = False

# --- venue patterns -----------------------------------------------------------
_KALSHI_RE = re.compile(r"kalshi", re.IGNORECASE)
_POLY_RE   = re.compile(r"polymarket|poly", re.IGNORECASE)
_ESPN_RE   = re.compile(r"espn", re.IGNORECASE)


def _infer_venue(row: Dict[str, Any]) -> str:
    channel    = str(row.get("channel") or "").lower()
    taken_book = str(row.get("taken_book") or "")
    event_id   = str(row.get("event_id") or "")
    if "kalshi" in channel:
        return "kalshi"
    if "polymarket" in channel or "poly" in channel:
        return "polymarket"
    if _KALSHI_RE.search(taken_book):
        return "kalshi"
    if _POLY_RE.search(taken_book):
        return "polymarket"
    if event_id and _ESPN_RE.search(event_id):
        return "sportsbook"
    if taken_book:
        return "sportsbook"
    return "unknown"


def _extract_market_id(row: Dict[str, Any]) -> Optional[str]:
    explicit = row.get("market_id")
    if explicit is not None:
        return str(explicit)
    event_id = str(row.get("event_id") or "").strip()
    if not event_id or event_id.isdigit() or _ESPN_RE.search(event_id):
        return None
    return event_id


def _infer_tier(row: Dict[str, Any]) -> Optional[str]:
    if row.get("tier") is not None:
        return str(row["tier"])
    ev: Optional[float] = None
    ev_pct_raw = row.get("ev_pct")
    model_ev_raw = row.get("model_ev")
    if ev_pct_raw is not None:
        try:
            ev = float(ev_pct_raw) / 100.0
        except (TypeError, ValueError):
            pass
    elif model_ev_raw is not None:
        try:
            ev = float(model_ev_raw)
        except (TypeError, ValueError):
            pass
    if ev is None:
        return None
    bump = _EV_PROXY_PENALTY if bool(row.get("clv_is_proxy", False)) else 0.0
    if ev >= _EV_FLOOR_A + bump:
        return "A"
    if ev >= _EV_FLOOR_B + bump:
        return "B"
    if ev >= _EV_FLOOR_C + bump:
        return "C"
    return None


def _infer_flat_unit(row: Dict[str, Any]) -> Optional[float]:
    raw = row.get("flat_unit")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    su = row.get("stake_units")
    if su is not None:
        try:
            val = float(su)
            if 0.0 < val <= 2.0:
                return round(val, 6)
        except (TypeError, ValueError):
            pass
    return None


def _infer_quarter_kelly(row: Dict[str, Any]) -> Optional[float]:
    raw = row.get("quarter_kelly")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    return None


def _extract_closing_decimals(row: Dict[str, Any]) -> "Optional[tuple[float, float]]":
    """Return (close_home_decimal, close_away_decimal) or None."""
    for hk, ak in (
        ("closing_decimal_home", "closing_decimal_away"),
        ("close_home_price",     "close_away_price"),
    ):
        h_raw = row.get(hk)
        a_raw = row.get(ak)
        if h_raw is None or a_raw is None:
            continue
        try:
            h, a = float(h_raw), float(a_raw)
        except (TypeError, ValueError):
            continue
        if h > 1.0 and a > 1.0:
            return (h, a)
    return None


_NO_CLOSE = {
    "clv_pct": None,
    "beat_close": None,
    "clv_status": "no_close",
}


def _compute_clv_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    """Compute CLV fields from closing line embedded in row. Never raises."""
    if not _CLV_OK or _compute_clv is None:
        return dict(_NO_CLOSE, clv_note="compute_clv unavailable")

    # Already computed (non-null, non-no_close): keep.
    existing_pct = row.get("clv_pct")
    existing_status = row.get("clv_status")
    if (existing_pct is not None
            and existing_status not in (None, "no_close", "INSUFFICIENT_DATA")):
        return {
            "clv_pct": existing_pct,
            "beat_close": row.get("beat_close"),
            "clv_status": existing_status,
            "clv_note": row.get("clv_note", ""),
        }

    legs = _extract_closing_decimals(row)
    history_proxy: Optional[bool] = None
    close_kind: Optional[str] = None
    # PERF (2026-07-15, audit-corrected): for ESPN-numeric-keyed sports a KX
    # venue ticker id can never match line history, so scanning for the miss
    # (seconds per row) is skipped. KBO/NPB/soccer_intl line history IS
    # KX-keyed (audit finding #2), so those sports always take the lookup.
    _jid = str(row.get("game_id") or row.get("event_id") or "")
    _sport = str(row.get("sport") or "").lower()
    _is_kx = bool(re.search(r"(^|\|)KX[A-Z0-9]", _jid.upper()))
    _skip_history = _is_kx and _sport in ("mlb", "nba", "wnba")
    if legs is None and not _skip_history and _lookup_close_legs is not None:
        hl = _lookup_close_legs(row)
        if hl is not None:
            legs = (hl[0], hl[1])
            history_proxy = not hl[2]  # at-lock=True -> real; else proxy
    # LANE-5 additive fallback: only reached when the ESPN-keyed path above found
    # nothing (row.game_id is a venue ticker, e.g. Kalshi KX*, off that id space).
    if legs is None and _lookup_close_legs_kx is not None:
        hl_kx = _lookup_close_legs_kx(row)
        if hl_kx is not None:
            legs = (hl_kx[0], hl_kx[1])
            history_proxy = not hl_kx[2]  # always True (last-tick proxy)
            close_kind = "last_tick"
    if legs is None:
        return dict(_NO_CLOSE,
                    clv_note="no closing line captured; CLV unavailable (win/loss only)")

    side = str(row.get("side") or "").strip().lower()
    if side not in ("home", "away"):
        return dict(_NO_CLOSE, clv_note="side missing/invalid; cannot compute CLV")

    try:
        taken = float(row.get("taken_decimal") or 0.0)
    except (TypeError, ValueError):
        taken = 0.0
    if taken <= 1.0:
        return dict(_NO_CLOSE, clv_note="taken_decimal invalid; cannot compute CLV")

    close_home, close_away = legs
    try:
        clv = _compute_clv(side, taken, close_home, close_away)
    except Exception as exc:  # noqa: BLE001
        return dict(_NO_CLOSE, clv_note="compute_clv error: %s" % type(exc).__name__)

    is_proxy = (history_proxy if history_proxy is not None
                else bool(row.get("clv_is_proxy", False)))
    src = "kx ticker tick series" if close_kind else (
        "line history" if history_proxy is not None else "row")
    out: Dict[str, Any] = {
        "clv_pct":    clv["clv_pct"],
        "beat_close": clv["beat_close"],
        "clv_status": "clv_proxy" if is_proxy else "clv_real",
        "clv_is_proxy": is_proxy,
        "clv_note": (
            "CLV computed from closing line (%s enrich); "
            "%s side; taken=%.4f home=%.4f away=%.4f"
            % (src, side, taken, close_home, close_away)
        ),
    }
    if close_kind:
        # LANE-5: last-tick close-proxy inherits venue staleness -- stamp every
        # derived CLV row so scoreboards can segregate it from a real/at-lock close.
        out["close_kind"] = close_kind
    return out


def enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a READ-ONLY enriched copy of one ledger row.

    Fills venue, market_id, tier, flat_unit, quarter_kelly, is_pm, clv_pct,
    beat_close, clv_status, clv_note.  Never mutates the original dict.
    No $ / dollar / pnl field added.
    """
    enriched = dict(row)

    venue = _infer_venue(row)
    if not enriched.get("venue"):
        enriched["venue"] = venue
    enriched["is_pm"] = enriched["venue"] in ("kalshi", "polymarket")

    mid = _extract_market_id(row)
    if enriched.get("market_id") is None:
        enriched["market_id"] = mid

    enriched["tier"] = _infer_tier(row)
    if enriched.get("flat_unit") is None:
        enriched["flat_unit"] = _infer_flat_unit(row)
    if enriched.get("quarter_kelly") is None:
        enriched["quarter_kelly"] = _infer_quarter_kelly(row)

    # CLV gap-fill: run for settled rows or any row that carries a closing line.
    is_settled = str(row.get("status") or "").lower() == "settled"
    has_close  = _extract_closing_decimals(row) is not None
    if is_settled or has_close:
        cf = _compute_clv_fields(row)
        # clv_pct / beat_close: fill gap only.
        if enriched.get("clv_pct") is None:
            enriched["clv_pct"] = cf["clv_pct"]
        if enriched.get("beat_close") is None:
            enriched["beat_close"] = cf["beat_close"]
        # clv_status: promote to a real status when we computed one.
        current_status = enriched.get("clv_status")
        new_status = cf.get("clv_status", "no_close")
        if current_status in (None, "no_close", "INSUFFICIENT_DATA"):
            enriched["clv_status"] = new_status
        # clv_is_proxy: stamp it when the close came from the line-history bridge.
        if "clv_is_proxy" in cf:
            enriched["clv_is_proxy"] = cf["clv_is_proxy"]
        # close_kind: LANE-5 -- present only for a KX-ticker last-tick proxy close;
        # absent (never fabricated) for the ESPN/line-history path. Lets scoreboards
        # segregate a last-tick proxy from a real/at-lock close.
        if "close_kind" in cf:
            enriched["close_kind"] = cf["close_kind"]
        # clv_note: fill gap.
        if not enriched.get("clv_note"):
            enriched["clv_note"] = cf.get("clv_note", "")
    else:
        enriched.setdefault("clv_pct", None)
        enriched.setdefault("beat_close", None)
        enriched.setdefault("clv_status", "no_close")
        enriched.setdefault("clv_note", "open row; no closing line yet")

    enriched["executed"] = False
    return enriched


def enrich_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return enriched copies of all rows. Never raises; bad rows pass through."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            out.append(enrich_row(row))
        except Exception:  # noqa: BLE001 -- one bad row never sinks the batch
            try:
                out.append(dict(row))  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001 -- row is truly un-dict-able (e.g. None)
                out.append({})
    return out


__all__ = ["enrich_row", "enrich_rows"]
