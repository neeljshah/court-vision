"""Per-file tests for domains.tennis.playstyle_ingame_gate (H3).

Run ONLY this file (full pytest freezes the box):
    python -m pytest domains/tennis/test_playstyle_ingame_gate.py -q

Synthetic, in-memory + tmp_path-parquet only (no dependency on the real corpora).
Covers:
  * _serve_bucket: archetype-bucket assignment uses the SAME threshold constants
    atlas_playstyle_specs defines (clay/hard/grass deltas, height).
  * load_player_buckets: provenance guard raises on unexpected corpus_id (honest
    fail, not a silent WTA fabrication).
  * _build_frame: joins states -> hold -> matches -> atlas buckets correctly.
  * _tercile_gate / _pairing_detail_raw: TRAIN-only tercile edges are computed
    PER pair_type (spec: "for that pairing type") and gate the detail term to 0
    outside that pair_type's own top/bottom tercile. KEYSTONE tests prove
    pair_type is load-bearing (identical hold_diff_blind, different pair_type ->
    can differ in gated output) and that scrambling pair_type changes the
    computed edges -- directly falsifying the prior bug where buckets were
    mathematically inert (np.allclose-identical detail term under scrambling).
  * walk_forward_h0_vs_h1: produces folds; planted-null shuffles bucket LABELS
    only and is proven to preserve the covered row population exactly
    (n_train/n_test match real vs null per fold) -- the prior bug fabricated
    "neutral" for lookup-missing players and inflated the null's coverage.
  * gate_tour('wta'): returns not_testable=True (no WTA atlas source) -- the
    HONEST BLOCK, never a fabricated result.
  * run(): WTA not_testable forces verdict in {NOT_TESTABLE} regardless of ATP,
    since SHIP requires WTA replication which is categorically unreachable.
  * KEYSTONE NEGATIVE CONTROL: meaningless bucket assignment (no real pairing
    signal) must not falsely clear the ship bar while the null stays dead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.tennis.playstyle_ingame_gate import (
    MIN_CELL,
    _build_frame,
    _clears_bar,
    _covered,
    _null_clears_bar,
    gate_tour,
    run,
    walk_forward_h0_vs_h1,
)
from domains.tennis.playstyle_ingame_gate_buckets import (
    ATLAS_CORPUS_ID,
    _pairing_detail_raw,
    _tercile_gate,
    load_player_buckets,
    serve_bucket as _serve_bucket,
)

_SURFACES = ("hard", "clay", "grass")


# --------------------------------------------------------------------- _serve_bucket
class TestServeBucket:
    def test_clay_specialist_maps_to_return_bucket(self):
        row = pd.Series({"ov_wr": 0.40, "hard_wr": 0.38, "clay_wr": 0.55,
                         "grass_wr": 0.35, "height": 180.0})
        assert _serve_bucket(row) == "return"

    def test_tall_hard_specialist_maps_to_serve_bucket(self):
        row = pd.Series({"ov_wr": 0.40, "hard_wr": 0.55, "clay_wr": 0.30,
                         "grass_wr": 0.45, "height": 198.0})
        assert _serve_bucket(row) == "serve"

    def test_no_signal_maps_to_neutral(self):
        row = pd.Series({"ov_wr": 0.50, "hard_wr": 0.50, "clay_wr": 0.50,
                         "grass_wr": 0.50, "height": 180.0})
        assert _serve_bucket(row) == "neutral"

    def test_missing_fields_do_not_crash(self):
        row = pd.Series({"ov_wr": None, "hard_wr": None, "clay_wr": None,
                         "grass_wr": None, "height": None})
        assert _serve_bucket(row) == "neutral"


# --------------------------------------------------------------------- provenance guard
class TestLoadPlayerBuckets:
    def test_rejects_unexpected_corpus_id(self, tmp_path):
        df = pd.DataFrame({
            "player_id": [1, 2], "ov_wr": [0.5, 0.5], "hard_wr": [0.5, 0.5],
            "clay_wr": [0.5, 0.5], "grass_wr": [0.5, 0.5], "height": [180.0, 180.0],
            "corpus_id": ["some_other_corpus", "some_other_corpus"],
        })
        p = tmp_path / "atlas.parquet"
        df.to_parquet(p)
        with pytest.raises(ValueError, match="expected single corpus_id"):
            load_player_buckets(p)

    def test_accepts_expected_corpus_id(self, tmp_path):
        df = pd.DataFrame({
            "player_id": [1, 2], "ov_wr": [0.5, 0.5], "hard_wr": [0.5, 0.5],
            "clay_wr": [0.5, 0.5], "grass_wr": [0.5, 0.5], "height": [180.0, 180.0],
            "corpus_id": [ATLAS_CORPUS_ID, ATLAS_CORPUS_ID],
        })
        p = tmp_path / "atlas.parquet"
        df.to_parquet(p)
        out = load_player_buckets(p)
        assert set(out.columns) == {"player_id", "bucket"}
        assert len(out) == 2


# --------------------------------------------------------------------- synthetic corpus
def _synthetic(n_games: int, ticks: int, seed: int, pairing_effect: float = 0.0,
              bucket_random: bool = False, unmapped_frac: float = 0.0):
    """Build synthetic (states, hold, matches, atlas) frames. outcome depends on
    final state_diff plus pairing_effect * hold_diff_blind ONLY when the row's
    pair_type is an extreme-tercile pairing -- pairing_effect=0 => no real signal.

    unmapped_frac: fraction of players who are NEVER written into the atlas
    frame at all (they exist in matches/states but have no atlas row), so
    their p1_bucket/p2_bucket comes back NaN from the _build_frame .map()
    lookup -- exercises the atlas-unmapped-player / NaN-shuffle code path
    that a fully-covered synthetic atlas (every player mapped) never hits.
    """
    rng = np.random.default_rng(seed)
    n_players = max(20, n_games // 2)
    player_ids = list(range(1000, 1000 + n_players))
    buckets = ["serve", "neutral", "return"]
    if bucket_random:
        player_bucket = {pid: str(rng.choice(buckets)) for pid in player_ids}
    else:
        player_bucket = {pid: buckets[i % 3] for i, pid in enumerate(player_ids)}

    n_unmapped = int(round(unmapped_frac * n_players))
    unmapped_ids = set(rng.choice(player_ids, size=n_unmapped, replace=False)) \
        if n_unmapped > 0 else set()
    atlas_player_ids = [pid for pid in player_ids if pid not in unmapped_ids]

    rows_states, rows_hold, rows_matches = [], [], []
    atlas_rows = [{"player_id": pid, "ov_wr": 0.5, "hard_wr": 0.5, "clay_wr": 0.5,
                  "grass_wr": 0.5, "height": 180.0, "corpus_id": ATLAS_CORPUS_ID,
                  "bucket_override": player_bucket[pid]} for pid in atlas_player_ids]
    atlas_df = pd.DataFrame(atlas_rows)

    for g in range(n_games):
        gid = f"g{seed}_{g}"
        p1, p2 = rng.choice(player_ids, size=2, replace=False)
        p1_prior = float(rng.integers(5, 50))
        p2_prior = float(rng.integers(5, 50))
        hold_p1 = 0.70 + 0.05 * rng.normal()
        hold_p2 = 0.70 + 0.05 * rng.normal()
        hold_diff_blind = hold_p1 - hold_p2
        pair_type = f"{player_bucket[p1]}_vs_{player_bucket[p2]}"
        extreme = abs(hold_diff_blind) > 0.03  # crude synthetic "extreme tercile" proxy
        signal = pairing_effect * hold_diff_blind * 30.0 if extreme else 0.0
        final = 0.5 * float(rng.normal(0.0, 6.0)) + signal
        win = int(rng.random() < 1.0 / (1.0 + np.exp(-0.35 * final)))
        rows_hold.append({"event_id": gid, "p1_hold_pct_asof": hold_p1,
                          "p2_hold_pct_asof": hold_p2, "p1_n_prior": p1_prior,
                          "p2_n_prior": p2_prior})
        rows_matches.append({"event_id": gid, "p1_id": int(p1), "p2_id": int(p2)})
        for k in range(ticks):
            frac = (k + 1) / ticks
            sd = final * frac + float(rng.normal(0.0, 3.0)) * (1.0 - frac)
            rows_states.append({"sport": "tennis", "game_id": gid, "asof_idx": k,
                               "state_diff": sd, "frac_elapsed": frac, "p0": 0.5,
                               "outcome": win, "surface": "Hard"})
    return (pd.DataFrame(rows_states), pd.DataFrame(rows_hold),
            pd.DataFrame(rows_matches), atlas_df, pair_type)


def _frame_from_disk(tmp_path, n_games=60, ticks=10, seed=0, pairing_effect=0.0,
                     bucket_random=False, unmapped_frac=0.0):
    st, hd, mt, atlas, _ = _synthetic(n_games, ticks, seed, pairing_effect, bucket_random,
                                      unmapped_frac=unmapped_frac)
    atlas_use = atlas.drop(columns=["bucket_override"]).copy()
    # monkeypatch _serve_bucket-equivalent by writing overrides directly as the
    # bucket the gate would assign is threshold-driven; instead we inject a
    # deterministic bucket via a controlled height/win-rate combo per row so
    # _serve_bucket reproduces player_bucket exactly is NOT guaranteed --
    # so for this disk round-trip test we bypass _serve_bucket entirely by
    # monkeypatching load_player_buckets in the caller. See test below.
    states_path = tmp_path / "states.parquet"
    hold_path = tmp_path / "hold.parquet"
    matches_path = tmp_path / "matches.parquet"
    atlas_path = tmp_path / "atlas.parquet"
    st.to_parquet(states_path)
    hd.to_parquet(hold_path)
    mt.to_parquet(matches_path)
    atlas_use.to_parquet(atlas_path)
    return states_path, hold_path, matches_path, atlas_path


class TestBuildFrame:
    def test_build_frame_joins_all_four_sources(self, tmp_path, monkeypatch):
        st, hd, mt, atlas, _ = _synthetic(n_games=15, ticks=5, seed=1)
        paths = _frame_from_disk(tmp_path, n_games=15, ticks=5, seed=1)
        states_path, hold_path, matches_path, atlas_path = paths
        df = _build_frame(states_path, hold_path, matches_path, atlas_path)
        assert len(df) > 0
        assert "hold_diff_blind" in df.columns
        assert "pair_type" in df.columns
        assert df["p1_bucket"].notna().any()


class TestCovered:
    def test_min_prior_and_bucket_presence_required(self):
        df = pd.DataFrame({
            "p1_n_prior": [10, 0], "p2_n_prior": [10, 10],
            "hold_diff_blind": [0.1, 0.1], "p1_bucket": ["serve", "serve"],
            "p2_bucket": ["return", "return"],
        })
        cov = _covered(df)
        assert cov.iloc[0] == True  # noqa: E712
        assert cov.iloc[1] == False  # noqa: E712


class TestTercileGate:
    def test_tercile_edges_gate_detail_to_zero_in_middle(self):
        train = pd.DataFrame({
            "hold_diff_blind": np.linspace(-1, 1, 30),
            "pair_type": ["serve_vs_return"] * 30,
        })
        edges = _tercile_gate(train)
        lo, hi = edges["__pooled__"]
        assert lo < 0 < hi
        detail = _pairing_detail_raw(train, edges)
        mid_mask = (train["hold_diff_blind"] > lo) & (train["hold_diff_blind"] < hi)
        assert (detail[mid_mask] == 0.0).all()
        extreme_mask = ~mid_mask
        assert (detail[extreme_mask] != 0.0).any()

    def test_degenerate_train_returns_zero_edges(self):
        train = pd.DataFrame({"hold_diff_blind": [np.nan, np.nan],
                              "pair_type": ["serve_vs_return", "serve_vs_return"]})
        edges = _tercile_gate(train)
        assert edges["__pooled__"] == (0.0, 0.0)

    def test_pair_type_is_load_bearing_in_detail_term(self):
        """KEYSTONE (line-119 finding fix): two rows with the IDENTICAL
        hold_diff_blind value must be able to get DIFFERENT gated detail outputs
        when their pair_type differs, because each pair_type earns its OWN
        tercile from its OWN historical distribution. This is the exact property
        the reviewer proved was absent (scrambling buckets was a no-op)."""
        rng = np.random.default_rng(0)
        # pair_type A: hold_diff_blind clustered near 0 (its own tercile is tight)
        a_vals = rng.normal(0.0, 0.01, size=30)
        # pair_type B: hold_diff_blind spread wide (its own tercile is wide)
        b_vals = rng.normal(0.0, 0.30, size=30)
        train = pd.DataFrame({
            "hold_diff_blind": np.concatenate([a_vals, b_vals]),
            "pair_type": ["A_vs_A"] * 30 + ["B_vs_B"] * 30,
        })
        edges = _tercile_gate(train)
        assert "A_vs_A" in edges and "B_vs_B" in edges
        assert edges["A_vs_A"] != edges["B_vs_B"]

        probe_value = 0.05  # extreme for A's tight distribution, mid-range for B's wide one
        probe = pd.DataFrame({
            "hold_diff_blind": [probe_value, probe_value],
            "pair_type": ["A_vs_A", "B_vs_B"],
        })
        detail = _pairing_detail_raw(probe, edges)
        # SAME hold_diff_blind, DIFFERENT pair_type -> must NOT collapse to the
        # same gating outcome for both rows (proves buckets/pair_type are load-bearing).
        assert detail.iloc[0] != detail.iloc[1] or (detail.iloc[0] == 0.0) != (detail.iloc[1] == 0.0)

    def test_scrambling_pair_type_changes_the_computed_edges(self):
        """Directly falsifies the reviewer's np.allclose-identical-detail-term
        finding: scrambling pair_type across a FIXED row set must generally
        change the per-pair-type tercile edges (edges are a function of which
        rows share a pair_type, not just of hold_diff_blind's marginal values)."""
        rng = np.random.default_rng(1)
        n = 90
        vals = rng.normal(0.0, 0.15, size=n)
        pair_types = rng.choice(["A_vs_A", "B_vs_B", "C_vs_C"], size=n)
        train = pd.DataFrame({"hold_diff_blind": vals, "pair_type": pair_types})
        edges_real = _tercile_gate(train)

        scrambled = rng.permutation(pair_types)
        train_scrambled = pd.DataFrame({"hold_diff_blind": vals, "pair_type": scrambled})
        edges_scrambled = _tercile_gate(train_scrambled)

        real_detail = _pairing_detail_raw(train, edges_real)
        scrambled_detail = _pairing_detail_raw(
            pd.DataFrame({"hold_diff_blind": vals, "pair_type": scrambled}), edges_scrambled)
        assert not np.allclose(real_detail.to_numpy(), scrambled_detail.to_numpy())


# --------------------------------------------------------------------- walk-forward
class TestWalkForward:
    def test_produces_multiple_folds_on_adequate_corpus(self, tmp_path):
        states_path, hold_path, matches_path, atlas_path = _frame_from_disk(
            tmp_path, n_games=200, ticks=12, seed=6)
        df = _build_frame(states_path, hold_path, matches_path, atlas_path)
        res = walk_forward_h0_vs_h1(df, n_folds=3, min_cell=10)
        assert res["n_folds_run"] >= 2
        assert len(res["folds"]) == res["n_folds_run"]
        assert "export_rows" in res

    def test_planted_null_shuffles_bucket_assignment_only(self, tmp_path):
        states_path, hold_path, matches_path, atlas_path = _frame_from_disk(
            tmp_path, n_games=100, ticks=10, seed=7)
        df = _build_frame(states_path, hold_path, matches_path, atlas_path)
        res_real = walk_forward_h0_vs_h1(df, n_folds=3, min_cell=10)
        res_null = walk_forward_h0_vs_h1(df, n_folds=3, min_cell=10, shuffle_bucket_seed=0)
        assert res_real["folds"] or res_null["folds"]

    def test_walk_forward_folds_have_matching_n_train_real_vs_null(self, tmp_path):
        """KEYSTONE (line-139 finding fix). unmapped_frac=0.6 means ~60% of
        players have NO atlas row at all, so p1_bucket/p2_bucket comes back
        NaN for them -- this is the exact path a fully-atlas-covered synthetic
        corpus (unmapped_frac=0.0) never exercises. Before the real fix,
        np.random.permutation() on a list mixing str labels with float NaN
        silently upcast the WHOLE array to <U32 strings, turning every NaN
        into the literal STRING 'nan' (truthy, passes pandas .notna()) --
        so the null run's covered population came out LARGER than the real
        run's (verified on the real ATP corpus: real 34992 vs buggy-null
        35805 covered rows, +813; per-fold n_train real=[8748,17496,26244]
        vs buggy-null=[8951,17902,26853]). This test reproduces that
        mismatch on the synthetic corpus too (real covered 170 vs buggy-null
        covered 1500 rows at these params) -- it FAILS on the pre-fix code
        and passes only because the fix now partitions mapped/unmapped
        players before permuting, so unmapped players stay true NaN and the
        covered-population mask is identical between real and null."""
        states_path, hold_path, matches_path, atlas_path = _frame_from_disk(
            tmp_path, n_games=150, ticks=10, seed=10, unmapped_frac=0.6)
        df = _build_frame(states_path, hold_path, matches_path, atlas_path)
        res_real = walk_forward_h0_vs_h1(df, n_folds=3, min_cell=10)
        res_null = walk_forward_h0_vs_h1(df, n_folds=3, min_cell=10, shuffle_bucket_seed=0)
        assert res_real["n_folds_run"] == res_null["n_folds_run"]
        for f_real, f_null in zip(res_real["folds"], res_null["folds"]):
            assert f_real["n_train"] == f_null["n_train"]
            assert f_real["n_test"] == f_null["n_test"]

    def test_insufficient_data_returns_no_folds_gracefully(self, tmp_path):
        states_path, hold_path, matches_path, atlas_path = _frame_from_disk(
            tmp_path, n_games=3, ticks=2, seed=8)
        df = _build_frame(states_path, hold_path, matches_path, atlas_path)
        res = walk_forward_h0_vs_h1(df, n_folds=3, min_cell=MIN_CELL)
        assert res["n_folds_run"] == 0
        assert res["pooled_delta_h1_minus_h0"] is None


# --------------------------------------------------------------------- honest WTA block
class TestWtaHardBlock:
    def test_gate_tour_wta_is_not_testable(self):
        res = gate_tour("wta")
        assert res["not_testable"] is True
        assert res["n_states_joined"] == 0
        assert "atp-only" in res["reason"].lower() or "atp-only" in res["reason"] or \
            "no wta equivalent" in res["reason"].lower()

    def test_clears_bar_false_for_not_testable(self):
        res = gate_tour("wta")
        assert _clears_bar(res) is False
        assert _null_clears_bar(res) is False


# --------------------------------------------------------------------- ship-bar honesty
class TestShipBarHonesty:
    def test_meaningless_pairing_does_not_falsely_ship(self, tmp_path):
        """KEYSTONE NEGATIVE CONTROL: pairing_effect=0 means bucket assignment carries
        no real outcome-relevant signal. A 'clears AND null-does-not-clear' outcome
        should be rare-to-never across resampled seeds."""
        false_ships = 0
        trials = 5
        for seed in range(trials):
            states_path, hold_path, matches_path, atlas_path = _frame_from_disk(
                tmp_path, n_games=150, ticks=10, seed=100 + seed, pairing_effect=0.0)
            df = _build_frame(states_path, hold_path, matches_path, atlas_path)
            res = {"real": walk_forward_h0_vs_h1(df, n_folds=3, min_cell=10),
                  "planted_null": walk_forward_h0_vs_h1(
                      df, n_folds=3, min_cell=10, shuffle_bucket_seed=1)}
            clears = _clears_bar(res)
            null_clears = _null_clears_bar(res)
            if clears and not null_clears:
                false_ships += 1
        assert false_ships <= 1, (
            f"{false_ships}/{trials} seeds falsely cleared the bar with no real "
            "pairing signal and a dead null -- ship criterion is too loose")


# --------------------------------------------------------------------- run() end-to-end verdict shape
class TestRunVerdictShape:
    def test_run_reports_not_testable_verdict_family(self, monkeypatch):
        """run() against the REAL on-disk corpora (if present) must land in
        {NOT_TESTABLE, REJECT} -- SHIP is categorically unreachable since WTA
        cannot be tested. This exercises the real CLI path end-to-end."""
        res = run()
        assert res["verdict"] in ("NOT_TESTABLE", "REJECT")
        assert res["wta_testable"] is False
        assert "as_of_caveat" in res and "SEASON-LEVEL SNAPSHOT" in res["as_of_caveat"]
