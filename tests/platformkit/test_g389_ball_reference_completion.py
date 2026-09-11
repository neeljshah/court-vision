from pathlib import Path

import pytest

from scripts.platformkit.tracking.g389_finish import (assert_no_drop, dev_boxes, even_subset,
                                                      prior_decisions)
from scripts.platformkit.tracking.g389_merge import full_schema_merge
from scripts.platformkit.tracking.g389_prepare import (CHECKPOINTS, allocation, append_completed,
                                                        bins_and_permutation, completion_status)
from scripts.platformkit.tracking.g389_premise import check_binding
from scripts.platformkit.tracking.g389_q6_scan import scan


def _rows(n=60):
    return [{"frame_key": "k%03d" % index, "split": "development" if index % 2 else "heldout",
             "source": "g%02d" % (index % 6), "section": "s", "frame_index": str(index)}
            for index in range(n)]


def test_g389_restart_overlap_merge_checkpoints_and_unknown(tmp_path: Path):
    rows = _rows()
    groups, order = bins_and_permutation(rows)
    assert len(groups) == 30
    assert CHECKPOINTS == (30, 120, 240, 360, 506)
    assert [row["frame_key"] for row in order[:30]] == [group[0]["frame_key"] for group in groups]
    first = allocation(rows, {"k000"}, ("rater_a", "rater_b"))
    assert "k000" not in {row["frame_key"] for row in first}
    log = tmp_path / "completed.tsv"
    append_completed(log, [{"frame_key": "k001", "label": "UNKNOWN"}])
    with pytest.raises(ValueError, match="duplicate-decision-key"):
        append_completed(log, [{"frame_key": "k001", "label": "VISIBLE"}])
    merged = full_schema_merge(rows[:2], [], [{"frame_key": "k001", "label": "UNKNOWN"}], {"k001"})
    assert [(row["frame_key"], row["review_state"], row["label"]) for row in merged] == [
        ("k000", "UNVISITED", ""), ("k001", "REVIEWED", "UNKNOWN")]
    with pytest.raises(ValueError, match="unknown-requires-reviewed-decision"):
        full_schema_merge(rows[:1], [], [], {"k000"})
    assert completion_status(("k%03d" % index for index in range(500))) == "PARTIAL"
    assert completion_status(("k%03d" % index for index in range(506))) == "DONE"
    check_binding({"manifest": 1620, "settled": 1114, "pending": 506,
                   "pending_development": 301, "pending_heldout": 205, "dev_boxes": 312,
                   "heldout_absent": 161, "heldout_visible": 157, "heldout_unknown": 26,
                   "candidate_executions": 0})
    with pytest.raises(ValueError, match="binding-counts-changed"):
        check_binding({"manifest": 1})
    prose = tmp_path / "prose.txt"
    prose.write_text("ledger\n" + chr(101) + chr(100) + chr(103) + chr(101), encoding="utf-8")
    assert scan([prose]) == {str(prose): ["".join(chr(code) for code in (101, 100, 103, 101))]}


def test_g389_merge_keeps_every_prior_decision_and_refuses_a_prefix_pass():
    prior = prior_decisions([{"frame_key": "k000", "label": "VISIBLE"}],
                            [{"frame_key": "k001", "label": "UNKNOWN"}])
    merged = [{"frame_key": "k000", "label": "VISIBLE"}, {"frame_key": "k001", "label": "UNKNOWN"},
              {"frame_key": "k002", "label": "ABSENT"}]
    assert assert_no_drop(merged, prior) == {"prior_decisions": 2, "prior_reproduced": 2}
    with pytest.raises(ValueError, match="prior-decision-lost"):
        assert_no_drop(merged[1:], prior)
    with pytest.raises(ValueError, match="prior-decision-lost"):
        assert_no_drop([{"frame_key": "k000", "label": "ABSENT"}] + merged[1:], prior)

    order = [{"frame_key": "k%03d" % index, "bin": str(index % 30)} for index in range(60)]
    spread = {row["frame_key"] for row in order[:30]}
    assert even_subset(order, spread)["bins_covered"] == 30
    with pytest.raises(ValueError, match="partial-pass-not-even"):
        even_subset(order, {"k000", "k030", "k001", "k031", "k002"})


def test_g389_sweep_order_is_deterministic_and_boxes_dedupe_causal_neighbours():
    rows = _rows()
    first = [row["frame_key"] for row in bins_and_permutation(rows)[1]]
    shuffled = rows[17:] + rows[:17]
    assert [row["frame_key"] for row in bins_and_permutation(shuffled)[1]] == first
    assert [row["frame_key"] for row in bins_and_permutation(list(reversed(rows)))[1]] == first

    frames = {"k%03d" % index: {"game": "g1", "section": "s1", "frame_index": str(index),
                                "width": "1920", "height": "1080", "sheet_scale": "1.0"}
              for index in range(6)}
    merged = [{"frame_key": "k%03d" % index, "split": "development", "label": "VISIBLE",
               "cx": "10", "cy": "10", "diameter": "30", "decided_by": "ADJUDICATOR",
               "source": "extra"} for index in range(6)]
    boxes, skipped = dev_boxes(merged, frames)
    assert (len(boxes), skipped) == (2, 4)
    merged[0]["label"] = "UNKNOWN"
    assert dev_boxes(merged[:1], frames) == ([], 0)
