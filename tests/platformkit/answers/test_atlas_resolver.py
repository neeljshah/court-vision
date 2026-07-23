"""Per-file tests: atlas_card resolver (entity lookup across built atlas
manifests) + classifier/registry-dispatch routing.

Run: python -m pytest tests/platformkit/answers/test_atlas_resolver.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.answers import atlas_resolver
from scripts.platformkit.answers.resolver_registry import classify, resolve


@pytest.fixture()
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_resolver, "_REPO", tmp_path)
    d = tmp_path / atlas_resolver._OUT_DIR_REL
    d.mkdir(parents=True)
    return d


def _write_manifest(out_dir, sport, entries):
    manifest = {"sport": sport, "generated_at": "2026-07-22T00:00:00+00:00",
                "descriptive_only": True, "n_entries": len(entries), "entries": entries}
    (out_dir / f"atlas_{sport}_manifest.json").write_text(json.dumps(manifest), encoding="ascii")


def _entry(entity, **key_numbers):
    return {"entity": entity, "card_path": f"docs/img/atlas/x/{entity}.png",
            "key_numbers": key_numbers, "floors": "n>=1 (test)", "as_of": "2026-07-20"}


def test_classifier_routes_atlas_card():
    assert classify("card for Nikola Jokic") == "atlas_card"
    assert classify("show Nikola Jokic atlas") == "atlas_card"
    assert classify("atlas card for LeBron James") == "atlas_card"
    assert classify("show me the Lakers atlas card") == "atlas_card"
    # unrelated queries stay unrelated (no false-positive on plain "card")
    assert classify("claim survival card decay") != "atlas_card"


def test_parse_entity_extracts_both_shapes():
    assert atlas_resolver.parse_entity("card for Nikola Jokic") == "Nikola Jokic"
    assert atlas_resolver.parse_entity("show Nikola Jokic atlas") == "Nikola Jokic"
    assert atlas_resolver.parse_entity("atlas card for the Lakers?") == "Lakers"
    assert atlas_resolver.parse_entity("show me the Boston Celtics atlas") == "Boston Celtics"
    assert atlas_resolver.parse_entity("who is the best shooter") is None


def test_no_manifests_built_fails_closed(out_dir):
    r = atlas_resolver.resolve("Nikola Jokic")
    assert r["status"] == "no_data"
    assert "no atlas manifests built" in r["note"]


def test_no_match_fails_closed_never_invented(out_dir):
    _write_manifest(out_dir, "nba", [_entry("Nikola Jokic", career_games=210)])
    r = atlas_resolver.resolve("Some Player Nobody Tracks")
    assert r["status"] == "no_data"
    assert "refusing, not guessing" in r["note"]


def test_ok_match_returns_manifest_fields_verbatim(out_dir):
    entry = _entry("Nikola Jokic", career_games=210, career_pts_per36=28.4)
    _write_manifest(out_dir, "nba", [entry])
    r = atlas_resolver.resolve("Nikola Jokic")
    assert r["status"] == "ok"
    assert r["sport"] == "nba"
    assert r["source_artifact"] == "scripts/platformkit/analytics_showcase/out/atlas_nba_manifest.json"
    assert r["card_path"] == entry["card_path"]
    assert r["key_numbers"] == entry["key_numbers"]  # verbatim, not recomputed
    assert r["floors"] == entry["floors"]
    assert r["descriptive_only"] is True
    assert r["edge_claimed"] is False


def test_name_normalization_case_accent_whitespace(out_dir):
    _write_manifest(out_dir, "tennis", [_entry("Novak Djokovic", hard_wr_career=0.83),
                                         _entry("Luka Doncic", hard_wr_career=0.0)])
    for query in ("  NOVAK DJOKOVIC  ", "novak   djokovic", "Novak Djokovic"):
        r = atlas_resolver.resolve(query)
        assert r["status"] == "ok" and r["entity"] == "Novak Djokovic"
    # stored ASCII name still matches an accented query (NFKD strip both sides)
    r = atlas_resolver.resolve("Luka Dončić")
    assert r["status"] == "ok" and r["entity"] == "Luka Doncic"


def test_ambiguous_across_manifests_then_sport_filter_narrows(out_dir):
    _write_manifest(out_dir, "nba", [_entry("Jordan Walsh", career_games=40)])
    _write_manifest(out_dir, "mlb", [_entry("Jordan Walsh", pitches_faced=500)])
    r = atlas_resolver.resolve("Jordan Walsh")
    assert r["status"] == "ambiguous"
    assert {c["sport"] for c in r["candidates"]} == {"nba", "mlb"}
    narrowed = atlas_resolver.resolve("Jordan Walsh", sport_filter="mlb")
    assert narrowed["status"] == "ok" and narrowed["sport"] == "mlb"


def test_registry_dispatch_end_to_end(out_dir):
    entry = _entry("Nikola Jokic", career_games=210)
    _write_manifest(out_dir, "nba", [entry])
    r = resolve("card for Nikola Jokic")
    assert r["status"] == "ok"
    assert r["category"] == "atlas_card"
    assert r["card_path"] == entry["card_path"]
    # unparseable entity (category forced explicitly) -> honest no_data, never a crash
    r2 = resolve("", category="atlas_card")
    assert r2["status"] == "no_data"
