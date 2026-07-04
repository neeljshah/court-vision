"""Per-file tests for scripts.platformkit.clv.kx_close_fallback (Lane 5).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/clv/test_kx_close_fallback.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.clv import kx_ticker_close as K
from scripts.platformkit.clv import kx_close_fallback as F


def _seed_close(tmp_path, ticker: str, sport: str, close_prob: float):
    grade_dir = tmp_path / "grade"
    out_dir = tmp_path / "closes"
    p = grade_dir / sport / (ticker + ".jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "sport": sport, "game_id": ticker, "ts": "2026-07-01T12:00:00Z",
            "market_prob": close_prob, "model_prob": 0.5, "side": "home",
        }) + "\n")
    K.write_closes(sport, grade_dir=grade_dir, out_dir=out_dir)
    return out_dir


# ---------------------------------------------------------------------------
# lookup_close_legs_kx: happy path -- derives (home_dec, away_dec, False)
# ---------------------------------------------------------------------------

def test_lookup_close_legs_kx_happy_path(tmp_path, monkeypatch):
    out_dir = _seed_close(tmp_path, "KXMLBGAME-HAPPY", "mlb", 0.65)
    monkeypatch.setattr(F._kx, "DEFAULT_CLOSES_DIR", out_dir)
    row = {"game_id": "KXMLBGAME-HAPPY", "sport": "mlb"}
    legs = F.lookup_close_legs_kx(row)
    assert legs is not None
    home_dec, away_dec, is_true = legs
    assert home_dec == pytest.approx(1.0 / 0.65)
    assert away_dec == pytest.approx(1.0 / 0.35)
    assert is_true is False  # a last-tick proxy is NEVER a true close


# ---------------------------------------------------------------------------
# ESPN-numeric game_id rows are OUT OF SCOPE for this fallback.
# ---------------------------------------------------------------------------

def test_lookup_close_legs_kx_none_for_espn_numeric_id():
    row = {"game_id": "401815820", "sport": "mlb"}
    assert F.lookup_close_legs_kx(row) is None


def test_lookup_close_legs_kx_none_for_missing_id():
    assert F.lookup_close_legs_kx({"sport": "mlb"}) is None


# ---------------------------------------------------------------------------
# No derived close on disk -> None (honest miss, not a crash).
# ---------------------------------------------------------------------------

def test_lookup_close_legs_kx_none_when_never_derived(tmp_path, monkeypatch):
    out_dir = tmp_path / "closes_empty"
    monkeypatch.setattr(F._kx, "DEFAULT_CLOSES_DIR", out_dir)
    row = {"game_id": "KXMLBGAME-NEVER", "sport": "mlb"}
    assert F.lookup_close_legs_kx(row) is None


# ---------------------------------------------------------------------------
# Degenerate close_prob (0.0 or 1.0) must not divide-by-zero -> None.
# ---------------------------------------------------------------------------

def test_lookup_close_legs_kx_degenerate_prob_is_none(tmp_path, monkeypatch):
    out_dir = _seed_close(tmp_path, "KXMLBGAME-DEGEN", "mlb", 1.0)
    monkeypatch.setattr(F._kx, "DEFAULT_CLOSES_DIR", out_dir)
    row = {"game_id": "KXMLBGAME-DEGEN", "sport": "mlb"}
    assert F.lookup_close_legs_kx(row) is None


# ---------------------------------------------------------------------------
# event_id fallback join (same preference order as clv_close_lookup._join_id).
# ---------------------------------------------------------------------------

def test_lookup_close_legs_kx_uses_event_id_when_no_game_id(tmp_path, monkeypatch):
    out_dir = _seed_close(tmp_path, "KXMLBGAME-EVT", "mlb", 0.55)
    monkeypatch.setattr(F._kx, "DEFAULT_CLOSES_DIR", out_dir)
    row = {"event_id": "KXMLBGAME-EVT", "sport": "mlb"}
    legs = F.lookup_close_legs_kx(row)
    assert legs is not None


# ---------------------------------------------------------------------------
# close_kind_for_row mirrors lookup_close_legs_kx's success/failure.
# ---------------------------------------------------------------------------

def test_close_kind_for_row(tmp_path, monkeypatch):
    out_dir = _seed_close(tmp_path, "KXMLBGAME-KIND", "mlb", 0.6)
    monkeypatch.setattr(F._kx, "DEFAULT_CLOSES_DIR", out_dir)
    row = {"game_id": "KXMLBGAME-KIND", "sport": "mlb"}
    assert F.close_kind_for_row(row) == "last_tick"
    assert F.close_kind_for_row({"game_id": "401815820", "sport": "mlb"}) is None
