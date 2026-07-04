"""domains.basketball_wnba.cdn_states_extract -- per-checkpoint states from a
backfilled CDN boxscore+playbyplay pair (see cdn_backfill.py).

WHY A SEPARATE MODULE FROM ingame_live_cdn.extract_state
----------------------------------------------------------
extract_state() reads a LIVE boxscore snapshot -- its in_bonus_*/foul_trouble_
flags fields are the CDN's OWN point-in-time truth. Once a game is Final, the
boxscore is a single END-OF-GAME snapshot: inBonus and players[].statistics.
foulsPersonal reflect the LAST moment of the game, not "as of end-Q1". This
module instead reconstructs three checkpoints (end_q1, half, end_q3) purely
from the immutable playbyplay action log (which DOES carry period/clock-
stamped history), replaying state forward the same way a live poller would
have seen it in real time. Score is exact (cumulative fields on every
action). Lineup and bonus/team-foul-count are DERIVED via replay, not read
directly off a field -- see honest-gap notes below.

CHECKPOINT DEFINITION: end_q1/half/end_q3 are read from each period's own
explicit actionType=="period", subType=="end" marker action (NOT merely the
last list entry with that period value -- fouls/subs can be logged with an
out-of-order timeActual relative to the period-end marker). Ground-truthed
against gameId 1022600149 this wave: period-1 end marker reports
scoreHome=22/scoreAway=19, matching the boxscore's periods[0].score=22 for a
manual cross-check.

HONEST GAPS (this wave, documented not fabricated):
  - lineup_home/lineup_away: reconstructed via boxscore starters (players[]
    with starter=="1") + chronological substitution-action replay up to the
    checkpoint's elapsed game-clock. If replay ever yields != 5 oncourt for a
    side, that side's lineup is None (same "honest None over fabricated 5th
    player" contract as ingame_live_cdn._oncourt_ids) -- never silently
    truncated/padded.
  - foul_trouble_flags: NOT reconstructed here. A completed game's boxscore
    only has END-OF-GAME cumulative personal fouls, so "fouls as of end-Q1"
    is not recoverable without a full free-throw/foul-action player-level
    replay this wave did not build; this field is omitted (not zero-filled).
  - in_bonus_home/in_bonus_away: a PROXY, not the CDN's own ground-truth flag.
    Computed as (team personal-foul-count within that period reaches
    BONUS_FOUL_THRESHOLD). This threshold is a documented convention for this
    proxy, not a claimed rule citation -- treat it as directional, gated the
    same as every other candidate covariate (see ingame_live_cdn.py's gate
    discipline note; this field is measurement-only, same restriction).

PROVENANCE: every row carries provenance="cdn_backfill" (VALIDATION corpus --
never pooled with a forward-only capture stream, per AUTONOMY_CHARTER).

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; pure functions
(no I/O in the extraction logic itself -- only load_backfilled_pair touches
disk); never raises (a malformed/missing input degrades one row, or one
field, to None -- never aborts the whole batch).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_cdn_states_extract.py -q
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import domains.basketball_wnba.cdn_backfill as _backfill_mod
from domains.basketball_wnba.cdn_backfill import game_dir
from domains.basketball_wnba.ingame_live_cdn import _run_last_3min

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
STATES_PATH = _REPO_ROOT / "data" / "domains" / "wnba" / "cdn_backfill_states.jsonl"

CHECKPOINTS = ("end_q1", "half", "end_q3")
_CHECKPOINT_PERIOD = {"end_q1": 1, "half": 2, "end_q3": 3}
BONUS_FOUL_THRESHOLD = 5  # team personal fouls within a period -- proxy, not a rule citation


def load_backfilled_pair(game_id: str) -> Optional[Dict[str, dict]]:
    """{'boxscore': ..., 'playbyplay': ...} for a backfilled game, or None if
    either file is absent/malformed (never raises)."""
    d = game_dir(game_id)
    out: Dict[str, dict] = {}
    for name in ("boxscore", "playbyplay"):
        p = d / f"{name}.json"
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        game = payload.get("game")
        if not isinstance(game, dict):
            return None
        out[name] = game
    return out


def _period_end_marker(actions: List[dict], period: int) -> Optional[dict]:
    """The explicit actionType=='period', subType=='end' action for *period*,
    or None if absent (game did not reach that period, or malformed feed).
    Ground-truthed against gameId 1022600149: each period's own 'end' marker
    (not merely the last list entry in that period, which can be a foul/sub
    logged with an out-of-order timestamp) carries the authoritative
    cumulative score at that exact boundary."""
    for a in actions:
        if isinstance(a, dict) and a.get("actionType") == "period" \
           and a.get("subType") == "end" and a.get("period") == period:
            return a
    return None


def _checkpoint_scores(actions: List[dict]) -> Dict[str, Dict[str, Optional[float]]]:
    """{'end_q1': {'home':.., 'away':..}, ...} from each period's own 'end'
    marker action. A period the game never reached yields None/None."""
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for cp, period in _CHECKPOINT_PERIOD.items():
        marker = _period_end_marker(actions, period)
        if marker is None:
            out[cp] = {"home": None, "away": None}
            continue
        try:
            out[cp] = {"home": float(marker.get("scoreHome")), "away": float(marker.get("scoreAway"))}
        except (TypeError, ValueError):
            out[cp] = {"home": None, "away": None}
    return out


def _team_fouls_in_period(actions: List[dict], team_id: Any, period: int) -> int:
    """Count of personal/shooting/offensive foul actions charged to team_id
    within exactly this period (team fouls reset each period)."""
    n = 0
    for a in actions:
        if not isinstance(a, dict) or a.get("period") != period:
            continue
        if a.get("actionType") != "foul":
            continue
        if a.get("subType") not in ("personal", "shooting", "offensive"):
            continue
        if a.get("teamId") == team_id:
            n += 1
    return n


def _lineup_at_checkpoint(box_game: dict, actions: List[dict], side: str, period: int
                           ) -> Optional[List[str]]:
    """Starters (boxscore players[].starter=='1') + chronological substitution
    replay through the END of *period*. None if the reconstructed oncourt set
    is ever not exactly 5 (honest gap, never fabricated)."""
    team = box_game.get(f"{side}Team") or {}
    team_id = team.get("teamId")
    players = team.get("players") or []
    oncourt = {str(p.get("personId")) for p in players
               if isinstance(p, dict) and str(p.get("starter")) == "1"}
    if len(oncourt) != 5:
        return None

    subs = [a for a in actions if isinstance(a, dict)
            and a.get("actionType") == "substitution"
            and a.get("teamId") == team_id
            and a.get("period") is not None and a.get("period") <= period]
    # actions are chronological in the feed; apply in order.
    for a in subs:
        pid = str(a.get("personId"))
        if a.get("subType") == "out":
            oncourt.discard(pid)
        elif a.get("subType") == "in":
            oncourt.add(pid)
    return sorted(oncourt) if len(oncourt) == 5 else None


def extract_checkpoint_states(game_id: str, box_game: dict, pbp_game: dict
                               ) -> List[Dict[str, Any]]:
    """box_game + pbp_game (as loaded by load_backfilled_pair) -> one row per
    checkpoint reached (end_q1/half/end_q3). A checkpoint the game never
    reached (should not happen for a Final game past period 3, but a
    truncated/malformed feed is handled honestly) is skipped, not fabricated.
    Pure function, no I/O. Never raises."""
    actions = pbp_game.get("actions") or []
    scores = _checkpoint_scores(actions)
    home_team = box_game.get("homeTeam") or {}
    away_team = box_game.get("awayTeam") or {}
    home_id, away_id = home_team.get("teamId"), away_team.get("teamId")

    rows: List[Dict[str, Any]] = []
    for cp in CHECKPOINTS:
        period = _CHECKPOINT_PERIOD[cp]
        sc = scores[cp]
        if sc["home"] is None or sc["away"] is None:
            continue  # game never reached this period (or malformed) -- skip, don't fake

        home_fouls = _team_fouls_in_period(actions, home_id, period)
        away_fouls = _team_fouls_in_period(actions, away_id, period)
        run = _run_last_3min(actions, period, 0.0)  # 0.0 remaining = end-of-period checkpoint

        rows.append({
            "game_id": str(game_id),
            "checkpoint": cp,
            "period": period,
            "score_home": sc["home"],
            "score_away": sc["away"],
            "team_fouls_home": home_fouls,
            "team_fouls_away": away_fouls,
            "in_bonus_home": home_fouls >= BONUS_FOUL_THRESHOLD,
            "in_bonus_away": away_fouls >= BONUS_FOUL_THRESHOLD,
            "lineup_home": _lineup_at_checkpoint(box_game, actions, "home", period),
            "lineup_away": _lineup_at_checkpoint(box_game, actions, "away", period),
            "run_last_3min": run,
            "foul_trouble_flags": None,  # honest gap -- see module docstring
            "provenance": "cdn_backfill",
        })
    return rows


def extract_and_append(game_id: str, out_path: Optional[Path] = None) -> int:
    """Load a backfilled game + append its checkpoint rows to *out_path*
    (default STATES_PATH). Returns rows written (0 if the pair is missing/
    malformed). Best-effort; never raises."""
    pair = load_backfilled_pair(game_id)
    if pair is None:
        return 0
    rows = extract_checkpoint_states(game_id, pair["boxscore"], pair["playbyplay"])
    if not rows:
        return 0
    path = out_path or STATES_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    except OSError as exc:
        logger.debug("extract_and_append write failed game=%s err=%s", game_id, exc)
        return 0
    return len(rows)


def run_extract_all(out_path: Optional[Path] = None) -> Dict[str, int]:
    """Walk every backfilled gameId under cdn_backfill.BACKFILL_DIR and append
    its checkpoint states. Returns {n_games, n_rows}. Reads BACKFILL_DIR via
    the module reference (not a name-imported copy) so tests can monkeypatch
    domains.basketball_wnba.cdn_backfill.BACKFILL_DIR and have it apply here."""
    backfill_dir = _backfill_mod.BACKFILL_DIR
    if not backfill_dir.exists():
        return {"n_games": 0, "n_rows": 0}
    n_games, n_rows = 0, 0
    for d in sorted(backfill_dir.iterdir()):
        if not d.is_dir():
            continue
        n = extract_and_append(d.name, out_path=out_path)
        if n:
            n_games += 1
            n_rows += n
    return {"n_games": n_games, "n_rows": n_rows}


def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    summary = run_extract_all()
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "load_backfilled_pair", "extract_checkpoint_states", "extract_and_append",
    "run_extract_all", "CHECKPOINTS", "BONUS_FOUL_THRESHOLD", "STATES_PATH",
]
