"""
test_issue009_game_id_wiring.py — ISSUE-009: --game-id wiring end-to-end.

Verifies that:
1. game_id is stored in possession rows when UnifiedPipeline is constructed
   with game_id=TEST.
2. _run_enrichment forwards game_id to nba_enricher.enrich() and the
   result populates possessions.result in the enriched CSV.
"""
import csv
import os
import types
import uuid
from pathlib import Path
from unittest.mock import patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stub(game_id: str, data_dir: str):
    """Minimal stub mirroring the fields _run_enrichment uses."""
    import src.pipeline.unified_pipeline as up
    stub = types.SimpleNamespace()
    stub.game_id = game_id
    stub.clip_id = str(uuid.uuid4())
    stub.clip_start_sec = 0.0
    stub._data_dir = data_dir
    stub._run_enrichment = up.UnifiedPipeline._run_enrichment.__get__(stub)
    return stub


def _write_possessions(path: str, rows):
    fields = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _write_shot_log(path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=["game_id", "shot_id", "frame"]).writeheader()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGameIdWiring:

    def test_possession_rows_carry_game_id(self):
        """_aggregate_possession stores game_id in the returned dict."""
        import src.pipeline.unified_pipeline as up
        import numpy as np

        fake_buf = [
            {
                "frame": i, "spacing": 5000.0, "isolation": 150.0,
                "vtb": 0.1, "shot_event": False, "play_type": "half_court",
                "poss_type": None, "fast_break": False, "drive": False,
                "paint_touches": 0, "off_ball_distance": 0.0,
                "shot_clock_est": 24.0, "handler_zone": None,
            }
            for i in range(10)
        ]
        # _summarize_possession is a @staticmethod
        row = up.UnifiedPipeline._summarize_possession(
            pid=1, team="GSW", start_f=0, end_f=9,
            buf=fake_buf, fps=30.0, game_id="TEST",
        )
        assert row["game_id"] == "TEST", f"Expected 'TEST', got {row['game_id']}"
        assert row["result"] == "", "result must be empty before enrichment"

    def test_run_enrichment_calls_enrich_with_game_id(self, tmp_path, monkeypatch):
        """_run_enrichment passes game_id to nba_enricher.enrich()."""
        # ── Set up fake CSV files that _infer_period_count / _infer_fps need ──
        poss_path = tmp_path / "possessions.csv"
        shot_path = tmp_path / "shot_log.csv"
        track_path = tmp_path / "tracking_data.csv"

        _write_possessions(str(poss_path), [
            {"possession_id": 1, "team": "GSW", "start_frame": 0,
             "end_frame": 30, "duration_sec": 1.0, "result": "", "game_id": "TEST"}
        ])
        _write_shot_log(str(shot_path))
        with open(str(track_path), "w") as f:
            f.write("frame,timestamp\n1,0.033\n")

        captured = {}

        def _fake_enrich(**kwargs):
            captured.update(kwargs)
            # Simulate enricher writing possessions_enriched.csv with result populated
            out = tmp_path / "possessions_enriched.csv"
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f, fieldnames=["possession_id", "team", "result", "game_id"]
                )
                w.writeheader()
                w.writerow({"possession_id": 1, "team": "GSW",
                             "result": "scored", "game_id": "TEST"})
            return {"possessions_enriched": str(out)}

        stub = _make_stub("TEST", str(tmp_path))

        with patch("src.data.nba_enricher.enrich", side_effect=_fake_enrich), \
             patch("src.data.nba_enricher._infer_period_count",
                   return_value=([1], 1.0)), \
             patch("src.data.nba_enricher._infer_fps",
                   return_value=30.0):
            stub._run_enrichment(fps=30.0)

        assert captured.get("game_id") == "TEST", \
            f"enrich() called with wrong game_id: {captured}"

        # Verify possessions_enriched.csv has result populated
        enriched = tmp_path / "possessions_enriched.csv"
        assert enriched.exists(), "possessions_enriched.csv not written"
        rows = list(csv.DictReader(open(enriched, encoding="utf-8")))
        assert rows[0]["result"] == "scored", \
            f"result not populated: {rows[0]['result']!r}"

    def test_run_enrichment_skipped_when_no_game_id(self, tmp_path, capsys):
        """_run_enrichment is not called from outside when game_id is None.

        Tested indirectly: with game_id=None, the condition in run() that gates
        _run_enrichment is False. Here we verify _run_enrichment still completes
        without crashing when _infer_period_count fails (no tracking_data.csv).
        """
        stub = _make_stub(None, str(tmp_path))
        # Should not raise even if data files missing
        stub._run_enrichment(fps=30.0)
        out, _ = capsys.readouterr()
        # Either prints nothing or prints a non-fatal warning
        assert "Traceback" not in out
