"""Focused S200 coverage. Run only this file with pytest."""
from __future__ import annotations

from scripts.platformkit.eval_gate.calibration_report import build_report
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.eval_gate import s200_regime_key_oof
from scripts.platformkit.eval_gate.s200_regime_key_oof import (
    build_sport_summary, changed_label_count, oof_per_regime, train_only_keys,
)
from scripts.platformkit.regime_calibration import buckets


def _records(n: int = 60) -> list[dict[str, float | str]]:
    return [
        {"event_id": "event-%03d" % index, "model_prob": (index % 17) / 16,
         "event_date": "2020-01-%02d" % (1 + index // 3),
         "corpus_unit": "synthetic", "y": float(index % 3 == 0),
         "period": str(1 + index % 4)}
        for index in range(n)
    ]


def test_train_only_keys_are_prefix_invariant_and_keep_all_rows() -> None:
    records = _records()
    short = train_only_keys(records[:40], [float(row["model_prob"]) for row in records[:40]])
    long = train_only_keys(records, [float(row["model_prob"]) for row in records])

    assert short == long[:40]
    assert len(long) == len(records)
    assert {key.rsplit("confidence=", 1)[-1] for key in long} <= {"T1", "T2", "T3"}
    assert changed_label_count(buckets(records), long) >= 0


def test_same_date_rows_use_only_strictly_earlier_date_key_state() -> None:
    records = _records(6)
    for row in records[:3]:
        row["event_date"] = "2020-01-01"
    keys = train_only_keys(records, [float(row["model_prob"]) for row in records])

    assert [key.rsplit("confidence=", 1)[-1] for key in keys[:3]] == ["T1", "T1", "T1"]


def test_train_report_stable_sorts_every_sequential_pass() -> None:
    records = _records()
    forward = build_report(records, "synthetic", min_n=10, key_source="train")
    reverse = build_report(list(reversed(records)), "synthetic", min_n=10, key_source="train")

    assert forward["ece_after"] == reverse["ece_after"]
    assert forward["confidence_label_change_count"] == reverse["confidence_label_change_count"]


def test_opt_in_train_report_preserves_default_and_archives_paired_rows() -> None:
    records = _records()
    default = build_report(records, "synthetic", min_n=10)
    explicit_default = build_report(records, "synthetic", min_n=10, key_source="global")
    train = build_report(records, "synthetic", min_n=10, key_source="train")
    summary, paired = build_sport_summary(
        records, "synthetic", {"ece_after": default["ece_after"]}, min_n=10)

    assert default == explicit_default
    assert "key_source" not in default
    assert train["scored_rows"] == default["scored_rows"] == len(records)
    assert train["dropped_rows"] == default["dropped_rows"] == 0
    assert summary["default_path_abs_diff"] == 0.0
    assert summary["label_change_count"] == len([row for row in paired if row["label_changed"]])
    assert len(paired) == len(records)
    assert all({"cluster_id", "timestamp", "default_squared_loss", "train_squared_loss"} <= set(row)
               for row in paired)


def test_oof_cache_is_call_order_invariant_between_clean_and_prior_arms() -> None:
    probs = [index / 19 for index in range(20)]
    outcomes = [float(index % 3 == 0) for index in range(20)]
    keys = ["phase=all|confidence=T1"] * len(probs)
    rows = _records(20)

    s200_regime_key_oof._GLOBAL_OOF_CACHE.clear()
    clean_first = oof_per_regime(probs, outcomes, keys, 5, rows=rows,
                                 fallback_source="prior_date")
    oof_per_regime(probs, outcomes, keys, 5, fallback_source="full_sample")
    clean_after_prior = oof_per_regime(probs, outcomes, keys, 5, rows=rows,
                                       fallback_source="prior_date")
    clean_first_ece = ece(clean_first, outcomes)
    assert abs(clean_first_ece - ece(clean_after_prior, outcomes)) <= 1e-12

    s200_regime_key_oof._GLOBAL_OOF_CACHE.clear()
    oof_per_regime(probs, outcomes, keys, 5, fallback_source="full_sample")
    prior_first_ece = ece(oof_per_regime(
        probs, outcomes, keys, 5, rows=rows, fallback_source="prior_date"), outcomes)
    assert abs(clean_first_ece - prior_first_ece) <= 1e-12
