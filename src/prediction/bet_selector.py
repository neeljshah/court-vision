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
from datetime import datetime, timedelta
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)

_CONFIG_PATH  = os.path.join(PROJECT_DIR, "config", "betting.yaml")
_OUTPUT_DIR   = os.path.join(PROJECT_DIR, "data", "output")
_BET_LOG_PATH = os.path.join(PROJECT_DIR, "data", "models", "bet_log.json")

# Conformal predictor cache (per stat, loaded once per process)
_conformal_cache: dict = {}
try:
    from src.prediction.conformal_props import ConformalPredictor as _CP
    _has_conformal = True
except Exception:
    _has_conformal = False


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


def _resolve_clv_predictor(model_path: Optional[str] = None):
    """Return a callable(features)->prediction dict, or None if unavailable.

    The CLV gate degrades gracefully: when clv_predictor.pkl has not been
    trained yet (no settled-bet history), this returns None and bet_selector
    falls back to edge-only filtering rather than crashing the daily run.
    """
    try:
        from src.prediction.clv_predictor import load_model, predict_clv
        load_model(model_path)  # probe — raises FileNotFoundError if absent
    except FileNotFoundError:
        log.warning("clv_predictor.pkl not found — CLV gate skipped (edge-only filtering)")
        return None
    except Exception as exc:  # noqa: BLE001 — any import/load failure -> skip gate
        log.warning("CLV predictor unavailable (%s) — CLV gate skipped", exc)
        return None
    return lambda feats: predict_clv(feats, model_path)


def _resolve_timing_recommender():
    """Return a callable(bet)->recommendation dict, or None if unavailable.

    line_timing.get_fire_recommendation self-degrades to "fire_now" when no
    closing-price model exists, so this only returns None on import failure.
    """
    try:
        from src.data.line_timing import get_fire_recommendation
    except Exception as exc:  # noqa: BLE001
        log.warning("line_timing unavailable (%s) — timing optimiser skipped", exc)
        return None
    return get_fire_recommendation


def select(
    edge_rows: list[dict],
    date_str: str,
    dry_run: bool = False,
    bankroll: Optional[float] = None,
    *,
    clv_predict_fn=None,
    clv_model_path: Optional[str] = None,
    timing_recommend_fn=None,
) -> list[dict]:
    """
    Filter and size bets from slate edge_rows.

    Args:
        edge_rows:       top_edges list from run_daily_slate.py output.
        date_str:        YYYY-MM-DD for output filename.
        dry_run:         If True, bets logged with status="paper".
        bankroll:        Override config bankroll.
        clv_predict_fn:  Injectable callable(features)->{clv_prob, expected_clv,...}
                         for the dual edge+CLV gate.  If None, the real
                         clv_predictor is loaded (when clv_predictor.pkl exists).
        clv_model_path:  Override path to clv_predictor.pkl.
        timing_recommend_fn: Injectable callable(bet)->fire-recommendation dict
                         for the timing optimiser.  If None, the real
                         line_timing.get_fire_recommendation is used.

    Returns:
        List of bet dicts written to data/output/bets_YYYYMMDD.json.  Bets the
        timing optimiser recommends delaying are diverted to the persisted
        delay queue (bet_timing_queue.json) instead of this list.

    Dual filter (task 16.5-03): a candidate must clear BOTH
        |edge| > edge_min (4%)   AND   predicted CLV > clv_min (1.5%)
    before it is sized and selected.
    """
    cfg = _load_config()

    edge_min      = _cfg_float(cfg, "edge_min",      0.04)
    bk            = bankroll if bankroll is not None else _cfg_float(cfg, "bankroll", 1000.0)
    max_per_game  = _cfg_int(cfg,   "max_bets_per_game",        3)
    max_combined  = _cfg_float(cfg, "max_combined_pct",         0.06)
    default_odds  = _cfg_int(cfg,   "default_odds",             -110)
    clv_min       = _cfg_float(cfg, "clv_min",                  1.5)
    clv_enabled   = bool(cfg.get("clv_filter_enabled", True))
    if dry_run is False:
        dry_run = bool(cfg.get("dry_run", False))

    # Resolve the CLV predictor for the dual gate (None -> edge-only fallback).
    _clv_fn = clv_predict_fn
    if _clv_fn is None and clv_enabled:
        _clv_fn = _resolve_clv_predictor(clv_model_path)
    clv_dropped = 0

    # Resolve the timing optimiser (None -> fire every bet immediately).
    timing_enabled = bool(cfg.get("timing_optimizer_enabled", True))
    _timing_fn = timing_recommend_fn
    if _timing_fn is None and timing_enabled:
        _timing_fn = _resolve_timing_recommender()
    scheduled: list[dict] = []   # bets diverted to the delayed-fire queue

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

    def _get_ci(stat: str, projection: Optional[float]) -> tuple:
        """Return (lo_80, hi_80) from conformal predictor or (None, None)."""
        if not _has_conformal or projection is None:
            return None, None
        if stat not in _conformal_cache:
            try:
                _conformal_cache[stat] = _CP.load_residuals(stat)
            except Exception:
                _conformal_cache[stat] = None
        cp = _conformal_cache.get(stat)
        if cp is None:
            return None, None
        try:
            return cp.predict_interval(float(projection), coverage=0.80)
        except Exception:
            return None, None

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

        # 1a. Stat-direction filter (iter-51): skip bet directions with no edge.
        #     BLK OVER has zero edge (Iter-50 finding); blocked here so live
        #     selection never places a zero-edge BLK OVER bet.
        try:
            from src.prediction.bet_thresholds import allowed_directions_for as _allowed_dirs
            _direction_here = "over" if edge > 0 else "under"
            if _direction_here not in _allowed_dirs(stat):
                log.debug("skip %s/%s: direction %s not allowed for %s (stat-direction filter)",
                          player, stat, _direction_here, stat)
                continue
        except Exception:
            pass  # degraded gracefully — never block on import error

        # 1c. Bet-policy stat allowlist (CV_BET_POLICY). Strict no-op under the
        #     default policy `iter57`; under `reb_ast` skips PTS / FG3M / STL /
        #     BLK / TOV candidates. See docs/VS_VEGAS_ASSESSMENT.md §7.
        try:
            from src.prediction.bet_policy import policy_allows_stat as _policy_allows
            if not _policy_allows(stat):
                log.debug("skip %s/%s: stat not in active CV_BET_POLICY", player, stat)
                continue
        except Exception:
            pass  # degraded gracefully — never block on import error

        # 1c-i. Per-policy edge floor + closing-line cap + regime guard
        #     (CV_BET_POLICY). Mirrors compare_to_lines.py:411-431 so live
        #     selection matches the graded harness. `edge` here is RAW stat
        #     units (proj - line, from run_daily_slate.build_edge_rows), so the
        #     0.75 ast_high floor is in the same units. Strict no-op under the
        #     default iter57 policy (policy_min_edge -> 0.0, policy_drops_line ->
        #     False). The playoff-AST guard (IN-2 / §8e) is the one default-on
        #     change: AST bets on playoff game_ids (prefix 004) are skipped
        #     unless CV_ALLOW_PLAYOFF_AST=1, because gated playoff AST is -2.78%.
        try:
            from src.prediction.bet_policy import (
                policy_min_edge as _policy_min_edge,
                policy_drops_line as _policy_drops_line,
                policy_allows_context as _policy_allows_context,
            )
            _floor = _policy_min_edge(stat)
            if _floor > 0.0 and abs(edge) < _floor:
                log.debug("skip %s/%s: |edge| %.2f < policy floor %.2f",
                          player, stat, abs(edge), _floor)
                continue
            _bline = row.get("book_line")
            if _bline is not None and _policy_drops_line(stat, float(_bline)):
                log.debug("skip %s/%s: line %.1f over policy cap", player, stat, float(_bline))
                continue
            if not _policy_allows_context(stat, game_id):
                log.debug("skip %s/%s: regime guard (playoff AST) for game %s",
                          player, stat, game_id)
                continue
        except Exception:
            pass  # degraded gracefully — never block on import error

        # 1b. CLV gate — dual filter: drop bets the model expects to lose
        #     closing-line value, even when the edge clears the bar.
        clv_pred: Optional[dict] = None
        if _clv_fn is not None:
            try:
                clv_pred = _clv_fn({
                    "our_edge":              abs(edge),
                    "pinnacle_delta":        float(row.get("pinnacle_delta", 0.0) or 0.0),
                    "public_pct":            float(row.get("public_pct", 0.5) or 0.5),
                    "time_to_game":          float(row.get("time_to_game", 0.0) or 0.0),
                    "lineup_freshness":      float(row.get("lineup_freshness", 0.0) or 0.0),
                    "line_movement_last_2h": float(row.get("line_movement_last_2h", 0.0) or 0.0),
                })
            except Exception as exc:  # noqa: BLE001 — a bad prediction must not abort the slate
                log.warning("CLV prediction failed for %s/%s (%s) — keeping bet", player, stat, exc)
                clv_pred = None

            if clv_pred is not None and float(clv_pred.get("expected_clv", 0.0)) <= clv_min:
                clv_dropped += 1
                log.debug("skip %s/%s: predicted CLV %.2f%% <= %.2f%%",
                          player, stat, clv_pred.get("expected_clv", 0.0), clv_min)
                continue

        # 2. Game exposure cap
        game_count = game_counts.get(game_id, 0)
        if game_id and game_count >= max_per_game:
            log.debug("skip %s/%s: game cap (%d)", player, stat, max_per_game)
            continue

        # 3. Kelly sizing with correlation matrix
        odds = int(row.get("odds", default_odds) or default_odds)

        # CV_AST_DURABLE_KELLY (default OFF — byte-identical when OFF):
        # For AST bets, size on the durable ~+5%/55%-win core rather than the
        # regime-inflated in-window edge (16–22% edge_frac → win_prob 62–74%).
        # Passes win_prob_override=0.55 (durable 55% win rate, not the +19% peak)
        # AND caps AST stake at 2% (per AST_EDGE_MAXIMIZATION.md §4).
        # Sizing changes the STAKE only — same bets selected, ROI% unchanged.
        # See docs/_audits/AST_CORRECTNESS_AUDIT.md Check 6.
        _AST_DURABLE_KELLY_ON = os.environ.get("CV_AST_DURABLE_KELLY", "0").strip() in ("1", "true", "yes", "on")
        _ast_win_prob_override = None
        _ast_stake_cap = None
        if _AST_DURABLE_KELLY_ON and stat.lower() == "ast":
            _ast_win_prob_override = 0.55   # durable +5% core: full-Kelly 5.5%, quarter-Kelly 1.38%
            _ast_stake_cap = 0.02           # ~2.06% max (quarter-Kelly × 1.5 pace tilt)

        if _has_kelly:
            size = _kelly_corr(
                edge=abs(edge) / max(abs(row.get("book_line", 1.0) or 1.0), 1.0),
                odds=odds,
                bankroll=bk,
                stat=stat,
                open_stats=open_stats,
                win_prob_override=_ast_win_prob_override,
            )
            # Apply AST-specific cap when durable Kelly is active
            if _ast_stake_cap is not None:
                size = min(size, round(bk * _ast_stake_cap, 2))
        else:
            # Fallback: quarter-Kelly approximation
            _fallback_cap = _ast_stake_cap if _ast_stake_cap is not None else 0.04
            fraction = min(abs(edge) * 0.25, _fallback_cap)
            size = round(bk * fraction, 2)

        # 3a. Kelly SIZING tilt (CV_KELLY_TILT). Strict no-op (×1.0) by default.
        #     H1 (INTEL_CAMPAIGN / VS_VEGAS §8d): high opp_pace concentrates the
        #     gated AST edge — nudge that slice up ~1.25× (never down, never drops
        #     a bet). Reads row['opp_pace'] when present; absent => ×1.0.
        try:
            from src.prediction.bet_policy import policy_kelly_tilt as _kelly_tilt
            _tilt = _kelly_tilt(stat, row.get("opp_pace"))
            if _tilt != 1.0:
                size = round(size * _tilt, 2)
        except Exception:
            pass  # degraded gracefully — never block on import error

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

        proj = row.get("projection")
        lo_80, hi_80 = _get_ci(stat, proj)

        bet = {
            "player":     player,
            "stat":       stat,
            "direction":  "over" if edge > 0 else "under",
            "projection": proj,
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
                f"(proj {proj}), "
                f"kelly={size:.2f}, conf={row.get('confidence','?')}"
            ),
            "ci_lo_80":    lo_80,
            "ci_hi_80":    hi_80,
            "alt_line":    row.get("alt_line"),
            "alt_line_ev": row.get("alt_line_ev"),
            "clv_prob":    clv_pred.get("clv_prob") if clv_pred else None,
            "predicted_clv": clv_pred.get("expected_clv") if clv_pred else None,
            "source":      row.get("source", "slate"),
        }

        # 5. Timing optimiser — fire now, or divert to the delayed-fire queue.
        if _timing_fn is not None:
            try:
                rec = _timing_fn(bet)
            except Exception as exc:  # noqa: BLE001 — never let timing abort a slate
                log.warning("timing recommendation failed for %s/%s (%s) — firing now",
                            player, stat, exc)
                rec = None
            if rec is not None and rec.get("action") == "wait":
                fire_at = (
                    datetime.utcnow()
                    + timedelta(minutes=float(rec.get("delay_minutes", 0.0) or 0.0))
                )
                bet["status"] = "scheduled"
                scheduled.append({
                    "bet": bet,
                    "fire_at": fire_at.isoformat() + "Z",
                    "recommendation": rec,
                })
                game_counts[game_id] = game_count + 1
                player_stakes[player] = committed + size
                open_stats.append(stat)
                continue
            if rec is not None:
                bet["timing"] = rec

        bets.append(bet)
        game_counts[game_id] = game_count + 1
        player_stakes[player] = committed + size
        open_stats.append(stat)

    if _timing_fn is not None:
        _write_timing_queue(scheduled, date_str)

    _write_bets(bets, date_str)

    if dry_run:
        _append_to_bet_log(bets)

    mode = "PAPER" if dry_run else "LIVE"
    clv_note = f", clv_min={clv_min}% ({clv_dropped} dropped)" if _clv_fn is not None else ""
    timing_note = f", {len(scheduled)} scheduled" if _timing_fn is not None and scheduled else ""
    print(f"[bet_selector] {mode}: {len(bets)} bets selected from {len(candidates)} edges "
          f"(edge_min={edge_min}, bankroll=${bk:.0f}{clv_note}{timing_note})")
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


def route_intraday_events(events: list[dict], date_str: str = None) -> int:
    """Receive intraday trigger events and persist them for bet selection.

    Called by scripts/intraday_trigger.py (task 19.5-02): live trigger events
    (foul trouble, late scratch, garbage time) arrive here each carrying a
    ``source`` tag.  They are appended to data/output/intraday_triggers_{date}.json
    so the selection pipeline can act on them.

    Args:
        events:   List of trigger-event dicts, each with a ``source`` key.
        date_str: YYYY-MM-DD (default: today) for the output filename.

    Returns:
        Number of events routed in this call.
    """
    from datetime import date as _date
    date_str = date_str or str(_date.today())
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    path = os.path.join(_OUTPUT_DIR, f"intraday_triggers_{date_str.replace('-', '')}.json")

    existing: list[dict] = []
    if os.path.exists(path):
        try:
            with open(path) as f:
                existing = json.load(f).get("events", [])
        except Exception:
            existing = []

    stamped = []
    for ev in events:
        ev = dict(ev)
        ev.setdefault("source", "intraday")
        ev["routed_at"] = datetime.utcnow().isoformat() + "Z"
        stamped.append(ev)
        log.info("intraday event routed: source=%s event=%s",
                 ev.get("source"), ev.get("event", ev.get("recommendation", "?")))

    payload = {"date": date_str, "count": len(existing) + len(stamped),
               "events": existing + stamped}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return len(stamped)


def _write_timing_queue(scheduled: list[dict], date_str: str) -> str:
    """Persist the delayed-fire queue to data/output/bet_timing_queue.json.

    Written on every run (even when empty) so the queue file always reflects
    the current scheduling state for the timing-aware firing loop to consume.
    """
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    path = os.path.join(_OUTPUT_DIR, "bet_timing_queue.json")
    payload = {
        "date":         date_str,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count":        len(scheduled),
        "queue":        scheduled,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    if scheduled:
        print(f"[bet_selector] {len(scheduled)} bets scheduled for delayed fire -> {path}")
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


if __name__ == "__main__":
    import argparse
    from datetime import date as _date

    parser = argparse.ArgumentParser(description="Bet selector: produce bets_YYYYMMDD.json")
    parser.add_argument("--date", default=str(_date.today()), help="Date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Paper mode (status=paper)")
    parser.add_argument("--bankroll", type=float, default=None, help="Override bankroll")
    args = parser.parse_args()

    # Guard: LIVE_BETTING env var must be 0 (paper mode enforced)
    live = int(os.environ.get("LIVE_BETTING", "0"))
    if live != 0:
        print("[bet_selector] ERROR: LIVE_BETTING must be 0 (paper mode only)", file=sys.stderr)
        sys.exit(1)

    # Load slate edges for the date
    date_compact = args.date.replace("-", "")
    slate_path = os.path.join(_OUTPUT_DIR, f"slate_{date_compact}.json")
    if not os.path.exists(slate_path):
        print(f"[bet_selector] No slate file for {args.date}: {slate_path}")
        sys.exit(0)  # not an error — no games today

    try:
        with open(slate_path) as _f:
            _slate = json.load(_f)
        _edge_rows = _slate.get("top_edges", [])
    except Exception as _exc:
        print(f"[bet_selector] ERROR reading slate: {_exc}", file=sys.stderr)
        sys.exit(1)

    select(
        edge_rows=_edge_rows,
        date_str=args.date,
        dry_run=args.dry_run,
        bankroll=args.bankroll,
    )
