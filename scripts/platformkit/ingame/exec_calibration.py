"""scripts.platformkit.ingame.exec_calibration -- execution-calibration MEASUREMENT for
the Kalshi PAPER in-play chain.

WHY: paper CLV assumes perfect fills at the recorded price. MEASURES (never tunes on
outcomes) how far that is from reality: spread cost at gate time, quote staleness by
placement, whether the market moved against us after fill (adverse selection), and
whether the model/market gap at bet time was signal or a stale/thin quote artifact.

INPUTS: ledger=data/frontend/clv_ledger.jsonl (channel=="paper_ingame" rows are in-play
paper bets; other channels still feed spread/staleness/divergence if fields present).
grade_dir=data/cache/ingame_grade/<sport>/<game_id>.jsonl (ts, market_prob home-side,
model_prob, side; used for the adverse-selection post-fill lookup).

HONESTY: UNITS/PROBABILITY only, edge_claimed always False. declared_thresholds are
DECLARED FROM MEASUREMENT (label "declared_from_measurement_2026_07_19"), never fit
against outcomes. <=300 LOC; ASCII only; no network at import; never writes
data/registry/; never flips a flag; never edits any other file.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_exec_calibration.py -q
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LEDGER = _REPO_ROOT / "data" / "frontend" / "clv_ledger.jsonl"
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_OUT = _REPO_ROOT / "data" / "cache" / "benchmarks" / "exec_calibration.json"

MIN_N_FOR_THRESHOLDS = 10
MAX_DIVERGENCE_CAP = 0.15
POST_FILL_LAG_SEC = 5 * 60

def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a jsonl file into a list of dict rows. Never raises; bad/missing -> []."""
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out

def _pctile(vals: List[float], q: float) -> Optional[float]:
    """Nearest-rank percentile; None on empty input."""
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]

def _dist(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {"median": None, "p90": None, "max": None, "n": 0}
    return {
        "median": statistics.median(vals),
        "p90": _pctile(vals, 0.90),
        "max": max(vals),
        "n": len(vals),
    }

def _fill_prob(row: Dict[str, Any]) -> Optional[float]:
    dec = row.get("taken_decimal")
    if not dec:
        return None
    try:
        return 1.0 / float(dec)
    except (TypeError, ValueError, ZeroDivisionError):
        return None

def spread_cost(ledger_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Distribution of exec_gate.spread_bp across rows that carry it; null-safe skip."""
    vals = []
    for r in ledger_rows:
        gate = r.get("exec_gate")
        if isinstance(gate, dict) and gate.get("spread_bp") is not None:
            try:
                vals.append(float(gate["spread_bp"]))
            except (TypeError, ValueError):
                continue
    return _dist(vals)

def quote_staleness(ledger_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Distribution of placement_latency_ms across rows that carry it."""
    vals = []
    for r in ledger_rows:
        v = r.get("placement_latency_ms")
        if v is not None:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
    return _dist(vals)

def _post_fill_market_prob(grade_rows: List[Dict[str, Any]], bet_ts: str) -> Optional[float]:
    """market_prob (home side) at the first tick >= 5 min after bet_ts; None if none."""
    def _parse(ts: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    bet_dt = _parse(bet_ts)
    if bet_dt is None:
        return None
    best = None
    best_dt = None
    for r in grade_rows:
        if r.get("market_prob") is None:
            continue
        row_dt = _parse(r.get("ts", ""))
        if row_dt is None:
            continue
        delta = (row_dt - bet_dt).total_seconds()
        if delta < POST_FILL_LAG_SEC:
            continue
        if best_dt is None or row_dt < best_dt:
            best_dt = row_dt
            try:
                best = float(r["market_prob"])
            except (TypeError, ValueError):
                best = None
    return best

def adverse_selection(ledger_rows: List[Dict[str, Any]], grade_dir: Path) -> Dict[str, Any]:
    """Per-sport mean/median/n of signed adverse_move for channel=='paper_ingame' bets.

    adverse_move = post_prob - fill_prob; NEGATIVE = market moved against our side
    after fill. side=='away' flips both probs to the away frame (1 - p) first.
    """
    per_sport: Dict[str, List[float]] = {}
    grade_cache: Dict[str, List[Dict[str, Any]]] = {}
    for r in ledger_rows:
        if r.get("channel") != "paper_ingame":
            continue
        sport = r.get("sport")
        gid = r.get("game_id")
        if not sport or not gid:
            continue
        fill_p = _fill_prob(r)
        if fill_p is None:
            continue
        key = "%s/%s" % (sport, gid)
        if key not in grade_cache:
            grade_cache[key] = _read_jsonl(grade_dir / str(sport) / ("%s.jsonl" % gid))
        grows = grade_cache[key]
        if not grows:
            continue
        post_p = _post_fill_market_prob(grows, r.get("ts", ""))
        if post_p is None:
            continue
        side = r.get("side")
        if side == "away":
            fill_p = 1.0 - fill_p
            post_p = 1.0 - post_p
        elif side != "home":
            continue
        per_sport.setdefault(sport, []).append(post_p - fill_p)

    out: Dict[str, Any] = {}
    for sport, vals in per_sport.items():
        out[sport] = {
            "mean": statistics.mean(vals),
            "median": statistics.median(vals),
            "n": len(vals),
        }
    return out

def divergence_and_warnings(ledger_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """|model_prob - market_prob| distribution at bet time + warnings for |div| > 0.15.

    market_prob at bet time = fill price (1/taken_decimal), the same fair-price proxy
    exec_gate.fair_prob already uses; the ledger has no separate market_prob field.
    BASIS NOTE: this is VIG-INCLUSIVE, whereas ingame_exec_gate's live divergence
    gate uses the DEVIGGED price -- the two "0.15" numbers are related but not on
    the same basis (this one runs slightly hotter by ~half the spread). Same for
    adverse_selection's fill_prob vs the grade file's devigged market_prob: the
    signed mean carries a systematic vig component, disclosed here, not corrected.
    """
    vals: List[float] = []
    warnings: List[Dict[str, Any]] = []
    for r in ledger_rows:
        model_p = r.get("model_prob")
        if model_p is None:
            continue
        market_p = _fill_prob(r)
        if market_p is None:
            continue
        try:
            model_p = float(model_p)
        except (TypeError, ValueError):
            continue
        div = abs(model_p - market_p)
        vals.append(div)
        if div > MAX_DIVERGENCE_CAP:
            warnings.append({
                "bet_id": r.get("bet_id") or r.get("edge_key"),
                "sport": r.get("sport"),
                "game_id": r.get("game_id"),
                "ts": r.get("ts"),
                "model_prob": model_p,
                "market_prob": round(market_p, 6),
                "divergence": round(div, 6),
                "note": "divergence exceeds 0.15 -- likely stale/thin quote, not signal",
            })
    return {"dist": _dist(vals), "flagged_values": vals, "warnings": warnings}

def declared_thresholds(n_bets: int, staleness: Dict[str, Any],
                        divergence_dist: Dict[str, Any], flagged_vals: List[float],
                        warnings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """DECLARED (not fitted-on-outcomes) recommendations from the measured distributions."""
    if n_bets < MIN_N_FOR_THRESHOLDS:
        return {
            "label": "declared_from_measurement_2026_07_19",
            "insufficient_n": True,
            "max_divergence": MAX_DIVERGENCE_CAP,
            "max_staleness_ms": None,
            "min_book_depth": "no depth data in ledger -- cannot declare",
        }
    non_flagged = [v for v in flagged_vals if v <= MAX_DIVERGENCE_CAP]
    p95_nonflagged = _pctile(non_flagged, 0.95)
    max_div = MAX_DIVERGENCE_CAP if p95_nonflagged is None else min(MAX_DIVERGENCE_CAP, p95_nonflagged)
    return {
        "label": "declared_from_measurement_2026_07_19",
        "insufficient_n": False,
        "max_divergence": max_div,
        "max_staleness_ms": staleness.get("p90"),
        "min_book_depth": "no depth data in ledger -- cannot declare",
    }

def compute(ledger: Optional[Path] = None, grade_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Run the full exec-calibration measurement. Never raises."""
    ledger_path = Path(ledger) if ledger is not None else DEFAULT_LEDGER
    grade_dir_path = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    rows = _read_jsonl(ledger_path)
    n_bets = sum(1 for r in rows if r.get("channel") == "paper_ingame")
    spread = spread_cost(rows)
    staleness = quote_staleness(rows)
    adverse = adverse_selection(rows, grade_dir_path)
    div = divergence_and_warnings(rows)
    thresholds = declared_thresholds(n_bets, staleness, div["dist"], div["flagged_values"],
                                     div["warnings"])
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_bets": n_bets,
        "spread_cost": spread,
        "staleness": staleness,
        "adverse_selection": adverse,
        "divergence": div["dist"],
        "warnings": div["warnings"],
        "declared_thresholds": thresholds,
        "honest_note": "measurement only -- units/probability space, never $/ROI; "
                       "declared_thresholds are derived from observed distributions, "
                       "not fit against outcomes",
        "edge_claimed": False,
    }

def write_report(out_path: Optional[Path] = None, ledger: Optional[Path] = None,
                 grade_dir: Optional[Path] = None) -> Dict[str, Any]:
    result = compute(ledger, grade_dir)
    out = Path(out_path) if out_path is not None else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(out)
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi in-play exec-calibration measurement")
    parser.add_argument("--ledger", type=str, default=None)
    parser.add_argument("--grade-dir", type=str, default=None)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()
    result = write_report(
        out_path=Path(args.out) if args.out else None,
        ledger=Path(args.ledger) if args.ledger else None,
        grade_dir=Path(args.grade_dir) if args.grade_dir else None,
    )
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()

__all__ = [
    "DEFAULT_LEDGER", "DEFAULT_GRADE_DIR", "DEFAULT_OUT",
    "spread_cost", "quote_staleness", "adverse_selection",
    "divergence_and_warnings", "declared_thresholds", "compute", "write_report", "main",
]
