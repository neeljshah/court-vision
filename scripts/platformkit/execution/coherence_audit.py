"""scripts.platformkit.execution.coherence_audit -- sum-to-one MEASUREMENT over
captured books. CALIBRATION ONLY: no trading logic, no order path. Fees are
REUSED verbatim from venue_fees.py; the only formula not simply called is the
HHI complete-set-cost APPROXIMATION 0.07*(1-HHI) taker / 0.0175*(1-HHI) maker
(Kalshi batch-ceiling shortcut, MASTER_PLAN_2026-09-14 section 2b.4/2b.6), which
reuses venue_fees's own Kalshi coefficients by name rather than retyping them.

GROUPING (set_id + size on every output row): kalshi event_ticker with >=2
tickers -> multi-outcome set (yes side per ticker, e.g. a strike suffix); 1
ticker -> binary set (yes+no, same row -- no is ALGEBRAICALLY derived from yes
in kalshi_book_row.book_row, so this is a construction check, not a second
quote). polymarket condition_id with >=2 token_ids -> one set, one leg/token.
ALIGNMENT: anchors = the first leg's own timestamps; any other leg without a
point within 2s drops the WHOLE snapshot (never partial-summed).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_coherence_audit.py -q
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from scripts.platformkit.execution import venue_fees as fees

ALIGN_WINDOW_MS = 2000
GROUPING_RULE = ("kalshi: event_ticker w/ >=2 tickers -> multi-outcome (yes side per ticker); "
                  "1 ticker -> binary (yes+no). polymarket: condition_id w/ >=2 token_ids -> one set.")
_SIZE_BUCKETS = (("2", lambda n: n == 2), ("3-8", lambda n: 3 <= n <= 8), ("9+", lambda n: n >= 9))
_MINUTES_BUCKETS = ((">60", lambda m: m > 60), ("30-60", lambda m: 30 <= m <= 60),
                     ("10-30", lambda m: 10 <= m < 30), ("3-10", lambda m: 3 <= m < 10),
                     ("<3", lambda m: m < 3))

def _size_bucket(n: int) -> str:
    for label, pred in _SIZE_BUCKETS:
        if pred(n):
            return label
    return "9+"
def _minutes_bucket(m: Optional[float]) -> str:
    if m is None:
        return "unknown"
    for label, pred in _MINUTES_BUCKETS:
        if pred(m):
            return label
    return "unknown"

def minutes_to_close(row: Dict[str, Any], ts_ms: int) -> Optional[float]:
    """row.minutes_to_close if present, else derived from row.close_time (ISO8601) -- NEITHER field is written by kalshi_book_row/polymarket_book_row today (see NOT_VERIFIED)."""
    mtc = row.get("minutes_to_close")
    if isinstance(mtc, (int, float)):
        return float(mtc)
    try:
        s = str(row.get("close_time"))
        s = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(s)
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return (dt.timestamp() * 1000.0 - ts_ms) / 60000.0
def load_rows(paths: Sequence[str], venue: str) -> List[Dict[str, Any]]:
    """Every 'snapshot' row for *venue* out of every *.jsonl under *paths* (files or dirs, recursive). Malformed lines/files are skipped, never raise."""
    files: List[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.jsonl")))
        elif path.is_file():
            files.append(path)
    out: List[Dict[str, Any]] = []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("record_type") == "snapshot" and row.get("venue") == venue:
                out.append(row)
    return out
def _kalshi_leg(r: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    yb, ya = r.get("yes_bid"), r.get("yes_ask")
    return ((yb + ya) / 2.0 if yb is not None and ya is not None else None), yb, ya
def _poly_leg(r: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    bid, ask, mid = r.get("best_bid"), r.get("best_ask"), r.get("mid")
    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
    return mid, bid, ask
def _points(rows: List[Dict[str, Any]], leg_of) -> List[Dict[str, Any]]:
    """One {ts_ms, mid, bid, ask, row} point per row with a full (mid, bid, ask) and ts_ms; sorted ASC by ts_ms."""
    pts = []
    for r in rows:
        mid, bid, ask = leg_of(r)
        if mid is not None and bid is not None and ask is not None and r.get("ts_ms") is not None:
            pts.append({"ts_ms": r["ts_ms"], "mid": mid, "bid": bid, "ask": ask, "row": r})
    return sorted(pts, key=lambda p: p["ts_ms"])
def _sport_of(legs_rows: Dict[str, List[Dict[str, Any]]]) -> Optional[str]:
    for pts in legs_rows.values():
        if pts:
            return pts[0]["row"].get("sport")
    return None

def _align_snapshots(set_id: str, legs_rows: Dict[str, List[Dict[str, Any]]],
                      window_ms: int = ALIGN_WINDOW_MS) -> Iterator[Dict[str, Any]]:
    leg_ids = sorted(k for k, v in legs_rows.items() if v)
    if len(leg_ids) < 2:
        return
    sport = _sport_of(legs_rows)
    for anchor in legs_rows[leg_ids[0]]:
        legs, ok = {}, True
        for lid in leg_ids:
            best = min(legs_rows[lid], key=lambda p: abs(p["ts_ms"] - anchor["ts_ms"]))
            if abs(best["ts_ms"] - anchor["ts_ms"]) > window_ms:
                ok = False
                break
            legs[lid] = best
        if ok:
            yield {"set_id": set_id, "sport": sport, "anchor_ts_ms": anchor["ts_ms"], "legs": legs}
def _kalshi_binary_snapshots(ticker: str, rows: List[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    for r in rows:
        yb, ya, nb, na = r.get("yes_bid"), r.get("yes_ask"), r.get("no_bid"), r.get("no_ask")
        if None in (yb, ya, nb, na) or r.get("ts_ms") is None:
            continue
        legs = {"yes": {"ts_ms": r["ts_ms"], "mid": (yb + ya) / 2.0, "bid": yb, "ask": ya, "row": r},
                "no": {"ts_ms": r["ts_ms"], "mid": (nb + na) / 2.0, "bid": nb, "ask": na, "row": r}}
        yield {"set_id": "kalshi:binary:%s" % ticker, "sport": r.get("sport"),
               "anchor_ts_ms": r["ts_ms"], "legs": legs}
def build_snapshots(rows: List[Dict[str, Any]], venue: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if venue == "kalshi":
        by_event: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for r in rows:
            et, tk = r.get("event_ticker"), r.get("ticker")
            if et and tk:
                by_event[et][tk].append(r)
        for et, tickers in by_event.items():
            if len(tickers) >= 2:
                legs_rows = {tk: _points(rs, _kalshi_leg) for tk, rs in tickers.items()}
                out.extend(_align_snapshots("kalshi:multi:%s" % et, legs_rows))
            else:
                (tk, rs), = tickers.items()
                out.extend(_kalshi_binary_snapshots(tk, rs))
    else:  # polymarket
        by_cond: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for r in rows:
            cid, tok = r.get("condition_id"), r.get("token_id")
            if cid and tok:
                by_cond[cid][tok].append(r)
        for cid, tokens in by_cond.items():
            if len(tokens) >= 2:
                legs_rows = {tok: _points(rs, _poly_leg) for tok, rs in tokens.items()}
                out.extend(_align_snapshots("poly:%s" % cid, legs_rows))
    return out

def _fee(venue: str, mode: str, price: float) -> float:
    if venue == "kalshi":
        return fees.fee_kalshi_taker(1.0, price) if mode == "taker" else fees.fee_kalshi_maker(1.0, price)
    return fees.fee_polymarket(mode, 1.0, price)
def _hhi(mids: List[float]) -> Optional[float]:
    total = sum(mids)
    return sum((m / total) ** 2 for m in mids) if total > 0 else None
def compute_metrics(snap: Dict[str, Any], venue: str) -> Dict[str, Any]:
    legs = snap["legs"]
    mids = [l["mid"] for l in legs.values()]
    asks = [l["ask"] for l in legs.values()]
    bids = [l["bid"] for l in legs.values()]
    sum_mid, sum_ask, sum_bid = sum(mids), sum(asks), sum(bids)
    taker_fees_total = sum(_fee(venue, "taker", a) for a in asks)
    maker_fees_total = sum(_fee(venue, "maker", b) for b in bids)
    buy_all_pre, sell_all_pre = 1.0 - sum_ask, sum_bid - 1.0
    hhi = _hhi(mids)
    if venue == "kalshi" and hhi is not None:  # reused coefs, not restated
        fee_taker_approx, fee_maker_approx = fees._KALSHI_TAKER_COEF * (1.0 - hhi), fees._KALSHI_MAKER_COEF * (1.0 - hhi)
    else:
        fee_taker_approx, fee_maker_approx = taker_fees_total, maker_fees_total
    leg_residuals = [{"leg_id": lid, "mid": l["mid"],
                       "residual": (l["mid"] - l["mid"] / sum_mid) if sum_mid else None}
                      for lid, l in legs.items()]
    any_row = next(iter(legs.values()))["row"]
    return {
        "set_id": snap["set_id"], "sport": snap["sport"] or "unknown", "size": len(legs),
        "anchor_ts_ms": snap["anchor_ts_ms"], "minutes_to_close": minutes_to_close(any_row, snap["anchor_ts_ms"]),
        "sum_mid": sum_mid, "sum_ask": sum_ask, "sum_bid": sum_bid, "residual_mid": sum_mid - 1.0,
        "taker_fees_total": taker_fees_total, "maker_fees_total": maker_fees_total, "buy_all_pre_fee": buy_all_pre, "sell_all_pre_fee": sell_all_pre,
        "buy_all": buy_all_pre - taker_fees_total, "sell_all": sell_all_pre - maker_fees_total,
        "hhi": hhi, "complete_set_fee_taker_approx": fee_taker_approx,
        "complete_set_fee_maker_approx": fee_maker_approx, "leg_residuals": leg_residuals,
    }
def _stat(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {"n": 0, "median": None, "p90": None}
    vs = sorted(vals)
    return {"n": len(vs), "median": round(statistics.median(vs), 6),
             "p90": round(vs[min(len(vs) - 1, int(round(0.9 * (len(vs) - 1))))], 6)}
def _share_pct(flags: List[bool]) -> Optional[float]:
    return round(100.0 * sum(flags) / len(flags), 4) if flags else None

def build_distributions(obs: List[Dict[str, Any]]) -> Dict[str, Any]:
    buckets: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for o in obs:
        key = (o["sport"], _size_bucket(o["size"]), _minutes_bucket(o["minutes_to_close"]))
        b = buckets.setdefault(key, {"snaps": [], "set_ids": set()})
        b["snaps"].append(o)
        b["set_ids"].add(o["set_id"])
    out: Dict[str, Any] = {}
    for (sport, size_b, min_b), b in sorted(buckets.items()):
        snaps = b["snaps"]
        top20 = sorted(({"set_id": s["set_id"], "leg_id": lr["leg_id"], "residual": lr["residual"]}
                         for s in snaps for lr in s["leg_residuals"] if lr["residual"] is not None),
                        key=lambda r: abs(r["residual"]), reverse=True)[:20]
        out["%s|%s|%s" % (sport, size_b, min_b)] = {
            "n_snapshots": len(snaps), "n_sets": len(b["set_ids"]), "abs_residual_mid": _stat([abs(s["residual_mid"]) for s in snaps]),
            "share_buy_all_gt0_pre_fee_pct": _share_pct([s["buy_all_pre_fee"] > 0 for s in snaps]), "share_sell_all_gt0_pre_fee_pct": _share_pct([s["sell_all_pre_fee"] > 0 for s in snaps]),
            "share_buy_all_gt0_post_fee_pct": _share_pct([s["buy_all"] > 0 for s in snaps]), "share_sell_all_gt0_post_fee_pct": _share_pct([s["sell_all"] > 0 for s in snaps]),
            "top20_option_residuals": top20,
        }
    return out

def build_set_summary(obs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_set: Dict[str, Dict[str, Any]] = {}
    for o in obs:
        s = by_set.setdefault(o["set_id"], {"sport": o["sport"], "size": o["size"], "hhi": [],
                                             "fee_taker": [], "fee_maker": []})
        if o["hhi"] is not None:
            s["hhi"].append(o["hhi"])
            s["fee_taker"].append(o["complete_set_fee_taker_approx"])
            s["fee_maker"].append(o["complete_set_fee_maker_approx"])
    out = []
    for set_id, s in sorted(by_set.items()):
        out.append({"set_id": set_id, "sport": s["sport"], "size": s["size"], "n_snapshots": len(s["hhi"]),
                     "hhi_median": round(statistics.median(s["hhi"]), 6) if s["hhi"] else None,
                     "complete_set_fee_taker_approx_median": round(statistics.median(s["fee_taker"]), 6) if s["fee_taker"] else None,
                     "complete_set_fee_maker_approx_median": round(statistics.median(s["fee_maker"]), 6) if s["fee_maker"] else None})
    return out
def build_verdict(obs: List[Dict[str, Any]], venue: str) -> Dict[str, Any]:
    if not obs:
        return {"venue": venue, "verdict": "NO_DATA", "n_snapshots": 0}
    buy_post = [o["buy_all"] for o in obs]
    sell_post = [o["sell_all"] for o in obs]
    buy_med, sell_med = statistics.median(buy_post), statistics.median(sell_post)
    share_gt0 = _share_pct([b > 0 or s > 0 for b, s in zip(buy_post, sell_post)])
    coherent = buy_med < 0 and sell_med < 0 and (share_gt0 or 0.0) < 1.0
    return {"venue": venue, "verdict": "COHERENT" if coherent else "RESIDUAL_PRESENT",
             "buy_all_post_fee_median": round(buy_med, 6), "sell_all_post_fee_median": round(sell_med, 6),
             "share_buy_or_sell_gt0_post_fee_pct": share_gt0, "n_snapshots": len(obs)}

NOT_VERIFIED = [
    "no real venue capture consumed by this module -- input rows are whatever --books points at",
    "Kalshi event_ticker->outcome-set grouping is a heuristic: assumes every ticker under one event_ticker is a mutually exclusive outcome of the same question; a mixed event_ticker would misgroup",
    "Kalshi binary (yes+no) sets are a construction check, not an independent second quote -- kalshi_book_row.book_row derives no_bid/no_ask algebraically from yes_bid/yes_ask",
    "Polymarket condition_id->token pairing assumes every token under one condition_id is a mutually exclusive outcome, per polymarket_book_row's own field, not re-verified against gamma market metadata",
    "minutes_to_close reads an optional row.close_time/minutes_to_close field that neither kalshi_book_row.book_row nor polymarket_book_row.book_row writes today -- real rows land in 'unknown'",
]

def run(book_paths: Sequence[str], venue: str) -> Dict[str, Any]:
    rows = load_rows(book_paths, venue)
    obs = [compute_metrics(s, venue) for s in build_snapshots(rows, venue)]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "venue": venue, "claim": "calibration_only", "grouping_rule": GROUPING_RULE,
        "n_input_rows": len(rows), "n_sets": len({o["set_id"] for o in obs}), "n_snapshots": len(obs),
        "verdict": build_verdict(obs, venue), "distributions": build_distributions(obs),
        "sets": build_set_summary(obs), "not_verified": NOT_VERIFIED,
    }

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Sum-to-one coherence audit over captured order books (measurement only, no trading logic)")
    ap.add_argument("--books", nargs="+", required=True, help="jsonl file(s) or dir(s) to search recursively")
    ap.add_argument("--venue", choices=("kalshi", "polymarket"), required=True)
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)
    report = run(args.books, args.venue)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ("coherence_audit_%s.json" % args.venue)
    out_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True), encoding="ascii")
    print("no trading logic; calibration/measurement only")
    print(json.dumps({"out": str(out_path), "venue": args.venue, "n_sets": report["n_sets"],
                       "n_snapshots": report["n_snapshots"], "verdict": report["verdict"]["verdict"]},
                      ensure_ascii=True))
    return 0

__all__ = ["GROUPING_RULE", "load_rows", "build_snapshots", "compute_metrics", "build_distributions",
           "build_set_summary", "build_verdict", "run", "minutes_to_close"]

if __name__ == "__main__":
    raise SystemExit(main())
