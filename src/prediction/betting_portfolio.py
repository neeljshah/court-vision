"""
betting_portfolio.py — Phase 4.8: Quantitative betting infrastructure.

Handles:
  - Kelly sizing with correlation-aware fractional sizing
  - Cross-book arbitrage detection
  - CLV (closing line value) tracking per bet
  - Portfolio construction: max bets in-flight, drawdown guard

Public API
----------
    kelly_corr(edge, odds, bankroll, corr_matrix)    -> float (bet size $)
    detect_arb(lines_by_book)                        -> list[ArbOpportunity]
    log_bet(bet)                                     -> None
    record_clv(bet_id, closing_line)                 -> None
    get_portfolio_summary()                          -> dict
    get_open_bets()                                  -> list[dict]
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_BET_LOG      = os.path.join(PROJECT_DIR, "data", "models", "bet_log.json")
_CLV_LOG      = os.path.join(PROJECT_DIR, "data", "models", "clv_log.json")
_CORR_MATRIX  = os.path.join(PROJECT_DIR, "data", "models", "prop_corr_matrix.json")

_PROP_STATS_ORDER = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _load_corr_matrix() -> Dict[str, Dict[str, float]]:
    """Load prop correlation matrix from disk. Returns identity (zeros) on miss."""
    if os.path.exists(_CORR_MATRIX):
        try:
            return json.load(open(_CORR_MATRIX, encoding="utf-8"))
        except Exception:
            pass
    return {}

# Portfolio guards
MAX_OPEN_BETS     = 20      # never more than N bets in-flight at once
MAX_DRAWDOWN_PCT  = 0.15    # halt betting when drawdown exceeds 15% of bankroll
KELLY_FRACTION    = 0.25    # full Kelly is too aggressive; use quarter-Kelly
MAX_BET_PCT       = 0.04    # cap any single bet at 4% of bankroll


@dataclass
class Bet:
    """A single prop or game bet."""
    bet_id:        str
    player_id:     str
    player_name:   str
    stat:          str            # 'pts', 'reb', 'game_total', etc.
    direction:     str            # 'over' or 'under'
    line:          float
    pred:          float
    book:          str
    odds:          int            # American odds, e.g. -110
    edge_pct:      float          # (pred - line) / line
    kelly_size:    float          # recommended bet in dollars
    placed_at:     float = field(default_factory=time.time)
    closing_line:  Optional[float] = None
    clv:           Optional[float] = None   # closing line value
    result:        Optional[str]  = None    # 'win', 'loss', 'push', None=open
    pnl:           Optional[float] = None


def _american_to_prob(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def _american_to_payout(odds: int) -> float:
    """Return net payout per $1 wagered."""
    if odds > 0:
        return odds / 100.0
    if odds == 0:
        return 0.0
    return 100.0 / abs(odds)


def check_drawdown_ok(bankroll_start: float, bankroll_now: float) -> bool:
    """Return False when drawdown from start exceeds MAX_DRAWDOWN_PCT (15%)."""
    if bankroll_start <= 0:
        return True
    drawdown = (bankroll_start - bankroll_now) / bankroll_start
    return drawdown <= MAX_DRAWDOWN_PCT


def kelly_corr(
    edge: float,
    odds: int,
    bankroll: float,
    corr_with_open: float = 0.0,
    existing_exposure: float = 0.0,
    stat: Optional[str] = None,
    open_stats: Optional[List[str]] = None,
    bankroll_start: Optional[float] = None,
    win_prob_override: Optional[float] = None,
) -> float:
    """
    Kelly criterion with correlation adjustment and bankroll guards.

    Full Kelly = (bp - q) / b  where b=payout, p=win_prob, q=1-p.
    Scales by KELLY_FRACTION (quarter-Kelly), then reduces for correlated
    exposure already in the portfolio.

    If *stat* and *open_stats* are provided, loads the persisted prop
    correlation matrix to compute average correlation automatically.
    *corr_with_open* is ignored when stat-based lookup succeeds.

    Args:
        edge:               Model edge as fraction (e.g. 0.06 = 6%).
        odds:               American odds on this bet.
        bankroll:           Current bankroll in dollars.
        corr_with_open:     Fallback average correlation (0-1) if matrix absent.
        existing_exposure:  Total $ already at risk on correlated bets.
        stat:               Stat key for this bet (e.g. "pts").
        open_stats:         List of stat keys for currently open bets.
        win_prob_override:  Calibrated P(win) from isotonic regression.  When
                            provided, replaces the implied_prob + edge heuristic.
                            Obtain via CalibrationLayer.win_prob() or
                            PropStackResult.calibrated_win_probs[stat].

    Returns:
        Recommended bet size in dollars (0 if Kelly is negative).
    """
    # Drawdown guard: halt betting when loss exceeds MAX_DRAWDOWN_PCT
    if bankroll_start is not None and not check_drawdown_ok(bankroll_start, bankroll):
        return 0.0

    # Resolve correlation from matrix if stat info provided
    if stat and open_stats:
        matrix = _load_corr_matrix()
        if matrix:
            stat_row = matrix.get(stat, {})
            corrs = [abs(float(stat_row.get(s, 0.0))) for s in open_stats if s != stat]
            if corrs:
                corr_with_open = float(np.mean(corrs))
    implied_prob = _american_to_prob(odds)
    # Use calibrated win probability when available; raw heuristic otherwise
    if win_prob_override is not None:
        win_prob = max(0.05, min(0.95, float(win_prob_override)))
    else:
        win_prob = min(0.95, implied_prob + edge)
    b = _american_to_payout(odds)
    q = 1.0 - win_prob

    full_kelly = (win_prob * b - q) / b
    if full_kelly <= 0:
        return 0.0

    # Quarter-Kelly
    f = full_kelly * KELLY_FRACTION

    # Correlation reduction: if we already have correlated exposure, shrink bet
    corr_penalty = 1.0 - (corr_with_open * existing_exposure / max(bankroll, 1))
    f = f * max(0.0, corr_penalty)

    # Hard cap
    f = min(f, MAX_BET_PCT)
    return round(f * bankroll, 2)


@dataclass
class ArbOpportunity:
    """A detected cross-book arbitrage."""
    stat:      str
    player:    str
    over_book: str
    over_odds: int
    under_book: str
    under_odds: int
    arb_pct:   float   # guaranteed profit % of total stake


def detect_arb(
    lines_by_book: Dict[str, Dict[str, Tuple[float, int, int]]],
) -> List[ArbOpportunity]:
    """
    Detect arbitrage across books for the same stat/player.

    Args:
        lines_by_book: {book_name: {player_stat_key: (line, over_odds, under_odds)}}
                       player_stat_key example: "LeBron_pts_over"

    Returns:
        List of ArbOpportunity where profit % > 0.
    """
    arbs: List[ArbOpportunity] = []
    # Build lookup: player_stat → {book: (over_odds, under_odds, line)}
    lookup: Dict[str, Dict[str, Tuple]] = {}
    for book, markets in lines_by_book.items():
        for key, (line, over_odds, under_odds) in markets.items():
            if key not in lookup:
                lookup[key] = {}
            lookup[key][book] = (over_odds, under_odds, line)

    for key, book_data in lookup.items():
        if len(book_data) < 2:
            continue
        # Find best over and best under across all books
        best_over  = max(book_data.items(), key=lambda x: x[1][0])  # highest over odds
        best_under = max(book_data.items(), key=lambda x: x[1][1])  # highest under odds
        over_imp  = _american_to_prob(best_over[1][0])
        under_imp = _american_to_prob(best_under[1][1])
        total_imp = over_imp + under_imp
        if total_imp < 1.0:
            arb_pct = round((1.0 / total_imp - 1.0) * 100, 3)
            # Parse player name from key
            parts = key.rsplit("_", 2)
            player = parts[0] if parts else key
            stat   = parts[1] if len(parts) > 1 else "?"
            arbs.append(ArbOpportunity(
                stat=stat,
                player=player,
                over_book=best_over[0],
                over_odds=best_over[1][0],
                under_book=best_under[0],
                under_odds=best_under[1][1],
                arb_pct=arb_pct,
            ))
    return sorted(arbs, key=lambda a: a.arb_pct, reverse=True)


def _load_bet_log() -> List[dict]:
    if not os.path.exists(_BET_LOG):
        return []
    try:
        return json.load(open(_BET_LOG, encoding="utf-8"))
    except Exception:
        return []


def _save_bet_log(bets: List[dict]) -> None:
    os.makedirs(os.path.dirname(_BET_LOG), exist_ok=True)
    json.dump(bets, open(_BET_LOG, "w", encoding="utf-8"), indent=2)


def log_bet(bet: Bet) -> None:
    """Append a new bet to the persistent bet log."""
    bets = _load_bet_log()
    bets.append(asdict(bet))
    _save_bet_log(bets)


def record_clv(bet_id: str, closing_line: float) -> None:
    """
    Record the closing line for a placed bet and compute CLV.

    CLV = (closing_line - opening_line) / opening_line (for overs)
    Positive CLV means we beat the market close.
    """
    bets = _load_bet_log()
    for b in bets:
        if b["bet_id"] == bet_id:
            b["closing_line"] = closing_line
            opening = b.get("line", closing_line)
            if b.get("direction") == "over":
                b["clv"] = round((closing_line - opening) / max(opening, 0.01), 4)
            else:
                b["clv"] = round((opening - closing_line) / max(opening, 0.01), 4)
            break
    _save_bet_log(bets)

    # Also append to CLV log
    clv_log: List[dict] = []
    if os.path.exists(_CLV_LOG):
        try:
            clv_log = json.load(open(_CLV_LOG, encoding="utf-8"))
        except Exception:
            pass
    entry = next((b for b in bets if b["bet_id"] == bet_id), {})
    if entry:
        clv_log.append({
            "bet_id":       bet_id,
            "stat":         entry.get("stat"),
            "player_name":  entry.get("player_name"),
            "direction":    entry.get("direction"),
            "opening_line": entry.get("line"),
            "closing_line": closing_line,
            "clv":          entry.get("clv"),
            "edge_pct":     entry.get("edge_pct"),
            "placed_at":    entry.get("placed_at"),
        })
        json.dump(clv_log, open(_CLV_LOG, "w", encoding="utf-8"), indent=2)


def get_open_bets() -> List[dict]:
    """Return all bets with result=None."""
    return [b for b in _load_bet_log() if b.get("result") is None]


def get_portfolio_summary() -> dict:
    """
    Return a summary of the current betting portfolio.

    Returns:
        {
            "total_bets": int,
            "open_bets": int,
            "wins": int,
            "losses": int,
            "total_pnl": float,
            "roi_pct": float,
            "avg_clv": float,
            "clv_positive_rate": float,
            "total_wagered": float,
        }
    """
    bets = _load_bet_log()
    if not bets:
        return {
            "total_bets": 0, "open_bets": 0, "wins": 0, "losses": 0,
            "total_pnl": 0.0, "roi_pct": 0.0, "avg_clv": 0.0,
            "clv_positive_rate": 0.0, "total_wagered": 0.0,
        }

    open_bets  = sum(1 for b in bets if b.get("result") is None)
    wins       = sum(1 for b in bets if b.get("result") == "win")
    losses     = sum(1 for b in bets if b.get("result") == "loss")
    total_pnl  = sum(b.get("pnl", 0.0) or 0.0 for b in bets)
    wagered    = sum(b.get("kelly_size", 0.0) or 0.0 for b in bets)
    roi        = total_pnl / max(wagered, 1) * 100

    clv_vals   = [b["clv"] for b in bets if b.get("clv") is not None]
    avg_clv    = float(np.mean(clv_vals)) if clv_vals else 0.0
    clv_pos    = sum(1 for c in clv_vals if c > 0) / max(len(clv_vals), 1)

    return {
        "total_bets":       len(bets),
        "open_bets":        open_bets,
        "wins":             wins,
        "losses":           losses,
        "total_pnl":        round(total_pnl, 2),
        "roi_pct":          round(roi, 2),
        "avg_clv":          round(avg_clv, 4),
        "clv_positive_rate": round(clv_pos, 3),
        "total_wagered":    round(wagered, 2),
    }


def compute_prop_corr_matrix(residuals_path: Optional[str] = None) -> Dict[str, Dict[str, float]]:
    """
    Compute pairwise Pearson correlation matrix for prop stats from residuals.

    Reads data/models/prop_residuals.json (rows: {stat, predicted, player_id, game_id}).
    Groups by (player_id, game_id), keeps only rows where all 7 stats are present,
    then computes pairwise Pearson correlations between predicted values.

    Saves result to data/models/prop_corr_matrix.json and returns the matrix.
    Returns empty dict if fewer than 10 complete player-game rows exist.
    """
    if residuals_path is None:
        residuals_path = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
    if not os.path.exists(residuals_path):
        print(f"  [corr] {residuals_path} not found — cannot compute correlation matrix")
        return {}

    try:
        residuals = json.load(open(residuals_path, encoding="utf-8"))
    except Exception as e:
        print(f"  [corr] failed to load residuals: {e}")
        return {}

    # Pivot: (player_id, game_id) → {stat: predicted_value}
    from collections import defaultdict
    rows: Dict[tuple, Dict[str, float]] = defaultdict(dict)
    for r in residuals:
        stat = r.get("stat")
        pred = r.get("predicted")
        pid  = str(r.get("player_id", r.get("player_name", "")))
        gid  = str(r.get("game_id", ""))
        if stat in _PROP_STATS_ORDER and pred is not None and pid:
            rows[(pid, gid)][stat] = float(pred)

    # Keep only rows with all 7 stats present
    complete = [d for d in rows.values() if all(s in d for s in _PROP_STATS_ORDER)]
    if len(complete) < 10:
        print(f"  [corr] only {len(complete)} complete player-game rows — skipping (need ≥10)")
        return {}

    arrays: Dict[str, List[float]] = {s: [d[s] for d in complete] for s in _PROP_STATS_ORDER}

    matrix: Dict[str, Dict[str, float]] = {}
    for s1 in _PROP_STATS_ORDER:
        matrix[s1] = {}
        x = np.array(arrays[s1])
        for s2 in _PROP_STATS_ORDER:
            if s1 == s2:
                matrix[s1][s2] = 1.0
            else:
                y = np.array(arrays[s2])
                if np.std(x) > 0 and np.std(y) > 0:
                    matrix[s1][s2] = round(float(np.corrcoef(x, y)[0, 1]), 4)
                else:
                    matrix[s1][s2] = 0.0

    os.makedirs(os.path.dirname(_CORR_MATRIX), exist_ok=True)
    json.dump(matrix, open(_CORR_MATRIX, "w", encoding="utf-8"), indent=2)
    print(f"  [corr] Saved {len(complete)}-row correlation matrix to {_CORR_MATRIX}")
    return matrix


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Betting portfolio utilities")
    parser.add_argument("--compute-corr", action="store_true",
                        help="Compute prop correlation matrix from residuals and save")
    parser.add_argument("--summary", action="store_true",
                        help="Print portfolio summary")
    args = parser.parse_args()

    if args.compute_corr:
        mat = compute_prop_corr_matrix()
        if mat:
            print("\nCorrelation matrix:")
            header = "     " + "  ".join(f"{s:5s}" for s in _PROP_STATS_ORDER)
            print(header)
            for s1 in _PROP_STATS_ORDER:
                row_str = "  ".join(f"{mat[s1][s2]:5.2f}" for s2 in _PROP_STATS_ORDER)
                print(f"{s1:4s} {row_str}")
    else:
        summary = get_portfolio_summary()
        print("Portfolio Summary:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
