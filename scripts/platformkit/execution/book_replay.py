"""scripts.platformkit.execution.book_replay -- Kalshi maker/taker fill-plausibility
replay over the CAPTURED depth archives. MEASUREMENT ONLY: no order path, no
policy change, no $ / ROI / edge claim -- price/probability terms only.
Two archives, do not conflate cadence: book_depth/kalshi/<date>.jsonl (ts,
ticker, best_bid, best_ask, trades_last_5m, sport) is dense (~40s median
per-ticker, verified 2026-07-09) but ONLY {mlb, wnba} -- used for Q2
(quote-cross fill proxy) + Q4 (adverse timing), sub-15-min resolution needed.
depth_history/<sport>/<date>.jsonl (ts, sport, ticker, yes_bids/yes_asks
ladders; yes_asks is the RAW no_dollars ladder -- fill_sim/depth_capture
convention, a resting NO-bid at p prices a YES-ask at 1-p) covers 6 sports at
~26min median cadence -- used for Q1 (spread/depth) + Q3 (taker cost), which
only need point-in-time levels.
HONESTY GAP (checked 2026-07-09): neither archive stores a per-trade PRICE
tape, only a trailing trades_last_5m COUNT + last_trade_ts (grep both trees
for a trade-price field: zero hits). The mission's literal Q2/Q4 test ("tape
prints AT that price") is NOT computable for ANY sport -- INSUFFICIENT_DATA,
never faked. Computed instead: a weaker quote-crossing proxy (a passive join
at best_bid is "plausibly filled" in a horizon if a LATER best_ask <= the
join price) -- upper bound only, queue position unknown.
INVARIANTS: <=300 LOC; ASCII; stdlib only; local-only output; never writes
data/registry/; never flips a flag. Test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/test_book_replay.py -q
"""
from __future__ import annotations

import glob
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[3]
BOOK_DEPTH_DIR = _REPO / "data" / "cache" / "book_depth" / "kalshi"
DEPTH_HISTORY_DIR = _REPO / "data" / "cache" / "depth_history"
LADDER_SPORTS = ["kbo", "mlb", "npb", "soccer_intl", "tennis", "wnba"]
DENSE_SPORTS = ["mlb", "wnba"]  # only sports book_depth/kalshi covers
HORIZONS_S = (60, 300, 900)  # 1 / 5 / 15 min

def _parse_ts(s: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
def _epoch(ts: Any) -> Optional[float]:
    dt = _parse_ts(ts)
    return dt.timestamp() if dt is not None else None

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Every parseable row in *path*; a malformed line is skipped, never raises."""
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out

def _rungs(ladder: Any) -> List[Tuple[float, float]]:
    """Valid (price, size) rungs, DESC by price (best-first). Never raises."""
    out: List[Tuple[float, float]] = []
    for r in ladder if isinstance(ladder, list) else []:
        try:
            p, sz = float(r[0]), float(r[1])
        except (TypeError, ValueError, IndexError):
            continue
        if 0.0 < p < 1.0 and sz > 0.0:
            out.append((p, sz))
    return sorted(out, key=lambda r: -r[0])

def ladder_best(yes_bids_raw: Any, yes_asks_raw: Any) -> Dict[str, Optional[float]]:
    """{best_bid, best_ask, thin3} from a depth_history row (yes_asks_raw is the
    RAW no_dollars ladder: best_ask = 1 - best resting NO-bid). None if empty."""
    bids, no_bids = _rungs(yes_bids_raw), _rungs(yes_asks_raw)
    return {
        "best_bid": bids[0][0] if bids else None,
        "best_ask": (1.0 - no_bids[0][0]) if no_bids else None,
        "thin3": round(sum(sz for _p, sz in bids[:3]) + sum(sz for _p, sz in no_bids[:3]), 2),
    }

def half_spread(best_bid: Optional[float], best_ask: Optional[float]) -> Optional[float]:
    """(ask-bid)/2 in price units (0-1). None if unquoted or crossed (bad book)."""
    if best_bid is None or best_ask is None or best_ask < best_bid:
        return None
    return (best_ask - best_bid) / 2.0

def phase_bucket(idx: int, n: int) -> str:
    """Capture-order tercile in one ticker's snapshot sequence -- a PROXY for game-phase (no true clock in this archive)."""
    if n <= 1:
        return "mid"
    frac = idx / (n - 1)
    return "early" if frac < 1 / 3 else ("late" if frac > 2 / 3 else "mid")

def quantile_breakpoints(values: List[float]) -> Tuple[float, float]:
    """(q33, q67) via sorted-index split. Empty -> (0, 0)."""
    vs = sorted(values)
    return (vs[len(vs) // 3], vs[(2 * len(vs)) // 3]) if vs else (0.0, 0.0)

def thinness_tercile(value: float, breakpoints: Tuple[float, float]) -> str:
    lo, hi = breakpoints
    return "thin" if value <= lo else ("thick" if value > hi else "mid")
def _stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0}
    vs = sorted(values)
    return {"n": len(vs), "median": round(statistics.median(vs), 5),
             "p25": round(vs[len(vs) // 4], 5), "p75": round(vs[(3 * len(vs)) // 4], 5)}

def detect_quote_cross(snaps: List[Tuple[float, Optional[float], Optional[float]]],
                        join_idx: int, horizon_s: float) -> Optional[float]:
    """*snaps* = one ticker's (t_epoch, best_bid, best_ask) sorted ASC by t. t_epoch
    of the FIRST later snapshot within horizon_s whose best_ask <= join_price
    (NECESSARY not sufficient for a fill; queue position unknown). None if no cross."""
    t0, join_price, _ = snaps[join_idx]
    if join_price is None:
        return None
    for t, _bid, ask in snaps[join_idx + 1:]:
        if t - t0 > horizon_s:
            break
        if ask is not None and ask <= join_price:
            return t
    return None

def mid_at_or_after(snaps: List[Tuple[float, Optional[float], Optional[float]]],
                     target_epoch: float, slack_s: float = 120.0) -> Optional[float]:
    """Mid of the first snapshot at/after target_epoch (within slack_s), else None."""
    for t, bid, ask in snaps:
        if t >= target_epoch:
            return None if (t - target_epoch > slack_s or bid is None or ask is None) else (bid + ask) / 2.0
    return None

def _group_by_ticker_sorted(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """{ticker: rows} sorted ASC by ts, dropping rows with no ticker/ts."""
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("ticker") and r.get("ts"):
            out[r["ticker"]].append(r)
    for tk in out:
        out[tk].sort(key=lambda r: str(r["ts"]))
    return out

def load_dense_rows() -> List[Dict[str, Any]]:
    """All book_depth/kalshi rows (mlb+wnba, dense cadence)."""
    out: List[Dict[str, Any]] = []
    for p in sorted(glob.glob(str(BOOK_DEPTH_DIR / "*.jsonl"))):
        out.extend(load_jsonl(Path(p)))
    return out

def load_ladder_rows(sport: str) -> List[Dict[str, Any]]:
    """All depth_history/<sport> rows, normalized with ladder_best merged in."""
    out: List[Dict[str, Any]] = []
    for p in sorted((DEPTH_HISTORY_DIR / sport).glob("*.jsonl")):
        for r in load_jsonl(p):
            out.append({**r, **ladder_best(r.get("yes_bids"), r.get("yes_asks"))})
    return out

def build_profile_and_taker_cost(sport_rows: Dict[str, List[Dict[str, Any]]]
                                  ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Q1 (spread/thinness by sport x phase_proxy) + Q3 (half-spread by sport x phase_proxy x thinness tercile), one pass per sport."""
    profile: Dict[str, Any] = {}
    taker: Dict[str, Any] = {}
    for sport, rows in sport_rows.items():
        thin_bps = quantile_breakpoints([r["thin3"] for r in rows if r.get("best_bid") is not None])
        spread_b: Dict[str, List[float]] = defaultdict(list)
        thin_b: Dict[str, List[float]] = defaultdict(list)
        cells: Dict[Tuple[str, str], List[float]] = defaultdict(list)
        for trs in _group_by_ticker_sorted(rows).values():
            n = len(trs)
            for i, r in enumerate(trs):
                hs = half_spread(r.get("best_bid"), r.get("best_ask"))
                if hs is None:
                    continue
                ph = phase_bucket(i, n)
                spread_b[ph].append(hs * 2.0)
                thin_b[ph].append(r["thin3"])
                cells[(ph, thinness_tercile(r["thin3"], thin_bps))].append(hs)
        profile[sport] = {ph: {"spread_price": _stats(spread_b[ph]), "thinness": _stats(thin_b[ph])}
                          for ph in ("early", "mid", "late")}
        taker[sport] = {"%s_x_%s" % k: _stats(v) for k, v in cells.items()}
    return profile, taker

def build_maker_fill_and_adverse(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Q2 (quote-cross proxy) + Q4 (adverse timing 5min post-fill) for one DENSE sport (mlb/wnba)."""
    per_horizon: Dict[int, List[bool]] = {h: [] for h in HORIZONS_S}
    adverse_moves: List[float] = []
    for trs in _group_by_ticker_sorted(rows).values():
        snaps = [(_epoch(r["ts"]), r.get("best_bid"), r.get("best_ask")) for r in trs]
        snaps = [s for s in snaps if s[0] is not None]
        for i in range(len(snaps) - 1):
            _t0, join_price, _ = snaps[i]
            if join_price is None:
                continue
            for h in HORIZONS_S:
                per_horizon[h].append(detect_quote_cross(snaps, i, h) is not None)
            cross_t = detect_quote_cross(snaps, i, 300)
            if cross_t is not None:
                mid5 = mid_at_or_after(snaps, cross_t + 300.0)
                if mid5 is not None:
                    adverse_moves.append(mid5 - join_price)
    return {
        "quote_cross_proxy": {"%ds" % h: {"n_joins": len(v),
                              "pct_crossed": round(100.0 * sum(v) / len(v), 2) if v else None}
                              for h, v in per_horizon.items()},
        "adverse_timing_5min_post_fill_price_move": _stats(adverse_moves),
    }

def _cadence_median_s(rows: List[Dict[str, Any]]) -> Optional[float]:
    gaps: List[float] = []
    for trs in _group_by_ticker_sorted(rows).values():
        ts = sorted(t for t in (_epoch(r["ts"]) for r in trs) if t is not None)
        gaps.extend(b - a for a, b in zip(ts, ts[1:]))
    return round(statistics.median(gaps), 1) if gaps else None

def run_replay() -> Dict[str, Any]:
    """Full report across every question, honest per-sport coverage/gap notes."""
    ladder_rows = {s: load_ladder_rows(s) for s in LADDER_SPORTS}
    dense_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in load_dense_rows():
        if r.get("sport") in DENSE_SPORTS:
            dense_rows[r["sport"]].append(r)
    coverage = {s: {"n_rows": len(rs), "n_tickers": len({r.get("ticker") for r in rs}),
                    "cadence_median_s": _cadence_median_s(rs)}
                for s, rs in ladder_rows.items()}
    for s, rs in dense_rows.items():
        coverage[s]["dense_n_rows"] = len(rs)
        coverage[s]["dense_cadence_median_s"] = _cadence_median_s(rs)
    q2q4 = {s: build_maker_fill_and_adverse(dense_rows.get(s, [])) for s in DENSE_SPORTS}
    insufficient = [s for s in LADDER_SPORTS if s not in DENSE_SPORTS]
    profile, taker = build_profile_and_taker_cost(ladder_rows)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "edge_claimed": False,
        "honesty_notes": [
            "No per-trade PRICE tape exists in either archive (checked, zero hits for a trade-price field) -- Q2/Q4's literal 'tape prints at price' test is INSUFFICIENT_DATA for every sport; quote_cross_proxy below is a weaker necessary-condition substitute (ask crosses <= join price), queue position unknown.",
            "phase_proxy buckets are capture-order terciles within a ticker's own snapshot sequence, NOT a true inning/quarter/period game clock -- this archive has none.",
            "Q2/Q4 quote_cross_proxy computed only for mlb/wnba (book_depth/kalshi, ~40s median cadence). kbo/npb/soccer_intl/tennis only have depth_history (~26min median cadence, see coverage.cadence_median_s) -- coarser than the 1/5/15-min horizons required, so those sports are INSUFFICIENT_DATA for Q2/Q4.",
            "thin3 in soccer_intl/tennis is often 100k+ (vs low-thousands for mlb/wnba near game time) -- observed, not filtered: likely reflects Kalshi's own automated market-maker resting AT the market price on lower-volume/futures markets rather than genuine trader-provided size; do not read large thinness there as absorbable taker liquidity without further filtering.",
        ],
        "coverage": coverage,
        "q1_spread_depth_profile": profile,
        "q2_maker_fill_plausibility": {
            "quote_cross_proxy_by_sport": {s: q2q4[s]["quote_cross_proxy"] for s in DENSE_SPORTS},
            "insufficient_data_sports": insufficient,
        },
        "q3_taker_cost": taker,
        "q4_adverse_timing": {**{s: q2q4[s]["adverse_timing_5min_post_fill_price_move"]
                                 for s in DENSE_SPORTS}, "insufficient_data_sports": insufficient},
    }

def _md_summary(r: Dict[str, Any]) -> str:
    ln = ["# Kalshi execution profile (maker/taker measurement, no $/edge claim)", "",
          "Generated: %s" % r["generated_at"], "", "## Honesty notes"]
    ln += ["- %s" % n for n in r["honesty_notes"]]
    ln += ["", "## Coverage", "| sport | n_rows | n_tickers | cadence_median_s | dense_cadence_median_s |",
           "|---|---|---|---|---|"]
    ln += ["| %s | %d | %d | %s | %s |" % (s, c["n_rows"], c["n_tickers"], c.get("cadence_median_s"),
           c.get("dense_cadence_median_s")) for s, c in sorted(r["coverage"].items())]
    ln += ["", "## Q1 spread/depth (median full spread, price units; phase = capture-order proxy)"]
    ln += ["- %s/%s: n=%d spread_median=%s thin_median=%s" % (
           s, ph, d["spread_price"].get("n", 0), d["spread_price"].get("median"), d["thinness"].get("median"))
           for s, phases in sorted(r["q1_spread_depth_profile"].items()) for ph, d in phases.items()]
    ln += ["", "## Q2 maker-fill quote-cross proxy (mlb/wnba only; % of joins where ask crossed the join price)"]
    ln += ["- %s @ %s: n=%d pct_crossed=%s" % (s, h, d["n_joins"], d["pct_crossed"])
           for s, hz in sorted(r["q2_maker_fill_plausibility"]["quote_cross_proxy_by_sport"].items())
           for h, d in hz.items()]
    ln.append("- INSUFFICIENT_DATA sports: %s" % ", ".join(
        r["q2_maker_fill_plausibility"]["insufficient_data_sports"]))
    ln += ["", "## Q4 adverse timing (mid 5min after proxy-fill minus join price, price units)"]
    ln += ["- %s: n=%d median=%s p25=%s p75=%s" % (
           s, r["q4_adverse_timing"].get(s, {}).get("n", 0), r["q4_adverse_timing"].get(s, {}).get("median"),
           r["q4_adverse_timing"].get(s, {}).get("p25"), r["q4_adverse_timing"].get(s, {}).get("p75"))
           for s in DENSE_SPORTS]
    return "\n".join(ln) + "\n"

def main() -> int:
    report = run_replay()
    out_json = _REPO / "data" / "frontend" / "ops" / "kalshi_execution_profile.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    out_md = _REPO / "docs" / "research" / "kalshi_execution_profile_2026-07-09.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_md_summary(report), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "coverage": report["coverage"]},
                      ensure_ascii=True, indent=2))
    return 0

__all__ = ["load_jsonl", "ladder_best", "half_spread", "phase_bucket", "quantile_breakpoints",
           "thinness_tercile", "detect_quote_cross", "mid_at_or_after", "load_dense_rows",
           "load_ladder_rows", "build_profile_and_taker_cost", "build_maker_fill_and_adverse", "run_replay"]

if __name__ == "__main__":
    raise SystemExit(main())
