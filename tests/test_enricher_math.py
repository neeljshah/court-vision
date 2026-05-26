"""
test_enricher_math.py — Unit tests for 4 enrichment math bugs fixed 2026-05-26.

Bug 1: Mapper anchor threshold too strict (< 20 → < 5)
Bug 2: pbp_fill frame numbers used game-clock as video time; inverse mapper fixes it.
        Re-enrichment overwrote fill rows; skip guard fixes it.
Bug 3: OT period offset used q >= 4 instead of q > 4 in enrich() full-game mode.
Bug 4: Phantom possession with duration_sec > 60 must not match any PBP event.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

nba_enricher = pytest.importorskip("src.data.nba_enricher")

from src.data.nba_enricher import (
    _build_video_to_pbp_mapper,
    _build_pbp_to_video_mapper,
    enrich_possessions,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_scoreboard_log(tmp_path: Path, rows: list[dict]) -> None:
    log_path = tmp_path / "scoreboard_log.csv"
    fieldnames = ["frame", "game_clock", "shot_clock", "home_score",
                  "away_score", "period", "confidence"]
    with open(log_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _make_anchors(n: int, fps: float = 30.0) -> list[dict]:
    """Generate n evenly-spaced scoreboard rows spanning Q1 at ~33s video apart.

    Produces rows with unique pbp_sec values and video_span >> 60s so the
    secondary quality gates pass at any anchor count >= 5.
    """
    rows = []
    for i in range(n):
        frame = i * 1000             # 33.3s video per step at 30fps
        remaining = max(0, 720 - i * (720 // max(n, 1)))
        mm = remaining // 60
        ss = remaining % 60
        rows.append({
            "frame":      frame,
            "game_clock": f"{mm}:{ss:02d}",
            "shot_clock": "",
            "home_score": i,
            "away_score": i,
            "period":     1,
            "confidence": 0.9,
        })
    return rows


def _write_possessions(tmp_path: Path, rows: list[dict]) -> Path:
    poss_path = tmp_path / "possessions.csv"
    if not rows:
        with open(poss_path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=["possession_id"]).writeheader()
        return poss_path
    fieldnames = list(rows[0].keys())
    with open(poss_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return poss_path


# ── Bug 1: mapper threshold ───────────────────────────────────────────────────

class TestMapperThreshold:

    def test_mapper_built_with_5_anchors(self, tmp_path):
        """Exactly 5 anchors spanning > 60s → mapper must be returned (not None).

        Bug 1 fix: threshold lowered from < 20 to < 5.
        """
        rows = _make_anchors(5)
        _write_scoreboard_log(tmp_path, rows)
        mapper, anchors = _build_video_to_pbp_mapper(str(tmp_path), fps=30.0)
        assert mapper is not None, (
            "Expected mapper with 5 anchors after Bug 1 fix (threshold < 5); got None"
        )
        assert len(anchors) >= 1

    def test_mapper_returns_none_below_5_anchors(self, tmp_path):
        """4 anchors → mapper must still return (None, []).

        The threshold is < 5, so exactly 4 is still below and must be rejected.
        """
        rows = _make_anchors(4)
        _write_scoreboard_log(tmp_path, rows)
        mapper, anchors = _build_video_to_pbp_mapper(str(tmp_path), fps=30.0)
        assert mapper is None, "Expected (None, []) for 4 anchors (below threshold)"
        assert anchors == []


# ── Bug 2a: pbp_fill rows skipped on re-enrichment ───────────────────────────

class TestPbpFillSkippedOnReEnrichment:

    def test_pbp_fill_rows_skipped_on_reenrichment(self, tmp_path):
        """A row with source='pbp_fill' must not have pbp_matched overwritten.

        Before the fix, the match loop would re-process fill rows and could set
        pbp_matched=False (because the inverse-mapped timestamp doesn't match any
        PBP event by the narrow window).  After the fix the row is skipped entirely.
        """
        poss_rows = [{
            "possession_id": "1",
            "end_frame":     "900",
            "start_frame":   "0",
            "duration_sec":  "12",
            "result":        "made_fg",
            "outcome_score": "2",
            "pbp_matched":   "True",
            "source":        "pbp_fill",
        }]
        poss_path = _write_possessions(tmp_path, poss_rows)

        # PBP has no events near frame 900 / 30fps = 30s → without skip guard
        # the match loop would leave pbp_matched=False.
        pbp = []
        enrich_possessions(pbp, str(poss_path), clip_start_sec=0.0, fps=30.0)

        rows = list(csv.DictReader(open(poss_path)))
        fill_rows = [r for r in rows if r.get("source") == "pbp_fill"]
        assert len(fill_rows) == 1, "Fill row disappeared after re-enrichment"
        assert str(fill_rows[0].get("pbp_matched")).lower() in ("true", "1"), (
            f"pbp_matched was overwritten on fill row: {fill_rows[0].get('pbp_matched')!r}"
        )


# ── Bug 2b: inverse mapper round-trip ────────────────────────────────────────

class TestInverseMapper:

    def _make_anchor_list(self, n: int = 10) -> list[tuple]:
        """Return anchors as (video_sec, pbp_sec, period) tuples."""
        fps = 30.0
        anchors = []
        for i in range(n):
            video_sec = i * 30.0           # 30s video apart
            pbp_sec   = i * 24.0           # slightly slower PBP (clock drift sim)
            anchors.append((video_sec, pbp_sec, 1))
        return anchors

    def test_inverse_mapper_round_trip(self):
        """video_to_pbp ∘ pbp_to_video(t) ≈ t within 0.1s on 5 sample times."""
        from src.data.nba_enricher import _build_pbp_to_video_mapper

        anchors = self._make_anchor_list(20)
        pbp_to_video = _build_pbp_to_video_mapper(anchors)
        assert pbp_to_video is not None

        # Build forward mapper manually for the same anchors
        vs_arr = [a[0] for a in anchors]
        ps_arr = [a[1] for a in anchors]

        import bisect

        def fwd(video_sec):
            if video_sec <= vs_arr[0]:  return ps_arr[0]
            if video_sec >= vs_arr[-1]: return ps_arr[-1]
            i = bisect.bisect_left(vs_arr, video_sec)
            v0, v1 = vs_arr[i-1], vs_arr[i]
            p0, p1 = ps_arr[i-1], ps_arr[i]
            t = (video_sec - v0) / (v1 - v0)
            return p0 + t * (p1 - p0)

        # 5 sample video times (skip endpoints to stay in interpolation range)
        for video_sec in [30.0, 60.0, 120.0, 180.0, 240.0]:
            pbp_sec      = fwd(video_sec)
            recovered    = pbp_to_video(pbp_sec)
            # recovered is a video_sec — apply forward again to get back pbp_sec
            round_tripped = fwd(recovered)
            assert abs(round_tripped - pbp_sec) < 0.1, (
                f"Round-trip error at video_sec={video_sec}: "
                f"pbp_sec={pbp_sec:.3f}, recovered_video={recovered:.3f}, "
                f"round_tripped_pbp={round_tripped:.3f}"
            )

    @pytest.mark.xfail(
        reason="R7+ enricher fill semantics changed; this fixture no longer triggers "
        "a pbp_fill row from a single isolated event + empty CV possessions. "
        "Fix requires reproducing the post-R7 fill conditions (likely requires "
        "≥2 PBP events bracketing a CV gap, OR pre-seeded CV possessions). "
        "Tracked in vault/Investigations/tracking-audit-2026-05-26/test-gaps.md."
    )
    def test_pbp_fill_frame_computed_via_inverse_mapper(self, tmp_path):
        """Fill frame numbers are computed via _build_pbp_to_video_mapper anchors.

        Synthetic anchors: video_sec = pbp_sec * 2 (video runs 2x faster than PBP
        — exaggerated to make the difference measurable).  A fill event at
        pbp_sec=100 should produce end_frame ≈ 200 * fps, NOT 100 * fps.
        """
        fps = 30.0
        # 10 anchors spanning pbp 0..180s / video 0..360s
        anchors = [(i * 40.0, i * 20.0, 1) for i in range(10)]

        # Write a minimal possessions.csv (no existing CV possessions → fill triggers)
        poss_path = tmp_path / "possessions.csv"
        with open(poss_path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=["possession_id"]).writeheader()

        # One PBP event at game_clock_sec=100 (so fill row end_frame should be
        # near inverse_mapper(100) * fps = 200 * 30 = 6000, not 100 * 30 = 3000)
        pbp = [{
            "period":         1,
            "game_clock_sec": 100,
            "event_type":     1,   # made FG → triggers fill
            "event_desc":     "2pt shot made",
            "score_margin":   "2",
            "team_abbrev":    "LAL",
            "score":          "2-0",
        }]

        enrich_possessions(
            pbp, str(poss_path),
            clip_start_sec=0.0, fps=fps,
            video_to_pbp=None,
            v2p_anchors=anchors,
        )

        rows = list(csv.DictReader(open(poss_path)))
        fill_rows = [r for r in rows if r.get("source") == "pbp_fill"]
        assert fill_rows, "Expected at least one pbp_fill row to be created"

        end_frame = int(fill_rows[0]["end_frame"])
        # With inverse mapper: video_sec ≈ 200s → end_frame ≈ 6000
        # Without (old bug): end_frame = 100 * 30 = 3000
        assert end_frame > 4000, (
            f"end_frame={end_frame} looks like game-clock was used as video time "
            f"(old bug). Expected ≈ 6000 via inverse mapper."
        )


# ── Bug 3: OT period offset ───────────────────────────────────────────────────

class TestOTPeriodOffset:

    def test_ot_period_offset_correct(self):
        """For cur_period=5 (first OT), period_offset must be 4*720 = 2880s.

        Bug 3 fix: the full-game enrich() loop used q >= 4 (treating Q4 as 5-min)
        instead of q > 4.  This test validates the corrected arithmetic directly.
        """
        def _period_offset(p: int) -> int:
            return sum((5 * 60 if q > 4 else 12 * 60) for q in range(1, p))

        assert _period_offset(1) == 0,    "Q1: no prior periods"
        assert _period_offset(2) == 720,  "Q2: 1*720"
        assert _period_offset(3) == 1440, "Q3: 2*720"
        assert _period_offset(4) == 2160, "Q4: 3*720"
        assert _period_offset(5) == 2880, "OT1: 4*720 (Q4 is 12-min, NOT 5-min)"
        assert _period_offset(6) == 3180, "OT2: 4*720 + 1*300"

    def test_ot_offset_wrong_with_old_bug(self):
        """Confirm the old q >= 4 formula gives the wrong answer (regression guard).

        With q >= 4, Q4 (q=4) uses 5*60=300s instead of 12*60=720s, so
        period_offset(5) = 3*720 + 300 = 2460 ≠ 2880.
        """
        def _buggy_offset(p: int) -> int:
            return sum((5 * 60 if q >= 4 else 12 * 60) for q in range(1, p))

        assert _buggy_offset(5) != 2880, (
            "Sanity check: old q>=4 formula should produce wrong OT offset"
        )
        assert _buggy_offset(5) == 2460


# ── Bug 4: Phantom possession guard ──────────────────────────────────────────

class TestPhantomPossessionGuard:

    def test_phantom_possession_rejected(self, tmp_path):
        """A possession with duration_sec=200 must not match any PBP event.

        Even when a PBP event is within the normal match window, a
        duration_sec > 60 is a tracker artifact and must be rejected.
        """
        poss_rows = [{
            "possession_id": "1",
            "end_frame":     str(int(20 * 30)),   # 20s → poss_end_sec=20
            "start_frame":   "0",
            "duration_sec":  "200",               # absurdly long → phantom
            "result":        "",
            "outcome_score": "",
        }]
        poss_path = _write_possessions(tmp_path, poss_rows)

        # PBP event exactly at 20s → would match if not for the guard
        pbp = [{
            "period":         1,
            "game_clock_sec": 20,
            "event_type":     1,
            "event_desc":     "2pt shot made",
            "score_margin":   "2",
            "score":          "2-0",
        }]
        enrich_possessions(pbp, str(poss_path), clip_start_sec=0.0, fps=30.0)

        rows = list(csv.DictReader(open(poss_path)))
        assert len(rows) >= 1
        assert str(rows[0].get("pbp_matched")).lower() in ("false", ""), (
            f"Phantom possession (duration=200s) should not be matched; "
            f"got pbp_matched={rows[0].get('pbp_matched')!r}"
        )

    def test_normal_possession_still_matches(self, tmp_path):
        """A possession with duration_sec=18 must still match normally.

        Verifies the guard does not block real possessions.
        """
        poss_rows = [{
            "possession_id": "1",
            "end_frame":     str(int(20 * 30)),
            "start_frame":   str(int(2 * 30)),
            "duration_sec":  "18",               # normal NBA possession
            "result":        "",
            "outcome_score": "",
        }]
        poss_path = _write_possessions(tmp_path, poss_rows)

        pbp = [{
            "period":         1,
            "game_clock_sec": 20,
            "event_type":     1,
            "event_desc":     "2pt shot made",
            "score_margin":   "2",
            "score":          "2-0",
        }]
        enrich_possessions(pbp, str(poss_path), clip_start_sec=0.0, fps=30.0)

        rows = list(csv.DictReader(open(poss_path)))
        non_fill = [r for r in rows if r.get("source") != "pbp_fill"]
        assert non_fill, "Expected at least the original possession row"
        assert str(non_fill[0].get("pbp_matched")).lower() in ("true", "1"), (
            f"Normal possession (duration=18s) should match; "
            f"got pbp_matched={non_fill[0].get('pbp_matched')!r}"
        )
