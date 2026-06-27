"""tests.platformkit.improve.test_settle_audit -- MF3 anti-0-fill tripwire.

Asserts the contract from the autonomy plan (risk-register A, GAP D/E):
  * a batch with one empty-states game + one all-zero-outcome game -> BOTH
    quarantined, the clean set EXCLUDES them, and a provenance reason is present;
  * an all-bad batch raises FeedDegradedError (dead feed -> NO_CANDIDATE, never 0-fill);
  * a missing outcome label is NEVER 0-filled into a clean/neutral observation.

Per-file test only (full pytest freezes the box). ASCII; stdlib-only deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve.settle_audit import (  # noqa: E402
    audit_settled, AuditSummary, FeedDegradedError,
    R_EMPTY_STATES, R_MISSING_OUTCOME, R_ALL_ZERO_OUTCOME,
)


# --------------------------------------------------------------------------- #
# Builders for canonical-schema settled games.                                #
# {sport, game_id, asof_idx, state_diff, frac_elapsed, p0, outcome}.          #
# --------------------------------------------------------------------------- #
def _state(outcome, *, idx=0, diff=3.0, frac=0.5, p0=0.55):
    s = {"sport": "nba", "game_id": "g", "asof_idx": idx,
         "state_diff": diff, "frac_elapsed": frac, "p0": p0}
    if outcome is not None:
        s["outcome"] = outcome
    return s


def _good_game(gid, label=1.0):
    """A foldable game: real state rows, at least one confirmed-positive outcome."""
    return {"sport": "nba", "game_id": gid, "outcome": label,
            "states": [_state(1.0, idx=0), _state(1.0, idx=1)]}


def _empty_states_game(gid):
    """FINAL per ESPN but ingest produced NO usable state rows."""
    return {"sport": "nba", "game_id": gid, "outcome": 1.0, "states": []}


def _all_zero_outcome_game(gid):
    """Every state outcome 0 AND no confirmed-positive game label -- indistinguishable
    from a 0-fill of a missing label, so it must be quarantined, never folded."""
    return {"sport": "nba", "game_id": gid, "outcome": 0.0,
            "states": [_state(0.0, idx=0), _state(0.0, idx=1)]}


def _missing_label_game(gid):
    """No game-level label AND no per-state label -> must NOT be 0-filled to clean."""
    return {"sport": "nba", "game_id": gid,
            "states": [_state(None, idx=0), _state(None, idx=1)]}


# --------------------------------------------------------------------------- #
# 1. one empty-states + one all-zero-outcome -> both quarantined, clean excl. #
# --------------------------------------------------------------------------- #
def test_empty_and_all_zero_both_quarantined_with_reasons():
    empty = _empty_states_game("EMPTY")
    allzero = _all_zero_outcome_game("ALLZERO")
    good = _good_game("GOOD")
    # 1 bad-empty + 1 bad-zero + 3 good -> frac 2/5 = 0.4 < 0.5, no degrade raise.
    batch = [empty, allzero, good, _good_game("GOOD2"), _good_game("GOOD3")]

    summary = audit_settled(batch)
    assert isinstance(summary, AuditSummary)

    # The clean set EXCLUDES both bad games.
    clean_ids = {g["game_id"] for g in summary.clean_games}
    assert "EMPTY" not in clean_ids
    assert "ALLZERO" not in clean_ids
    assert {"GOOD", "GOOD2", "GOOD3"} <= clean_ids
    assert summary.n_clean == 3
    assert summary.n_quarantined == 2

    # Provenance reason present + correct for each quarantined game.
    by_id = {g["game_id"]: reason for g, reason in summary.quarantined}
    assert by_id["EMPTY"] == R_EMPTY_STATES
    assert by_id["ALLZERO"] == R_ALL_ZERO_OUTCOME
    assert all(r for _, r in summary.quarantined)  # non-empty reason strings


# --------------------------------------------------------------------------- #
# 2. all-bad batch -> FeedDegradedError (dead feed, never 0-fill).            #
# --------------------------------------------------------------------------- #
def test_all_bad_batch_raises_feed_degraded():
    batch = [_empty_states_game("E1"), _all_zero_outcome_game("Z1"),
             _missing_label_game("M1")]
    with pytest.raises(FeedDegradedError) as exc:
        audit_settled(batch)
    # Carries the summary; nothing clean survived; never 0-filled.
    assert exc.value.summary.n_clean == 0
    assert exc.value.summary.n_quarantined == 3
    assert exc.value.summary.degraded is True


def test_degraded_summary_when_not_raising():
    batch = [_empty_states_game("E1"), _all_zero_outcome_game("Z1")]
    summary = audit_settled(batch, raise_on_degraded=False)
    assert summary.degraded is True
    assert summary.n_clean == 0
    assert summary.quarantine_fraction == 1.0


# --------------------------------------------------------------------------- #
# 3. a missing outcome label is NEVER 0-filled into a clean observation.      #
# --------------------------------------------------------------------------- #
def test_missing_label_quarantined_not_zero_filled():
    # majority-good so no degrade raise; the lone missing-label game must quarantine.
    batch = [_missing_label_game("MISS"),
             _good_game("G1"), _good_game("G2"), _good_game("G3")]
    summary = audit_settled(batch)
    clean_ids = {g["game_id"] for g in summary.clean_games}
    assert "MISS" not in clean_ids
    by_id = {g["game_id"]: reason for g, reason in summary.quarantined}
    assert by_id["MISS"] == R_MISSING_OUTCOME


def test_present_zero_label_is_not_treated_as_absent():
    # A genuine all-loss game (outcome present == 0) is STILL quarantined because we
    # cannot distinguish it from a 0-fill -- the conservative, no-fabrication choice.
    g = _all_zero_outcome_game("ZERO")
    summary = audit_settled([g, _good_game("A"), _good_game("B")])
    by_id = {gg["game_id"]: r for gg, r in summary.quarantined}
    assert by_id["ZERO"] == R_ALL_ZERO_OUTCOME


# --------------------------------------------------------------------------- #
# 4. all-clean batch folds through untouched; empty batch is a no-op.         #
# --------------------------------------------------------------------------- #
def test_all_clean_batch_folds_through():
    batch = [_good_game("A"), _good_game("B")]
    summary = audit_settled(batch)
    assert summary.n_quarantined == 0
    assert summary.n_clean == 2
    assert summary.degraded is False
    assert [g["game_id"] for g in summary.clean_games] == ["A", "B"]


def test_empty_batch_is_noop_not_degraded():
    summary = audit_settled([])
    assert summary.n_total == 0
    assert summary.n_clean == 0
    assert summary.degraded is False
    assert summary.quarantine_fraction == 0.0


def test_structured_summary_dict_has_no_dollar_fields():
    summary = audit_settled([_good_game("A")])
    d = summary.to_dict()
    for k in d:
        assert not any(tok in k.lower() for tok in ("roi", "pnl", "dollar", "edge"))
    assert "calibration" in d["note"]
