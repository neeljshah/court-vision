"""tests/test_nba_injury_report_scraper.py — R22_O8 scraper + daemon tests.

Covers:
  1. Status normalisation maps the full canonical taxonomy.
  2. Parsing the canned PDF fixture extracts the expected player rows.
  3. to_dataframe attaches the right player_ids + availability_factors.
  4. write_parquet_atomic round-trips the dataframe.
  5. Daemon heartbeat fires on every run_tick().
  6. Production wire (src/prediction/injury_availability) picks up the
     parquet over the legacy JSON snapshot.

All tests are offline (monkeypatched HTTP/PDF) and use tmp_path.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import nba_injury_report_scraper as scraper        # noqa: E402
from scripts import nba_injury_scraper_daemon as daemon         # noqa: E402
from scripts import fetch_injury_report as fir                  # noqa: E402


# Canned PDF text (mirrors the layout fetch_injury_report.parse_injury_text
# is designed to handle — see tests/test_fetch_injury_report.py).
_CANNED_PDF_TEXT = """\
Injury Report: 2026-05-26 05:30 PM

Game Date Game Time Matchup Team Player Name Current Status Reason
Boston Celtics Tatum, Jayson OUT Knee; Surgery
Boston Celtics Brown, Jaylen QUESTIONABLE Wrist
Minnesota Timberwolves Edwards, Anthony PROBABLE Ankle
Denver Nuggets Jokic, Nikola AVAILABLE Rest Mgmt
Los Angeles Lakers James, LeBron DOUBTFUL Foot
"""


# ---------------------------------------------------------------------------
# Test 1 — status normalisation covers the full canonical taxonomy.
# ---------------------------------------------------------------------------

def test_normalize_status_covers_canonical_taxonomy() -> None:
    for raw, expected in [
        ("Out", "OUT"),
        ("OUT", "OUT"),
        ("doubtful", "DOUBTFUL"),
        ("QUESTIONABLE", "QUESTIONABLE"),
        ("Day-To-Day", "QUESTIONABLE"),
        ("dtd", "QUESTIONABLE"),
        ("probable", "PROBABLE"),
        ("Available", "AVAILABLE"),
        ("active", "AVAILABLE"),
        ("suspended", "NOT WITH TEAM"),
        ("NWT", "NOT WITH TEAM"),
        ("not with team", "NOT WITH TEAM"),
    ]:
        assert scraper.normalize_status(raw) == expected, raw

    # Unknown / blank strings → None (skipped by to_dataframe).
    assert scraper.normalize_status("Garbage") is None
    assert scraper.normalize_status("") is None
    assert scraper.normalize_status(None) is None


# ---------------------------------------------------------------------------
# Test 2 — canned PDF text parses to per-player rows + correct statuses.
# ---------------------------------------------------------------------------

def test_pdf_fixture_parses_rows() -> None:
    rows = fir.parse_injury_text(_CANNED_PDF_TEXT)
    by_name = {r["name"]: r for r in rows}
    assert by_name["Jayson Tatum"]["status"] == "OUT"
    assert by_name["Jaylen Brown"]["status"] == "QUESTIONABLE"
    assert by_name["Anthony Edwards"]["status"] == "PROBABLE"
    assert by_name["Nikola Jokic"]["status"] == "AVAILABLE"
    assert by_name["LeBron James"]["status"] == "DOUBTFUL"


# ---------------------------------------------------------------------------
# Test 3 — to_dataframe attaches availability_factor + player_id.
# ---------------------------------------------------------------------------

def test_to_dataframe_attaches_availability_factor() -> None:
    name_index = {"jayson tatum": 1628369, "lebron james": 2544}
    rows = [
        {"player_name": "Jayson Tatum", "team": "BOS", "status": "OUT",
         "reason": "Knee", "source": "nba_pdf"},
        {"player_name": "LeBron James", "team": "LAL", "status": "PROBABLE",
         "reason": "Foot", "source": "nba_pdf"},
        # Status normalisation drops the unrecognised row.
        {"player_name": "Mystery Player", "team": "PHI", "status": "Garbage",
         "reason": "?", "source": "nba_pdf"},
        # Blank name dropped.
        {"player_name": "", "team": "BOS", "status": "OUT", "reason": "x",
         "source": "nba_pdf"},
    ]
    df = scraper.to_dataframe(rows, report_date="2026-05-26",
                              fetched_at="2026-05-26T08:00:00",
                              name_index=name_index)
    assert len(df) == 2
    tatum = df[df["player_name"] == "Jayson Tatum"].iloc[0]
    lbj   = df[df["player_name"] == "LeBron James"].iloc[0]

    assert int(tatum["player_id"]) == 1628369
    assert tatum["availability_factor"] == 0.0
    assert int(lbj["player_id"]) == 2544
    assert lbj["availability_factor"] == 0.9
    assert tatum["report_date"] == "2026-05-26"


# ---------------------------------------------------------------------------
# Test 4 — write_parquet_atomic round-trips and the file is readable.
# ---------------------------------------------------------------------------

def test_write_parquet_atomic_roundtrip(tmp_path) -> None:
    df = pd.DataFrame([
        {"player_id": 1, "player_name": "A", "team": "BOS", "status": "OUT",
         "availability_factor": 0.0, "reason": "x", "source": "nba_pdf",
         "fetched_at": "2026-05-26", "report_date": "2026-05-26"},
    ])
    out_path = str(tmp_path / "nba_injuries_2026-05-26.parquet")
    scraper.write_parquet_atomic(df, out_path)
    assert os.path.exists(out_path)
    round_trip = pd.read_parquet(out_path)
    assert len(round_trip) == 1
    assert round_trip.iloc[0]["status"] == "OUT"


# ---------------------------------------------------------------------------
# Test 5 — daemon run_tick fires the heartbeat and surfaces star alerts.
# ---------------------------------------------------------------------------

def test_daemon_run_tick_heartbeat_and_alerts(tmp_path, monkeypatch) -> None:
    """One tick on a fake scraper output should:
        * write the heartbeat file
        * emit an alert when a top-100 star flips to OUT for the first time
        * NOT re-alert on the same OUT star on the next tick.
    """
    # Route heartbeat + seen-OUT JSON to tmp.
    hb_dir = tmp_path / "heartbeats"
    monkeypatch.setattr(daemon, "_LAST_SEEN_OUT_FILE",
                        str(tmp_path / "seen_out.json"))
    from src.monitor import daemon_heartbeat
    monkeypatch.setattr(daemon_heartbeat, "_HB_DIR", str(hb_dir))
    # Route daemon's heartbeat import (cached at module load) to the test dir.
    monkeypatch.setattr(daemon, "_r19_hb",
                        lambda name: daemon_heartbeat.write_heartbeat(name, str(hb_dir)))

    # Stub the scraper so we don't hit the network.
    star_pid = 1628369
    df = pd.DataFrame([
        {"player_id": star_pid, "player_name": "Jayson Tatum", "team": "BOS",
         "status": "OUT", "availability_factor": 0.0, "reason": "Knee",
         "source": "nba_pdf", "fetched_at": "2026-05-26", "report_date": "2026-05-26"},
        {"player_id": 999, "player_name": "Bench Guy", "team": "BOS",
         "status": "QUESTIONABLE", "availability_factor": 0.6, "reason": "Foot",
         "source": "nba_pdf", "fetched_at": "2026-05-26", "report_date": "2026-05-26"},
    ])
    out_path = str(tmp_path / "nba_injuries_2026-05-26.parquet")
    df.to_parquet(out_path, index=False)
    monkeypatch.setattr(daemon.scraper, "scrape_once", lambda: (df, out_path))

    alerts_sent: list = []

    def _fake_alert(*args, **kwargs):
        alerts_sent.append({"args": args, "kwargs": kwargs})
        return {"discord_sent": False, "file_written": True,
                "vault_appended": True}

    # First tick — emit heartbeat + alert star OUT.
    daemon._r19_hb(daemon._HEARTBEAT_NAME)
    summary = daemon.run_tick(stars={star_pid}, alert_fn=_fake_alert)
    assert summary["n_rows"] == 2
    assert summary["n_out"] == 1
    assert summary["n_new_out_stars"] == 1
    assert summary["n_alerts_sent"] == 1
    assert len(alerts_sent) == 1
    assert (hb_dir / f"{daemon._HEARTBEAT_NAME}.txt").exists()

    # Second tick — same OUT, no NEW alert.
    summary2 = daemon.run_tick(stars={star_pid}, alert_fn=_fake_alert)
    assert summary2["n_new_out_stars"] == 0
    assert summary2["n_alerts_sent"] == 0
    assert len(alerts_sent) == 1


# ---------------------------------------------------------------------------
# Test 6 — production wire reads the parquet over the legacy JSON snapshot.
# ---------------------------------------------------------------------------

def test_production_wire_prefers_parquet_over_json(tmp_path, monkeypatch) -> None:
    """The R22_O8 wire must consult today's nba_injuries_<date>.parquet
    BEFORE falling back to the ESPN injury_status_<date>.json. We seed
    both, with conflicting statuses, and assert the parquet wins.
    """
    from src.prediction import injury_availability as ia

    cache_dir = tmp_path / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ia, "_CACHE_DIR", str(cache_dir))
    ia.reset_cache()

    today = date.today().isoformat()
    # Legacy JSON says PROBABLE.
    json_payload = {
        "date": today, "source": "espn_public_api",
        "fetched_at": "2026-05-26T08:00:00", "n_players": 1,
        "players": [{
            "player_name": "Jayson Tatum", "team": "BOS",
            "status": "PROBABLE", "player_id": 1628369,
            "availability_factor": 0.9,
        }],
    }
    (cache_dir / f"injury_status_{today}.json").write_text(
        json.dumps(json_payload), encoding="utf-8")

    # Parquet says OUT — should override.
    df = pd.DataFrame([{
        "player_id": 1628369, "player_name": "Jayson Tatum", "team": "BOS",
        "status": "OUT", "availability_factor": 0.0, "reason": "Knee",
        "source": "nba_pdf", "fetched_at": "2026-05-26", "report_date": today,
    }])
    df.to_parquet(cache_dir / f"nba_injuries_{today}.parquet", index=False)

    # Disable the auto-fresh-scrape guard so we don't shell out.
    monkeypatch.setattr(ia, "_trigger_fresh_scrape", lambda: True)

    factor = ia.get_availability_factor(player_id=1628369)
    assert factor == 0.0, "parquet (OUT=0.0) must beat JSON (PROBABLE=0.9)"


def test_production_wire_falls_back_to_json_when_parquet_absent(
        tmp_path, monkeypatch) -> None:
    """When no parquet exists for today, the legacy JSON snapshot still wires
    through (R15_W1 backwards compatibility).
    """
    from src.prediction import injury_availability as ia

    cache_dir = tmp_path / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ia, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(ia, "_trigger_fresh_scrape", lambda: True)
    ia.reset_cache()

    today = date.today().isoformat()
    json_payload = {
        "date": today, "source": "espn_public_api",
        "fetched_at": "2026-05-26T08:00:00", "n_players": 1,
        "players": [{
            "player_name": "LeBron James", "team": "LAL",
            "status": "QUESTIONABLE", "player_id": 2544,
            "availability_factor": 0.6,
        }],
    }
    (cache_dir / f"injury_status_{today}.json").write_text(
        json.dumps(json_payload), encoding="utf-8")

    factor = ia.get_availability_factor(player_id=2544)
    assert factor == 0.6
