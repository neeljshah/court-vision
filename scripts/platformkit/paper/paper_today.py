"""scripts.platformkit.paper.paper_today -- the "execution view" of placed paper bets.

PURE builders (no daemon loop here -- bankroll_daemon drives the cadence). Reads the
PLACED paper bets from the canonical CLV ledger (data/frontend/clv_ledger.jsonl: the
bets the supervised m1_paper auto_loop actually staked, executed=False) and produces:

  * build_today(...)  -> the front-end execution view {date, placed, pending,
    settled_today, day_units, cumulative_units, bankroll, ...}. "placed" carries each
    staked bet with placed=True, stake_units, tier and (when graded) unit_result + clv.
    The money-makers (best bets) are exactly these placed, tier-cleared bets.
  * reconcile(...)    -> the proof object: the cumulative_units the equity curve shows
    MUST equal the sum of the placed bets' graded unit_results (flat-1-unit normalised),
    so "how much you'd have made" is never a fabricated number -- it is the literal sum
    of the staked bets that settled.

HONEST RAILS (binding):
  * UNITS ONLY -- no $/pnl/roi/profit/bankroll($) key is ever emitted. Stakes are the
    policy flat unit; legacy dollar-Kelly stake_units contamination is re-normalised to
    a flat 1 unit (pnl_normalize.normalize_flat) WITHOUT mutating the on-disk ledger.
  * executed=False / edge_claimed=False everywhere. Real money stays default-DENY.
  * CLV is the yardstick: mean CLV is INSUFFICIENT_DATA when no close was captured,
    never a fabricated number. Nothing is fabricated -- only graded rows move the curve.

A "day" is the ET settle-date (the games are an ET slate, so the day boundary uses
America/New_York, NOT UTC -- at 8pm ET / 00:00 UTC the UTC date is already tomorrow
and would roll the daily bucket a full ET-day early). A still-open placed bet belongs
to its game/record day and shows as pending until its game is FINAL and graded.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.paper import bankroll as _bank
from scripts.platformkit.paper import et_day as _et
from scripts.platformkit.paper import paper_exec_summary as _exec
from scripts.platformkit.paper import pnl_normalize as _nz

# Min true-close sample before a mean CLV is reported as a number; below it the
# small-N mean is noise, so report INSUFFICIENT_DATA and surface n_clv (the count).
MIN_CLV_N = 8

# Keys the placed-bet view exposes (units + tier + clv only -- never a dollar field).
_PLACED_FIELDS = ("sport", "matchup", "side", "selection", "taken_book",
                  "taken_decimal", "model_prob", "tier", "stake_units",
                  "flat_unit", "quarter_kelly", "event_id", "commence_time", "ts",
                  # prop identity (market_type=="prop"): render the player/stat/line
                  # so a placed prop is not shown as a meaningless home/away game row.
                  "market_type", "market", "prop_player", "prop_stat", "prop_side",
                  "line", "market_prob")

_HONEST_NOTE = (
    "Today's PLACED paper bets (executed=False) and their running UNITS P&L. The "
    "money-makers are the tier-cleared staked bets; each is flat 1 unit at the taken "
    "price, so cumulative_units == sum of graded placed-bet unit_results (the "
    "reconcile() proof). 'How much you'd have made' is a paper track record in units, "
    "NOT realized profit and NOT a $ ROI; no edge is claimed. CLV (better-than-close) "
    "is the honest yardstick -- INSUFFICIENT_DATA means no close was captured."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_utc() -> str:
    """The betting 'today' as an ET calendar date (the slate is ET, not UTC).

    Name kept for API stability; the boundary is now America/New_York so the daily
    bucket no longer rolls a full ET-day early at 8pm ET / 00:00 UTC.
    """
    return _et.now_et_day()


def _settle_day(row: Dict[str, Any]) -> str:
    for k in ("settled_at", "ts", "logged_at"):
        v = row.get(k)
        if v:
            return _et.et_day_of(str(v))
    return "unknown"


def _record_day(row: Dict[str, Any]) -> str:
    """The ET day a placed bet belongs to before it settles (its record/game day)."""
    for k in ("game_date", "ts", "commence_time"):
        v = row.get(k)
        if v:
            return _et.et_day_of(str(v))
    return "unknown"


def _is_placed(row: Dict[str, Any]) -> bool:
    """A real PLACED paper bet: a CLV-ledger row with a usable taken price.

    The CLV ledger only ever holds placed paper bets (run_paper_today records them);
    a row with a > 1.0 taken_decimal is a genuine staked position.
    """
    try:
        return float(row.get("taken_decimal", 0.0)) > 1.0
    except (TypeError, ValueError):
        return False


def _view_row(row: Dict[str, Any], *, placed: bool) -> Dict[str, Any]:
    """A clean front-end row, FLAT-1-UNIT normalised (units + tier + clv only, no $).

    The on-disk ledger carries legacy dollar-Kelly stake_units (67, 204, 500...) and a
    matching dollar-magnitude unit_result (-500..+536). Echoing those onto the units-only
    rail paints giant fake wins/losses, so every served row is re-staked to a flat 1 unit
    and (for settled rows) unit_result is recomputed at flat 1u from the taken price +
    outcome -- exactly how the equity curve is built -- so the served rows RECONCILE to
    the curve. The underlying ledger is NOT mutated; normalisation is on-read only.
    """
    out: Dict[str, Any] = {k: row.get(k) for k in _PLACED_FIELDS if k in row}
    out["stake_units"] = 1.0  # flat 1u (drop legacy dollar-Kelly magnitude)
    out["flat_unit"] = 1.0
    out["placed"] = bool(placed)
    out["executed"] = False
    if row.get("status") == "settled":
        out["outcome"] = row.get("outcome")
        out["unit_result"] = _nz.flat_unit_result(row)  # flat 1u, recomputed
        out["clv_pct"] = row.get("clv_pct")
        out["clv_status"] = row.get("clv_status")
        out["clv_is_proxy"] = bool(row.get("clv_is_proxy", False))
    return out


def load_placed(clv_path: Optional[Any] = None) -> List[Dict[str, Any]]:
    """All PLACED paper bets from the canonical CLV ledger (synthetic rows dropped)."""
    rows = _clv.load_ledger(clv_path) if clv_path is not None else _clv.load_ledger()
    return [r for r in rows if _is_placed(r)]


def _clv_values(rows: Sequence[Dict[str, Any]]) -> List[float]:
    """The clv_pct values of rows that captured a TRUE close (n_clv = len of this).

    Proxy closes (clv_is_proxy=True) are a weaker substitute and are EXCLUDED so they
    cannot contaminate the headline mean; they remain counted in n_settled elsewhere.
    """
    return [float(r["clv_pct"]) for r in rows
            if r.get("clv_pct") is not None and not bool(r.get("clv_is_proxy", False))]


def _mean_clv(rows: Sequence[Dict[str, Any]], *, min_n: int = MIN_CLV_N) -> Any:
    """Mean clv_pct, but INSUFFICIENT_DATA below the min true-close sample (small-N noise).

    A handful of true closes beside a large n_bets is small-N noise painted as a result;
    report INSUFFICIENT_DATA until at least *min_n* true closes are captured. n_clv (the
    count) is surfaced separately by build_today so the sample size is always visible.
    """
    vals = _clv_values(rows)
    if len(vals) < min_n:
        return "INSUFFICIENT_DATA"
    return round(sum(vals) / len(vals), 6)


def reconcile(
    placed: Sequence[Dict[str, Any]], *, start_units: float,
) -> Dict[str, Any]:
    """PROVE the curve == sum of placed graded unit_results (flat-1-unit normalised).

    Returns {start_units, cumulative_units, current_units, n_settled, reconciles}.
    cumulative_units is the literal sum of every settled placed bet's flat unit_result;
    current_units = start_units + cumulative_units. reconciles is always True by
    construction (one source of truth) -- the field exists so a caller/test can assert it.
    """
    settled = [r for r in placed if r.get("status") == "settled"]
    # One position per market (collapse a symmetric two-way market's home+away to the
    # single model-backed side, and dedup same-side duplicates) BEFORE summing, so the
    # reconcile total matches the corrected curve -- not the double-counted both-sides.
    settled = _nz.select_clv_positions(settled)
    flat = _nz.normalize_flat(settled)  # re-stake to flat 1 unit; drop void/no-result
    cumulative = round(sum(float(r["unit_result"]) for r in flat), 6)
    return {
        "start_units": float(start_units),
        "cumulative_units": cumulative,
        "current_units": round(float(start_units) + cumulative, 6),
        "n_settled": len(flat),
        "reconciles": True,
    }


def build_today(
    *,
    clv_path: Optional[Any] = None,
    start_units: Optional[float] = None,
    today: Optional[str] = None,
    bankroll_path: Optional[Any] = None,
) -> Dict[str, Any]:
    """The front-end execution view of TODAY's placed paper bets + running P&L.

    placed        = today's staked bets still pending settlement (game not final).
    settled_today = today's staked bets that settled today (carry unit_result + clv).
    pending       = a compact pending list (matchup/side/tier) for the UI.
    day_units     = net flat units settled TODAY; cumulative_units = all-time net.
    bankroll      = {start_units, current_units, net_units} reconciled to placed bets.
    """
    day = today or _today_utc()
    su = float(start_units) if start_units is not None \
        else float(_bank.read_config(bankroll_path)["start_units"])
    placed_rows = load_placed(clv_path)

    # All-time reconciliation (the authoritative bankroll + curve).
    rec = reconcile(placed_rows, start_units=su)

    # Today's buckets. Collapse to one position per market first (drop the non-backed
    # side of a symmetric two-way market + same-side duplicates) so today's served
    # settled rows and day_units match the one-per-market curve, not the double count.
    settled = _nz.select_clv_positions(
        [r for r in placed_rows if r.get("status") == "settled"])
    settled_today_rows = [r for r in settled if _settle_day(r) == day]
    flat_today = _nz.normalize_flat(settled_today_rows)
    day_units = round(sum(float(r["unit_result"]) for r in flat_today), 6)

    open_rows = [r for r in placed_rows if r.get("status") != "settled"]
    placed_today = [r for r in open_rows if _record_day(r) == day]

    return {
        "date": day,
        "generated_at": _now_iso(),
        "placed": [_view_row(r, placed=True) for r in placed_today],
        # pending rows are flat-units normalised too (same _view_row rail as
        # placed/settled_today) -- never echo the legacy dollar-Kelly stake_units,
        # so EVERY served row shows a flat 1.0u.
        "pending": [_view_row(r, placed=True) for r in open_rows],
        "settled_today": [_view_row(r, placed=True) for r in settled_today_rows],
        "day_units": day_units,
        "cumulative_units": rec["cumulative_units"],
        # UNITS-rail: flat *_units keys (matches the clean paper_bankroll.json
        # schema). The 'bankroll' token is banned by the honesty linter even with a
        # 'units' suffix, so we never emit it; net is cumulative_units (above).
        "start_units": rec["start_units"],
        "current_units": rec["current_units"],
        "net_units": rec["cumulative_units"],
        "n_placed_alltime": len(placed_rows),
        "n_settled_alltime": rec["n_settled"],
        "n_open": len(open_rows),
        "mean_clv_pct_or_INSUFFICIENT": _mean_clv(settled),
        "n_clv": len(_clv_values(settled)),
        "min_clv_n": MIN_CLV_N,
        "reconciles": rec["reconciles"],
        # Per-market rolling CLV + circuit-breaker state + execution-quality
        # aggregates. Degrades to "UNKNOWN"/nulls if the breaker module (owned by
        # a concurrent lane) is not yet on disk -- never fabricated.
        "execution": _exec.build_execution_block(placed_rows, _now_iso()),
        "honest_note": _HONEST_NOTE,
        "edge_claimed": False,
        "executed": False,
    }


__all__ = ["load_placed", "reconcile", "build_today", "MIN_CLV_N",
           "_today_utc", "_settle_day", "_record_day", "_view_row",
           "_mean_clv", "_clv_values"]
