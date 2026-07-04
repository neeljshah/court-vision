"""Per-file tests for ingest_kbo (offline; injected http_get, inline fixture JSON).

Team tokens in fixtures use the SAME site tokens observed live 2026-07-04
(Latin codes KIA/KT/LG/NC/SSG; Korean glyphs for the other five clubs) --
these are DATA in the fixture, matching real site markup, not a
romanization; the parser only reads text verbatim.

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_ingest_kbo.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.baseball_kbo import ingest_kbo as ikbo


def _day_cell(text: str, rowspan=None) -> dict:
    return {"Text": text, "Class": "day", "Scope": None, "RowSpan": rowspan,
            "ColSpan": None, "Width": None, "TypeObj": None}


def _play_cell_scored(away: str, home: str, away_score: int, home_score: int,
                       away_cls="lose", home_cls="win") -> dict:
    text = (f'<span>{away}</span><em><span class="{away_cls}">{away_score}</span>'
            f'<span>vs</span><span class="{home_cls}">{home_score}</span></em>'
            f'<span>{home}</span>')
    return {"Text": text, "Class": "play", "Scope": None, "RowSpan": None,
            "ColSpan": None, "Width": None, "TypeObj": None}


def _play_cell_unplayed(away: str, home: str) -> dict:
    text = f'<span>{away}</span><em><span>vs</span></em><span>{home}</span>'
    return {"Text": text, "Class": "play", "Scope": None, "RowSpan": None,
            "ColSpan": None, "Width": None, "TypeObj": None}


def _row_group(*cells) -> dict:
    return {"row": list(cells), "Class": None, "OnClick": None, "Style": None,
            "Value": None, "Id": None}


def _body(rows) -> str:
    return json.dumps({"colgroup": [], "headers": [], "rows": rows})


def test_parse_schedule_extracts_completed_game_and_labels_home_win():
    body = _body([
        _row_group(_day_cell("05.01(THU)", rowspan="1"),
                   _play_cell_scored("KT", "DOOSAN", 3, 4)),
    ])
    rows = ikbo._parse_schedule(body, "2025")
    assert len(rows) == 1
    assert rows[0]["away_team"] == "KT"
    assert rows[0]["home_team"] == "DOOSAN"
    assert rows[0]["away_score"] == 3.0 and rows[0]["home_score"] == 4.0
    assert rows[0]["home_win"] == 1.0
    assert rows[0]["tied"] is False
    assert rows[0]["date"] == "2025-05-01"


def test_parse_schedule_rowspan_merged_day_block_carries_date_forward():
    """A multi-game day: the "day" cell appears ONCE (first row-group of the
    day); subsequent row-groups for the same day omit it entirely. The date
    must carry forward, not reset/guess."""
    body = _body([
        _row_group(_day_cell("05.01(THU)", rowspan="3"),
                   _play_cell_scored("KT", "DOOSAN", 3, 4)),
        _row_group(_play_cell_scored("SAMSUNG", "SSG", 1, 4, away_cls="lose", home_cls="win")),
        _row_group(_play_cell_scored("KIA", "LG", 2, 2, away_cls="same", home_cls="same")),
    ])
    rows = ikbo._parse_schedule(body, "2025")
    assert len(rows) == 3
    assert all(r["date"] == "2025-05-01" for r in rows)
    assert rows[0]["home_team"] == "DOOSAN"
    assert rows[1]["home_team"] == "SSG"
    assert rows[2]["home_team"] == "LG"


def test_parse_schedule_tie_excluded_from_home_win_but_flagged():
    body = _body([
        _row_group(_day_cell("09.08(MON)", rowspan="1"),
                   _play_cell_scored("KIA", "LG", 3, 3, away_cls="same", home_cls="same")),
    ])
    rows = ikbo._parse_schedule(body, "2025")
    assert len(rows) == 1
    assert rows[0]["tied"] is True
    assert rows[0]["home_win"] is None


def test_parse_schedule_skips_inprogress_zero_zero_placeholder():
    """A 0-0/same/same cell is an in-progress-not-final placeholder (found
    live 2026-07-04), NOT a real completed tie -- must be skipped, never
    recorded as home_win=None/tied=True."""
    body = _body([
        _row_group(_day_cell("07.04(SAT)", rowspan="1"),
                   _play_cell_scored("LG", "SSG", 0, 0, away_cls="same", home_cls="same")),
    ])
    rows = ikbo._parse_schedule(body, "2026")
    assert rows == []


def test_parse_schedule_skips_postponed_unplayed_game():
    body = _body([
        _row_group(_day_cell("09.05(FRI)", rowspan="1"),
                   _play_cell_unplayed("KT", "SSG")),
    ])
    rows = ikbo._parse_schedule(body, "2025")
    assert rows == []


def test_parse_schedule_normalizes_korean_glyph_teams():
    body = _body([
        _row_group(_day_cell("04.05(SAT)", rowspan="1"),
                   _play_cell_scored("거울", "두산", 2, 5)),
    ])
    # (the away token here is a deliberately-unmapped glyph to exercise
    # passthrough; the home token "두산" = Doosan's real site glyph)
    rows = ikbo._parse_schedule(body, "2025")
    assert len(rows) == 1
    assert rows[0]["home_team"] == "DOOSAN"


def test_parse_schedule_non_json_body_returns_empty():
    """The load-bearing 200-with-HTML-error-page trap: a missing Referer
    yields a 200 whose body is NOT valid JSON -- must degrade to zero rows,
    never crash."""
    assert ikbo._parse_schedule("<html>error page, not JSON</html>", "2025") == []


def test_parse_schedule_empty_body_returns_empty():
    assert ikbo._parse_schedule("", "2025") == []


def test_is_json_body():
    assert ikbo._is_json_body('{"rows": []}') is True
    assert ikbo._is_json_body("<html>nope</html>") is False
    assert ikbo._is_json_body("") is False


def test_build_body_includes_required_team_id_param():
    """teamId= is REQUIRED (empty string) -- omitting it 500s on the real
    endpoint (verified live 2026-07-04); the body must always include it."""
    body = ikbo._build_body("2025", "05")
    assert "teamId=" in body
    assert "leId=1" in body
    assert "seasonId=2025" in body
    assert "gameMonth=05" in body


def test_fetch_season_whole_uses_injected_http_get_with_empty_game_month():
    calls = []

    def http_get(url, body):
        calls.append((url, body))
        return _body([
            _row_group(_day_cell("03.22(SAT)", rowspan="1"),
                       _play_cell_scored("KIA", "LG", 1, 6)),
        ])

    rows = ikbo.fetch_season_whole("2025", http_get=http_get)
    assert len(rows) == 1
    assert len(calls) == 1
    url, body = calls[0]
    assert url == ikbo._URL
    assert "gameMonth=" in body
    assert "gameMonth=05" not in body  # empty gameMonth, not a specific month


def test_fetch_month_uses_injected_http_get():
    calls = []

    def http_get(url, body):
        calls.append(body)
        return _body([
            _row_group(_day_cell("04.01(TUE)", rowspan="1"),
                       _play_cell_scored("SSG", "KT", 2, 3)),
        ])

    rows = ikbo.fetch_month("2024", 4, http_get=http_get)
    assert len(rows) == 1
    assert "gameMonth=04" in calls[0]
    assert "seasonId=2024" in calls[0]


def test_ingest_season_writes_and_dedups_via_whole_season_path(tmp_path):
    out = tmp_path / "kbo_results.parquet"
    body = _body([
        _row_group(_day_cell("06.01(SUN)", rowspan="1"),
                   _play_cell_scored("SAMSUNG", "KIWOOM", 2, 1)),
    ])

    def http_get(url, req_body):
        return body

    ikbo.ingest_season("2023", http_get=http_get, out_path=out, sleep_seconds=0.0)
    df1 = pd.read_parquet(out)
    assert len(df1) == 1 and df1.iloc[0]["home_score"] == 1.0

    # re-ingest with an UPDATED score for the same (date, home, away) key
    updated_body = _body([
        _row_group(_day_cell("06.01(SUN)", rowspan="1"),
                   _play_cell_scored("SAMSUNG", "KIWOOM", 2, 5)),
    ])

    def http_get2(url, req_body):
        return updated_body

    ikbo.ingest_season("2023", http_get=http_get2, out_path=out, sleep_seconds=0.0)
    df2 = pd.read_parquet(out)
    assert len(df2) == 1 and df2.iloc[0]["home_score"] == 5.0


def test_ingest_season_falls_back_to_per_month_when_whole_season_empty(tmp_path):
    out = tmp_path / "kbo_fallback.parquet"

    def http_get(url, req_body):
        if "gameMonth=&" in req_body or req_body.endswith("gameMonth="):
            return ""  # whole-season path fails
        if "gameMonth=04" in req_body:
            return _body([
                _row_group(_day_cell("04.10(THU)", rowspan="1"),
                           _play_cell_scored("HANWHA", "NC", 1, 2)),
            ])
        return _body([])

    ikbo.ingest_season("2022", http_get=http_get, out_path=out,
                        months=(4,), sleep_seconds=0.0, whole_season_first=True)
    df = pd.read_parquet(out)
    assert len(df) == 1
    assert df.iloc[0]["home_team"] == "NC"


def test_ingest_seasons_multiple_seasons_accumulate(tmp_path):
    out = tmp_path / "multi.parquet"

    def http_get_factory(season, home, away, hs, as_):
        body = _body([
            _row_group(_day_cell("04.05(SAT)", rowspan="1"),
                       _play_cell_scored(away, home, as_, hs)),
        ])

        def http_get(url, req_body):
            return body if f"seasonId={season}" in req_body else _body([])
        return http_get

    ikbo.ingest_season("2022", http_get=http_get_factory("2022", "LG", "KT", 3, 2),
                        out_path=out, sleep_seconds=0.0)
    ikbo.ingest_season("2023", http_get=http_get_factory("2023", "SSG", "NC", 4, 1),
                        out_path=out, sleep_seconds=0.0)
    df = pd.read_parquet(out)
    assert len(df) == 2
    assert set(df["season"].tolist()) == {"2022", "2023"}
