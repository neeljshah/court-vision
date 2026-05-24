"""Tests for scripts/fetch_lineups.py — rotowire projected lineups (cycle 61).

The HTML structure is real — captured from a live rotowire fetch on 2026-05-24
and abbreviated for test fixture clarity. The regexes target the specific
rotowire conventions (lineup__list / lineup__player / is-pct-play-N /
lineup__inj / MAY NOT PLAY divider) so these tests would break if rotowire
restructures the page — exactly the failure mode worth catching.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.fetch_lineups as fl  # noqa: E402


# ── fixtures ─────────────────────────────────────────────────────────────────

_OKC_VISIT_UL = '''<ul class="lineup__list is-visit">
    <li class="lineup__status is-expected">
        <div class="dot is-medium is-yellow" style="margin-right:5px;"></div>Expected Lineup
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">PG</div>
        <a title="Shai Gilgeous-Alexander" href="/x">S. Gilgeous-Alexander</a>
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">SG</div>
        <a title="Luguentz Dort" href="/x">Luguentz Dort</a>
    </li>
    <li class="lineup__player is-pct-play-50 has-injury-status" title="Toss Up">
        <div class="lineup__pos">SF</div>
        <a title="Jalen Williams" href="/x">J. Williams</a>
        <span class="lineup__inj">Ques</span>
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">PF</div>
        <a title="Chet Holmgren" href="/x">Chet Holmgren</a>
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">C</div>
        <a title="Isaiah Hartenstein" href="/x">I. Hartenstein</a>
    </li>
    <li><button data-team="OKC" data-nickname="Thunder" data-home="0">Projected Minutes</button></li>
    <li class="lineup__title is-middle">MAY NOT PLAY</li>
    <li class="lineup__player is-pct-play-0" title="Out">
        <div class="lineup__pos">G</div>
        <a title="Ajay Mitchell" href="/x">Ajay Mitchell</a>
        <span class="lineup__inj">Out</span>
    </li>
</ul>'''

_SAS_HOME_UL = '''<ul class="lineup__list is-home">
    <li class="lineup__status is-expected">
        <div class="dot is-medium is-yellow"></div>Expected Lineup
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">PG</div>
        <a title="De'Aaron Fox" href="/x">D. Fox</a>
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">SG</div>
        <a title="Stephon Castle" href="/x">S. Castle</a>
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">SF</div>
        <a title="Devin Vassell" href="/x">D. Vassell</a>
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">PF</div>
        <a title="Julian Champagnie" href="/x">J. Champagnie</a>
    </li>
    <li class="lineup__player is-pct-play-100" title="Very Likely To Play">
        <div class="lineup__pos">C</div>
        <a title="Victor Wembanyama" href="/x">V. Wembanyama</a>
    </li>
    <li><button data-team="SAS" data-nickname="Spurs" data-home="1">Projected Minutes</button></li>
</ul>'''

_FULL_GAME_HTML = _OKC_VISIT_UL + "\n" + _SAS_HOME_UL


# ── tests ────────────────────────────────────────────────────────────────────

def test_parse_one_list_full_okc_visit():
    p = fl.parse_one_list(_OKC_VISIT_UL)
    assert p["team"] == "OKC"
    assert p["status"] == "Expected"
    # 5 starters — Ajay Mitchell (MAY NOT PLAY section) excluded.
    assert len(p["starters"]) == 5
    names = [s["name"] for s in p["starters"]]
    assert names == ["Shai Gilgeous-Alexander", "Luguentz Dort", "Jalen Williams",
                     "Chet Holmgren", "Isaiah Hartenstein"]
    positions = [s["pos"] for s in p["starters"]]
    assert positions == ["PG", "SG", "SF", "PF", "C"]
    # Williams flagged Questionable at 50% — the test that catches greedy-regex bugs.
    williams = next(s for s in p["starters"] if s["name"] == "Jalen Williams")
    assert williams["play_pct"] == 50
    assert williams["injury"] == "Ques"
    # No injury on the others — must be None, not blank string or stale carry-over.
    sga = next(s for s in p["starters"] if s["name"] == "Shai Gilgeous-Alexander")
    assert sga["injury"] is None
    assert sga["play_pct"] == 100


def test_parse_one_list_full_sas_home():
    p = fl.parse_one_list(_SAS_HOME_UL)
    assert p["team"] == "SAS"
    assert p["status"] == "Expected"
    assert len(p["starters"]) == 5
    # All 100%, no injuries
    assert all(s["play_pct"] == 100 for s in p["starters"])
    assert all(s["injury"] is None for s in p["starters"])


def test_parse_html_pairs_visit_then_home_in_doc_order():
    games = fl.parse_html(_FULL_GAME_HTML)
    assert len(games) == 1
    g = games[0]
    assert g["away_team"] == "OKC"
    assert g["home_team"] == "SAS"
    assert g["away_lineup"]["status"] == "Expected"
    assert g["home_lineup"]["status"] == "Expected"
    assert len(g["away_lineup"]["starters"]) == 5
    assert len(g["home_lineup"]["starters"]) == 5


def test_parse_html_skips_lists_with_zero_starters():
    """A stub <ul class='lineup__list ...'> with no <li.lineup__player> is a
    placeholder rotowire renders before the lineup is announced — drop it."""
    html = (_OKC_VISIT_UL +
            '<ul class="lineup__list is-home"></ul>' +
            _SAS_HOME_UL)
    games = fl.parse_html(html)
    # Empty UL should be skipped so the OKC-visit and SAS-home still pair.
    assert len(games) == 1
    assert games[0]["away_team"] == "OKC"
    assert games[0]["home_team"] == "SAS"


def test_parse_html_returns_empty_when_no_lineups():
    """No <ul class='lineup__list ...'> in body → empty list, no crash."""
    games = fl.parse_html("<html><body>nothing here</body></html>")
    assert games == []


def test_write_payload_creates_dir_and_returns_starter_count():
    games = fl.parse_html(_FULL_GAME_HTML)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "deep", "nested", "lineups.json")
        n = fl.write_payload(games, "2026-05-24", out)
        # 10 = 5 visit + 5 home
        assert n == 10
        assert os.path.exists(out)
        with open(out) as fh:
            d = json.load(fh)
        assert d["date"] == "2026-05-24"
        assert d["source"] == fl._ROTOWIRE_URL
        assert len(d["games"]) == 1


def test_parser_does_not_bleed_injury_tag_across_li():
    """Regression: when a middle <li> has <span class='lineup__inj'>, an
    earlier-version regex used .*? which spanned <li> boundaries and ate
    PG+SG into a single PG-with-injury match. Locked down by /</li> anchor."""
    p = fl.parse_one_list(_OKC_VISIT_UL)
    sga = next(s for s in p["starters"] if s["pos"] == "PG")
    dort = next(s for s in p["starters"] if s["pos"] == "SG")
    williams = next(s for s in p["starters"] if s["pos"] == "SF")
    assert sga["injury"] is None
    assert dort["injury"] is None
    assert williams["injury"] == "Ques"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
