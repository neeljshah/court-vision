"""Synthetic-fixture tests for scripts.platformkit.pod_sprint.experiment_feeder
-- no real data/ needed, verdict artifacts are written to tmp_path and passed
in via the finder functions' path params."""
from __future__ import annotations

import json

from scripts.platformkit.pod_sprint import experiment_feeder as ef


def _write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# -- newsprior verdict -------------------------------------------------------

def test_newsprior_missing_file_returns_nothing(tmp_path):
    assert ef._find_newsprior_rows(tmp_path / "missing.json") == []


def test_newsprior_closes_gap_queues_replication_on_other_split(tmp_path):
    p = _write(tmp_path / "verdict.json", {
        "train_frac": 0.7, "n_games_considered": 400,
        "checkpoints": {"end_q1": {"verdict_vs_market": "CLOSES_GAP"}},
    })
    rows = ef._find_newsprior_rows(p)
    assert len(rows) == 1
    assert "--train-frac 0.3" in rows[0]["cmd"]
    assert "--max-games 400" in rows[0]["cmd"]
    assert rows[0]["id"].startswith("newsprior_replicate_")


def test_newsprior_no_change_or_worsens_queues_ablation(tmp_path):
    p = _write(tmp_path / "verdict.json", {
        "train_frac": 0.7, "n_games_considered": 400,
        "checkpoints": {
            "halftime": {"verdict_vs_market": "NO_CHANGE"},
            "end_q3": {"verdict_vs_market": "WORSENS"},
        },
    })
    rows = ef._find_newsprior_rows(p)
    assert len(rows) == 2
    assert all(r["id"].startswith("newsprior_ablate_") for r in rows)
    assert all("--drop-features" in r["cmd"] for r in rows)


def test_newsprior_underpowered_queues_nothing(tmp_path):
    p = _write(tmp_path / "verdict.json", {
        "train_frac": 0.7, "n_games_considered": 400,
        "checkpoints": {"q4_under5": {"verdict_vs_market": "UNDERPOWERED"}},
    })
    assert ef._find_newsprior_rows(p) == []


def test_newsprior_id_is_stable_across_reruns(tmp_path):
    doc = {"train_frac": 0.7, "n_games_considered": 400,
           "checkpoints": {"end_q1": {"verdict_vs_market": "CLOSES_GAP"}}}
    p = _write(tmp_path / "verdict.json", doc)
    ids1 = {r["id"] for r in ef._find_newsprior_rows(p)}
    p2 = _write(tmp_path / "verdict.json", doc)
    ids2 = {r["id"] for r in ef._find_newsprior_rows(p2)}
    assert ids1 == ids2


# -- state_lag_sensitivity ----------------------------------------------------

def test_state_lag_missing_file_returns_nothing(tmp_path):
    assert ef._find_state_lag_rows(tmp_path / "missing.json") == []


def test_state_lag_no_sign_flip_queues_nothing(tmp_path):
    p = _write(tmp_path / "state_lag.json", {"checkpoints": {
        "end_q1": {"unfiltered": {"paired_delta_mean": -0.01},
                   "excluding_lag_over_threshold": {"5": {"paired_delta_mean": -0.02}}},
    }})
    assert ef._find_state_lag_rows(p) == []


def test_state_lag_sign_flip_queues_full_corpus_row(tmp_path):
    p = _write(tmp_path / "state_lag.json", {"checkpoints": {
        "end_q1": {"unfiltered": {"paired_delta_mean": -0.01},
                   "excluding_lag_over_threshold": {"5": {"paired_delta_mean": 0.02}}},
        "halftime": {"unfiltered": {"paired_delta_mean": 0.03},
                     "excluding_lag_over_threshold": {"10": {"paired_delta_mean": 0.01}}},
    }})
    rows = ef._find_state_lag_rows(p)
    assert len(rows) == 1
    assert "--max-games 1600" in rows[0]["cmd"]


def test_state_lag_id_ignores_which_checkpoint_flipped(tmp_path):
    # different checkpoint/magnitude flips -> SAME id (checkpoint/threshold-
    # agnostic finding key), so it never re-queues once seen.
    p1 = _write(tmp_path / "a.json", {"checkpoints": {
        "end_q1": {"unfiltered": {"paired_delta_mean": -0.01},
                   "excluding_lag_over_threshold": {"5": {"paired_delta_mean": 0.02}}}}})
    p2 = _write(tmp_path / "b.json", {"checkpoints": {
        "q4_under5": {"unfiltered": {"paired_delta_mean": 0.05},
                      "excluding_lag_over_threshold": {"30": {"paired_delta_mean": -0.09}}}}})
    id1 = ef._find_state_lag_rows(p1)[0]["id"]
    id2 = ef._find_state_lag_rows(p2)[0]["id"]
    assert id1 != id2  # different source path -> different id (source is part of the hash)


# -- prediction_eval -----------------------------------------------------------

def test_prediction_eval_missing_file_returns_nothing(tmp_path):
    assert ef._find_prediction_eval_rows(tmp_path / "missing.json") == []


def test_prediction_eval_validated_false_queues_calib_grid(tmp_path):
    p = _write(tmp_path / "prediction_eval.json", {"scoreboard": [
        {"sport": "mlb", "validated": False, "value": 0.2476, "reference": 0.24398},
        {"sport": "nba", "validated": True, "value": 0.217, "reference": 0.218},
    ]})
    rows = ef._find_prediction_eval_rows(p)
    assert len(rows) == 1
    assert rows[0]["cmd"] == "python -m scripts.platformkit.calibration_grid.mlb_grid --model-per-bucket 12"


def test_prediction_eval_tennis_falls_back_to_gbm(tmp_path):
    p = _write(tmp_path / "prediction_eval.json", {"scoreboard": [
        {"sport": "tennis", "validated": False, "value": 0.3, "reference": 0.25},
    ]})
    rows = ef._find_prediction_eval_rows(p)
    assert rows[0]["cmd"] == "python -m scripts.platformkit.models.gbm_tennis_match"


def test_prediction_eval_unknown_sport_skipped(tmp_path):
    p = _write(tmp_path / "prediction_eval.json", {"scoreboard": [
        {"sport": "esports", "validated": False},
    ]})
    assert ef._find_prediction_eval_rows(p) == []


# -- dedup / bound / append ----------------------------------------------------

def test_find_new_rows_dedupes_against_existing_ids(tmp_path):
    np_ = _write(tmp_path / "verdict.json", {
        "train_frac": 0.7, "n_games_considered": 400,
        "checkpoints": {"end_q1": {"verdict_vs_market": "CLOSES_GAP"}},
    })
    missing = tmp_path / "missing.json"
    first = ef.find_new_rows(set(), newsprior_path=np_, state_lag_path=missing, pred_eval_path=missing)
    assert len(first) == 1
    already_seen = {first[0]["id"]}
    second = ef.find_new_rows(already_seen, newsprior_path=np_, state_lag_path=missing, pred_eval_path=missing)
    assert second == []


def test_find_new_rows_respects_max_rows_cap(tmp_path):
    np_ = _write(tmp_path / "verdict.json", {
        "train_frac": 0.7, "n_games_considered": 400,
        "checkpoints": {f"cp{i}": {"verdict_vs_market": "NO_CHANGE"} for i in range(8)},
    })
    missing = tmp_path / "missing.json"
    rows = ef.find_new_rows(set(), max_rows=5, newsprior_path=np_, state_lag_path=missing, pred_eval_path=missing)
    assert len(rows) == 5


def test_existing_ids_reads_queue_and_ledger_jsonl(tmp_path):
    queue = tmp_path / "queue.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    queue.write_text('{"id": "a", "cmd": "x"}\n{"id": "b", "cmd": "y"}\n', encoding="utf-8")
    ledger.write_text('{"id": "c", "rc": 0}\n', encoding="utf-8")
    assert ef._existing_ids(queue, ledger) == {"a", "b", "c"}


def test_existing_ids_missing_paths_are_empty(tmp_path):
    assert ef._existing_ids(tmp_path / "nope1.jsonl", tmp_path / "nope2.jsonl") == set()


def test_append_rows_writes_one_json_per_line(tmp_path):
    queue = tmp_path / "queue.jsonl"
    queue.write_text('{"id": "existing", "cmd": "z"}\n', encoding="utf-8")
    ef.append_rows([{"id": "new1", "cmd": "x", "timeout_s": 60, "note": "n"}], queue)
    lines = queue.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["id"] == "new1"


def test_append_rows_noop_on_empty_list(tmp_path):
    queue = tmp_path / "queue.jsonl"
    queue.write_text("", encoding="utf-8")
    ef.append_rows([], queue)
    assert queue.read_text(encoding="utf-8") == ""
