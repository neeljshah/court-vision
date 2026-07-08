"""Per-file test for domains.basketball_wnba.claims_player_form -- synthetic
frame (no real parquet dependency) covering the per-36/eFG math and the
declared n-floor exclusion behavior for both windows.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_claims_player_form.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_wnba.claims_player_form import build_claims, write_claims


def _rows(player_id: str, n_games: int, **per_game) -> list[dict]:
    out = []
    for i in range(n_games):
        row = {"game_id": f"{player_id}_{i:03d}", "game_date": f"2026-05-{i + 1:02d}",
               "player_id": player_id, "player_name": f"Player {player_id}"}
        row.update(per_game)
        out.append(row)
    return out


@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    rows = []
    # player 1: 15 games, clears the full-window floor (>=15)
    rows += _rows("1", 15, minutes=30, pts=15, reb=5, ast=3, tov=2,
                  fga=10, fgm=5, fg3a=3, fg3m=1, fta=2, ftm=1)
    # player 2: 10 games, clears last_10 floor (>=5) but NOT the full floor (>=15)
    rows += _rows("2", 10, minutes=24, pts=8, reb=4, ast=2, tov=1,
                  fga=8, fgm=4, fg3a=2, fg3m=0, fta=1, ftm=1)
    # player 3: 3 games, clears neither floor
    rows += _rows("3", 3, minutes=10, pts=4, reb=1, ast=1, tov=1,
                  fga=4, fgm=2, fg3a=1, fg3m=0, fta=0, ftm=0)
    return pd.DataFrame(rows)


def _claim(claims, metric, window):
    return next(c for c in claims if c["criteria"]["metric"] == metric and c["criteria"]["window"] == window)


def test_pts_per36_math_and_full_window_floor(synthetic_df):
    claims = build_claims(synthetic_df, "full")
    c = _claim(claims, "pts_per36", "full")
    assert c["n_considered"] == 3
    assert c["n_excluded_below_floor"] == 2  # players 2 and 3 fail games>=15
    assert len(c["ranking"]) == 1
    top = c["ranking"][0]
    assert top["player_id"] == "1"
    assert top["value"] == pytest.approx(36 * 15 / 30, abs=1e-4)  # 18.0
    assert top["n"] == 15
    assert top["deviation"] == 0.0  # sole survivor == league mean


def test_efg_pct_math(synthetic_df):
    claims = build_claims(synthetic_df, "full")
    c = _claim(claims, "efg_pct", "full")
    top = c["ranking"][0]
    expected = (5 * 15 + 0.5 * 1 * 15) / (10 * 15)  # (sum fgm + .5*sum fg3m)/sum fga = 0.55
    assert top["value"] == pytest.approx(expected, abs=1e-4)


def test_last_10_window_includes_lower_game_player(synthetic_df):
    claims = build_claims(synthetic_df, "last_10")
    c = _claim(claims, "pts_per36", "last_10")
    ids = {r["player_id"] for r in c["ranking"]}
    assert ids == {"1", "2"}  # player 3 (3 games) fails games>=5; player 2 (10) clears it
    assert c["n_excluded_below_floor"] == 1
    row2 = next(r for r in c["ranking"] if r["player_id"] == "2")
    assert row2["n"] == 10
    assert row2["value"] == pytest.approx(36 * 8 / 24, abs=1e-4)  # 12.0
    row1 = next(r for r in c["ranking"] if r["player_id"] == "1")
    assert row1["n"] == 10  # windowed to the last 10 of player 1's 15 games


def test_usage_proxy_fallback_caveat_present(synthetic_df):
    claims = build_claims(synthetic_df, "full")
    c = _claim(claims, "usage_proxy_per36", "full")
    assert any("USAGE FALLBACK" in cav for cav in c["caveats"])


def test_write_claims_jsonl_roundtrip(tmp_path, monkeypatch, synthetic_df):
    import domains.basketball_wnba.claims_player_form as mod
    out = tmp_path / "claims.jsonl"
    monkeypatch.setattr(mod, "CLAIMS_PATH", out)
    claims = build_claims(synthetic_df, "full")
    write_claims(claims)
    lines = out.read_text(encoding="ascii").strip().split("\n")
    assert len(lines) == len(claims)
    for line in lines:
        row = json.loads(line)
        assert {"claim_id", "criteria", "ranking", "source_files", "n_considered"}.issubset(row.keys())
