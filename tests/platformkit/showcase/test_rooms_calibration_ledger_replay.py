"""Tests for showcase rooms: calibration, ledger, replay. Run per-file only:
python -m pytest tests/platformkit/showcase/test_rooms_calibration_ledger_replay.py -q
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.platformkit.showcase.lint_bundle import lint_bundle
from scripts.platformkit.showcase.rooms import calibration, ledger, replay


def test_calibration_build_carries_honesty_framing_and_verdicts():
    result = calibration.build()
    assert result.get("status") != "unavailable", result
    per_sport = result["per_sport"]
    assert per_sport, "expected at least one sport row"
    for row in per_sport:
        assert row["label"] == "MEASURED"
        assert row["framing"], "honesty_note must be carried verbatim"
        assert row["receipt"]["label"] == "MEASURED"
        assert row["receipt"]["artifact"]

    crps = result.get("crps")
    if crps:
        for entry in crps.values():
            assert entry["label"], "crps entry must carry the source file's own verdict"
            assert entry["receipt"]["label"] == entry["label"]


def test_ledger_build_has_no_banned_tokens_or_bet_id():
    result = ledger.build()
    assert result.get("status") != "unavailable", result
    paper = result["paper"]
    assert isinstance(paper["n_positions"], int) and paper["n_positions"] > 0
    assert paper["framing"] == "CLV is the yardstick; measurement infrastructure, not an edge claim."
    assert "receipt" in result

    dumped = json.dumps(result)
    assert "bet_id" not in dumped

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ledger.json"
        out.write_text(dumped, encoding="utf-8")
        violations = lint_bundle(Path(tmp))
        token_violations = [v for v in violations if "banned token" in v or "banned retracted" in v]
        assert not token_violations, token_violations


def test_replay_build_returns_index_games_or_unavailable():
    result = replay.build()
    if result.get("status") == "unavailable":
        assert result["reason"]
        return

    assert "index" in result and "games" in result
    game_ids = result["index"]["game_ids"]
    assert game_ids
    assert set(game_ids) == set(result["games"])

    for game_id, game in result["games"].items():
        ticks = game["ticks"]
        assert ticks, f"{game_id} has no ticks"
        assert len(ticks) <= 500
        prev_t = None
        for tick in ticks:
            if prev_t is not None:
                assert tick["t"] >= prev_t, "ticks must be monotone in t"
            prev_t = tick["t"]
            assert 0.0 <= tick["prob_market"] <= 1.0
        assert game["game"]["sport"] == "mlb"
        assert game["receipt"]["artifact"]
