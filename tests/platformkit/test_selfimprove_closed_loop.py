"""Offline closed-loop tests for the self-improve FIXES A-E + the serving seam (FIX C).

ZERO network. Asserts the loop is no longer INERT due to wiring:
  * (A) states_for_game reconstructs leak-free {p0, outcome} rows; settled_games_fn returns
        STATE-BEARING clean games that reach build_candidate.
  * a CANDIDATE is BUILT and the 5-gate ratchet RUNS -- ship-reachable AND a planted-null
        is honestly REJECTED (the gate stays trustworthy; it is NOT weakened).
  * (B) the cursor advances on an armed processed-but-declined cycle, and is PRESERVED while
        inert (so a future-armed batch is not skipped).
  * (C) the serving adapter is a NO-OP unless the sentinel + held-out guard both pass; a
        regressing shipped map is rejected at serve (do-no-harm).
"""
from __future__ import annotations

import sys
import pathlib

import numpy as np
import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve import settled_ingest as SI  # noqa: E402
from scripts.platformkit.improve import recalibrator as RC  # noqa: E402
from scripts.platformkit.improve import served_recal_adapter as SRA  # noqa: E402
from scripts.platformkit.improve import selfimprove_daemon as D  # noqa: E402
from scripts.platformkit.improve import selfimprove_stage as ST  # noqa: E402


# --------------------------------------------------------------------------- FIX A: states
def test_states_for_game_reconstructs_p0_and_outcome_leak_free():
    """A settled final + a pregame prior -> exactly one terminal row {p0, outcome}.

    p0 comes from the PREGAME prior provider (leak-free); outcome from the FINAL score.
    The outcome must NOT influence p0 (leak-free): swapping the final score flips outcome
    but leaves p0 untouched.
    """
    game = {"sport": "nba", "game_id": "E1", "home": "H", "away": "A",
            "home_score": 110.0, "away_score": 101.0}

    def prior(sport, gid):  # injected leak-free pregame prior
        return 0.58

    rows = SI.states_for_game("nba", game, p0_provider=prior)
    assert len(rows) == 1
    r = rows[0]
    assert r["p0"] == 0.58           # the leak-free pregame prior (the BASE)
    assert r["outcome"] == 1.0       # home won (110 > 101)
    assert r["frac_elapsed"] == 1.0  # terminal state

    # leak-free: flip the realized score -> outcome flips, p0 unchanged.
    loss = dict(game, home_score=99.0, away_score=120.0)
    r2 = SI.states_for_game("nba", loss, p0_provider=prior)[0]
    assert r2["outcome"] == 0.0
    assert r2["p0"] == 0.58


def test_states_for_game_no_prior_yields_no_state_never_fabricated():
    """No pregame prior -> no state row (honest empty, never a 0.5 guess)."""
    game = {"sport": "nba", "game_id": "E2", "home_score": 100.0, "away_score": 90.0}
    assert SI.states_for_game("nba", game, p0_provider=lambda s, g: None) == []


def test_states_for_game_tie_or_missing_score_skipped():
    """A tie / absent final score -> no outcome -> skipped (absent != 0)."""
    tie = {"sport": "nba", "game_id": "E3", "home_score": 100.0, "away_score": 100.0}
    assert SI.states_for_game("nba", tie, p0_provider=lambda s, g: 0.5) == []
    noscore = {"sport": "nba", "game_id": "E4"}
    assert SI.states_for_game("nba", noscore, p0_provider=lambda s, g: 0.5) == []


# ------------------------------------------------------ candidate built + gate runs (ship)
def _settled_window(n=40, seed=0, skill=1.4):
    """A clean settled batch whose UNDER-confident base p0 a Platt re-fit can sharpen.

    p0 is a deliberately shrunk-toward-0.5 prior; outcomes follow a sharper truth, so a
    Platt temperature > 1 genuinely improves Brier (ship-reachable). Each game carries a
    game-level outcome + a terminal state row {p0, outcome} (audit-clean).
    """
    rng = np.random.default_rng(seed)
    games = []
    for i in range(n):
        true_p = float(rng.uniform(0.1, 0.9))
        y = 1.0 if rng.random() < true_p else 0.0
        # under-confident base: pull true_p toward 0.5 so a sharpening re-fit helps.
        base = 0.5 + (true_p - 0.5) / skill
        games.append({
            "sport": "nba", "game_id": "S%d" % i, "outcome": y,
            "outcome_confirmed": True,
            "states": [{"p0": base, "outcome": y, "frac_elapsed": 1.0,
                        "outcome_confirmed": True}],
        })
    return games


def test_candidate_built_and_gate_runs_ship_reachable(monkeypatch, tmp_path):
    """ARMED, an honest under-confident window BUILDS a candidate and the gate RUNS.

    With a real 2nd corpus injected the >=2-corpora rule is satisfiable -> SHIP-reachable.
    We do NOT assert a forced ship; we assert the gate actually evaluated (decision is one
    of the real gate outcomes, candidate.oos_improves true, n_rep>=2 achievable).
    """
    # ARM the pipeline via the sentinel (test-injected; never creates the real file).
    monkeypatch.setattr(RC, "pipeline_enabled", lambda *a, **k: True)
    # skip the on-disk grades CLV path; inject a ready 2nd all-positive corpus instead.
    monkeypatch.setattr(
        "scripts.platformkit.ingame.aggregate_clv_to_corpus.inject_grades_corpus",
        lambda cand, **k: cand)

    second_corpus = {"corpus_id": "clv_close", "folds": [{"delta": 0.01}],
                     "all_positive": True}
    cand = RC.build_candidate("nba", _settled_window(seed=1),
                              clv_corpus=second_corpus)
    assert cand is not None, "armed clean window must BUILD a candidate (gate reachable)"
    assert cand["oos_improves"] is True
    # FIX E: the 2nd corpus is wired -> the >=2-corpora rule is now satisfiable.
    assert D._count_replicated_corpora(cand) >= 2

    # the gate actually RUNS on the built candidate (ship-reachable: a real verdict).
    verdict = ST.default_gate_fn(cand)
    assert isinstance(verdict, dict) and "ship" in verdict


# ------------------------------------------------------- planted-null REJECTS (gate honest)
def test_planted_null_rejects_through_the_gate(monkeypatch):
    """A PLANTED NULL (an ALREADY-WELL-CALIBRATED base) must NOT ship -- the gate is honest.

    A recal re-fit on a base whose outcomes already track p0 cannot genuinely beat it OOS;
    any apparent lift is seed-noise. The candidate is BUILT (so the gate RUNS), but the
    gate's seed-stability discipline must REJECT it -- proving the gate is NOT weakened.
    (Contrast: a base that is genuinely MISCALIBRATED is a REAL improvement, not a null --
    so the null here is the calibrated base, the correct calibration-gate null.)
    """
    monkeypatch.setattr(RC, "pipeline_enabled", lambda *a, **k: True)
    monkeypatch.setattr(
        "scripts.platformkit.ingame.aggregate_clv_to_corpus.inject_grades_corpus",
        lambda cand, **k: cand)

    rng = np.random.default_rng(11)
    games = []
    for i in range(400):
        p = float(rng.uniform(0.05, 0.95))      # base IS the truth -> already calibrated
        y = 1.0 if rng.random() < p else 0.0    # outcome tracks p0 -> no real recal lift
        games.append({"sport": "nba", "game_id": "N%d" % i, "outcome": y,
                      "outcome_confirmed": True,
                      "states": [{"p0": p, "outcome": y, "frac_elapsed": 1.0,
                                  "outcome_confirmed": True}]})
    second = {"corpus_id": "clv_close", "folds": [{"delta": 0.01}], "all_positive": True}
    cand = RC.build_candidate("nba", games, clv_corpus=second)
    if cand is None:
        return  # degenerate/no-op guard rejected the null pre-gate -- also an honest reject.
    verdict = ST.default_gate_fn(cand)
    n_rep = D._count_replicated_corpora(cand)
    # the loop SHIP rule (gate.ship AND oos_improves AND >=2 corpora) must NOT fire on a null.
    loop_ship = bool(verdict.get("ship")) and bool(cand.get("oos_improves")) and n_rep >= 2
    assert not loop_ship, ("a calibrated-base NULL must NOT ship -- gate verdict=%s"
                           % verdict.get("reasons"))


# ------------------------------------------------------------------- FIX B: cursor advance
def _run_one_cycle(tmp_path, settled, armed):
    ckpt = str(tmp_path / "ckpt.json")
    import scripts.platformkit.improve.selfimprove_daemon as DD

    def settled_fn(name, *, since="", seen_ids=None, **k):
        return list(settled)

    def recal_fn(name, settled, window):
        return None  # force NO_CANDIDATE to exercise the advance branch

    orig = DD._pipeline_armed
    DD._pipeline_armed = lambda: armed
    try:
        res = DD.run_cycle(name="nba", settled_games_fn=settled_fn,
                           recalibrate_fn=recal_fn, ckpt_path=ckpt,
                           proposals_path=tmp_path / "p.jsonl",
                           reject_path=tmp_path / "r.jsonl",
                           status_path=tmp_path / "s.jsonl", now=1.0)
        from scripts.platformkit.improve.checkpoint import load_checkpoint
        cur = load_checkpoint(ckpt).cursor("nba")
        return res, cur
    finally:
        DD._pipeline_armed = orig


def test_cursor_preserved_while_inert(tmp_path):
    """INERT (sentinel absent): a NO_CANDIDATE batch is PRESERVED (seen_ids untouched)."""
    settled = [{"sport": "nba", "game_id": "G1", "key": "2026-06-10|G1"}]
    res, cur = _run_one_cycle(tmp_path, settled, armed=False)
    assert res.decision == D.NO_CANDIDATE
    assert "G1" not in (cur.get("seen_ids") or [])  # NOT consumed -> re-surfaces when armed


def test_cursor_advances_when_armed_but_declined(tmp_path):
    """ARMED + processed-but-declined: the cursor ADVANCES so the dead batch stops spinning."""
    settled = [{"sport": "nba", "game_id": "G2", "key": "2026-06-10|G2"}]
    res, cur = _run_one_cycle(tmp_path, settled, armed=True)
    assert res.decision == D.NO_CANDIDATE
    assert "G2" in (cur.get("seen_ids") or [])  # consumed -> not re-spun forever


# --------------------------------------------------------- FIX C: serving adapter no-op
def test_serving_adapter_noop_when_sentinel_absent():
    """Sentinel absent -> RAW passthrough, applied=False (byte-identical to today)."""
    raw = [0.6, 0.4, 0.7]
    out = SRA.maybe_apply_shipped("nba", raw, sentinel_fn=lambda: False)
    assert out["applied"] is False
    assert out["status"] == "raw_inert"
    assert out["probs"] == raw


def test_serving_adapter_rejects_regressing_shipped_map():
    """Armed + shipped, but the map REGRESSES held-out Brier -> RAW (do-no-harm)."""
    # a shipped map that INVERTS the prob (a=-1) will worsen held-out Brier badly.
    def current_fn(sport, root):
        return {"payload": {"family": "platt", "a": -1.0, "b": 0.0}}

    rng = np.random.default_rng(3)
    hp = np.clip(rng.uniform(0.1, 0.9, 40), 1e-6, 1 - 1e-6)
    hy = (rng.random(40) < hp).astype(float)  # outcomes track hp -> inversion regresses
    out = SRA.maybe_apply_shipped("nba", [0.6, 0.4],
                                  heldout_probs=hp.tolist(),
                                  heldout_outcomes=hy.tolist(),
                                  sentinel_fn=lambda: True, current_fn=current_fn)
    assert out["applied"] is False
    assert out["status"] == "raw_rejected"
    assert out["probs"] == [0.6, 0.4]  # RAW unchanged


def test_serving_adapter_applies_when_all_guards_pass():
    """Armed + shipped + held-out NOT regressed -> the shipped map is applied."""
    # identity-ish map (a=1,b=0) never regresses held-out Brier -> accepted.
    def current_fn(sport, root):
        return {"payload": {"family": "platt", "a": 1.0, "b": 0.0}}

    rng = np.random.default_rng(4)
    hp = np.clip(rng.uniform(0.1, 0.9, 40), 1e-6, 1 - 1e-6)
    hy = (rng.random(40) < hp).astype(float)
    out = SRA.maybe_apply_shipped("nba", [0.6, 0.4],
                                  heldout_probs=hp.tolist(),
                                  heldout_outcomes=hy.tolist(),
                                  sentinel_fn=lambda: True, current_fn=current_fn)
    assert out["applied"] is True
    assert out["status"] == "applied"
    assert len(out["probs"]) == 2


def test_serving_adapter_insufficient_heldout_is_noop():
    """Too-thin a held-out window -> never trust the map -> RAW passthrough."""
    def current_fn(sport, root):
        return {"payload": {"family": "platt", "a": 1.0, "b": 0.0}}

    out = SRA.maybe_apply_shipped("nba", [0.6],
                                  heldout_probs=[0.5, 0.5],
                                  heldout_outcomes=[1.0, 0.0],
                                  sentinel_fn=lambda: True, current_fn=current_fn)
    assert out["applied"] is False
    assert out["status"] == "raw_insufficient"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
