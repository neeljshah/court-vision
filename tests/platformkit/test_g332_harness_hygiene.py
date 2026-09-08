"""G332 -- one test per harness-hygiene hole named by the 2026-09-08 verifiers.

n = 7 CONSTRUCT, enumerated by hand to match section 1 of
`docs/evidence/tracking/g332_prereg_2026-09-08.md`: a x2 (opt-out byte parity), b x2 (fatal
snapshot, expected arm), c x3 (snapshot-list rigour, construct-only fallback, TXT rule).
No route runs, no detector, no video, no pod, nothing outside tmp_path is written.

a1 and a2 are COVERAGE holes: byte parity already held on master and what was absent was the
ASSERTION, so those two cannot fail on unmutated old code. The other five do.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.platformkit.env_sidecar import SIDECAR_NAME  # noqa: E402
from scripts.platformkit.tracking import census_recomputable as cr  # noqa: E402
from scripts.platformkit.tracking import g310_instance_key  # noqa: E402
from scripts.platformkit.tracking import g327_detector_batch_stability as g327  # noqa: E402
from scripts.platformkit.tracking import g330_run_attempt2 as g330  # noqa: E402
from scripts.platformkit.tracking.g327_arms import (  # noqa: E402
    read_arm_csv, write_arm_csv,
)

FROZEN = 1000000000.0   # gzip stamps time.time() into every member header
SHA_A = "a" * 64
SHA_B = "b" * 64


def _files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _parity(run, dest: Path) -> tuple:
    """Run twice into the SAME dest -- with the sidecar, then opted out -- and diff bytes."""
    out = []
    for opted_out in (False, True):
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        run(opted_out)
        out.append(_files(dest))
    return out


# ---------------------------------------------------------------- HOLE a1
def test_g310_instance_key_opt_out_is_byte_parity(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: FROZEN)
    data = tmp_path / "run"
    data.mkdir()
    (data / "tracking_data.csv").write_text(
        "frame,player_id,bbox_x1,bbox_y1,bbox_x2,bbox_y2\n"
        "1,1,10,10,20,40\n4,1,11,10,21,41\n1,2,50,10,60,40\n", encoding="ascii")
    (data / "ball_tracking.csv").write_text("frame,detected\n1,1\n4,0\n", encoding="ascii")
    dest = tmp_path / "dest"

    def run(opted_out):
        argv = ["g310_instance_key.py", "--run", "r1=%s=%s=720" % (data, data / "log.txt"),
                "--dest", str(dest), "--out-json", str(dest / "proxies.json")]
        monkeypatch.setattr(sys, "argv", argv + (["--no-env-sidecar"] if opted_out else []))
        g310_instance_key.main()

    on, off = _parity(run, dest)
    assert set(on) - set(off) == {SIDECAR_NAME}
    assert set(off) - set(on) == set()
    assert all(on[name] == off[name] for name in off), "the opt-out changed a real output"
    assert off, "the opted-out run wrote nothing at all"


# ---------------------------------------------------------------- HOLE a2
def test_g330_run_attempt2_opt_out_is_byte_parity(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "pod_census.txt").write_text(
        SHA_A + "|100|1.0|/w/nba__0000000001_s1_pano.png\n"
        + SHA_A + "|100|1.0|/w/nba__0000000002_s2_pano.png\n", encoding="ascii")
    box = tmp_path / "box"          # a cwd with no data/ or resources/ to walk
    box.mkdir()
    monkeypatch.chdir(box)
    dest = tmp_path / "evidence"

    def run(opted_out):
        argv = ["prog", str(work), str(dest), "census"]
        assert g330.main(argv + (["--no-env-sidecar"] if opted_out else [])) == 0

    on, off = _parity(run, dest)
    assert set(on) - set(off) == {SIDECAR_NAME}
    assert set(off) == {"census.csv"}
    assert on["census.csv"] == off["census.csv"]


# ---------------------------------------------------------------- HOLE b1
def _snapshot(work: Path) -> list:
    frames = [np.zeros((4, 4, 3), dtype=np.uint8), np.ones((4, 4, 3), dtype=np.uint8)]
    np.save(work / "g.npy", np.stack(frames))
    import hashlib
    return [hashlib.sha256(f.tobytes()).hexdigest() for f in frames]


def _game(name, shas, npy="g.npy", slot=1):
    return {"slot": slot, "game": name, "npy": npy, "frame_indices": [40, 41],
            "frame_sha256": list(shas)}


def test_verify_snapshot_is_fatal_on_a_mismatched_or_missing_frame(tmp_path):
    shas = _snapshot(tmp_path)
    intact = {"games": [_game("g_ok", shas)]}
    assert len(g327.verify_snapshot(intact, tmp_path)) == 1, "an intact snapshot still passes"

    altered = {"games": [_game("g_altered", [shas[0], "f" * 64])]}
    with pytest.raises(ValueError) as mismatch:
        g327.verify_snapshot(altered, tmp_path)
    assert "g_altered" in str(mismatch.value) and "41" in str(mismatch.value)

    absent = {"games": [_game("g_absent", shas, npy="gone.npy", slot=2)]}
    with pytest.raises(ValueError) as missing:
        g327.verify_snapshot(absent, tmp_path)
    assert "g_absent" in str(missing.value) and "gone.npy" in str(missing.value)

    # fatal=False stays reachable and reproduces the landed drop-and-continue (B2).
    reduced = {"games": [_game("g_altered", [shas[0], "f" * 64]), _game("g_ok", shas, slot=3)]}
    kept = g327.verify_snapshot(reduced, tmp_path, fatal=False)
    assert [g["game"] for g, _frames in kept] == ["g_ok"]


# ---------------------------------------------------------------- HOLE b2
def test_read_arm_csv_rejects_a_wholly_mislabelled_arm_file(tmp_path):
    boxes = (np.array([[1.0, 2.0, 3.0, 4.0]]), np.array([0.5]), np.array([0.0]))
    path = tmp_path / "g327a2_boxes_fp32.csv"       # the NAME says fp32 ...
    assert write_arm_csv(path, "batch8", [(1, [7], [boxes])]) == 1   # ... the CELLS say batch8

    with pytest.raises(ValueError) as wrong:
        read_arm_csv(path, expected_arm="fp32")
    assert "batch8" in str(wrong.value) and "fp32" in str(wrong.value)

    order, table = read_arm_csv(path)                       # B2: the old call still parses
    assert order == {1: [7]} and len(table[1][7]) == 1
    assert read_arm_csv(path, expected_arm="batch8")[0] == {1: [7]}


# ---------------------------------------------------------------- HOLE c1
def _memo(root: Path, body: str, name: str = "memo.md") -> str:
    (root / name).write_text("# construct\n" + body + "\n", encoding="ascii")
    return name


def test_a_snapshot_list_without_sha256_and_timestamp_is_unverified(tmp_path):
    import json
    (tmp_path / "loose.json").write_text(
        json.dumps({"snapshots": [{"note": "a"}, {"note": "b"}, {"note": "c"}]}),
        encoding="ascii")
    (tmp_path / "chained.json").write_text(json.dumps({"snapshots": [
        {"sha256": SHA_A, "rows": 5, "at": "2026-09-08T00:00:00Z"},
        {"sha256": SHA_B, "rows": 7, "at": "2026-09-08T00:01:00Z", "parent_sha256": SHA_A}]}),
        encoding="ascii")

    loose = cr.scan_memo(_memo(tmp_path, "The run covered n = 3 rows, per `loose.json`."),
                         tmp_path, construct_only=True)
    assert loose["rows"][0]["verdict"] == cr.UNVERIFIED_SNAPSHOT
    assert loose["rows"][0]["artifacts"] == ["loose.json"]
    assert loose["totals"] == {cr.UNVERIFIED_SNAPSHOT: 1}

    good = cr.scan_memo(
        _memo(tmp_path, "The list carries n = 7 rows, per `chained.json`.", "ok.md"),
        tmp_path, construct_only=True)
    assert good["rows"][0]["verdict"] == cr.RECOMPUTABLE
    assert good["rows"][0]["artifacts"] == ["chained.json"]

    # A component NO artifact reproduces at all is still NOT RECOMPUTABLE, not unverified.
    gone = cr.scan_memo(
        _memo(tmp_path, "The run covered n = 999 rows, per `loose.json`.", "gone.md"),
        tmp_path, construct_only=True)
    assert gone["rows"][0]["verdict"] == cr.NOT_RECOMPUTABLE


# ---------------------------------------------------------------- HOLE c2
def test_a_git_index_failure_raises_unless_construct_only(tmp_path):
    memo = _memo(tmp_path, "The sweep saw n = 3 rows, per `untracked.csv`.")
    (tmp_path / "untracked.csv").write_text("a\n1\n2\n3\n", encoding="ascii")
    probe = subprocess.run(["git", "-C", str(tmp_path), "ls-files"],
                           capture_output=True, text=True)
    assert probe.returncode != 0, "this construct needs a root that is NOT a repository"

    with pytest.raises(RuntimeError) as failed:
        cr.scan_memo(memo, tmp_path)
    assert "git" in str(failed.value).lower()

    walked = cr.scan_memo(memo, tmp_path, construct_only=True)
    assert walked["rows"][0]["verdict"] == cr.RECOMPUTABLE
    assert walked["rows"][0]["artifacts"] == ["untracked.csv"]


# ---------------------------------------------------------------- HOLE c3
def test_a_txt_artifact_counts_lines_only_unless_txt_header(tmp_path):
    txt = tmp_path / "probe.txt"
    txt.write_text("one\ntwo\nthree\n", encoding="ascii")
    assert cr._artifact_values(txt) == {3}
    assert cr._artifact_values(txt, txt_header=True) == {3, 2}

    csv = tmp_path / "probe.csv"                    # CSV keeps both values, as landed
    csv.write_text("head\n1\n2\n3\n", encoding="ascii")
    assert cr._artifact_values(csv) == {4, 3}
