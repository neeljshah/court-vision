"""Prepare-only rails for the G384 phase-2 continuation helpers."""
from __future__ import annotations

import csv

import pytest

from scripts.platformkit.tracking.g384_arm_receipt import accounting
from scripts.platformkit.tracking.g384_adjudicate import completed_keys, append, load
from scripts.platformkit.tracking.g384_build import RECON_FIELDS, CHECK_FIELDS, prior_decisions, reference_decisions
from scripts.platformkit.tracking.g384_native_frames import require_native_scale
from scripts.platformkit.tracking.g384_queue import interleaved_queue, reconcile
from scripts.platformkit.tracking.g373_ball_detector_v2 import prereg_seal_matches
from pathlib import Path


PREREG = (Path(__file__).resolve().parents[2] / "docs/evidence/tracking/"
          "g384_ball_phase2_receipt_2026-09-10/g384_execution_prereg_2026-09-10.md")
G373 = PREREG.parent.parent / "g373_ball_detector_v2_2026-09-10"
OUT = PREREG.parent


def _manifest(*keys: str) -> list[dict]:
    return [{"frame_key": key, "split": "development" if key == "dev" else "heldout",
             "source": "sealed"} for key in keys]


def test_sheet_scale_half_table_is_refused_before_scoring():
    with pytest.raises(ValueError, match="REFUSED sheet_scale != 1.0"):
        require_native_scale([{"frame_key": "k", "sheet_scale": "0.5"}])


def test_prereg_seal_reads_the_file_and_normalizes_crlf():
    assert prereg_seal_matches(PREREG)


def test_keyed_frame_already_rated_is_never_requeued():
    queue = [{"frame_key": "dev", "why": "LABEL-DISAGREEMENT"},
             {"frame_key": "held", "why": "CENTRE-GAP"}]
    rows = interleaved_queue(_manifest("dev", "held"), queue, {"dev"})
    assert [row["frame_key"] for row in rows] == ["held"]


def test_receipt_names_every_unmet_quota():
    rows = {row["arm"]: row for row in accounting({})}
    assert rows["A8"]["state"] == "CLOSED AT LIMIT"
    assert rows["A8"]["unmet_quotas"] == (
        "reference_complete;reference_usable;heldout_visible_150;heldout_absent_150;"
        "time_budget;development_boxes_500;development_games_5")
    assert "pinned_licence_dependency_receipt" in rows["A9"]["unmet_quotas"]
    assert "A8_available" in rows["A10"]["unmet_quotas"]


def test_reconciliation_refuses_a_queue_key_settled_in_reference():
    with pytest.raises(ValueError, match="queue-reconciliation-failed"):
        reconcile(_manifest("k"), [{"frame_key": "k"}], [],
                  [{"frame_key": "k", "why": "CENTRE-GAP"}])


def test_second_candidate_heldout_execution_is_refused():
    with pytest.raises(ValueError, match="second-candidate"):
        accounting({}, candidate_heldout_executions=2)


def test_finisher_loader_excludes_completed_key_and_append_rejects_duplicate(tmp_path):
    path = tmp_path / "decisions.csv"
    row = {"ordinal": 1, "frame_key": "0d2ba648eac22051a8ab8cfc6d58f4acd4743d600cd7d81cf27886be5e7a1e4a",
           "split": "development", "why": "CENTRE-GAP", "label": "ABSENT", "panel": "",
           "cx": "", "cy": "", "diameter": "", "reason": "test"}
    append(path, [row])
    order, _, _ = load(G373, path)
    assert row["frame_key"] not in {item["frame_key"] for item in order}
    with pytest.raises(ValueError, match="duplicate-decision-key"):
        append(path, [row])


def test_merged_reference_keeps_every_prior_decision_key():
    assert {row["frame_key"] for row in prior_decisions()} <= {
        row["frame_key"] for row in reference_decisions()}


def test_finisher_loader_keeps_one_argument_default():
    order, _, _ = load(G373)
    assert order
    done = completed_keys(OUT / "adjudications_g384.csv")
    keys = {row["frame_key"] for row in order}
    assert len(keys) == 506 and not (keys & done)


def test_parent_field_names_remain_beside_g384_aliases():
    assert {"allocation", "allocation_g384"} <= set(RECON_FIELDS)
    assert {"verdict", "verdict_g384"} <= set(CHECK_FIELDS)
    with (OUT / "queue_reconciliation.csv").open(encoding="ascii", newline="") as handle:
        assert {"allocation", "allocation_g384"} <= set(csv.DictReader(handle).fieldnames or ())
    with (OUT / "transform_checks.csv").open(encoding="ascii", newline="") as handle:
        assert {"verdict", "verdict_g384"} <= set(csv.DictReader(handle).fieldnames or ())
