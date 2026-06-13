"""clv.py — HONEST closing-line-value (CLV) tracker math + append-only ledger.

CLV is the backward-looking TRUTH metric of betting skill: did the PRICE you
took at bet time beat the PRICE at the close?  POSITIVE CLV = you beat the
close.  It is NOT a forward edge and NOT a realized-return claim — markets
are efficient and NO model edge is ever asserted here.  It records what
already happened to a price; it predicts nothing.

CLV FORMULA (single source of truth)
====================================
Implied prob from a price:  decimal d>0 -> p = 1/d ;  american o -> p =
100/(o+100) if o>=0 else |o|/(|o|+100).
PRIMARY (price/odds CLV — the headline truth metric):
    clv_pct = (close_prob - bet_prob) / bet_prob * 100   (POSITIVE = beat close)
    ev_delta_usd = clv_pct / 100 * stake                 (sized, not realized P/L)
No-vig variant (opposite-side close supplied): close_prob_novig =
close_prob_side / (close_prob_side + close_prob_other), then the same
(close - bet)/bet subtraction on the stripped prob.
DIAGNOSTIC ONLY (line CLV, NOT the headline):
    over: line_clv = close_line - bet_line ;  under: line_clv = bet_line - close_line
This is what ``src/prediction/betting_portfolio.record_clv`` computes; we do
NOT import or reuse it — it conflates line-movement with price value and gets
the PRICE sign wrong.  We use PRICE-CLV as headline, line_clv as diagnostic.
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

_HONEST_NOTE = (
    "CLV is backward-looking: did your bet-time price beat the closing price? "
    "Positive = you beat the close. A record of past prices, not a forward "
    "edge and not realized P/L. Markets are efficient; no model edge is claimed."
)

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

# ── price / probability conversion ───────────────────────────────────────────

def _decimal_to_prob(decimal: float) -> float:
    d = float(decimal)
    if d <= 0:
        raise ValueError(f"decimal price must be > 0, got {decimal!r}")
    return 1.0 / d

def _american_to_decimal(odds: float) -> float:
    o = float(odds)
    return 1.0 + (o / 100.0 if o >= 0 else 100.0 / abs(o))

def _to_decimal(odds: float, fmt: str = "decimal") -> float:
    if fmt == "american":
        return _american_to_decimal(odds)
    if fmt != "decimal":
        raise ValueError(f"unknown fmt {fmt!r} (use 'decimal' or 'american')")
    d = float(odds)
    if d <= 0:
        raise ValueError(f"decimal price must be > 0, got {odds!r}")
    return d

def _compute_clv(
    bet_dec: float, close_dec: float, stake: float,
    close_dec_other: Optional[float] = None,
) -> tuple[float, float]:
    """Return (clv_pct, ev_delta_usd). Positive clv_pct => you beat the close."""
    bet_prob = _decimal_to_prob(bet_dec)
    close_prob = _decimal_to_prob(close_dec)
    if close_dec_other is not None:  # devig the close to a no-vig prob
        denom = close_prob + _decimal_to_prob(close_dec_other)
        if denom > 0:
            close_prob = close_prob / denom
    clv_pct = (close_prob - bet_prob) / bet_prob * 100.0
    return clv_pct, clv_pct / 100.0 * float(stake)

def _line_clv(side: str, bet_line: float, close_line: float) -> float:
    """Diagnostic line CLV (NOT the headline). over: close-bet; under: bet-close."""
    if (side or "").strip().lower() == "under":
        return float(bet_line) - float(close_line)
    return float(close_line) - float(bet_line)

# ── data model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PickCLV:
    pick_id: str
    sport: str
    event_id: str
    market: str
    side: str
    bet_decimal: float
    stake: float = 1.0
    settled: bool = False
    close_decimal: Optional[float] = None
    bet_prob: Optional[float] = None
    close_prob: Optional[float] = None
    clv_pct: Optional[float] = None
    ev_delta_usd: Optional[float] = None
    line_clv: Optional[float] = None

# ── ledger paths + IO ─────────────────────────────────────────────────────────

def _ledger_path(root: Optional[Path], sport: str) -> Path:
    base = Path(root) if root is not None else _repo_root()
    return base / "data" / "domains" / sport / "clv" / "picks.jsonl"

def _append_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

def _iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def _all_ledger_paths(root: Optional[Path], sport: Optional[str]) -> list[Path]:
    base = Path(root) if root is not None else _repo_root()
    if sport is not None:
        return [_ledger_path(root, sport)]
    domains = base / "data" / "domains"
    if not domains.exists():
        return []
    return sorted(domains.glob("*/clv/picks.jsonl"))

def _collapse(rows: Iterable[dict]) -> list[PickCLV]:
    """Collapse append-only rows to latest state per pick_id (settle wins)."""
    state: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        pid = row.get("pick_id")
        if not pid:
            continue
        if pid not in state:
            state[pid] = {}
            order.append(pid)
        state[pid].update(row)
    out: list[PickCLV] = []
    for pid in order:
        r = state[pid]
        out.append(PickCLV(
            pick_id=pid, sport=r.get("sport", ""), event_id=r.get("event_id", ""),
            market=r.get("market", ""), side=r.get("side", ""),
            bet_decimal=float(r.get("bet_decimal", 0.0)),
            stake=float(r.get("stake", 1.0)), settled=bool(r.get("settled", False)),
            close_decimal=r.get("close_decimal"), bet_prob=r.get("bet_prob"),
            close_prob=r.get("close_prob"), clv_pct=r.get("clv_pct"),
            ev_delta_usd=r.get("ev_delta_usd"), line_clv=r.get("line_clv"),
        ))
    return out

# ── public API ────────────────────────────────────────────────────────────────

def append_pick(
    sport: str, event_id: str, market: str, side: str, bet_odds: float,
    stake: float = 1.0, bet_line: Optional[float] = None,
    ts_utc: Optional[str] = None, fmt: str = "decimal",
    pick_id: Optional[str] = None, root: Optional[Path] = None,
) -> str:
    """Append an unsettled pick to the gitignored-local JSONL ledger. Returns pick_id."""
    ts = ts_utc or datetime.now(timezone.utc).isoformat()
    bet_dec = _to_decimal(bet_odds, fmt)
    if pick_id is None:
        key = f"{sport}|{event_id}|{market}|{side}|{ts}"
        pick_id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    row = {
        "kind": "pick", "pick_id": pick_id, "ts_utc": ts, "sport": sport,
        "event_id": event_id, "market": market, "side": side,
        "bet_decimal": bet_dec, "bet_prob": _decimal_to_prob(bet_dec),
        "bet_line": bet_line, "stake": float(stake), "settled": False,
    }
    _append_row(_ledger_path(root, sport), row)
    return pick_id

def settle_pick(
    pick_id: str, close_odds: float, close_line: Optional[float] = None,
    close_odds_other: Optional[float] = None, fmt: str = "decimal",
    root: Optional[Path] = None, sport: Optional[str] = None,
) -> PickCLV:
    """Append a settle row computing PRICE-CLV; return the collapsed settled pick."""
    raw = list(_iter_jsonl(_ledger_path(root, sport)) if sport else [])
    if not sport:
        raw = list(_iter_jsonl(_ledger_path(root, _sport_of(root, pick_id))))
    pick = next((p for p in _collapse(raw) if p.pick_id == pick_id), None)
    if pick is None:
        raise KeyError(f"pick_id {pick_id!r} not found in ledger")
    bet_line = next(
        (r.get("bet_line") for r in raw
         if r.get("pick_id") == pick_id and r.get("bet_line") is not None), None
    )
    close_dec = _to_decimal(close_odds, fmt)
    close_dec_other = (
        _to_decimal(close_odds_other, fmt) if close_odds_other is not None else None
    )
    clv_pct, ev_delta = _compute_clv(
        pick.bet_decimal, close_dec, pick.stake, close_dec_other
    )
    row = {
        "kind": "settle", "pick_id": pick_id,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "sport": pick.sport, "close_decimal": close_dec,
        "close_prob": _decimal_to_prob(close_dec),
        "clv_pct": clv_pct, "ev_delta_usd": ev_delta,
        "line_clv": (
            _line_clv(pick.side, float(bet_line), close_line)
            if close_line is not None and bet_line is not None else None
        ),
        "settled": True,
    }
    _append_row(_ledger_path(root, pick.sport), row)
    return next(
        p for p in _collapse(_iter_jsonl(_ledger_path(root, pick.sport)))
        if p.pick_id == pick_id
    )

def _sport_of(root: Optional[Path], pick_id: str) -> str:
    for p in load_picks(root=root):
        if p.pick_id == pick_id:
            return p.sport
    raise KeyError(f"pick_id {pick_id!r} not found in any ledger")

def load_picks(root: Optional[Path] = None, sport: Optional[str] = None) -> list[PickCLV]:
    """Read + collapse the ledger(s) to one latest-state PickCLV per pick_id."""
    rows: list[dict] = []
    for path in _all_ledger_paths(root, sport):
        rows.extend(_iter_jsonl(path))
    return _collapse(rows)

_DIST_KEYS = ("p10", "p25", "p50", "p75", "p90", "min", "max", "std")

def _dist(values: list[float]) -> dict[str, float]:
    if not values:
        return {k: 0.0 for k in _DIST_KEYS}
    s = sorted(values)

    def pct(q: float) -> float:
        idx = q * (len(s) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (idx - lo)

    return {
        "p10": pct(0.10), "p25": pct(0.25), "p50": pct(0.50),
        "p75": pct(0.75), "p90": pct(0.90), "min": s[0], "max": s[-1],
        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }

def _group(picks: list[PickCLV], key: Any) -> dict[str, dict]:
    out: dict[str, list[float]] = {}
    for p in picks:
        out.setdefault(key(p), []).append(float(p.clv_pct))
    return {
        k: {"n": len(v), "mean_clv_pct": statistics.fmean(v),
            "pct_positive": sum(1 for x in v if x > 0) / len(v)}
        for k, v in out.items()
    }

def clv_summary(
    picks: Optional[list[PickCLV]] = None, root: Optional[Path] = None
) -> dict:
    """Aggregate settled CLV. Zero settled => all-zero numerics + honest_note."""
    if picks is None:
        picks = load_picks(root=root)
    settled = [p for p in picks if p.settled and p.clv_pct is not None]
    vals = [float(p.clv_pct) for p in settled]
    n = len(settled)
    return {
        "n_picks": len(picks),
        "n_settled": n,
        "mean_clv_pct": statistics.fmean(vals) if n else 0.0,
        "median_clv_pct": statistics.median(vals) if n else 0.0,
        "pct_positive": (sum(1 for x in vals if x > 0) / n) if n else 0.0,
        "total_ev_delta_usd": sum(float(p.ev_delta_usd or 0.0) for p in settled),
        "clv_pct_distribution": _dist(vals),
        "by_sport": _group(settled, lambda p: p.sport),
        "by_market": _group(settled, lambda p: p.market),
        "honest_note": _HONEST_NOTE,
    }

if __name__ == "__main__":  # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(description="Honest CLV tracker")
    ap.add_argument("--summary", action="store_true", help="print clv_summary")
    if ap.parse_args().summary:
        print(json.dumps(clv_summary(), indent=2))
