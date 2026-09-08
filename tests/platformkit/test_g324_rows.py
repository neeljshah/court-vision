"""G324 per-file test: batching and raw-row durability on SYNTHETIC boxes only.

Pins what this row ADDS over G311 (whose IoU >= 0.5 threshold, greedy one-to-one
matching and both-way agreement asymmetry are already covered by
tests/platformkit/test_g311_proxies.py and are NOT duplicated here):
  - batch-8 chunking covers every frame, in order, last chunk short;
  - the batch-8 and single-image paths yield IDENTICAL box sets for a deterministic
    detector, and `batch_vs_single` reports it rather than assuming it;
  - the raw-row writer emits frame index + xyxy + score + class for EVERY box;
  - a zero-box frame keeps its slot and its share of the denominator on both paths.
No GPU, no model, no I/O beyond one tmp CSV.
"""

import numpy as np

from scripts.platformkit.tracking.g324_arms import (
    BATCH,
    batch_vs_single,
    chunk,
    rows_to_csv,
    run_batched,
    run_single,
)

# frame 2 is deliberately EMPTY: a zero-box frame must never be dropped.
FAKE = {
    0: (np.array([[0.0, 0.0, 10.0, 20.0]]), np.array([0.9]), np.array([0])),
    1: (np.array([[5.0, 5.0, 15.0, 25.0], [1.0, 2.0, 3.0, 4.0]]), np.array([0.8, 0.4]),
        np.array([0, 0])),
    2: (np.zeros((0, 4)), np.zeros(0), np.zeros(0)),
}
FRAMES = [0, 1, 2] * 4 + [0]  # 13 frames -> chunks of 8 + 5


def fake_call(fs):
    """Deterministic synthetic detector: the frame IS its key."""
    return [FAKE[f] for f in fs]


def test_chunk_covers_every_frame_last_chunk_short():
    cs = chunk(FRAMES, BATCH)
    assert [len(c) for c in cs] == [8, 5]
    assert [f for c in cs for f in c] == FRAMES


def test_batched_and_single_agree_on_boxes():
    srows, sms = run_single(FRAMES, fake_call)
    brows, bms = run_batched(FRAMES, fake_call, BATCH)
    assert len(srows) == len(brows) == len(FRAMES)
    for a, b in zip(srows, brows):
        assert np.array_equal(a[0], b[0])
    assert sms is not None and bms is not None
    v = batch_vs_single(srows, brows)
    assert v["identical_box_counts"] is True
    assert v["max_abs_coord_delta_px"] == 0.0


def test_batch_vs_single_reports_a_real_difference():
    srows, _ = run_single(FRAMES, fake_call)
    shifted = [(r[0] + 3.0 if len(r[0]) else r[0], r[1], r[2]) for r in srows]
    assert batch_vs_single(srows, shifted)["max_abs_coord_delta_px"] == 3.0
    dropped = list(srows)
    dropped[1] = (np.zeros((0, 4)), np.zeros(0), np.zeros(0))
    assert batch_vs_single(srows, dropped)["identical_box_counts"] is False


def test_zero_box_frame_keeps_its_slot_on_both_paths():
    srows, _ = run_single(FRAMES, fake_call)
    brows, _ = run_batched(FRAMES, fake_call, BATCH)
    empties = [i for i, r in enumerate(srows) if not len(r[0])]
    assert empties == [2, 5, 8, 11]
    assert [i for i, r in enumerate(brows) if not len(r[0])] == empties
    assert len(srows) == len(FRAMES)  # denominator is FRAMES, not non-empty frames


def test_raw_rows_carry_index_xyxy_score_and_class(tmp_path):
    srows, _ = run_single(FRAMES, fake_call)
    idxs = list(range(100, 100 + len(FRAMES)))
    p = tmp_path / "boxes.csv"
    n = rows_to_csv(srows, idxs, p)
    lines = p.read_text().splitlines()
    assert lines[0] == "frame_index,x1,y1,x2,y2,score,class"
    assert n == len(lines) - 1 == sum(len(r[0]) for r in srows) == 13
    first = lines[1].split(",")
    assert len(first) == 7
    assert first[0] == "100" and float(first[1]) == 0.0 and float(first[5]) == 0.9
    assert first[6] == "0"
    # the empty frame contributes no row but is still in the frame denominator
    assert not any(line.startswith("102,") for line in lines[1:])


def test_wheel_hash_mismatch_invokes_source_build_fallback(tmp_path, monkeypatch):
    """G324-REUSE-FALLBACK (verifier NEW GAP, fix 1b): a wheel whose SHA-256 does
    NOT match the sealed value must call source_build_step, never dead-end at
    REUSE REFUSED. Fix 1c (B2): the REUSE REFUSED status survives as an additive
    `premise_status` alias, and the build runs into a FRESH prefix (verifier NEW
    GAP G324-FALLBACK-INSTALL-IDENTITY), never the original reuse target. Build
    and gate are both mocked -- no real pip/subprocess."""
    import scripts.platformkit.tracking.g324_apache_arm_rebudget as mod

    wheel = tmp_path / "bad.whl"
    wheel.write_bytes(b"not the sealed wheel bytes")
    constraints = tmp_path / "constraints.txt"
    constraints.write_text("")
    target = str(tmp_path / "env")

    calls = []
    monkeypatch.setattr(
        mod, "source_build_step",
        lambda tgt, cons, budget: calls.append((tgt, cons)) or
        {"cmd": "fake-build", "rc": 0, "elapsed_s": 0.0, "tail": "built"})
    monkeypatch.setattr(
        mod, "sh",
        lambda cmd, budget, env=None: {"cmd": " ".join(cmd), "rc": 0, "elapsed_s": 0.0, "tail": ""})

    out = mod.install_premise(str(wheel), target, str(constraints))

    assert len(calls) == 1 and calls[0][1] == str(constraints)
    fallback_target = calls[0][0]
    assert fallback_target != target and fallback_target.startswith(target + "_fallback_")
    assert out["fallback_target"] == fallback_target
    assert out["wheel_reused"] is False
    assert out["source_build_fallback"] is True
    assert out["premise_status"] == "REUSE REFUSED -> SOURCE BUILD FALLBACK"
    assert out["steps"][0]["cmd"] == "fake-build"
    assert out["verdict"] == "PREMISE MET"  # mocked gate rc=0 -- fallback did not refuse the row


def test_fallback_build_failure_blocks_gate_ok_even_if_gate_would_pass(tmp_path, monkeypatch):
    """G324-FALLBACK-INSTALL-IDENTITY (verifier NEW GAP, fix 1c): a failed source
    build must not be masked by a stale import surviving from an earlier populated
    prefix. gate_ok depends on the build step's own rc, not just the gate's rc."""
    import scripts.platformkit.tracking.g324_apache_arm_rebudget as mod

    wheel = tmp_path / "bad.whl"
    wheel.write_bytes(b"still not the sealed wheel bytes")
    constraints = tmp_path / "constraints.txt"
    constraints.write_text("")
    target = str(tmp_path / "env")

    build_calls = []
    monkeypatch.setattr(
        mod, "source_build_step",
        lambda tgt, cons, budget: build_calls.append(tgt) or
        {"cmd": "fake-build", "rc": 1, "elapsed_s": 0.0, "tail": "build failed"})
    # The gate itself is mocked to SUCCEED (rc=0) -- simulating a stale import
    # from an already-populated prefix -- to prove gate_ok still goes False.
    monkeypatch.setattr(
        mod, "sh",
        lambda cmd, budget, env=None: {"cmd": " ".join(cmd), "rc": 0, "elapsed_s": 0.0, "tail": ""})

    out = mod.install_premise(str(wheel), target, str(constraints))

    assert build_calls == [out["fallback_target"]]
    assert out["fallback_target"] != target
    assert out["gate_ok"] is False
    assert out["verdict"].startswith("CLOSED AT LIMIT")
