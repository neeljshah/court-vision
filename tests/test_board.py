"""Fast unit tests for the V9 PAPER board data assembler and renderer.

Uses a stubbed sim result (np-generated samples, no GPU/cache) injected via
build_board(_result=stub, ...) so NO GPU/sim/cache is needed. Mirrors the
pattern from test_sportsbook_engine.py. Whole suite must run in < 30s.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
import types

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import board_data as bd          # noqa: E402
import board_render as br        # noqa: E402


# ---------------------------------------------------------------------------
# Canonical stub (mirrors test_sportsbook_engine._stub_result exactly)
# ---------------------------------------------------------------------------

_ALL_KEYS = ["pts", "fga", "fgm", "fg3a", "fg3m", "fta", "ftm",
             "oreb", "dreb", "ast", "stl", "blk", "tov", "pf", "reb"]


def _player(rng, pts_mean, reb_mean, ast_mean, name, team, pool, pie_sign=0.0):
    n = pool.shape[0]
    pts = np.clip(rng.normal(pts_mean, pts_mean * 0.18, n) + pie_sign * (pool - pool.mean()), 0, None)
    reb = np.clip(rng.normal(reb_mean, max(reb_mean * 0.4, 1.0), n), 0, None)
    ast = np.clip(rng.normal(ast_mean, max(ast_mean * 0.5, 1.0), n), 0, None)
    s = {
        "pts": pts, "reb": reb, "ast": ast,
        "fga": pts * 0.9, "fgm": pts * 0.4, "fg3a": pts * 0.25, "fg3m": pts * 0.1,
        "fta": pts * 0.3, "ftm": pts * 0.25,
        "oreb": reb * 0.3, "dreb": reb * 0.7,
        "stl": rng.poisson(1.0, n).astype(float),
        "blk": rng.poisson(0.6, n).astype(float),
        "tov": rng.poisson(2.0, n).astype(float),
        "pf": rng.poisson(2.2, n).astype(float),
    }
    return {
        "name": name, "team": team,
        "mean": {"pts": float(pts.mean()), "reb": float(reb.mean()), "ast": float(ast.mean())},
        "reb_mean": float(reb.mean()),
        "samples": {k: s[k] for k in _ALL_KEYS},
    }


def _stub_result(n: int = 4000, seed: int = 1):
    rng = np.random.default_rng(seed)
    pool = rng.normal(0, 6, n)
    players = {
        101: _player(rng, 26, 4, 7, "Star Guard", "NYK", pool, pie_sign=+1.0),
        102: _player(rng, 20, 11, 3, "Big Man", "NYK", pool, pie_sign=-1.0),
        103: _player(rng, 14, 5, 4, "Wing", "NYK", pool),
        201: _player(rng, 24, 10, 4, "Away Star", "SAS", -pool, pie_sign=+1.0),
        202: _player(rng, 13, 6, 5, "Away Wing", "SAS", -pool, pie_sign=-1.0),
    }
    home_total = sum(players[p]["samples"]["pts"] for p in (101, 102, 103)) + rng.normal(50, 6, n)
    away_total = sum(players[p]["samples"]["pts"] for p in (201, 202)) + rng.normal(70, 6, n)
    return types.SimpleNamespace(
        home_tri="NYK", away_tri="SAS",
        home_total=home_total, away_total=away_total,
        home_win_prob=float((home_total > away_total).mean()),
        players=players,
    )


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def board(monkeypatch_module):
    monkeypatch_module.setenv("CV_PAPER_BOARD", "1")
    stub = _stub_result()
    return bd.build_board(
        home="NYK", away="SAS", nsims=100,
        demo=True, _result=stub,
    )


# monkeypatch_module helper (module-scope monkeypatch)
@pytest.fixture(scope="module")
def monkeypatch_module(request):
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_import_side_effect_free(capsys):
    """Reimporting board_data prints nothing."""
    importlib.reload(bd)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert hasattr(bd, "build_board")


def test_gate_default_off(monkeypatch):
    """CV_PAPER_BOARD unset -> is_enabled False."""
    monkeypatch.delenv("CV_PAPER_BOARD", raising=False)
    assert bd.is_enabled(force=False) is False


def test_gate_enabled_by_env_or_force(monkeypatch):
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    assert bd.is_enabled(force=False) is True
    monkeypatch.setenv("CV_PAPER_BOARD", "0")
    assert bd.is_enabled(force=False) is False
    assert bd.is_enabled(force=True) is True


def test_build_board_keys(monkeypatch):
    """All top-level sections present in board dict."""
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    stub = _stub_result()
    b = bd.build_board(home="NYK", away="SAS", nsims=50, demo=True, _result=stub)
    required_keys = {
        "meta", "banners", "pregame", "edges_plain_english",
        "portfolio", "live", "bankroll_clv", "guardrails",
        "caveat", "honesty_class",
    }
    assert required_keys.issubset(set(b.keys())), f"Missing keys: {required_keys - set(b.keys())}"


def test_board_honesty_paper(monkeypatch):
    """honesty_class=='paper'; all 3 banners present; every edge sentence ends with playoff caveat."""
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    stub = _stub_result()
    b = bd.build_board(home="NYK", away="SAS", nsims=50, demo=True, _result=stub)

    assert b["honesty_class"] == "paper"
    assert len(b["banners"]) == 3
    levels = [bn["level"] for bn in b["banners"]]
    assert levels.count("critical") >= 2
    assert any("warn" in lv for lv in levels)

    for edge in b.get("edges_plain_english", []):
        assert "paper only" in edge["sentence"].lower(), (
            f"Edge sentence missing playoff caveat: {edge['sentence'][:80]}"
        )


def test_plain_english_only_flagged_edges(monkeypatch):
    """edges_plain_english all have edge>=MIN_EDGE and ev>0."""
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    stub = _stub_result()
    b = bd.build_board(home="NYK", away="SAS", nsims=50, demo=True, _result=stub)
    for edge in b.get("edges_plain_english", []):
        assert float(edge["edge"]) >= bd.MIN_EDGE, f"edge {edge['edge']} < MIN_EDGE"
        assert float(edge["ev"]) > 0.0, f"ev {edge['ev']} not positive"


def test_guardrail_small_default_bankroll(monkeypatch):
    """meta.bankroll == DEFAULT_BANKROLL (100); portfolio max_stake_pct <= 0.04."""
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    stub = _stub_result()
    b = bd.build_board(home="NYK", away="SAS", nsims=50, demo=True, _result=stub)
    assert b["meta"]["bankroll"] == bd.DEFAULT_BANKROLL
    assert b["portfolio"]["max_stake_pct"] <= 0.04


def test_portfolio_never_increases_stake(monkeypatch):
    """Guardrail bets must have stake == source PaperBet.stake (no inflation)."""
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    stub = _stub_result()

    # Build raw portfolio for comparison
    from market_catalog import price_markets
    from portfolio_optimizer import build_portfolio
    from sportsbook_engine import synth_paper_lines
    paper_lines = synth_paper_lines(stub)
    markets = price_markets(stub, paper_lines)
    raw_port = build_portfolio(stub, markets, bankroll=bd.DEFAULT_BANKROLL)

    b = bd.build_board(home="NYK", away="SAS", nsims=50, demo=True, _result=stub)
    guardrail_bets = b["portfolio"]["bets"]

    # Build a lookup of source stakes by (entity, market_type, side, line)
    raw_stakes = {}
    for raw_b in raw_port["bets"]:
        rd = raw_b if isinstance(raw_b, dict) else vars(raw_b)
        key = (rd.get("entity"), rd.get("market_type"), rd.get("side"), rd.get("line"))
        raw_stakes[key] = float(rd.get("stake", 0.0))

    for gb in guardrail_bets:
        key = (gb.get("entity"), gb.get("market_type"), gb.get("side"), gb.get("line"))
        if key in raw_stakes:
            assert float(gb["stake"]) <= raw_stakes[key] + 1e-6, (
                f"Guardrail inflated stake: {gb['stake']} > {raw_stakes[key]} for {key}"
            )


def test_live_section_none_when_no_pbp(monkeypatch):
    """build_board with a nonexistent game_id -> board['live'] is None."""
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    stub = _stub_result()
    b = bd.build_board(
        home="NYK", away="SAS", nsims=50, demo=True,
        _result=stub, live_game_id="0000000000",
    )
    assert b["live"] is None


def test_clv_graceful_when_no_log(monkeypatch, tmp_path):
    """clv_available=False and no crash when log is absent."""
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    # Point CLV log to a nonexistent path by monkeypatching the LOG var
    import clv_capture
    monkeypatch.setattr(clv_capture, "LOG", str(tmp_path / "nonexistent_clv_log.parquet"))

    stub = _stub_result()
    b = bd.build_board(home="NYK", away="SAS", nsims=50, demo=True, _result=stub)
    assert b["bankroll_clv"]["clv_available"] is False


def test_render_html_standalone(monkeypatch):
    """render_board -> self-contained HTML: doctype, banners, CONFIRM, no external deps."""
    monkeypatch.setenv("CV_PAPER_BOARD", "1")
    stub = _stub_result()
    b = bd.build_board(home="NYK", away="SAS", nsims=50, demo=True, _result=stub)
    h = br.render_board(b)

    assert isinstance(h, str) and len(h) > 500
    assert "<!doctype html" in h.lower(), "Missing doctype"

    # No external resources
    assert not re.search(r'src="https?://', h), "External src= found"
    assert not re.search(r'cdn\.', h), "CDN reference found"
    assert not re.search(r'<script\s+src', h, re.IGNORECASE), "External script tag found"

    # All 3 banners
    assert "PAPER -- no real money is placed." in h
    assert "NO proven betting edge" in h
    assert "ROI requires" in h

    # CONFIRM friction present
    assert "Type CONFIRM" in h


def test_no_realmoney_path():
    """board_data.py source must NOT call real-money path functions.

    Comments/docstrings may MENTION these tokens to document what is forbidden;
    actual imports or call-site references are the real check. We strip comment
    lines (# ...) and docstring literals before scanning.
    """
    src_path = os.path.join(ROOT, "scripts", "team_system", "board_data.py")
    with open(src_path, encoding="utf-8") as f:
        lines = f.readlines()

    # Keep only non-comment, non-docstring lines; strip inline comments
    code_lines = []
    in_docstring = False
    for line in lines:
        stripped = line.strip()
        # Toggle docstring state
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        # Strip inline comment
        code_part = line.split("#")[0]
        code_lines.append(code_part)

    code_only = "\n".join(code_lines)
    # Real-money call patterns: import or function-call form
    forbidden_patterns = [r"log_bet\s*\(", r"record_clv\s*\(", r"bet_log\.json"]
    import re as _re
    for pat in forbidden_patterns:
        match = _re.search(pat, code_only)
        assert match is None, (
            f"Real-money pattern '{pat}' called in board_data.py code: "
            f"{code_only[max(0,match.start()-40):match.end()+40]!r}"
        )
