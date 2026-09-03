"""Per-file S186 reproduction for append-only in-game cycle history."""
from __future__ import annotations

import json

from scripts.platformkit.ingame import inplay_capture_loop as loop


def test_30_ticks_keep_cycle_one_failure_reason_readable(tmp_path, monkeypatch):
    """Every driven offline cycle remains readable after the final heartbeat overwrite."""
    monkeypatch.setattr(loop._ls, "live_states", lambda sport: [])

    def fetch(sport):
        return [
            {"sport": sport, "game_id": "KXMLBGAME-26SEP031200AWYHOM",
             "market_type": "moneyline", "side": "HOM", "prob": 0.55},
            {"sport": sport, "game_id": "KXMLBGAME-26SEP031200AWYHOM",
             "market_type": "moneyline", "side": "AWY", "prob": 0.47},
        ]

    ticks = loop.serve_forever(
        max_ticks=30, clock=lambda seconds: None, sports=["mlb"],
        live_state_fn=lambda sport, game_id: None, model_fn=lambda sport, state: None,
        inplay_fetch_fn=fetch, finals_fn=lambda sport: [], grade_dir=tmp_path / "grade",
        ledger_path=tmp_path / "ledger.jsonl", heartbeat_path=tmp_path / "heartbeat.json",
    )

    files = list((tmp_path / "ingame_cycle_history").glob("*.jsonl"))
    assert ticks == 30 and len(files) == 1
    rows = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    required = {"ts", "n_live", "n_pairs", "n_bets", "n_requests_total", "n_429_total",
                "cycle_duration_sec", "grade_write_fail_by_reason"}
    assert len(rows) == 30 and all(required <= set(row) for row in rows)
    assert rows[0]["grade_write_fail_by_reason"] == {"no_live_state": 1}
    assert rows[-1]["grade_write_fail_by_reason"] == {"no_live_state": 1}
