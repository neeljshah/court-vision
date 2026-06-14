"""Tests for scripts.platformkit.platform_scoreboard — synthetic injected loader."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.platform_scoreboard import (
    build_scoreboard,
    render_markdown,
    write_artifact,
)


def _loader(seed: int = 0):
    def _load(sport: str):
        rng = np.random.default_rng(seed + len(sport))
        n = 500
        # mild home edge so ratings have signal; binary outcomes
        games = [{"home": f"H{rng.integers(0, 6)}", "away": f"A{rng.integers(0, 6)}",
                  "season": "2020" if i < 250 else "2021",
                  "home_win": float(rng.random() < 0.55)} for i in range(n)]
        base_p = np.full(n, 0.5)
        base_y = np.array([g["home_win"] for g in games])
        return games, base_p, base_y
    return _load


def test_build_scoreboard_all_sports():
    rep = build_scoreboard(loader=_loader(), min_history=100)
    assert rep["n_sports"] == 4
    sports = {r["sport"] for r in rep["rows"]}
    assert sports == {"nba", "mlb", "tennis", "soccer"}
    for r in rep["rows"]:
        assert "metric" in r and "value" in r and "validated" in r
    assert "accuracy" in rep["note"].lower() and "edge" in rep["note"].lower()


def test_soccer_uses_rmse_metric():
    rep = build_scoreboard(["soccer"], loader=_loader(), min_history=100)
    r = rep["rows"][0]
    assert r["kind"] == "score" and "RMSE" in r["metric"]


def test_render_and_write(tmp_path):
    rep = build_scoreboard(["nba", "soccer"], loader=_loader(), min_history=100)
    md = render_markdown(rep)
    assert "Platform Prediction Scoreboard" in md and "Validated?" in md
    assert "not a market edge" in md.lower() or "no edge claimed" in md.lower()
    assert "roi" not in md.lower()
    path = write_artifact(rep, organized_root=tmp_path)
    assert (tmp_path / "_Index" / "_Platform_Scoreboard.md").is_file()
    assert path.endswith("_Platform_Scoreboard.md")
