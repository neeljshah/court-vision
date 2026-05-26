"""
build_clv_backtest.py — CLV backtester.

Joins our model's historical predictions (data/models/prop_residuals.json +
data/models/bet_log.json) with scraped closing lines to compute:

  - Edge: model_prob - implied_close_prob (after devig)
  - CLV:  open_line_price - close_line_price, in cents  (positive = line moved our way)
  - ROI:  realized P&L if bet at open

Aggregates by stat and edge bucket. Writes to:
    data/models/clv_backtest_summary.json

Usage:
    python scripts/build_clv_backtest.py
    python scripts/build_clv_backtest.py --lines-dir data/cache/closing_lines
    python scripts/build_clv_backtest.py --verbose
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.devig import american_to_prob, shin_devig

_MODELS_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_RESIDUALS   = os.path.join(_MODELS_DIR, "prop_residuals.json")
_BET_LOG     = os.path.join(_MODELS_DIR, "bet_log.json")
_LINES_DIR   = os.path.join(PROJECT_DIR, "data", "cache", "closing_lines")
_PROPS_DIR   = os.path.join(PROJECT_DIR, "data", "cache", "closing_lines_props")
_OUTPUT      = os.path.join(_MODELS_DIR, "clv_backtest_summary.json")

log = logging.getLogger(__name__)


# ── Devig helpers ──────────────────────────────────────────────────────────────

def _devig_ml_pair(ml_home: Optional[int], ml_away: Optional[int]) -> tuple[float, float]:
    """Return (fair_home_prob, fair_away_prob) using Shin devig."""
    if ml_home is None or ml_away is None:
        return 0.5, 0.5
    raw_h = american_to_prob(ml_home)
    raw_a = american_to_prob(ml_away)
    return tuple(shin_devig([raw_h, raw_a]))  # type: ignore[return-value]


def _devig_total(close_total: float, close_ml_over: Optional[int],
                 close_ml_under: Optional[int]) -> tuple[float, float]:
    """Return (fair_over_prob, fair_under_prob) for a total line."""
    if close_ml_over is None or close_ml_under is None:
        return 0.5, 0.5
    raw_o = american_to_prob(close_ml_over)
    raw_u = american_to_prob(close_ml_under)
    return tuple(shin_devig([raw_o, raw_u]))  # type: ignore[return-value]


def _implied_prob_from_spread(spread_home: Optional[float]) -> float:
    """Rough implied home-win prob from point spread (Pythagorean approx)."""
    if spread_home is None:
        return 0.5
    # ~3 points ≈ 10% win-prob shift
    return max(0.05, min(0.95, 0.5 - spread_home * (1 / 30.0)))


def _american_to_decimal(odds: Optional[int]) -> Optional[float]:
    if odds is None:
        return None
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


# ── CLV in cents ─────────────────────────────────────────────────────────────

def _clv_cents(open_odds: Optional[int], close_odds: Optional[int],
               direction: str = "over") -> Optional[float]:
    """CLV = how many cents better is open vs close for our bet direction.

    Positive CLV = line moved in our favour (we got a better number than close).
    Negative CLV = line moved against us.

    Computed in decimal-odds space, converted to cents:
        CLV_cents = (open_decimal - close_decimal) * 100
    For 'under' bets, invert: a line dropping (open 224 → close 221) is good
    for under bettors.
    """
    open_d = _american_to_decimal(open_odds)
    close_d = _american_to_decimal(close_odds)
    if open_d is None or close_d is None:
        return None
    diff = (open_d - close_d) * 100.0
    return diff if direction != "under" else -diff


# ── Load data sources ─────────────────────────────────────────────────────────

def _load_residuals() -> list:
    if not os.path.exists(_RESIDUALS):
        log.warning("prop_residuals.json not found: %s", _RESIDUALS)
        return []
    with open(_RESIDUALS) as f:
        return json.load(f)


def _load_bet_log() -> list:
    if not os.path.exists(_BET_LOG):
        log.warning("bet_log.json not found: %s", _BET_LOG)
        return []
    with open(_BET_LOG) as f:
        return json.load(f)


def _load_all_lines(lines_dir: str) -> dict:
    """Load all cached game line files. Returns {date_str: [records]}."""
    result: dict = {}
    pattern = os.path.join(lines_dir, "*.json")
    for path in glob.glob(pattern):
        date_str = os.path.basename(path).replace(".json", "")
        try:
            with open(path) as f:
                data = json.load(f)
            result[date_str] = data.get("lines", [])
        except Exception as exc:
            log.debug("skip %s: %s", path, exc)
    return result


def _load_all_props(props_dir: str) -> dict:
    """Load all cached prop line files. Returns {date_str: [records]}."""
    result: dict = {}
    pattern = os.path.join(props_dir, "*.json")
    for path in glob.glob(pattern):
        date_str = os.path.basename(path).replace(".json", "")
        try:
            with open(path) as f:
                data = json.load(f)
            result[date_str] = data.get("lines", [])
        except Exception as exc:
            log.debug("skip %s: %s", path, exc)
    return result


# ── Matching helpers ──────────────────────────────────────────────────────────

def _normalize_date(raw: str) -> str:
    """Convert 'Nov 02, 2024' or '2024-11-02' to 'YYYY-MM-DD'."""
    raw = raw.strip()
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw[:10]  # best-effort


def _find_prop_line(player: str, stat: str, date_str: str,
                    props_by_date: dict) -> Optional[dict]:
    """Find the closest matching prop line for a player/stat/date."""
    lines = props_by_date.get(date_str, [])
    player_l = player.lower().strip()
    for rec in lines:
        if rec.get("stat", "") == stat and rec.get("player", "").lower().strip() == player_l:
            return rec
    # Fuzzy: last name match
    last = player_l.split()[-1] if player_l else ""
    for rec in lines:
        if rec.get("stat", "") == stat and last in rec.get("player", "").lower():
            return rec
    return None


def _find_game_line(home: str, away: str, date_str: str,
                    lines_by_date: dict) -> Optional[dict]:
    for rec in lines_by_date.get(date_str, []):
        if rec.get("home", "").upper() == home.upper() and rec.get("away", "").upper() == away.upper():
            return rec
    return None


# ── Edge-bucket helper ────────────────────────────────────────────────────────

def _edge_bucket(edge_pct: float) -> str:
    abs_e = abs(edge_pct)
    if abs_e < 0.02:
        return "0-2pct"
    if abs_e < 0.05:
        return "2-5pct"
    if abs_e < 0.10:
        return "5-10pct"
    return "10pct+"


# ── ROI calculation ───────────────────────────────────────────────────────────

def _roi_at_open(predicted: float, actual: float, line: float,
                 direction: str, odds: int = -110) -> float:
    """Return P&L in units (stake=1) if bet at 'odds' with 'direction'."""
    hit = (actual > line) if direction == "over" else (actual < line)
    if actual == line:
        return 0.0  # push
    dec = _american_to_decimal(odds) or 1.909
    return (dec - 1.0) if hit else -1.0


# ── Main backtester ───────────────────────────────────────────────────────────

def run_backtest(lines_dir: str = _LINES_DIR, props_dir: str = _PROPS_DIR,
                 output_path: str = _OUTPUT) -> dict:
    residuals = _load_residuals()
    bet_log   = _load_bet_log()
    lines_by_date = _load_all_lines(lines_dir)
    props_by_date = _load_all_props(props_dir)

    all_dates = sorted(set(list(lines_by_date.keys()) + list(props_by_date.keys())))
    log.info("Loaded: %d residuals, %d bet_log entries, %d line-dates, %d prop-dates",
             len(residuals), len(bet_log), len(lines_by_date), len(props_by_date))

    entries = []

    # ── Process prop residuals ───────────────────────────────────────────────
    for r in residuals:
        date_str = _normalize_date(r.get("game_date", ""))
        stat     = r.get("stat", "")
        player   = r.get("player_name", "")
        predicted = float(r.get("predicted", 0))
        actual    = float(r.get("actual", 0)) if r.get("actual") is not None else None
        line      = float(r.get("line", 0)) if r.get("line") is not None else None
        edge_pct  = float(r.get("edge_pct", 0))
        direction = r.get("direction", "over")

        if line is None or actual is None:
            continue

        prop_rec = _find_prop_line(player, stat, date_str, props_by_date)
        close_line = prop_rec["line"] if prop_rec else None
        # Use prop open as 'open line' if available; else use residual line
        open_line = prop_rec.get("line", line) if prop_rec is not None else line

        # For prop CLV: did the line move toward our pick?
        clv_cents: Optional[float] = None
        if close_line is not None and line is not None:
            # Positive CLV for 'over': open_line < close_line (line rose; we got under the rise)
            # Positive CLV for 'under': open_line > close_line (line fell; we got over the drop)
            diff = close_line - open_line
            clv_cents = diff if direction == "over" else -diff

        model_prob = 0.5 + edge_pct / 2.0  # rough conversion from edge_pct
        implied_close = 0.5  # default — no close price available for props

        roi = _roi_at_open(predicted, actual, line, direction) if actual is not None else None

        entries.append({
            "type": "prop",
            "stat": stat,
            "player": player,
            "date": date_str,
            "direction": direction,
            "edge_pct": edge_pct,
            "model_prob": model_prob,
            "implied_close_prob": implied_close,
            "clv_cents": clv_cents,
            "clv_positive": (clv_cents > 0) if clv_cents is not None else None,
            "roi": roi,
        })

    # ── Process bet_log (game-level bets) ────────────────────────────────────
    for b in bet_log:
        date_str  = _normalize_date(b.get("date", ""))
        stat      = b.get("stat", "total")
        direction = b.get("direction", "over")
        edge_pct  = float(b.get("edge", 0)) / 100.0  # edge is stored in pts, rough convert
        odds      = int(b.get("odds", -110))
        projection = float(b.get("projection", 0))
        book_line  = float(b.get("book_line", 0))
        home_team  = b.get("team", "")
        away_team  = b.get("opp_team", "")

        game_rec = _find_game_line(home_team, away_team, date_str, lines_by_date)
        open_ml_h  = game_rec.get("open_ml_home") if game_rec else None
        close_ml_h = game_rec.get("close_ml_home") if game_rec else None
        open_ml_a  = game_rec.get("open_ml_away") if game_rec else None
        close_ml_a = game_rec.get("close_ml_away") if game_rec else None

        # Model prob from edge
        model_prob = american_to_prob(odds) + edge_pct

        # Implied close prob (devigged)
        if close_ml_h is not None and close_ml_a is not None:
            fair_h, fair_a = _devig_ml_pair(close_ml_h, close_ml_a)
            implied_close = fair_h if stat in ("spread", "ml_home") else fair_a
        else:
            implied_close = american_to_prob(odds)

        overall_edge = model_prob - implied_close

        # CLV in cents (open vs close)
        pick_open_odds  = open_ml_h if stat == "ml_home" else open_ml_a
        pick_close_odds = close_ml_h if stat == "ml_home" else close_ml_a
        clv_cents = _clv_cents(pick_open_odds, pick_close_odds, direction)

        entries.append({
            "type": "game",
            "stat": stat,
            "player": b.get("player", ""),
            "date": date_str,
            "direction": direction,
            "edge_pct": overall_edge,
            "model_prob": model_prob,
            "implied_close_prob": implied_close,
            "clv_cents": clv_cents,
            "clv_positive": (clv_cents > 0) if clv_cents is not None else None,
            "roi": None,  # no settled outcomes in bet_log
        })

    # ── Aggregate ─────────────────────────────────────────────────────────────
    n_total = len(entries)
    n_with_clv = sum(1 for e in entries if e["clv_cents"] is not None)
    n_clv_pos  = sum(1 for e in entries if e.get("clv_positive") is True)
    clv_vals   = [e["clv_cents"] for e in entries if e["clv_cents"] is not None]
    roi_vals   = [e["roi"] for e in entries if e["roi"] is not None]

    clv_mean  = (sum(clv_vals) / len(clv_vals)) if clv_vals else None
    clv_beat  = (n_clv_pos / n_with_clv) if n_with_clv > 0 else None
    roi_mean  = (sum(roi_vals) / len(roi_vals)) if roi_vals else None
    win_pct   = (sum(1 for r in roi_vals if r > 0) / len(roi_vals)) if roi_vals else None

    # By stat
    by_stat: dict = defaultdict(lambda: {
        "n": 0, "clv_mean": None, "clv_beat_rate": None, "roi": None, "_clvs": [], "_rois": []
    })
    for e in entries:
        s = e["stat"]
        by_stat[s]["n"] += 1
        if e["clv_cents"] is not None:
            by_stat[s]["_clvs"].append(e["clv_cents"])
        if e["roi"] is not None:
            by_stat[s]["_rois"].append(e["roi"])

    for s, d in by_stat.items():
        clvs = d.pop("_clvs")
        rois = d.pop("_rois")
        d["clv_mean"]      = round(sum(clvs) / len(clvs), 4) if clvs else None
        d["clv_beat_rate"] = round(sum(1 for c in clvs if c > 0) / len(clvs), 4) if clvs else None
        d["roi"]           = round(sum(rois) / len(rois), 4) if rois else None
        d["n_with_clv"]    = len(clvs)

    # By edge bucket
    by_bucket: dict = defaultdict(lambda: {"n": 0, "_clvs": [], "_rois": []})
    for e in entries:
        bk = _edge_bucket(e["edge_pct"])
        by_bucket[bk]["n"] += 1
        if e["clv_cents"] is not None:
            by_bucket[bk]["_clvs"].append(e["clv_cents"])
        if e["roi"] is not None:
            by_bucket[bk]["_rois"].append(e["roi"])

    for bk, d in by_bucket.items():
        clvs = d.pop("_clvs")
        rois = d.pop("_rois")
        d["clv_mean"]      = round(sum(clvs) / len(clvs), 4) if clvs else None
        d["clv_beat_rate"] = round(sum(1 for c in clvs if c > 0) / len(clvs), 4) if clvs else None
        d["roi"]           = round(sum(rois) / len(rois), 4) if rois else None
        d["n_with_clv"]    = len(clvs)

    period_str = f"{min(e['date'] for e in entries) if entries else 'N/A'}..{max(e['date'] for e in entries) if entries else 'N/A'}"

    summary = {
        "generated_at":    datetime.utcnow().isoformat() + "Z",
        "period":          period_str,
        "n_bets":          n_total,
        "n_with_clv":      n_with_clv,
        "clv_mean_cents":  round(clv_mean, 4) if clv_mean is not None else None,
        "clv_beat_rate":   round(clv_beat, 4) if clv_beat is not None else None,
        "roi_at_open":     round(roi_mean, 4) if roi_mean is not None else None,
        "win_pct":         round(win_pct, 4) if win_pct is not None else None,
        "coverage_note":   (
            "CLV requires scraped closing lines stored in data/cache/closing_lines/. "
            "Run refresh_closing_lines.py daily to accumulate history. "
            f"Currently {n_with_clv}/{n_total} bets have scraped line data."
        ),
        "by_stat":         dict(by_stat),
        "by_edge_bucket":  dict(by_bucket),
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)

    log.info("CLV backtest written to %s", output_path)
    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="CLV backtester")
    ap.add_argument("--lines-dir", default=_LINES_DIR, help="Directory of cached game lines")
    ap.add_argument("--props-dir", default=_PROPS_DIR, help="Directory of cached prop lines")
    ap.add_argument("--output",    default=_OUTPUT,    help="Output JSON path")
    ap.add_argument("--verbose",   action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    result = run_backtest(args.lines_dir, args.props_dir, args.output)

    print("\n=== CLV Backtest Summary ===")
    print(f"  Period:        {result['period']}")
    print(f"  N bets:        {result['n_bets']}")
    print(f"  N with CLV:    {result['n_with_clv']}")
    print(f"  CLV mean:      {result['clv_mean_cents']} cents")
    print(f"  CLV beat rate: {result['clv_beat_rate']}")
    print(f"  ROI at open:   {result['roi_at_open']}")
    print(f"  Win %:         {result['win_pct']}")
    print(f"\n  {result['coverage_note']}")
    print(f"\n  Output: {args.output}")
