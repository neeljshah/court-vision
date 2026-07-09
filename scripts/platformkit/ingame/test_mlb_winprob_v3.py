"""Per-file tests for mlb_winprob_v3.py + mlb_winprob_v3_prior.py -- pregame market-price
prior anchor added to v2's state-conditioned MLB live win-prob model.

OFFLINE + deterministic: synthetic Polymarket/Kalshi jsonl + pitch-state frames under
tmp_path, no network, no real corpus reads.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v3.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.platformkit.ingame.mlb_winprob_v2_features as feat
import scripts.platformkit.ingame.mlb_winprob_v3 as v3
import scripts.platformkit.ingame.mlb_winprob_v3_prior as prior_mod


class _FakeResolver:
    """Stand-in for MlbOutcomeResolver -- only the `_abbrs` attribute is read here."""
    _abbrs = {"NYY", "BOS"}


def _write_pm_doc(path: Path, date: str, home: str, away: str, prices: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"date": date, "home": home, "away": away, "outcome_home_win": 1,
          "prices": [{"ts": ts, "prob_home": p} for ts, p in prices]}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(doc) + "\n")


def _write_kalshi_side(path: Path, ticker_side: str, candles: list) -> None:
    path.mkdir(parents=True, exist_ok=True)
    doc = {"ticker": ticker_side, "candles": [{"ts": ts, "prob": p, "traded": tr}
                                              for ts, p, tr in candles]}
    (path / (ticker_side + ".jsonl")).write_text(json.dumps(doc), encoding="utf-8")


def _write_grade_game(grade_dir: Path, gid: str, first_ts: str) -> None:
    p = grade_dir / "mlb" / (gid + ".jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"sport": "mlb", "game_id": gid, "ts": first_ts, "side": "home",
          "model_prob": 0.6, "market_prob": 0.55,
          "state_summary": "home_score=1 away_score=0 inning=3 half=top outs=1 base=2 count=1-1"}
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------- #
def test_no_2026_in_train_guard(tmp_path: Path) -> None:
    """v3 relies on feat.load_training_seasons's guard, reused unchanged."""
    with pytest.raises(ValueError):
        feat.load_training_seasons([2026], data_dir=tmp_path)


def test_pm_prior_matching_and_team_name_override(tmp_path: Path) -> None:
    pm_dir = tmp_path / "pm"
    _write_pm_doc(pm_dir / "2024-06-01.jsonl", "2024-06-01", "Boston Red Sox",
                 "New York Yankees", [("2024-06-01T17:00:00Z", 0.42), ("2024-06-01T18:00:00Z", 0.5)])
    # CHC/SFG override case
    _write_pm_doc(pm_dir / "2024-06-02.jsonl", "2024-06-02", "Chicago Cubs",
                 "San Francisco Giants", [("2024-06-02T17:00:00Z", 0.61)])
    index, counts = prior_mod.build_pm_prior_index([pm_dir])
    assert counts["n_docs_matched"] == 2
    key1 = ("2024-06-01", frozenset({"NYY", "BOS"}))
    assert index[key1] == ("BOS", pytest.approx(0.42))  # (pm_home_abbr, FIRST price)
    assert index[("2024-06-02", frozenset({"SFO", "CUB"}))][0] == "CUB"

    # pitch_states game_id encodes "<date>-<HOME>-<AWAY>-<n>" (verified against the
    # parquet's own home_team/away_team columns -- BOS is home here, matching the PM doc's
    # own "home" claim, so no reorientation is needed for this row).
    df = pd.DataFrame({"game_id": ["2024-06-01-BOS-NYY-1", "2024-06-03-BOS-NYY-1"]})
    out, acounts = prior_mod.attach_priors(df, index)
    assert acounts["n_games"] == 2 and acounts["n_games_with_prior"] == 1
    matched = out[out["game_id"] == "2024-06-01-BOS-NYY-1"].iloc[0]
    assert matched["has_prior"] and matched["prior_home"] == pytest.approx(0.42)


def test_pm_prior_reorients_when_pm_home_label_is_flipped(tmp_path: Path) -> None:
    """The landmine this module works around: PM's own home/away label can be wrong for a
    given game. attach_priors must orient off pitch_states' verified home_team, not PM's
    claim -- a PM doc that calls the pitch_states AWAY team "home" must still yield the
    correct prior_home via a 1-p flip."""
    pm_dir = tmp_path / "pm"
    # PM claims ARI is home; pitch_states (ground truth, verified against espn_boxscores in
    # production) says MIL is actually home for this game -- exactly the observed landmine.
    _write_pm_doc(pm_dir / "d.jsonl", "2025-04-11", "Arizona Diamondbacks",
                 "Milwaukee Brewers", [("2025-04-10T08:17:05Z", 0.7)])
    index, _ = prior_mod.build_pm_prior_index([pm_dir])
    df = pd.DataFrame({"game_id": ["2025-04-11-MIL-ARI-1"]})  # home=MIL, away=ARI
    out, counts = prior_mod.attach_priors(df, index)
    assert counts["n_games_with_prior"] == 1
    # PM's prob_home=0.7 was P(ARI), but true home is MIL -> flipped to 1-0.7
    assert out.iloc[0]["prior_home"] == pytest.approx(0.3)


def test_has_prior_fallback_never_fabricated(tmp_path: Path) -> None:
    """No matching PM doc / no matching Kalshi side file -> prior=0.5, has_prior=False."""
    df = pd.DataFrame({"game_id": ["2099-01-01-ZZZ-YYY-1", "malformed_id"]})
    out, counts = prior_mod.attach_priors(df, {})
    assert counts["n_games_with_prior"] == 0
    assert (out["prior_home"] == 0.5).all()
    assert (~out["has_prior"]).all()

    grade_dir = tmp_path / "grade"
    _write_grade_game(grade_dir, "KXMLBGAME-24JUN011200NYYBOS", "2024-06-01T12:00:00Z")
    eval_priors, ecounts = prior_mod.build_eval_priors(grade_dir, _FakeResolver(),
                                                        kalshi_dir=tmp_path / "no_such_dir")
    prior, has = eval_priors["KXMLBGAME-24JUN011200NYYBOS"]
    assert prior == 0.5 and has is False
    assert ecounts["n_games_with_prior"] == 0


def test_kalshi_eval_prior_uses_last_traded_candle_before_cutoff(tmp_path: Path) -> None:
    grade_dir = tmp_path / "grade"
    ticker = "KXMLBGAME-24JUN011200NYYBOS"
    _write_grade_game(grade_dir, ticker, "2024-06-01T18:00:00Z")
    kalshi_dir = tmp_path / "kalshi"
    # home=BOS (per parse_mlb_ticker's away+home tail split) -> this file's prob IS P(home win)
    _write_kalshi_side(kalshi_dir, ticker + "-BOS", [
        ("2024-06-01T16:00:00Z", 0.40, True),
        ("2024-06-01T17:00:00Z", 0.45, True),   # last traded before cutoff -> expected pick
        ("2024-06-01T19:00:00Z", 0.90, True),   # AFTER cutoff -- must be ignored
    ])
    eval_priors, counts = prior_mod.build_eval_priors(grade_dir, _FakeResolver(), kalshi_dir=kalshi_dir)
    prior, has = eval_priors[ticker]
    assert has is True
    assert prior == pytest.approx(0.45)
    assert counts["n_games_with_prior"] == 1


def test_fit_blend_and_blend_predict_bounds() -> None:
    rng = np.random.RandomState(0)
    p_state = rng.uniform(0.1, 0.9, size=200)
    prior = rng.uniform(0.1, 0.9, size=200)
    y = (rng.uniform(size=200) < p_state).astype(float)
    alpha, beta = v3.fit_blend(p_state, prior, y)
    assert np.isfinite(alpha) and np.isfinite(beta)
    probs = v3.blend_predict(p_state, prior, alpha, beta)
    assert probs.shape == p_state.shape
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0)
    # degenerate (single-class) y -> honest pass-through, never a fabricated fit
    a2, b2 = v3.fit_blend(p_state, prior, np.ones(200))
    assert (a2, b2) == (1.0, 0.0)
    assert v3.blend_predict(np.zeros(0), np.zeros(0), 1.0, 0.0).shape == (0,)


def test_train_xy_v3_adds_prior_columns_and_aligns_rows() -> None:
    df = pd.DataFrame({
        "game_id": ["g1", "g1", "g2"],
        "half_inning_label": ["top1", "bottom1", "GARBAGE"],  # last row unparseable -> dropped
        "outs": [0, 1, 2], "runners": [0, 3, 5], "count_balls": [1, 2, 0], "count_strikes": [0, 1, 2],
        "state_diff": [0.0, 1.0, -2.0], "frac_elapsed": [0.1, 0.2, 0.3], "outcome": [1, 1, 0],
        "prior_home": [0.6, 0.6, 0.5], "has_prior": [True, True, False],
    })
    X, y, n_dropped = v3.train_xy_v3(df)
    assert n_dropped == 1
    assert X.shape == (2, len(v3.FEATURE_NAMES_V3))
    # prior_logit column (index 8) matches logit(0.6) for both surviving rows
    assert X[:, 8] == pytest.approx(prior_mod._logit(np.array([0.6, 0.6])))
    assert list(X[:, 9]) == [1.0, 1.0]  # has_prior column


def test_save_model_meta_feature_count_matches_pkl_for_winning_spec(tmp_path: Path) -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.isotonic import IsotonicRegression
    clf = HistGradientBoostingClassifier(random_state=0)
    X = np.random.RandomState(0).uniform(size=(20, len(v3.FEATURE_NAMES_V3)))
    y = (X[:, 0] > 0.5).astype(int)
    clf.fit(X, y)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(clf.predict_proba(X)[:, 1], y)
    bundle = {"clf_a": clf, "iso_a": iso, "clf_state": None, "iso_state": None,
             "alpha": 1.0, "beta": 0.0, "winner": "a",
             "val_brier_spec_a": 0.2, "val_brier_spec_b": 0.25, "meta": {"prior_coverage": {}}}
    pkl_path, meta_path = v3.save_model(bundle, model_path=tmp_path / "m.pkl",
                                        meta_path=tmp_path / "m_meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["n_features"] == clf.n_features_in_ == len(v3.FEATURE_NAMES_V3)
    assert pkl_path.is_file()
