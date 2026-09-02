"""Constructed four-case contract tests for forward claim primacy."""
from __future__ import annotations

from scripts.platformkit.eval_gate.claim_primacy import FORWARD, RETROSPECTIVE, primacy
from scripts.platformkit.ingame import forward_evidence_scoreboard as fes


def _series(value, verdict, settled_n=10, min_n=5):
    return {"value": value, "verdict": verdict, "settled_n": settled_n, "min_n": min_n}


def test_forward_ahead_agrees_with_retro():
    outcome = primacy(_series("forward", "AHEAD"), _series("retro", "AHEAD"))
    assert outcome["claim"] == "forward"
    assert outcome["provenance"] == FORWARD
    assert outcome["conflict"] is False


def test_forward_ahead_wins_when_retro_behind():
    retro = _series("retro", "BEHIND")
    outcome = primacy(_series("forward", "AHEAD"), retro)
    assert outcome["claim"] == "forward"
    assert outcome["provenance"] == FORWARD
    assert outcome["conflict"] is True
    assert outcome["retro"] == retro


def test_forward_behind_wins_when_retro_ahead():
    outcome = primacy(_series("forward", "BEHIND"), _series("retro", "AHEAD"))
    assert outcome["claim"] == "forward"
    assert outcome["provenance"] == FORWARD
    assert outcome["conflict"] is True


def test_empty_or_below_minimum_forward_is_explicitly_retrospective():
    outcome = primacy(_series("forward", "INSUFFICIENT", settled_n=2, min_n=5),
                      _series("retro", "AHEAD"))
    assert outcome["claim"] == "retro"
    assert outcome["provenance"] == RETROSPECTIVE
    assert outcome["label"] == RETROSPECTIVE
    assert outcome["conflict"] is False


def test_live_scoreboard_labels_rows_without_changing_existing_values(monkeypatch):
    original_label_row = fes.label_row
    unlabeled_rows = []

    def capture_then_label(row):
        unlabeled_rows.append(dict(row))
        return original_label_row(row)

    monkeypatch.setattr(fes, "label_row", capture_then_label)
    rows = fes.build_scoreboard()["rows"]
    existing = {
        "gate", "sport", "pre_registered_at", "days_accruing", "forward_n", "verdict",
        "distance_to_decidable", "source",
    }
    assert rows
    assert len(rows) == len(unlabeled_rows)
    for row, unlabeled in zip(rows, unlabeled_rows):
        assert "claim_label" in row
        assert "claim_provenance" in row
        assert existing <= set(row)
        assert row["claim_label"] == row["claim_provenance"]
        assert {key: row[key] for key in existing} == unlabeled
