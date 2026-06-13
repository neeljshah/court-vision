"""tests/platform/test_build_board.py — tests for build_board.build().

Coverage: writes json+html · sport keys · honest banner · no banned words ·
graceful absent corpus · default build is windowed (max_rows=200, html<=500 KB) ·
real-corpus rows capped at 200 · real-corpus html small.

Run: python -m pytest tests/platform/test_build_board.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.platformkit.frontend.build_board import build, _REPO_ROOT, _DEFAULT_MAX_ROWS
from scripts.platformkit.frontend.board import _SPORT_REGISTRY

_BANNED_DATA = ("guaranteed", "beat the market", "+ev edge", "profit")
_BANNED_HTML = ("guaranteed", "beat the market", "+ev edge", "profit")
_HONEST = ("no model edge", "markets are efficient")
_MAX_HTML = 500 * 1024  # 500 KB


def _json(tmp_path):
    p = tmp_path / "board.json"
    assert p.exists()
    return json.loads(p.read_text())


def _html(tmp_path):
    p = tmp_path / "board.html"
    assert p.exists()
    return p.read_text(encoding="utf-8")


# --- constants ---

def test_default_max_rows_is_200():
    assert _DEFAULT_MAX_ROWS == 200


# --- file existence ---

def test_build_writes_json(tmp_path):
    build(out_dir=tmp_path)
    assert (tmp_path / "board.json").exists()

def test_build_writes_html(tmp_path):
    build(out_dir=tmp_path)
    assert (tmp_path / "board.html").exists()


# --- board.json content ---

def test_json_has_all_sport_keys(tmp_path):
    build(out_dir=tmp_path)
    data = _json(tmp_path)
    for sid in _SPORT_REGISTRY:
        assert sid in data

def test_json_sport_values_are_lists(tmp_path):
    build(out_dir=tmp_path)
    for sid, rows in _json(tmp_path).items():
        assert isinstance(rows, list)

def test_json_no_banned_words(tmp_path):
    build(out_dir=tmp_path)
    raw = (tmp_path / "board.json").read_text().lower()
    for phrase in _BANNED_DATA:
        assert phrase not in raw


# --- board.html content ---

def test_html_contains_honest_banner(tmp_path):
    build(out_dir=tmp_path)
    low = _html(tmp_path).lower()
    for phrase in _HONEST:
        assert phrase in low

def test_html_no_banned_words(tmp_path):
    build(out_dir=tmp_path)
    no_css = re.sub(r"<style[^>]*>.*?</style>", " ", _html(tmp_path).lower(), flags=re.DOTALL)
    for phrase in _BANNED_HTML:
        assert phrase not in no_css

def test_html_is_well_formed(tmp_path):
    build(out_dir=tmp_path)
    h = _html(tmp_path)
    assert h.startswith("<!DOCTYPE html>")
    assert "</html>" in h


# --- absent corpus ---

def test_build_graceful_absent_corpus(tmp_path):
    fake = tmp_path / "fake_repo"
    fake.mkdir()
    import scripts.platformkit.frontend.build_board as bb
    orig = bb._REPO_ROOT
    bb._REPO_ROOT = fake
    try:
        board = build(out_dir=tmp_path / "out")
    finally:
        bb._REPO_ROOT = orig
    for rows in board.values():
        assert rows == []


# --- Task 3: default build is windowed ---

def test_build_default_windowed_html_small(tmp_path):
    """Default build (max_rows=200) produces html <= 500 KB even with no corpus."""
    build(out_dir=tmp_path)
    size = (tmp_path / "board.html").stat().st_size
    assert size <= _MAX_HTML, f"board.html is {size} bytes; expected <= {_MAX_HTML}"

def test_build_default_uses_max_rows_200(tmp_path):
    """build() with no window args must forward max_rows_per_sport=200."""
    import scripts.platformkit.frontend.board as board_mod
    captured: dict = {}

    def patched_build_all(repo_root, *, last_n_days, max_rows_per_sport, future_only):
        captured.update(
            max_rows=max_rows_per_sport,
            last_n_days=last_n_days,
            future_only=future_only,
        )
        return {sport: [] for sport in _SPORT_REGISTRY}

    orig = board_mod.build_all_board
    board_mod.build_all_board = patched_build_all
    try:
        build(out_dir=tmp_path)
    finally:
        board_mod.build_all_board = orig

    assert captured["max_rows"] == 200
    assert captured["last_n_days"] is None
    assert captured["future_only"] is False


# --- Real-corpus smoke (skip when absent) ---

@pytest.mark.parametrize("sport_id", list(_SPORT_REGISTRY.keys()))
def test_real_corpus_rows_nonempty(sport_id, tmp_path):
    reg = _SPORT_REGISTRY[sport_id]
    if not (_REPO_ROOT / reg["corpus_dir"] / reg["primary_parquet"]).exists():
        pytest.skip(f"Corpus absent for {sport_id}")
    board = build(out_dir=tmp_path)
    assert len(board.get(sport_id, [])) > 0

@pytest.mark.parametrize("sport_id", list(_SPORT_REGISTRY.keys()))
def test_real_corpus_row_schema(sport_id, tmp_path):
    reg = _SPORT_REGISTRY[sport_id]
    if not (_REPO_ROOT / reg["corpus_dir"] / reg["primary_parquet"]).exists():
        pytest.skip(f"Corpus absent for {sport_id}")
    board = build(out_dir=tmp_path)
    for row in board.get(sport_id, []):
        assert "model_prob" in row and "market_fair_prob" in row
        if row["model_prob"] is not None:
            assert 0.0 <= row["model_prob"] <= 1.0
        if row["market_fair_prob"] is not None:
            assert 0.0 <= row["market_fair_prob"] <= 1.0

@pytest.mark.parametrize("sport_id", list(_SPORT_REGISTRY.keys()))
def test_real_corpus_windowed_rows_capped(sport_id, tmp_path):
    """Default windowed build returns <= 200 rows per sport."""
    reg = _SPORT_REGISTRY[sport_id]
    if not (_REPO_ROOT / reg["corpus_dir"] / reg["primary_parquet"]).exists():
        pytest.skip(f"Corpus absent for {sport_id}")
    board = build(out_dir=tmp_path)
    assert len(board.get(sport_id, [])) <= 200

@pytest.mark.parametrize("sport_id", list(_SPORT_REGISTRY.keys()))
def test_real_corpus_html_small(sport_id, tmp_path):
    """Default windowed build: board.html <= 500 KB."""
    reg = _SPORT_REGISTRY[sport_id]
    if not (_REPO_ROOT / reg["corpus_dir"] / reg["primary_parquet"]).exists():
        pytest.skip(f"Corpus absent for {sport_id}")
    build(out_dir=tmp_path)
    size = (tmp_path / "board.html").stat().st_size
    assert size <= _MAX_HTML, f"board.html {size // 1024} KB > {_MAX_HTML // 1024} KB limit"
