"""scripts.platformkit.clv_ledger -- append-only bet ledger + closing-line value.

The honest track-record layer. A bet is recorded WHEN PLACED with the price the
human actually got; later, when the market closes, the bet is settled against the
two-way closing line and its closing-line value (CLV) is computed.

Honesty contract (binding):
  * This is the PROOF GATE before any real money. We do NOT claim a model edge.
    CLV is the one honest yardstick: did you lock a BETTER NUMBER than the close?
  * Append-only, mirroring data/frontend/bet_intents.jsonl: every record is a new
    line; nothing is ever overwritten. Settlement appends a settled twin, it does
    not mutate the open row.
  * Devig is NEVER reimplemented here -- we reuse the vetted Shin solver via
    scripts.platformkit.odds_shop.devig_twoway (which wraps eval_gate.shin).

CLV SIGN (stated explicitly -- the repo has a documented 'record_clv backwards'
gotcha, so this is deliberate):
  CLV is POSITIVE when you GOT A BETTER NUMBER than the close. For a moneyline /
  two-way market we devig the closing line to a no-vig FAIR probability for the
  side you bet (fair_close). Your taken decimal price implies taken_p = 1/decimal.
  You beat the close iff your taken price implies a LOWER probability than the
  fair close -- you are being paid as if the outcome is less likely than the
  market's settled estimate. Hence:

      clv_pct = (fair_close - taken_p) / taken_p * 100.0

  taken_p < fair_close  -> clv_pct > 0  (better number than the close = good)
  taken_p > fair_close  -> clv_pct < 0  (worse number than the close = bad)

  Equivalently in price space: fair decimal at the close is 1/fair_close; you beat
  it when your taken decimal > that fair decimal. Same sign, by construction.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; no secrets; reuse
the vetted devig; never claim a money edge.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.odds_shop import devig_twoway

# Append-only ledger lives under the gitignored data/ tree -- the human's own
# record, never sent anywhere. Override with FRONTEND_CLV_LEDGER env or `path=`.
_HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = _HERE.parents[1] / "data" / "frontend" / "clv_ledger.jsonl"

_SIDE_HOME = "home"
_SIDE_AWAY = "away"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_bet(
    sport: str,
    matchup: str,
    side: str,
    taken_book: str,
    taken_decimal: float,
    model_prob: Optional[float] = None,
    stake: float = 0.0,
    *,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append one open bet to the CLV ledger and return the stored record.

    *side* must be 'home' or 'away' (the two-way side you backed). *taken_decimal*
    is the decimal price you actually got. Pure I/O on a local JSONL file -- NO
    network, NO book API, never overwrites an existing line.
    """
    s = str(side).strip().lower()
    if s not in (_SIDE_HOME, _SIDE_AWAY):
        raise ValueError("side must be 'home' or 'away', got %r" % (side,))
    dec = float(taken_decimal)
    if dec <= 1.0:
        raise ValueError("taken_decimal must be > 1.0, got %r" % (taken_decimal,))
    record: Dict[str, Any] = {
        "ts": _now_iso(),
        "sport": str(sport),
        "matchup": str(matchup),
        "side": s,
        "taken_book": str(taken_book),
        "taken_decimal": dec,
        "model_prob": (float(model_prob) if model_prob is not None else None),
        "stake": float(stake),
        "status": "open",
        "executed": False,  # invariant: this tool NEVER places a real bet
    }
    target = Path(path) if path is not None else DEFAULT_LEDGER
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return record


def compute_clv(
    side: str,
    taken_decimal: float,
    closing_decimal_home: float,
    closing_decimal_away: float,
) -> Dict[str, Any]:
    """Pure CLV math for one two-way bet. No I/O.

    Devigs the closing line (home, away) to no-vig fair probabilities via the
    vetted Shin solver, then compares your taken price's implied prob against the
    fair closing prob FOR THE SIDE YOU BET. See module docstring for the sign:
    positive CLV = you got a better number than the close.

    Returns {taken_p, fair_close, clv_pct, fair_close_decimal, beat_close}.
    """
    s = str(side).strip().lower()
    if s not in (_SIDE_HOME, _SIDE_AWAY):
        raise ValueError("side must be 'home' or 'away', got %r" % (side,))
    fair_home, fair_away = devig_twoway(closing_decimal_home, closing_decimal_away)
    fair_close = fair_home if s == _SIDE_HOME else fair_away
    taken_p = 1.0 / float(taken_decimal)
    # Positive when taken price implies a LOWER prob than the fair close = better number.
    clv_pct = (fair_close - taken_p) / taken_p * 100.0
    fair_close_decimal = (1.0 / fair_close) if fair_close > 0 else None
    return {
        "taken_p": round(taken_p, 8),
        "fair_close": round(fair_close, 8),
        "fair_close_decimal": (round(fair_close_decimal, 6)
                               if fair_close_decimal is not None else None),
        "clv_pct": round(clv_pct, 6),
        "beat_close": clv_pct > 0.0,
    }


def settle_closing_line(
    bet: Dict[str, Any],
    closing_decimal_home: float,
    closing_decimal_away: float,
) -> Dict[str, Any]:
    """Return a SETTLED twin of *bet* with CLV fields filled in.

    Pure (no I/O): the caller decides where to persist (use append_settlement to
    write the settled twin as a new append-only line). The original open record is
    never mutated. *bet* must carry 'side' and 'taken_decimal'.
    """
    clv = compute_clv(
        bet["side"], bet["taken_decimal"],
        closing_decimal_home, closing_decimal_away,
    )
    settled = dict(bet)
    settled["status"] = "settled"
    settled["settled_at"] = _now_iso()
    settled["closing_decimal_home"] = float(closing_decimal_home)
    settled["closing_decimal_away"] = float(closing_decimal_away)
    settled["fair_close_prob"] = clv["fair_close"]
    settled["taken_implied_prob"] = clv["taken_p"]
    settled["clv_pct"] = clv["clv_pct"]
    settled["beat_close"] = clv["beat_close"]
    return settled


def append_settlement(
    settled: Dict[str, Any], *, path: Optional[Path] = None
) -> Dict[str, Any]:
    """Append a settled record to the ledger (append-only; never overwrites)."""
    target = Path(path) if path is not None else DEFAULT_LEDGER
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(settled, default=str) + "\n")
    return settled


def load_ledger(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every JSONL line from the ledger. Missing file -> empty list."""
    target = Path(path) if path is not None else DEFAULT_LEDGER
    if not target.exists():
        return []
    out: List[Dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a partial trailing write, never crash
    return out


def clv_summary(ledger: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate CLV over SETTLED bets in *ledger*.

    Returns n_bets (settled), pct_beat_close, mean_clv_pct, and a by_sport
    breakdown. Open/unsettled rows (no clv_pct) are ignored. CLV is the honest
    yardstick -- this is a track record, not an edge claim.
    """
    settled = [
        b for b in ledger
        if b.get("status") == "settled" and b.get("clv_pct") is not None
    ]
    n = len(settled)
    if n == 0:
        return {"n_bets": 0, "pct_beat_close": None, "mean_clv_pct": None,
                "by_sport": {}}
    clvs = [float(b["clv_pct"]) for b in settled]
    beats = sum(1 for c in clvs if c > 0.0)
    by_sport: Dict[str, Any] = {}
    for b in settled:
        sport = str(b.get("sport", "unknown"))
        bucket = by_sport.setdefault(sport, {"n": 0, "_sum": 0.0, "_beats": 0})
        c = float(b["clv_pct"])
        bucket["n"] += 1
        bucket["_sum"] += c
        bucket["_beats"] += 1 if c > 0.0 else 0
    for sport, bucket in by_sport.items():
        cnt = bucket["n"]
        bucket["mean_clv_pct"] = round(bucket.pop("_sum") / cnt, 6)
        bucket["pct_beat_close"] = round(100.0 * bucket.pop("_beats") / cnt, 4)
    return {
        "n_bets": n,
        "pct_beat_close": round(100.0 * beats / n, 4),
        "mean_clv_pct": round(sum(clvs) / n, 6),
        "by_sport": by_sport,
    }


__all__ = [
    "record_bet",
    "compute_clv",
    "settle_closing_line",
    "append_settlement",
    "load_ledger",
    "clv_summary",
]
