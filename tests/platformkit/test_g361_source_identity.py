"""G361 identity-map classification, collision, sampling and seal checks."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking import g361_source_identity as g361

REPO = Path(__file__).resolve().parents[2]
PREREG = (REPO / "docs/evidence/tracking/g361_source_identity_2026-09-09"
          / "g361_prereg_2026-09-09.md")
HEADER = "frame,timestamp,player_id\n"
EXACT_ID = "AAAAAAAAAAA_s90"
ALIGNED_ID = "BBBBBBBBBBB_s90"
UNKNOWN_ID = "CCCCCCCCCCC_s90"
COLLIDING_ID = "lnb-AAAAAAAAAAA_s90"


def verify_seal(path: Path) -> tuple[str, str]:
    """(recorded, computed) SHA-256 over the CRLF-normalised bytes above SEAL."""
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
    marker = b"SEAL sha256 "
    index = raw.rfind(b"\n" + marker)
    if index < 0:
        return ("", "")
    return (raw[index + 1 + len(marker):].split(b"\n")[0].decode("ascii").strip(),
            hashlib.sha256(raw[:index + 1]).hexdigest())


def _fixture(root: Path) -> dict:
    """Synthetic ledger + tables covering one row of every join class."""
    tracking = root / "tracking"
    ledger = root / "ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as handle:
        for index, game in enumerate((EXACT_ID, ALIGNED_ID, UNKNOWN_ID, COLLIDING_ID)):
            (tracking / game).mkdir(parents=True)
            (tracking / game / "tracking_data.csv").write_text(
                HEADER + "".join("%d,%.3f,1\n" % (n, n / 30.0) for n in range(120)),
                encoding="utf-8")
            (tracking / game / "ball_tracking.csv").write_text("frame\n0\n", encoding="utf-8")
            handle.write(json.dumps({"game_id": game, "finished_at": 1000 + index,
                                     "seconds": 10}) + "\n")
    sources = root / "sources.csv"
    with sources.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["game_id", "source_sha256"])
        writer.writeheader()
        writer.writerow({"game_id": EXACT_ID, "source_sha256": "d" * 64})
    alignment = root / "alignment.csv"
    with alignment.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["game_id", "landmark", "within_bar"])
        writer.writeheader()
        for landmark in range(g361.LANDMARKS):
            writer.writerow({"game_id": ALIGNED_ID, "landmark": landmark, "within_bar": "1"})
        writer.writerow({"game_id": UNKNOWN_ID, "landmark": 0, "within_bar": "0"})
    return {"ledger": ledger, "tracking": tracking, "sources": sources,
            "alignment": alignment, "out": root / "out"}


def _links(root: Path):
    paths = _fixture(root)
    g361.main(["links", "--ledger", str(paths["ledger"]), "--tracking", str(paths["tracking"]),
               "--sources", str(paths["sources"]), "--alignment", str(paths["alignment"]),
               "--out", str(paths["out"])])
    with (paths["out"] / "ledger_links.csv").open(encoding="utf-8") as handle:
        return {row["game_id"]: row for row in csv.DictReader(handle)}, paths


def test_join_classes(tmp_path):
    rows, _ = _links(tmp_path)
    assert rows[EXACT_ID]["join_class"] == "EXACT"
    assert rows[ALIGNED_ID]["join_class"] == "ALIGNED"
    assert rows[UNKNOWN_ID]["join_class"] == "UNKNOWN"
    assert rows[UNKNOWN_ID]["reason"] == "no_source_bytes_and_no_alignment"
    assert rows[EXACT_ID]["run_start_utc"] == "1970-01-01T00:16:30Z"


def test_unreadable_table_stays_unknown(tmp_path):
    paths = _fixture(tmp_path)
    (paths["tracking"] / EXACT_ID / "tracking_data.csv").unlink()
    g361.main(["links", "--ledger", str(paths["ledger"]), "--tracking", str(paths["tracking"]),
               "--sources", str(paths["sources"]), "--out", str(paths["out"])])
    with (paths["out"] / "ledger_links.csv").open(encoding="utf-8") as handle:
        rows = {row["game_id"]: row for row in csv.DictReader(handle)}
    assert rows[EXACT_ID]["join_class"] == "UNKNOWN"
    assert rows[EXACT_ID]["reason"] == "table_unreadable"


def test_collision_is_reported(tmp_path):
    _, paths = _links(tmp_path)
    g361.main(["summary", "--links", str(paths["out"] / "ledger_links.csv"),
               "--alignment", str(paths["alignment"]), "--ledger", str(paths["ledger"]),
               "--out", str(paths["out"])])
    summary = json.loads((paths["out"] / "summary.json").read_text(encoding="utf-8"))
    assert summary["collision_count"] == 1
    assert summary["collisions"]["AAAAAAAAAAA@90"] == sorted([EXACT_ID, COLLIDING_ID])
    assert summary["ledger_game_ids"] == 4
    assert summary["classified_share_of_ledger"] == 1.0
    assert summary["join_class_counts"] == {"EXACT": 1, "ALIGNED": 1, "UNKNOWN": 2}


def test_even_sampler_is_not_a_head_slice():
    items = list(range(300))
    picked = g361.even_sample(items)
    assert len(picked) >= 30
    assert picked[0] == 0 and picked[-1] >= 290
    assert len(set(picked)) == len(picked)
    assert g361.even_sample(list(range(40))) == list(range(40))


def test_sample_spans_the_eligible_set(tmp_path):
    _, paths = _links(tmp_path)
    g361.main(["sample", "--links", str(paths["out"] / "ledger_links.csv"),
               "--out", str(paths["out"])])
    with (paths["out"] / "sections.csv").open(encoding="utf-8") as handle:
        picked = [row["game_id"] for row in csv.DictReader(handle)]
    assert picked == sorted([EXACT_ID, ALIGNED_ID, UNKNOWN_ID, COLLIDING_ID])
    with (paths["out"] / "sample_census.csv").open(encoding="utf-8") as handle:
        census = list(csv.DictReader(handle))
    assert all(row["eligible"] == "1" for row in census)


def test_archived_ticks_are_evenly_spaced(tmp_path):
    paths = _fixture(tmp_path)
    ticks = g361.archived_ticks(paths["tracking"] / EXACT_ID / "tracking_data.csv")
    assert len(ticks) >= 30
    assert ticks[0][0] == 0 and ticks[-1][0] >= 100


def test_seal_normalises_crlf(tmp_path):
    body = "# prereg\r\nline two\r\n"
    digest = hashlib.sha256(body.replace("\r\n", "\n").encode("ascii")).hexdigest()
    path = tmp_path / "prereg.md"
    path.write_bytes((body + "SEAL sha256 %s\n" % digest).encode("ascii"))
    recorded, computed = verify_seal(path)
    assert recorded == computed == digest


def test_prereg_seal_matches_its_own_bytes():
    assert PREREG.exists(), "prereg must be committed before the lane work"
    recorded, computed = verify_seal(PREREG)
    assert recorded and recorded == computed


def test_aligned_games_requires_landmark_floor(tmp_path):
    """Sub-30 distinct landmarks, even if all within bar, must not classify ALIGNED (B10/Q3)."""
    alignment = tmp_path / "alignment.csv"
    with alignment.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["game_id", "landmark", "within_bar"])
        writer.writeheader()
        for landmark in range(9):
            writer.writerow({"game_id": "fiba-x_s1", "landmark": landmark, "within_bar": "1"})
        for landmark in range(g361.LANDMARKS):
            writer.writerow({"game_id": "ok-y_s1", "landmark": landmark, "within_bar": "1"})
    aligned = g361.aligned_games(alignment)
    assert "fiba-x_s1" not in aligned
    assert "ok-y_s1" in aligned
