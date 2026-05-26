"""tests/test_nba_lineup_daemon.py — R17 J1.

Coverage:
  1. normalize_games -> canonical schema (slot, status, captured_at)
  2. diff_snapshots STARTER_SWAP detection
  3. diff_snapshots LATE_SCRATCH detection
  4. find_killed_bets flags slate player not in starters
  5. mark_killed_in_ledger updates pending bets, leaves settled bets alone
  6. append_alert_md writes URGENT lines
  7. run_once end-to-end with injected fetcher (no network)
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date as _date

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import nba_lineup_daemon as d  # noqa: E402


# ── fixtures ──────────────────────────────────────────────────────────────────
def _make_games(home_pf: str = "Julian Champagnie"):
    return [{
        "away_team": "SAS", "home_team": "OKC",
        "away_lineup": {
            "status": "Expected",
            "starters": [
                {"pos": "PG", "name": "De'Aaron Fox",      "play_pct": 100, "injury": None},
                {"pos": "SG", "name": "Stephon Castle",     "play_pct": 100, "injury": None},
                {"pos": "SF", "name": "Devin Vassell",      "play_pct": 100, "injury": None},
                {"pos": "PF", "name": home_pf,              "play_pct": 100, "injury": None},
                {"pos": "C",  "name": "Victor Wembanyama",  "play_pct": 100, "injury": None},
            ],
        },
        "home_lineup": {
            "status": "Expected",
            "starters": [
                {"pos": "PG", "name": "Shai Gilgeous-Alexander", "play_pct": 100, "injury": None},
                {"pos": "SG", "name": "Luguentz Dort",           "play_pct": 100, "injury": None},
                {"pos": "SF", "name": "Jalen Williams",          "play_pct": 100, "injury": None},
                {"pos": "PF", "name": "Chet Holmgren",           "play_pct": 100, "injury": None},
                {"pos": "C",  "name": "Isaiah Hartenstein",      "play_pct": 100, "injury": None},
            ],
        },
    }]


# ── 1. schema ─────────────────────────────────────────────────────────────────
def test_normalize_games_canonical_schema():
    rows = d.normalize_games(_make_games())
    assert len(rows) == 10
    required = {"game_id", "team", "player_id", "player_name",
                "position", "slot", "status", "captured_at"}
    for r in rows:
        assert required.issubset(r.keys())
        assert r["slot"] in d._SLOT_ORDER
        assert r["status"] in {"CONFIRMED", "PROJECTED", "QUESTIONABLE", "OUT"}
    sas_rows = [r for r in rows if r["team"] == "SAS"]
    okc_rows = [r for r in rows if r["team"] == "OKC"]
    assert len(sas_rows) == 5 and len(okc_rows) == 5
    assert any(r["player_name"] == "Victor Wembanyama" for r in sas_rows)


def test_normalize_games_injury_overrides_status():
    games = _make_games()
    games[0]["home_lineup"]["starters"][2]["injury"] = "Ques"
    games[0]["home_lineup"]["starters"][2]["play_pct"] = 50
    rows = d.normalize_games(games)
    jw = next(r for r in rows if r["player_name"] == "Jalen Williams")
    assert jw["status"] == "QUESTIONABLE"


# ── 2 + 3. diff detection ─────────────────────────────────────────────────────
def test_diff_detects_starter_swap():
    prior = d.normalize_games(_make_games(home_pf="Julian Champagnie"))
    new = d.normalize_games(_make_games(home_pf="Keldon Johnson"))
    events = d.diff_snapshots(prior, new)
    swaps = [e for e in events if e["event"] == "STARTER_SWAP"]
    assert any(e["out_player"] == "Julian Champagnie"
               and e["in_player"] == "Keldon Johnson" for e in swaps)


def test_diff_detects_late_scratch_and_new_starter():
    prior = d.normalize_games(_make_games(home_pf="Julian Champagnie"))
    new = d.normalize_games(_make_games(home_pf="Keldon Johnson"))
    events = d.diff_snapshots(prior, new)
    scratched = {e["player_name"] for e in events if e["event"] == "LATE_SCRATCH"}
    new_starters = {e["player_name"] for e in events if e["event"] == "NEW_STARTER"}
    assert "Julian Champagnie" in scratched
    assert "Keldon Johnson" in new_starters


# ── 4. find_killed_bets ───────────────────────────────────────────────────────
def test_find_killed_bets_flags_absent_slate_player():
    rows = d.normalize_games(_make_games(home_pf="Julian Champagnie"))
    # Keldon is on the slate but NOT in the SAS starting five
    slate = {"Keldon Johnson", "Victor Wembanyama", "Shai Gilgeous-Alexander"}
    killed = d.find_killed_bets(rows, slate)
    killed_names = {k["player"] for k in killed}
    assert "Keldon Johnson" in killed_names
    # SGA and Wemby ARE starting — must not be flagged
    assert "Shai Gilgeous-Alexander" not in killed_names
    assert "Victor Wembanyama" not in killed_names


def test_find_killed_bets_flags_out_status():
    rows = d.normalize_games(_make_games(home_pf="Keldon Johnson"))
    # mark Keldon as OUT
    for r in rows:
        if r["player_name"] == "Keldon Johnson":
            r["status"] = "OUT"
    killed = d.find_killed_bets(rows, {"Keldon Johnson"})
    assert killed and killed[0]["reason"] == "status_out"


# ── 5. ledger update ──────────────────────────────────────────────────────────
def test_mark_killed_in_ledger(tmp_path):
    ledger = tmp_path / "pnl_ledger.csv"
    rows = [
        # pending bet on Keldon -> must flip to line_killed
        {"bet_id": "b1", "player": "Keldon Johnson", "status": "pending",
         "stat": "reb", "side": "OVER"},
        # settled bet on Keldon -> must NOT change
        {"bet_id": "b2", "player": "Keldon Johnson", "status": "won",
         "stat": "pts", "side": "OVER"},
        # different player pending -> must NOT change
        {"bet_id": "b3", "player": "SGA", "status": "pending",
         "stat": "ast", "side": "OVER"},
    ]
    with open(ledger, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    updated = d.mark_killed_in_ledger(
        [{"player": "Keldon Johnson", "reason": "not_starting"}],
        path=str(ledger),
    )
    assert updated == 1

    with open(ledger, encoding="utf-8") as fh:
        out = list(csv.DictReader(fh))
    by_id = {r["bet_id"]: r for r in out}
    assert by_id["b1"]["status"] == "line_killed"   # pending Keldon -> killed
    assert by_id["b2"]["status"] == "won"           # settled -> untouched
    assert by_id["b3"]["status"] == "pending"       # other player -> untouched


# ── 6. alert markdown ─────────────────────────────────────────────────────────
def test_append_alert_md_writes_urgent_line(tmp_path):
    path = tmp_path / "alerts.md"
    n = d.append_alert_md(
        [{"player": "Keldon Johnson", "reason": "not_starting"}],
        path=str(path),
    )
    assert n == 1
    txt = path.read_text(encoding="utf-8")
    assert "URGENT" in txt and "Keldon Johnson" in txt


# ── 7. end-to-end run_once with injected fetcher ──────────────────────────────
def test_run_once_end_to_end(tmp_path):
    # craft a tiny rotowire-style HTML by reusing the real parser path:
    # the simplest end-to-end is to bypass HTML by monkey-patching the parser.
    games = _make_games(home_pf="Julian Champagnie")

    snap_dir = tmp_path / "lineups"
    ledger = tmp_path / "ledger.csv"
    alerts = tmp_path / "alerts.md"
    slate = tmp_path / "slate.json"

    # ledger with one pending Keldon bet
    with open(ledger, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["bet_id", "player", "status"])
        w.writeheader()
        w.writerow({"bet_id": "b1", "player": "Keldon Johnson", "status": "pending"})

    slate.write_text(json.dumps({"ranked_bets": [
        {"player": "Keldon Johnson"},
        {"player": "Victor Wembanyama"},
    ]}), encoding="utf-8")

    # monkey-patch the parser so fetcher's return value is irrelevant
    import scripts.nba_lineup_daemon as mod
    orig_parse = mod._rw_parse_html
    mod._rw_parse_html = lambda body: games
    try:
        result = d.run_once(
            fetcher=lambda: "<html/>",
            slate_path=str(slate),
            ledger_path=str(ledger),
            alerts_path=str(alerts),
            snapshot_dir=str(snap_dir),
        )
    finally:
        mod._rw_parse_html = orig_parse

    assert result["n_starters"] == 10
    killed_names = {k["player"] for k in result["killed"]}
    assert "Keldon Johnson" in killed_names
    assert result["alerts_written"] >= 1
    assert result["ledger_updates"] == 1
    # snapshot file exists
    snap_file = snap_dir / f"{_date.today().isoformat()}.json"
    assert snap_file.exists()
    payload = json.loads(snap_file.read_text(encoding="utf-8"))
    assert payload["n_starters"] == 10
    assert "starters" in payload


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
