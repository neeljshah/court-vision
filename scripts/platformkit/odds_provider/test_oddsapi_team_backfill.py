"""Per-file tests for oddsapi_team_backfill (pure parsers + planner; no network)."""
from __future__ import annotations

from scripts.platformkit.odds_provider import oddsapi_team_backfill as bf


def _canned_snapshot():
    """One event, 3 books (Pinnacle anchor + DK + FD). Prices are AMERICAN
    moneyline -- the exact format fetch_historical_odds returns."""
    return {
        "timestamp": "2026-01-15T23:25:00Z",
        "previous_timestamp": "2026-01-15T23:20:00Z",
        "next_timestamp": "2026-01-15T23:30:00Z",
        "data": [{
            "id": "evt1",
            "commence_time": "2026-01-16T00:10:00Z",
            "home_team": "Orlando Magic",
            "away_team": "Memphis Grizzlies",
            "bookmakers": [
                {"title": "Pinnacle", "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Orlando Magic", "price": -200},
                        {"name": "Memphis Grizzlies", "price": 179}]},
                    {"key": "spreads", "outcomes": [
                        {"name": "Orlando Magic", "price": -110, "point": -6.5},
                        {"name": "Memphis Grizzlies", "price": -105, "point": 6.5}]},
                    {"key": "totals", "outcomes": [
                        {"name": "Over", "price": -110, "point": 224.5},
                        {"name": "Under", "price": -110, "point": 224.5}]},
                ]},
                {"title": "DraftKings", "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Orlando Magic", "price": -208},
                        {"name": "Memphis Grizzlies", "price": 172}]}]},
                {"title": "FanDuel", "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Orlando Magic", "price": -205},
                        {"name": "Memphis Grizzlies", "price": 174}]}]},
            ],
        }],
    }


def test_american_converted_to_decimal():
    ev = _canned_snapshot()["data"][0]
    row = bf.parse_event(ev, "h2h")
    pin = {o["name"]: o for o in row["anchor_outcomes"]}
    # -200 -> 1.5 decimal, +179 -> 2.79 decimal; raw american preserved
    assert abs(pin["Orlando Magic"]["price"] - 1.5) < 1e-6
    assert pin["Orlando Magic"]["american"] == -200
    assert abs(pin["Memphis Grizzlies"]["price"] - 2.79) < 1e-6


def test_parse_event_h2h_anchor_devig():
    snap = _canned_snapshot()
    row = bf.parse_event(snap["data"][0], "h2h")
    assert row is not None
    assert row["n_books"] == 3
    assert len(row["anchor_outcomes"]) == 2
    dev = row["anchor_devig"]
    assert dev is not None
    # fair probs sum to 1 and home (favorite) outranks away
    assert abs(sum(dev["probs"]) - 1.0) < 1e-6
    assert dev["probs"][0] > dev["probs"][1]
    assert dev["booksum"] > 1.0                 # real overround present
    assert dev["z"] >= 0.0


def test_parse_event_spreads_and_totals():
    ev = _canned_snapshot()["data"][0]
    sp = bf.parse_event(ev, "spreads")
    assert sp is not None and sp["n_books"] == 1   # only Pinnacle priced spreads
    assert sp["anchor_outcomes"][0]["point"] == -6.5
    assert sp["anchor_devig"] is not None
    tot = bf.parse_event(ev, "totals")
    assert tot is not None
    assert {o["name"] for o in tot["anchor_outcomes"]} == {"Over", "Under"}


def test_parse_event_missing_market_returns_none():
    ev = _canned_snapshot()["data"][0]
    assert bf.parse_event(ev, "h2h_3_way") is None   # no book prices this market


def test_anchor_absent_devig_none_but_row_kept():
    ev = _canned_snapshot()["data"][0]
    # strip Pinnacle -> still have DK/FD h2h, but no anchor devig
    ev["bookmakers"] = [b for b in ev["bookmakers"] if b["title"] != "Pinnacle"]
    row = bf.parse_event(ev, "h2h")
    assert row is not None and row["n_books"] == 2
    assert row["anchor_outcomes"] == []
    assert row["anchor_devig"] is None           # never fabricated


def test_parse_snapshot_stamps_date_and_ts():
    rows = bf.parse_snapshot(_canned_snapshot(), "h2h", "2026-01-15T23:30:00Z")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-15"
    assert rows[0]["snapshot_ts"] == "2026-01-15T23:25:00Z"


def test_season_snapshots_inclusive_and_iso():
    snaps = bf.season_snapshots("nba", "2025_26")
    assert snaps[0].startswith("2025-10-21T")
    assert snaps[-1].startswith("2026-04-12T")
    # Oct 21 2025 .. Apr 12 2026 inclusive
    assert len(snaps) == 174
    assert all(s.endswith("Z") for s in snaps)


def test_season_snapshots_mlb_and_wc():
    assert bf.season_snapshots("mlb", "2026")[0].startswith("2026-03-26T22:30:00")
    wc = bf.season_snapshots("soccer_intl", "wc2026")
    assert wc[0].startswith("2026-06-11T15:30:00") and wc[-1].startswith("2026-06-26T")


def test_pregame_guard_drops_inplay():
    snap = _canned_snapshot()
    snap["timestamp"] = "2026-01-16T01:00:00Z"   # AFTER the 00:10Z commence -> in-play
    rows = bf.parse_snapshot(snap, "h2h", "2026-01-15T23:30:00Z")
    assert rows == []                             # in-play games are not a close


def test_soccer_3way_devig_sums_to_one():
    ev = {"id": "wc1", "commence_time": "2026-06-27T19:00:00Z",
          "home_team": "Brazil", "away_team": "Spain",
          "bookmakers": [{"title": "Pinnacle", "markets": [
              {"key": "h2h", "outcomes": [
                  {"name": "Brazil", "price": 140},
                  {"name": "Spain", "price": 210},
                  {"name": "Draw", "price": 230}]}]}]}
    row = bf.parse_event(ev, "h2h", snapshot_ts="2026-06-27T15:30:00Z")
    dev = row["anchor_devig"]
    assert len(dev["probs"]) == 3
    assert abs(sum(dev["probs"]) - 1.0) < 1e-6
    assert "Draw" in dev["names"]


def test_done_key_stable():
    k = bf._done_key("mlb", "2026-04-15T22:30:00Z", "h2h", "us,eu")
    assert k == "mlb|2026-04-15|h2h|us,eu"
