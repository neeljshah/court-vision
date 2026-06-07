"""betting_edge.py — Phase 11: Edge calculation, CLV tracking, arb detection.

Imports utilities from betting_portfolio.py — no duplication.
"""
from __future__ import annotations

import csv
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from src.prediction.betting_portfolio import (
    _american_to_prob,
    kelly_corr,
    KELLY_FRACTION,
)

_ROOT    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CLV_CSV = os.path.join(_ROOT, "data", "clv_log.csv")

_CLV_FIELDS = ["bet_id", "market", "model_prob", "opening_line",
               "closing_line", "result", "clv"]


# ── BettingEdge ───────────────────────────────────────────────────────────────

class BettingEdge:
    """Calculate model edge vs book implied probability and assign star rating."""

    @staticmethod
    def implied_prob(american_odds: int) -> float:
        """Convert American odds to no-vig implied probability."""
        return _american_to_prob(american_odds)

    @staticmethod
    def edge(model_prob: float, american_odds: int) -> float:
        """Return edge = model_prob - implied_prob. Positive = value bet."""
        return model_prob - _american_to_prob(american_odds)

    @staticmethod
    def star_rating(edge_val: float) -> int:
        """1★ edge>5%, 2★ edge>8%, 3★ edge>12%. 0 = no edge."""
        if edge_val > 0.12:
            return 3
        if edge_val > 0.08:
            return 2
        if edge_val > 0.05:
            return 1
        return 0

    def evaluate(self, model_prob: float, american_odds: int,
                 bankroll: float = 1000.0) -> dict:
        """Return full evaluation dict for a candidate bet."""
        e = self.edge(model_prob, american_odds)
        stars = self.star_rating(e)
        size = kelly_corr(e, american_odds, bankroll) if e > 0 else 0.0
        return {
            "model_prob":    round(model_prob, 4),
            "implied_prob":  round(_american_to_prob(american_odds), 4),
            "edge":          round(e, 4),
            "stars":         stars,
            "kelly_size":    size,
        }


# ── CLVTracker ────────────────────────────────────────────────────────────────

@dataclass
class CLVEntry:
    bet_id:       str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    market:       str = ""
    model_prob:   float = 0.0
    opening_line: int   = 0
    closing_line: Optional[int] = None
    result:       Optional[str] = None     # 'win'|'loss'|'push'|None
    clv:          Optional[float] = None   # closing_implied - opening_implied


class CLVTracker:
    """Log bets and compute closing line value."""

    def __init__(self, path: str = _CLV_CSV) -> None:
        self._path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _read(self) -> List[dict]:
        if not os.path.exists(self._path):
            return []
        with open(self._path, newline="") as f:
            return list(csv.DictReader(f))

    def _write(self, rows: List[dict]) -> None:
        with open(self._path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_CLV_FIELDS)
            w.writeheader()
            w.writerows(rows)

    def log(self, market: str, model_prob: float, opening_line: int) -> str:
        """Append a new bet. Returns bet_id."""
        entry = CLVEntry(market=market, model_prob=model_prob,
                         opening_line=opening_line)
        rows = self._read()
        rows.append({
            "bet_id":       entry.bet_id,
            "market":       market,
            "model_prob":   model_prob,
            "opening_line": opening_line,
            "closing_line": "",
            "result":       "",
            "clv":          "",
        })
        self._write(rows)
        return entry.bet_id

    def close(self, bet_id: str, closing_line: int,
              result: Optional[str] = None) -> Optional[float]:
        """Record closing line, compute CLV = closing_implied - opening_implied."""
        rows = self._read()
        clv_val: Optional[float] = None
        for r in rows:
            if r["bet_id"] == bet_id:
                open_imp  = _american_to_prob(int(r["opening_line"]))
                close_imp = _american_to_prob(closing_line)
                clv_val   = round(close_imp - open_imp, 4)
                r["closing_line"] = closing_line
                r["result"]       = result or ""
                r["clv"]          = clv_val
                break
        self._write(rows)
        return clv_val

    def clv_summary(self) -> dict:
        """Return avg CLV, win rate, ROI across all logged bets."""
        rows = self._read()
        if not rows:
            return {"count": 0, "avg_clv": 0.0, "win_rate": 0.0, "roi": 0.0}
        clv_vals  = [float(r["clv"]) for r in rows if r.get("clv") not in ("", None)]
        settled   = [r for r in rows if r.get("result") in ("win", "loss", "push")]
        wins      = sum(1 for r in settled if r["result"] == "win")
        win_rate  = wins / len(settled) if settled else 0.0
        # Simplified ROI: each bet risked 1 unit; win pays implied payout
        roi_vals: List[float] = []
        for r in settled:
            try:
                ol  = int(r["opening_line"])
                pay = (100 / abs(ol)) if ol < 0 else (ol / 100.0)
                roi_vals.append(pay if r["result"] == "win" else -1.0)
            except (ValueError, ZeroDivisionError):
                pass
        roi = float(np.mean(roi_vals)) if roi_vals else 0.0
        return {
            "count":    len(rows),
            "avg_clv":  round(float(np.mean(clv_vals)) if clv_vals else 0.0, 4),
            "win_rate": round(win_rate, 3),
            "roi":      round(roi, 4),
        }


# ── ArbDetector ───────────────────────────────────────────────────────────────

@dataclass
class ArbResult:
    type:  str         # "arb" | "middle"
    legs:  List[dict]  # [{book, side, odds}]
    ev:    float


class ArbDetector:
    """Detect pure arbs and middles from multi-book lines."""

    MIDDLE_GAP = 0.5   # minimum line gap to flag as middle

    def detect(self, book_lines: Dict[str, Dict[str, int]]) -> List[ArbResult]:
        """
        Detect arbs/middles.

        Args:
            book_lines: {market_key: {book: american_odds}}
                        For two-sided markets pass "{key}_over" and "{key}_under".

        Returns:
            List of ArbResult sorted by EV descending.
        """
        results: List[ArbResult] = []
        # Group by base market (strip _over/_under suffix)
        markets: Dict[str, Dict[str, Dict[str, int]]] = {}
        for key, book_odds in book_lines.items():
            base, _, side = key.rpartition("_")
            if side not in ("over", "under"):
                base, side = key, "moneyline"
            markets.setdefault(base, {})[side] = book_odds

        for base, sides in markets.items():
            if "over" not in sides or "under" not in sides:
                continue
            best_over  = max(sides["over"].items(),  key=lambda x: x[1])
            best_under = max(sides["under"].items(), key=lambda x: x[1])
            imp_over   = _american_to_prob(best_over[1])
            imp_under  = _american_to_prob(best_under[1])
            total_imp  = imp_over + imp_under

            if total_imp < 1.0:
                ev = round((1.0 / total_imp - 1.0), 4)
                results.append(ArbResult(
                    type="arb",
                    legs=[
                        {"book": best_over[0],  "side": "over",  "odds": best_over[1]},
                        {"book": best_under[0], "side": "under", "odds": best_under[1]},
                    ],
                    ev=ev,
                ))

        return sorted(results, key=lambda r: r.ev, reverse=True)

    def detect_middles(
        self,
        book_lines: Dict[str, Dict[str, float]],
    ) -> List[ArbResult]:
        """
        Detect middle opportunities where over_line > under_line on same market.

        Args:
            book_lines: {market_key: {book: prop_line_value}}
                        e.g. {"LeBron_pts": {"DK": 27.5, "FD": 28.5}}
        """
        results: List[ArbResult] = []
        for market, book_vals in book_lines.items():
            if len(book_vals) < 2:
                continue
            best_over_book  = max(book_vals.items(), key=lambda x: x[1])   # highest line → best over
            best_under_book = min(book_vals.items(), key=lambda x: x[1])   # lowest line  → best under
            gap = best_over_book[1] - best_under_book[1]
            if gap >= self.MIDDLE_GAP and best_over_book[0] != best_under_book[0]:
                results.append(ArbResult(
                    type="middle",
                    legs=[
                        {"book": best_under_book[0], "side": "over",  "line": best_under_book[1]},
                        {"book": best_over_book[0],  "side": "under", "line": best_over_book[1]},
                    ],
                    ev=round(gap, 2),
                ))
        return sorted(results, key=lambda r: r.ev, reverse=True)


# ── Prop correlation matrix ───────────────────────────────────────────────────

_CORR_MATRIX_PATH = os.path.join(_ROOT, "data", "models", "prop_corr_matrix.json")
_PROP_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def compute_prop_correlation_matrix(prop_history_df: "object") -> dict:
    """DEPRECATED — dead code, zero callers repo-wide (2026-06-01 hygiene).

    The LIVE regenerator is
    ``src.prediction.betting_portfolio.compute_prop_corr_matrix`` (invoked via
    ``python -m src.prediction.betting_portfolio --compute-corr``).  Do NOT
    call this function; it is retained only for reference and will be removed
    in a future cleanup pass.

    Bug note: the original implementation grouped residuals by
    ``residuals.index // 7`` (arbitrary adjacent-row bucketing), which
    correlated whatever rows happened to share a bucket rather than the same
    (player_id, game_id).  The group key below is corrected to
    ``(player_id, game_id)`` so the logic is at least sound if this function
    is ever resurrected.

    Args:
        prop_history_df: pandas DataFrame with columns
            [stat, predicted, actual, player_id, game_id].
            Residual = predicted - actual.  One row per prediction.

    Returns:
        Nested dict {stat_a: {stat_b: corr}} with NaN filled as 0.0.
        Also persists result to data/models/prop_corr_matrix.json.
    """
    try:
        residuals = prop_history_df.copy()
        residuals["residual"] = (
            residuals["predicted"].astype(float) - residuals["actual"].astype(float)
        )
        residuals = residuals[residuals["stat"].isin(_PROP_STATS)]
        if residuals.empty:
            return {}

        # Fixed group key: was ``residuals.index // max(len(_PROP_STATS), 1)``
        # (index//7 — arbitrary adjacent-row bucketing that inflated v1 corrs).
        # Correct key is (player_id, game_id) so each bucket = one player-game.
        group_key = list(
            zip(
                residuals.get("player_id", residuals.index).astype(str),
                residuals.get("game_id", residuals.index).astype(str),
            )
        )
        residuals = residuals.copy()
        residuals["_group"] = group_key
        pivot = residuals.pivot_table(
            index="_group",
            columns="stat",
            values="residual",
            aggfunc="mean",
        )
        corr = pivot.corr().fillna(0.0)
        result: dict = {
            s: {t: round(float(corr.at[s, t]), 4)
                for t in _PROP_STATS if t in corr.columns}
            for s in _PROP_STATS if s in corr.index
        }
        with open(_CORR_MATRIX_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return result
    except Exception as e:
        import logging
        logging.warning("compute_prop_correlation_matrix failed: %s", e)
        return {}
