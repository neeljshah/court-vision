"""Per-file tests for ingest_npb (offline; injected http_get, inline fixture HTML).

Team names in fixtures are romanized (Nipponham, Yakult, Kyojin, Hanshin,
Chunichi, Rakuten, Softbank, Seibu, Hiroshima, DeNA) rather than the real
kanji/katakana npb.jp serves live -- ASCII-only per repo convention. The
parser (_parse_month) only reads team1/team2 div TEXT verbatim (never
interprets it), so this substitution changes nothing about what is being
tested; see ingest_npb.py's module docstring for the real (non-ASCII) team
names actually observed live 2026-07-03.

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_ingest_npb.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.baseball_npb import ingest_npb as inpb


def _row_html(md: str, team1: str, team2: str, s1=None, s2=None, cancel=None) -> str:
    """One <tr id="dateMMDD"> block, matching npb.jp's real markup shape
    (verified live 2026-07-03)."""
    if cancel is not None:
        body = (
            f'<td><div class="team1">{team1}</div>'
            f'<a href="/scores/x/"><div class="cancel">{cancel}</div></a>'
            f'<div class="team2">{team2}</div></td>'
        )
    elif s1 is None:
        body = '<td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>'
    else:
        body = (
            f'<td><div class="team1">{team1}</div>'
            f'<a href="/scores/x/"><div class="score1">{s1}</div>'
            f'<div class="state">-</div><div class="score2">{s2}</div></a>'
            f'<div class="team2">{team2}</div></td>'
        )
    return f'<tr id="date{md}" class="">{body}</tr>'


def test_parse_month_extracts_completed_games_and_labels_home_win():
    body = (
        _row_html("0601", "Nipponham", "Yakult", 0, 5)
        + _row_html("0602", "Kyojin", "Hanshin", 4, 2)
    )
    rows = inpb._parse_month(body, "2023", 6)
    assert len(rows) == 2
    assert rows[0]["home_team"] == "Nipponham"
    assert rows[0]["away_team"] == "Yakult"
    assert rows[0]["home_score"] == 0.0 and rows[0]["away_score"] == 5.0
    assert rows[0]["home_win"] == 0.0
    assert rows[0]["tied"] is False
    assert rows[1]["home_win"] == 1.0


def test_parse_month_tie_excluded_from_home_win_but_flagged():
    body = _row_html("0908", "DeNA", "Chunichi", 3, 3)
    rows = inpb._parse_month(body, "2023", 9)
    assert len(rows) == 1
    assert rows[0]["tied"] is True
    assert rows[0]["home_win"] is None


def test_parse_month_skips_off_day_placeholder():
    body = _row_html("0904", "", "")
    rows = inpb._parse_month(body, "2023", 9)
    assert rows == []


def test_parse_month_skips_postponed_and_no_game():
    body = (
        _row_html("0905", "Rakuten", "Nipponham", cancel="chuushi")
        + _row_html("0922", "DeNA", "Chunichi", cancel="nogame")
    )
    rows = inpb._parse_month(body, "2023", 9)
    assert rows == []  # postponed ("chuushi") and no-game both excluded


def test_parse_month_empty_body_returns_empty():
    assert inpb._parse_month("", "2023", 12) == []


def test_fetch_month_uses_injected_http_get():
    body = _row_html("0401", "Hanshin", "Hiroshima", 6, 1)
    calls = []

    def http_get(url):
        calls.append(url)
        return body

    rows = inpb.fetch_month("2024", 4, http_get=http_get)
    assert len(rows) == 1
    assert len(calls) == 1
    assert "schedule_04_detail.html" in calls[0]
    assert "2024" in calls[0]


def test_looks_bot_walled_true_only_when_marker_missing_and_body_nonempty():
    assert inpb._looks_bot_walled("") is False  # empty is a clean 404, not a wall
    assert inpb._looks_bot_walled("<html>schedule_detail stuff</html>") is False
    assert inpb._looks_bot_walled("<html>captcha challenge page</html>") is True


def test_ingest_season_writes_and_dedups(tmp_path):
    out = tmp_path / "npb_results.parquet"
    month_body = _row_html("0601", "Softbank", "Seibu", 2, 1)

    def http_get(url):
        return month_body if "schedule_06" in url else ""

    inpb.ingest_season("2023", http_get=http_get, out_path=out, months=(6,), sleep_seconds=0.0)
    df1 = pd.read_parquet(out)
    assert len(df1) == 1 and df1.iloc[0]["home_score"] == 2.0

    # re-ingest with an UPDATED score for the same (date, home, away) key
    updated_body = _row_html("0601", "Softbank", "Seibu", 5, 1)

    def http_get2(url):
        return updated_body if "schedule_06" in url else ""

    inpb.ingest_season("2023", http_get=http_get2, out_path=out, months=(6,), sleep_seconds=0.0)
    df2 = pd.read_parquet(out)
    assert len(df2) == 1 and df2.iloc[0]["home_score"] == 5.0


def test_ingest_season_empty_months_is_a_noop(tmp_path):
    out = tmp_path / "empty.parquet"
    inpb.ingest_season("1999", http_get=lambda url: "", out_path=out, months=(3,), sleep_seconds=0.0)
    assert not out.exists()


def test_ingest_seasons_multiple_years_accumulate(tmp_path):
    out = tmp_path / "multi.parquet"

    def http_get_factory(year, home, away, hs, as_):
        body = _row_html("0405", home, away, hs, as_)

        def http_get(url):
            return body if "schedule_04" in url and year in url else ""
        return http_get

    inpb.ingest_season("2022", http_get=http_get_factory("2022", "Hiroshima", "Chunichi", 3, 2),
                        out_path=out, months=(4,), sleep_seconds=0.0)
    inpb.ingest_season("2023", http_get=http_get_factory("2023", "Kyojin", "Hanshin", 4, 1),
                        out_path=out, months=(4,), sleep_seconds=0.0)
    df = pd.read_parquet(out)
    assert len(df) == 2
    assert set(df["season"].tolist()) == {"2022", "2023"}
