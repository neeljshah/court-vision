"""
betting_portfolio.py — Phase 4.8: Quantitative betting infrastructure.

Handles:
  - Kelly sizing with correlation-aware fractional sizing
  - Iter-33 Kelly-informed edge-proportional sizing (kelly_b_stake)
  - Cross-book arbitrage detection
  - CLV (closing line value) tracking per bet
  - Portfolio construction: max bets in-flight, drawdown guard

Public API
----------
    kelly_corr(edge, odds, bankroll, corr_matrix)    -> float (bet size $)
    kelly_b_stake(edge_abs, stat, bankroll, unit_size) -> float (bet size $)
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

KELLY_PCT_MAX = 0.25


def clamp_kelly_pct(x: Optional[float]) -> Optional[float]:
    """Clamp a Kelly fraction to [0, KELLY_PCT_MAX]. Pass-through for None/NaN."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    if v < 0.0:
        return 0.0
    if v > KELLY_PCT_MAX:
        return KELLY_PCT_MAX
    return v

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


def _infer_bankroll_start_enabled() -> bool:
    """Whether to infer a bankroll_start (and thus activate the drawdown guard)
    when the caller passes None.

    Gated behind env flag CV_INFER_BANKROLL_START (default OFF).  OFF preserves
    the ORIGINAL behavior: a None bankroll_start SKIPS the drawdown guard.
    This is a real-money behavior gate — see kelly_corr() for the rationale.
    """
    return os.environ.get("CV_INFER_BANKROLL_START", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _infer_bankroll_start(bankroll_now: float) -> float:
    """Infer the starting bankroll when a caller omits bankroll_start.

    Derives the pre-betting bankroll from realized PnL in the bet log:
    ``start ≈ current_bankroll - net_realized_pnl``.  This lets the drawdown
    guard fire even when callers never pass an explicit start.  When the bet
    log has no realized PnL (fresh state), falls back to the current bankroll
    (drawdown 0 → guard passes), which is the safe no-op default.
    """
    try:
        net_pnl = sum(
            b.get("pnl", 0.0) or 0.0
            for b in _load_bet_log()
            if b.get("result") in ("win", "loss", "push")
        )
    except Exception:
        net_pnl = 0.0
    start = bankroll_now - net_pnl
    # Guard against degenerate/negative inferred starts.
    if start <= 0:
        return bankroll_now
    return start


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
    # Drawdown guard: halt betting when loss exceeds MAX_DRAWDOWN_PCT.
    #
    # REAL-MONEY GATE (CV_INFER_BANKROLL_START, default OFF):
    #   When the caller omits bankroll_start, the NEW behavior derives a
    #   reference from realized PnL in the bet log (start ≈ current bankroll -
    #   net PnL) so the drawdown guard always evaluates.  This can flip a live
    #   stake from a positive size to 0.0 (halt) — a silent behavior change.
    #   It is therefore OFF by default: with the flag OFF, a None start SKIPS
    #   the guard exactly as the original code did (byte-identical behavior).
    #   Set CV_INFER_BANKROLL_START=1 to opt in to the inferred-start guard.
    if bankroll_start is None and _infer_bankroll_start_enabled():
        bankroll_start = _infer_bankroll_start(bankroll)
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


# ── Iter-33: Kelly-B edge-proportional sizing ─────────────────────────────────
# Ship decision: SHIP (+2.52pp aggregate ROI lift vs flat, 1 regression on pts).
# Calibrated on 1,016 fully-OOS 2025-26 bets (iter-22+25+28 production).
# Per-stat hit-rate calibration points (training estimate):
_KELLY_B_HIT_RATES: Dict[str, float] = {
    "pts": 0.5847, "reb": 0.5982, "ast": 0.6716,
    "fg3m": 0.7183, "stl": 0.6183, "blk": 0.6654, "tov": 0.52,
}
# Per-stat thresholds (iter-25)
_KELLY_B_THRESHOLDS: Dict[str, float] = {
    "pts": 0.7, "reb": 1.5, "ast": 1.0,
    "fg3m": 0.7, "stl": 0.4, "blk": 0.4, "tov": 0.5,
}
_KELLY_B_FRACTION   = 0.25    # quarter-Kelly
_KELLY_B_MAX_U      = 3.0     # max 3u (cap to limit blowup risk)


def kelly_b_stake(
    edge_abs: float,
    stat: str,
    bankroll: float,
    unit_size: Optional[float] = None,
    odds: int = -110,
) -> float:
    """Iter-33 Kelly-informed stake sizing.

    Sizes ALL positive-edge bets proportionally to their edge magnitude.
    Bigger edges get higher p_win estimate -> larger Kelly fraction.
    Smaller edges get lower p_win -> smaller but non-zero fraction.
    No abstain: every bet above threshold gets a stake.

    Args:
        edge_abs:    Absolute edge in stat units (e.g. |pred - line|).
        stat:        Stat key ('pts', 'reb', etc.).
        bankroll:    Current bankroll in dollars.
        unit_size:   1 unit in dollars. Defaults to bankroll * 0.01 (1%).
        odds:        American odds for this bet (default -110).

    Returns:
        Recommended bet size in dollars, capped at 3u.
    """
    thr  = _KELLY_B_THRESHOLDS.get(stat.lower(), 0.5)
    hit  = _KELLY_B_HIT_RATES.get(stat.lower(), 0.52)
    payout_b = _american_to_payout(odds)
    if payout_b <= 0:
        return 0.0

    # Linear edge -> p_win interpolation:
    # at edge = thr:    p_win = hit
    # at edge = thr*3:  p_win = min(0.85, hit + 0.08)
    frac  = min(1.0, max(0.0, (edge_abs - thr) / max(thr * 2.0, 0.01)))
    p_hi  = min(0.85, hit + 0.08)
    p_win = hit + frac * (p_hi - hit)
    p_win = min(0.90, max(0.50, p_win))

    q          = 1.0 - p_win
    full_kelly = (p_win * payout_b - q) / payout_b
    if full_kelly <= 0.0:
        return 0.0

    u = unit_size if unit_size and unit_size > 0 else bankroll * 0.01
    raw_units  = _KELLY_B_FRACTION * full_kelly
    capped_u   = min(raw_units, _KELLY_B_MAX_U)
    return round(capped_u * u, 2)


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
    Record the closing line for a placed bet and compute side-aware CLV.

    Positive CLV = we locked a BETTER number than the close:
      - OVER  bet: a HIGHER closing line is favorable (the market agrees the
                   player will score more, validating our bet), so
                   CLV = (closing - opening) / |opening|.
      - UNDER bet: a LOWER closing line is favorable (the market agrees the
                   player will score less, validating our bet), so
                   CLV = (opening - closing) / |opening|.

    Example: bet OVER 22.5, market closes at 24.5 → we locked in the easier
    number (22.5 vs 24.5) → CLV = (24.5 - 22.5) / 22.5 > 0.

    Matches the convention in scripts/clv_tracker.py::_compute_clv,
    clv_tracker_daemon.py, compute_clv.py (label side), player_props.py,
    and build_clv_training_data labels.
    """
    bets = _load_bet_log()
    for b in bets:
        if b["bet_id"] == bet_id:
            b["closing_line"] = closing_line
            opening = b.get("line", closing_line)
            denom = max(abs(opening), 0.01)
            if b.get("direction") == "over":
                # Over: positive CLV when closing > opening (line moved up,
                # we locked the lower/easier number).
                b["clv"] = round((closing_line - opening) / denom, 4)
            else:
                # Under: positive CLV when closing < opening (line moved down,
                # we locked the higher/easier number).
                b["clv"] = round((opening - closing_line) / denom, 4)
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
    Compute pairwise Pearson correlation matrix for prop stats from RESIDUALS.

    Reads data/models/prop_residuals.json (rows: {stat, predicted, actual,
    player_id, game_id, ...}).  Groups by (player_id, game_id), keeps only
    rows where all 7 stats have both predicted AND actual present, then
    computes pairwise Pearson correlations between (predicted - actual)
    residuals.  Correlating residuals instead of raw predictions avoids
    inflating correlations via shared usage/minutes variance (the v1 bug
    that produced pts-tov=0.80 from raw predicted values).

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

    # Pivot: (player_id, game_id) → {stat: residual_value (predicted - actual)}
    # Correlating residuals avoids the inflated correlations from shared
    # minutes/usage (the v1 bug that produced pts-tov=0.80 from raw predicted).
    from collections import defaultdict
    rows: Dict[tuple, Dict[str, float]] = defaultdict(dict)
    for r in residuals:
        stat   = r.get("stat")
        pred   = r.get("predicted")
        actual = r.get("actual")
        pid    = str(r.get("player_id") or r.get("player_name") or "")
        # Per-game key: prefer a real game_id, but residual rows carry
        # game_id=None and identify the game via game_date — fall back to date
        # so each player-game is a distinct row (the (player_id, date) key the
        # EX-8 v2 rebuild used).  ``or`` (not dict-default) because the key
        # exists with a None value.
        gid    = str(r.get("game_id") or r.get("game_date") or "")
        if stat in _PROP_STATS_ORDER and pred is not None and actual is not None and pid:
            rows[(pid, gid)][stat] = float(pred) - float(actual)

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
