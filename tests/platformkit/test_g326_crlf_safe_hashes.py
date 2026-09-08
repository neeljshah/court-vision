"""G326 -- a text-artifact seal must not depend on the checkout's line endings.

CONSTRUCT, not a sample: T1/T2 enumerate the whole behaviour of the helper, T3/T4 pin the one
site the G326 hash-delta rule permitted converting. Run this file alone; never a full pytest.
"""
import hashlib
import json
from pathlib import Path

from scripts.platformkit.hash_lf import sha256_lf

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact"
ARMS = ("A", "A_repeat", "B", "C")
BODY = "source_frame,player_id,foot_x_px,foot_y_px\n1,7,100.5,200.5\n2,8,300.0,400.0\n"


def _raw(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_crlf_and_lf_files_hash_equal_and_raw_hashing_does_not(tmp_path):
    """T1: the defect, demonstrated -- identical content, two checkouts, two raw digests."""
    lf, crlf = tmp_path / "lf.csv", tmp_path / "crlf.csv"
    lf.write_bytes(BODY.encode("ascii"))
    crlf.write_bytes(BODY.replace("\n", "\r\n").encode("ascii"))
    assert lf.read_bytes() != crlf.read_bytes()
    assert _raw(lf) != _raw(crlf), "raw hashing must be checkout-dependent, else there is no defect"
    assert sha256_lf(lf) == sha256_lf(crlf)


def test_normalization_is_idempotent_and_equals_the_lf_digest(tmp_path):
    """T2: on LF bytes the helper is exactly hashlib.sha256, so no LF seal moves."""
    lf = tmp_path / "lf.csv"
    lf.write_bytes(BODY.encode("ascii"))
    assert sha256_lf(lf) == _raw(lf) == hashlib.sha256(BODY.encode("ascii")).hexdigest()
    lone_cr = tmp_path / "cr.csv"
    lone_cr.write_bytes(b"a\rb\r\nc\n")
    assert sha256_lf(lone_cr) == hashlib.sha256(b"a\rb\nc\n").hexdigest()


def test_converted_g298_detection_seals_reproduce_under_lf_normalization():
    """T3: the committed detections seal is an LF digest, so converting it moved no seal."""
    for arm in ARMS:
        meta = json.loads((OUT / f"{arm}_summary.json").read_text())
        csv = OUT / ("A.csv" if arm == "A_repeat" else f"{arm}.csv")
        assert sha256_lf(csv) == meta["detections_sha256"], arm
        if b"\r\n" in csv.read_bytes():
            assert _raw(csv) != meta["detections_sha256"], f"{arm}: raw hashing must fail on CRLF"


def test_g298_audit_runs_to_completion_on_this_checkout(capsys):
    """T4: the regression the row exists for -- the audit is re-executable from this clone.

    `audit()` rewrites its own `artifact_inventory.json`, a COMMITTED artifact, and that file
    records absolute worktree paths plus the audit module's own raw sha256 -- so running it
    anywhere but the worktree that sealed it dirties the repo. Snapshot and restore the bytes
    so this test leaves the tree exactly as it found it.
    """
    from scripts.platformkit.tracking import g298_audit

    inventory = OUT / "artifact_inventory.json"
    before = inventory.read_bytes()
    try:
        g298_audit.audit()
        assert "PASS" in capsys.readouterr().out
    finally:
        inventory.write_bytes(before)
    assert inventory.read_bytes() == before
