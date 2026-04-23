"""
bet_selector.py — Phase 15: Bet selector middleware.

Input:  slate JSON (top_edges list from run_daily_slate.py)
Output: bets_YYYYMMDD.json — flat list of placeable bets with stakes

Filters:
  - |edge| > EDGE_MIN (default 0.04)
  - kelly_size > 0
  - max MAX_BETS_PER_GAME bets per game_id
  - cap combined bankroll exposure when same player has 2+ stat bets
  - apply kelly_corr() with live correlation matrix for final stake
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)

_CONFIG_PATH  = os.path.join(PROJECT_DIR, "config", "betting.yaml")
_OUTPUT_DIR   = os.path.join(PROJECT_DIR, "data", "output")
_BET_LOG_PATH = os.path.join(PROJECT_DIR, "data", "models", "bet_log.json")


def _load_config() -> dict:
    try:
        import yaml
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # yaml not installed — parse minimal subset manually
        cfg: dict = {}
        try:
            with open(_CONFIG_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or ":" not in line:
                        continue
                    k, _, v = line.partition(":")
                    v = v.strip()
                    try:
                        cfg[k.strip()] = float(v) if "." in v else int(v)
                    except ValueError:
                        cfg[k.strip()] = v
        except Exception:
            pass
        return cfg
    except Exception:
        return {}


def _cfg_float(cfg: dict, key: str, default: float) -> float:
    return float(cfg.get(key, default))


def _cfg_int(cfg: dict, key: str, default: int) -> int:
    return int(cfg.get(key, default))


def select(
    edge_rows: list[dict],
    date_str: str,
    dry_run: bool = False,
    bankroll: Optional[float] = None,
) -> list[dict]:
    """
    Filter and size bets from slate edge_rows.

    Args:
        edge_rows:  top_edges list from run_daily_slate.py output.
        date_str:   YYYY-MM-DD for output filename.
        dry_run:    If True, bets logged with status="paper".
        bankroll:   Override config bankroll.

    Returns:
        List of bet dicts written to data/output/bets_YYYYMMDD.json.
    """
    cfg = _load_config()

    edge_min      = _cfg_float(cfg, "edge_min",      0.04)
    bk            = bankroll if bankroll is not None else _cfg_float(cfg, "bankroll", 1000.0)
    max_per_game  = _cfg_int(cfg,   "max_bets_per_game",        3)
    max_combined  = _cfg_float(cfg, "max_combined_pct",         0.06)
    default_odds  = _cfg_int(cfg,   "default_odds",             -110)
    if dry_run is False:
        dry_run = bool(cfg.get("dry_run", False))

    # Import kelly_corr (graceful fallback if portfolio unavailable)
    try:
        from src.prediction.betting_portfolio import kelly_corr as _kelly_corr
        _has_kelly = True
    except Exception:
        _has_kelly = False

    bets: list[dict] = []
    game_counts:   dict[str, int]   = {}   # game_id -> bet count
    player_stakes: dict[str, float] = {}   # player -> total $ committed
    open_stats:    list[str]        = []   # stats with bets already selected

    # Sort descending by absolute edge — take best edges first
    candidates = sorted(edge_rows, key=lambda r: abs(r.get("edge", 0.0)), reverse=True)

    for row in candidates:
        edge    = float(row.get("edge", 0.0))
        player  = row.get("player", "")
        stat    = row.get("stat", "")
        game_id = row.get("game_id", "")

        # 1. Edge threshold
        if abs(edge) < edge_min:
            continue

        # 2. Game exposure cap
        game_count = game_counts.get(game_id, 0)
        if game_id and game_count >= max_per_game:
            log.debug("skip %s/%s: game cap (%d)", player, stat, max_per_game)
            continue

        # 3. Kelly sizing with correlation matrix
        odds = int(row.get("odds", default_odds) or default_odds)
        if _has_kelly:
            size = _kelly_corr(
                edge=abs(edge) / max(abs(row.get("book_line", 1.0) or 1.0), 1.0),
                odds=odds,
                bankroll=bk,
                stat=stat,
                open_stats=open_stats,
            )
        else:
            # Fallback: quarter-Kelly approximation
            fraction = min(abs(edge) * 0.25, 0.04)
            size = round(bk * fraction, 2)

        if size <= 0:
            continue

        # 4. Per-player combined cap (same player, multiple stats)
        committed = player_stakes.get(player, 0.0)
        if committed + size > bk * max_combined:
            size = max(bk * max_combined - committed, 0.0)
            if size <= 0:
                log.debug("skip %s/%s: combined player cap", player, stat)
                continue

        size = round(size, 2)

        bet = {
            "player":     player,
            "stat":       stat,
            "direction":  "over" if edge > 0 else "under",
            "projection": row.get("projection"),
            "book_line":  row.get("book_line"),
            "edge":       round(edge, 4),
            "odds":       odds,
            "stake":      size,
            "kelly_size": size,
            "confidence": row.get("confidence", "low"),
            "team":       row.get("team", ""),
            "opp_team":   row.get("opp_team", ""),
            "game_id":    game_id,
            "date":       date_str,
            "status":     "paper" if dry_run else "pending",
            "rationale":  (
                f"edge={edge:+.2f} vs line {row.get('book_line')} "
                f"(proj {row.get('projection')}), "
                f"kelly={size:.2f}, conf={row.get('confidence','?')}"
            ),
        }

        bets.append(bet)
        game_counts[game_id] = game_count + 1
        player_stakes[player] = committed + size
        open_stats.append(stat)

    _write_bets(bets, date_str)

    if dry_run:
        _append_to_bet_log(bets)

    mode = "PAPER" if dry_run else "LIVE"
    print(f"[bet_selector] {mode}: {len(bets)} bets selected from {len(candidates)} edges "
          f"(edge_min={edge_min}, bankroll=${bk:.0f})")
    _print_bets_table(bets)

    return bets


def _write_bets(bets: list[dict], date_str: str) -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    date_compact = date_str.replace("-", "")
    path = os.path.join(_OUTPUT_DIR, f"bets_{date_compact}.json")
    payload = {
        "date":         date_str,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count":        len(bets),
        "bets":         bets,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[bet_selector] Written -> {path}")
    return path


def _append_to_bet_log(bets: list[dict]) -> None:
    """Append paper bets to bet_log.json (idempotent by player+stat+date key)."""
    existing: list[dict] = []
    if os.path.exists(_BET_LOG_PATH):
        try:
            with open(_BET_LOG_PATH) as f:
                existing = json.load(f)
        except Exception:
            existing = []

    seen = {(b.get("player"), b.get("stat"), b.get("date")) for b in existing}
    added = 0
    for bet in bets:
        key = (bet.get("player"), bet.get("stat"), bet.get("date"))
        if key not in seen:
            existing.append(bet)
            seen.add(key)
            added += 1

    with open(_BET_LOG_PATH, "w") as f:
        json.dump(existing, f, indent=2)

    if added:
        log.info("bet_log: appended %d paper bets", added)


def _print_bets_table(bets: list[dict]) -> None:
    if not bets:
        print("[bet_selector] No bets meet criteria.")
        return
    print(f"\n  {'#':>2}  {'Player':<24} {'Stat':<6} {'Dir':<6} "
          f"{'Line':>6} {'Proj':>6} {'Edge':>7} {'Stake':>8}")
    print(f"  {'-'*70}")
    for i, b in enumerate(bets, 1):
        line_s = f"{b['book_line']:>6.1f}" if b["book_line"] is not None else "   N/A"
        proj_s = f"{b['projection']:>6.1f}" if b["projection"] is not None else "   N/A"
        print(f"  {i:>2}  {b['player']:<24} {b['stat']:<6} {b['direction']:<6} "
              f"{line_s} {proj_s} {b['edge']:>+7.4f} ${b['stake']:>7.2f}")
    total = sum(b["stake"] for b in bets)
    print(f"  {'':>2}  {'TOTAL STAKE':>24}                              ${total:>7.2f}\n")
