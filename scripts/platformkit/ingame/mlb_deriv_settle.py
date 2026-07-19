"""scripts.platformkit.ingame.mlb_deriv_settle -- settlement for the MLB in-play
totals/run-line derivative channel (inplay_derivative_mlb.py's sibling; split out
to keep both files under the platform's <=300 LOC/file rail).

NEW LOGIC (not reused from grade_paper_one._outcome): that helper is a HOME/AWAY
MONEYLINE comparator (side vs which team scored more) and does not fit a
total-runs-vs-line or run-line-cover outcome, so this module implements its own
total/spread comparator. It DOES reuse the FINAL-score fetch (settled_finals) and
the pure unit-result math (grade_paper_one._unit_result -- outcome/taken_decimal/
stake only, sport-agnostic).

LEDGER SIDE CONVENTION (binding, mirrors mlb_deriv_align.ledger_side): side=="home"
means over (total) / home-team-favorite (spread); side=="away" means under / away-
dog. `market` (e.g. "total_8.5_over") carries the real proposition; this module
parses it back out to decide win/loss/push.

PUSH: an INTEGER total line landing exactly on the final total voids the bet
(unit_result=0.0, outcome="push"); the repricer's run-line (always the half-integer
1.5) can never push.

HONEST: no independent proxy-close feed is captured for this channel yet, so every
settled row is clv_pct=None / clv_status="no_close" (win/loss only, CLV genuinely
unavailable) -- never fabricated. Paper only; executed always False.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only.
Per-file test: see tests/platformkit/ingame/test_inplay_derivative_mlb.py.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.ingame import mlb_deriv_align as _align

logger = logging.getLogger(__name__)

SPORT = "mlb"
CHANNEL = "paper_ingame"

FinalsFn = Callable[[str], List[Dict[str, Any]]]


def _default_finals(sport: str) -> List[Dict[str, Any]]:
    try:
        from scripts.platformkit.ingame import settled_finals as _sf
        return list(_sf.settled_since(sport))
    except Exception as exc:  # noqa: BLE001
        logger.warning("mlb_deriv_settle finals failed: %s", exc)
        return []


def settle_outcome(market: str, side: str, home_score: int, away_score: int
                   ) -> Optional[str]:
    """win|loss|push for ONE settled total/spread derivative bet. None if `market`
    is unparseable (never fabricated)."""
    parts = str(market).split("_")
    if len(parts) < 3 or parts[0] not in ("total", "spread"):
        return None
    try:
        line = float(parts[1])
    except (TypeError, ValueError):
        return None
    if parts[0] == "total":
        total = int(home_score) + int(away_score)
        if total == line:
            return "push"
        over_wins = total > line
        want_over = side == "home"  # ledger_side convention: over -> "home"
        return "win" if (over_wins == want_over) else "loss"
    diff = int(home_score) - int(away_score)
    home_covers = diff >= 2
    want_home_favorite = side == "home"  # ledger_side convention: home_favorite -> "home"
    return "win" if (home_covers == want_home_favorite) else "loss"


def _team_names_for_game(gid: str, grade_dir: Path) -> tuple:
    """Best-effort (home, away) display names for *gid*, read off this channel's OWN
    capture history (state_summary, written every tick regardless of gate outcome).
    ("", "") if no capture history exists yet -- never fabricated."""
    home, away = "", ""
    path = _lg._grade_path(SPORT, gid, grade_dir)
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            ss = row.get("state_summary") or {}
            if ss.get("home") and ss.get("away"):
                home, away = str(ss["home"]), str(ss["away"])
    except Exception:  # noqa: BLE001 -- no capture history -> can't settle this pass
        pass
    return home, away


def _match_final(home: str, away: str, finals: List[Dict[str, Any]]
                 ) -> Optional[Dict[str, Any]]:
    for g in finals:
        gh, ga = str(g.get("home") or ""), str(g.get("away") or "")
        if (home and away and _align._name_match(home, gh) and _align._name_match(away, ga)
                and g.get("home_score") is not None and g.get("away_score") is not None):
            return g
    return None


def settle_open_bets(*, ledger_path: Optional[Path] = None,
                     grade_dir: Optional[Path] = None,
                     finals_fn: Optional[FinalsFn] = None,
                     now: Optional[datetime] = None) -> Dict[str, Any]:
    """Settle every OPEN paper_ingame derivative (total_*/spread_*) MLB bet whose
    game is FINAL. Idempotent (skips an edge_key already settled). Never raises."""
    from scripts.platformkit import clv_ledger as _clv
    from scripts.platformkit.grade_paper_one import _unit_result

    fin_fn = finals_fn or _default_finals
    target = Path(ledger_path) if ledger_path is not None else _clv.DEFAULT_LEDGER
    base = Path(grade_dir) if grade_dir is not None else (
        Path(__file__).resolve().parents[3] / "data" / "cache" / "ingame_grade_deriv")
    nowdt = now or datetime.now(timezone.utc)
    n_settled = n_pending = 0
    try:
        rows = _clv.load_ledger(target)
    except Exception:  # noqa: BLE001 -- unreadable ledger -> nothing to settle this pass
        rows = []
    already = {r.get("edge_key") for r in rows
              if r.get("channel") == CHANNEL and r.get("status") == "settled"}
    open_deriv = [r for r in rows if r.get("channel") == CHANNEL
                 and r.get("status") == "open" and str(r.get("sport")) == SPORT
                 and str(r.get("market", "")).split("_")[0] in ("total", "spread")
                 and r.get("edge_key") not in already]
    if not open_deriv:
        return {"n_settled": 0, "n_pending": 0}
    try:
        finals = fin_fn(SPORT)
    except Exception:  # noqa: BLE001
        finals = []
    for bet in open_deriv:
        home, away = _team_names_for_game(str(bet.get("game_id") or ""), base)
        game = _match_final(home, away, finals)
        if game is None:
            n_pending += 1
            continue
        outcome = settle_outcome(str(bet.get("market")), str(bet.get("side")),
                                 int(game["home_score"]), int(game["away_score"]))
        if outcome is None:
            n_pending += 1
            continue
        settled = dict(bet)
        settled.update({
            "status": "settled", "settled_at": nowdt.isoformat(), "outcome": outcome,
            "home_score": int(game["home_score"]), "away_score": int(game["away_score"]),
            "unit_result": _unit_result(outcome, float(bet.get("taken_decimal", 1.0)),
                                        float(bet.get("stake", 0.0) or 0.0)),
            "executed": False, "clv_pct": None, "clv_is_proxy": True,
            "clv_status": "no_close",
            "clv_note": "derivative channel: no independent proxy-close feed captured",
            "settle_key": bet.get("edge_key"), "bet_id": bet.get("edge_key"),
        })
        _clv.append_settlement(settled, path=target)
        n_settled += 1
    return {"n_settled": n_settled, "n_pending": n_pending}


__all__ = ["settle_outcome", "settle_open_bets"]
