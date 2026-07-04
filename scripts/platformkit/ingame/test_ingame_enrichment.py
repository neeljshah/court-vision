"""Per-file test for the LANE 1 None-safe enrichment facade.

OFFLINE + deterministic: fixture sidecar dirs (tmp_path) for each source -- no real
data/domains reads, no network. Covers: real fixture hit per source, absent-sidecar
honest None, poisoned-build permanent None (never raises), None-safe when the caller
passes no event_id / no ticker.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ingame/test_ingame_enrichment.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_enrichment as E


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


# --------------------------------------------------------------------------------------- #
# fotmob_xg                                                                                 #
# --------------------------------------------------------------------------------------- #
def test_fotmob_xg_fixture_hit(tmp_path):
    fotmob_dir = tmp_path / "fotmob_live"
    _write_jsonl(fotmob_dir / "123456.jsonl", [
        {"cutoff_min": 30.0, "xg_home": 0.4, "xg_away": 0.1,
         "home": "Argentina", "away": "Australia"},
        {"cutoff_min": 55.0, "xg_home": 1.1, "xg_away": 0.3,
         "home": "Argentina", "away": "Australia"},
    ])
    facade = E.EnrichmentFacade(fotmob_dir=fotmob_dir)
    out = facade.fotmob_xg("Argentina", "Australia")
    assert out == {"xg_home": 1.1, "xg_away": 0.3, "xg_asof_min": 55.0}


def test_fotmob_xg_no_sidecar_dir_is_honest_none(tmp_path):
    facade = E.EnrichmentFacade(fotmob_dir=tmp_path / "absent")
    assert facade.fotmob_xg("Argentina", "Australia") is None


def test_fotmob_xg_no_unambiguous_match_is_none(tmp_path):
    fotmob_dir = tmp_path / "fotmob_live"
    _write_jsonl(fotmob_dir / "1.jsonl", [{"cutoff_min": 10.0, "xg_home": 0.1, "xg_away": 0.0,
                                            "home": "France", "away": "Germany"}])
    facade = E.EnrichmentFacade(fotmob_dir=fotmob_dir)
    assert facade.fotmob_xg("Argentina", "Australia") is None


# --------------------------------------------------------------------------------------- #
# book_depth                                                                                #
# --------------------------------------------------------------------------------------- #
def test_book_depth_fixture_hit_kalshi(tmp_path):
    depth_dir = tmp_path / "book_depth"
    _write_jsonl(depth_dir / "kalshi" / "2026-07-06.jsonl", [
        {"ticker": "KXMLBGAME-26JUL06DETCWS", "spread_bp": 120.0,
         "book_thinness": 40, "stale_quote_flag": False},
        {"ticker": "KXMLBGAME-26JUL06DETCWS", "spread_bp": 80.0,
         "book_thinness": 55, "stale_quote_flag": True},
    ])
    facade = E.EnrichmentFacade(book_depth_dir=depth_dir)
    out = facade.book_depth("KXMLBGAME-26JUL06DETCWS")
    assert out == {"spread_bp": 80.0, "book_thinness": 55, "stale_quote": True}


def test_book_depth_fixture_hit_polymarket_slug(tmp_path):
    depth_dir = tmp_path / "book_depth"
    _write_jsonl(depth_dir / "polymarket" / "2026-07-06.jsonl", [
        {"slug": "det-cws-2026-07-06", "spread_bp": 200.0,
         "book_thinness": 10, "stale_quote_flag": False},
    ])
    facade = E.EnrichmentFacade(book_depth_dir=depth_dir)
    out = facade.book_depth("det-cws-2026-07-06")
    assert out == {"spread_bp": 200.0, "book_thinness": 10, "stale_quote": False}


def test_book_depth_no_sidecar_tree_is_honest_none(tmp_path):
    facade = E.EnrichmentFacade(book_depth_dir=tmp_path / "absent")
    assert facade.book_depth("KXMLBGAME-26JUL06DETCWS") is None


def test_book_depth_no_matching_ticker_is_none(tmp_path):
    depth_dir = tmp_path / "book_depth"
    _write_jsonl(depth_dir / "kalshi" / "2026-07-06.jsonl", [
        {"ticker": "KXWNBAGAME-OTHER", "spread_bp": 10.0, "book_thinness": 5,
         "stale_quote_flag": False},
    ])
    facade = E.EnrichmentFacade(book_depth_dir=depth_dir)
    assert facade.book_depth("KXMLBGAME-26JUL06DETCWS") is None


# --------------------------------------------------------------------------------------- #
# espn_wp                                                                                   #
# --------------------------------------------------------------------------------------- #
def test_espn_wp_fixture_hit_mlb(tmp_path):
    espn_dir = tmp_path / "domains"
    _write_jsonl(espn_dir / "mlb" / "espn_wp" / "401815820.jsonl", [
        {"espn_wp_home": 0.61, "n_wp_points": 40},
        {"espn_wp_home": 0.66, "n_wp_points": 41},
    ])
    facade = E.EnrichmentFacade(espn_wp_dir=espn_dir)
    out = facade.espn_wp("mlb", "401815820")
    assert out == {"espn_wp": 0.66}


def test_espn_wp_unsupported_sport_is_none(tmp_path):
    espn_dir = tmp_path / "domains"
    _write_jsonl(espn_dir / "soccer_intl" / "espn_wp" / "1.jsonl", [{"espn_wp_home": 0.5}])
    facade = E.EnrichmentFacade(espn_wp_dir=espn_dir)
    assert facade.espn_wp("soccer_intl", "1") is None


def test_espn_wp_no_event_id_is_none_pending(tmp_path):
    facade = E.EnrichmentFacade(espn_wp_dir=tmp_path / "domains")
    assert facade.espn_wp("mlb", None) is None
    assert facade.espn_wp("mlb", "") is None


def test_espn_wp_absent_sidecar_is_honest_none(tmp_path):
    facade = E.EnrichmentFacade(espn_wp_dir=tmp_path / "domains")
    assert facade.espn_wp("mlb", "999999") is None


# --------------------------------------------------------------------------------------- #
# poisoned-build never raises, permanent None                                              #
# --------------------------------------------------------------------------------------- #
def test_fotmob_poisoned_glob_permanent_none_never_raises(tmp_path, monkeypatch):
    fotmob_dir = tmp_path / "fotmob_live"
    _write_jsonl(fotmob_dir / "1.jsonl", [{"cutoff_min": 1.0, "xg_home": 0.0, "xg_away": 0.0,
                                            "home": "A", "away": "B"}])
    facade = E.EnrichmentFacade(fotmob_dir=fotmob_dir)

    def _boom(self, *a, **kw):
        raise RuntimeError("poisoned fotmob import")

    monkeypatch.setattr(
        "domains.soccer.ingame_fotmob.match_to_fixture",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("poisoned fotmob")))
    out1 = facade.fotmob_xg("A", "B")
    assert out1 is None
    # permanent: a SECOND call after the poison must ALSO be None (short-circuited),
    # never re-raise even if the underlying call would no longer explode.
    monkeypatch.undo()
    out2 = facade.fotmob_xg("A", "B")
    assert out2 is None


def test_book_depth_poisoned_dir_scan_permanent_none_never_raises(tmp_path, monkeypatch):
    depth_dir = tmp_path / "book_depth"
    _write_jsonl(depth_dir / "kalshi" / "2026-07-06.jsonl", [
        {"ticker": "X", "spread_bp": 1.0, "book_thinness": 1, "stale_quote_flag": False}])
    facade = E.EnrichmentFacade(book_depth_dir=depth_dir)

    class _BoomPath:
        def is_dir(self):
            raise RuntimeError("poisoned filesystem")

    monkeypatch.setattr(facade, "_book_depth_dir", _BoomPath())
    out1 = facade.book_depth("X")
    assert out1 is None
    out2 = facade.book_depth("X")
    assert out2 is None


def test_espn_wp_poisoned_import_permanent_none_never_raises(tmp_path, monkeypatch):
    facade = E.EnrichmentFacade(espn_wp_dir=tmp_path / "domains")
    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *a, **kw):
        if name == "scripts.platformkit.espn_wp_reference":
            raise ImportError("poisoned import")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    out1 = facade.espn_wp("mlb", "1")
    assert out1 is None
    monkeypatch.undo()
    out2 = facade.espn_wp("mlb", "1")
    assert out2 is None


def test_get_facade_singleton_returns_same_instance():
    a = E.get_facade()
    b = E.get_facade()
    assert a is b
