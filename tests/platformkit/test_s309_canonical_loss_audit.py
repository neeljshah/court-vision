"""Construct coverage for S309's canonical keys and strict-past state route."""
from __future__ import annotations

import pandas as pd
import pytest

import scripts.platformkit.s309_canonical_loss_audit as route
from scripts.platformkit.s309_canonical_loss_audit import _canonical, _score


def _prices() -> pd.DataFrame:
    """Real vocabulary: Polymarket sides are "home"/"away", Kalshi sides are tricodes."""
    row = {"ticker_or_slug": "nba-phi-bos-2026-04-26", "market_type": "moneyline"}
    kal = {"market_type": "moneyline", "venue": "kalshi", "event_key": "kal"}
    return pd.DataFrame([
        {**row, "venue": "polymarket", "event_key": "poly", "side": "home", "ts": 1, "prob": .7},
        {**row, "venue": "polymarket", "event_key": "poly", "side": "away", "ts": 1, "prob": .3},
        {**kal, "ticker_or_slug": "KXNBAGAME-26APR26PHIBOS-BOS", "side": "BOS", "ts": 1, "prob": .8},
        {**kal, "ticker_or_slug": "KXNBAGAME-26APR26PHIBOS-PHI", "side": "PHI", "ts": 1, "prob": .2},
        {**kal, "ticker_or_slug": "KXNBAGAME-26APR26PHIBOS-PHI", "side": "PHI", "ts": 2, "prob": .25},
    ])


def test_canonical_complements_and_two_venue_namespaces() -> None:
    checkpoints = pd.DataFrame({"game_id": [1], "market_ticker": ["nba-phi-bos-2026-04-26"]})
    accounting, keys = _canonical(_prices(), checkpoints)
    # the away side is complemented only where its key carries no home-side row
    assert set(accounting.accounting_reason) == {"CANONICAL", "COMPLEMENT_UNUSED_HOME_PRESENT"}
    assert sorted(keys.canonical_home_prob) == [.7, .75, .8]
    assert keys.canonical_branch.value_counts().to_dict() == {"DIRECT_HOME": 2, "COMPLEMENT_AWAY": 1}
    assert keys[["game_id_alias", "venue", "event_key", "ts"]].duplicated().sum() == 0


def test_exact_repeat_collapses_but_conflicting_timestamp_is_rejected() -> None:
    checkpoints = pd.DataFrame({"game_id": [1], "market_ticker": ["nba-phi-bos-2026-04-26"]})
    repeat = pd.concat([_prices(), _prices().iloc[:1]], ignore_index=True)
    accounting, keys = _canonical(repeat, checkpoints)
    assert (accounting.accounting_reason == "EXACT_DUPLICATE_TICK").sum() == 1
    assert sorted(keys.canonical_home_prob) == [.7, .75, .8]
    conflict = _prices().iloc[:1].assign(prob=.6)
    with pytest.raises(AssertionError, match="duplicate canonical"):
        _canonical(pd.concat([_prices(), conflict], ignore_index=True), checkpoints)


def _checkpoints(n_games: int = 12) -> pd.DataFrame:
    """One game per day; cpcv_splits needs at least 8 distinct state timestamps."""
    base = 1735689600                       # 2025-01-01T00:00:00Z
    rows = []
    for game in range(n_games):
        away, home = "T%02d" % (game % 6), "T%02d" % ((game + 2) % 6)
        rows.append({"game_id": 100 + game, "game_date": "2025-01-%02d" % (game + 1),
                     "ts": base + 86400 * game,
                     "market_ticker": "nba-%s-%s-2025-01-%02d" % (away.lower(), home.lower(), game + 1),
                     "market_prob": 0.05 + 0.9 * ((game * 7) % 11) / 10.0,
                     "outcome_home_win": game % 2})
    return pd.DataFrame(rows)


def test_one_state_per_tick_and_shared_evaluator_provenance() -> None:
    scored, folds, provenance = _score(_checkpoints())
    assert scored.state_key.is_unique and set(scored.evaluator_records) == {1}
    assert provenance["forward"]["evaluator"].endswith("walkforward.walk_forward")
    assert provenance["cpcv"]["evaluator"].endswith("cpcv_engine.cpcv_evaluate")
    assert provenance["cpcv"]["symmetric_embargo"] and provenance["cpcv"]["symmetric_embargo_days"] == 1
    assert provenance["record_agreement_max_abs_error"] <= 1e-9
    forward = [fold for fold in folds if fold["arm"] == "forward"]
    # every forward fit trains only on games SETTLED before its first test state
    assert forward and all(not fold["max_train_settle"]
                           or fold["max_train_settle"] < fold["first_test_state_ts"]
                           for fold in forward)


def test_s272_replay_is_a_stop_gate_ahead_of_scoring(monkeypatch, tmp_path) -> None:
    """A failed S272 replay stops the run before _score and before any source store is read."""
    def _boom(*args, **kwargs):
        raise RuntimeError("scored or read a source store after a failed replay")

    monkeypatch.setattr(route.pd, "read_parquet", _boom)
    monkeypatch.setattr(route, "_score", _boom)
    monkeypatch.setattr(route, "_historical", lambda: {
        "baseline_replay_error": 0.0, "candidate_replay_error": 1e-9, "tail_ece_replay_error": 0.0})
    with pytest.raises(AssertionError, match="NOT REPRODUCED"):
        route.run(tmp_path)


def test_retained_s272_values_replay_including_the_tail_ece_change() -> None:
    """The retained S299 before-values: candidate improvement and the tail ECE change."""
    historical = route._historical()
    assert historical["baseline_replay_error"] <= 1e-12
    assert historical["candidate_replay_error"] <= 1e-12
    assert historical["tail_ece_replay_error"] <= 1e-12
    assert historical["retained_candidate_improvement"] == pytest.approx(-0.000037, abs=5e-7)
    change = historical["retained_tail_ece_change_candidate_minus_incumbent"]
    assert change == pytest.approx(-0.000248, abs=1e-6)
