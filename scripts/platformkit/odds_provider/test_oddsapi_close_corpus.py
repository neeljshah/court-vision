"""Per-file tests for oddsapi_close_corpus (pure close-selection + outcome join)."""
from __future__ import annotations

from scripts.platformkit.odds_provider import oddsapi_close_corpus as cc


def _row(snap, anchor=True, home="Pirates", away="Phillies", market="h2h",
         names=None, probs=None, commence="2026-05-15T22:41:00Z"):
    dev = None
    if anchor:
        dev = {"names": names or [home, away], "probs": probs or [0.55, 0.45],
               "z": 0.02, "booksum": 1.02}
    return {"event_id": "e1", "market": market, "commence_time": commence,
            "snapshot_ts": snap, "date": "2026-05-15", "home": home, "away": away,
            "anchor_devig": dev}


def test_select_closes_picks_latest_pregame():
    rows = [
        _row("2026-05-15T18:00:00Z"),          # early pregame
        _row("2026-05-15T22:25:00Z"),          # latest pregame = THE close
        _row("2026-05-15T23:30:00Z"),          # AFTER commence -> in-play, dropped
    ]
    closes = cc.select_closes(rows)
    assert len(closes) == 1
    assert closes[0]["snapshot_ts"] == "2026-05-15T22:25:00Z"


def test_select_closes_drops_unanchored():
    assert cc.select_closes([_row("2026-05-15T22:00:00Z", anchor=False)]) == []


def test_select_closes_separates_markets():
    rows = [_row("2026-05-15T22:00:00Z", market="h2h"),
            _row("2026-05-15T22:00:00Z", market="totals", names=["Over", "Under"])]
    assert len(cc.select_closes(rows)) == 2


def test_home_prob_aligned_to_home():
    # names ordered away-first; _home_prob must still pick the HOME entry
    c = _row("2026-05-15T22:00:00Z", names=["Phillies", "Pirates"], probs=[0.4, 0.6])
    assert abs(cc._home_prob(c) - 0.6) < 1e-9


def test_to_home_win_states_joins_and_excludes_unlabeled():
    closes = cc.select_closes([
        _row("2026-05-15T22:00:00Z", home="Pirates", away="Phillies"),
    ])
    # result_fn: Pirates (home) won
    states = cc.to_home_win_states(closes, lambda c: 1, "mlb")
    assert len(states) == 1
    s = states[0]
    assert s["outcome"] == 1
    assert abs(s["devig_close_prob"] - 0.55) < 1e-9
    assert s["home"] == "Pirates" and s["game_id"].startswith("mlb-")
    # unlabeled (result_fn -> None) excluded
    assert cc.to_home_win_states(closes, lambda c: None, "mlb") == []


def test_brier_of_perfect_and_coin():
    perfect = [{"devig_close_prob": 1.0, "outcome": 1}, {"devig_close_prob": 0.0, "outcome": 0}]
    assert cc._brier(perfect) == 0.0
    coin = [{"devig_close_prob": 0.5, "outcome": 1}, {"devig_close_prob": 0.5, "outcome": 0}]
    assert abs(cc._brier(coin) - 0.25) < 1e-9


def test_mlb_result_fn_joins_datetime64_box_dates(tmp_path):
    # REGRESSION: espn_boxscores.parquet stores "date" as datetime64 (domains.mlb.
    # ingest_espn_box normalises it that way). A bare str(...)[:8] slice on a
    # datetime64 value yields "2026-06-" (month-only, with dashes) which NEVER
    # matches _game_dates()'s "YYYYMMDD" key -> the whole join silently returned
    # None for every close (build_states('mlb') went to 0 states). Locks in the
    # pd.to_datetime(...).dt.strftime("%Y%m%d") fix.
    import pandas as pd
    box = pd.DataFrame([
        {"date": pd.Timestamp("2026-05-15"), "home_abbr": "PIT", "away_abbr": "PHI",
         "home_score": 5.0, "away_score": 3.0},
    ])
    domains_root = tmp_path / "mlb"
    domains_root.mkdir()
    box.to_parquet(domains_root / "espn_boxscores.parquet", index=False)

    fn = cc._mlb_result_fn(domains_root)
    close = {"home": "Pittsburgh Pirates", "away": "Philadelphia Phillies",
            "commence_time": "2026-05-15T22:41:00Z"}
    assert fn(close) == 1  # home (Pirates) won 5-3


def test_mlb_result_fn_unresolved_game_is_none(tmp_path):
    import pandas as pd
    box = pd.DataFrame([
        {"date": pd.Timestamp("2026-05-15"), "home_abbr": "PIT", "away_abbr": "PHI",
         "home_score": 5.0, "away_score": 3.0},
    ])
    domains_root = tmp_path / "mlb"
    domains_root.mkdir()
    box.to_parquet(domains_root / "espn_boxscores.parquet", index=False)

    fn = cc._mlb_result_fn(domains_root)
    close = {"home": "New York Yankees", "away": "Boston Red Sox",
            "commence_time": "2026-05-15T22:41:00Z"}
    assert fn(close) is None  # not in this box frame -> unresolved, never guessed
