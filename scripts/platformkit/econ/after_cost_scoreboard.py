"""scripts.platformkit.econ.after_cost_scoreboard -- after-cost channel P&L (6.3).

Extends the CLV scoreboard's honest per-channel record with a NET-OF-COST
number: replay each measurable settled bet through cost_model AS A TAKER (this
system only ever takes today; no maker path exists yet) and report both the
GROSS units already on record and an AFTER-COST units figure alongside it.

This is a NEW module, not an edit to clv_scoreboard.py (that file is near its
300 LOC budget) -- it calls clv_scoreboard.scoreboard() / reads the same
canonical ledger, mirroring how clv_result_reconciler.py is a separate reader
over the same ledger rather than bloating the scoreboard file.

COST APPLICATION (read carefully -- what "after-cost" means here):
  Each settled bet's own taken_decimal implies a taken price p = 1/decimal for
  the side actually bet. cost_model.breakeven_edge_prob(venue, p) gives the
  ROUND-TRIP (entry+exit) fee cost in PROBABILITY units at that price. We
  convert that probability-unit cost into a UNITS deduction against the bet's
  own stake_units: cost_units = breakeven_prob * stake_units (a first-order
  approximation -- the fee is charged on notional, and at $1-notional-per-
  contract with stake_units contracts the dollar cost of the round trip scales
  linearly with stake_units, so this is exact for Kalshi's per-contract fee
  and Polymarket's percent-of-notional fee, not merely an approximation of
  those two formulas). Venue is read from each row's own `venue` field; when
  absent, we fall back to the channel's default venue (paper_pm -> kalshi,
  since every paper_pm row observed to date carries venue=kalshi) and, failing
  that, skip the row's after-cost calc (never fabricate a venue).

NEVER raises on a single bad row; a channel/row with insufficient fields to
cost is included in GROSS but excluded from the AFTER-COST tally, with the
gap reported honestly as n_costed vs n_measurable. Units only; no $ claims.

Run:  python -m scripts.platformkit.econ.after_cost_scoreboard
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv_ledger import load_ledger  # canonical reader
from scripts.platformkit.clv.clv_scoreboard import (
    _channel_of, _dedup_settled, _is_measurable, _CHANNEL_LABEL)
from scripts.platformkit.econ.cost_model import breakeven_edge_prob

_OUT_JSON = os.path.join(_REPO, "data", "frontend", "ops", "after_cost_scoreboard.json")

# Fallback venue per channel when a row has no explicit `venue` field. Only
# populated where we have OBSERVED evidence (every paper_pm row seen to date
# carries venue=kalshi) -- never guessed for a channel with no venue evidence.
_CHANNEL_DEFAULT_VENUE = {
    "paper_pm": "kalshi",
}


def _row_venue(row: Dict[str, Any]) -> Optional[str]:
    v = row.get("venue")
    if v:
        return str(v).strip().lower()
    ch = _channel_of(row)
    return _CHANNEL_DEFAULT_VENUE.get(ch)


def _row_taken_price(row: Dict[str, Any]) -> Optional[float]:
    try:
        dec = float(row.get("taken_decimal"))
    except (TypeError, ValueError):
        return None
    if dec <= 1.0:
        return None
    return 1.0 / dec


def after_cost_units(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pure per-row after-cost calc. Returns None when uncostable (never raises)."""
    venue = _row_venue(row)
    if venue is None:
        return None
    price = _row_taken_price(row)
    if price is None:
        return None
    try:
        stake = float(row.get("stake_units", 1.0))
    except (TypeError, ValueError):
        stake = 1.0
    try:
        gross_ur = float(row.get("unit_result"))
    except (TypeError, ValueError):
        return None
    breakeven = breakeven_edge_prob(venue, price, size=stake, side="taker")
    if breakeven is None:
        return None
    cost_units = breakeven * stake  # see module docstring: exact, not approximate
    return {
        "venue": venue,
        "cost_units": round(cost_units, 6),
        "gross_units": round(gross_ur, 6),
        "after_cost_units": round(gross_ur - cost_units, 6),
    }


def _channel_after_cost(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    gross_total = 0.0
    after_total = 0.0
    cost_total = 0.0
    n_costed = 0
    by_venue: Dict[str, int] = {}
    for r in rows:
        rec = after_cost_units(r)
        if rec is None:
            continue
        n_costed += 1
        gross_total += rec["gross_units"]
        after_total += rec["after_cost_units"]
        cost_total += rec["cost_units"]
        by_venue[rec["venue"]] = by_venue.get(rec["venue"], 0) + 1
    return {
        "n_measurable": len(rows),
        "n_costed": n_costed,
        "gross_units": round(gross_total, 3),
        "after_cost_units": round(after_total, 3),
        "total_cost_units": round(cost_total, 3),
        "by_venue": by_venue,
        "sign_flip": (gross_total > 0.0) != (after_total > 0.0) if n_costed else False,
    }


def scoreboard(ledger: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build the per-channel after-cost P&L dict (pure; no printing/I-O)."""
    if ledger is None:
        ledger = load_ledger()
    settled = _dedup_settled(ledger)

    by_ch: Dict[str, List[Dict[str, Any]]] = {}
    for r in settled:
        if not _is_measurable(r):
            continue  # only measurable (true_close, not off-market) rows can be costed
        ch = _channel_of(r)
        by_ch.setdefault(ch, []).append(r)

    channels: Dict[str, Any] = {}
    for ch, rows in by_ch.items():
        c = _channel_after_cost(rows)
        c["label"] = _CHANNEL_LABEL.get(ch, ch)
        channels[ch] = c

    return {"channels": channels}


def render(board: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("AFTER-COST CHANNEL P&L -- taker replay through cost_model (units only)")
    lines.append("=" * 78)
    hdr = ("%-18s %5s %6s %10s %10s %10s  %s"
           % ("channel", "meas", "costed", "gross_u", "cost_u", "net_u", "flip?"))
    lines.append(hdr)
    lines.append("-" * 78)
    for ch in sorted(board["channels"], key=lambda c: -board["channels"][c]["n_measurable"]):
        c = board["channels"][ch]
        lines.append("%-18s %5d %6d %+10.2f %10.2f %+10.2f  %s"
                     % (c["label"], c["n_measurable"], c["n_costed"],
                        c["gross_units"], c["total_cost_units"], c["after_cost_units"],
                        "YES" if c["sign_flip"] else "no"))
    lines.append("-" * 78)
    lines.append("flip? = after-cost sign differs from gross sign (a channel that LOOKS")
    lines.append("+EV gross but is NOT after real fees, or vice versa).")
    lines.append("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    board = scoreboard()
    print(render(board))
    try:
        os.makedirs(os.path.dirname(_OUT_JSON), exist_ok=True)
        with open(_OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(board, fh, indent=1)
        print("\nwrote %s" % _OUT_JSON)
    except OSError as exc:
        print("(after_cost_scoreboard JSON not written: %s)" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
