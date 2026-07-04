"""Per-file tests for npb_kbo_live_state.py -- fixture-based, no network.

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_npb_kbo_live_state.py -q
"""
from __future__ import annotations

import datetime as _dt

import scripts.platformkit.ingame.npb_kbo_live_state as S

# ---- NPB fixtures (real npb.jp schedule-detail row shapes, verified live 2026-07-04) ----

_NPB_SCHEDULED_ROW = (
    '<tr id="date0704"><th class="saturday" rowspan="6">7/4</th>'
    '<td><div class="team1">ヤクルト</div>'
    '<div class="score1">&nbsp;</div><div class="state">-</div>'
    '<div class="score2">&nbsp;</div><div class="team2">DeNA</div></td></tr>'
)

_NPB_FINAL_ROW = (
    '<tr id="date0703"><th rowspan="1">7/3</th>'
    '<td><div class="team1">巨人</div>'
    '<div class="score1">4</div><div class="state">-</div>'
    '<div class="score2">4</div><div class="team2">中日</div></td></tr>'
)

_NPB_OFFDAY_ROW = '<tr id="date0702"><th rowspan="1">7/2</th><td>&nbsp;</td></tr>'


def test_npb_today_rows_scheduled_game_scores_none():
    rows = S._npb_today_rows(_NPB_SCHEDULED_ROW, 2026, 7, 4)
    assert len(rows) == 1
    r = rows[0]
    assert r["home"] == "ヤクルト" and r["away"] == "DeNA"
    assert r["home_score"] is None and r["away_score"] is None


def test_npb_today_rows_final_game_scores_numeric():
    rows = S._npb_today_rows(_NPB_FINAL_ROW, 2026, 7, 3)
    assert len(rows) == 1
    assert rows[0]["home_score"] == 4.0 and rows[0]["away_score"] == 4.0


def test_npb_today_rows_offday_row_skipped():
    rows = S._npb_today_rows(_NPB_OFFDAY_ROW, 2026, 7, 2)
    assert rows == []


def test_npb_today_rows_wrong_date_returns_empty():
    rows = S._npb_today_rows(_NPB_SCHEDULED_ROW, 2026, 7, 5)
    assert rows == []


def test_npb_states_scheduled_game_status_scheduled():
    states = S._npb_states(_dt.date(2026, 7, 4),
                           lambda url: _NPB_SCHEDULED_ROW)
    assert len(states) == 1
    st = states[0]
    assert st["sport"] == "npb"
    assert st["status"] == "scheduled"
    assert st["home_score"] is None
    assert st["inning"] is None and st["frac_elapsed"] is None
    # English alias resolves for a mapped team; native name passes through otherwise
    assert st["away_display"] == "Yokohama DeNA BayStars"


def test_npb_states_final_game_status_final_and_diff():
    states = S._npb_states(_dt.date(2026, 7, 3), lambda url: _NPB_FINAL_ROW)
    assert len(states) == 1
    st = states[0]
    assert st["status"] == "final"
    assert st["state_diff"] == 0.0


def test_npb_states_http_error_returns_empty_list():
    def _boom(url):
        raise RuntimeError("network down")
    assert S._npb_states(_dt.date(2026, 7, 4), _boom) == []


def test_npb_states_defaults_to_today_when_date_none():
    seen = {}

    def _getter(url):
        seen["url"] = url
        return ""
    S._npb_states(None, _getter)
    assert "npb.jp/games/" in seen["url"]


# ---- KBO fixtures (real GetScheduleList JSON row-group shape, verified live 2026-07-04) --

def _kbo_body(rows):
    import json
    return json.dumps({"rows": rows})


_KBO_ROWS_TODAY_INPROGRESS = [
    {"row": [{"Class": "day", "Text": "07.04(토)"},
             {"Class": "play", "Text": '<span>NC</span><em><span class="same">0</span>'
                                        '<span>vs</span><span class="same">0</span></em>'
                                        '<span>KIA</span>'}]},
]

_KBO_ROWS_YESTERDAY_FINAL = [
    {"row": [{"Class": "day", "Text": "07.03(금)"},
             {"Class": "play", "Text": '<span>LG</span><em><span class="lose">1</span>'
                                        '<span>vs</span><span class="win">8</span></em>'
                                        '<span>KT</span>'}]},
]

_KBO_ROWS_MULTI_DAY_ROWSPAN = [
    {"row": [{"Class": "day", "Text": "07.03(금)"},
             {"Class": "play", "Text": '<span>LG</span><em><span class="lose">1</span>'
                                        '<span>vs</span><span class="win">8</span></em>'
                                        '<span>KT</span>'}]},
    {"row": [{"Class": "play", "Text": '<span>NC</span><em><span class="win">6</span>'
                                        '<span>vs</span><span class="lose">2</span></em>'
                                        '<span>SSG</span>'}]},
]

_KBO_ROWS_POSTPONED = [
    {"row": [{"Class": "day", "Text": "07.03(금)"},
             {"Class": "play", "Text": '<span>LG</span><em><span>vs</span></em><span>KT</span>'}]},
]


def test_kbo_today_rows_inprogress_placeholder_parses():
    rows = S._kbo_today_rows(_kbo_body(_KBO_ROWS_TODAY_INPROGRESS), 7, 4)
    assert len(rows) == 1
    assert rows[0]["tied_marker"] is True
    assert rows[0]["home_score"] == 0.0 and rows[0]["away_score"] == 0.0


def test_kbo_today_rows_final_game_scores_numeric():
    rows = S._kbo_today_rows(_kbo_body(_KBO_ROWS_YESTERDAY_FINAL), 7, 3)
    assert len(rows) == 1
    assert rows[0]["home_score"] == 8.0 and rows[0]["away_score"] == 1.0
    assert rows[0]["tied_marker"] is False


def test_kbo_today_rows_rowspan_carries_day_forward():
    rows = S._kbo_today_rows(_kbo_body(_KBO_ROWS_MULTI_DAY_ROWSPAN), 7, 3)
    assert len(rows) == 2


def test_kbo_today_rows_postponed_game_skipped():
    rows = S._kbo_today_rows(_kbo_body(_KBO_ROWS_POSTPONED), 7, 3)
    assert rows == []


def test_kbo_today_rows_not_json_returns_empty():
    assert S._kbo_today_rows("<html>error</html>", 7, 3) == []


def test_kbo_states_inprogress_status_and_none_scores():
    states = S._kbo_states(_dt.date(2026, 7, 4),
                           lambda url, body: _kbo_body(_KBO_ROWS_TODAY_INPROGRESS))
    assert len(states) == 1
    st = states[0]
    assert st["sport"] == "kbo"
    assert st["status"] == "in_progress_or_scheduled"
    assert st["home_score"] is None and st["state_diff"] is None
    assert st["inning"] is None and st["frac_elapsed"] is None


def test_kbo_states_final_game_status_final():
    states = S._kbo_states(_dt.date(2026, 7, 3),
                           lambda url, body: _kbo_body(_KBO_ROWS_YESTERDAY_FINAL))
    assert len(states) == 1
    st = states[0]
    assert st["status"] == "final"
    assert st["state_diff"] == 7.0


def test_kbo_states_http_error_returns_empty_list():
    def _boom(url, body):
        raise RuntimeError("network down")
    assert S._kbo_states(_dt.date(2026, 7, 4), _boom) == []


# ---- dispatch (live_states) ---------------------------------------------------------

def test_live_states_dispatches_npb():
    states = S.live_states("npb", date=_dt.date(2026, 7, 4),
                           http_get=lambda url: _NPB_SCHEDULED_ROW)
    assert len(states) == 1 and states[0]["sport"] == "npb"


def test_live_states_dispatches_kbo():
    states = S.live_states("kbo", date=_dt.date(2026, 7, 4),
                           http_get=lambda url, body: _kbo_body(_KBO_ROWS_TODAY_INPROGRESS))
    assert len(states) == 1 and states[0]["sport"] == "kbo"


def test_live_states_unknown_sport_returns_empty():
    assert S.live_states("mlb") == []


def test_live_states_never_raises_on_dispatch_error():
    def _boom(url, **kw):
        raise RuntimeError("boom")
    assert S.live_states("npb", http_get=_boom) == []
