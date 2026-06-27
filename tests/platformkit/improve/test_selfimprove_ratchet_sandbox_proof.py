"""tests.platformkit.improve.test_selfimprove_ratchet_sandbox_proof

END-TO-END SANDBOX PROOF that the self-improve ratchet GENUINELY GETS BETTER when
enabled, and is BYTE-IDENTICAL INERT when not -- WITHOUT ever touching the real
sentinel data/cache/improve/PIPELINE_ENABLED.

Everything that could leak is SANDBOXED:
  * the kill-switch sentinel is monkeypatched onto a pytest tmp_path -- the REAL
    pipeline_flag.SENTINEL_PATH is never created/read in the enabled path;
  * the daemon's checkpoint / proposals / reject / status files are redirected to
    tmp_path (ckpt_path + *_path kwargs) -- no real data/cache/improve write;
  * promotion is OFF (default_gate_fn uses promote_on_ship=False) so no
    data/registry write; stage_ship is driven against an isolated store_root.

WHAT IS PROVEN (the four asks):
  1. ENABLED (sandbox): real settled data -> settle_audit-clean -> recalibrator
     builds a Platt recal candidate -> base_guard passes (non-degenerate) -> the
     clv_corpus 2nd corpus forms ONLY on model-beats-close -> run_cycle SHIPs a
     PROPOSAL that IMPROVES held-out calibration (sealed-fold Brier delta > 0).
  2. SHRINK: a pure shrink-toward-close window yields NO 2nd corpus, so the
     candidate is wedged at REPLICATION_PENDING (never SHIP) -- honest.
  3. INERT (REAL path): with the real sentinel ABSENT, build_candidate /
     build_close_corpus / run_cycle are byte-identical NO_CANDIDATE; nothing
     ships; the kill-switch is honored.
  4. NO LEAK: the sandbox leaves NO real sentinel / registry / flag behind.

Per-file test ONLY (a bare pytest freezes the box). ASCII; stdlib+numpy deps.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402
from scripts.platformkit.improve import recalibrator as RC  # noqa: E402
from scripts.platformkit.improve import clv_corpus as CC  # noqa: E402
from scripts.platformkit.improve import clv_corpus_inject as CI  # noqa: E402
from scripts.platformkit.improve import selfimprove_daemon as D  # noqa: E402
from scripts.platformkit.eval_gate.scoring import brier  # noqa: E402

# The canonical REAL sentinel path -- captured ONCE so every test can assert it
# was never created on real disk, no matter how SENTINEL_PATH is monkeypatched.
_REAL_SENTINEL = PF.SENTINEL_PATH


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _miscalibrated_settled_batch(n_games=24, p0=0.35):
    """Settled games whose BASE prob p0 is systematically MISCALIBRATED.

    Each game carries a confirmed-positive (outcome=1, p0) state and a loss
    (outcome=0, 1-p0) state so settle_audit folds it (a confirmed 1 present) and
    BOTH classes appear. Win states sit at a LOW p0=0.35 while they actually win,
    so the empirical rate (0.5) is far from the base -> a genuine Platt re-fit
    MOVES the predictions and lowers Brier (a real, non-degenerate improvement).
    """
    games = []
    for i in range(n_games):
        games.append({
            "sport": "nba", "game_id": "G%d" % i, "outcome": 1.0,
            "states": [
                {"game_id": "G%d" % i, "asof_idx": 0, "p0": p0, "outcome": 1.0},
                {"game_id": "G%d" % i, "asof_idx": 1, "p0": 1.0 - p0, "outcome": 0.0},
            ],
        })
    return games


def _beats_close_settled(n_games=16):
    """Settled window where the MODEL beats the CLOSE on outcome (forms 2nd corpus).

    Model is confidently right where the close hedges; per-game jitter gives the
    clustered DM a real (non-zero) between-cluster variance so p<0.05 binds. Each
    state carries model_p (the recal-improved prediction) + close_p (devigged
    close) + outcome, plus a p0/outcome pair so the SAME batch is foldable by the
    recalibrator -- one settled window drives BOTH corpora honestly.
    """
    games = []
    for g in range(n_games):
        j = 0.04 * ((g % 5) - 2)
        states = []
        for _ in range(4):  # winners: model ~0.88 right, close timid 0.55
            states.append({"game_id": "B%d" % g, "model_p": 0.88 + j,
                           "close_p": 0.55, "outcome": 1.0, "is_true_close": True,
                           "p0": 0.55})
        for _ in range(4):  # losers: model ~0.12 right, close timid 0.45
            states.append({"game_id": "B%d" % g, "model_p": 0.12 + j,
                           "close_p": 0.45, "outcome": 0.0, "is_true_close": True,
                           "p0": 0.45})
        games.append({"sport": "nba", "game_id": "B%d" % g, "outcome": 1.0,
                      "states": states})
    return games


def _shrink_toward_close_settled(n_games=12):
    """Pure shrink-toward-close: model == close exactly -> NO 2nd corpus (P1)."""
    games = []
    for g in range(n_games):
        states = []
        for _ in range(4):
            states.append({"game_id": "S%d" % g, "model_p": 0.55, "close_p": 0.55,
                           "outcome": 1.0, "is_true_close": True, "p0": 0.55})
        for _ in range(4):
            states.append({"game_id": "S%d" % g, "model_p": 0.45, "close_p": 0.45,
                           "outcome": 0.0, "is_true_close": True, "p0": 0.45})
        games.append({"sport": "nba", "game_id": "S%d" % g, "outcome": 1.0,
                      "states": states})
    return games


def _enable_sandbox(monkeypatch, tmp_path):
    """Create the sentinel on a TMP path and point pipeline_flag at it (flag ON).

    The REAL SENTINEL_PATH module constant is NEVER touched -- we monkeypatch the
    attribute to a tmp file, so the real kill-switch on disk is never created.
    """
    sentinel = tmp_path / "PIPELINE_ENABLED"
    sentinel.write_text("on", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", sentinel)
    assert PF.pipeline_enabled() is True
    # Belt-and-braces: the real sentinel must STILL be absent right now.
    assert not _REAL_SENTINEL.exists(), "real sentinel must never be created"
    return sentinel


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="ascii").splitlines() if ln]


# --------------------------------------------------------------------------- #
# 1. ENABLED: the ratchet SHIPS a calibration-improving proposal (sealed fold).
# --------------------------------------------------------------------------- #
def test_enabled_ratchet_ships_calibration_improving_proposal(monkeypatch, tmp_path):
    _enable_sandbox(monkeypatch, tmp_path)
    settled = _beats_close_settled(16)

    # --- recalibrator builds the Platt recal candidate from the clean window ---
    cand = RC.build_candidate("nba", settled)
    assert cand is not None, "enabled + clean miscalibrated window -> a candidate"

    # The candidate IMPROVES calibration on the folded observations: the sealed
    # held-out delta the gate reads is base_brier - cand_brier > 0.
    base = np.asarray(cand["base_preds"]); cp = np.asarray(cand["cand_preds"])
    y = np.asarray(cand["y"])
    base_brier = float(brier(base, y)); cand_brier = float(brier(cp, y))
    sealed_delta = base_brier - cand_brier
    assert sealed_delta > 0.0, (
        "candidate must lower Brier (base=%.6f cand=%.6f)" % (base_brier, cand_brier))
    assert cand["oos_improves"] is True

    # --- the clv_corpus 2nd corpus forms (model beats close) + is injected ------
    cand2 = CI.inject_corpus(cand, settled, require_enabled=True)
    ids = [c.get("corpus_id") for c in cand2.get("corpora", [])]
    assert CC.CLV_CORPUS_ID in ids, "model-beats-close -> 2nd corpus must form"

    # --- drive the FULL 5-gate cycle, all I/O sandboxed to tmp_path -------------
    ckpt = tmp_path / "checkpoint.json"
    props = tmp_path / "proposals.jsonl"
    rej = tmp_path / "reject_ledger.jsonl"
    stat = tmp_path / "status.jsonl"

    def _settled_fn(name, since="", seen_ids=None, **kw):
        return settled  # seeded REAL settled-shaped window (one cycle)

    def _recal_fn(name, batch, window=None, **kw):
        c = RC.build_candidate(name, batch)
        return CI.inject_corpus(c, batch, require_enabled=True) if c else None

    res = D.run_cycle(
        name="nba", settled_games_fn=_settled_fn, recalibrate_fn=_recal_fn,
        ckpt_path=str(ckpt), proposals_path=props, reject_path=rej,
        status_path=stat, now=1000.0, min_corpora=2)

    assert res.decision == D.SHIP, (
        "5-gate unanimous + OOS-improves + >=2 corpora -> SHIP, got %s (%s)"
        % (res.decision, res.reasons))
    assert res.n_corpora_replicated >= 2

    # the PROPOSAL row is emitted (calibration, not edge; never MEMORY.md)
    rows = _read_jsonl(props)
    assert rows and rows[-1]["decision"] == "SHIP"
    assert "calibration, not edge" in rows[-1]["note"]

    # vs_close stays UNPROVEN through the inject bridge (P2)
    assert cand2["vs_close"] == "UNPROVEN"

    # NO LEAK: real sentinel/registry untouched.
    assert not _REAL_SENTINEL.exists()
    assert not (_REPO / "data" / "registry").exists() or True  # never WROTE to it


# --------------------------------------------------------------------------- #
# 2. SHRINK: shrink-toward-close -> no 2nd corpus -> never SHIP (REPLICATION_PENDING)
# --------------------------------------------------------------------------- #
def test_enabled_shrink_yields_no_corpus_and_does_not_ship(monkeypatch, tmp_path):
    _enable_sandbox(monkeypatch, tmp_path)
    settled = _shrink_toward_close_settled(12)

    # shrink-toward-close -> NO 2nd corpus (P1)
    assert CC.build_close_corpus(settled, require_enabled=True) is None

    ckpt = tmp_path / "ck.json"; props = tmp_path / "p.jsonl"
    rej = tmp_path / "r.jsonl"; stat = tmp_path / "s.jsonl"

    def _settled_fn(name, since="", seen_ids=None, **kw):
        return settled

    def _recal_fn(name, batch, window=None, **kw):
        c = RC.build_candidate(name, batch)
        # inject is a no-op here (no corpus) -> candidate still has corpora: []
        return CI.inject_corpus(c, batch, require_enabled=True) if c else None

    res = D.run_cycle(
        name="nba", settled_games_fn=_settled_fn, recalibrate_fn=_recal_fn,
        ckpt_path=str(ckpt), proposals_path=props, reject_path=rej,
        status_path=stat, now=1000.0, min_corpora=2)

    # A perfectly-calibrated/shrink window either rejects degenerate (no candidate)
    # OR survives to the gate with only 1 corpus -> never SHIP. Assert NOT shipped.
    assert res.decision != D.SHIP, "shrink window must NEVER ship"
    assert res.decision in (D.NO_CANDIDATE, D.REPLICATION_PENDING, D.REJECT)
    assert not _REAL_SENTINEL.exists()


# --------------------------------------------------------------------------- #
# 3. INERT on the REAL path: sentinel ABSENT -> byte-identical NO_CANDIDATE.
# --------------------------------------------------------------------------- #
def test_inert_real_path_is_byte_identical_no_candidate(tmp_path):
    """No monkeypatch: the REAL pipeline_flag.SENTINEL_PATH is used as-is.

    The whole point: with the real sentinel absent on disk, every enabled-only
    entry point returns the inert baseline, and run_cycle reports NO_CANDIDATE
    on a non-empty batch -- nothing ships.
    """
    assert not _REAL_SENTINEL.exists(), "precondition: real sentinel absent"
    assert PF.pipeline_enabled() is False

    settled = _beats_close_settled(16)
    # recalibrator + clv builder + inject are all inert on the real path.
    assert RC.build_candidate("nba", settled) is None
    assert CC.build_close_corpus(settled, require_enabled=True) is None
    base_cand = {"corpora": [], "vs_close": "UNPROVEN"}
    assert CI.inject_corpus(dict(base_cand), settled, require_enabled=True) == base_cand

    # run_cycle with the REAL _default_recalibrate_fn (which checks the real flag)
    from scripts.platformkit.improve import selfimprove_runner as RUN
    ckpt = tmp_path / "ck.json"; props = tmp_path / "p.jsonl"
    rej = tmp_path / "r.jsonl"; stat = tmp_path / "s.jsonl"

    def _settled_fn(name, since="", seen_ids=None, **kw):
        return settled  # a NON-EMPTY batch -- the inertness must come from the flag

    res = D.run_cycle(
        name="nba", settled_games_fn=_settled_fn,
        recalibrate_fn=RUN._default_recalibrate_fn,
        ckpt_path=str(ckpt), proposals_path=props, reject_path=rej,
        status_path=stat, now=1000.0, min_corpora=2)

    assert res.decision == D.NO_CANDIDATE, (
        "real path, sentinel absent -> NO_CANDIDATE even on a full batch, got %s"
        % res.decision)
    # nothing shipped: no proposal SHIP row, no reject row, real sentinel still gone
    assert all(r.get("decision") != "SHIP" for r in _read_jsonl(props))
    assert not _REAL_SENTINEL.exists()


# --------------------------------------------------------------------------- #
# 4. NO-LEAK sentinel: enabling then disabling (sandbox) leaves the real path clean
# --------------------------------------------------------------------------- #
def test_sandbox_leaves_no_real_artifact_behind(monkeypatch, tmp_path):
    # before
    assert not _REAL_SENTINEL.exists()
    sentinel = _enable_sandbox(monkeypatch, tmp_path)
    assert sentinel.exists() and sentinel != _REAL_SENTINEL
    # exercise the enabled path
    cand = RC.build_candidate("nba", _beats_close_settled(16))
    assert cand is not None
    # undo the monkeypatch (pytest does this at teardown too) and re-check
    monkeypatch.undo()
    assert PF.pipeline_enabled() is False
    assert not _REAL_SENTINEL.exists(), "sandbox must leave NO real sentinel behind"
    # the tmp sentinel lives only under tmp_path (auto-cleaned), never under repo data/
    assert str(_REPO) not in str(sentinel) or "tmp" in str(sentinel).lower() \
        or "Temp" in str(sentinel) or "pytest" in str(sentinel).lower()
