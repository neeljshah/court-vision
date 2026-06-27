"""Per-file tests for the playstyle_corr validation gate (the validation-of-record).

Covers the mandated checks:
  * the gate REJECTS a planted null (shuffled archetype labels carry no real conditioning);
  * POSITIVE CONTROL: a TRUE archetype-conditioned correlation (signal in ONE archetype) SHIPS
    REPLICATED-STABLE under the corrected cell-level label-permutation null (proves the gate is
    not a reject-everything power artifact -- the decisive must-fix of the broken perm null);
  * NEGATIVE CONTROL: label-INDEPENDENT subset co-movement (same signal in EVERY player) does
    NOT ship -- subset structure is killed at the cell level;
  * FREEZE MECHANISM: a forced family planted-null survivor blocks even a true per-cell survivor;
  * leak-free AS-OF: residual de-trend uses pregame OOF (never a same-game actual leak)
    and the gate carries the 'correlation/joint-pricing, not a $ edge' note;
  * FULL stat-pair surface (all 21 C(7,2) pairs), not a single cherry-picked pair;
  * FWER tightens with K (Bonferroni alpha/K shrinks as the search widens).

Synthetic, deterministic corpora -- no network, no real-data dependency.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.signals.playstyle_corr_gate import (
    _STAT_PAIRS, fwer_threshold, parse_spec_archetype, resolve_archetype,
    run_playstyle_corr_gate, SpecVerdict,
)
from scripts.platformkit.improve.candidate_families import FAMILY_PLAYSTYLE_CORR


# --------------------------------------------------------------------- helpers
def _make_corpus(n_games=160, players_per_arch=8, arches=("SPOT_UP_SHOOTER",
                 "THREE_AND_D_WING", "RIM_ROLL_BIG"), planted_signal=0.0, seed=7):
    """Synthetic player-game residual corpus with a controllable archetype-conditioned
    co-movement. planted_signal>0 injects extra pts/reb co-movement for the FIRST archetype
    only -- so a positive-control survives and a null (planted_signal=0) does not."""
    rng = np.random.default_rng(seed)
    rows = []
    pid = 1000
    base_dates = pd.date_range("2025-10-21", periods=n_games, freq="D")
    for ai, arch in enumerate(arches):
        for _ in range(players_per_arch):
            pid += 1
            for gi in range(n_games):
                gid = "G%04d" % gi
                z = float(rng.normal())
                extra = planted_signal if ai == 0 else 0.0
                rp = z * (0.2 + extra) + float(rng.normal(0, 0.5))
                rr = z * (0.2 + extra) + float(rng.normal(0, 0.5))
                row = {"player_id": pid, "game_id": gid, "game_date": base_dates[gi],
                       "archetype": arch, "corpus": "A" if gi % 2 == 0 else "B"}
                for s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                    row["resid_%s" % s] = float(rng.normal())
                row["resid_pts"] = rp
                row["resid_reb"] = rr
                rows.append(row)
    return pd.DataFrame(rows)


def _make_uniform_corpus(n_games=160, players_per_arch=8,
                         arches=("SPOT_UP_SHOOTER", "THREE_AND_D_WING"), seed=4):
    """Pure SUBSET-STRUCTURE null: an IDENTICAL strong pts/reb co-movement injected into EVERY
    player regardless of archetype. The co-movement is real but LABEL-INDEPENDENT, so the
    cell-level label-permutation null must NOT find it archetype-specific -> no survivor (the
    corrected null kills subset structure at the cell level, before the family-freeze tripwire)."""
    rng = np.random.default_rng(seed)
    rows = []
    pid = 1000
    base_dates = pd.date_range("2025-10-21", periods=n_games, freq="D")
    for arch in arches:
        for _ in range(players_per_arch):
            pid += 1
            for gi in range(n_games):
                z = float(rng.normal())
                rp = z * 1.0 + float(rng.normal(0, 0.2))
                rr = z * 1.0 + float(rng.normal(0, 0.2))
                row = {"player_id": pid, "game_id": "G%04d" % gi, "game_date": base_dates[gi],
                       "archetype": arch, "corpus": "A" if gi % 2 == 0 else "B"}
                for s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                    row["resid_%s" % s] = float(rng.normal())
                row["resid_pts"] = rp
                row["resid_reb"] = rr
                rows.append(row)
    return pd.DataFrame(rows)


class _Spec:
    def __init__(self, arch_slug):
        self.family = FAMILY_PLAYSTYLE_CORR
        self.signature = "playstyle_corr=arch:%s|pair:x_y" % arch_slug
        self.scope = "pregame"
        self.target = "win_prob"


# --------------------------------------------------------------------- tests
def test_full_stat_pair_surface_is_21_pairs_not_one():
    # FULL surface, never a single cherry-picked dominant pair.
    assert len(_STAT_PAIRS) == 21
    assert ("pts", "reb") in _STAT_PAIRS and ("ast", "pts") in _STAT_PAIRS
    # all pairs are sorted + distinct.
    assert all(a < b for (a, b) in _STAT_PAIRS)


def test_fwer_tightens_with_k():
    # Bonferroni alpha/K: wider search => strictly stricter bar.
    assert fwer_threshold(1) == pytest.approx(0.05)
    assert fwer_threshold(21) < fwer_threshold(10) < fwer_threshold(1)
    assert fwer_threshold(105) == pytest.approx(0.05 / 105)


def test_gate_rejects_planted_null_shuffled_labels():
    # A null corpus (no archetype-conditioned signal) must NOT yield a REPLICATED-STABLE.
    corpus = _make_corpus(planted_signal=0.0, seed=11)
    specs = [_Spec("spot"), _Spec("3_and_d_wing"), _Spec("rim_running")]
    verds, summ = run_playstyle_corr_gate(specs, corpus=corpus, n_perm=200, seed=3)
    assert summ["corpus_present"] is True
    assert all(v.verdict != "REPLICATED-STABLE" for v in verds), \
        "planted null must not ship a survivor"


def test_positive_control_true_signal_ships_replicated_stable():
    # POSITIVE CONTROL (must-fix #2): a TRUE archetype-conditioned correlation -- strong pts/reb
    # co-movement injected EXCLUSIVELY into ONE archetype -- MUST ship REPLICATED-STABLE under the
    # corrected cell-level label-permutation null, while the other archetypes REJECT. n_perm is
    # set so the perm-p floor 1/(n_perm+1) is below the FWER threshold (alpha/K), else the floor
    # alone would force a reject (a power artifact, not a verdict). This proves the gate CAN ship.
    corpus = _make_corpus(planted_signal=3.0, seed=11)
    specs = [_Spec("spot"), _Spec("3_and_d_wing"), _Spec("rim_running")]
    verds, summ = run_playstyle_corr_gate(specs, corpus=corpus, n_perm=3000, seed=3)
    by = {v.archetype_name: v for v in verds}
    # floor must be below the FWER bar so a true signal is reachable.
    assert 1.0 / (3000 + 1) < summ["fwer_threshold"], "n_perm too low: floor exceeds FWER bar"
    assert by["spot"].verdict == "REPLICATED-STABLE", "true conditioned signal must SHIP"
    assert by["spot"].n_cells_survive >= 1
    assert by["3_and_d_wing"].verdict == "REJECT" and by["rim_running"].verdict == "REJECT", \
        "archetypes WITHOUT the injected signal must REJECT"
    # the planted null (shuffled labels) must reject for the right reason -> family not frozen.
    assert summ["planted_null_survivors"] == 0 and summ["family_frozen"] is False
    assert summ["planted_null_rejects"] is True


def test_subset_structure_does_not_ship_label_independent_comovement():
    # NEGATIVE CONTROL: a real but LABEL-INDEPENDENT co-movement (identical pts/reb co-movement in
    # EVERY player, any archetype) must NOT produce a survivor. The corrected cell-level null
    # recognises the co-movement is reproduced by a random equal-size player set (perm_p ~ 1), so
    # nothing ships -- subset structure is killed at the cell level. This replaces the old
    # conditional family-freeze test, which the corrected null left as a no-op.
    corpus = _make_uniform_corpus(seed=4)
    specs = [_Spec("spot"), _Spec("3_and_d_wing")]
    verds, summ = run_playstyle_corr_gate(specs, corpus=corpus, n_perm=2000, seed=2)
    assert all(v.verdict != "REPLICATED-STABLE" for v in verds), \
        "label-independent subset co-movement must not ship as an archetype edge"
    assert summ["planted_null_rejects"] is True


def test_note_is_correlation_not_dollar_edge():
    corpus = _make_corpus(planted_signal=0.0, seed=5)
    verds, _ = run_playstyle_corr_gate([_Spec("spot")], corpus=corpus, n_perm=50, seed=1)
    assert verds and "not a $ edge" in verds[0].note
    # SpecVerdict carries no $/pnl/roi/edge field (calibration only).
    fields = set(SpecVerdict.__dataclass_fields__)
    assert not (fields & {"pnl", "roi", "edge", "dollars", "ev"})


def test_leak_free_residual_detrend_uses_oof_not_actual():
    # The corpus loader de-trends by pregame OOF (oof_pred), never same-game actual.
    import scripts.platformkit.signals.playstyle_corr_corpus as c
    src = open(c.__file__, encoding="utf-8").read()
    assert "oof_pred" in src, "residual must be de-trended by pregame OOF projection"
    # leak guard: residual subtracts an OOF/player-mean baseline, not the same-game target.
    assert "m[oc].fillna" in src and "actual - pregame OOF" in src


def test_not_bindable_when_name_does_not_resolve():
    # A vault archetype name with no corpus keyword maps to None -> NOT-BINDABLE (not forced).
    assert resolve_archetype("completely unknown concept xyz") is None
    corpus = _make_corpus(planted_signal=0.0, seed=9)
    verds, _ = run_playstyle_corr_gate([_Spec("completely_unknown_concept_xyz")],
                                       corpus=corpus, n_perm=20, seed=1)
    assert verds[0].verdict == "NOT-BINDABLE" and verds[0].bindable is False


def test_parse_and_resolve_spec_archetype():
    assert parse_spec_archetype("playstyle_corr=arch:3_and_d_wing|pair:a_b") == "3_and_d_wing"
    assert resolve_archetype("3_and_d_wing") == "THREE_AND_D_WING"
    assert resolve_archetype("playmaking guard") == "HIGH_AST_PLAYMAKER"


def test_family_freezes_mechanism_blocks_a_per_cell_survivor(monkeypatch):
    # FREEZE MECHANISM (non-conditional, must-fix #2/#3): the prior test was a no-op because the
    # corrected cell-level null already kills subset structure per cell, so a genuine family-level
    # planted-null survivor is hard to construct from synthetic data. Test the mechanism DIRECTLY:
    # force the family planted-null to report a survivor (>0); even a TRUE per-cell survivor (the
    # positive-control corpus) must then be blocked -> REJECT, family_frozen True, null !rejects.
    import scripts.platformkit.signals.playstyle_corr_gate as g
    monkeypatch.setattr(g, "planted_null_survivors", lambda *a, **k: 5)
    corpus = _make_corpus(planted_signal=3.0, seed=11)  # has a real SPOT_UP survivor cell
    verds, summ = g.run_playstyle_corr_gate([_Spec("spot")], corpus=corpus, n_perm=3000, seed=3)
    assert summ["planted_null_survivors"] == 5 and summ["family_frozen"] is True
    assert summ["planted_null_rejects"] is False
    assert all(v.verdict != "REPLICATED-STABLE" for v in verds), \
        "a frozen family must ship nothing, even with a true per-cell survivor"


def test_summary_carries_planted_null_keys():
    corpus = _make_corpus(planted_signal=0.0, seed=6)
    _, summ = run_playstyle_corr_gate([_Spec("spot")], corpus=corpus, n_perm=50, seed=1)
    assert "planted_null_survivors" in summ and "planted_null_rejects" in summ
    assert "family_frozen" in summ


def test_cold_start_corpus_absent_all_not_bindable():
    # corpus explicitly empty -> every spec NOT-BINDABLE, no fabrication.
    empty = pd.DataFrame(columns=["player_id", "game_id", "game_date", "archetype",
                                  "corpus"] + ["resid_%s" % s for s in
                                  ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")])
    verds, summ = run_playstyle_corr_gate([_Spec("spot")], corpus=empty, n_perm=10, seed=1)
    assert all(v.verdict == "NOT-BINDABLE" for v in verds)
