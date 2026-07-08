"""Per-file tests for scripts.platformkit.ingame.kbo_baseout_accrual.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_baseout_accrual.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame.kbo_baseout_accrual import (
    accrue_and_write, accrue_game_states, load_state_rows, parse_kbo_baseout,
    run_accrue_all,
)


def _row(inning, half, outs, base_state, sh, sa, ts):
    return {"game_id": "g1", "inning": inning, "half": half, "outs": outs,
            "base_state": base_state, "score_home": sh, "score_away": sa,
            "count": "0-0", "fetch_ts": ts}


# ---------------------------------------------------------------------------
# parse_kbo_baseout -- ports MLB's RE24 table onto KBO's boolean shape
# ---------------------------------------------------------------------------

def test_parse_kbo_baseout_bases_empty_matches_mlb_re24():
    out = parse_kbo_baseout({"outs": 0, "base1": False, "base2": False, "base3": False})
    assert out["base_state"] == 0
    assert out["base_out_state"] == 0
    assert out["run_expectancy"] == 0.481  # published RE24 bases-empty-0-out constant


def test_parse_kbo_baseout_bases_loaded_one_out():
    out = parse_kbo_baseout({"outs": 1, "base1": True, "base2": True, "base3": True})
    assert out["base_label"] == "123"
    assert out["base_out_state"] == 7 * 3 + 1
    assert out["run_expectancy"] == 1.541


def test_parse_kbo_baseout_three_outs_is_not_inplay():
    assert parse_kbo_baseout({"outs": 3, "base1": False, "base2": False, "base3": False}) is None


def test_parse_kbo_baseout_missing_dict_is_none():
    assert parse_kbo_baseout(None) is None
    assert parse_kbo_baseout({}) is None


# ---------------------------------------------------------------------------
# accrue_game_states -- segment collapse over a real multi-state sequence
# ---------------------------------------------------------------------------

def test_accrue_collapses_repeated_ticks_into_segments():
    rows = [
        _row(1, "top", 0, "---", 0, 0, "t1"),
        _row(1, "top", 0, "---", 0, 0, "t2"),   # same state, repeated poll
        _row(1, "top", 1, "1--", 0, 0, "t3"),   # single -> runner reaches 1st
        _row(1, "top", 2, "12-", 0, 0, "t4"),   # another single
        _row(1, "top", 2, "12-", 0, 0, "t5"),   # repeated poll again
    ]
    summary = accrue_game_states(rows)
    assert summary["n_ticks_total"] == 5
    assert summary["n_ticks_excluded"] == 0
    assert summary["n_segments"] == 3
    assert summary["segments"][0]["n_ticks"] == 2
    assert summary["segments"][0]["base_label"] == "---"
    assert summary["segments"][1]["n_ticks"] == 1
    assert summary["segments"][1]["base_label"] == "1--"
    assert summary["segments"][2]["n_ticks"] == 2
    assert summary["segments"][2]["base_label"] == "12-"
    assert summary["segments"][2]["run_expectancy"] == 0.429  # RE24[12-][2 outs]


def test_accrue_excludes_end_of_game_outs3_ticks_honestly():
    """Matches the real on-disk corpus this wave: a completed game's frozen
    final relay tick reports outs=3 -- not a valid in-play state, so it must
    be EXCLUDED, never silently coerced into a fake segment."""
    rows = [_row(9, "top", 3, "1--", 10, 2, "t1") for _ in range(5)]
    summary = accrue_game_states(rows)
    assert summary["n_ticks_total"] == 5
    assert summary["n_ticks_excluded"] == 5
    assert summary["n_segments"] == 0


def test_accrue_empty_input():
    summary = accrue_game_states([])
    assert summary == {"n_ticks_total": 0, "n_ticks_excluded": 0, "n_segments": 0, "segments": []}


# ---------------------------------------------------------------------------
# disk round trip -- load_state_rows / accrue_and_write / run_accrue_all
# ---------------------------------------------------------------------------

def test_load_state_rows_missing_file_is_empty(tmp_path):
    assert load_state_rows("nope", state_dir=tmp_path) == []


def test_accrue_and_write_round_trips(tmp_path):
    state_dir = tmp_path / "state"
    out_dir = tmp_path / "out"
    state_dir.mkdir()
    with (state_dir / "g1.jsonl").open("w", encoding="utf-8") as fh:
        for r in [_row(3, "bottom", 0, "-2-", 1, 0, "t1"), _row(3, "bottom", 1, "-2-", 1, 0, "t2")]:
            fh.write(json.dumps(r) + "\n")

    summary = accrue_and_write("g1", state_dir=state_dir, out_dir=out_dir)
    assert summary["game_id"] == "g1"
    assert summary["n_segments"] == 2
    written = json.loads((out_dir / "g1.json").read_text(encoding="utf-8"))
    assert written["n_segments"] == 2

    totals = run_accrue_all(state_dir=state_dir, out_dir=out_dir)
    assert totals == {"n_games": 1, "n_segments_total": 2}


def test_accrue_and_write_no_rows_returns_none(tmp_path):
    assert accrue_and_write("nope", state_dir=tmp_path, out_dir=tmp_path) is None
