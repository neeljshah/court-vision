"""scripts.platformkit.bestbets.props_paper_placer -- paper-place PRICED player props
into the SAME unified units ledger (clv_ledger.jsonl) the game-moneyline + PM bets use.

THE GAP: props were COMPUTED as cards (prop_cards.py) but NEVER paper-placed -> they
never reached the bankroll P&L or the "best bets you placed" view. This reads the PRICED
prop board edges (prop_edge.build_prop_board), tiers each via the SAME pm_trading.policy
the day-trader uses, and records a paper bet.

HONEST FRAMING (binding):
  * Only PRICED edges (edge_basis=="ev_vs_priced") place; model-only DFS pick'em skipped.
  * Legacy taken price = RAW vig-inclusive decimal ((ev+1)/p), the CONSERVATIVE line faced;
    when CV_PROP_BEST_EXEC is on (default) it is shopped to the best cross-book price via
    prop_best_exec.gate_and_stamp (suppress-only: can block or improve, never worsen).
  * clv_is_proxy=True ALWAYS (a prop close is a proxy) -> EV floors raised by the penalty.
  * Rows carry market_type="prop" so the game-moneyline settler skips them; they settle on
    their own stat outcome -- until then PLACED + PENDING (0 P&L movement; nothing faked).
  * UNITS only, NO $ field; executed=False; edge_claimed=False; real-money default-DENY.

RAILS: build only under scripts/platformkit/; ASCII; public fns NEVER raise.
Per-file test: scripts/platformkit/bestbets/test_props_paper_placer.py
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.bestbets import prop_best_exec as _exec

logger = logging.getLogger(__name__)

def _best_exec_on() -> bool:
    """Best-exec (shop+devig CLV gate+breaker) gates every write unless off; read
    per-call (not at import) so tests can toggle it via monkeypatch/env."""
    return os.environ.get("CV_PROP_BEST_EXEC", "1").strip().lower() not in ("0", "false", "off")

# Sports whose prop board produces priced edges today (mirrors prop_cards.DEFAULT).
DEFAULT_PROP_SPORTS = ("soccer_intl", "mlb")

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER = _REPO / "data" / "frontend" / "clv_ledger.jsonl"

_HONEST_NOTE = (
    "Paper-placed PRICED player props (UNITS not $). Taken at the raw vig-inclusive "
    "line; clv_is_proxy=True (no true prop close); settles on the stat outcome, not the "
    "game moneyline. edge_claimed=False; real-money DENY."
)

# Tier evidence rank (A strongest). min_tier discipline: drop the marginal lower tiers
# (their EV is swamped by the proxy-close penalty + vig) so the paper slate concentrates
# on the model's higher-conviction picks. EV here is MODEL_VIEW, never a proven edge.
_TIER_RANK = {"A": 0, "B": 1, "C": 2}

# Per-sport SETTLEABLE-stat allowlist: only place a prop we can grade from a keyless feed
# (else it PENDS forever = a phantom placement). Soccer/WC (prop_settler_soccer): goals/
# assists/cards resolve per player, shots/saves for the leader; Shots On Target / Fouls have
# NO keyless feed -> dropped. Sports ABSENT here (mlb: full statsapi boxscore) place all stats.
_SETTLEABLE_STATS_BY_SPORT: Dict[str, frozenset] = {
    "soccer_intl": frozenset({"Goals", "Assists", "Goal+Assist", "Cards", "Shots", "Saves"}),
}
_SETTLEABLE_STATS_BY_SPORT["soccer"] = _SETTLEABLE_STATS_BY_SPORT["soccer_intl"]


def _is_settleable(sport: str, stat: Any) -> bool:
    """True unless *sport* has an allowlist and *stat* is outside it (ungradeable keyless)."""
    allow = _SETTLEABLE_STATS_BY_SPORT.get(str(sport).lower())
    return True if allow is None else (str(stat or "").strip() in allow)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _today_et() -> str:
    try:
        from scripts.platformkit.paper.et_day import now_et_day
        return now_et_day()
    except Exception:  # noqa: BLE001
        return datetime.now(tz=timezone.utc).date().isoformat()


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None  # drop NaN


def placement_from_edge(edge: Dict[str, Any], sport: str,
                        *, today: Optional[str] = None,
                        min_tier: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """One PRICED prop board edge -> a tiered placement dict, or None (skip).

    Skips: non-priced (model-only) edges, unparseable probs/EV, below the proxy-
    adjusted EV floor (tier None), or weaker than *min_tier*. Side = the board's
    higher-EV best_side; taken decimal reconstructed from ev_side + model_prob."""
    if not isinstance(edge, dict):
        return None
    if str(edge.get("edge_basis") or "") != "ev_vs_priced":
        return None  # model-only -> no price -> not placeable
    side = str(edge.get("best_side") or edge.get("side") or "").strip().lower()
    if side not in ("over", "under"):
        return None
    p_over = _f(edge.get("model_p_over"))
    if p_over is None or not (0.0 <= p_over <= 1.0):
        return None
    model_prob = p_over if side == "over" else round(1.0 - p_over, 6)
    ev = _f(edge.get("ev_over") if side == "over" else edge.get("ev_under"))
    market_prob = _f(edge.get("fair_over") if side == "over" else edge.get("fair_under"))
    if ev is None or model_prob <= 0.0:
        return None
    taken_decimal = round((ev + 1.0) / model_prob, 6)  # raw vig-inclusive line
    if taken_decimal <= 1.0:
        return None

    from scripts.platformkit.pm_trading import policy as _policy
    tier = _policy.tier(ev=ev, model_prob=model_prob, market_prob=market_prob,
                        clv_is_proxy=True)
    if tier is None:
        return None  # below the proxy-adjusted EV floor -> NO bet (honest)
    if min_tier is not None and _TIER_RANK.get(str(tier), 9) > _TIER_RANK.get(str(min_tier), -1):
        return None  # weaker than the discipline floor -> skip the marginal pick
    stakes = _policy.stake_units(ev=ev, model_prob=model_prob,
                                 taken_decimal=taken_decimal, tier=tier,
                                 clv_is_proxy=True)

    player = str(edge.get("player") or edge.get("matched_name") or "").strip()
    stat = str(edge.get("stat") or "").strip()
    if not player or not stat:
        return None
    line = edge.get("line")
    book = str(edge.get("source") or "prop").strip().lower() or "prop"
    market = "prop|%s|%s|%s|%s" % (player, stat, line, side)
    day = today or _today_et()
    return {
        "sport": sport,
        "matchup": str(edge.get("match") or ""),
        "ledger_side": "home" if side == "over" else "away",  # binary-leg encoding
        "prop_side": side,
        "prop_player": player,
        "prop_stat": stat,
        "line": line,
        "taken_book": book,
        "taken_decimal": taken_decimal,
        "model_prob": round(model_prob, 6),
        "market_prob": (round(market_prob, 6) if market_prob is not None else None),
        "ev": round(ev, 6),
        "tier": tier,
        "flat_unit": float(stakes["flat_unit"]),
        "quarter_kelly": float(stakes["quarter_kelly"]),
        "market": market,
        # date in the bet_id -> idempotent WITHIN a day, but a new slate day re-places
        # the same player/stat/line as a fresh position (one prop position per day).
        "bet_id": "prop|%s|%s|%s|%s|%s|%s|%s" % (day, sport, player, stat, line, side, book),
        "game_date": day,
    }


def _ledger_row(p: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical OPEN prop ledger row from a placement. UNITS only; no $ key."""
    edge_vs_market = None
    if p.get("market_prob") is not None:
        edge_vs_market = round(float(p["model_prob"]) - float(p["market_prob"]), 6)
    return {
        "ts": _now_iso(),
        "sport": str(p["sport"]),
        "matchup": str(p.get("matchup") or ""),
        "side": p["ledger_side"],
        "taken_book": str(p["taken_book"]),
        "taken_decimal": float(p["taken_decimal"]),
        "model_prob": float(p["model_prob"]),
        "stake_units": float(p["flat_unit"]),
        "quarter_kelly": float(p["quarter_kelly"]),
        "status": "open",
        "executed": False,
        "channel": "paper",
        "is_pm": False,
        "market": str(p["market"]),
        "market_type": "prop",
        "prop_player": str(p["prop_player"]),
        "prop_stat": str(p["prop_stat"]),
        "prop_side": str(p["prop_side"]),
        "line": p.get("line"),
        "tier": str(p["tier"]),
        "market_prob": p.get("market_prob"),
        "edge": edge_vs_market,
        "clv_is_proxy": True,
        "clv_status": "INSUFFICIENT_DATA",
        "game_date": str(p["game_date"]),
        "edge_claimed": False,
        "bet_id": str(p["bet_id"]),
        "exec_gate": p.get("exec_gate"),
        "signal_ts": p.get("signal_ts"),
        "placement_latency_ms": p.get("placement_latency_ms"),
    }


def _existing_bet_ids(rows: List[Dict[str, Any]]) -> set:
    return {str(r.get("bet_id")) for r in rows if r.get("bet_id")}


def _append(row: Dict[str, Any], ledger_path: Path) -> bool:
    try:
        from scripts.platformkit.clv_ledger_io import append_row as _ar
        _ar(row, path=ledger_path)
        return True
    except Exception:  # noqa: BLE001
        try:
            import json
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
            return True
        except Exception as exc2:  # noqa: BLE001
            logger.debug("props_paper_placer: append failed: %s", exc2)
            return False


def _board_edges(sport: str, board_fn: Callable[[str], Any],
                 *, calibration_only: bool = False) -> List[Dict[str, Any]]:
    """Priced + reliable edges from the sport's prop board; [] on any failure.

    *calibration_only* also drops (sport, stat) pairs whose calibration is NOT
    proven -- concentrates stake on families we've earned the right to bet."""
    try:
        board = board_fn(sport)
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_paper_placer: board(%s) failed: %s", sport, exc)
        return []
    if not isinstance(board, dict) or not str(board.get("status", "")).startswith("ok"):
        return []
    proven = None
    if calibration_only:
        from scripts.platformkit.bestbets.calibration_gate import proven_families
        proven = proven_families()
    out: List[Dict[str, Any]] = []
    for e in board.get("edges") or []:
        if not isinstance(e, dict):
            continue
        # discipline: only reliable + ev_flag ok edges are placeable (mirror prop_cards).
        if not bool(e.get("reliable")) or str(e.get("ev_flag", "")) != "ok":
            continue
        # honesty: never stake a prop ungradeable from a keyless feed (would pend forever).
        if not _is_settleable(sport, e.get("stat")):
            continue
        # smarter selection: stake pregame props only where calibration is PROVEN.
        if calibration_only:
            from scripts.platformkit.bestbets.calibration_gate import is_calibration_proven
            if not is_calibration_proven(sport, str(e.get("stat") or ""), proven=proven):
                continue
        out.append(e)
    return out


def run(sports: Sequence[str] = DEFAULT_PROP_SPORTS, *,
        ledger_path: Optional[Path] = None,
        board_fn: Optional[Callable[[str], Any]] = None,
        place: bool = True,
        max_per_sport: Optional[int] = None,
        min_tier: Optional[str] = None,
        calibration_only: bool = False,
        today: Optional[str] = None) -> Dict[str, Any]:
    """Place priced prop bets for each sport into the unified ledger. Never raises.

    Idempotent (bet_id dedup). *place*=False computes but does not write (dry run).
    *max_per_sport* caps NEW placements per sport (highest-EV first, overflow counted
    in by_sport["capped"]); None = no cap. Returns an honest summary (UNITS, no $).
    """
    _ledger = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    _board = board_fn
    if _board is None:
        from scripts.platformkit.prop_edge import build_prop_board as _bpb
        _board = _bpb
    _today = today or _today_et()
    ledger_rows = _exec.load_ledger_rows(_ledger) if place else []
    seen = _existing_bet_ids(ledger_rows) if place else set()

    by_sport: Dict[str, Dict[str, int]] = {}
    placed: List[str] = []
    n_edges = n_priced = n_placed = n_dup = n_capped = 0
    for sport in sports:
        edges = _board_edges(sport, _board, calibration_only=calibration_only)
        n_edges += len(edges)
        # (edge, placement) pairs -- edge kept for the exec gate; highest-EV first.
        cands = [(p, e) for e in edges
                 if (p := placement_from_edge(e, sport, today=_today, min_tier=min_tier))
                 is not None]
        cands.sort(key=lambda c: float(c[0].get("ev", 0.0)), reverse=True)
        s_priced = len(cands)
        n_priced += s_priced
        s_placed = s_dup = s_capped = 0
        for p, e in cands:
            if p["bet_id"] in seen:
                s_dup += 1
                n_dup += 1
                continue
            if max_per_sport is not None and s_placed >= max_per_sport:
                s_capped += 1
                n_capped += 1
                continue
            if place:
                if _best_exec_on():
                    p = _exec.gate_and_stamp(p, e, sport, ledger_rows)
                    if p is None:
                        continue
                if _append(_ledger_row(p), _ledger):
                    seen.add(p["bet_id"])
                    placed.append(p["market"])
                    s_placed += 1
                    n_placed += 1
            else:
                placed.append(p["market"])
                s_placed += 1
                n_placed += 1
        by_sport[sport] = {"edges": len(edges), "priced_tiered": s_priced,
                           "placed": s_placed, "dup_skipped": s_dup,
                           "capped": s_capped}

    return {
        "ts": _now_iso(),
        "n_edges": n_edges,
        "n_priced_tiered": n_priced,
        "n_placed": n_placed,
        "n_dup_skipped": n_dup,
        "n_capped": n_capped,
        "by_sport": by_sport,
        "placed_markets": placed,
        "place": bool(place),
        "executed": False,
        "edge_claimed": False,
        "honest_note": _HONEST_NOTE,
    }


def _main() -> int:  # pragma: no cover
    import argparse
    import json as _json
    ap = argparse.ArgumentParser(
        description="Paper-place PRICED player props into the unified units ledger.")
    ap.add_argument("--max-per-sport", type=int, default=5,
                    help="Cap NEW placements per sport (highest-EV first). 0 = no cap.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute placements but do NOT write to the ledger.")
    ap.add_argument("--sports", default=",".join(DEFAULT_PROP_SPORTS),
                    help="Comma-separated sports (default: %(default)s).")
    a = ap.parse_args()
    cap = None if a.max_per_sport == 0 else a.max_per_sport
    out = run(tuple(s.strip() for s in a.sports.split(",") if s.strip()),
              place=not a.dry_run, max_per_sport=cap)
    print(_json.dumps({k: out[k] for k in (
        "n_edges", "n_priced_tiered", "n_placed", "n_dup_skipped", "n_capped",
        "by_sport", "place")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["DEFAULT_PROP_SPORTS", "placement_from_edge", "run"]
