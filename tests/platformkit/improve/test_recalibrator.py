"""tests.platformkit.improve.test_recalibrator -- the recal BRIDGE contract (MF1+MF2+MF3).

Asserts:
  (a) MF1 -- sentinel ABSENT -> build_candidate returns None even on a NON-EMPTY,
      foldable settled batch (the kill-switch is the first line; inert when absent).
  (b) MF3 -- a batch with an empty-states game + an all-zero-outcome game has BOTH
      EXCLUDED from the folded y (quarantined), never 0-filled into observations.
  (c) MF2 -- a no-op / collapse candidate -> None with a recorded degenerate reason.
  (d) no $/pnl/roi/edge key anywhere in the candidate dict; carries the calibration
      note + vs_close='UNPROVEN'.

The sentinel is monkeypatched via pipeline_flag.SENTINEL_PATH (never created on real disk).
Per-file test only (full pytest freezes the box). ASCII; stdlib + numpy deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import recalibrator as RC  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402


# --------------------------------------------------------------------------- helpers
def _state(outcome, *, idx=0, p0=0.55):
    s = {"sport": "nba", "game_id": "g", "asof_idx": idx, "p0": p0}
    if outcome is not None:
        s["outcome"] = outcome
    return s


def _good_game(gid, *, label, p0):
    """A foldable game with a confirmed-positive somewhere when label==1.

    The audit (MF3) quarantines any game with NO confirmed-positive state, so a clean
    foldable game must carry at least one outcome==1 state. We attach a (p0, outcome)
    per-state observation: a win-state (1) and a loss-state (0) so the folded window
    carries BOTH classes while still passing the audit (the win state is the confirmed
    positive). p0 is the BASE probability the candidate must recalibrate.
    """
    return {"sport": "nba", "game_id": gid, "outcome": 1.0,
            "states": [_state(1.0, idx=0, p0=p0),
                       _state(0.0, idx=1, p0=1.0 - p0)]}


def _settled_batch():
    """A miscalibrated, well-formed batch with >= _MIN_OBS clean obs and BOTH classes,
    so a Platt fit is genuine (non-degenerate). Win-states sit at a low p0 and loss-states
    at the complementary high p0, so recalibration actually MOVES the predictions
    (not a no-op) and the audit folds every game (each has a confirmed-positive state)."""
    return [_good_game("G%d" % i, label=1, p0=0.35) for i in range(8)]


def _enable(monkeypatch, tmp_path):
    """Create the sentinel on a tmp path and point pipeline_flag at it (flag ON)."""
    sentinel = tmp_path / "PIPELINE_ENABLED"
    sentinel.write_text("on", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", sentinel)
    return sentinel


# ---------------------------------------------------------- path regression guard
def test_real_sentinel_path_resolves_under_repo_root():
    """Guard the parents[3] root: the REAL (unpatched) SENTINEL_PATH must resolve to
    the DOCUMENTED location under the repo, nba-ai-system/data/cache/improve/
    PIPELINE_ENABLED. A parents[4] regression points one level ABOVE the repo, so the
    human-created kill-switch sentinel would never be seen. The other MF1 tests
    monkeypatch SENTINEL_PATH to a tmp path and so cannot catch that defect -- this one
    inspects the real module constant directly."""
    real = PF.SENTINEL_PATH.resolve()
    tail = ("nba-ai-system", "data", "cache", "improve", "PIPELINE_ENABLED")
    assert real.parts[-len(tail):] == tail, (
        "SENTINEL_PATH %s must resolve under nba-ai-system/data/cache/improve" % real)
    # The sentinel must sit beside this test's repo root (parents[3] == repo root).
    assert real == (PROJECT_DIR / "data" / "cache" / "improve" / "PIPELINE_ENABLED")


# --------------------------------------------------------------------------- (a) MF1
def test_sentinel_absent_returns_none_even_with_nonempty_batch(monkeypatch, tmp_path):
    # Point the sentinel at a path that does NOT exist (flag OFF).
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    assert PF.pipeline_enabled() is False
    out = RC.build_candidate("nba", _settled_batch())
    assert out is None  # inert: kill-switch is the first line, even on a full batch.


# --------------------------------------------------------------------------- (b) MF3
def test_quarantined_games_excluded_from_folded_y(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    empty = {"sport": "nba", "game_id": "EMPTY", "outcome": 1.0, "states": []}
    allzero = {"sport": "nba", "game_id": "ALLZERO", "outcome": 0.0,
               "states": [_state(0.0, idx=0, p0=0.6), _state(0.0, idx=1, p0=0.6)]}
    # majority good so the feed is not degraded; the 2 bad games must be quarantined.
    batch = [empty, allzero] + _settled_batch()
    cand = RC.build_candidate("nba", batch)
    assert cand is not None
    # The quarantined games contributed NO observations: only clean p0=0.35/0.65 rows
    # are present. An empty-states game contributes nothing; an all-zero game (p0=0.6)
    # would show 0.6 -- assert that NEITHER quarantined signature leaked into the fold.
    base = cand["base_preds"]
    assert all(abs(b - 0.6) > 1e-9 for b in base)  # all-zero game's p0=0.6 never folded
    assert cand["n_quarantined"] == 2
    assert cand["n_clean"] == len(_settled_batch())
    # y is never 0-filled with the quarantined labels: count of clean obs only.
    assert len(cand["y"]) == len(base)


def test_degraded_feed_returns_none(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    # all-bad batch -> audit raises FeedDegradedError -> NO_CANDIDATE (never 0-fill).
    bad = [{"sport": "nba", "game_id": "E1", "outcome": 1.0, "states": []},
           {"sport": "nba", "game_id": "Z1", "outcome": 0.0,
            "states": [_state(0.0, p0=0.6)]}]
    assert RC.build_candidate("nba", bad) is None


# --------------------------------------------------------------------------- (c) MF2
def test_noop_candidate_rejected_with_degenerate_reason(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    # A perfectly-calibrated batch: p0 already equals the empirical rate, so a Platt
    # re-fit is (within noise) the identity -> degenerate no-op -> None.
    games = []
    for i in range(20):
        # half the p0=0.5 games win, half lose -> base already calibrated -> identity fit.
        games.append(_good_game("W%d" % i, label=(i % 2), p0=0.5))
    out = RC.build_candidate("nba", games)
    assert out is None  # MF2: a no-op / collapsed candidate is an honest REJECT.


def test_cold_start_too_few_obs_returns_none(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tiny = [_good_game("W0", label=1, p0=0.4)]  # 2 obs < _MIN_OBS
    assert RC.build_candidate("nba", tiny) is None


# --------------------------------------------------------------------------- (d) no $
def test_candidate_has_no_dollar_keys_and_carries_calibration_note(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cand = RC.build_candidate("nba", _settled_batch())
    assert cand is not None

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower()
                assert not any(tok in kl for tok in ("roi", "pnl", "dollar", "edge", "$")), \
                    "forbidden $-edge key: %s" % k
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                _walk(v)

    _walk(cand)
    assert cand["note"] == "calibration, not edge"
    assert cand["vs_close"] == "UNPROVEN"
    # shape the gate consumes is present.
    for key in ("base_preds", "cand_preds", "y", "fold_results", "stability_metric_fn",
                "artifact", "payload"):
        assert key in cand


# ------------------------------------------- (e) CLV settled-close 2nd-corpus bridge
# (docs/research/organization-sprint/PROPOSED-clv-corpus-wiring.md -- the ~5-LOC bridge
# already lives in build_candidate via _inject_clv_corpus; these assert its contract.)
def test_clv_corpus_stays_empty_without_a_real_second_corpus(monkeypatch, tmp_path):
    """No on-disk grades and no injected `clv_corpus` kwarg -> corpora stays [] (the
    honest REPLICATION_PENDING baseline is never fabricated into a phantom 2nd corpus).
    """
    _enable(monkeypatch, tmp_path)
    # the on-disk grade-file adapter finds nothing in an empty/nonexistent dir.
    cand = RC.build_candidate("nba", _settled_batch(), grade_dir=tmp_path / "no_grades")
    assert cand is not None
    assert cand["corpora"] == []  # unchanged: no phantom corpus ever fabricated


def test_clv_corpus_injected_via_test_hook_satisfies_two_corpora_rule(monkeypatch, tmp_path):
    """The `clv_corpus` kwarg (offline/test hook documented in _inject_clv_corpus) appends
    a genuine 2nd corpus to `candidate['corpora']` -- the SAME path a real settled-CLV
    close-beats window would take. vs_close stays UNPROVEN regardless (P2 -- the bridge
    NEVER self-stamps an upgrade).
    """
    _enable(monkeypatch, tmp_path)
    second_corpus = {"corpus_id": "clv_settled_close",
                     "folds": [{"delta": 0.01, "metric": "brier"}],
                     "all_positive": True}
    cand = RC.build_candidate("nba", _settled_batch(), clv_corpus=second_corpus)
    assert cand is not None
    assert cand["corpora"] == [second_corpus]
    assert cand["vs_close"] == "UNPROVEN"  # never self-stamped, even with a 2nd corpus


def test_clv_corpus_inject_never_raises_on_a_malformed_hook(monkeypatch, tmp_path):
    """A malformed `clv_corpus` value (not a dict) must be ignored, never crash the
    choke point -- purity: any failure leaves the candidate's corpora UNCHANGED ([])."""
    _enable(monkeypatch, tmp_path)
    cand = RC.build_candidate("nba", _settled_batch(), clv_corpus="not-a-dict")
    assert cand is not None
    assert cand["corpora"] == []


# --------------------------------------- (f) do-no-harm chronological HOLDOUT gate
# gap-ledger rank 4: the highest-risk untested behavior -- a candidate that looks
# like a genuine improvement IN-SAMPLE (fit on all rows) must still be REFUSED when
# a genuine chronological holdout (recal_holdout_fit.fit_and_score, train=earlier
# rows, test=later rows) shows the map does NOT generalize. Fixture: 24 "train"
# games where low base p0 always precedes a WIN (base underestimates -> a Platt fit
# learns to shift predictions UP), followed by 8 chronologically-later "test" games
# at the SAME base p0 range whose true regime has FLIPPED (always a LOSS) -- the
# up-shifting map is disastrous on those held-out rows even though it "improves"
# when scored back on the very data it was fit on.
def _regime_shift_batch():
    """24 train obs (low p0 -> win, miscalibrated low) + 8 chronologically-later
    test obs (SAME p0 range, but the true regime flips to always-loss). Each
    observation is its OWN confirmed-outcome game so MF3 never quarantines it
    regardless of the (0 or 1) label -- the honesty audit is not what this test
    exercises; the holdout gate is."""
    import numpy as _np
    games = []
    p0_train = _np.linspace(0.20, 0.45, 24)
    for i, p0 in enumerate(p0_train):
        y = 0.0 if i < 4 else 1.0  # mostly wins -> base (0.2-0.45) underestimates
        games.append({"sport": "nba", "game_id": "TR%d" % i, "outcome": y,
                     "outcome_confirmed": True,
                     "states": [{"p0": float(p0), "outcome": y}]})
    p0_test = _np.linspace(0.20, 0.45, 8)
    for i, p0 in enumerate(p0_test):
        games.append({"sport": "nba", "game_id": "TE%d" % i, "outcome": 0.0,
                     "outcome_confirmed": True,
                     "states": [{"p0": float(p0), "outcome": 0.0}]})  # regime flipped
    return games


def test_holdout_gate_refuses_when_in_sample_improves_but_oos_regime_shifted(
    monkeypatch, tmp_path,
):
    """The naive in-sample check (fit on ALL rows, score back on ALL rows) WOULD
    show an improvement here -- proving this fixture is a genuine "looks good
    in-sample" trap -- but the real chronological holdout (train=first 24,
    test=last 8) catches the regime shift and the gate must REFUSE (None,
    reason=holdout_insufficient_data is NOT it -- reason must be the genuine
    holdout_no_oos_gain decline, never a fabricated ship)."""
    import numpy as _np
    from scripts.platformkit.eval_gate.scoring import brier as _brier

    _enable(monkeypatch, tmp_path)
    batch = _regime_shift_batch()

    # Prove the "in-sample improves" half of the trap directly against the
    # module's own fit helpers (same math build_candidate uses internally).
    base_list, y_list = RC._extract_obs(batch)
    base_arr = RC._clip01(_np.asarray(base_list, dtype=float))
    y_arr = _np.asarray(y_list, dtype=float)
    ab = RC._fit_platt(base_arr, y_arr)
    assert ab is not None
    cand_arr = RC._apply_platt(base_arr, ab)
    in_sample_base_brier = _brier(base_arr.tolist(), y_arr.tolist())
    in_sample_cand_brier = _brier(cand_arr.tolist(), y_arr.tolist())
    assert in_sample_cand_brier < in_sample_base_brier  # the in-sample trap: looks better

    # The real gate must still REFUSE: chronological holdout shows the shifted-up
    # map is worse on the later (regime-flipped) rows than the untouched base.
    report: dict = {}
    out = RC.build_candidate("nba", batch, report=report)
    assert out is None
    assert report["reason"] == "holdout_no_oos_gain"
    assert report["transient"] is False  # a GENUINE evaluated decline, never retried


def test_holdout_gate_accepts_a_genuine_oos_improvement(monkeypatch, tmp_path):
    """Companion accept path: _settled_batch() (16 clean obs, consistent
    miscalibration across the whole window) passes the REAL chronological holdout
    -- oos_improves True -- and the gate ships a candidate carrying that verdict."""
    from scripts.platformkit.improve.recal_holdout_fit import fit_and_score, STATUS_OK

    base_list, y_list = RC._extract_obs(_settled_batch())
    holdout = fit_and_score(base_list, y_list)
    assert holdout["status"] == STATUS_OK
    assert holdout["oos_improves"] is True  # sanity: this fixture is a genuine OOS win

    _enable(monkeypatch, tmp_path)
    report: dict = {}
    cand = RC.build_candidate("nba", _settled_batch(), report=report)
    assert cand is not None
    assert cand["oos_improves"] is True
    assert report["reason"] == "evaluated"
    assert cand["fold_results"][0]["metric"] == "brier_oos"
