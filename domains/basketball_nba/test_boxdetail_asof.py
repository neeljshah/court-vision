"""Tests for domains.basketball_nba.boxdetail_asof -- leak-free box-detail as-of."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.boxdetail_asof import STATS, build_boxdetail_asof


def _game(event_id, date, home, away, hfb, afb, hpaint=40.0, apaint=40.0,
          htov=15.0, atov=15.0, hlead=5.0, alead=5.0, htech=0.0, atech=0.0,
          hflag=0.0, aflag=0.0):
    return {
        "event_id": event_id, "date": date, "home_abbr": home, "away_abbr": away,
        "home_fast_break_pts": hfb, "away_fast_break_pts": afb,
        "home_paint_pts": hpaint, "away_paint_pts": apaint,
        "home_tov_pts": htov, "away_tov_pts": atov,
        "home_largest_lead": hlead, "away_largest_lead": alead,
        "home_tech": htech, "away_tech": atech,
        "home_flagrant": hflag, "away_flagrant": aflag,
    }


def _toy_games(rows: list) -> pd.DataFrame:
    """games.parquet-shaped frame for the id-bridge: game_id == event_id here
    (same tricodes/dates as the espn_box rows), so the schedule-key join
    matches every toy row 1:1 and downstream assertions can keep using the
    event_id strings directly."""
    return pd.DataFrame([
        {"game_id": r["event_id"], "date": r["date"],
         "home_team": r["home_abbr"], "away_team": r["away_abbr"]}
        for r in rows
    ])


def _toy_frame() -> pd.DataFrame:
    # Team A plays 3 games; team B and C fill the other side. Detail is
    # missing (NaN) on game g0 to prove a partial-coverage game never counts
    # as a "prior game" and never corrupts the running mean.
    rows = [
        _game("g0", "2026-01-01", "A", "B", np.nan, np.nan, hpaint=np.nan, apaint=np.nan,
              htov=np.nan, atov=np.nan, hlead=np.nan, alead=np.nan),  # no box-detail this game
        _game("g1", "2026-01-03", "A", "B", 10.0, 6.0),        # A's first COUNTED game (home)
        _game("g2", "2026-01-05", "C", "A", 4.0, 20.0),        # A away, 2nd counted game
        _game("g3", "2026-01-07", "A", "B", 8.0, 2.0),         # A home, 3rd counted game
    ]
    return pd.DataFrame(rows)


def test_walk_forward_snapshot_before_update():
    rows = _toy_frame().to_dict("records")
    df = pd.DataFrame(rows)
    gm = _toy_games(rows)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "boxdetail_asof.parquet"
        build_boxdetail_asof(espn_box=df, games=gm, out_path=str(dest))
        out = pd.read_parquet(dest).set_index("game_id")

    # g0 has NaN raw fast_break_pts -> must not count as a prior game for A.
    assert pd.isna(out.loc["g0", "home_fast_break_pts_asof"])
    assert out.loc["g0", "home_n_prior"] == 0

    # g1: A's first COUNTED game (g0 didn't count) -> still zero prior -> NaN.
    assert pd.isna(out.loc["g1", "home_fast_break_pts_asof"])
    assert out.loc["g1", "home_n_prior"] == 0

    # g2: A away, one prior counted game (g1 home fast_break_pts=10.0).
    assert out.loc["g2", "away_fast_break_pts_asof"] == 10.0
    assert out.loc["g2", "away_n_prior"] == 1

    # g3: A home, two prior counted games (10.0 from g1, 20.0 from g2) -> mean 15.0.
    assert out.loc["g3", "home_fast_break_pts_asof"] == 15.0
    assert out.loc["g3", "home_n_prior"] == 2

    # diff columns are home-away and L10 tracks the same short history (< window).
    assert out.loc["g3", "fast_break_pts_diff_asof"] == (
        out.loc["g3", "home_fast_break_pts_asof"] - out.loc["g3", "away_fast_break_pts_asof"]
    )
    assert out.loc["g3", "home_fast_break_pts_l10_asof"] == out.loc["g3", "home_fast_break_pts_asof"]


def test_foul_trouble_combines_tech_and_flagrant():
    rows = [
        _game("g0", "2026-01-01", "A", "B", 5.0, 5.0, htech=1.0, hflag=2.0),
        _game("g1", "2026-01-03", "A", "B", 5.0, 5.0),
    ]
    gm = _toy_games(rows)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "boxdetail_asof.parquet"
        build_boxdetail_asof(espn_box=pd.DataFrame(rows), games=gm, out_path=str(dest))
        out = pd.read_parquet(dest).set_index("game_id")
    # g1's trailing foul_trouble for A = g0's tech(1.0) + flagrant(2.0) = 3.0.
    assert out.loc["g1", "home_foul_trouble_asof"] == 3.0


def test_output_columns_cover_all_stats_both_windows():
    from domains.basketball_nba.boxdetail_asof import OUTPUT_COLS
    for s in STATS:
        assert f"{s}_diff_asof" in OUTPUT_COLS
        assert f"{s}_l10_diff_asof" in OUTPUT_COLS


if __name__ == "__main__":
    test_walk_forward_snapshot_before_update()
    test_foul_trouble_combines_tech_and_flagrant()
    test_output_columns_cover_all_stats_both_windows()
    print("OK: boxdetail_asof leak-free walk-forward self-checks pass.")
