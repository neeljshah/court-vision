"""Per-file tests for domains.basketball_wnba.rest_covariate_gate (synthetic, offline).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_rest_covariate_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.basketball_wnba import rest_covariate_gate as rcg


def _synthetic_scoreboard(n_per_season=120, seed=0, rest_effect=0.0):
    """Synthetic ESPN-scoreboard-shaped corpus. Teams cycle through a fixed rest
    schedule so ``days_since_last_game`` varies; ``rest_effect`` controls how much
    (if any) real signal rest_diff carries in home_win (0.0 = no real effect)."""
    rng = np.random.RandomState(seed)
    teams = ["A", "B", "C", "D", "E", "F", "G", "H"]
    strength = {t: rng.normal(0, 1) for t in teams}
    rows = []
    for season in ["2025", "2026"]:
        cur_date = pd.Timestamp(f"{season}-05-01")
        team_last_date = {}
        for i in range(n_per_season):
            gap = int(rng.choice([1, 2, 3, 4]))
            cur_date = cur_date + pd.Timedelta(days=gap)
            home, away = rng.choice(teams, size=2, replace=False)
            home_rest = (cur_date - team_last_date[home]).days if home in team_last_date else np.nan
            away_rest = (cur_date - team_last_date[away]).days if away in team_last_date else np.nan
            team_last_date[home] = cur_date
            team_last_date[away] = cur_date
            rd = (home_rest - away_rest) if (home_rest == home_rest and away_rest == away_rest) else 0.0
            d = strength[home] - strength[away] + 0.25 + rest_effect * rd
            p_true = 1.0 / (1.0 + np.exp(-d))
            hw = 1.0 if rng.random_sample() < p_true else 0.0
            rows.append({
                "event_id": f"{season}-{i}", "date": cur_date, "season": season,
                "home_team": home, "away_team": away,
                "home_score": 80.0 if hw else 75.0, "away_score": 75.0 if hw else 80.0,
                "home_win": hw, "neutral_site": False, "status_name": "STATUS_FINAL",
            })
    return pd.DataFrame(rows)


def test_days_since_last_game_first_appearance_is_nan():
    df = _synthetic_scoreboard(n_per_season=30, seed=1)
    df["date"] = pd.to_datetime(df["date"])
    out = rcg._days_since_last_game(df)
    assert "rest_diff" in out.columns
    # first game overall has no prior game for either team -> NaN rest_diff
    first_row = out.sort_values("date").iloc[0]
    assert pd.isna(first_row["rest_diff"])


def test_days_since_last_game_is_leak_free_schedule_quantity(monkeypatch, tmp_path):
    df = _synthetic_scoreboard(n_per_season=40, seed=2)
    df["date"] = pd.to_datetime(df["date"])
    out = rcg._days_since_last_game(df)
    covered = out.dropna(subset=["rest_diff"])
    assert len(covered) > 0
    # rest_diff must be a plain float, computable from schedule alone (no outcome cols used)
    assert covered["rest_diff"].dtype.kind == "f"


def test_build_corpus_adds_null_column_with_same_coverage(monkeypatch):
    df = _synthetic_scoreboard(n_per_season=60, seed=3)
    df.to_parquet_called = False

    def _fake_read_parquet(path):
        return df.copy()

    monkeypatch.setattr(rcg.pd, "read_parquet", _fake_read_parquet)
    feat = rcg.build_corpus()
    assert "rest_diff_null" in feat.columns
    real_cov = feat["rest_diff"].notna().mean()
    null_cov = feat["rest_diff_null"].notna().mean()
    assert abs(real_cov - null_cov) < 1e-9


def test_fold_returns_none_on_thin_corpus():
    df = _synthetic_scoreboard(n_per_season=10, seed=4)
    df["date"] = pd.to_datetime(df["date"])
    feat = rcg.walk_forward_elo(rcg._days_since_last_game(df))
    season_df = feat[feat["season"] == "2025"]
    assert rcg._fold(season_df, "2025", "rest_diff") is None


def test_fold_returns_result_on_adequate_corpus():
    df = _synthetic_scoreboard(n_per_season=120, seed=5)
    df["date"] = pd.to_datetime(df["date"])
    feat = rcg.walk_forward_elo(rcg._days_since_last_game(df))
    season_df = feat[feat["season"] == "2025"]
    result = rcg._fold(season_df, "2025", "rest_diff")
    assert result is not None
    assert result.n_train > 0 and result.n_test > 0
    assert isinstance(result.feat_improves, bool)


def test_decide_insufficient_data_on_no_folds():
    verdict, comparable = rcg._decide([], [])
    assert verdict == "INSUFFICIENT_DATA"
    assert comparable is False


def test_decide_invalid_base_takes_priority():
    f = rcg.FoldResult(season="2025", n_train=50, n_test=20, brier_base=0.24,
                       brier_feat=0.23, brier_delta=0.01, logloss_base=0.68,
                       logloss_feat=0.67, bss_vs_coin_base=-0.01,
                       base_degenerate=True, feat_improves=True)
    verdict, comparable = rcg._decide([f], [])
    assert verdict == "INVALID_BASE"


def test_decide_reject_when_feature_does_not_improve_all_folds():
    f_good = rcg.FoldResult(season="2025", n_train=50, n_test=20, brier_base=0.24,
                            brier_feat=0.23, brier_delta=0.01, logloss_base=0.68,
                            logloss_feat=0.67, bss_vs_coin_base=0.05,
                            base_degenerate=False, feat_improves=True)
    f_bad = rcg.FoldResult(season="2026", n_train=50, n_test=20, brier_base=0.24,
                           brier_feat=0.245, brier_delta=-0.005, logloss_base=0.68,
                           logloss_feat=0.69, bss_vs_coin_base=0.05,
                           base_degenerate=False, feat_improves=False)
    verdict, comparable = rcg._decide([f_good, f_bad], [])
    assert verdict == "REJECT"


def test_decide_not_testable_when_null_comparable_to_real():
    real = rcg.FoldResult(season="2025", n_train=50, n_test=20, brier_base=0.24,
                          brier_feat=0.23, brier_delta=0.01, logloss_base=0.68,
                          logloss_feat=0.67, bss_vs_coin_base=0.05,
                          base_degenerate=False, feat_improves=True)
    null = rcg.FoldResult(season="2025", n_train=50, n_test=20, brier_base=0.24,
                          brier_feat=0.233, brier_delta=0.007, logloss_base=0.68,
                          logloss_feat=0.672, bss_vs_coin_base=0.05,
                          base_degenerate=False, feat_improves=True)
    verdict, comparable = rcg._decide([real], [null])
    assert verdict == "NOT_TESTABLE"
    assert comparable is True


def test_decide_ship_candidate_when_null_fails_to_replicate():
    real = rcg.FoldResult(season="2025", n_train=50, n_test=20, brier_base=0.24,
                          brier_feat=0.23, brier_delta=0.01, logloss_base=0.68,
                          logloss_feat=0.67, bss_vs_coin_base=0.05,
                          base_degenerate=False, feat_improves=True)
    null = rcg.FoldResult(season="2025", n_train=50, n_test=20, brier_base=0.24,
                          brier_feat=0.241, brier_delta=-0.001, logloss_base=0.68,
                          logloss_feat=0.681, bss_vs_coin_base=0.05,
                          base_degenerate=False, feat_improves=False)
    verdict, comparable = rcg._decide([real], [null])
    assert verdict == "SHIP_CANDIDATE"
    assert comparable is False


def test_run_on_real_wnba_scoreboard_never_claims_close_comparison():
    """Integration smoke test against the real on-disk corpus (if present) -- the
    verdict must never fabricate a close comparison (no WNBA close data exists)."""
    if not rcg._SCOREBOARD.exists():
        pytest.skip("espn_scoreboard.parquet not on disk in this environment")
    v = rcg.run()
    assert v.close_comparison == "PENDING_CLOSE_COMPARISON"
    assert v.verdict in ("INSUFFICIENT_DATA", "INVALID_BASE", "REJECT",
                         "NOT_TESTABLE", "SHIP_CANDIDATE")


def test_run_reports_insufficient_data_when_scoreboard_missing(monkeypatch, tmp_path):
    fake_path = tmp_path / "does_not_exist.parquet"
    monkeypatch.setattr(rcg, "_SCOREBOARD", fake_path)
    v = rcg.run()
    assert v.verdict == "INSUFFICIENT_DATA"
    assert any("not on disk" in c for c in v.caveats)


def test_write_produces_ascii_json(tmp_path):
    v = rcg.RestGateVerdict(verdict="REJECT", folds=[], null_folds=[],
                            null_comparable=False, caveats=["x"])
    out = tmp_path / "verdict.json"
    path = rcg.write(v, out=out)
    assert path == str(out)
    text = out.read_text(encoding="ascii")
    assert '"verdict": "REJECT"' in text
    assert '"close_comparison"' in text
