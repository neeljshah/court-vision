"""Gate 1 CLV validation — compares model predictions vs Pinnacle closing lines.

Usage:
    python scripts/run_gate1.py [--db PATH] [--stat pts] [--min-edge 0.0]

Exit codes:
    0  PASS (all three thresholds met)
    1  FAIL or INSUFFICIENT DATA
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# Resolve project root so the script works from any cwd
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.validation.clv_tracker import compute_clv  # noqa: E402  (validates import)

# ── constants ─────────────────────────────────────────────────────────────────

_DEFAULT_DB = _ROOT / "data" / "nba" / "nba_data.db"
_DEFAULT_RESIDUALS = _ROOT / "data" / "models" / "prop_residuals.json"

_MARKET_TO_STAT: Dict[str, str] = {
    "player_points": "pts",
    "player_rebounds": "reb",
    "player_assists": "ast",
    "player_threes": "fg3m",
    "player_steals": "stl",
    "player_blocks": "blk",
    "player_turnovers": "tov",
}

_QUERY = """
SELECT pl.player_id, pl.game_id, pl.market,
       pl.line AS close_line,
       pl.over_odds, pl.under_odds,
       po.actual_value, po.result
FROM prop_lines pl
JOIN prop_outcomes po
  ON pl.game_id    = po.game_id
 AND pl.player_id  = po.player_id
 AND pl.market     = po.market
 AND pl.sport      = po.sport
WHERE pl.bookmaker  = 'pinnacle'
  AND pl.is_closing = 1
  AND pl.sport      = 'basketball_nba'
  AND po.result IN ('over', 'under', 'push')
"""


# ── helpers ───────────────────────────────────────────────────────────────────

def _game_date_from_game_id(game_id: str) -> Optional[str]:
    """Extract YYYY-MM-DD from game_id like '2024-01-15_BOS_LAL'.

    Returns None if the first token does not look like an ISO date.
    """
    token = game_id.split("_")[0]
    parts = token.split("-")
    if len(parts) == 3 and len(parts[0]) == 4 and parts[0].isdigit():
        return token
    return None


def _load_residuals(path: Path, stat_filter: Optional[str]) -> Dict[Tuple[str, str, str], float]:
    """Load prop_residuals.json into a lookup dict.

    Key: (player_id_str, game_date_iso, stat) → predicted value.
    The JSON stores game_date as "Nov 02, 2024"; we normalise to ISO.
    """
    from datetime import datetime

    with open(path) as fh:
        records = json.load(fh)

    lookup: Dict[Tuple[str, str, str], float] = {}
    for rec in records:
        stat = rec.get("stat", "")
        if stat_filter and stat != stat_filter:
            continue
        raw_date = rec.get("game_date", "")
        try:
            # Handle both "Nov 02, 2024" and already-ISO "2024-11-02"
            if "-" in raw_date and len(raw_date) == 10:
                iso_date = raw_date
            else:
                iso_date = datetime.strptime(raw_date, "%b %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        key = (str(rec.get("player_id", "")), iso_date, stat)
        lookup[key] = float(rec.get("predicted", 0.0))
    return lookup


def _payout(odds: float, win: bool) -> float:
    """Dollar payout for a $100 stake given American odds."""
    if win:
        if odds < 0:
            return 100.0 / abs(odds) * 100.0
        return odds / 100.0 * 100.0
    return -100.0


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone() is not None


# ── core logic ────────────────────────────────────────────────────────────────

def run_gate1(
    db_path: Path,
    residuals_path: Path,
    stat_filter: Optional[str],
    min_bets: int,
    min_beat_rate: float,
    min_roi: float,
) -> int:
    """Execute Gate 1 validation. Returns exit code (0=PASS, 1=FAIL/insufficient)."""

    # Load residuals lookup
    if not residuals_path.exists():
        print("INSUFFICIENT DATA: residuals file not found")
        return 1

    lookup = _load_residuals(residuals_path, stat_filter)

    # Connect to DB
    if not db_path.exists():
        print("INSUFFICIENT DATA: DB empty")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if not _table_exists(conn, "prop_lines"):
        conn.close()
        print("INSUFFICIENT DATA: DB empty")
        return 1

    rows = conn.execute(_QUERY).fetchall()
    conn.close()

    # Process rows
    n_bets = 0
    wins = 0
    total_payout = 0.0

    for row in rows:
        market = row["market"]
        stat = _MARKET_TO_STAT.get(market)
        if stat is None:
            continue
        if stat_filter and stat != stat_filter:
            continue

        game_date = _game_date_from_game_id(str(row["game_id"]))
        if game_date is None:
            continue

        key = (str(row["player_id"]), game_date, stat)
        predicted = lookup.get(key)
        if predicted is None:
            continue

        result = row["result"]
        if result == "push":
            continue

        close_line = float(row["close_line"])
        bet_over = predicted > close_line
        win = (bet_over and result == "over") or (not bet_over and result == "under")

        odds = float(row["over_odds"] if bet_over else row["under_odds"])
        payout = _payout(odds, win)

        n_bets += 1
        if win:
            wins += 1
        total_payout += payout

    # Validate import by calling compute_clv (no-op side effect)
    _ = compute_clv(taken_odds=-110, closing_odds=-110, stake=100.0)

    # Aggregate
    print("=== Gate 1 CLV Validation ===")
    print(f"n_bets:     {n_bets}")

    if n_bets < min_bets:
        print(f"beat_rate:  N/A")
        print(f"roi:        N/A")
        print()
        print(f"Gate 1: INSUFFICIENT DATA (N<{min_bets})")
        return 1

    beat_rate = wins / n_bets
    roi = total_payout / (n_bets * 100.0) * 100.0

    beat_pct = beat_rate * 100.0
    print(f"beat_rate:  {beat_pct:.2f}% (need >=55%)")
    print(f"roi:        {roi:.2f}% (need >=3%)")
    print()

    passed = beat_rate >= min_beat_rate and roi >= min_roi
    if passed:
        print("Gate 1: PASS ✓")
        return 0
    print("Gate 1: FAIL ✗")
    return 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Gate 1 CLV validation against Pinnacle closing lines."
    )
    p.add_argument("--db", default=str(_DEFAULT_DB), help="SQLite DB path")
    p.add_argument("--residuals", default=str(_DEFAULT_RESIDUALS), help="prop_residuals.json path")
    p.add_argument("--stat", default=None, help="Filter to one stat (pts/reb/ast/...)")
    p.add_argument("--min-bets", type=int, default=50, help="Min bets threshold (default 50)")
    p.add_argument("--min-beat-rate", type=float, default=0.55, help="Min beat rate (default 0.55)")
    p.add_argument("--min-roi", type=float, default=3.0, help="Min ROI %% (default 3.0)")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    code = run_gate1(
        db_path=Path(args.db),
        residuals_path=Path(args.residuals),
        stat_filter=args.stat,
        min_bets=args.min_bets,
        min_beat_rate=args.min_beat_rate,
        min_roi=args.min_roi,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
