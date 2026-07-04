"""scripts.platformkit.venue_history.kalshi_tail_validation -- cross-venue band-stats verdict.

Runs the SAME price-band calibration measurement as ingame_tail_scan (venue price vs
realized outcome, game-clustered bootstrap CI) on the Kalshi HISTORICAL candle corpus
built by kalshi_intragame.py. This is a SEPARATE, independent validation corpus -- never
pooled with lane 1's file or with the forward pre-registered gates (ingame_tail_gate).

DISCOVERY-WINDOW CAVEAT (binding): this backfill window overlaps the LIVE in-play capture
discovery corpus (2026-06-19..07-02, see ingame_tail_gate.py). Any ticker whose close_time
falls in that band is flagged ``in_discovery_window`` by the fetcher. The HONEST INDEPENDENT
subset is games whose close_time is BEFORE 2026-06-19 or AFTER 2026-07-02 -- this module
reports BOTH the pooled (all markets) and the discovery-excluded subset numbers side by side
so the excluded-subset verdict is never silently mixed with the overlapping one.

Each settled market/ticker is one binary side ("does THIS team win"); its outcome is the
market's own ``result`` field (yes=1/no=0), never invented. A market's candles are bucketed
by price band using ``prob`` (falls back to bid/ask mid on tradeless minutes, see fetcher).

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry writes.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_kalshi_tail_validation.py -q
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS_DIR = _REPO_ROOT / "data" / "venue_history" / "kalshi"
DEFAULT_OUT = DEFAULT_CORPUS_DIR / "mlb_tail_validation.json"

BAND_EDGES: List[float] = [0.0, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90, 1.0]
MIN_GAMES_BAND = 8
BOOTSTRAP_ITERS = 2000
SEED = 13

Row = Tuple[str, float, int]  # (ticker, prob, outcome)


def _band_label(p: float) -> str:
    for lo, hi in zip(BAND_EDGES, BAND_EDGES[1:]):
        if lo <= p < hi or (hi == 1.0 and p == 1.0):
            close = "]" if hi == 1.0 else ")"
            return "[%.2f,%.2f%s" % (lo, hi, close)
    return "UNK"


def _band_stats(rows: List[Row], iters: int = BOOTSTRAP_ITERS, seed: int = SEED) -> Dict[str, Any]:
    """rows = [(ticker, venue_prob, outcome)] for ONE band. Venue-only (no model
    column -- this is a historical validation corpus, not a live grade file).

    Bootstrap resamples MARKETS (not raw ticks): each market is pre-aggregated to
    one (sum_prob, sum_outcome, n) tuple once, so a resample iteration costs
    O(n_markets), not O(n_ticks) -- this corpus can carry millions of candles per
    band and a per-tick resample would be prohibitively slow in pure Python."""
    tickers = sorted({r[0] for r in rows})
    n_g, n_t = len(tickers), len(rows)
    mean_p = sum(r[1] for r in rows) / n_t
    realized = sum(r[2] for r in rows) / n_t
    brier = sum((r[1] - r[2]) ** 2 for r in rows) / n_t
    out: Dict[str, Any] = {
        "n_ticks": n_t, "n_markets": n_g,
        "mean_venue_price": round(mean_p, 4), "realized_rate": round(realized, 4),
        "venue_gap": round(realized - mean_p, 4), "brier_venue": round(brier, 5),
    }
    if n_g < MIN_GAMES_BAND:
        out.update(venue_verdict="INSUFFICIENT_DATA", venue_gap_ci95=None)
        return out
    agg: Dict[str, Tuple[float, float, int]] = {}
    for tkr, prob, outcome in rows:
        sp, so, n = agg.get(tkr, (0.0, 0.0, 0))
        agg[tkr] = (sp + prob, so + outcome, n + 1)
    per_market = [agg[t] for t in tickers]
    rng = random.Random(seed)
    gaps: List[float] = []
    for _ in range(iters):
        sp_tot = so_tot = 0.0
        n_tot = 0
        for _ in range(n_g):
            sp, so, n = per_market[rng.randrange(n_g)]
            sp_tot += sp
            so_tot += so
            n_tot += n
        gaps.append(so_tot / n_tot - sp_tot / n_tot)
    gaps.sort()
    lo_i, hi_i = int(0.025 * iters), min(int(0.975 * iters), iters - 1)
    ci = (round(gaps[lo_i], 4), round(gaps[hi_i], 4))
    out["venue_gap_ci95"] = list(ci)
    if ci[0] > 0:
        out["venue_verdict"] = "VENUE_UNDERPRICES"
    elif ci[1] < 0:
        out["venue_verdict"] = "VENUE_OVERPRICES"
    else:
        out["venue_verdict"] = "CALIBRATED"
    return out


def _load_market_doc(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            line = fh.readline()
        return json.loads(line) if line.strip() else None
    except Exception:
        return None


def _rows_from_doc(doc: Dict[str, Any]) -> List[Row]:
    result = str(doc.get("result") or "").lower()
    if result not in ("yes", "no"):
        return []  # unresolved / voided market -- never invent an outcome
    outcome = 1 if result == "yes" else 0
    ticker = str(doc.get("ticker") or "")
    rows: List[Row] = []
    for c in doc.get("candles") or []:
        prob = c.get("prob")
        if isinstance(prob, (int, float)) and 0.0 <= prob <= 1.0:
            rows.append((ticker, float(prob), outcome))
    return rows


def run_validation(
    corpus_dir: Optional[Path] = None,
    sport: str = "mlb",
    iters: int = BOOTSTRAP_ITERS,
) -> Dict[str, Any]:
    """Scan every *.jsonl market doc under corpus_dir, band-bucket its candles by
    venue price, and return BOTH the pooled-all verdict and the discovery-window-
    excluded (honest independent) subset verdict, side by side."""
    base = Path(corpus_dir) if corpus_dir is not None else DEFAULT_CORPUS_DIR / sport.lower()
    files = sorted(f for f in base.glob("*.jsonl") if not f.name.startswith("_")) if base.is_dir() else []

    all_rows_by_band: Dict[str, List[Row]] = {}
    excl_rows_by_band: Dict[str, List[Row]] = {}
    n_markets = n_in_window = n_excluded = n_unresolved = 0

    for f in files:
        doc = _load_market_doc(f)
        if doc is None:
            continue
        n_markets += 1
        rows = _rows_from_doc(doc)
        if not rows:
            n_unresolved += 1
            continue
        in_window = bool(doc.get("in_discovery_window"))
        n_in_window += 1 if in_window else 0
        n_excluded += 1 if not in_window else 0
        for tkr, prob, outcome in rows:
            band = _band_label(prob)
            all_rows_by_band.setdefault(band, []).append((tkr, prob, outcome))
            if not in_window:
                excl_rows_by_band.setdefault(band, []).append((tkr, prob, outcome))

    bands_all = {b: _band_stats(rows, iters=iters) for b, rows in sorted(all_rows_by_band.items())}
    bands_excl = {b: _band_stats(rows, iters=iters) for b, rows in sorted(excl_rows_by_band.items())}

    doc_out = {
        "component": "kalshi_tail_validation", "sport": sport,
        "provenance": "kalshi_historical_validation",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("historical Kalshi candle corpus, venue-price-vs-realized-outcome "
                 "calibration by price band; game-clustered bootstrap CI; SEPARATE from "
                 "lane 1's file and from the forward pre-registered ingame_tail_gate; "
                 "never pooled with forward evidence"),
        "discovery_window_caveat": (
            "this backfill overlaps the live in-play capture discovery corpus "
            "(2026-06-19..07-02); the honest independent subset is close_time before "
            "2026-06-19 or after 2026-07-02 -- see 'excluded_discovery_window' below"),
        "n_markets_scanned": n_markets, "n_markets_unresolved": n_unresolved,
        "n_markets_in_discovery_window": n_in_window,
        "n_markets_excluded_independent": n_excluded,
        "min_games_band": MIN_GAMES_BAND,
        "pooled_all": {"bands": bands_all},
        "excluded_discovery_window": {"bands": bands_excl},
        "edge_claimed": False,
    }
    return doc_out


def write_verdict(doc: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    p = Path(out_path) if out_path is not None else DEFAULT_OUT
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    os.replace(str(tmp), str(p))
    return p


def main() -> None:
    doc = run_validation()
    print("kalshi_tail_validation | markets scanned=%d unresolved=%d" %
          (doc["n_markets_scanned"], doc["n_markets_unresolved"]))
    for label, s in doc["excluded_discovery_window"]["bands"].items():
        print("  [excl-window] %-14s n_mkt=%-4d n_tick=%-6d verdict=%s" %
              (label, s["n_markets"], s["n_ticks"], s["venue_verdict"]))
    path = write_verdict(doc)
    print("verdict: %s" % path)
    print("NOTE: calibration measurement only; no edge claimed.")


if __name__ == "__main__":
    main()


__all__ = ["run_validation", "write_verdict", "BAND_EDGES", "MIN_GAMES_BAND"]
