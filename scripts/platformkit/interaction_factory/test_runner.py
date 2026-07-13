"""Per-file test for scripts.platformkit.interaction_factory.runner.

Covers the discipline that separates the factory from p-hacking:
 * LEAK-GUARD: build_nba_offense_frame's as-of feature for game t uses ONLY
   strictly-prior games -- the unit's own outcome window is never in its feature.
 * K / cum-K ledger math: only REAL tests (SURVIVES|NULL) advance cum_K;
   NOT_TESTABLE spends none; a re-run dedupes TERMINAL verdicts only --
   NOT_TESTABLE is non-terminal and legitimately re-enumerates (generator.py
   tested_ids docstring, fixed in f9f62354 so candidates aren't stuck forever
   once their builder lands).
 * NOT_TESTABLE path: a template whose feature_builder is unregistered yields
   honest NOT_TESTABLE rows, cum_K flat.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_runner.py -q
"""
from __future__ import annotations

import json
import threading

import numpy as np
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
    # mlb_pa_attr_x_count_state's feature_builder (mlb_pa_count_state_asof) is
    # still genuinely unregistered -> NOT_TESTABLE (nba_shot_attr_x_state now
    # HAS a real builder -- see test_offense_state_builder_is_registered below).
    ledger = tmp_path / "ledger.jsonl"
    rows = RUN.run_batch("mlb_pa_attr_x_count_state", 20, ledger_path=ledger)
    assert rows, "expected at least one candidate row"
    assert all(r["verdict"] == RUN.NOT_TESTABLE for r in rows)
    assert all(r["cum_K"] == 0 for r in rows)  # NOT_TESTABLE spends no budget
    assert all(r["edge_claimed"] is False for r in rows)
    # additive hypothesis_source field: every written row carries it, default 'blind'.
    assert all(r.get("hypothesis_source") == "blind" for r in rows)
    # NOT_TESTABLE is non-terminal (tested_ids docstring / propose_gate_job.py):
    # a STILL-unregistered builder re-enumerates the SAME candidates every call
    # (never deduped) -- only a terminal verdict (SURVIVES/NULL/...) dedupes.
    again = RUN.run_batch("mlb_pa_attr_x_count_state", 20, ledger_path=ledger)
    assert len(again) == len(rows)
    assert all(r["verdict"] == RUN.NOT_TESTABLE for r in again)


def test_stint_and_pa_builders_are_registered():
    # Task-50 additions: both were previously unregistered (-> NOT_TESTABLE).
    assert "nba_stint_lineup_asof" in RUN._BUILDERS
    assert "mlb_pa_asof" in RUN._BUILDERS


def test_offense_state_builder_is_registered():
    # nba_shot_attr_x_state's feature_builder was unregistered -> NOT_TESTABLE
    # (factory-plumbing fix); now shares _nba_builder with nba_player_offense_asof.
    assert "nba_offense_state_asof" in RUN._BUILDERS
    assert RUN._BUILDERS["nba_offense_state_asof"] is RUN._nba_builder
    assert "clutch_efg" in RUN._NBA_ATTR_COLS


def _synthetic_stint_df():
    """One team, one lineup, 4 chronological stints (+ 1 noise lineup so the
    groupby is exercised). n_on_court==5 throughout."""
    rows = [
        {"game_id": "g1", "team_id": 1, "period": 1, "lineup_key": "A", "n_on_court": 5,
         "start_s": 0.0, "elapsed_s": 100.0, "pts_for": 10, "pts_against": 4},
        {"game_id": "g1", "team_id": 1, "period": 2, "lineup_key": "A", "n_on_court": 5,
         "start_s": 200.0, "elapsed_s": 200.0, "pts_for": 6, "pts_against": 6},
        {"game_id": "g2", "team_id": 1, "period": 1, "lineup_key": "A", "n_on_court": 5,
         "start_s": 0.0, "elapsed_s": 150.0, "pts_for": 8, "pts_against": 8},
        {"game_id": "g2", "team_id": 1, "period": 2, "lineup_key": "A", "n_on_court": 5,
         "start_s": 200.0, "elapsed_s": 120.0, "pts_for": 2, "pts_against": 2},
    ]
    return pd.DataFrame(rows)


def test_nba_stint_frame_is_leak_free():
    frame = RUN.build_nba_stint_frame(_synthetic_stint_df(), ["synergy_residual", "continuity_s"],
                                       min_prior_stints=1)
    frame = frame.reset_index(drop=True)
    # first stint has 0 prior stints for lineup A -> NaN (never defined from nothing).
    assert pd.isna(frame.loc[0, "asof__synergy_residual"])
    assert pd.isna(frame.loc[0, "asof__continuity_s"])
    # 2nd stint's as-of continuity = mean(elapsed_s of stint 1 only) = 100.0.
    assert abs(frame.loc[1, "asof__continuity_s"] - 100.0) < 1e-9
    # y is net_pts, current stint's own outcome -- never folded into its own feature.
    assert frame.loc[0, "y"] == 6  # 10 - 4


def _synthetic_pa_df():
    """One batter facing one pitcher across 3 PAs (2 pitches each); PA1=K,
    PA2=BB, PA3=in-play contact. Chronological by game_pk."""
    rows = []
    for gp, ab, ev, desc1, desc2, ls in [
        (1, 1, "strikeout", "foul", "swinging_strike", None),
        (2, 1, "walk", "ball", "ball", None),
        (3, 1, "single", "foul", "hit_into_play", 95.0),
    ]:
        rows.append({"game_pk": gp, "game_date": "2025-0%d-01" % gp, "at_bat_number": ab,
                      "pitch_number": 1, "pitcher": 9, "batter": 1, "events": None,
                      "description": desc1, "launch_speed": None})
        rows.append({"game_pk": gp, "game_date": "2025-0%d-01" % gp, "at_bat_number": ab,
                      "pitch_number": 2, "pitcher": 9, "batter": 1, "events": ev,
                      "description": desc2, "launch_speed": ls})
    return pd.DataFrame(rows)


def _synthetic_platoon_df():
    """One pitcher, 5 chronological PAs alternating opposing-batter stand:
    R(walk,on-base) / R(K) / L(single,on-base) / L(K) / R(K). Tests the
    per-hand floor + leak-free cumsum-shift together (min_prior_pa_per_hand=1)."""
    rows = []
    for gp, stand, ev, desc in [
        (1, "R", "walk", "ball"),
        (2, "R", "strikeout", "swinging_strike"),
        (3, "L", "single", "hit_into_play"),
        (4, "L", "strikeout", "swinging_strike"),
        (5, "R", "strikeout", "swinging_strike"),
    ]:
        rows.append({"game_pk": gp, "game_date": "2025-0%d-01" % gp, "at_bat_number": 1,
                      "pitch_number": 1, "pitcher": 9, "batter": 1, "stand": stand,
                      "events": ev, "description": desc, "launch_speed": None})
    return pd.DataFrame(rows)


def test_mlb_pa_platoon_split_is_leak_free_and_per_hand_floored():
    frame = RUN.build_mlb_pa_frame(_synthetic_platoon_df(), ["platoon_split"],
                                    min_prior_pa_per_hand=1)
    frame = frame.reset_index(drop=True)
    # PA1-PA3: at least one hand has zero prior PAs -> undefined, never invented.
    assert pd.isna(frame.loc[0, "asof__platoon_split"])
    assert pd.isna(frame.loc[1, "asof__platoon_split"])
    assert pd.isna(frame.loc[2, "asof__platoon_split"])
    # PA4: prior R rate = 1/2 (PA1 on-base, PA2 not), prior L rate = 1/1 (PA3 on-base).
    assert abs(frame.loc[3, "asof__platoon_split"] - (0.5 - 1.0)) < 1e-9
    # PA5: prior R rate = 1/2 (unchanged), prior L rate = 1/2 (PA3 on-base, PA4 not).
    assert abs(frame.loc[4, "asof__platoon_split"] - (0.5 - 0.5)) < 1e-9


def test_mlb_pa_frame_is_leak_free():
    frame = RUN.build_mlb_pa_frame(_synthetic_pa_df(), ["K_avoidance", "BB_rate", "whiff_rate"],
                                    min_prior_pa=1)
    frame = frame.reset_index(drop=True)
    # PA1: no prior PAs for this batter/pitcher -> NaN.
    assert pd.isna(frame.loc[0, "asof__K_avoidance"])
    assert frame.loc[0, "y"] == 1.0  # PA1 outcome is a strikeout
    # PA2's as-of K_avoidance reflects ONLY PA1 (1 K / 1 PA) -> 1 - 1.0 = 0.0.
    assert abs(frame.loc[1, "asof__K_avoidance"] - 0.0) < 1e-9
    assert frame.loc[1, "y"] == 0.0  # PA2 is a walk, not a strikeout
    # PA3's as-of BB_rate reflects PA1+PA2 (1 BB / 2 PA) -> 0.5 -- excludes PA3's own outcome.
    assert abs(frame.loc[2, "asof__BB_rate"] - 0.5) < 1e-9


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

    # ledger persisted. A fresh run dedupes the ONE terminal (real) candidate
    # forever, but legitimately re-enumerates the two NOT_TESTABLE ones --
    # tested_ids() excludes NOT_TESTABLE from the terminal set (generator.py,
    # fixed in f9f62354: a candidate graded NOT_TESTABLE before its builder
    # existed must not be skipped forever once conditions change).
    persisted = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert len(persisted) == 3
    monkeypatch.setattr(RUN, "_fit_candidate", lambda b, c: None)
    more = RUN.run_batch(tid, 3, ledger_path=ledger)
    real_id = real[0]["candidate_id"]
    nt_ids = {r["candidate_id"] for r in nt}
    more_ids = {r["candidate_id"] for r in more}
    assert real_id not in more_ids  # terminal verdict never re-tested
    assert nt_ids <= more_ids  # non-terminal NOT_TESTABLE candidates re-enumerate
    assert all(r["verdict"] == RUN.NOT_TESTABLE for r in more)
    assert all(r["cum_K"] == 1 for r in more)  # no real test ran this batch


def test_run_batch_concurrent_appends_no_dup_rows_sequential_cum_k(tmp_path, monkeypatch):
    """2026-07-13 audit: two writers each reading a stale ledger before either
    appended produced 2 duplicate (candidate_id, verdict, cum_K) rows in
    production (interaction_factory_ledger.jsonl). run_batch now holds
    ledger_lock across read+select+fit+append, so two threads racing the same
    template/ledger must land zero duplicate candidate_ids and a strictly
    sequential cum_K (no repeats, no gaps)."""
    ledger = tmp_path / "ledger.jsonl"
    tid = "nba_shot_offense_x_offense"  # 8-attr self_cross pool -> C(8,2)=28 candidates

    monkeypatch.setitem(RUN._BUILDERS, "nba_player_offense_asof",
                        lambda attrs, tpl: {"frame": pd.DataFrame(), "cluster": "player_id",
                                            "corpus": "syn", "kind": "ols"})
    # Every candidate is a real, fast, deterministic test (-> NULL) so every
    # appended row advances cum_K, maximizing the exercised race window.
    monkeypatch.setattr(RUN, "_fit_candidate",
                        lambda build, cand: {"effect": 0.01, "p": 0.9, "n": 1000, "term": "fa:fb"})

    errors = []

    def worker():
        try:
            RUN.run_batch(tid, 15, ledger_path=ledger)
        except Exception as exc:  # noqa: BLE001 -- surface any thread failure to the test
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    ids = [r["candidate_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate candidate_id rows after concurrent run_batch"
    assert sorted(r["cum_K"] for r in rows) == list(range(1, len(rows) + 1))


def test_task39b_builders_are_registered():
    for key in ("nba_boxdetail_asof", "mlb_battrack_asof", "mlb_pa_archetype_asof",
                "tennis_match_asof", "soccer_match_asof"):
        assert key in RUN._BUILDERS


def test_insufficient_train_history_short_circuits_without_a_fit(tmp_path, monkeypatch):
    # nba_boxdetail's known limitation (train coverage starts after the
    # sibling gate's 70% cutoff) must NOT_TESTABLE every candidate in the
    # batch with the explicit reason, spending no cum_K, never calling _fit_candidate.
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setitem(RUN._BUILDERS, "nba_boxdetail_asof",
                        lambda attrs, tpl: {"frame": None, "cluster": "game_id", "corpus": "boxdetail_asof",
                                             "kind": "logit", "insufficient_train_history": True,
                                             "train_note": "synthetic guard for this test"})

    def _boom(build, cand):
        raise AssertionError("_fit_candidate must not run when insufficient_train_history is set")
    monkeypatch.setattr(RUN, "_fit_candidate", _boom)

    rows = RUN.run_batch("nba_boxdetail_self_cross", 10, ledger_path=ledger)
    assert rows and all(r["verdict"] == RUN.NOT_TESTABLE for r in rows)
    assert all(r["note"].startswith("insufficient_train_history: synthetic guard") for r in rows)
    assert all(r["cum_K"] == 0 for r in rows)


def test_fit_candidate_covariate_and_entity_class_scoping():
    # covariate: 'y ~ cov + fa + fb + fa:fb' -- included column must be present
    # and standardized, never silently dropped. Random (seeded) inputs, not a
    # perfectly-separable pattern, so the logit Hessian stays non-singular.
    rng = np.random.default_rng(0)
    n = 400
    frame = pd.DataFrame({
        "y": rng.integers(0, 2, n).astype(float),
        "asof__a": rng.normal(size=n),
        "asof__b": rng.normal(size=n),
        "p_base": rng.uniform(0.2, 0.8, n),
        "cl": rng.integers(0, 10, n),
    })
    cand = GEN.Candidate(candidate_id="x", template_id="t", sport="basketball_nba",
                         atomic_unit="team_game", outcome="home_win", attr_a="a", attr_b="b",
                         feature_builder="nba_boxdetail_asof")
    build = {"frame": frame, "cluster": "cl", "kind": "logit", "covariate": "p_base"}
    fit = RUN._fit_candidate(build, cand)
    assert fit is not None and "n" in fit

    # entity_class: scoping to an unresolvable class -> NOT_TESTABLE (None), never silently
    # falls back to the unscoped frame.
    build2 = {"frame": frame.assign(team=["X"] * 400), "cluster": "cl", "kind": "logit",
              "archetype_members": {"known_slug": {"X"}}, "entity_col": "team"}
    cand_unknown = GEN.Candidate(candidate_id="y", template_id="t", sport="mlb",
                                 atomic_unit="plate_appearance", outcome="is_k", attr_a="a", attr_b="b",
                                 feature_builder="mlb_pa_archetype_asof", entity_class="unknown_slug")
    assert RUN._fit_candidate(build2, cand_unknown) is None
    cand_known = GEN.Candidate(candidate_id="z", template_id="t", sport="mlb",
                               atomic_unit="plate_appearance", outcome="is_k", attr_a="a", attr_b="b",
                               feature_builder="mlb_pa_archetype_asof", entity_class="known_slug")
    assert RUN._fit_candidate(build2, cand_known) is not None


def test_battrack_frame_joins_season_y_to_season_yplus1_outcome():
    # synthetic overlap (real on-disk corpus currently has none -- see
    # build_mlb_battrack_frame docstring) proves the season-shift join itself.
    profiles = pd.DataFrame([
        {"entity_id": 1, "window": "season_2024", "attribute": "swing_speed", "raw_value": 75.0},
        {"entity_id": 1, "window": "season_2025", "attribute": "contact_quality", "raw_value": 0.4},
        {"entity_id": 2, "window": "season_2024", "attribute": "swing_speed", "raw_value": 70.0},
        {"entity_id": 2, "window": "season_2026", "attribute": "contact_quality", "raw_value": 0.1},  # wrong year, no match
    ])
    frame = RUN.build_mlb_battrack_frame(profiles, ["swing_speed"])
    row = frame.set_index("entity_id")
    assert row.loc[1, "y"] == 0.4 and row.loc[1, "asof__swing_speed"] == 75.0
    assert 2 not in row.index  # season_2024 -> needs outcome at season_2025, batter 2 only has season_2026


def test_pa_archetype_frame_derives_batting_team_from_topbot():
    pitch_df = pd.DataFrame([
        {"game_pk": 1, "at_bat_number": 1, "pitch_number": 1, "pitcher": 9, "batter": 1,
         "game_date": "2025-04-01", "events": "strikeout", "description": "swinging_strike", "launch_speed": None,
         "home_team": "NYY", "away_team": "BOS", "inning_topbot": "Top"},
        {"game_pk": 1, "at_bat_number": 2, "pitch_number": 1, "pitcher": 5, "batter": 2,
         "game_date": "2025-04-01", "events": "walk", "description": "ball", "launch_speed": None,
         "home_team": "NYY", "away_team": "BOS", "inning_topbot": "Bot"},
    ])
    frame = RUN.build_mlb_pa_archetype_frame(pitch_df, ["K_avoidance"])
    teams = frame.set_index("at_bat_number")["team"]
    assert teams.loc[1] == "BOS"  # top half -> away team bats
    assert teams.loc[2] == "NYY"  # bottom half -> home team bats


def test_tennis_and_soccer_match_frames_derive_win_target():
    matches = pd.DataFrame([
        {"event_id": "e1", "tourney_id": "t1", "winner": 1},
        {"event_id": "e2", "tourney_id": "t1", "winner": 2},
    ])
    ret = pd.DataFrame([{"event_id": "e1", "diff_return_won_asof": 0.1},
                        {"event_id": "e2", "diff_return_won_asof": -0.2}])
    feats = pd.DataFrame([{"event_id": "e1", "diff_ace_rate_asof": 0.05},
                          {"event_id": "e2", "diff_ace_rate_asof": -0.01}])
    tframe = RUN.build_tennis_match_frame(matches, ret, feats, ["diff_return_won_asof", "diff_ace_rate_asof"])
    y = tframe.set_index("event_id")["y"]
    assert y.loc["e1"] == 1.0 and y.loc["e2"] == 0.0

    soc_matches = pd.DataFrame([{"event_id": "s1", "div": "E1", "fthg": 2, "ftag": 1},
                                {"event_id": "s2", "div": "E1", "fthg": 0, "ftag": 3}])
    soc_feats = pd.DataFrame([{"event_id": "s1", "diff_sot_for_asof": 1.5},
                              {"event_id": "s2", "diff_sot_for_asof": -0.5}])
    sframe = RUN.build_soccer_match_frame(soc_matches, soc_feats, ["diff_sot_for_asof"])
    ys = sframe.set_index("event_id")["y"]
    assert ys.loc["s1"] == 1.0 and ys.loc["s2"] == 0.0
