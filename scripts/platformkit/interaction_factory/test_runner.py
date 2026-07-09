"""Per-file test for scripts.platformkit.interaction_factory.runner.

Covers the discipline that separates the factory from p-hacking:
 * LEAK-GUARD: build_nba_offense_frame's as-of feature for game t uses ONLY
   strictly-prior games -- the unit's own outcome window is never in its feature.
 * K / cum-K ledger math: only REAL tests (SURVIVES|NULL) advance cum_K;
   NOT_TESTABLE spends none; a re-run dedupes (never re-tests).
 * NOT_TESTABLE path: a template whose feature_builder is unregistered yields
   honest NOT_TESTABLE rows, cum_K flat.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_runner.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import runner as RUN


def _synthetic_offense_df():
    """One player, 3 dated games. rim: g1 1/2, g2 2/2, g3 0/2. The as-of feature
    for a game must reflect ONLY the games strictly before it."""
    return pd.DataFrame([
        {"player_id": 1, "game_id": "g1", "date": "2025-10-01", "total_fgm": 3, "total_fga": 6,
         "above_break_3_fgm": 0, "corner3_fgm": 0, "rim_fgm": 1, "rim_fga": 2},
        {"player_id": 1, "game_id": "g2", "date": "2025-10-03", "total_fgm": 4, "total_fga": 6,
         "above_break_3_fgm": 0, "corner3_fgm": 0, "rim_fgm": 2, "rim_fga": 2},
        {"player_id": 1, "game_id": "g3", "date": "2025-10-05", "total_fgm": 2, "total_fga": 6,
         "above_break_3_fgm": 0, "corner3_fgm": 0, "rim_fgm": 0, "rim_fga": 2},
    ])


def test_asof_feature_is_leak_free():
    frame = RUN.build_nba_offense_frame(
        _synthetic_offense_df(), ["zone_efg_rim"], min_prior_att=1, min_game_fga=1)
    frame = frame.set_index("game_id")
    col = "asof__zone_efg_rim"
    # g1 has no prior games -> NaN (undefined, dropped per-candidate later).
    assert pd.isna(frame.loc["g1", col])
    # g2's as-of = g1's rim eFG = 1/2 = 0.5 (rim has no 3s).
    assert abs(frame.loc["g2", col] - 0.5) < 1e-9
    # g3's as-of = (g1+g2) rim eFG = (1+2)/(2+2) = 0.75 -- excludes g3's own 0/2.
    assert abs(frame.loc["g3", col] - 0.75) < 1e-9


def test_not_testable_when_builder_unregistered(tmp_path):
    # nba_stint_lineup_x_lineup's feature_builder is not registered -> NOT_TESTABLE.
    ledger = tmp_path / "ledger.jsonl"
    rows = RUN.run_batch("nba_stint_lineup_x_lineup", 20, ledger_path=ledger)
    assert rows, "expected at least one candidate row"
    assert all(r["verdict"] == RUN.NOT_TESTABLE for r in rows)
    assert all(r["cum_K"] == 0 for r in rows)  # NOT_TESTABLE spends no budget
    assert all(r["edge_claimed"] is False for r in rows)
    # re-run dedupes: no new rows appended for already-tested candidates.
    again = RUN.run_batch("nba_stint_lineup_x_lineup", 20, ledger_path=ledger)
    assert again == []


def test_cum_k_math_only_real_tests_advance(tmp_path, monkeypatch):
    """First candidate is a real test (fake fit), the rest NOT_TESTABLE. cum_K
    must equal the count of real tests, and the fitter's per-test bar tightens."""
    ledger = tmp_path / "ledger.jsonl"
    tid = "nba_shot_offense_x_offense"

    # Register a build so run_batch treats the frame as available.
    monkeypatch.setitem(RUN._BUILDERS, "nba_player_offense_asof",
                        lambda attrs, tpl: {"frame": pd.DataFrame(), "cluster": "player_id",
                                            "corpus": "syn", "kind": "ols"})
    calls = {"n": 0}

    def fake_fit(build, cand):
        calls["n"] += 1
        # only the very first candidate returns a real fit; others NOT_TESTABLE.
        if calls["n"] == 1:
            return {"effect": 0.02, "p": 0.9, "n": 1000, "term": "fa:fb"}
        return None

    monkeypatch.setattr(RUN, "_fit_candidate", fake_fit)

    rows = RUN.run_batch(tid, 3, ledger_path=ledger)
    assert len(rows) == 3
    real = [r for r in rows if r["verdict"] in (RUN.SURVIVES, RUN.NULL)]
    nt = [r for r in rows if r["verdict"] == RUN.NOT_TESTABLE]
    assert len(real) == 1 and len(nt) == 2
    assert real[0]["cum_K"] == 1  # exactly one real test spent
    # p=0.9 far above eps/cum_K=0.05 -> NULL (an honest recorded success).
    assert real[0]["verdict"] == RUN.NULL
    assert real[0]["alpha_fwer"] == 0.05  # eps_eff(0.05, cum_K=1)

    # ledger persisted + a fresh run dedupes those 3 candidates.
    persisted = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert len(persisted) == 3
    monkeypatch.setattr(RUN, "_fit_candidate", lambda b, c: None)
    more = RUN.run_batch(tid, 3, ledger_path=ledger)
    assert {r["candidate_id"] for r in more}.isdisjoint({r["candidate_id"] for r in rows})
