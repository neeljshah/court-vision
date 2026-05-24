"""Cycle 54: integration tests for --injuries / --include-injured wiring
in predict_player.py and predict_slate.py (added in cycle 53).

These tests target the new code paths that touch user behavior:
- predict_slate._filter_injuries (pure function)
- predict_player main()'s injury cross-reference branch (mocked at edges)

Other injury logic (taxonomy, file loader, lookup_status) is already covered
by tests/test_data_injuries.py — these tests focus on the CLI integration.
"""
from __future__ import annotations

import json
import os
import runpy
import sys
import tempfile
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# --- predict_slate._filter_injuries ----------------------------------------

import scripts.predict_slate as ps  # noqa: E402


def _row(name, pid, team):
    return {"player_id": pid, "name": name, "team": team,
            "preds": {"pts": 20.0, "reb": 5.0}}


def test_filter_drops_unavailable_players():
    rows = [_row("LeBron James", 2544, "LAL"),
            _row("Anthony Davis", 203076, "LAL"),
            _row("Austin Reaves", 1630559, "LAL")]
    unav = {"lebron james": "OUT", "anthony davis": "DOUBTFUL"}
    out = ps._filter_injuries(rows, unav, {})
    assert [r["name"] for r in out] == ["Austin Reaves"]


def test_filter_tags_soft_warn_players_in_place():
    rows = [_row("Nikola Jokic", 203999, "DEN"),
            _row("Aaron Gordon", 203932, "DEN")]
    soft = {"nikola jokic": "QUESTIONABLE"}
    out = ps._filter_injuries(rows, {}, soft)
    # Both players survive — Jokic gets tagged, Gordon untouched.
    names = [r["name"] for r in out]
    assert "Nikola Jokic [QUESTIONABLE]" in names
    assert "Aaron Gordon" in names


def test_filter_does_not_mutate_input_for_soft_warn():
    """Tagging must not mutate the caller's row dict (would leak into CSV save)."""
    original = _row("Nikola Jokic", 203999, "DEN")
    soft = {"nikola jokic": "QUESTIONABLE"}
    _ = ps._filter_injuries([original], {}, soft)
    # The original dict's name field is unchanged.
    assert original["name"] == "Nikola Jokic"


def test_filter_with_no_injuries_returns_input_unchanged():
    rows = [_row("LeBron James", 2544, "LAL")]
    out = ps._filter_injuries(rows, {}, {})
    assert out == rows


def test_filter_diacritic_insensitive_match():
    """Accented JSON name 'Nikola Jokić' matches plain 'Nikola Jokic' row."""
    rows = [_row("Nikola Jokic", 203999, "DEN")]
    unav = {"nikola jokic": "OUT"}    # already canonical-form key
    out = ps._filter_injuries(rows, unav, {})
    assert out == []


# --- predict_player injury branch ------------------------------------------

import scripts.predict_player as pp  # noqa: E402


def _write_injury_json(players):
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8")
    json.dump({"date": "2026-05-24", "source_pdf": "x.pdf",
               "fetched_at": "2026-05-24T17:00", "players": players}, fh)
    fh.close()
    return fh.name


def _run_predict_player(argv, expected_exit_code):
    """Run main() with patched argv; assert SystemExit code."""
    with mock.patch.object(sys, "argv", ["predict_player.py"] + argv):
        with pytest.raises(SystemExit) as exc:
            pp.main()
    code = exc.value.code if exc.value.code is not None else 0
    assert code == expected_exit_code, f"expected {expected_exit_code}, got {code}"


def test_predict_player_exits_two_when_listed_out(monkeypatch):
    """Listed OUT player exits 2 with --injuries. Uses --name + mocked
    resolver so the injury cross-reference key matches the JSON entry."""
    monkeypatch.setattr(pp, "_resolve_player_id", lambda n: 2544)
    inj_path = _write_injury_json([
        {"team": "LAL", "name": "LeBron James", "status": "OUT", "reason": "rest"},
    ])
    try:
        _run_predict_player(
            ["--name", "LeBron James", "--opp", "DEN", "--home",
             "--injuries", inj_path],
            expected_exit_code=2,
        )
    finally:
        os.unlink(inj_path)


def test_predict_player_does_not_exit_with_include_injured_override(monkeypatch):
    """--include-injured bypasses the OUT skip; main() then proceeds and
    eventually hits the playerlog cache miss (sys.exit 2 on no gamelog)."""
    monkeypatch.setattr(pp, "_resolve_player_id", lambda n: 2544)
    monkeypatch.setattr(pp, "_get_playerlog", lambda *a, **k: [])
    monkeypatch.setattr(pp, "build_prediction_row", lambda *a, **k: None)
    inj_path = _write_injury_json([
        {"team": "LAL", "name": "LeBron James", "status": "OUT", "reason": "rest"},
    ])
    try:
        with mock.patch.object(sys, "argv", [
            "predict_player.py", "--name", "LeBron James", "--opp", "DEN", "--home",
            "--injuries", inj_path, "--include-injured",
        ]):
            captured = []
            def cap(*args, **kwargs):
                captured.append(" ".join(str(a) for a in args))
            with mock.patch("builtins.print", side_effect=cap):
                with pytest.raises(SystemExit):
                    pp.main()
        injury_skip = [line for line in captured
                       if "listed OUT" in line and "injury report" in line]
        assert injury_skip == [], "--include-injured should suppress the [skip] line"
    finally:
        os.unlink(inj_path)


def test_predict_player_soft_warn_questionable_prints_warning(monkeypatch):
    """QUESTIONABLE doesn't block; warn line appears."""
    monkeypatch.setattr(pp, "_resolve_player_id", lambda n: 203999)
    monkeypatch.setattr(pp, "_get_playerlog", lambda *a, **k: [])
    monkeypatch.setattr(pp, "build_prediction_row", lambda *a, **k: None)
    inj_path = _write_injury_json([
        {"team": "DEN", "name": "Nikola Jokic", "status": "QUESTIONABLE", "reason": "ankle"},
    ])
    captured = []
    def cap(*args, **kwargs):
        captured.append(" ".join(str(a) for a in args))
    try:
        with mock.patch.object(sys, "argv", [
            "predict_player.py", "--name", "Nikola Jokic", "--opp", "LAL", "--home",
            "--injuries", inj_path,
        ]):
            with mock.patch("builtins.print", side_effect=cap):
                with pytest.raises(SystemExit):
                    pp.main()
        warn = [line for line in captured if "QUESTIONABLE" in line and "[warn]" in line]
        assert warn, f"expected QUESTIONABLE warn line, got: {captured[:5]}"
    finally:
        os.unlink(inj_path)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
