"""test_team_stats_aggregation.py — cycle 99e (loop 5).

Pins the team_advanced_stats parquet build + opp-context rolling-5 join
contracts. Four cases:

1. The aggregation script (aggregate_team_stats_from_boxscores.py)
   produces a parquet with the expected schema given a synthetic
   boxscore_adv cache.
2. Per-(team, date) rolling computation excludes the target game itself
   (no leakage) — opp_team_<col>_l5 and opp_def_<stat>_l5 both honour
   the "strictly before current_date" contract.
3. build_pergame_dataset row dict now carries opp_def_<stat>_l5 +
   opp_team_<col>_l5 keys when the parquet is present.
4. build_pergame_dataset is a graceful no-op when the parquet is absent
   — row keys still exist but values are None / no leakage.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Dict, List

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    _TEAM_ADV_COLS,
    _TEAM_ADV_FEATURE_KEYS,
    _TeamAdvancedL5,
    build_opponent_defense,
    build_pergame_dataset,
    build_team_advanced_l5,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_gamelog(tmp_path, pid: int, games: List[dict],
                   season: str = "2024-25") -> None:
    (tmp_path / f"gamelog_{pid}_{season}.json").write_text(
        json.dumps(games), encoding="utf-8"
    )


def _opp_games(opp: str, dates_and_pts: List[tuple]) -> List[dict]:
    """A list of synthetic gamelog rows where OPP is the opponent.

    `build_opponent_defense` keys `allowed[opp]` by what the player's MATCHUP
    string reports as the opposing team — so to seed "GSW allowed pts", we
    need rows like {MATCHUP: "XXX vs. GSW"} (player on XXX, opponent GSW).
    """
    out = []
    for gdate, pts in dates_and_pts:
        out.append({
            "GAME_DATE": gdate, "MATCHUP": f"XXX vs. {opp}",
            "PTS": pts, "REB": 5, "AST": 4, "FG3M": 1,
            "STL": 1, "BLK": 0, "TOV": 2, "MIN": 30,
        })
    return out


def _write_team_adv_parquet(path: str, rows: List[Dict]) -> None:
    import pandas as pd  # noqa: PLC0415
    pd.DataFrame(rows).to_parquet(path, index=False)


# ── 1. aggregation script schema ─────────────────────────────────────────────

def test_aggregation_script_produces_expected_schema(tmp_path, monkeypatch):
    """Run the aggregation script against a synthetic boxscore_adv cache and
    verify the resulting parquet has the documented schema."""
    pytest.importorskip("pyarrow")
    import pandas as pd  # noqa: PLC0415

    nba_cache = tmp_path / "nba"
    nba_cache.mkdir()

    # Two synthetic boxscore_adv files (two games) — minimal teams entries.
    for i, (gid, gdate) in enumerate([
        ("0022400061", "2024-10-22"),
        ("0022400062", "2024-10-23"),
    ]):
        payload = {
            "game_id": gid,
            "teams": [
                {
                    "teamtricode": "LAL",
                    "offensiverating": 115.0 + i,
                    "defensiverating": 110.0 - i,
                    "pace": 100.0,
                    "offensivereboundpercentage": 0.25,
                    "defensivereboundpercentage": 0.72,
                    "assistpercentage": 0.55,
                    "effectivefieldgoalpercentage": 0.55,
                    "trueshootingpercentage": 0.58,
                    "turnoverratio": 13.0,
                },
                {
                    "teamtricode": "GSW",
                    "offensiverating": 118.0,
                    "defensiverating": 112.0,
                    "pace": 101.0,
                    "offensivereboundpercentage": 0.22,
                    "defensivereboundpercentage": 0.74,
                    "assistpercentage": 0.60,
                    "effectivefieldgoalpercentage": 0.57,
                    "trueshootingpercentage": 0.60,
                    "turnoverratio": 12.5,
                },
            ],
        }
        (nba_cache / f"boxscore_adv_{gid}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    # season_games file pairs game_id -> date so the script can join.
    season_payload = {"v": 1, "rows": [
        {"game_id": "0022400061", "game_date": "2024-10-22"},
        {"game_id": "0022400062", "game_date": "2024-10-23"},
    ]}
    (nba_cache / "season_games_2024-25.json").write_text(
        json.dumps(season_payload), encoding="utf-8"
    )

    out_path = tmp_path / "team_advanced_stats.parquet"

    # Monkey-patch the script's module-level _NBA_CACHE/_OUT_PATH so it
    # writes to our tmp dir instead of the real data/ tree.
    import scripts.aggregate_team_stats_from_boxscores as agg
    monkeypatch.setattr(agg, "_NBA_CACHE", str(nba_cache))
    monkeypatch.setattr(agg, "_OUT_PATH", str(out_path))

    agg.main()

    assert out_path.exists(), "aggregation must write the parquet"
    df = pd.read_parquet(out_path)
    # Schema: game_id, game_date, team_tricode, then each _TEAM_ADV_COLS column.
    expected_cols = {"game_id", "game_date", "team_tricode"} | set(_TEAM_ADV_COLS)
    assert expected_cols.issubset(set(df.columns)), (
        f"missing columns: {expected_cols - set(df.columns)}"
    )
    # 2 games x 2 teams = 4 rows.
    assert len(df) == 4
    assert set(df["team_tricode"].unique()) == {"LAL", "GSW"}
    # off_rtg from game 2's LAL row is 116.0 (115.0 + 1).
    lal_g2 = df[(df["team_tricode"] == "LAL") & (df["game_id"] == "0022400062")]
    assert lal_g2["off_rtg"].iloc[0] == pytest.approx(116.0)


# ── 2. rolling computation excludes target game (no leakage) ────────────────

def test_rolling_l5_excludes_target_game(tmp_path):
    """opp_team_<col>_l5 must use STRICTLY-prior games; the row for date D
    cannot see the opponent's own game on date D."""
    pytest.importorskip("pyarrow")

    # 6 games for opp GSW: first 5 have off_rtg=110, the sentinel 6th has 9999.
    # A lookup for the 6th date must average ONLY the first 5 (= 110), and
    # NEVER include the sentinel.
    rows = []
    dates = ["2024-10-22", "2024-10-25", "2024-10-28",
             "2024-10-30", "2024-11-02", "2024-11-05"]
    for i, gdate in enumerate(dates):
        off_rtg = 9999.0 if i == 5 else 110.0
        row = {
            "game_id": f"00224000{60+i:02d}",
            "game_date": gdate,
            "team_tricode": "GSW",
            "off_rtg": off_rtg,
            "def_rtg": 108.0,
            "pace": 100.0,
            "oreb_pct": 0.25,
            "dreb_pct": 0.72,
            "ast_pct": 0.60,
            "efg_pct": 0.55,
            "ts_pct": 0.58,
            "tov_ratio": 13.0,
        }
        rows.append(row)

    parquet = tmp_path / "team_advanced_stats.parquet"
    _write_team_adv_parquet(str(parquet), rows)

    wrap = build_team_advanced_l5(parquet_path=str(parquet))
    assert isinstance(wrap, _TeamAdvancedL5)
    assert len(wrap) == 6

    # Lookup for the 6th game's DATE must see only the first 5 prior games.
    feats = wrap.features("GSW", datetime(2024, 11, 5))
    assert feats["opp_team_off_rtg_l5"] == pytest.approx(110.0), (
        f"leaked sentinel: got {feats['opp_team_off_rtg_l5']}, expected 110.0"
    )
    # Other columns unchanged across all 6 rows so L5 == constant.
    assert feats["opp_team_def_rtg_l5"] == pytest.approx(108.0)
    assert feats["opp_team_pace_l5"] == pytest.approx(100.0)

    # Lookup BEFORE the very first game (no prior history) → all None.
    feats_early = wrap.features("GSW", datetime(2024, 10, 21))
    for k in _TEAM_ADV_FEATURE_KEYS:
        assert feats_early[k] is None

    # Unknown team → all None.
    feats_unknown = wrap.features("ZZZ", datetime(2024, 11, 5))
    for k in _TEAM_ADV_FEATURE_KEYS:
        assert feats_unknown[k] is None


# ── 3. build_pergame_dataset row dict carries new keys when parquet present ──

def test_build_pergame_dataset_attaches_opp_context_keys(tmp_path, monkeypatch):
    """When team_advanced_stats.parquet exists, every emitted row dict
    carries the opp_team_<col>_l5 + opp_def_<stat>_l5 keys."""
    pytest.importorskip("pyarrow")

    # 1) Target player: 5 prior LAL home games vs. GSW (build_opponent_defense
    #    iterates EVERY gamelog so GSW needs its own gamelog file too).
    pid = 9991234
    target_games = [
        {"GAME_DATE": "Oct 22, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 20, "REB": 5, "AST": 4, "FG3M": 1,
         "STL": 1, "BLK": 0, "TOV": 2, "MIN": 30},
        {"GAME_DATE": "Oct 25, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 22, "REB": 6, "AST": 3, "FG3M": 2,
         "STL": 0, "BLK": 1, "TOV": 1, "MIN": 32},
        {"GAME_DATE": "Oct 28, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 18, "REB": 4, "AST": 5, "FG3M": 0,
         "STL": 2, "BLK": 0, "TOV": 3, "MIN": 28},
        {"GAME_DATE": "Oct 30, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 25, "REB": 7, "AST": 4, "FG3M": 3,
         "STL": 1, "BLK": 0, "TOV": 2, "MIN": 34},
        {"GAME_DATE": "Nov 02, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 19, "REB": 5, "AST": 6, "FG3M": 1,
         "STL": 1, "BLK": 1, "TOV": 1, "MIN": 30},
        {"GAME_DATE": "Nov 05, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 24, "REB": 4, "AST": 5, "FG3M": 2,
         "STL": 0, "BLK": 0, "TOV": 2, "MIN": 31},
    ]
    _write_gamelog(tmp_path, pid, target_games)

    # 2) Synthetic opp_games for GSW so build_opponent_defense has data to
    #    populate the L5 allowed window.
    gsw_pid = 8881234
    gsw_games = _opp_games("GSW", [
        ("Oct 21, 2024", 15),
        ("Oct 24, 2024", 18),
        ("Oct 27, 2024", 20),
        ("Oct 29, 2024", 16),
        ("Nov 01, 2024", 22),
    ])
    _write_gamelog(tmp_path, gsw_pid, gsw_games)

    # 3) team_advanced_stats parquet with 5 GSW games before Nov 05.
    team_rows = []
    for i, gdate in enumerate(["2024-10-21", "2024-10-24", "2024-10-27",
                               "2024-10-29", "2024-11-01"]):
        team_rows.append({
            "game_id": f"00224000{80+i:02d}",
            "game_date": gdate,
            "team_tricode": "GSW",
            "off_rtg": 115.0,
            "def_rtg": 112.0,
            "pace": 101.0,
            "oreb_pct": 0.25,
            "dreb_pct": 0.74,
            "ast_pct": 0.60,
            "efg_pct": 0.55,
            "ts_pct": 0.58,
            "tov_ratio": 13.0,
        })
    parquet = tmp_path / "team_advanced_stats.parquet"
    _write_team_adv_parquet(str(parquet), team_rows)
    monkeypatch.setattr(
        "src.prediction.prop_pergame._TEAM_ADV_STATS_PATH", str(parquet)
    )

    rows, _cols = build_pergame_dataset(gamelog_dir=str(tmp_path), min_prior=0)
    assert rows, "expected at least one emitted row"
    # Find the row dated Nov 5 (target) — it should have all opp_team_<col>_l5
    # populated with the constant 115.0 / 112.0 / etc. and opp_def_<stat>_l5
    # populated from the 5 GSW gamelog rows.
    target = next((r for r in rows
                   if r["date"].startswith("2024-11-05")), None)
    assert target is not None, "missing Nov 5 target row"
    for k in _TEAM_ADV_FEATURE_KEYS:
        assert k in target, f"row dict missing {k}"
        assert target[k] is not None, f"{k} should be populated, got None"
    assert target["opp_team_off_rtg_l5"] == pytest.approx(115.0)
    assert target["opp_team_def_rtg_l5"] == pytest.approx(112.0)
    assert target["opp_team_pace_l5"] == pytest.approx(101.0)

    # opp_def_<stat>_l5 keys exist for every stat and at least pts/reb are
    # populated (we created 5 GSW rows so the L5 window has data).
    for s in STATS:
        k = f"opp_def_{s}_l5"
        assert k in target, f"row dict missing {k}"
    assert target["opp_def_pts_l5"] is not None
    # _OpponentDefense pools EVERY player gamelog row whose MATCHUP names
    # GSW as the opponent — that includes our target player's 5 prior games
    # vs. GSW AND the 5 seed XXX-vs-GSW rows. The L5 window picks the 5
    # most-recent dates strictly before Nov 5: Oct 28 (18), Oct 29 (16),
    # Oct 30 (25), Nov 01 (22), Nov 02 (19) → sum 100, mean 20.0.
    assert target["opp_def_pts_l5"] == pytest.approx(20.0)


# ── 4. graceful no-op when parquet absent ────────────────────────────────────

def test_no_op_when_team_advanced_parquet_absent(tmp_path, monkeypatch):
    """Absent parquet → opp_team_<col>_l5 keys still present, all None.

    Existing opp_def_<stat>_l5 keys come from gamelog scan so they still
    populate (no parquet dependency) — that's tested too.
    """
    pid = 9991234
    target_games = [
        {"GAME_DATE": "Oct 22, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 20, "REB": 5, "AST": 4, "FG3M": 1,
         "STL": 1, "BLK": 0, "TOV": 2, "MIN": 30},
        {"GAME_DATE": "Oct 25, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 22, "REB": 6, "AST": 3, "FG3M": 2,
         "STL": 0, "BLK": 1, "TOV": 1, "MIN": 32},
    ]
    _write_gamelog(tmp_path, pid, target_games)
    # Also seed a GSW gamelog so opp_def L5 has at least 1 prior to draw from.
    _write_gamelog(tmp_path, 8881234, _opp_games("GSW", [
        ("Oct 20, 2024", 15),
    ]))

    missing = str(tmp_path / "does_not_exist.parquet")
    assert not os.path.exists(missing)
    monkeypatch.setattr(
        "src.prediction.prop_pergame._TEAM_ADV_STATS_PATH", missing
    )

    rows, _cols = build_pergame_dataset(gamelog_dir=str(tmp_path), min_prior=0)
    assert rows
    # Every row carries the team_adv L5 keys with value None.
    for r in rows:
        for k in _TEAM_ADV_FEATURE_KEYS:
            assert k in r, f"missing key {k}"
            assert r[k] is None, f"absent parquet → {k} must be None, got {r[k]!r}"
        # opp_def_<stat>_l5 still present (gamelog-derived, not parquet).
        for s in STATS:
            assert f"opp_def_{s}_l5" in r


# ── bonus: build_opponent_defense exposes l5_allowed correctly ───────────────

def test_l5_allowed_is_strict_prior(tmp_path):
    """oppdef.l5_allowed honours the strictly-before-date contract."""
    # 6 GSW games — pts = 10, 20, 30, 40, 50, 999. Lookup at the 6th date
    # must average ONLY the first 5 (= 30).
    _write_gamelog(tmp_path, 8881234, _opp_games("GSW", [
        ("Oct 22, 2024", 10),
        ("Oct 25, 2024", 20),
        ("Oct 28, 2024", 30),
        ("Oct 30, 2024", 40),
        ("Nov 02, 2024", 50),
        ("Nov 05, 2024", 999),  # sentinel
    ]))

    oppdef = build_opponent_defense(gamelog_dir=str(tmp_path))
    feats = oppdef.l5_allowed("GSW", datetime(2024, 11, 5))
    assert feats["opp_def_pts_l5"] == pytest.approx(30.0), (
        f"leaked sentinel: got {feats['opp_def_pts_l5']}, expected 30.0"
    )
    # Lookup before first game → all None.
    feats_early = oppdef.l5_allowed("GSW", datetime(2024, 10, 21))
    for s in STATS:
        assert feats_early[f"opp_def_{s}_l5"] is None
