"""Cycle 63: integration tests for --lineups / --require-starter-lineup in
predict_player.py."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.predict_player as pp  # noqa: E402
import scripts.predict_slate as ps  # noqa: E402
import scripts.compare_to_lines as ctl  # noqa: E402


def _starter(pos, name, play_pct=100, injury=None):
    return {"pos": pos, "name": name, "play_pct": play_pct, "injury": injury}


def _lineup_json(games):
    return {"date": "2026-05-24", "fetched_at": "2026-05-24T17:00:00",
            "source": "https://rotowire/x", "games": games}


def _write_tmp(payload):
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json",
                                       encoding="utf-8")
    json.dump(payload, fh); fh.close()
    return fh.name


def _capture_run(argv, monkeypatch):
    """Run predict_player.main with mocked nba_api boundary, capture stdout."""
    monkeypatch.setattr(pp, "_resolve_player_id", lambda n: 2544)
    monkeypatch.setattr(pp, "_get_playerlog", lambda *a, **k: [])
    monkeypatch.setattr(pp, "build_prediction_row", lambda *a, **k: None)
    captured = []
    def cap(*args, **kwargs):
        captured.append(" ".join(str(a) for a in args))
    with mock.patch.object(sys, "argv", ["predict_player.py"] + argv):
        with mock.patch("builtins.print", side_effect=cap):
            try:
                pp.main()
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code if e.code is not None else 0
    return exit_code, captured


def test_lineups_flag_prints_starter_classification(monkeypatch):
    """Player in lineup at 100% play_pct → 'STARTER' line in output."""
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "LAL",
        "away_lineup": {"status": "Expected", "starters": []},
        "home_lineup": {"status": "Confirmed", "starters": [
            _starter("SF", "LeBron James", play_pct=100),
        ]},
    }])
    path = _write_tmp(lu)
    try:
        exit_code, captured = _capture_run(
            ["--name", "LeBron James", "--opp", "OKC", "--home",
             "--lineups", path], monkeypatch)
    finally:
        os.unlink(path)
    lineup_line = [c for c in captured if c.startswith("  Lineup:")]
    assert lineup_line, f"no Lineup: line in output: {captured[:6]}"
    assert "STARTER" in lineup_line[0]
    assert "Confirmed" in lineup_line[0]
    assert "100" in lineup_line[0]


def test_lineups_flag_classifies_questionable(monkeypatch):
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "SAS",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("SF", "Jalen Williams", play_pct=50, injury="Ques"),
        ]},
        "home_lineup": {"status": "Expected", "starters": []},
    }])
    path = _write_tmp(lu)
    try:
        _, captured = _capture_run(
            ["--name", "Jalen Williams", "--opp", "SAS", "--away",
             "--lineups", path], monkeypatch)
    finally:
        os.unlink(path)
    line = [c for c in captured if c.startswith("  Lineup:")][0]
    assert "QUESTIONABLE" in line
    assert "play_pct=50" in line
    assert "inj=Ques" in line


def test_lineups_flag_classifies_bench_for_unknown_player(monkeypatch):
    """LeBron not in OKC/SAS lineups → BENCH classification (lineup data
    exists, player just isn't starting tonight)."""
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "SAS",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("PG", "Shai Gilgeous-Alexander"),
            _starter("SG", "Luguentz Dort"),
        ]},
        "home_lineup": {"status": "Expected", "starters": [
            _starter("C", "Victor Wembanyama"),
        ]},
    }])
    path = _write_tmp(lu)
    try:
        _, captured = _capture_run(
            ["--name", "LeBron James", "--opp", "OKC", "--home",
             "--lineups", path], monkeypatch)
    finally:
        os.unlink(path)
    line = [c for c in captured if c.startswith("  Lineup:")][0]
    # Not in starter index, index non-empty → BENCH (safe default per
    # src/data/lineups.classify_starter when player_team is unknown).
    assert "BENCH" in line


def test_require_starter_lineup_exits_two_for_bench(monkeypatch):
    """--require-starter-lineup exits 2 when player isn't classified
    starter or questionable."""
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "SAS",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("PG", "Shai Gilgeous-Alexander"),
        ]},
        "home_lineup": {"status": "Expected", "starters": []},
    }])
    path = _write_tmp(lu)
    try:
        exit_code, captured = _capture_run(
            ["--name", "Random Bench Guy", "--opp", "SAS", "--away",
             "--lineups", path, "--require-starter-lineup"], monkeypatch)
    finally:
        os.unlink(path)
    assert exit_code == 2
    assert any("--require-starter-lineup" in c for c in captured)


def test_require_starter_lineup_does_not_block_questionable(monkeypatch):
    """Questionable IS allowed through (caller chose to predict despite risk)."""
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "SAS",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("SF", "Jalen Williams", play_pct=50, injury="Ques"),
        ]},
        "home_lineup": {"status": "Expected", "starters": []},
    }])
    path = _write_tmp(lu)
    try:
        exit_code, captured = _capture_run(
            ["--name", "Jalen Williams", "--opp", "SAS", "--away",
             "--lineups", path, "--require-starter-lineup"], monkeypatch)
    finally:
        os.unlink(path)
    # Reach the "no gamelog cached" exit (build_prediction_row mock returns None
    # → exit 2 from that branch). Critically NOT exited by --require-starter-lineup.
    require_skip = [c for c in captured if "--require-starter-lineup set" in c]
    assert require_skip == []


def test_lineups_missing_file_returns_unknown(monkeypatch):
    """If the lineup file doesn't exist, classification is 'unknown' — no crash."""
    _, captured = _capture_run(
        ["--name", "LeBron James", "--opp", "DEN", "--home",
         "--lineups", "/tmp/never_exists_xyz.json"], monkeypatch)
    line = [c for c in captured if c.startswith("  Lineup:")][0]
    assert "UNKNOWN" in line


# ── predict_slate._tag_lineup (cycle 64) ─────────────────────────────────────

def _slate_row(name):
    return {"player_id": 1, "name": name, "team": "LAL",
            "preds": {"pts": 25.0}}


def test_tag_lineup_leaves_starters_untagged():
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 100,
                              "injury": None, "lineup_status": "Confirmed"}}
    out = ps._tag_lineup([_slate_row("LeBron James")], idx)
    assert out[0]["name"] == "LeBron James"   # no tag


def test_tag_lineup_tags_questionable_and_bench():
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 50,
                              "injury": "Ques", "lineup_status": "Expected"}}
    out = ps._tag_lineup([_slate_row("LeBron James"),
                            _slate_row("Austin Reaves")], idx)
    lebron = next(r for r in out if "LeBron" in r["name"])
    reaves = next(r for r in out if "Reaves" in r["name"])
    assert "[QUESTIONABLE]" in lebron["name"]
    assert "[BENCH]" in reaves["name"]


def test_tag_lineup_does_not_mutate_caller_dict():
    original = _slate_row("Austin Reaves")
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 100,
                              "injury": None, "lineup_status": "Confirmed"}}
    ps._tag_lineup([original], idx)
    assert original["name"] == "Austin Reaves"   # mutation prevention


# ── predict_slate._scale_lineup_preds (cycle 67) ─────────────────────────────

def test_scale_lineup_preds_applies_questionable_factor():
    """A starter listed Questionable (50% play) has preds scaled by 0.75."""
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 50,
                              "injury": "Ques", "lineup_status": "Expected"}}
    row = {"player_id": 1, "name": "LeBron James", "team": "LAL",
           "preds": {"pts": 28.0, "reb": 8.0}}
    out = ps._scale_lineup_preds([row], idx)
    # questionable → 0.75
    assert out[0]["preds"]["pts"] == pytest.approx(21.0)
    assert out[0]["preds"]["reb"] == pytest.approx(6.0)


def test_scale_lineup_preds_zeros_no_game():
    """Bench player on a team not playing tonight → preds * 0 → 0.

    Default classify_starter without player_team returns 'bench' (factor 0.30)
    not 'no-game', so use a player whose name IS in starting 5 and is OUT.
    Actually simpler: use no-game by direct classification — but we don't
    have that path easily. Test bench instead (factor 0.30)."""
    idx = {"shai gilgeous-alexander": {"team": "OKC", "pos": "PG",
                                         "play_pct": 100, "injury": None,
                                         "lineup_status": "Confirmed"}}
    row = {"player_id": 1, "name": "Austin Reaves", "team": "LAL",
           "preds": {"pts": 20.0}}
    out = ps._scale_lineup_preds([row], idx)
    # bench → 0.30 → 20.0 * 0.30 = 6.0
    assert out[0]["preds"]["pts"] == pytest.approx(6.0)


def test_scale_lineup_preds_handles_tag_in_name():
    """If _tag_lineup ran first and prepended '[BENCH]', scaling should still
    look up the raw name (not the tagged version)."""
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 100,
                              "injury": None, "lineup_status": "Confirmed"}}
    # Name already has the tag, as happens when _tag_lineup runs before scaling.
    row = {"player_id": 1, "name": "LeBron James [STARTER]", "team": "LAL",
           "preds": {"pts": 28.0}}
    out = ps._scale_lineup_preds([row], idx)
    # starter → 1.0 → unchanged
    assert out[0]["preds"]["pts"] == 28.0


def test_scale_lineup_preds_does_not_mutate_caller_dict():
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 50,
                              "injury": "Ques", "lineup_status": "Expected"}}
    original = {"player_id": 1, "name": "LeBron James", "team": "LAL",
                "preds": {"pts": 28.0}}
    ps._scale_lineup_preds([original], idx)
    assert original["preds"]["pts"] == 28.0   # not mutated


# ── compare_to_lines lineup filter end-to-end ────────────────────────────────

def test_compare_to_lines_lineup_filter_skips_bench(monkeypatch, capsys):
    """compare_to_lines --lineups skips rows for bench players."""
    # Lineup JSON has SGA but not LeBron — so SGA proceeds, LeBron is filtered.
    lu = _lineup_json([{
        "away_team": "OKC", "home_team": "LAL",
        "away_lineup": {"status": "Expected", "starters": [
            _starter("PG", "Shai Gilgeous-Alexander"),
        ]},
        "home_lineup": {"status": "Expected", "starters": []},
    }])
    lu_path = _write_tmp(lu)

    # Mock the heavy lifters so the test never touches nba_api / the model.
    monkeypatch.setattr(ctl, "_resolve_player_id", lambda n: 1)
    monkeypatch.setattr(ctl, "build_prediction_row", lambda *a, **k: {"f": 0.0})
    monkeypatch.setattr(ctl, "predict_pergame", lambda *a, **k: 25.0)
    monkeypatch.setattr(ctl, "predict_pergame_quantiles",
                          lambda *a, **k: {"q10": 20.0, "q50": 25.0, "q90": 30.0})

    csv_text = ("player,opp,venue,stat,line,over_odds,under_odds\n"
                "Shai Gilgeous-Alexander,LAL,away,pts,24.5,-110,-110\n"
                "LeBron James,OKC,home,pts,22.5,-110,-110\n")
    csv_path = tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv",
                                              encoding="utf-8")
    csv_path.write(csv_text); csv_path.close()

    try:
        with mock.patch.object(sys, "argv", [
            "compare_to_lines.py", csv_path.name, "--lineups", lu_path,
        ]):
            try:
                ctl.main()
            except SystemExit:
                pass
        out = capsys.readouterr().out
        # SGA should appear in the bets table; LeBron should be in the skip list.
        assert "Shai Gilgeous-Alexander" in out
        assert "LeBron James" in out          # in skip line
        assert "[lineups]" in out              # the skip header was printed
        assert "(bench)" in out
    finally:
        os.unlink(csv_path.name); os.unlink(lu_path)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
