"""scripts.platformkit.ingame.settle_stamp -- settled-OUTCOME stamp for the grade store (W3).

THE GAP THIS CLOSES: inplay_aggregate_grade's OUTCOME arm needs a settled binary label
(home_win in {0,1}) on each game's grade rows; without it the pool stays
INSUFFICIENT_DATA FOREVER, no matter how many games are captured. This module stamps that
label ONCE, at FINAL, onto the per-game grade store:
  data/cache/ingame_grade/<sport>/<game_id>.jsonl

  stamp_final(sport, game_id, *, home_win=None, ev=None, grade_dir=None) -> dict
     Append ONE settle row {"sport","game_id","ts","settled":True,"home_win":0|1,...} to
     the game's grade file IFF the game is FINAL and not already stamped. home_win may be
     given directly (0/1) or derived from a FINAL ESPN event dict `ev` (final scores). If
     the game is not final / the outcome is unreadable, NOTHING is written (status='skipped').
     IDEMPOTENT: a second call for an already-stamped game is a no-op (status='already').

LEAK-FREE (binding): the outcome is a LABEL stamped ONLY at settle (ESPN FINAL). It is
NEVER a feature -- the captured model_prob / market_prob rows are written live, before the
outcome is known, and the aggregate grader scores them against this held-out label. The
final close tick is excluded from scoring upstream. We never infer a label from a non-final
score state (that would risk grading against a fabricated outcome).

REUSES live_grade's atomic append discipline + grade-path convention so the stamp row lands
in the SAME file the aggregate OUTCOME arm reads (_OUTCOME_KEYS includes 'home_win').
Also REUSES ingame_live_state._competitors/_score (the team-then-athlete / sets-won
fallback built for tennis) for a raw nested ESPN event, and handles the flat
settled_finals-style game dict (no 'competitions' key -- the real production `ev` shape)
directly off home_score/away_score. See _home_win_from_event for all three shapes.

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network
at import; no data/registry write, no flag flip, no autostart; never edits live_grade
(reuses its helpers) / inplay_aggregate_grade / odds_provider / predict_service / domains /
src / kernel.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_settle_stamp.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.ingame import ingame_live_state as _ls
from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.ingame import settled_finals as _sf

logger = logging.getLogger(__name__)


def _iso(now: Optional[datetime]) -> str:
    d = now if now is not None else datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _grade_path(sport: str, game_id: str, grade_dir: Optional[Path]) -> Path:
    base = Path(grade_dir) if grade_dir is not None else _lg.DEFAULT_GRADE_DIR
    return _lg._grade_path(sport, game_id, base)  # same convention the grader reads


def already_stamped(path: Path) -> bool:
    """True iff any row in the grade file already carries a settled home_win label.

    Idempotency guard: scans for a row with settled==True OR a home_win in {0,1}. Never
    raises (an unreadable / missing file -> not stamped).
    """
    if not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("settled") is True:
                    return True
                hw = rec.get("home_win")
                try:
                    if hw is not None and float(hw) in (0.0, 1.0):
                        return True
                except (TypeError, ValueError):
                    continue
    except Exception as exc:  # noqa: BLE001 -- unreadable file -> treat as not stamped
        logger.debug("already_stamped read failed %s: %s", path, exc)
    return False


def _home_win_from_flat_game(ev: Dict[str, Any]) -> Optional[float]:
    """Derive binary home_win from a FLAT settled_finals-style game dict, or None.

    inplay_capture_loop._stamp_final's production `ev` is actually
    settled_finals.settled_since's flat game shape {home,away,home_score,away_score,...}
    -- it carries NO 'competitions' key at all, so the raw-ESPN-event path below never
    matches it (any sport, not just tennis). This is the SAME direct-score shape as
    settled_finals._final_games_from_board already emits (home_score/away_score already
    resolved leak-free, including tennis' sets-won fallback there). Only used when the
    dict has no 'competitions' key, so byte-identical raw-ESPN-event behavior is
    unaffected. Never raises (called only from the guarded caller below).
    """
    try:
        hs = float(ev["home_score"])
        as_ = float(ev["away_score"])
    except (KeyError, TypeError, ValueError):
        return None
    if hs == as_:
        return None
    return 1.0 if hs > as_ else 0.0


def _home_win_from_event(ev: Dict[str, Any]) -> Optional[float]:
    """Derive binary home_win from a FINAL ESPN event dict, or None.

    Handles THREE shapes, byte-identical for the first (existing team-sport behavior
    unchanged):
      1. Raw flat ESPN event: {"competitions":[{"status":..., "competitors":[...]}]} with
         numeric .score fields (nba/mlb/soccer -- the ORIGINAL, unchanged code path).
      2. Tennis (and any sport) nested/athlete-shaped event: competitors carry .athlete
         instead of .team and NO numeric .score (only per-set .linescores + .winner) --
         REUSES ingame_live_state._competitors/_score (the wave-3 fix) so this module
         does not duplicate that team-then-athlete / sets-won fallback logic.
      3. Flat settled_finals-style game dict with no 'competitions' key at all (the
         REAL shape inplay_capture_loop._stamp_final passes as `ev` in production) --
         reads home_score/away_score directly (see _home_win_from_flat_game).

    Only returns a label when the event is FINAL (settled_finals._is_final, shape 1/2)
    AND both final scores are readable AND not a tie. A non-final / tied / unreadable
    event -> None (we never stamp a fabricated or premature label).
    """
    if not isinstance(ev, dict):
        return None
    if "competitions" not in ev:
        # shape 3: no nested competitions at all -- the settled_finals flat game dict.
        return _home_win_from_flat_game(ev)
    if not _sf._is_final(ev):
        return None
    home, away = _ls._competitors(ev)
    hs, as_ = _ls._score(home), _ls._score(away)
    if hs is None or as_ is None or hs == as_:
        return None
    return 1.0 if hs > as_ else 0.0


def _coerce_home_win(home_win: Any) -> Optional[float]:
    try:
        v = float(home_win)
    except (TypeError, ValueError):
        return None
    return v if v in (0.0, 1.0) else None


def stamp_final(sport: str, game_id: str, *,
                home_win: Optional[Any] = None,
                ev: Optional[Dict[str, Any]] = None,
                now: Optional[datetime] = None,
                grade_dir: Optional[Path] = None,
                close_source: Optional[str] = None) -> Dict[str, Any]:
    """Stamp the settled binary home_win label onto a game's grade file ONCE, at FINAL.

    The label comes from `home_win` (0/1) if given, else is derived from a FINAL ESPN event
    dict `ev`. If neither yields a {0,1} label (game not final / unreadable / tie) NOTHING is
    written (status='skipped'). IDEMPOTENT: an already-stamped game is a no-op
    (status='already'). On a fresh stamp, appends one settle row carrying 'home_win' (which
    inplay_aggregate_grade's OUTCOME arm reads) and 'settled':True. NEVER raises. Returns a
    summary dict; UNITS / label only -- no $ field, edge_claimed False, leak-free (label-only).

    *close_source* (ADDITIVE, shadow-grade-join gap fix): an optional provenance string for
    where the settled outcome/close-proxy came from (e.g. "ingame_outcome_label:
    espn_boxscores_parquet"). Recorded on the stamp row so a downstream join (probabilities
    from the tick rows + this row's home_win) can also cite where the label originated. A
    bare label call (no close_source) is byte-identical to the pre-existing row shape.
    """
    path = _grade_path(sport, game_id, grade_dir)
    summary: Dict[str, Any] = {
        "sport": str(sport).lower(), "game_id": str(game_id), "path": str(path),
        "status": "skipped", "home_win": None, "edge_claimed": False,
    }
    try:
        hw = _coerce_home_win(home_win) if home_win is not None else None
        if hw is None and ev is not None:
            hw = _home_win_from_event(ev)
        if hw is None:
            summary["reason"] = "no_settled_outcome"
            return summary
        if already_stamped(path):
            summary.update({"status": "already", "home_win": hw,
                            "reason": "idempotent_no_op"})
            return summary
        row = {
            "sport": str(sport).lower(), "game_id": str(game_id), "ts": _iso(now),
            "settled": True, "home_win": float(hw),
            "state_summary": "FINAL", "edge_claimed": False,
        }
        if close_source:
            row["close_source"] = str(close_source)
        _lg._append_atomic(path, json.dumps(row, ensure_ascii=True))
        summary.update({"status": "stamped", "home_win": float(hw)})
    except Exception as exc:  # noqa: BLE001 -- a stamp failure must never sink the loop
        logger.warning("stamp_final(%s/%s) failed: %s", sport, game_id, exc)
        summary["reason"] = "error: %s" % type(exc).__name__
    return summary


__all__ = ["already_stamped", "stamp_final"]
