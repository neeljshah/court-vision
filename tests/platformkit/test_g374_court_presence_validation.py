"""Focused construct tests for the prepare-only G374 validation lane."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking.g374_premise import verify
from scripts.platformkit.tracking.g374_quota import adjudicated_quota
from scripts.platformkit.tracking.g374_recover import restore_one
from scripts.platformkit.tracking.g374_score import score_once


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/tracking/g374_court_presence_validation_2026-09-10"
PREREG = EVIDENCE / "g374_prereg_2026-09-10.md"
AMENDMENT = EVIDENCE / "g374_amendment_2026-09-10.md"


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _frozen_rows() -> list[dict[str, str]]:
    rows = []
    for prediction, count in (("COURT", 224), ("NON_COURT", 122), ("ABSTAIN", 14)):
        rows.extend({"frame_key": "%s:%03d" % (prediction, index), "prediction": prediction,
                     "game_id": "validation-%03d" % index, "competition": "c%d" % (index % 8)}
                    for index in range(count))
    return rows


def test_quota_is_proportional_even_and_lists_every_excluded_key():
    selected, excluded = adjudicated_quota(_frozen_rows())
    counts = {label: sum(row["prediction"] == label for row in selected)
              for label in ("COURT", "NON_COURT", "ABSTAIN")}
    assert len(selected) == 300 and len({row["frame_key"] for row in selected}) == 300
    assert counts == {"COURT": 185, "NON_COURT": 101, "ABSTAIN": 14}
    assert len(excluded) == 60 and {row["reason"] for row in excluded} == {"quota_not_selected"}
    selected_court = sorted(int(row["frame_key"].split(":")[1]) for row in selected
                            if row["prediction"] == "COURT")
    assert selected_court[0] > 0 and selected_court[-1] < 223
    assert selected_court[-1] > 200
    assert {row["frame_key"] for row in selected}.isdisjoint({row["frame_key"] for row in excluded})


def test_premise_reads_the_whole_pool_and_requires_the_frozen_binding(tmp_path: Path):
    rows = _frozen_rows()
    pool, predictions, development = tmp_path / "pool.csv", tmp_path / "predictions.csv", tmp_path / "dev.csv"
    _write_csv(pool, ["frame_key", "game_id", "competition"],
               [{field: row[field] for field in ("frame_key", "game_id", "competition")} for row in rows])
    model = tmp_path / "model.json"
    extractor = "e" * 64
    model.write_text(json.dumps({"threshold": 0.30, "feature_extractor_sha256": extractor}),
                     encoding="ascii")
    head = hashlib.sha256(model.read_bytes()).hexdigest()
    _write_csv(predictions, ["frame_key", "prediction", "model_sha256"],
               [{"frame_key": row["frame_key"], "prediction": row["prediction"],
                 "model_sha256": head} for row in rows])
    _write_csv(development, ["game_id"], [{"game_id": "development-only"}])
    identity = tmp_path / "model_identity.json"
    identity.write_text(json.dumps({"weights_sha256": extractor}), encoding="ascii")
    bound = verify(model, identity, pool, predictions, development)
    assert bound["model_sha256"] == head
    assert bound["pool_total"] == 360 and bound["court"] == 224 and bound["abstain"] == 14


def test_scorer_emits_the_required_additive_manifests(tmp_path: Path):
    model = tmp_path / "model.json"
    model.write_text('{"threshold": 0.30}\n', encoding="ascii")
    model_sha256 = hashlib.sha256(model.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    selected, _ = adjudicated_quota(_frozen_rows())
    validation_rows = [{"frame_key": row["frame_key"], "game_id": row["game_id"],
                        "competition": row["competition"], "prediction": row["prediction"],
                        "court_probability": "0.900000000", "model_sha256": model_sha256}
                       for row in selected]
    validation, development = tmp_path / "validation.csv", tmp_path / "dev.csv"
    _write_csv(validation, list(validation_rows[0]), validation_rows)
    _write_csv(development, ["game_id"], [{"game_id": "development-only"}])
    ratings = tmp_path / "ratings.csv"
    rating_rows = [{"frame_key": row["frame_key"], "rater": rater,
                    "label": "USABLE_COURT" if row["prediction"] == "COURT" else "CLOSEUP"}
                   for row in validation_rows for rater in ("terra", "sol")]
    _write_csv(ratings, ["frame_key", "rater", "label"], rating_rows)
    adjudication = tmp_path / "adjudication.csv"
    _write_csv(adjudication, ["frame_key", "label"], [])
    summary = score_once(development, validation, ratings, adjudication, model, tmp_path / "out")
    assert summary["n"] == 300 and not summary["bar_predicted_strata"]
    assert (tmp_path / "out" / "predictions.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "frame_key,prediction,court_probability,model_sha256")
    assert (tmp_path / "out" / "confusion.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "scope,prediction,reference_label,count")


def test_preregistration_seal_normalizes_crlf_without_git_history():
    text = PREREG.read_text(encoding="utf-8").replace("\r\n", "\n")
    prefix, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert hashlib.sha256((prefix + "\n").encode("utf-8")).hexdigest() == seal.strip()


def test_restore_classifies_a_pinned_source_by_its_digest_only(tmp_path: Path):
    scratch = tmp_path / "val"
    scratch.mkdir()
    target = scratch / "VIDEOIDABC_s90.mp4"
    target.write_bytes(b"pinned-bytes")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    row = {"section_id": "comp-VIDEOIDABC_s90", "video_id": "VIDEOIDABC", "offset_s": "90",
           "duration_s": "132.0", "source_sha256": digest, "byte_size": str(target.stat().st_size)}
    assert restore_one(row, scratch, 1)["status"] == "already_present"
    target.write_bytes(b"different-bytes")
    record = restore_one(row, scratch, 1)
    assert record["status"] in ("mismatch", "fetch_failed")
    assert record["observed_sha256"] != digest


def test_amendment_is_sealed_over_its_own_normalized_bytes():
    raw = AMENDMENT.read_bytes().replace(bytes([13, 10]), bytes([10]))
    marker = bytes([10]) + b"SEAL sha256 "
    prefix, seal = raw.rsplit(marker, 1)
    assert hashlib.sha256(prefix + bytes([10])).hexdigest() == seal.decode("ascii").strip()
