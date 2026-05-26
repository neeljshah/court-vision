"""Gate 1 CLV validation — compares model predictions vs Pinnacle closing lines.

Modes
-----
  --mode db      Real-Pinnacle path: join prop_lines (is_closing=1, pinnacle)
                 × prop_outcomes × prop_residuals.json. Default.
  --mode ledger  Synthetic-CLV path: reads data/pnl_ledger_clv_synthetic.csv
                 (335K bets, walk-forward OOF predictions vs synthetic close).
                 Honest "best available signal today" until real Pinnacle
                 closes accumulate during NBA season.

Usage:
    python scripts/run_gate1.py [--mode db|ledger] [--stat pts] [--audit-only]

Exit codes:
    0  PASS (all three thresholds met)
    1  FAIL or INSUFFICIENT DATA
"""
from __future__ import annotations

import argparse
import glob
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
_DEFAULT_LEDGER = _ROOT / "data" / "pnl_ledger_clv_synthetic.csv"
_SEASON_GAMES_GLOB = str(_ROOT / "data" / "nba" / "season_games_*.json")

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

_GAME_DATE_LOOKUP: Optional[Dict[str, str]] = None


def _load_game_date_lookup() -> Dict[str, str]:
    """Build NBA-Stats game_id → ISO date lookup from season_games_*.json."""
    global _GAME_DATE_LOOKUP
    if _GAME_DATE_LOOKUP is not None:
        return _GAME_DATE_LOOKUP
    out: Dict[str, str] = {}
    for path in glob.glob(_SEASON_GAMES_GLOB):
        try:
            blob = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        rows = blob.get("rows", blob) if isinstance(blob, dict) else blob
        if not isinstance(rows, list):
            continue
        for r in rows:
            gid = str(r.get("game_id", "")).strip()
            gdate = str(r.get("game_date", "")).strip()
            if gid and gdate and len(gdate) == 10:
                out[gid] = gdate
    _GAME_DATE_LOOKUP = out
    return out


def _game_date_from_game_id(game_id: str) -> Optional[str]:
    """Extract YYYY-MM-DD from game_id.

    Supports two formats:
      - ISO-prefixed: '2024-01-15_BOS_LAL' → '2024-01-15'
      - NBA Stats:   '0022400061' → looked up from season_games_*.json
    """
    token = game_id.split("_")[0]
    parts = token.split("-")
    if len(parts) == 3 and len(parts[0]) == 4 and parts[0].isdigit():
        return token
    # NBA Stats format: try lookup
    lookup = _load_game_date_lookup()
    return lookup.get(str(game_id))


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


def run_gate1_ledger(
    ledger_path: Path,
    stat_filter: Optional[str],
    min_bets: int,
    min_beat_rate: float,
    min_roi: float,
    audit_only: bool,
) -> int:
    """Synthetic-CLV mode: read pnl_ledger_clv_synthetic.csv directly.

    The ledger already pairs walk-forward OOF predictions with synthetic
    closing lines (4-tier fallback: real → snapshot → oof q50 → cohort).
    All rows are tier-3 (oof q50) by default — this is NOT real Pinnacle
    CLV, but it IS the cleanest forward-honest signal we have until
    October when the NBA season resumes and the Pinnacle daemon writes
    real closes to prop_lines.
    """
    import csv as _csv

    if not ledger_path.exists():
        print(f"INSUFFICIENT DATA: ledger not found at {ledger_path}")
        return 1

    n_bets = 0
    wins = 0
    total_stake = 0.0
    total_pnl = 0.0
    by_stat: Dict[str, Dict[str, float]] = {}
    tier_counts: Dict[int, int] = {}

    with open(ledger_path, encoding="utf-8") as fh:
        # Skip the leading comment line
        first = fh.readline()
        if not first.startswith("#"):
            fh.seek(0)
        reader = _csv.DictReader(fh)
        for row in reader:
            if audit_only and row.get("is_audit_fold", "false").lower() != "true":
                continue
            stat = (row.get("stat") or "").strip().lower()
            if stat_filter and stat != stat_filter:
                continue
            status = (row.get("status") or "").strip().lower()
            if status not in ("won", "lost"):
                continue
            try:
                stake = float(row.get("stake") or 0.0)
                pnl = float(row.get("profit_loss") or 0.0)
                tier = int(row.get("source_tier") or 0)
            except (ValueError, TypeError):
                continue
            n_bets += 1
            if status == "won":
                wins += 1
            total_stake += stake
            total_pnl += pnl
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            agg = by_stat.setdefault(stat, {"n": 0, "w": 0, "stake": 0.0, "pnl": 0.0})
            agg["n"] += 1
            if status == "won":
                agg["w"] += 1
            agg["stake"] += stake
            agg["pnl"] += pnl

    print("=== Gate 1 CLV Validation (LEDGER MODE) ===")
    print(f"  Source:     {ledger_path.name} ({'audit fold only' if audit_only else 'all rows'})")
    print(f"  Tier mix:   {tier_counts}")
    print(f"  CAVEAT:     synthetic close (tier 3 = oof q50). NOT real Pinnacle.")
    print()
    print(f"n_bets:     {n_bets}")

    if n_bets < min_bets:
        print(f"Gate 1: INSUFFICIENT DATA (N<{min_bets})")
        return 1

    beat_rate = wins / n_bets
    roi = (total_pnl / total_stake * 100.0) if total_stake > 0 else 0.0
    print(f"beat_rate:  {beat_rate * 100.0:.2f}%  (need >={min_beat_rate * 100:.0f}%)")
    print(f"roi:        {roi:.2f}%  (need >={min_roi:.1f}%)")
    print(f"total_pnl:  ${total_pnl:,.2f} on ${total_stake:,.2f} staked")
    print()
    print("Per-stat breakdown:")
    print(f"  {'stat':<6} {'n':>8} {'beat':>8} {'roi':>8}")
    for stat in sorted(by_stat):
        a = by_stat[stat]
        beat = a["w"] / a["n"] * 100.0 if a["n"] else 0.0
        sroi = a["pnl"] / a["stake"] * 100.0 if a["stake"] > 0 else 0.0
        print(f"  {stat:<6} {int(a['n']):>8d} {beat:>7.2f}% {sroi:>7.2f}%")
    print()

    passed = beat_rate >= min_beat_rate and roi >= min_roi
    if passed:
        print("Gate 1 (LEDGER MODE): PASS")
        return 0
    print("Gate 1 (LEDGER MODE): FAIL")
    return 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Gate 1 CLV validation against Pinnacle closing lines."
    )
    p.add_argument("--mode", choices=("db", "ledger"), default="db",
                   help="db=real Pinnacle (default), ledger=synthetic CLV from pnl_ledger")
    p.add_argument("--db", default=str(_DEFAULT_DB), help="SQLite DB path")
    p.add_argument("--residuals", default=str(_DEFAULT_RESIDUALS), help="prop_residuals.json path")
    p.add_argument("--ledger", default=str(_DEFAULT_LEDGER),
                   help="CLV ledger CSV path (ledger mode only)")
    p.add_argument("--audit-only", action="store_true",
                   help="Restrict ledger mode to is_audit_fold=true rows (hold-out subset)")
    p.add_argument("--stat", default=None, help="Filter to one stat (pts/reb/ast/...)")
    p.add_argument("--min-bets", type=int, default=50, help="Min bets threshold (default 50)")
    p.add_argument("--min-beat-rate", type=float, default=0.55, help="Min beat rate (default 0.55)")
    p.add_argument("--min-roi", type=float, default=3.0, help="Min ROI %% (default 3.0)")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.mode == "ledger":
        code = run_gate1_ledger(
            ledger_path=Path(args.ledger),
            stat_filter=args.stat,
            min_bets=args.min_bets,
            min_beat_rate=args.min_beat_rate,
            min_roi=args.min_roi,
            audit_only=args.audit_only,
        )
    else:
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
