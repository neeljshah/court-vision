"""scripts.platformkit.ingame.inplay_status -- "is the live in-play engine making bets
RIGHT NOW, and if not WHY?" -- a human-readable read-out over the capture heartbeat.

The in-play capture loop (inplay_capture_loop) already writes a heartbeat envelope every
tick: per live game it records whether a (model, price) pair was captured, whether a paper
bet was placed, and the REASON a game did not bet. This module turns that envelope into a
one-glance answer to the recurring question "is it betting the World Cup / live slate?"
WITHOUT re-deciding anything -- it is a pure read-out.

It separates the honest reasons a game is not bet:
  * not live yet   (no_live_state)        -- a FUTURE / pregame market on the book (Kalshi
    lists the next days' games; correct to skip until kickoff).
  * live, no model (no_model_prob)        -- in progress but no live model number resolved.
  * live, no price (no_home_leg)          -- in progress but the liquid legs would not align
    to a home/away pair (never guess -> never a fake CLV).
  * live, no edge  (below_floor)          -- priced + paired but the model does not beat the
    devigged in-play price past the floor (the gate working, not a failure).
  * already in     (hold_existing)        -- one position per game/side/day; holding.
  * LIVE + BET     (ok / action=bet)      -- a paper UNIT bet was placed on the live game.

So a slate of mostly "not live yet" with a couple of "LIVE + BET" is the engine working
correctly -- it bets the games that are actually in progress, not every market on the book.

HONESTY (binding): read-out only. UNITS / paper -- no $; never executes; never decides or
places (it reads a heartbeat the measurement daemon already produced). ASCII; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/ingame/test_inplay_status.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Human label + ordering for each per-game reason emitted by the capture loop.
_REASON_LABEL = {
    "no_live_state": "not live yet (future/pregame on book)",
    "bridge_date_mismatch": "live game found, but it is a different date's game",
    "no_model_prob": "live, no model number resolved",
    "no_home_leg": "live, price legs would not align",
    "below_floor": "live, priced -- no edge past floor",
    "hold_existing": "already in position (holding)",
    "stale": "live, price feed stale",
    "illiquid": "live, market not liquid enough",
    "not_calibration_justified": "live, lean not gate-justified (noise)",
}


def _bet_category(game: Dict[str, Any]) -> str:
    """Canonical category for one heartbeat game row (bet vs the reason it didn't)."""
    if game.get("bet") or game.get("action") == "bet":
        return "LIVE + BET"
    reason = str(game.get("reason") or "")
    if reason in ("ok", "hold_existing"):
        # 'ok' without bet = captured + held / no new placement this tick.
        return "already in position (holding)" if game.get("paired") else "live, captured"
    return _REASON_LABEL.get(reason, reason or "unknown")


def summarize(heartbeat: Dict[str, Any]) -> Dict[str, Any]:
    """Pure read-out of a capture heartbeat: counts + the games actually bet. Never raises."""
    games: List[Dict[str, Any]] = list(heartbeat.get("games") or [])
    by_cat: Dict[str, int] = {}
    bets: List[Dict[str, Any]] = []
    for g in games:
        cat = _bet_category(g)
        by_cat[cat] = by_cat.get(cat, 0) + 1
        if cat == "LIVE + BET":
            bets.append({
                "sport": g.get("sport"), "game_id": g.get("game_id"),
                "tier": g.get("tier"), "model_prob": g.get("model_prob"),
                "devigged_price": g.get("devigged_price"),
            })
    return {
        "as_of": heartbeat.get("as_of"),
        "sports": heartbeat.get("sports"),
        "n_games_on_book": len(games),
        "n_live_paired": int(heartbeat.get("n_pairs") or 0),
        "n_bets": int(heartbeat.get("n_bets") or 0),
        "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
        "bets": bets,
        "edge_claimed": False,
        "executed": False,
    }


def render(summary: Dict[str, Any]) -> str:
    """ASCII render of the live in-play status read-out."""
    L: List[str] = []
    L.append("=" * 74)
    L.append("LIVE IN-PLAY ENGINE STATUS -- is it betting the live slate? (paper, units)")
    L.append("=" * 74)
    L.append("as_of=%s  sports=%s" % (summary.get("as_of"), summary.get("sports")))
    L.append("games on book=%d  live+paired=%d  BETS PLACED=%d"
             % (summary["n_games_on_book"], summary["n_live_paired"], summary["n_bets"]))
    L.append("")
    L.append("breakdown by status:")
    for cat, n in summary["by_category"].items():
        L.append("  %3d  %s" % (n, cat))
    if summary["bets"]:
        L.append("")
        L.append("BETS PLACED on live games (paper, UNITS only, no $):")
        for b in summary["bets"]:
            mp = b.get("model_prob")
            dp = b.get("devigged_price")
            L.append("  %s %-24s tier=%s model_p=%s vs in-play_fair=%s"
                     % (b.get("sport"), str(b.get("game_id"))[:24], b.get("tier"),
                        ("%.3f" % mp) if isinstance(mp, (int, float)) else "--",
                        ("%.3f" % dp) if isinstance(dp, (int, float)) else "--"))
    else:
        L.append("")
        L.append("NO bets this tick. If every game reads 'not live yet', the live slate is "
                 "empty right now -- the engine bets games IN PROGRESS, not future markets.")
    L.append("=" * 74)
    return "\n".join(L)


def load_heartbeat(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read the capture daemon's last heartbeat JSON (the supervised loop writes it). None
    if absent/unreadable -- the caller can then run a one-off poll. Never raises."""
    from scripts.platformkit.ingame.inplay_capture_loop import DEFAULT_HEARTBEAT
    target = Path(path) if path is not None else DEFAULT_HEARTBEAT
    try:
        if not target.is_file():
            return None
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- a missing/corrupt heartbeat is just "unknown"
        return None


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover -- thin CLI
    """Render the daemon's last heartbeat; if none exists, run ONE bounded measurement poll
    to a throwaway dir (so this read-out never pollutes the real ledger) and render that."""
    import argparse
    import tempfile
    ap = argparse.ArgumentParser(prog="inplay_status")
    ap.add_argument("--sports", default="soccer_intl,mlb")
    ap.add_argument("--poll", action="store_true",
                    help="force a fresh one-off measurement poll (throwaway ledger)")
    args = ap.parse_args(argv)
    hb = None if args.poll else load_heartbeat()
    if hb is None:
        from scripts.platformkit.ingame import inplay_capture_loop as _loop
        tmp = Path(tempfile.mkdtemp())
        hb = _loop.poll_once(
            sports=[s.strip() for s in args.sports.split(",") if s.strip()],
            grade_dir=tmp / "g", ledger_path=tmp / "l.jsonl",
            heartbeat_path=tmp / "hb.json")
    print(render(summarize(hb)))
    return 0


__all__ = ["summarize", "render", "load_heartbeat", "main"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
