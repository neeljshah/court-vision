"""Per-file tests for domains.basketball_wnba.elo_refresh_gate (+ its IO
companion), synthetic + real-corpus smoke.

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_elo_refresh_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.basketball_wnba import elo_refresh_gate as erg
from domains.basketball_wnba import elo_refresh_gate_io as ergio
from domains.basketball_wnba.elo_config import ELO_HFA


def _synthetic_scoreboard(n_per_season=140, seed=0, mov_effect=0.0, neutral_frac=0.0):
    """Synthetic ESPN-scoreboard-shaped corpus. mov_effect>0 injects a real
    margin-of-victory-correlated-with-strength-gap signal into home_win (so C1
    has something real to find); neutral_frac controls neutral_site rate."""
    rng = np.random.RandomState(seed)
    teams = ["A", "B", "C", "D", "E", "F", "G", "H"]
    strength = {t: rng.normal(0, 1) for t in teams}
    rows = []
    for season in ["2025", "2026"]:
        cur_date = pd.Timestamp(f"{season}-05-01")
        for i in range(n_per_season):
            cur_date = cur_date + pd.Timedelta(days=int(rng.choice([1, 2, 3])))
            home, away = rng.choice(teams, size=2, replace=False)
            d = strength[home] - strength[away] + 0.25
            p_true = 1.0 / (1.0 + np.exp(-d))
            hw = 1.0 if rng.random_sample() < p_true else 0.0
            margin = abs(rng.normal(8 + mov_effect * abs(d) * 10, 5))
            neutral = bool(rng.random_sample() < neutral_frac)
            home_score = 80.0 + (margin if hw else 0.0)
            away_score = 80.0 + (0.0 if hw else margin)
            rows.append({
                "event_id": f"{season}-{i}", "date": cur_date, "season": season,
                "home_team": home, "away_team": away,
                "home_score": home_score, "away_score": away_score,
                "home_win": hw, "neutral_site": neutral, "status_name": "STATUS_FINAL",
            })
    return pd.DataFrame(rows)


def test_build_corpus_adds_margin_and_null_columns(monkeypatch, tmp_path):
    df = _synthetic_scoreboard(n_per_season=60, seed=1)
    path = tmp_path / "scoreboard.parquet"
    df.to_parquet(path)
    feat = erg.build_corpus(path)
    assert "margin_true" in feat.columns and "margin_null" in feat.columns
    assert (feat["margin_true"] >= 0).all()
    # null coverage matches true coverage (same rows, shuffled within season)
    assert feat["margin_true"].notna().sum() == feat["margin_null"].notna().sum()


def test_build_corpus_baseline_matches_frozen_ratings_module(tmp_path):
    """build_corpus's p_home_elo column must be byte-identical to calling
    ratings.walk_forward_elo directly -- this gate does not reimplement or
    perturb the frozen baseline replay."""
    from domains.basketball_wnba.ratings import walk_forward_elo
    df = _synthetic_scoreboard(n_per_season=50, seed=2)
    path = tmp_path / "scoreboard.parquet"
    df.to_parquet(path)
    direct = walk_forward_elo(df.assign(date=pd.to_datetime(df["date"])))
    feat = erg.build_corpus(path)
    assert np.allclose(direct["p_home_elo"].to_numpy(), feat["p_home_elo"].to_numpy())


def test_replay_candidate_baseline_equivalent_when_mov_and_neutral_off():
    """use_mov=False, neutral_aware=False must reproduce the frozen baseline's
    p_home_elo exactly (same K, HFA, regress, no MOV multiplier applied)."""
    from domains.basketball_wnba.ratings import walk_forward_elo
    df = _synthetic_scoreboard(n_per_season=50, seed=3)
    df["date"] = pd.to_datetime(df["date"])
    base = walk_forward_elo(df)
    cand = erg._replay_candidate(df, use_mov=False, neutral_aware=False)
    assert np.allclose(base["p_home_elo"].to_numpy(), cand["p_home_candidate"].to_numpy(),
                       atol=1e-9)


def test_replay_candidate_neutral_aware_zeroes_hfa_effect():
    df = _synthetic_scoreboard(n_per_season=60, seed=4, neutral_frac=0.5)
    df["date"] = pd.to_datetime(df["date"])
    plain = erg._replay_candidate(df, use_mov=False, neutral_aware=False)
    neutral_aware = erg._replay_candidate(df, use_mov=False, neutral_aware=True)
    # at least one neutral-site row's probability must differ once HFA=40 is removed
    neutral_rows = plain["neutral_site"].to_numpy()
    assert neutral_rows.any()
    diffs = np.abs(plain.loc[neutral_rows, "p_home_candidate"].to_numpy() -
                   neutral_aware.loc[neutral_rows, "p_home_candidate"].to_numpy())
    assert diffs.max() > 0.0
    assert ELO_HFA > 0  # sanity: HFA is non-zero in config, so removal must matter


def _featured(df: pd.DataFrame) -> pd.DataFrame:
    from domains.basketball_wnba.ratings import walk_forward_elo
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    feat = walk_forward_elo(df)
    feat["margin_true"] = (feat["home_score"] - feat["away_score"]).abs()
    return feat


def test_within_season_fold_returns_none_on_thin_corpus():
    feat = _featured(_synthetic_scoreboard(n_per_season=10, seed=5))
    assert erg._within_season_fold(feat, "2025", use_mov=True, neutral_aware=False,
                                   candidate_name="C1_mov") is None


def test_within_season_fold_returns_result_on_adequate_corpus():
    feat = _featured(_synthetic_scoreboard(n_per_season=140, seed=6))
    fr = erg._within_season_fold(feat, "2025", use_mov=True, neutral_aware=False,
                                 candidate_name="C1_mov")
    assert fr is not None
    assert fr.n_train > 0 and fr.n_test > 0
    assert isinstance(fr.cand_improves, bool)


def test_candidate_verdict_insufficient_data_on_missing_season():
    assert erg._candidate_verdict([{"bss_delta": 0.01, "base_degenerate": False}], []) \
        == "INSUFFICIENT_DATA"


def test_candidate_verdict_invalid_base_takes_priority():
    folds = [{"bss_delta": 0.01, "base_degenerate": True} for _ in erg.EVAL_SEASONS]
    assert erg._candidate_verdict(folds, []) == "INVALID_BASE"


def test_candidate_verdict_reject_on_split_sign():
    folds = [{"bss_delta": 0.01, "base_degenerate": False},
             {"bss_delta": -0.01, "base_degenerate": False}]
    assert erg._candidate_verdict(folds, []) == "REJECT"


def test_candidate_verdict_reject_below_adoption_floor():
    tiny = erg.ADOPTION_BSS_FLOOR / 10.0
    folds = [{"bss_delta": tiny, "base_degenerate": False} for _ in erg.EVAL_SEASONS]
    assert erg._candidate_verdict(folds, []) == "REJECT"


def test_candidate_verdict_not_testable_when_null_replicates():
    folds = [{"bss_delta": 0.01, "base_degenerate": False} for _ in erg.EVAL_SEASONS]
    nfolds = [{"bss_delta": 0.008} for _ in erg.EVAL_SEASONS]  # >=50% of real lift
    assert erg._candidate_verdict(folds, nfolds) == "NOT_TESTABLE"


def test_candidate_verdict_ships_when_null_fails_to_replicate():
    folds = [{"bss_delta": 0.01, "base_degenerate": False} for _ in erg.EVAL_SEASONS]
    nfolds = [{"bss_delta": -0.001} for _ in erg.EVAL_SEASONS]
    assert erg._candidate_verdict(folds, nfolds) == "SHIP_CANDIDATE"


def test_run_reports_insufficient_data_when_scoreboard_missing(tmp_path):
    fake = tmp_path / "does_not_exist.parquet"
    payload = erg.run(fake)
    assert payload["verdict"] == "INSUFFICIENT_DATA"


def test_run_never_edits_frozen_config_module():
    """Guard: importing/running the gate must not mutate elo_config's frozen
    constants (module-level attribute identity check)."""
    from domains.basketball_wnba import elo_config
    k_before, hfa_before = elo_config.ELO_K, elo_config.ELO_HFA
    df = _synthetic_scoreboard(n_per_season=120, seed=7)
    df["date"] = pd.to_datetime(df["date"])
    erg._replay_candidate(df, use_mov=True, neutral_aware=True)
    assert elo_config.ELO_K == k_before and elo_config.ELO_HFA == hfa_before


def test_run_on_real_wnba_scoreboard_never_claims_close_comparison():
    if not erg._SCOREBOARD.exists():
        pytest.skip("espn_scoreboard.parquet not on disk in this environment")
    payload = erg.run()
    assert payload["close_comparison"] == "PENDING_CLOSE_COMPARISON"
    assert payload["verdict"] in ("INSUFFICIENT_DATA", "REJECT", "NOT_TESTABLE",
                                  "SHIP_CANDIDATE")
    assert set(payload["candidate_verdicts"]) == set(erg.CANDIDATES)


def test_reproduce_fold_discrepancy_reconciles_real_corpus():
    """The season-pooled BSS and within-season-tail BSS must both be computed
    (no NaN) and reported for both eval seasons -- the core deliverable."""
    if not erg._SCOREBOARD.exists():
        pytest.skip("espn_scoreboard.parquet not on disk in this environment")
    feat = erg.build_corpus()
    disc = ergio.reproduce_fold_discrepancy(feat, erg.TRAIN_FRAC, erg._bss_vs_coin)
    assert set(disc.keys()) == {"2025", "2026"}
    for s, d in disc.items():
        assert d["n_season_pooled"] > d["n_within_season_test_tail"]
        assert not np.isnan(d["season_pooled_bss_raw_elo"])


def test_write_and_write_rows_ascii_and_roundtrip(tmp_path):
    payload = {"verdict": "REJECT", "candidate_verdicts": {}, "candidate_folds": {},
               "fold_discrepancy_explained": {}, "close_comparison": "PENDING_CLOSE_COMPARISON"}
    out = tmp_path / "verdict.json"
    path = ergio.write(payload, out)
    assert path == str(out)
    text = out.read_text(encoding="ascii")
    assert '"verdict": "REJECT"' in text

    feat = _featured(_synthetic_scoreboard(n_per_season=20, seed=8))
    rows_out = tmp_path / "rows.parquet"
    rows_path = ergio.write_rows(feat, rows_out)
    assert rows_path == str(rows_out)
    back = pd.read_parquet(rows_out)
    assert "p_home_elo" in back.columns and "margin_true" in back.columns


def test_report_contains_verdict_and_discrepancy_sections():
    payload = erg.run(erg._SCOREBOARD if erg._SCOREBOARD.exists() else None)
    text = ergio.report(payload)
    assert "OVERALL VERDICT" in text
    assert "close_comparison" in text
