"""Focused tests for the paper-only attributed track record."""
import json

from scripts.platformkit.paper_track_record import consolidate, render_summary, summary


def _write(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_consolidates_two_daemons_and_reports_skipped_store(tmp_path):
    m1 = tmp_path / "m1_paper_positions.jsonl"
    pm = tmp_path / "pm_paper_fills.jsonl"
    bad = tmp_path / "ingame_paper_settles.jsonl"
    _write(m1, [{"bet_id": "m1", "ts": "2026-08-01T10:00:00Z", "game_id": "g1",
                 "side": "home", "model_prob": .60, "market_prob": .55,
                 "stake_units": 2, "daemon": "m1_paper", "status": "open"},
                {"bet_id": "m1", "ts": "2026-08-01T12:00:00Z", "market_prob": .50,
                 "daemon": "m1_paper", "status": "won"}])
    _write(pm, [{"bet_id": "pm", "ts": "2026-08-02T10:00:00Z", "market_id": "g2",
                 "side": "away", "model_prob": .40, "market_prob": .45,
                 "units": 1, "strategy": "pm_alpha", "daemon": "pm_paper",
                 "status": "lost"}])
    bad.write_text("not json", encoding="utf-8")
    rows, notes = consolidate([m1, pm, bad])
    assert len(rows) == 2
    assert round(rows.loc[rows.decision_id == "m1", "clv_probability"].item(), 6) == .05
    assert set(rows.strategy) == {"m1_paper", "pm_alpha"}
    stats = summary(rows)
    assert set(stats.n) == {1}
    text = render_summary(stats, notes)
    assert "PAPER ONLY" in text and "INSUFFICIENT" in text
    assert "SKIP unparseable ingame_paper_settles.jsonl" in text
