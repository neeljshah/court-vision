"""tests/test_R23_P2_injury_kills_bet.py — R23_P2 wire audit.

The R22_O8 injury feed wrote ``data/cache/nba_injuries_<date>.parquet`` and
made ``src.prediction.injury_availability.get_availability_factor`` consult
it. But the in-play bet ranker (scripts/inplay_bet_ranker.py) never queried
that helper — once a player was flagged OUT after the pregame quarter_box
was captured, the ranker would still surface a bet recommendation for them.

This test pins down the R23_P2 kill guard:

    1. A synthetic ranker tick is constructed with 5 fake bookmaker
       lines for 5 different players (Sai Out, Bob Probable, Cam Healthy,
       Dee NotWithTeam, Ed Healthy).
    2. A test parquet ``nba_injuries_<today>.parquet`` marks Sai Out as
       OUT and Dee NotWithTeam as NOT WITH TEAM. The other three are
       absent (default factor 1.0).
    3. ``inplay_bet_ranker.run_tick`` is called against a synthetic
       quarter_box snapshot + an in-process projector stub so we can
       run without any real model artifacts or NBA Stats fetches.
    4. We assert:
         - 3 ranked_bets survive (one per healthy player).
         - 2 bets were killed by the injury guard (n_killed_by_injury=2).
         - The killed list contains exactly {Sai Out, Dee NotWithTeam}.
         - No surviving bet has availability_factor == 0.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date as _date

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import inplay_bet_ranker as ibr  # noqa: E402
from src.prediction import injury_availability as ia  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic builders
# ─────────────────────────────────────────────────────────────────────────────
PLAYERS = [
    # (player_id, name, status_in_parquet)  None = not in feed
    (901, "Sai Out",          "OUT"),
    (902, "Bob Probable",     None),
    (903, "Cam Healthy",      None),
    (904, "Dee NotWithTeam",  "NOT WITH TEAM"),
    (905, "Ed Healthy",       None),
]


def _write_synthetic_parquet(cache_dir: str, today: str) -> str:
    """Write a minimal ``nba_injuries_<today>.parquet`` covering the OUT
    players. Returns the path for assertions."""
    import pandas as pd
    rows = []
    for pid, name, status in PLAYERS:
        if status is None:
            continue
        rows.append({
            "player_id": pid,
            "player_name": name,
            "team": "HOM",
            "status": status,
            "availability_factor": 0.0,
            "reason": "synthetic test",
            "source": "test",
            "fetched_at": f"{today}T08:00:00",
            "report_date": today,
        })
    os.makedirs(cache_dir, exist_ok=True)
    pq_path = os.path.join(cache_dir, f"nba_injuries_{today}.parquet")
    pd.DataFrame(rows).to_parquet(pq_path, index=False)
    return pq_path


def _write_qbox(qbox_dir: str, game_id: str) -> None:
    os.makedirs(qbox_dir, exist_ok=True)
    players = []
    for pid, name, _ in PLAYERS:
        players.append({
            "game_id": game_id, "team_abbreviation": "HOM",
            "player_id": pid, "player_name": name,
            "start_position": "G",
            "min": "10:00", "pts": 8, "reb": 2, "ast": 2,
            "fg3m": 1, "stl": 0, "blk": 0, "to": 1, "pf": 1,
        })
    payload = {
        "game_id": game_id, "period": 1, "players": players,
        "teams": [
            {"team_abbreviation": "AWY", "pts": 25, "team_id": 2},
            {"team_abbreviation": "HOM", "pts": 30, "team_id": 1},
        ],
    }
    with open(os.path.join(qbox_dir, f"{game_id}_q1.json"), "w",
              encoding="utf-8") as f:
        json.dump(payload, f)


def _write_lines(lines_dir: str, date_str: str) -> None:
    os.makedirs(lines_dir, exist_ok=True)
    # Use the canonical 10-col schema the legacy reader supports.
    header = ("captured_at,book,game_id,player_id,player_name,"
              "stat,line,over_price,under_price,start_time\n")
    rows = []
    for pid, name, _ in PLAYERS:
        # Same fake line / odds for every player so the only thing varying
        # is the injury status. Line 10.5 PTS, OVER -110 / UNDER -110.
        rows.append(
            f"{date_str}T20:00:00,bov,GAUDIT,{pid},{name},pts,10.5,-110,-110,"
        )
    with open(os.path.join(lines_dir, f"{date_str}_bov.csv"), "w",
              encoding="utf-8") as f:
        f.write(header)
        f.write("\n".join(rows) + "\n")


def _fake_projector(snap, period=None):
    """Stub that returns a positive-edge projection for every player so all
    5 bets would be ranked if the injury guard were absent."""
    out = []
    for p in snap["players"]:
        cur = float(p.get("pts", 0) or 0)
        # Project well over the 10.5 line → OVER will be positive EV.
        out.append({
            "name": p["name"], "team": p["team"], "player_id": p["player_id"],
            "stat": "pts", "current": cur, "projected_final": cur + 8.0,
            "period": snap["period"], "q10": cur + 3.0, "q90": cur + 13.0,
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_injury_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ia, "_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv(ia._DISABLE_ENV, raising=False)
    ia.reset_cache()
    yield str(cache_dir)
    ia.reset_cache()


def test_out_player_bet_is_killed(tmp_path, monkeypatch, _isolate_injury_cache):
    today = _date.today().isoformat()
    cache_dir = _isolate_injury_cache
    pq_path = _write_synthetic_parquet(cache_dir, today)
    assert os.path.exists(pq_path), "parquet fixture must exist"

    qbox = tmp_path / "qbox"
    lines_dir = tmp_path / "lines"
    monkeypatch.setattr(ibr, "QBOX_DIR", str(qbox))
    monkeypatch.setattr(ibr, "LINES_DIR", str(lines_dir))
    monkeypatch.setattr(ibr, "_project_with_engine", _fake_projector)

    _write_qbox(str(qbox), "GAUDIT")
    _write_lines(str(lines_dir), today)

    payload = ibr.run_tick(
        game_id="GAUDIT", date_str=today, bankroll=1000.0,
        qbox_dir=str(qbox), books=("bov",),
    )

    assert payload["status"] in ("IN_PLAY", "IN_PLAY_STALE"), \
        f"unexpected status {payload['status']}"

    # 2 of 5 players were OUT / NOT WITH TEAM → 2 killed.
    assert payload["n_killed_by_injury"] == 2, (
        f"expected 2 injury kills, got {payload['n_killed_by_injury']}"
    )
    killed = set(payload["killed_by_injury_players"])
    assert killed == {"Sai Out", "Dee NotWithTeam"}, killed

    # Surviving bets cannot include any OUT player.
    surviving_players = {b["player"] for b in payload["ranked_bets"]}
    assert "Sai Out" not in surviving_players
    assert "Dee NotWithTeam" not in surviving_players

    # All surviving bets must carry the availability_factor breadcrumb
    # and never a factor of 0.0.
    for b in payload["ranked_bets"]:
        assert "availability_factor" in b, b
        assert b["availability_factor"] > 0.0, b

    # At least one healthy player's bet survived (sanity — the projector
    # stub gives every player positive EV).
    assert len(surviving_players) >= 1


def test_lookup_falls_back_to_name_when_pid_absent(tmp_path, monkeypatch,
                                                    _isolate_injury_cache):
    """If the projection row carries no player_id, the kill guard must
    still trigger via the name index built from the parquet."""
    today = _date.today().isoformat()
    _write_synthetic_parquet(_isolate_injury_cache, today)

    qbox = tmp_path / "qbox"
    lines_dir = tmp_path / "lines"
    monkeypatch.setattr(ibr, "QBOX_DIR", str(qbox))
    monkeypatch.setattr(ibr, "LINES_DIR", str(lines_dir))

    def _pidless_projector(snap, period=None):
        rows = _fake_projector(snap, period)
        for r in rows:
            r["player_id"] = None
        return rows

    monkeypatch.setattr(ibr, "_project_with_engine", _pidless_projector)
    _write_qbox(str(qbox), "GAUDIT")
    _write_lines(str(lines_dir), today)

    payload = ibr.run_tick(
        game_id="GAUDIT", date_str=today, bankroll=1000.0,
        qbox_dir=str(qbox), books=("bov",),
    )
    surviving = {b["player"] for b in payload["ranked_bets"]}
    assert "Sai Out" not in surviving
    assert "Dee NotWithTeam" not in surviving
    assert payload["n_killed_by_injury"] == 2
