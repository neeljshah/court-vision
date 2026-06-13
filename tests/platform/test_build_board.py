"""tests/platform/test_build_board.py — tests for build_board.build().

Coverage
--------
  - build() writes board.json and board.html into the specified tmp dir.
  - board.json is valid JSON with the 4 registered sport keys.
  - board.html contains the honest banner (no-edge language).
  - board.html contains no banned edge-claim words.
  - build() is graceful when a sport corpus is absent (returns [] for that sport).
  - Real-corpus smoke: build() on real data produces non-empty rows for sports
    with a corpus present (skipped per-sport when corpus absent).

Run: python -m pytest tests/platform/test_build_board.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.platformkit.frontend.build_board import build, _REPO_ROOT
from scripts.platformkit.frontend.board import _SPORT_REGISTRY

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Multi-word phrases and whole-word tokens that indicate edge claims.
# We test JSON (data layer) separately from HTML (which may contain CSS tokens
# that are substrings of banned words — e.g. "inline-block" contains "lock").
# For JSON we test exact substrings; for HTML we use whole-word regex to avoid
# CSS false positives ("inline-block" / "block" must not match "lock").
_BANNED_PHRASES = (
    "guaranteed",
    "beat the market",
    "+ev edge",
    "profit",
)
# These are tested as whole-word tokens in HTML to avoid CSS false positives.
_BANNED_WORDS_HTML = (
    "guaranteed",
    "beat the market",
    "+ev edge",
    "profit",
)

# Phrases that MUST appear in the HTML honest banner
_HONEST_PHRASES = (
    "no model edge",
    "markets are efficient",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(tmp_path: Path) -> dict:
    json_path = tmp_path / "board.json"
    assert json_path.exists(), f"board.json not written to {tmp_path}"
    with open(json_path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_html(tmp_path: Path) -> str:
    html_path = tmp_path / "board.html"
    assert html_path.exists(), f"board.html not written to {tmp_path}"
    return html_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# File-existence tests
# ---------------------------------------------------------------------------

def test_build_writes_json(tmp_path):
    build(out_dir=tmp_path)
    assert (tmp_path / "board.json").exists()


def test_build_writes_html(tmp_path):
    build(out_dir=tmp_path)
    assert (tmp_path / "board.html").exists()


# ---------------------------------------------------------------------------
# board.json content tests
# ---------------------------------------------------------------------------

def test_json_has_all_sport_keys(tmp_path):
    build(out_dir=tmp_path)
    data = _load_json(tmp_path)
    for sport_id in _SPORT_REGISTRY:
        assert sport_id in data, (
            f"board.json missing sport key {sport_id!r}; keys={list(data.keys())}"
        )


def test_json_sport_values_are_lists(tmp_path):
    build(out_dir=tmp_path)
    data = _load_json(tmp_path)
    for sport_id, rows in data.items():
        assert isinstance(rows, list), (
            f"board.json[{sport_id!r}] should be a list, got {type(rows)}"
        )


def test_json_no_banned_words(tmp_path):
    build(out_dir=tmp_path)
    raw = (tmp_path / "board.json").read_text(encoding="utf-8").lower()
    for phrase in _BANNED_PHRASES:
        assert phrase not in raw, (
            f"board.json contains banned edge-claim phrase: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# board.html content tests
# ---------------------------------------------------------------------------

def test_html_contains_honest_banner(tmp_path):
    build(out_dir=tmp_path)
    html = _read_html(tmp_path).lower()
    for phrase in _HONEST_PHRASES:
        assert phrase in html, (
            f"board.html honest banner missing phrase: {phrase!r}"
        )


def test_html_no_banned_words(tmp_path):
    """Check HTML data content (not CSS) for edge-claim language.

    We scan only the <body> text outside of <style> tags so that CSS tokens
    such as 'inline-block' don't produce false positives.
    """
    build(out_dir=tmp_path)
    html_raw = _read_html(tmp_path).lower()
    # Strip style blocks before checking word-level banned phrases
    body_no_css = re.sub(r"<style[^>]*>.*?</style>", " ", html_raw, flags=re.DOTALL)
    for phrase in _BANNED_WORDS_HTML:
        assert phrase not in body_no_css, (
            f"board.html (outside CSS) contains banned edge-claim phrase: {phrase!r}"
        )


def test_html_is_well_formed(tmp_path):
    build(out_dir=tmp_path)
    html = _read_html(tmp_path)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


# ---------------------------------------------------------------------------
# Graceful absent-corpus behaviour
# ---------------------------------------------------------------------------

def test_build_graceful_absent_corpus(tmp_path):
    """build() should not raise when all corpora are absent (empty repo clone)."""
    fake_root = tmp_path / "fake_repo"
    fake_root.mkdir()
    # Patch _REPO_ROOT inside the module so build() uses the fake root
    import scripts.platformkit.frontend.build_board as bb
    original = bb._REPO_ROOT
    bb._REPO_ROOT = fake_root
    try:
        board = build(out_dir=tmp_path / "out_absent")
    finally:
        bb._REPO_ROOT = original

    for sport_id, rows in board.items():
        assert rows == [], (
            f"Expected [] for absent corpus {sport_id!r}, got {len(rows)} rows"
        )


# ---------------------------------------------------------------------------
# Real-corpus smoke tests (skip per-sport when corpus absent)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sport_id", list(_SPORT_REGISTRY.keys()))
def test_real_corpus_rows_nonempty(sport_id, tmp_path):
    """When a real corpus exists, build() must return >0 rows for that sport."""
    reg = _SPORT_REGISTRY[sport_id]
    primary = _REPO_ROOT / reg["corpus_dir"] / reg["primary_parquet"]
    if not primary.exists():
        pytest.skip(f"Corpus absent for {sport_id}: {primary}")

    board = build(out_dir=tmp_path)
    rows = board.get(sport_id, [])
    assert len(rows) > 0, (
        f"build() returned 0 rows for {sport_id!r} despite corpus at {primary}"
    )


@pytest.mark.parametrize("sport_id", list(_SPORT_REGISTRY.keys()))
def test_real_corpus_row_schema(sport_id, tmp_path):
    """Row dicts for real-corpus sports must have model_prob/market_fair_prob keys."""
    reg = _SPORT_REGISTRY[sport_id]
    primary = _REPO_ROOT / reg["corpus_dir"] / reg["primary_parquet"]
    if not primary.exists():
        pytest.skip(f"Corpus absent for {sport_id}: {primary}")

    board = build(out_dir=tmp_path)
    rows = board.get(sport_id, [])
    for row in rows:
        assert "model_prob" in row, f"Row missing 'model_prob' for {sport_id}"
        assert "market_fair_prob" in row, f"Row missing 'market_fair_prob' for {sport_id}"
        mp = row["model_prob"]
        mfp = row["market_fair_prob"]
        if mp is not None:
            assert 0.0 <= mp <= 1.0, f"model_prob {mp} out of range for {sport_id}"
        if mfp is not None:
            assert 0.0 <= mfp <= 1.0, f"market_fair_prob {mfp} out of range for {sport_id}"
