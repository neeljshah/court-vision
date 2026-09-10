"""G369 prospective identity bindings, repeatability, collisions, and prereg seal."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from scripts.platformkit.tracking import g369_prospective_identity as g369

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "docs/evidence/tracking/g369_prospective_identity_2026-09-09/g369_prereg_2026-09-09.md"
AMENDMENT = REPO / "docs/evidence/tracking/g369_prospective_identity_2026-09-09/g369_prereg_amendment_1_2026-09-10.md"
AMENDMENT_2 = REPO / "docs/evidence/tracking/g369_prospective_identity_2026-09-09/g369_prereg_amendment_2_2026-09-10.md"


def _manifest() -> dict:
    file = {"path": "fixture", "sha256": "a" * 64, "bytes": 1}
    return {"routes": {"route": file}, "weights": {"weight": file}, "crop":
            {"rule": "TOPCUT = 60", "crop_rule": "TOPCUT = 60", "pixel_transform": "(x, y) -> (x, y-60)",
             "producer_config": "src/tracking/video_handler.py:11,61"}, "manifest_sha256": "b" * 64}


def _source(game_id: str = "nba-AAAAAAAAAAA_s90") -> dict:
    row = {field: "fixture" for field in g369.SOURCE_FIELDS}
    row.update(game_id=game_id, source_id="AAAAAAAAAAA", competition="nba", requested_start_s="90",
               source_path="/fixture.mp4", source_sha256="c" * 64, source_bytes=1, codec="h264",
               fps="30", width="1280", height="720", nb_frames="3900", first_pts="0.0",
               crop_rule="TOPCUT = 60", pixel_transform="(x, y) -> (x, y-60)",
               producer_config="src/tracking/video_handler.py:11,61", ledger_row_json="{}")
    return row


def _seal(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    index = raw.rfind(b"\nSEAL sha256 ")
    recorded = raw[index + len(b"\nSEAL sha256 "):].split(b"\n", 1)[0].decode("ascii")
    return recorded, hashlib.sha256(raw[:index + 1]).hexdigest()


def _write_inputs(root: Path, rows: list[dict]) -> None:
    with (root / "sources.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=g369.SOURCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with (root / "attempts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=g369.ATTEMPT_FIELDS)
        writer.writeheader()
        writer.writerow({"game_id": rows[0]["game_id"], "source_id": "AAAAAAAAAAA",
                         "requested_start_s": "90", "competition": "nba", "source_path": "/fixture.mp4",
                         "status": "PINNED", "error": ""})
    (root / "manifests.json").write_text(json.dumps(_manifest(), sort_keys=True), encoding="utf-8")
    (root / "alignment.csv").write_text(
        "game_id,landmark,archived_frame,archived_timestamp,mode,error_frames,within_bar\n", encoding="utf-8")


def test_synthetic_section_pins_every_required_field(tmp_path, monkeypatch):
    video = tmp_path / "nba-AAAAAAAAAAA_s90.mp4"
    video.write_bytes(b"fixture-video")
    candidate = {"game_id": "nba-AAAAAAAAAAA_s90", "source_id": "AAAAAAAAAAA", "competition": "nba",
                 "requested_start_s": "90", "source_path": str(video), "ledger": {"game_id": "fixture"}}
    monkeypatch.setattr(g369, "_candidates", lambda ledger, dirs: [candidate])
    monkeypatch.setattr(g369, "_manifest", lambda repo, weights: _manifest())
    monkeypatch.setattr(g369, "_probe", lambda path: {"codec": "h264", "fps": "30", "width": "1280",
                                                        "height": "720", "nb_frames": "3900", "first_pts": "0"})
    g369.cmd_pin(SimpleNamespace(ledger="unused", dirs=[], repo=".", weights=[], out=str(tmp_path / "out")))
    with (tmp_path / "out" / "sources.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert set(rows[0]) == set(g369.SOURCE_FIELDS)
    assert _manifest()["crop"]["rule"] == _manifest()["crop"]["crop_rule"]
    assert g369.binding_state(rows, _manifest()) == "DONE"


def test_missing_required_field_is_partial_not_pass():
    source = _source()
    source["first_pts"] = ""
    assert g369.binding_state([source], _manifest()) == "PARTIAL"


def test_two_exports_are_byte_identical(tmp_path):
    _write_inputs(tmp_path, [_source()])
    common = ["--sources", str(tmp_path / "sources.csv"), "--attempts", str(tmp_path / "attempts.csv"),
              "--manifests", str(tmp_path / "manifests.json"), "--alignment", str(tmp_path / "alignment.csv")]
    g369.main(["export", *common, "--out", str(tmp_path / "first.json")])
    g369.main(["export", *common, "--out", str(tmp_path / "second.json")])
    g369.main(["repeatability", "--first", str(tmp_path / "first.json"), "--second",
               str(tmp_path / "second.json"), "--out", str(tmp_path)])
    result = json.loads((tmp_path / "export_hashes.json").read_text(encoding="utf-8"))
    assert result["byte_identical"]
    assert result["first_sha256"] == result["second_sha256"]


def test_duplicate_source_offset_pair_is_a_collision(tmp_path):
    duplicate = _source("fiba-AAAAAAAAAAA_s90")
    _write_inputs(tmp_path, [_source(), duplicate])
    g369.main(["export", "--sources", str(tmp_path / "sources.csv"), "--attempts",
               str(tmp_path / "attempts.csv"), "--manifests", str(tmp_path / "manifests.json"),
               "--alignment", str(tmp_path / "alignment.csv"), "--out", str(tmp_path / "export.json")])
    result = json.loads((tmp_path / "export.json").read_text(encoding="utf-8"))
    assert result["collision_count"] == 1
    assert result["collisions"]["AAAAAAAAAAA@90"] == ["fiba-AAAAAAAAAAA_s90", "nba-AAAAAAAAAAA_s90"]


def test_prereg_seal_normalises_crlf_and_matches():
    recorded, computed = _seal(PREREG)
    assert recorded == computed
    recorded, computed = _seal(AMENDMENT)
    assert recorded == computed
    recorded, computed = _seal(AMENDMENT_2)
    assert recorded == computed
