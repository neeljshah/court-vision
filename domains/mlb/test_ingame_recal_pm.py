"""Per-file tests for ingame_recal_pm.py (LANE 3 sub-task B: PM historical
recalibration refit). Hermetic synthetic fixtures for the pure-function core
(extract_checkpoint_rows, build_corpus_rows, split_train_validate); a real-
corpus smoke test is SKIPPED (not failed) if the local PM corpus is absent.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_ingame_recal_pm.py -q
"""
from __future__ import annotations

import json

import pytest

from domains.mlb.ingame_recal_pm import (
    CHECKPOINT_FRACTIONS,
    MIN_PROB_RANGE,
    MIN_TICKS,
    TRAIN_SEASONS,
    VALIDATE_SEASONS,
    _PM_DIRS,
    build_corpus_rows,
    extract_checkpoint_rows,
    load_games,
    measure_pm_recalibration,
    split_train_validate,
)


def _game(date="2025-04-02", outcome=1, probs=None, slug="mlb-nyy-bos-2025-04-02"):
    if probs is None:
        probs = [0.5, 0.52, 0.55, 0.6, 0.7, 0.8, 0.9]
    return {
        "date": date, "market_slug": slug, "outcome_home_win": outcome,
        "prices": [{"ts": f"t{i}", "prob_home": p} for i, p in enumerate(probs)],
    }


# ---------------------------------------------------------------------------
# extract_checkpoint_rows
# ---------------------------------------------------------------------------


def test_extract_checkpoint_rows_normal_game():
    rows = extract_checkpoint_rows(_game())
    assert len(rows) == len(CHECKPOINT_FRACTIONS)
    for r in rows:
        assert r["season"] == "2025"
        assert 0.0 <= r["raw_prob"] <= 1.0
        assert r["outcome"] == 1.0


def test_extract_checkpoint_rows_excludes_degenerate_market():
    flat = _game(probs=[0.5] * 10)
    assert extract_checkpoint_rows(flat) == []


def test_extract_checkpoint_rows_excludes_missing_outcome():
    g = _game(outcome=None)
    assert extract_checkpoint_rows(g) == []


def test_extract_checkpoint_rows_excludes_too_few_ticks():
    g = _game(probs=[0.5, 0.6])  # < MIN_TICKS
    assert extract_checkpoint_rows(g) == []


def test_extract_checkpoint_rows_never_raises_on_malformed_prices():
    g = {"date": "2025-01-01", "market_slug": "x", "outcome_home_win": 1,
         "prices": [{"ts": "t", "prob_home": "not-a-number"}, None, {"foo": "bar"}]}
    assert extract_checkpoint_rows(g) == []


# ---------------------------------------------------------------------------
# build_corpus_rows / split_train_validate
# ---------------------------------------------------------------------------


def test_build_corpus_rows_pools_all_games():
    games = {"a": _game(slug="a"), "b": _game(slug="b", date="2023-04-01")}
    rows = build_corpus_rows(games)
    assert len(rows) == 2 * len(CHECKPOINT_FRACTIONS)


def test_split_train_validate_by_season():
    games = {"a": _game(slug="a", date="2023-04-01"),
             "b": _game(slug="b", date="2025-04-01"),
             "c": _game(slug="c", date="2026-04-01")}
    rows = build_corpus_rows(games)
    train, validate = split_train_validate(rows)
    assert all(r["season"] in TRAIN_SEASONS for r in train)
    assert all(r["season"] in VALIDATE_SEASONS for r in validate)
    assert len(train) == len(CHECKPOINT_FRACTIONS)
    assert len(validate) == 2 * len(CHECKPOINT_FRACTIONS)


def test_split_train_validate_sorted_deterministically():
    games = {"z": _game(slug="z", date="2025-04-01"), "a": _game(slug="a", date="2025-04-01")}
    rows = build_corpus_rows(games)
    _, validate = split_train_validate(rows)
    slugs = [r["market_slug"] for r in validate]
    assert slugs == sorted(slugs)


# ---------------------------------------------------------------------------
# load_games (dedup + malformed-line tolerance)
# ---------------------------------------------------------------------------


def test_load_games_dedupes_by_slug(tmp_path):
    f = tmp_path / "d.jsonl"
    f.write_text(
        json.dumps(_game(slug="dup")) + "\n" +
        json.dumps(_game(slug="dup", outcome=0)) + "\n" +  # duplicate -- first wins
        "not-json\n" +
        json.dumps(_game(slug="unique")) + "\n",
        encoding="utf-8",
    )
    games = load_games((tmp_path,))
    assert set(games.keys()) == {"dup", "unique"}
    assert games["dup"]["outcome_home_win"] == 1  # first-seen wins


def test_load_games_missing_dir_returns_empty(tmp_path):
    assert load_games((tmp_path / "does_not_exist",)) == {}


# ---------------------------------------------------------------------------
# measure_pm_recalibration end-to-end (synthetic corpus)
# ---------------------------------------------------------------------------


def test_measure_pm_recalibration_insufficient_data_on_empty(tmp_path):
    report = measure_pm_recalibration(pm_dirs=(tmp_path,))
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert report["edge_claimed"] is False


def test_measure_pm_recalibration_end_to_end_synthetic(tmp_path):
    import random
    rng = random.Random(42)
    lines = []
    for i in range(80):
        outcome = 1 if rng.random() < 0.55 else 0
        base = 0.55 if outcome else 0.45
        probs = [max(0.02, min(0.98, base + rng.uniform(-0.15, 0.15))) for _ in range(10)]
        lines.append(json.dumps(_game(date="2023-04-01", outcome=outcome, probs=probs, slug=f"t{i}")))
    for i in range(80):
        outcome = 1 if rng.random() < 0.55 else 0
        base = 0.55 if outcome else 0.45
        probs = [max(0.02, min(0.98, base + rng.uniform(-0.15, 0.15))) for _ in range(10)]
        lines.append(json.dumps(_game(date="2025-04-01", outcome=outcome, probs=probs, slug=f"v{i}")))
    f = tmp_path / "synthetic.jsonl"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = measure_pm_recalibration(pm_dirs=(tmp_path,), min_history=20, refit_every=5)
    assert report["edge_claimed"] is False
    assert report["verdict"] in ("MATCH", "IMPROVED", "WORSENED")
    assert report["n_validate_games"] == 80
    json.dumps(report, default=str)  # must be JSON-serializable


def test_real_corpus_smoke():
    if not any(d.exists() for d in _PM_DIRS):
        pytest.skip("local PM MLB corpus absent (gitignored data/ dir)")
    report = measure_pm_recalibration(refit_every=50)
    assert report["edge_claimed"] is False
    assert report["verdict"] in ("MATCH", "IMPROVED", "WORSENED", "INSUFFICIENT_DATA")
    json.dumps(report, default=str)
