"""Per-file tests for an_public_splits (synthetic payloads, zero network)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.data_frontier import an_public_splits as APS


def _payload(game_id=291677, tickets=72, money=66):
    return {"games": [{
        "id": game_id, "status": "scheduled",
        "start_time": "2026-07-09T16:35:00.000Z",
        "home_team_id": 203, "away_team_id": 215,
        "teams": [{"id": 203, "abbr": "PIT"}, {"id": 215, "abbr": "ATL"}],
        "num_bets": 15040, "is_free": False,
        "markets": {"15": {"event": {
            "moneyline": [
                {"side": "away", "odds": -110, "value": 0,
                 "bet_info": {"tickets": {"percent": tickets},
                              "money": {"percent": money}}},
                {"side": "home", "odds": -110, "value": 0, "bet_info": {}},
            ],
            "core_bet_type_6_team_score": [{"side": "home", "bet_info": {}}],
        }}},
    }]}


def test_flatten_rows_and_percent_fields():
    rows = APS.flatten(_payload(), "mlb", "2026-07-09T18:00:00Z")
    assert len(rows) == 2  # non-core market skipped
    away = next(r for r in rows if r["side"] == "away")
    assert away["tickets_pct"] == 72 and away["money_pct"] == 66
    assert away["market"] == "moneyline" and away["book_id"] == "15"
    assert away["away_abbr"] == "ATL" and away["home_abbr"] == "PIT"
    home = next(r for r in rows if r["side"] == "home")
    assert home["tickets_pct"] is None and home["money_pct"] is None


def test_candidate_dates_utc_et_split():
    # 03:00Z is still the previous day in ET -> both dates fetched
    d = APS.candidate_dates(datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc))
    assert d == ["20260708", "20260709"]
    # midday: one date only
    d = APS.candidate_dates(datetime(2026, 7, 9, 18, 0, tzinfo=timezone.utc))
    assert d == ["20260709"]


class _Resp:
    status_code = 200
    text = ""
    def __init__(self, payload):
        self._p = payload
    def json(self):
        return self._p


def test_pull_writes_dated_jsonl_and_status(tmp_path, monkeypatch):
    monkeypatch.setattr(APS, "STATUS_FP", tmp_path / "status.json")
    monkeypatch.setattr(APS, "_LOG_FP", tmp_path / "pull.log")
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params["date"]))
        assert timeout == 35.0
        return _Resp(_payload())

    now = datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)  # ET day = 07-08
    status = APS.pull(leagues=["mlb"], fetcher=fake_get,
                      out_dir=tmp_path / "public_splits", now=now)
    assert [d for _, d in calls] == ["20260708", "20260709"]  # both dates probed
    assert status["verdict"] == "POPULATED"
    ml = status["per_league"]["mlb"]
    assert ml["games"] == 1 and ml["rows_appended"] == 2  # deduped across dates
    fp = tmp_path / "public_splits" / "mlb" / "2026-07-08.jsonl"
    lines = fp.read_text(encoding="ascii").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["league"] == "mlb"
    # second pull appends (snapshot store, line_history convention)
    APS.pull(leagues=["mlb"], fetcher=fake_get,
             out_dir=tmp_path / "public_splits", now=now)
    assert len(fp.read_text(encoding="ascii").splitlines()) == 4


def test_pull_non200_recorded_not_worked_around(tmp_path, monkeypatch):
    monkeypatch.setattr(APS, "STATUS_FP", tmp_path / "status.json")
    monkeypatch.setattr(APS, "_LOG_FP", tmp_path / "pull.log")

    class _Gone:
        status_code = 403
        text = "blocked by upstream"
        def json(self):  # pragma: no cover
            return {}

    status = APS.pull(leagues=["mlb"], fetcher=lambda *a, **k: _Gone(),
                      out_dir=tmp_path / "public_splits",
                      now=datetime(2026, 7, 9, 18, 0, tzinfo=timezone.utc))
    assert status["verdict"] == "EMPTY_OR_BLOCKED"
    errs = status["per_league"]["mlb"]["errors"]
    assert errs and "HTTP 403" in errs[0]
    assert not (tmp_path / "public_splits" / "mlb").exists()  # nothing fabricated
