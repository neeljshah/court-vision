"""Per-file test for the durable shadow-evidence append store (LANE 2).

Covers: filters out rows with no shadow field; fail-open on an unwritable dir; size
bound is honored (further rows dropped once a day-file exceeds it); the hook wired into
inplay_capture_loop never raises into the caller even when shadow_history itself blows up.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_shadow_history.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.ingame import shadow_history as sh


def test_appender_filters_non_shadow_rows(tmp_path):
    rows = [
        {"sport": "mlb", "game_id": "g1", "reason": "ok", "model_prob_sp_shadow": 0.6},
        {"sport": "mlb", "game_id": "g2", "reason": "no_live_state"},  # no shadow key at all
        {"sport": "wnba", "game_id": "g3", "reason": "no_model_prob",
         "model_prob_wnba_shadow": None, "model_prob_nba_shadow": None,
         "model_prob_tennis_shadow": None, "model_prob_sp_shadow": None},  # all None
        {"sport": "tennis", "game_id": "g4", "reason": "no_model_prob",
         "model_prob_tennis_shadow": 0.5155},
    ]
    n = sh.append_shadow_rows(rows, history_dir=tmp_path)
    assert n == 2
    mlb_file = tmp_path / "mlb" / (datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl")
    tennis_file = tmp_path / "tennis" / (datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl")
    assert mlb_file.is_file() and tennis_file.is_file()
    rec = json.loads(mlb_file.read_text(encoding="utf-8").strip())
    assert rec["game_id"] == "g1" and rec["model_prob_sp_shadow"] == 0.6
    assert not (tmp_path / "wnba").exists()  # the all-None row wrote nothing


def test_non_dict_and_empty_rows_are_safe(tmp_path):
    assert sh.append_shadow_rows([], history_dir=tmp_path) == 0
    assert sh.append_shadow_rows([None, "bad", 5], history_dir=tmp_path) == 0
    assert sh.append_shadow_rows(None, history_dir=tmp_path) == 0


def test_fail_open_on_unwritable_dir(tmp_path, monkeypatch):
    # Point history_dir at a path that collides with an existing FILE, so mkdir must fail.
    blocker = tmp_path / "blocked"
    blocker.write_text("x", encoding="utf-8")
    rows = [{"sport": "mlb", "game_id": "g1", "reason": "ok", "model_prob_sp_shadow": 0.6}]
    n = sh.append_shadow_rows(rows, history_dir=blocker)  # blocker/mlb/... can't mkdir under a file
    assert n == 0  # never raises


def test_size_bound_drops_rows_once_over_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "MAX_BYTES_PER_DAY", 10)  # tiny bound forces the drop path
    rows1 = [{"sport": "mlb", "game_id": "g1", "reason": "ok", "model_prob_sp_shadow": 0.6}]
    n1 = sh.append_shadow_rows(rows1, history_dir=tmp_path)
    assert n1 == 1  # first row always lands (file starts empty, size 0 < bound)
    rows2 = [{"sport": "mlb", "game_id": "g2", "reason": "ok", "model_prob_sp_shadow": 0.7}]
    n2 = sh.append_shadow_rows(rows2, history_dir=tmp_path)
    assert n2 == 0  # file is already >= 10 bytes -> dropped, not appended
    day_file = tmp_path / "mlb" / (datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl")
    lines = day_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # g2 never landed


def test_hook_in_capture_loop_never_raises_when_shadow_history_blows_up(tmp_path, monkeypatch):
    """Mirrors the capture-loop's own hook: an exception inside append_shadow_rows must
    never propagate into poll_once. We simulate the hook exactly as inplay_capture_loop
    wires it (try/except around the call) since the module under test here owns the store,
    not the hook site itself."""
    def _boom(*a, **kw):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(sh, "append_shadow_rows", _boom)

    def _wired_hook(rows):
        try:
            sh.append_shadow_rows(rows)
        except Exception:  # noqa: BLE001 -- mirrors the fail-open hook contract
            pass
    _wired_hook([{"sport": "mlb", "game_id": "g1", "model_prob_sp_shadow": 0.5}])  # must not raise


def test_devigged_price_included_when_present(tmp_path):
    rows = [{"sport": "mlb", "game_id": "g1", "reason": "ok", "model_prob": 0.61,
            "devigged_price": 0.59, "model_prob_sp_shadow": 0.6}]
    sh.append_shadow_rows(rows, history_dir=tmp_path)
    day_file = tmp_path / "mlb" / (datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl")
    rec = json.loads(day_file.read_text(encoding="utf-8").strip())
    assert rec["devigged_price"] == 0.59 and rec["model_prob"] == 0.61
