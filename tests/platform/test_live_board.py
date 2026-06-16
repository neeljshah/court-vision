"""Per-file OFFLINE tests for the live multi-sport decision-support board (apps/live_board).

Runs entirely on the committed JSON fixtures in apps/live_board/_fixtures -- NO network. The
ESPN feed is monkeypatched so build_board / the server never touch site.api.espn.com.

Covers the four module contracts:
  (1) name_maps.to_corpus_id -- MLB displayName+abbrev resolve, soccer club map, national -> None
  (2) board._devig -- 2-way sums to 1, 3-way (incl draw) sums to 1, vig removed
  (3) build_board on the MLB fixture -- rows have an allowed source; in-corpus win_home in (0,1)
  (4) FastAPI server -- GET '/' == 200; GET '/api/board?sport=mlb' returns rows + the honest
      no-edge contract (no '$ edge'/ROI/'beat the market' claim string leaks through)

Predictor corpora are gitignored -> when a corpus is absent the in-corpus assertions are skipped
gracefully (the board still serves market-implied / unavailable rows, which we still validate).

Run ONLY this file (never the full suite -- it freezes the box):
  python -m pytest tests/platform/test_live_board.py -q
"""
from __future__ import annotations

import os

import pytest

from apps.live_board import board, espn_feed, name_maps

_FIXDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "..", "apps", "live_board", "_fixtures")
_FIXDIR = os.path.normpath(_FIXDIR)
_MLB_FIX = os.path.join(_FIXDIR, "espn_mlb.json")

_ALLOWED_SOURCES = {"model", "live-model", "market", "live-market", "unavailable"}

# Phrases that would constitute a forbidden $-edge / ROI / beat-the-market claim. We assert NONE
# appear. ('No $ edge claimed.' is the honest footer -> checked separately.) These are multi-word
# phrases on purpose so they cannot collide with CSS tokens (e.g. 'block' contains 'lock').
_FORBIDDEN_CLAIMS = (
    "beat the market", "beat the close", "guaranteed profit", "guaranteed win",
    "positive ev", "% edge", "edge of", "sure thing", "free money",
    "money machine", "+ev bet", "expected roi", "roi of",
)


# ---------------------------------------------------------------------------
# Fixtures: monkeypatch the feed so every consumer reads the committed JSON.
# ---------------------------------------------------------------------------
def _patch_feed_to_mlb_fixture(monkeypatch):
    """Make espn_feed.fetch_games (and the copy imported into board) read the MLB fixture.

    Capture the REAL fetch_games first so the fake can use its _fixture_path loader without
    recursing into the monkeypatched stub.
    """
    real_fetch = espn_feed.fetch_games

    def fake_fetch(sport, *, leagues=None, timeout=8, _fixture_path=None):  # noqa: ARG001
        if (sport or "").lower() == "mlb":
            return real_fetch("mlb", _fixture_path=_MLB_FIX)
        return []
    monkeypatch.setattr(espn_feed, "fetch_games", fake_fetch)
    monkeypatch.setattr(board, "fetch_games", fake_fetch)


# ---------------------------------------------------------------------------
# (1) name_maps.to_corpus_id
# ---------------------------------------------------------------------------
def test_name_maps_mlb_displayname_and_abbrev():
    assert name_maps.to_corpus_id("mlb", "Cincinnati Reds") == "CIN"
    assert name_maps.to_corpus_id("mlb", "New York Mets") == "NYM"
    # abbreviation path (ESPN sometimes only carries the abbreviation)
    assert name_maps.to_corpus_id("mlb", "NYM") == "NYM"
    assert name_maps.to_corpus_id("mlb", "CIN") == "CIN"
    # unknown / empty -> None
    assert name_maps.to_corpus_id("mlb", "Nonexistent Team") is None
    assert name_maps.to_corpus_id("mlb", "") is None
    assert name_maps.to_corpus_id("mlb", None) is None


def test_name_maps_soccer_clubs_and_national_teams():
    assert name_maps.to_corpus_id("soccer", "Manchester City") == "Man City"
    # exact-match club passes through unchanged
    assert name_maps.to_corpus_id("soccer", "Arsenal") == "Arsenal"
    # national teams (World Cup) are out of the club corpus -> None
    assert name_maps.to_corpus_id("soccer", "Brazil") is None
    assert name_maps.to_corpus_id("soccer", "Spain") is None
    assert name_maps.to_corpus_id("soccer", "United States") is None


def test_name_maps_tennis_passthrough_and_supported_leagues():
    # tennis hands the raw name to predictor._resolve downstream
    assert name_maps.to_corpus_id("tennis", "Carlos Alcaraz") == "Carlos Alcaraz"
    assert "mlb" in name_maps.SUPPORTED_LEAGUES["mlb"]
    assert "fifa.world" in name_maps.SUPPORTED_LEAGUES["soccer"]
    assert "atp" in name_maps.SUPPORTED_LEAGUES["tennis"]


# ---------------------------------------------------------------------------
# (2) board._devig
# ---------------------------------------------------------------------------
def test_devig_two_way_sums_to_one_and_removes_vig():
    probs = board._devig(-135, 115)
    assert probs is not None
    assert len(probs) == 2
    assert abs(sum(probs) - 1.0) < 1e-9
    # both legs are valid probabilities in (0, 1)
    assert all(0.0 < p < 1.0 for p in probs)
    # the favorite (-135) carries the larger fair prob
    assert probs[0] > probs[1]


def test_devig_three_way_with_draw_sums_to_one():
    probs = board._devig(-150, 290, 380)  # home / draw / away American lines
    assert probs is not None
    assert len(probs) == 3
    assert abs(sum(probs) - 1.0) < 1e-9
    assert all(0.0 < p < 1.0 for p in probs)


def test_devig_removes_vig_below_raw_overround():
    # raw implied probs sum to > 1 (the overround / vig); devig normalizes to exactly 1
    raw = board._implied(-135) + board._implied(115)
    assert raw > 1.0
    fair = board._devig(-135, 115)
    assert abs(sum(fair) - 1.0) < 1e-9


def test_devig_insufficient_prices_returns_none():
    assert board._devig(None, None) is None
    assert board._devig(-110) is None


# ---------------------------------------------------------------------------
# (3) build_board on the MLB fixture
# ---------------------------------------------------------------------------
def test_build_board_mlb_fixture_rows(monkeypatch):
    _patch_feed_to_mlb_fixture(monkeypatch)
    rows = board.build_board("mlb")
    assert isinstance(rows, list)
    assert len(rows) >= 1
    for r in rows:
        # every row honors the BoardRow contract
        assert r["source"] in _ALLOWED_SOURCES
        assert "win_home" in r and "win_away" in r and "note" in r
        assert "market_implied" in r and isinstance(r["market_implied"], bool)
        # win probabilities, when present, are valid
        for k in ("win_home", "win_away", "draw"):
            v = r[k]
            if v is not None:
                assert 0.0 <= v <= 1.0
        # honest: no row text claims a $ edge / ROI / beat-the-market
        note = (r.get("note") or "").lower()
        for bad in _FORBIDDEN_CLAIMS:
            assert bad not in note, "forbidden claim {!r} in note: {!r}".format(bad, r["note"])


def test_build_board_mlb_in_corpus_winprob_strict(monkeypatch):
    """If the MLB predictor corpus is present, in-corpus rows carry win_home in (0,1) from
    OUR model and are badged model/live-model. Skip if the corpus is absent (gitignored)."""
    _patch_feed_to_mlb_fixture(monkeypatch)
    try:
        from scripts.platformkit.predictor_jd import _build_predictor
        pred = _build_predictor("mlb")
    except Exception:  # noqa: BLE001
        pred = None
    if pred is None:
        pytest.skip("MLB predictor corpus absent (gitignored) -- market path only")
    rows = board.build_board("mlb")
    model_rows = [r for r in rows if r["source"] in ("model", "live-model")]
    assert model_rows, "expected at least one in-corpus MLB row from the fixture"
    for r in model_rows:
        assert r["market_implied"] is False
        assert r["win_home"] is not None and 0.0 < r["win_home"] < 1.0
        assert r["win_away"] is not None and 0.0 < r["win_away"] < 1.0


# ---------------------------------------------------------------------------
# (4) FastAPI server
# ---------------------------------------------------------------------------
def test_server_index_and_board_endpoint(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from apps.live_board import server

    _patch_feed_to_mlb_fixture(monkeypatch)

    client = TestClient(server.app)

    # health
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json().get("ok") is True

    # index page renders
    root = client.get("/")
    assert root.status_code == 200
    page = root.text
    # honest no-edge footer present on the page
    assert "No $ edge claimed" in page
    # page makes NO forbidden $-edge / ROI / beat-the-market claim
    low = page.lower()
    for bad in _FORBIDDEN_CLAIMS:
        assert bad not in low, "forbidden claim {!r} present in board.html".format(bad)

    # board JSON
    b = client.get("/api/board?sport=mlb")
    assert b.status_code == 200
    payload = b.json()
    assert payload.get("sport") == "mlb"
    assert "generated_at" in payload
    assert isinstance(payload.get("rows"), list)
    for r in payload["rows"]:
        assert r["source"] in _ALLOWED_SOURCES
        note = (r.get("note") or "").lower()
        for bad in _FORBIDDEN_CLAIMS:
            assert bad not in note
