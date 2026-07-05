"""Per-file tests for prereg_sha_stamp.

Covers: additive-only write (byte-equality of every other field), idempotence
(re-run with unchanged content does not rewrite), recompute-match (compute_sha
matches what stamp wrote), tamper-detect (editing a field after stamping makes
a fresh recompute mismatch the stamped value), and the refusal path (a crafted
object whose sha would collide-but-differ never silently corrupts other
fields -- proven via the byte-equality guard itself).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/l4/test_prereg_sha_stamp.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.l4.prereg_sha_stamp import compute_sha, stamp

_BASE_OBJ = {
    "component": "l4_context_gate",
    "pre_registered_at": "2026-07-04T16:33:48Z",
    "floors": {"min_games": 30, "min_rows": 300},
    "fail_action": "SCOUTING_ONLY, never wired to predictions",
    "edge_claimed": False,
}


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj, sort_keys=True), encoding="utf-8")
    return p


def test_stamp_adds_only_sha_field(tmp_path):
    p = _write(tmp_path, "prereg.json", _BASE_OBJ)
    snap_dir = tmp_path / "snap"
    result = stamp(p, snap_dir)
    assert result["ok"] is True
    assert result["rewrote"] is True
    after = json.loads(p.read_text(encoding="ascii"))
    minus_sha = {k: v for k, v in after.items() if k != "sha256"}
    assert minus_sha == _BASE_OBJ
    assert after["sha256"] == result["sha256"]


def test_stamp_is_idempotent_on_rerun(tmp_path):
    p = _write(tmp_path, "prereg.json", _BASE_OBJ)
    snap_dir = tmp_path / "snap"
    first = stamp(p, snap_dir)
    assert first["rewrote"] is True
    mtime_after_first = p.stat().st_mtime

    second = stamp(p, snap_dir)
    assert second["ok"] is True
    assert second["rewrote"] is False
    assert second["sha256"] == first["sha256"]
    assert p.stat().st_mtime == mtime_after_first  # no rewrite -> no mtime change


def test_recompute_matches_stamped_value(tmp_path):
    p = _write(tmp_path, "prereg.json", _BASE_OBJ)
    snap_dir = tmp_path / "snap"
    result = stamp(p, snap_dir)
    stamped_obj = json.loads(p.read_text(encoding="ascii"))
    recomputed = compute_sha(stamped_obj)
    assert recomputed == result["sha256"]
    # compute_sha on the ORIGINAL (pre-sha) object must match too -- proves the
    # hash is over content-minus-sha, not an opaque blob.
    assert compute_sha(_BASE_OBJ) == result["sha256"]


def test_tamper_after_stamp_forces_recompute_mismatch(tmp_path):
    p = _write(tmp_path, "prereg.json", _BASE_OBJ)
    snap_dir = tmp_path / "snap"
    result = stamp(p, snap_dir)

    tampered = json.loads(p.read_text(encoding="ascii"))
    tampered["floors"]["min_games"] = 5  # goalpost move after the fact
    recomputed = compute_sha(tampered)
    assert recomputed != result["sha256"]


def test_snapshot_created_on_first_stamp(tmp_path):
    p = _write(tmp_path, "prereg.json", _BASE_OBJ)
    snap_dir = tmp_path / "snap"
    result = stamp(p, snap_dir)
    snap_path = snap_dir / "prereg.json"
    assert snap_path.exists()
    assert result["snapshot_path"] == str(snap_path)
    # snapshot holds the FIRST-SEEN (pre-restamp) content, i.e. still has no
    # sha field mismatch relative to what was written at time of first stamp.
    snap_obj = json.loads(snap_path.read_text(encoding="utf-8"))
    assert snap_obj["sha256"] == result["sha256"]


def test_snapshot_never_overwritten_on_later_stamps(tmp_path):
    p = _write(tmp_path, "prereg.json", _BASE_OBJ)
    snap_dir = tmp_path / "snap"
    stamp(p, snap_dir)
    snap_path = snap_dir / "prereg.json"
    original_snapshot_bytes = snap_path.read_bytes()

    # Mutate the live file directly (simulating a later, different write) then
    # re-stamp -- the snapshot must stay pinned to the first-seen copy.
    mutated = json.loads(p.read_text(encoding="ascii"))
    del mutated["sha256"]
    mutated["floors"]["min_games"] = 999
    p.write_text(json.dumps(mutated, sort_keys=True), encoding="utf-8")
    stamp(p, snap_dir)

    assert snap_path.read_bytes() == original_snapshot_bytes


def test_refusal_path_aborts_without_writing_on_nonadditive_diff(tmp_path, monkeypatch):
    """If the additive-guard comparison would ever find a difference beyond the
    sha field, stamp() must abort (ok=False, reason=refused_nonadditive_change)
    and leave the file untouched -- proven by forcing the internal canonical
    comparison to disagree with itself on the FINAL ("after") call only, so
    the write path is reached but the guard still catches the drift."""
    p = _write(tmp_path, "prereg.json", _BASE_OBJ)
    snap_dir = tmp_path / "snap"
    original_bytes = p.read_bytes()

    import scripts.platformkit.l4.prereg_sha_stamp as mod

    real_canonical = mod._canonical_bytes
    call_count = {"n": 0}

    def _flaky_canonical(obj):
        call_count["n"] += 1
        real = real_canonical(obj)
        # Corrupt only the LAST call stamp() makes to _canonical_bytes (the
        # "after" comparison against the stamped dict) -- every earlier call
        # (before_minus_sha, and the one inside compute_sha) stays real so the
        # sha it writes is still correct; only the final equality check drifts.
        if call_count["n"] == 3:
            return real + b"x"
        return real

    monkeypatch.setattr(mod, "_canonical_bytes", _flaky_canonical)
    result = mod.stamp(p, snap_dir)

    assert result["ok"] is False
    assert result["reason"] == "refused_nonadditive_change"
    assert p.read_bytes() == original_bytes  # untouched


def test_stamp_returns_ok_false_for_non_json_object(tmp_path):
    p = tmp_path / "not_an_object.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    result = stamp(p, tmp_path / "snap")
    assert result["ok"] is False
    assert result["reason"] == "not_a_json_object"


def test_stamp_never_raises_on_missing_file(tmp_path):
    result = stamp(tmp_path / "does_not_exist.json", tmp_path / "snap")
    assert result["ok"] is False
    assert result["reason"] is not None
