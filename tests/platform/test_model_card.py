"""Tests for scripts.platformkit.model_card — synthetic injected loader, no pandas."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.model_card import build_card, write_card


def _make_games(n=700, seed=0):
    rng = np.random.default_rng(seed)
    strong = [f"S{i}" for i in range(5)]
    weak = [f"W{i}" for i in range(5)]
    teams = strong + weak
    games = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        ph = 0.78 if (h in strong and a in weak) else (0.30 if (h in weak and a in strong) else 0.5)
        season = "2020" if i < n // 2 else "2021"
        games.append({"home": str(h), "away": str(a), "season": season,
                      "home_win": float(rng.random() < ph)})
    return games


def _loader(games):
    base_y = np.array([g["home_win"] for g in games])
    base_p = np.full(len(games), 0.5)
    return lambda sport: (games, base_p, base_y)


def test_build_card_markdown():
    games = _make_games()
    card = build_card("nba", min_history=150, refit_every=20, loader=_loader(games))
    assert card["sport"] == "nba"
    md = card["markdown"]
    assert "Model Card" in md and "Brier" in md and "ECE" in md
    assert "not a market edge" in md.lower()
    assert "chosen calibrator" in md.lower()
    # no edge/roi claim leaked
    assert "roi" not in md.lower() and "+ev" not in md.lower()
    # the report carries the composed metrics
    assert "raw_elo" in card["report"] and "calibrated_elo" in card["report"]


def test_write_card(tmp_path):
    games = _make_games()
    card = build_card("nba", min_history=150, loader=_loader(games))
    path = write_card("nba", card, organized_root=tmp_path)
    assert path is not None
    p = tmp_path / "NBA" / "_Model_Card.md"
    assert p.is_file() and "Model Card" in p.read_text(encoding="utf-8")


def test_error_sport_handled():
    card = build_card("nba", min_history=500, loader=lambda s: (_make_games(50), None, None))
    assert "error" in card and write_card("nba", card) is None


def test_parse_card_metrics_roundtrip(tmp_path):
    from scripts.platformkit.model_card import parse_card_metrics
    games = _make_games()
    card = build_card("nba", min_history=150, loader=_loader(games))
    write_card("nba", card, organized_root=tmp_path)
    m = parse_card_metrics("nba", organized_root=tmp_path)
    assert m is not None
    assert set(m) == {"brier", "logloss", "ece", "calibrator"}
    assert 0.0 <= m["brier"] <= 1.0
    # absent card -> None (graceful)
    assert parse_card_metrics("mlb", organized_root=tmp_path) is None
