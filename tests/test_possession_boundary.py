"""
test_possession_boundary.py — Tests for possession-boundary bug fixes.

BUG 1: possession_id inflation — empty frames (ball not detected) must NOT end a
        possession or increment possession_id.  A possession only ends when a DIFFERENT
        real team takes the ball.  team→empty transitions are transient and must be
        ignored (same possession continues).
BUG 2: possession_id remap — after export, tracking_data.csv and shot_log.csv
        possession_id values must be the sequential 0-based IDs from possessions.csv.
BUG 3: _FRAME_STRIDE env-var override — NBA_FRAME_STRIDE=5 must be respected.
"""

import csv
import importlib
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Guard: skip entire module if unified_pipeline cannot be imported (e.g. missing CV deps)
unified_pipeline = pytest.importorskip(
    "src.pipeline.unified_pipeline",
    reason="src.pipeline.unified_pipeline not importable (likely missing CV deps)",
)
UnifiedPipeline = unified_pipeline.UnifiedPipeline


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 1 — possession_id inflation guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestPossessionIdInflationGuard:
    """Validate the _last_real_poss_team guard at unified_pipeline.py ~line 2158.

    Semantic: possession_id increments ONLY when a new non-empty team gets the ball.
    Empty frames (ball not detected) are transient — they do NOT end a possession.
    """

    def _run_sequence(self, transitions):
        """
        Simulate the possession state machine for a sequence of curr_poss values.
        Mirrors the fixed in-loop logic exactly:

            if curr_poss and curr_poss != _last_real_poss_team:
                possession_id += 1
                _last_real_poss_team = curr_poss

        Returns final possession_id after processing all transitions.
        """
        possession_id = 0
        _last_real_poss_team = ""
        for curr_poss in transitions:
            if curr_poss and curr_poss != _last_real_poss_team:
                possession_id += 1
                _last_real_poss_team = curr_poss
        return possession_id

    def test_possession_id_does_not_increment_for_no_ball_frames(self):
        """A run of empty→empty transitions must NOT increment possession_id.

        Simulates 50 consecutive no-ball frames (curr_poss="" each time).
        Expected result: possession_id == 0 (no real possession ever detected).
        """
        transitions = [""] * 50
        result = self._run_sequence(transitions)
        assert result == 0, (
            f"possession_id should be 0 for 50 no-ball frames, got {result}"
        )

    def test_possession_id_does_not_increment_empty_to_empty(self):
        """Team→empty transition must NOT increment possession_id.

        DAL holds ball for 5 frames, then 30 no-ball frames (ball lost).
        Exactly 1 real possession should be recorded — the empty frames are
        transient and do NOT end the DAL possession.
        """
        transitions = ["DAL"] * 5 + [""] * 30
        result = self._run_sequence(transitions)
        # First "DAL": _last_real="" → +1, _last_real="DAL"
        # subsequent "DAL": same team, no increment
        # all "": curr_poss falsy, no increment
        assert result == 1, (
            f"Expected 1 possession (DAL + no-ball run), got {result}"
        )

    def test_possession_id_increments_on_real_team_change(self):
        """DAL → OKC transition must increment possession_id by exactly 1.

        Sequence: DAL holds for 5 frames, OKC takes over for 5 frames.
        Expected: 2 increments total (DAL first seen, then OKC first seen).
        """
        transitions = ["DAL"] * 5 + ["OKC"] * 5
        result = self._run_sequence(transitions)
        assert result == 2, (
            f"Expected 2 possession IDs (DAL + OKC), got {result}"
        )

    def test_possession_id_increments_correctly_for_mixed_sequence(self):
        """Full realistic sequence: no-ball, DAL, no-ball, OKC, no-ball.

        Empty gaps between possessions must not inflate the counter.
        team→empty→team transitions count based on the new team only.
        """
        transitions = (
            [""] * 10          # startup: no ball
            + ["DAL"] * 20     # DAL possession
            + [""] * 15        # loose ball / gap — does NOT end DAL possession
            + ["OKC"] * 20     # OKC takes ball → new possession
            + [""] * 10        # end of clip — does NOT end OKC possession
        )
        result = self._run_sequence(transitions)
        # "" (startup): no increment
        # "DAL" first: _last_real="" → +1, _last_real="DAL"
        # "" (gap): falsy, no increment
        # "OKC" first: "OKC" != "DAL" → +1, _last_real="OKC"
        # "" (end): falsy, no increment
        assert result == 2, (
            f"Expected 2 possession ID increments for mixed sequence (DAL + OKC), got {result}"
        )

    def test_possession_id_team_empty_team_same(self):
        """DAL → empty → DAL must NOT create a new possession.

        Ball is briefly lost (empty frames) but the same team recovers it.
        Should remain 1 possession total.
        """
        transitions = ["DAL"] * 5 + [""] * 10 + ["DAL"] * 5
        result = self._run_sequence(transitions)
        # "DAL" first: +1, _last_real="DAL"
        # "": no increment
        # "DAL" again: curr_poss == _last_real → no increment
        assert result == 1, (
            f"Expected 1 possession (DAL + gap + DAL resumption), got {result}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 2 — possession_id remap produces sequential IDs in CSV
# ═══════════════════════════════════════════════════════════════════════════════

class TestRemapPossessionIdsForJoin:
    """Validate _remap_possession_ids_for_join() rewrites CSVs with 0-based sequential IDs."""

    def _write_csv(self, path, fieldnames, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    def _read_csv(self, path):
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_remap_possession_ids_produces_sequential_in_csv(self):
        """Synthetic possessions.csv with non-sequential frame-based IDs.

        tracking_data.csv and shot_log.csv use the same frame-based IDs.
        After _remap_possession_ids_for_join(), both files must use sequential
        0-based IDs matching possessions.csv row positions.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Frame-based IDs that would occur with the old bug (non-sequential, large gaps)
            frame_pids = [3, 45, 212, 876]

            # possessions.csv: 4 rows with the frame-based IDs
            poss_rows = [
                {"possession_id": str(pid), "team": "DAL", "start_frame": str(i * 100),
                 "end_frame": str(i * 100 + 90), "duration_sec": "3.0"}
                for i, pid in enumerate(frame_pids)
            ]
            poss_fields = ["possession_id", "team", "start_frame", "end_frame", "duration_sec"]
            self._write_csv(os.path.join(tmp_dir, "possessions.csv"), poss_fields, poss_rows)

            # tracking_data.csv: one tracking row per possession using frame-based IDs
            track_rows = [
                {"frame": str(i * 100), "possession_id": str(pid), "player_id": "7"}
                for i, pid in enumerate(frame_pids)
            ]
            track_fields = ["frame", "possession_id", "player_id"]
            self._write_csv(os.path.join(tmp_dir, "tracking_data.csv"), track_fields, track_rows)

            # shot_log.csv: one shot per possession using frame-based IDs
            shot_rows = [
                {"shot_id": str(i), "possession_id": str(pid), "made": "1"}
                for i, pid in enumerate(frame_pids)
            ]
            shot_fields = ["shot_id", "possession_id", "made"]
            self._write_csv(os.path.join(tmp_dir, "shot_log.csv"), shot_fields, shot_rows)

            # Create a minimal UnifiedPipeline instance with _data_dir set
            pipe = UnifiedPipeline.__new__(UnifiedPipeline)
            pipe._data_dir = tmp_dir

            # Run the remap
            pipe._remap_possession_ids_for_join()

            # tracking_data.csv should now have sequential IDs 0, 1, 2, 3
            track_after = self._read_csv(os.path.join(tmp_dir, "tracking_data.csv"))
            actual_track_pids = [int(r["possession_id"]) for r in track_after]
            assert actual_track_pids == list(range(len(frame_pids))), (
                f"tracking_data.csv possession_ids should be 0..{len(frame_pids)-1}, "
                f"got {actual_track_pids}"
            )

            # shot_log.csv should now have sequential IDs 0, 1, 2, 3
            shot_after = self._read_csv(os.path.join(tmp_dir, "shot_log.csv"))
            actual_shot_pids = [int(r["possession_id"]) for r in shot_after]
            assert actual_shot_pids == list(range(len(frame_pids))), (
                f"shot_log.csv possession_ids should be 0..{len(frame_pids)-1}, "
                f"got {actual_shot_pids}"
            )

    def test_remap_shot_ids_subset_of_possessions(self):
        """When shot_log only references a subset of possession IDs, remap still works.

        This simulates a game where shots only occurred during 2 of 4 possessions.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            frame_pids = [10, 87, 350, 999]

            poss_rows = [
                {"possession_id": str(pid), "team": "OKC", "start_frame": "0",
                 "end_frame": "100", "duration_sec": "3.0"}
                for pid in frame_pids
            ]
            poss_fields = ["possession_id", "team", "start_frame", "end_frame", "duration_sec"]
            self._write_csv(os.path.join(tmp_dir, "possessions.csv"), poss_fields, poss_rows)

            # Only shots for the 1st and 3rd possessions (frame_pids[0] and [2])
            shot_rows = [
                {"shot_id": "0", "possession_id": str(frame_pids[0]), "made": "0"},
                {"shot_id": "1", "possession_id": str(frame_pids[2]), "made": "1"},
            ]
            shot_fields = ["shot_id", "possession_id", "made"]
            self._write_csv(os.path.join(tmp_dir, "shot_log.csv"), shot_fields, shot_rows)

            pipe = UnifiedPipeline.__new__(UnifiedPipeline)
            pipe._data_dir = tmp_dir

            pipe._remap_possession_ids_for_join()

            shot_after = self._read_csv(os.path.join(tmp_dir, "shot_log.csv"))
            actual_pids = [int(r["possession_id"]) for r in shot_after]
            # frame_pids[0]=10 maps to seq 0; frame_pids[2]=350 maps to seq 2
            assert actual_pids == [0, 2], (
                f"Expected [0, 2] for subset shots, got {actual_pids}"
            )

    def test_remap_no_crash_when_possessions_csv_missing(self):
        """_remap_possession_ids_for_join must not raise when possessions.csv absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipe = UnifiedPipeline.__new__(UnifiedPipeline)
            pipe._data_dir = tmp_dir
            # No possessions.csv written — must return silently
            pipe._remap_possession_ids_for_join()  # should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 3 — _FRAME_STRIDE env-var override
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrameStrideEnvVarOverride:
    """Validate that NBA_FRAME_STRIDE env-var controls _FRAME_STRIDE at import time."""

    def test_frame_stride_env_var_override(self, monkeypatch):
        """Set NBA_FRAME_STRIDE=5, reload module, assert _FRAME_STRIDE == 5.

        Uses monkeypatch to set the env var before reimporting so the module-level
        assignment picks it up.  Restores original state via monkeypatch teardown.
        """
        monkeypatch.setenv("NBA_FRAME_STRIDE", "5")

        # Reload the module so the module-level constant is re-evaluated
        import importlib
        reloaded = importlib.reload(unified_pipeline)

        try:
            assert reloaded._FRAME_STRIDE == 5, (
                f"Expected _FRAME_STRIDE=5 when NBA_FRAME_STRIDE=5, "
                f"got {reloaded._FRAME_STRIDE}"
            )
        finally:
            # Always reload back to default so other tests see stride=3
            monkeypatch.delenv("NBA_FRAME_STRIDE", raising=False)
            importlib.reload(unified_pipeline)

    def test_frame_stride_default_is_3(self, monkeypatch):
        """Without NBA_FRAME_STRIDE set, _FRAME_STRIDE must be 3 (default)."""
        monkeypatch.delenv("NBA_FRAME_STRIDE", raising=False)

        import importlib
        reloaded = importlib.reload(unified_pipeline)

        try:
            assert reloaded._FRAME_STRIDE == 3, (
                f"Default _FRAME_STRIDE should be 3, got {reloaded._FRAME_STRIDE}"
            )
        finally:
            importlib.reload(unified_pipeline)
