"""No-leak property tests for ingame_blend_families.py (split out of
test_ingame_blend_families.py to keep both files under the 300 LOC cap).

Covers: the ADOPTED anchored constants match a fresh fit on the real 2024
corpus (no drift), and the explicit no-leak PROPERTY tests the LANE-4 brief
requires -- 2026 games/outcomes cannot move a fit restricted to 2024 rows,
whether by simply being present in the corpus or by having their outcomes
actively mutated.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingame_blend_no_leak.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from domains.basketball_wnba.ingame_blend_families import (
    build_corpus_with_p0,
    build_rows,
    fit_all_families,
    fit_anchored_params,
    fit_naive_k,
)


def _synthetic_games(n_per_season: int = 20) -> pd.DataFrame:
    rows = []
    eid = 0
    for season, start in [("2024", "2024-05-03"), ("2025", "2025-05-02"), ("2026", "2026-04-25")]:
        base = pd.Timestamp(start)
        for i in range(n_per_season):
            home_win = 1.0 if i % 2 == 0 else 0.0
            hs, as_ = (85.0, 78.0) if home_win else (78.0, 85.0)
            rows.append({
                "event_id": str(eid), "date": base + pd.Timedelta(days=i),
                "season": season, "home_team": "Aces", "away_team": "Fever",
                "home_score": hs, "away_score": as_, "home_win": home_win,
                "neutral_site": False, "status_name": "STATUS_FINAL",
            })
            eid += 1
    return pd.DataFrame(rows)


def _synthetic_linescores(games_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in games_df.iterrows():
        lead = 6.0 if g["home_win"] >= 0.5 else -6.0
        rows.append({
            "event_id": str(g["event_id"]),
            "home_end_q1": 20.0 + lead / 4, "away_end_q1": 20.0 - lead / 4,
            "home_half": 40.0 + lead / 2, "away_half": 40.0 - lead / 2,
            "home_end_q3": 60.0 + lead * 0.75, "away_end_q3": 60.0 - lead * 0.75,
        })
    return pd.DataFrame(rows)


@pytest.fixture()
def games_and_lines():
    games = _synthetic_games()
    lines = _synthetic_linescores(games)
    return games, lines


def test_fitted_params_recorded_in_module_match_frozen_constants():
    """The ADOPTED anchored_k/anchored_w0 (frozen in ingame_blend.py as
    ANCHORED_K/ANCHORED_W0) must match what fitting on the REAL 2024 corpus
    produces -- guards against the shipped constant drifting from the fit."""
    from domains.basketball_wnba.ingame_blend import ANCHORED_K, ANCHORED_W0

    repo = Path(__file__).resolve().parents[2]
    games_path = repo / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
    lines_path = repo / "data" / "domains" / "wnba" / "linescores.parquet"
    if not games_path.exists() or not lines_path.exists():
        pytest.skip("real WNBA corpus not present in this environment")

    games = pd.read_parquet(games_path)
    games["season"] = games["season"].astype(str)
    lines = pd.read_parquet(lines_path)
    lines["event_id"] = lines["event_id"].astype(str)

    train_2024 = build_corpus_with_p0(games, "2024")
    rows = build_rows(train_2024, lines)
    k, w0 = fit_anchored_params(rows)
    assert k == pytest.approx(ANCHORED_K, abs=1e-9)
    assert w0 == pytest.approx(ANCHORED_W0, abs=1e-9)


def test_fit_is_unaffected_by_appending_2026_rows(games_and_lines):
    """The property test the brief requires: fitting restricted to 2024 ROWS
    gives byte-identical params whether or not 2025/2026 games exist ANYWHERE
    in the corpus passed to build_corpus_with_p0/build_rows -- because the fit
    functions only ever consume the rows explicitly handed to them (2024-only
    train_rows), never the full games_df."""
    games, lines = games_and_lines

    wf_with_future = build_corpus_with_p0(games, "2024")
    rows_with_future = build_rows(wf_with_future, lines)
    fitted_with_future = fit_all_families(rows_with_future)

    # Now DROP every 2025/2026 game from the input games_df entirely and refit.
    games_2024_only = games[games["season"] == "2024"].reset_index(drop=True)
    wf_without_future = build_corpus_with_p0(games_2024_only, "2024")
    rows_without_future = build_rows(wf_without_future, lines)
    fitted_without_future = fit_all_families(rows_without_future)

    assert fitted_with_future == fitted_without_future


def test_fit_naive_k_unaffected_by_mutating_2026_outcomes(games_and_lines):
    """A stronger leak probe: even flipping every 2026 game's outcome/scores
    (as if the future had gone completely differently) must not move the
    2024-only fit by even one grid step, since 2026 rows are never included
    in train_rows in the first place."""
    games, lines = games_and_lines
    wf_2024 = build_corpus_with_p0(games, "2024")
    rows_2024 = build_rows(wf_2024, lines)
    k_before = fit_naive_k(rows_2024)

    mutated_games = games.copy()
    mask_2026 = mutated_games["season"] == "2026"
    mutated_games.loc[mask_2026, "home_win"] = 1.0 - mutated_games.loc[mask_2026, "home_win"]
    mutated_games.loc[mask_2026, "home_score"] = 999.0

    wf_2024_after = build_corpus_with_p0(mutated_games, "2024")
    rows_2024_after = build_rows(wf_2024_after, lines)
    k_after = fit_naive_k(rows_2024_after)

    assert k_before == k_after
