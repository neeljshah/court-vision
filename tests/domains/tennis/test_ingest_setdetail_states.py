"""tests/domains/tennis/test_ingest_setdetail_states.py

Per-file tests for the tennis per-SET / TIEBREAK trailing as-of layer
(domains/tennis/ingest_setdetail_states.py).  CEILING-CONFIRMING layer.

Covers exactly the four required contracts:
  1. SCHEMA      -- frozen base key (event_id) present + all additive as-of cols.
  2. LEAK-FREE   -- no future / no match-final / no current-match leakage; the
                    embedded no-future-leak assertion fires on a planted leak.
  3. AS-OF-MONOTONIC -- the row uses ONLY prior matches (shift1): debut -> NaN,
                    match-2 value equals the prior match's realized quantity, and
                    a player's own current set NEVER enters its own row.
  4. PARITY      -- one builder; train rows and inference rows from the SAME
                    function are byte-identical for a shared event_id.

Pure pandas/numpy; no src/ / kernel/ / api imports.  ASCII only.  Fast.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import domains.tennis.ingest_setdetail_states as isd
from domains.tennis.ingest_setdetail_states import (
    OUT_COLS,
    _METRICS,
    _SURFACES,
    assert_no_future_leak,
    build_asof_setdetail,
    match_realized,
    parse_sets_detail,
)


# ---------------------------------------------------------------------------
# Synthetic fixture builder
# ---------------------------------------------------------------------------
def _make_matches(rows: list[dict]) -> pd.DataFrame:
    defaults = {"date": "2020-01-01", "tour": "atp", "tourney_id": "T001",
                "round": "R32", "match_num": 1, "surface": "Hard",
                "winner": 1, "score": "6-3 6-3", "retirement": False}
    records = []
    for i, r in enumerate(rows):
        base = {**defaults, "event_id": f"evt-{i:04d}"}
        base.update(r)
        records.append(base)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 1. SCHEMA
# ---------------------------------------------------------------------------
class TestSchema:
    def test_frozen_base_key_present(self):
        mt = _make_matches([{"p1_id": 1, "p2_id": 2}])
        df = build_asof_setdetail(mt)
        assert "event_id" in df.columns
        # 1:1 to matches (frozen base contract).
        assert len(df) == len(mt)
        assert df["event_id"].is_unique

    def test_all_additive_cols_present_and_exact(self):
        mt = _make_matches([
            {"p1_id": 1, "p2_id": 2, "date": "2020-01-01"},
            {"p1_id": 1, "p2_id": 3, "date": "2020-01-02"},
        ])
        df = build_asof_setdetail(mt)
        assert list(df.columns) == OUT_COLS, f"col mismatch: {list(df.columns)}"
        # Every metric has p1/p2 overall, a diff, and 3 surface splits per side.
        for m in _METRICS:
            assert f"p1_{m}_asof" in df.columns
            assert f"p2_{m}_asof" in df.columns
            assert f"{m}_asof_diff" in df.columns
            for s in _SURFACES:
                assert f"p1_{m}_{s.lower()}_asof" in df.columns
                assert f"p2_{m}_{s.lower()}_asof" in df.columns

    def test_n_prior_int_dtype(self):
        df = build_asof_setdetail(_make_matches([{"p1_id": 1, "p2_id": 2}]))
        assert df["p1_n_prior"].dtype == np.int64
        assert df["p2_n_prior"].dtype == np.int64

    def test_parse_sets_detail_tiebreak_flag(self):
        # WINNER-first; tiebreak notation '(.)' flips the is_tiebreak flag.
        assert parse_sets_detail("6-7(5) 7-6(6) 6-1") == [
            (6, 7, True), (7, 6, True), (6, 1, False)]
        assert parse_sets_detail("6-3 6-1") == [(6, 3, False), (6, 1, False)]
        assert parse_sets_detail("") is None
        assert parse_sets_detail(None) is None


# ---------------------------------------------------------------------------
# 2. LEAK-FREE
# ---------------------------------------------------------------------------
class TestLeakFree:
    def test_assert_passes_when_clean(self):
        df = pd.DataFrame({
            "p1_n_prior": [0, 1], "p2_n_prior": [0, 1],
            **{f"p1_{m}_asof": [np.nan, 0.5] for m in _METRICS},
            **{f"p2_{m}_asof": [np.nan, 0.5] for m in _METRICS},
        })
        assert_no_future_leak(df)  # must not raise

    def test_assert_raises_on_planted_debut_leak(self):
        # A debut row (n_prior==0) carrying a non-NaN as-of value IS a leak.
        df = pd.DataFrame({
            "p1_n_prior": [0, 1], "p2_n_prior": [0, 1],
            **{f"p1_{m}_asof": [0.9, 0.5] for m in _METRICS},   # planted leak
            **{f"p2_{m}_asof": [np.nan, 0.5] for m in _METRICS},
        })
        with pytest.raises(AssertionError, match="Future-leak"):
            assert_no_future_leak(df)

    def test_build_output_passes_leak_assertion(self):
        mt = _make_matches([
            {"p1_id": 100, "p2_id": 200, "date": "2020-01-01"},
            {"p1_id": 100, "p2_id": 300, "date": "2020-01-02"},
            {"p1_id": 200, "p2_id": 300, "date": "2020-01-03"},
        ])
        df = build_asof_setdetail(mt)
        assert_no_future_leak(df)

    def test_no_match_final_columns_leak_in(self):
        # The builder must NOT surface winner / minutes / score / odds anywhere.
        df = build_asof_setdetail(_make_matches([{"p1_id": 1, "p2_id": 2}]))
        forbidden = {"winner", "score", "minutes", "close", "odds",
                     "retirement", "bpFaced", "bpSaved"}
        assert forbidden.isdisjoint(set(df.columns))

    def test_current_match_not_in_own_row(self):
        # p1 wins e0 with a tiebreak-set; on e0 (its debut) the as-of MUST be NaN,
        # i.e. the current match's own sets never enter its own row.
        mt = _make_matches([
            {"p1_id": 1, "p2_id": 2, "date": "2020-01-01",
             "winner": 1, "score": "7-6(3) 6-4"},
            {"p1_id": 1, "p2_id": 3, "date": "2020-01-02",
             "winner": 1, "score": "6-2 6-1"},
        ])
        df = build_asof_setdetail(mt)
        e0 = df[df["event_id"] == "evt-0000"].iloc[0]
        for m in _METRICS:
            assert np.isnan(e0[f"p1_{m}_asof"])


# ---------------------------------------------------------------------------
# 3. AS-OF-MONOTONIC (prior-N / shift1 only)
# ---------------------------------------------------------------------------
class TestAsOfMonotonic:
    def test_debut_is_nan_and_zero_prior(self):
        df = build_asof_setdetail(_make_matches([{"p1_id": 1, "p2_id": 2}]))
        row = df.iloc[0]
        assert row["p1_n_prior"] == 0 and row["p2_n_prior"] == 0
        for m in _METRICS:
            assert np.isnan(row[f"p1_{m}_asof"])
            assert np.isnan(row[f"p2_{m}_asof"])

    def test_second_match_reflects_only_prior(self):
        # e0: p1 drops 1 of 2 sets, plays/wins 1 tiebreak, close-set count = 1.
        # On e1, p1's as-of must EXACTLY equal those prior-match realized rates.
        mt = _make_matches([
            {"p1_id": 10, "p2_id": 20, "date": "2020-01-01",
             "winner": 1, "score": "7-6(3) 4-6 6-1"},
            {"p1_id": 10, "p2_id": 30, "date": "2020-01-02",
             "winner": 1, "score": "6-0 6-0"},
        ])
        df = build_asof_setdetail(mt)
        e1 = df[df["event_id"] == "evt-0001"].iloc[0]
        assert e1["p1_n_prior"] == 1
        # Prior match for p1: 3 sets, lost 1 -> dropped 1/3; 1 tiebreak won -> 1.0;
        # close sets (7-6) = 1 of 3.
        assert abs(e1["p1_tiebreak_win_pct_asof"] - 1.0) < 1e-9
        assert abs(e1["p1_sets_dropped_rate_asof"] - (1.0 / 3.0)) < 1e-9
        assert abs(e1["p1_close_set_rate_asof"] - (1.0 / 3.0)) < 1e-9
        # avg games/set: sets were 13,10,7 games -> 30/3 = 10.0
        assert abs(e1["p1_avg_games_per_set_asof"] - 10.0) < 1e-9

    def test_winner_orientation_signed_to_stable_id(self):
        # winner==2: Sackmann score is winner-first, so raw is p2-first and must
        # be swapped so the LOSER (p1) gets the dropped-sets credit.
        mt = _make_matches([
            {"p1_id": 5, "p2_id": 6, "date": "2020-01-01",
             "winner": 2, "score": "6-1 6-1"},  # p2 won both sets
            {"p1_id": 5, "p2_id": 7, "date": "2020-01-02",
             "winner": 1, "score": "6-2 6-2"},
        ])
        df = build_asof_setdetail(mt)
        e1 = df[df["event_id"] == "evt-0001"].iloc[0]
        # p1 LOST both sets in its prior match -> dropped rate 1.0 (not 0.0).
        assert abs(e1["p1_sets_dropped_rate_asof"] - 1.0) < 1e-9

    def test_retirement_skipped_in_update(self):
        # A retired prior match has an unreliable tail; it must NOT update history,
        # so the next match still reads n_prior=0 -> NaN.
        mt = _make_matches([
            {"p1_id": 9, "p2_id": 8, "date": "2020-01-01",
             "winner": 1, "score": "6-1 2-1", "retirement": True},
            {"p1_id": 9, "p2_id": 7, "date": "2020-01-02",
             "winner": 1, "score": "6-2 6-2"},
        ])
        df = build_asof_setdetail(mt)
        e1 = df[df["event_id"] == "evt-0001"].iloc[0]
        assert e1["p1_n_prior"] == 0
        assert np.isnan(e1["p1_sets_dropped_rate_asof"])

    def test_surface_split_only_uses_same_surface(self):
        mt = _make_matches([
            {"p1_id": 1, "p2_id": 2, "date": "2020-01-01", "surface": "Clay",
             "winner": 1, "score": "6-3 6-3"},
            {"p1_id": 1, "p2_id": 3, "date": "2020-01-02", "surface": "Hard"},
        ])
        df = build_asof_setdetail(mt)
        e1 = df[df["event_id"] == "evt-0001"].iloc[0]
        # Clay history exists; Hard does not.
        assert not np.isnan(e1["p1_avg_games_per_set_clay_asof"])
        assert np.isnan(e1["p1_avg_games_per_set_hard_asof"])

    def test_match_realized_pure_and_symmetric(self):
        # match_realized reads ONLY the supplied score (no global state).
        r = match_realized("7-6(3) 4-6 6-1", winner=1)
        assert r is not None
        p1, p2 = r
        assert p1["sets_played"] == 3 and p1["sets_lost"] == 1
        assert p1["tb_played"] == 1 and p1["tb_won"] == 1
        assert p2["sets_lost"] == 2  # p2 lost 2 of 3
        assert match_realized("6-1", winner=1) is None  # <2 sets -> None


# ---------------------------------------------------------------------------
# 4. PARITY (one builder; train == inference)
# ---------------------------------------------------------------------------
class TestParity:
    def test_train_and_inference_identical_for_shared_event(self):
        # "Train" pass = full history.  "Inference" pass = the same matches fed
        # through the SAME builder.  For any event whose entire prior history is
        # present in both, the as-of row must be byte-identical (no parallel path).
        hist = _make_matches([
            {"p1_id": 1, "p2_id": 2, "date": "2020-01-01", "score": "7-6(2) 6-4"},
            {"p1_id": 1, "p2_id": 3, "date": "2020-01-02", "score": "6-3 4-6 6-2"},
            {"p1_id": 1, "p2_id": 4, "date": "2020-01-03", "score": "6-1 6-1"},
        ])
        train = build_asof_setdetail(hist)
        # Inference on the same frame must reproduce the same row for the last evt.
        infer = build_asof_setdetail(hist.copy())
        eid = "evt-0002"
        tr = train[train["event_id"] == eid].iloc[0]
        inf = infer[infer["event_id"] == eid].iloc[0]
        for c in OUT_COLS:
            if c in ("event_id", "surface"):
                assert tr[c] == inf[c]
            else:
                a, b = tr[c], inf[c]
                assert (np.isnan(a) and np.isnan(b)) or abs(a - b) < 1e-12, c

    def test_appending_future_match_does_not_change_past_row(self):
        # A later match appended to the corpus must NOT alter an earlier as-of row
        # (the earlier row never sees the future -> shift1 / prior-only guarantee).
        base = _make_matches([
            {"p1_id": 1, "p2_id": 2, "date": "2020-01-01", "score": "6-3 6-3"},
            {"p1_id": 1, "p2_id": 3, "date": "2020-01-02", "score": "6-2 6-2"},
        ])
        extended = pd.concat([base, _make_matches([
            {"p1_id": 1, "p2_id": 9, "date": "2020-02-01", "score": "6-0 6-0"},
        ]).assign(event_id="evt-9999")], ignore_index=True)
        d_base = build_asof_setdetail(base)
        d_ext = build_asof_setdetail(extended)
        r0 = d_base[d_base["event_id"] == "evt-0001"].iloc[0]
        r1 = d_ext[d_ext["event_id"] == "evt-0001"].iloc[0]
        for m in _METRICS:
            a, b = r0[f"p1_{m}_asof"], r1[f"p1_{m}_asof"]
            assert (np.isnan(a) and np.isnan(b)) or abs(a - b) < 1e-12


# ---------------------------------------------------------------------------
# Real-data smoke (zero-network; skip if absent)
# ---------------------------------------------------------------------------
class TestRealDataSmoke:
    @pytest.fixture(scope="class")
    def real_df(self):
        import pathlib
        p = pathlib.Path("data/domains/tennis/matches.parquet")
        if not p.exists():
            pytest.skip("matches.parquet not on disk")
        return build_asof_setdetail(pd.read_parquet(p))

    def test_one_row_per_match(self, real_df):
        import pathlib
        n = len(pd.read_parquet("data/domains/tennis/matches.parquet"))
        assert len(real_df) == n
        assert real_df["event_id"].is_unique

    def test_no_future_leak_real(self, real_df):
        assert_no_future_leak(real_df)

    def test_coverage(self, real_df):
        cov = ((real_df["p1_n_prior"] >= 5) & (real_df["p2_n_prior"] >= 5)).mean()
        assert cov >= 0.40, f"coverage too low: {cov:.1%}"


# ---------------------------------------------------------------------------
# 5. CACHE MATERIALIZATION (canonical in-game mirror path)
# ---------------------------------------------------------------------------
class TestCacheMaterialization:
    def test_cache_paths_are_named_per_tour(self):
        # The canonical gate-facing cache lives under data/cache/ingame/.
        assert isd._ATP_CACHE.name == "tennis_setdetail__atp.parquet"
        assert isd._WTA_CACHE.name == "tennis_setdetail__wta.parquet"
        assert isd._ATP_CACHE.parent.name == "ingame"
        assert isd._WTA_CACHE.parent.name == "ingame"

    def test_main_writes_cache_mirror(self, tmp_path, monkeypatch):
        # _main() must materialize the cache parquet (byte-identical to the build).
        mt = _make_matches([
            {"p1_id": 1, "p2_id": 2, "date": "2020-01-01", "score": "7-6(2) 6-4"},
            {"p1_id": 1, "p2_id": 3, "date": "2020-01-02", "score": "6-3 4-6 6-2"},
        ])
        src = tmp_path / "matches.parquet"
        mt.to_parquet(src)
        dst = tmp_path / "asof.parquet"
        cache = tmp_path / "ingame" / "tennis_setdetail__atp.parquet"
        monkeypatch.setattr(isd, "_ATP_MATCHES", src)
        monkeypatch.setattr(isd, "_ATP_OUT", dst)
        monkeypatch.setattr(isd, "_ATP_CACHE", cache)
        monkeypatch.setattr("sys.argv", ["prog", "--tour", "atp"])
        isd._main()
        assert cache.exists() and dst.exists()
        built = build_asof_setdetail(mt)
        cached = pd.read_parquet(cache)
        assert list(cached.columns) == OUT_COLS
        assert len(cached) == len(built)
