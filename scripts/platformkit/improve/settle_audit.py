"""scripts.platformkit.improve.settle_audit -- the anti-0-fill tripwire (MF3).

The recalibrator folds newly-SETTLED games into a calibration candidate. A settled
game that ESPN reports FINAL but for which our ingest produced NO clean in-game
states, or NO real outcome label, is a TRAP: if such a game is folded, a missing
outcome silently becomes a neutral/favorable 0 and a real ESPN final is scored as a
(fabricated) observation -- "a count, never a win" (PLAN risk-register A, GAP D/E).

This module is the tripwire that MUST run BEFORE the recalibrator folds anything:

  audit_settled(games) -> AuditSummary
      QUARANTINES (never folds, never scores) any game that is
        * empty-states            -- no usable in-game state rows at all
        * all-zero/absent-outcome -- every state row's outcome is 0/absent (a dead
                                      ingest 0-filling a missing label looks exactly
                                      like a legitimate all-loss game; we refuse to
                                      assume -- if NOTHING is a confirmed 1 AND the
                                      game-level outcome label is absent, quarantine)
        * missing-outcome-label   -- the game-level final outcome is absent/None
      and returns (clean_games, quarantined_with_reason) plus batch counts. A
      provenance REASON string accompanies every quarantined game.

  A batch-level FeedDegradedError is raised when the quarantined FRACTION exceeds a
  threshold, so a DEAD settled feed degrades the whole cycle to NO_CANDIDATE + a
  status row -- it NEVER 0-fills a single missing outcome into a neutral observation.

INVARIANT (the one this module exists to enforce): NEVER 0-fill a missing outcome
into a neutral/favorable observation. Absent != 0. When in doubt, QUARANTINE.

Other invariants: never edits MEMORY.md, never writes data/registry/, never flips a
flag; calibration not edge (no $/ROI). Stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# A game is "degraded-feed" suspect when this fraction of the batch is quarantined.
DEFAULT_DEGRADE_FRACTION = 0.5

# Reason codes (provenance) -- stable strings sealed alongside each quarantined game.
R_EMPTY_STATES = "empty_states"
R_MISSING_OUTCOME = "missing_outcome_label"
R_ALL_ZERO_OUTCOME = "all_zero_or_absent_outcome"


class FeedDegradedError(Exception):
    """Raised when the quarantine fraction of a settled batch exceeds the threshold.

    Signals a DEAD / degraded settled feed: the caller must surface NO_CANDIDATE + a
    DEGRADED status, NEVER 0-fill the missing outcomes. Carries the audit summary so
    the daemon can log the exact quarantine reasons without re-auditing.
    """

    def __init__(self, message: str, summary: "AuditSummary") -> None:
        super().__init__(message)
        self.summary = summary


@dataclass
class AuditSummary:
    """Structured result of auditing one settled batch (no $/ROI -- counts only)."""

    clean_games: List[Dict[str, Any]] = field(default_factory=list)
    quarantined: List[Tuple[Dict[str, Any], str]] = field(default_factory=list)
    n_total: int = 0
    n_clean: int = 0
    n_quarantined: int = 0
    quarantine_fraction: float = 0.0
    degraded: bool = False
    note: str = "calibration, not edge; quarantine never scores a missing outcome"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_total": self.n_total,
            "n_clean": self.n_clean,
            "n_quarantined": self.n_quarantined,
            "quarantine_fraction": round(self.quarantine_fraction, 6),
            "degraded": self.degraded,
            "reasons": [r for _, r in self.quarantined],
            "note": self.note,
        }


def _states_of(game: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The game's in-game state rows. Tolerant of a few shape aliases; never raises."""
    for key in ("states", "state_rows", "rows"):
        val = game.get(key)
        if isinstance(val, list):
            return [s for s in val if isinstance(s, dict)]
    return []


def _has_outcome(value: Any) -> bool:
    """True iff `value` is a usable {0,1}-style outcome label (NOT absent, NOT None).

    Absent / None / non-numeric -> False (NEVER coerced to 0 -- that is the bug this
    whole module exists to forbid). 0.0 and 1.0 are both *present* labels.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def _outcome_is_one(value: Any) -> bool:
    """True iff a present outcome label is a confirmed positive (==1)."""
    if not _has_outcome(value):
        return False
    try:
        return float(value) == 1.0
    except (TypeError, ValueError):
        return False


def _classify(game: Dict[str, Any]) -> Optional[str]:
    """Return a quarantine REASON code, or None when the game is clean to fold.

    Quarantine when:
      * no usable state rows (empty-states);
      * the game-level outcome label is absent (missing-outcome-label);
      * every state row's outcome is absent OR zero AND the game label is not a
        confirmed positive -- i.e. NOTHING in the game is a verified 1, so folding it
        would 0-fill the whole game into all-loss observations on a feed that may
        simply have failed to attach labels. Absent != 0; when in doubt, quarantine.
    """
    states = _states_of(game)
    if not states:
        return R_EMPTY_STATES

    # Game-level outcome label (the final result). 'outcome' is canonical; accept a
    # couple of aliases but NEVER default a missing one to 0.
    game_label = game.get("outcome", game.get("final_outcome", game.get("y")))
    game_label_present = _has_outcome(game_label)
    game_label_one = _outcome_is_one(game_label)

    any_state_outcome_present = any(_has_outcome(s.get("outcome")) for s in states)
    any_state_outcome_one = any(_outcome_is_one(s.get("outcome")) for s in states)

    # Missing the outcome label entirely: no game-level label AND no per-state label.
    if not game_label_present and not any_state_outcome_present:
        return R_MISSING_OUTCOME

    # PROVENANCE escape hatch: a label explicitly flagged CONFIRMED (e.g. derived from the
    # realized FINAL score by the settled-ingest reconstructor) is a REAL observation -- a
    # genuine home-loss (outcome==0) is NOT a 0-fill. We trust it iff the label is PRESENT
    # (absent is still quarantined below -- the anti-0-fill invariant stays intact: only a
    # present, confirmed label clears the all-zero guard).
    confirmed = bool(game.get("outcome_confirmed")) or any(
        bool(s.get("outcome_confirmed")) for s in states)
    if confirmed and (game_label_present or any_state_outcome_present):
        return None

    # All-zero / absent outcome: nothing in the game is a confirmed positive AND the
    # game-level label is not a confirmed positive. A genuine all-loss game that the
    # ingest actually labelled (without provenance) still trips this -- by design we refuse
    # to fold a batch we cannot distinguish from a 0-fill, rather than fabricate observations.
    if not any_state_outcome_one and not game_label_one:
        return R_ALL_ZERO_OUTCOME

    return None


def audit_settled(games: Sequence[Dict[str, Any]],
                  *, degrade_fraction: float = DEFAULT_DEGRADE_FRACTION,
                  raise_on_degraded: bool = True) -> AuditSummary:
    """Audit a settled batch; quarantine unfoldable games; never 0-fill a missing label.

    Returns an AuditSummary whose ``clean_games`` EXCLUDES every quarantined game and
    whose ``quarantined`` carries (game, reason) provenance pairs. When the quarantine
    fraction exceeds ``degrade_fraction`` the feed is treated as DEGRADED: by default
    a FeedDegradedError is raised (caller -> NO_CANDIDATE + DEGRADED status); pass
    ``raise_on_degraded=False`` to get the summary with ``degraded=True`` instead.

    NEVER raises for any reason other than FeedDegradedError; a malformed game is
    quarantined, not crashed on.
    """
    games_list = [g for g in (games or []) if isinstance(g, dict)]
    clean: List[Dict[str, Any]] = []
    quarantined: List[Tuple[Dict[str, Any], str]] = []

    for game in games_list:
        try:
            reason = _classify(game)
        except Exception:  # noqa: BLE001 -- a malformed game is quarantined, not fatal
            reason = R_EMPTY_STATES
        if reason is None:
            clean.append(game)
        else:
            quarantined.append((game, reason))

    n_total = len(games_list)
    n_quar = len(quarantined)
    frac = (n_quar / n_total) if n_total else 0.0
    degraded = n_total > 0 and frac > float(degrade_fraction)

    summary = AuditSummary(
        clean_games=clean, quarantined=quarantined,
        n_total=n_total, n_clean=len(clean), n_quarantined=n_quar,
        quarantine_fraction=frac, degraded=degraded,
    )

    if degraded and raise_on_degraded:
        raise FeedDegradedError(
            "settled feed degraded: %d/%d games quarantined (frac %.3f > %.3f) -- "
            "NO_CANDIDATE, never 0-fill" % (n_quar, n_total, frac, degrade_fraction),
            summary)
    return summary


__all__ = [
    "audit_settled", "AuditSummary", "FeedDegradedError",
    "DEFAULT_DEGRADE_FRACTION",
    "R_EMPTY_STATES", "R_MISSING_OUTCOME", "R_ALL_ZERO_OUTCOME",
]
