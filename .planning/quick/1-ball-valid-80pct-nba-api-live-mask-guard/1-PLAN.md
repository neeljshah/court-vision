---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - src/tracking/ball_detect_track.py
  - src/pipeline/unified_pipeline.py
  - src/data/nba_enricher.py
  - _bench_run.py
  - tests/test_hardening.py
autonomous: true
requirements: [BALL-VALID-80PCT]

must_haves:
  truths:
    - "Tests in test_hardening.py and test_phase2.py remain green after all changes"
    - "Guard 2 skip for fresh Hough detections is in place (not _bbox_from_hough check in elif)"
    - "build_live_mask() exists in nba_enricher.py and returns {frame_idx: 'live'|'dead_ball'|'unknown'}"
    - "_bench_run.py default --frames is 3600"
    - "Vision-based non-live fallback fires when _sc_ever_seen is False and ball absent 20+ frames with <8 persons"
    - "_bench_run.py reports ball_valid_live and ball_valid_dead as separate metrics when game_id is provided"
  artifacts:
    - path: "src/data/nba_enricher.py"
      provides: "build_live_mask() function"
      contains: "def build_live_mask"
    - path: "_bench_run.py"
      provides: "live/dead ball_valid split metrics + 3600 default"
      contains: "ball_valid_live"
    - path: "tests/test_hardening.py"
      provides: "tests for build_live_mask and vision fallback"
      contains: "test_build_live_mask"
  key_links:
    - from: "_bench_run.py"
      to: "src/data/nba_enricher.build_live_mask"
      via: "evaluate_layers() calls build_live_mask when game_id present"
    - from: "src/pipeline/unified_pipeline.py"
      to: "ball_detect_track._bbox_from_hough"
      via: "Guard 2 elif condition already has not _bbox_from_hough"
---

<objective>
Push ball_valid to 80%+ across all clips by: committing in-flight guard fixes (Guard 2/3), adding NBA API live-mask to separate live vs dead-ball ball_valid metrics, extending bench to 3600 frames, adding a vision-based non-live fallback, and validating shot enrichment works end-to-end.

Purpose: ball_valid_pct is the primary quality signal for the CV tracker. Dead-ball frames (replays, halftime) artificially suppress it; splitting live vs dead gives an honest signal. Guard 2 currently fires on valid Hough re-detections during bos_mia — the `not _bbox_from_hough` fix eliminates that regression.

Output: Committed codebase with verified guard logic, build_live_mask(), split bench metrics, vision fallback, and updated tests.
</objective>

<execution_context>
@C:/Users/neelj/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/neelj/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/1-ball-valid-80pct-nba-api-live-mask-guard/1-PLAN.md

@src/tracking/ball_detect_track.py
@src/pipeline/unified_pipeline.py
@src/data/nba_enricher.py
@_bench_run.py
@tests/test_hardening.py

<interfaces>
<!-- Key interfaces the executor needs. No codebase exploration required. -->

From src/tracking/ball_detect_track.py:
- `_bbox_from_hough: bool` — set True in detection mode (Hough/template path), False in CSRT path
- Guard 2 (line ~361): `elif (not _bbox_from_hough and self._trajectory and hypot > 200):`
  - Already has `not _bbox_from_hough`. Executor must VERIFY this is correct and NOT accidentally gate on CSRT-only path.
- Guard 3 (line ~380): `elif (not _bbox_from_hough and not self._is_ball_orange(...)):`
  - Already skips orange check for Hough detections.
- `self._jump_resets: int` — counter in __init__, incremented in Guard 2 body.

From src/pipeline/unified_pipeline.py:
- `self._sc_ever_seen: bool` — True once OCR reads a valid shot clock
- `self._ball_track_suspended: bool` — True during replay/halftime sequences
- `self._sc_absent_streak: int` — increments when clock absent after `_sc_ever_seen`
- `_SHOT_CLOCK_ABSENT_THRESHOLD` — constant controlling suspension trigger
- YOLO person count: accessible via `yolo_results` list length (each entry = one person detection)
- `suspended_frame_count` — local counter inside run(), returned in results dict

From src/data/nba_enricher.py:
- PBP raw cache format: list of dicts with keys GAME_ID, EVENTMSGTYPE, PERIOD, HOMEDESCRIPTION,
  VISITORDESCRIPTION, SCOREMARGIN, PLAYER1_NAME (NBA API raw format — no pre-computed game_clock_sec)
- Cached per-game file: `data/nba/pbp_{game_id}.json` — full game, all periods
- `fetch_playbyplay(game_id, period)` — returns processed rows with `game_clock_sec` field
  (this is the per-period cache at `pbp_{game_id}_p{period}`, not the bulk scraper cache)
- The bulk pbp_scraper.py cache is at `data/nba/pbp_{game_id}.json` in NBA API raw format
- build_live_mask must handle BOTH: raw bulk cache AND nba_api endpoint fallback

From _bench_run.py:
- `evaluate_layers(data_dir, results, game_id)` — returns (layers, weakest, api_ok)
- `build_summary(results, fps, layers)` — builds summary dict from layers
- L2_Ball layer dict: `{"valid_ball_pct": float, "rows": int, "status": str}`
- `--frames` argparse default currently 300 — change to 3600
- Pipeline results dict has: `total_frames`, `jump_resets`, `suspended_frames`, `stability`, `id_switches`

PBP event type codes (EVENTMSGTYPE):
  1=made FG, 2=missed FG, 3=FT, 4=rebound, 5=turnover, 6=foul, 7=violation,
  8=substitution, 9=timeout, 10=jump ball, 12=start period, 13=end period
  "live play" events: 1, 2, 3, 4, 5, 6
  "dead ball" events: 9 (timeout), 12, 13 (period start/end)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Verify Guard 2/3 fix + run tests + commit in-flight changes</name>
  <files>src/tracking/ball_detect_track.py, src/pipeline/unified_pipeline.py</files>
  <action>
    Step 1a — Read ball_detect_track.py Guard 2 elif condition (around line 361).
    VERIFY it reads: `elif (not _bbox_from_hough and self._trajectory and hypot_check > 200):`
    If `not _bbox_from_hough` is missing from the elif, ADD it. This prevents Guard 2 from firing
    on valid Hough re-detections (bos_mia regression root cause).

    Step 1b — Read unified_pipeline.py. Verify `_jump_resets` and `suspended_frames` are present
    in the results dict returned by `run()`. If missing, add them:
      results["jump_resets"] = self.ball_det._jump_resets
      results["suspended_frames"] = suspended_frame_count

    Step 1c — Run tests:
      conda run -n basketball_ai python -m pytest tests/test_hardening.py tests/test_phase2.py -q

    Step 1d — If green, commit:
      git add src/tracking/ball_detect_track.py src/pipeline/unified_pipeline.py
      git commit -m "fix(ball_track): orange CSRT guard + suspension threshold + jump_resets counter"

    NOTE: Do NOT run video pipeline. Tests only.
  </action>
  <verify>
    <automated>conda run -n basketball_ai python -m pytest tests/test_hardening.py tests/test_phase2.py -q 2>&1 | tail -5</automated>
  </verify>
  <done>Tests green. `not _bbox_from_hough` is present in Guard 2 elif. `jump_resets` and `suspended_frames` are in the results dict. Commit made.</done>
</task>

<task type="auto">
  <name>Task 2: Add build_live_mask() to nba_enricher.py + vision-based fallback in unified_pipeline.py</name>
  <files>src/data/nba_enricher.py, src/pipeline/unified_pipeline.py</files>
  <action>
    PART A — build_live_mask() in nba_enricher.py:

    Add this function after the existing helpers (around line 130, before enrich_shot_log):

    ```python
    def build_live_mask(game_id: str, video_fps: float = 30.0) -> dict:
        """
        Build a frame-level live/dead-ball mask from cached PBP data.

        Loads data/nba/pbp_{game_id}.json (bulk NBA API raw format).
        Converts game-clock timestamps to approximate video frame numbers.
        Returns {frame_idx: "live" | "dead_ball" | "unknown"}.

        Classification rules:
          - "live":      frame is within 5s (±150 frames at 30fps) of a live-play event
                         (EVENTMSGTYPE in {1, 2, 3, 4, 5, 6})
          - "dead_ball": frame is >30s gap between consecutive live events
          - "unknown":   everything else (transitions, near dead-ball boundaries)

        Game-clock to frame mapping:
          Each period is 12 minutes (720 seconds). Period N starts at (N-1)*720*fps frames.
          game_clock_sec within a period = 720 - (remaining seconds from PCTIMESTRING).
          Frame ≈ (period_start_sec + game_clock_sec) * fps.

        Falls back to empty dict {} if cache file not found.
        """
        cache_path = os.path.join(_NBA_CACHE, f"pbp_{game_id}.json")
        if not os.path.exists(cache_path):
            return {}

        with open(cache_path) as f:
            raw = json.load(f)

        # Parse events — handle both raw NBA API format and processed format
        _LIVE_EVENT_TYPES = {1, 2, 3, 4, 5, 6}
        events = []  # list of (frame_idx, is_live: bool)

        for row in raw:
            # Raw NBA API format: EVENTMSGTYPE, PERIOD, PCTIMESTRING
            evt_type = int(row.get("EVENTMSGTYPE", 0) or 0)
            period   = int(row.get("PERIOD", 1) or 1)
            clock_str = str(row.get("PCTIMESTRING", "12:00") or "12:00")

            try:
                mm, ss = clock_str.split(":")
                remaining_sec = int(mm) * 60 + int(ss)
            except (ValueError, AttributeError):
                continue

            elapsed_in_period = 720 - remaining_sec  # seconds elapsed in this period
            total_elapsed_sec = (period - 1) * 720 + elapsed_in_period
            frame_idx = int(total_elapsed_sec * video_fps)

            events.append((frame_idx, evt_type in _LIVE_EVENT_TYPES))

        if not events:
            return {}

        events.sort(key=lambda x: x[0])

        # Build frame mask — mark ±150 frames around live events as "live"
        _LIVE_RADIUS_FRAMES = int(5 * video_fps)   # 5 seconds
        _DEAD_GAP_FRAMES    = int(30 * video_fps)  # 30 seconds gap = dead_ball

        max_frame = events[-1][0] + _LIVE_RADIUS_FRAMES + 1
        mask = {}

        # Mark live zones
        for frame_idx, is_live in events:
            if is_live:
                for f in range(max(0, frame_idx - _LIVE_RADIUS_FRAMES),
                               frame_idx + _LIVE_RADIUS_FRAMES + 1):
                    mask[f] = "live"

        # Mark dead_ball zones (large gaps between live events)
        live_frames = sorted(fi for fi, il in events if il)
        for i in range(len(live_frames) - 1):
            gap = live_frames[i + 1] - live_frames[i]
            if gap > _DEAD_GAP_FRAMES:
                # Middle of gap is dead_ball
                gap_start = live_frames[i] + _LIVE_RADIUS_FRAMES
                gap_end   = live_frames[i + 1] - _LIVE_RADIUS_FRAMES
                for f in range(gap_start, gap_end):
                    if f not in mask:
                        mask[f] = "dead_ball"

        # Everything else is "unknown"
        # (caller can check: mask.get(frame_idx, "unknown"))
        return mask
    ```

    PART B — Vision-based non-live fallback in unified_pipeline.py:

    In the scoreboard OCR section (around line 740), AFTER the existing `_sc_ever_seen` / `_sc_absent_streak`
    logic but BEFORE `if self._ball_track_suspended:`, add:

    ```python
    # Vision-based fallback: if shot clock OCR never fired on this clip,
    # use YOLO person count + ball-absent streak as a proxy non-live signal.
    # Fires when: clock never seen + ball absent 20+ consecutive gameplay frames
    # + fewer than 8 persons visible (warmup / between-period / ad break).
    if (not self._sc_ever_seen
            and not self._ball_track_suspended
            and self._no_ball_vision_streak >= 20
            and len(yolo_results) < 8):
        self._ball_track_suspended = True
    ```

    Also add `self._no_ball_vision_streak: int = 0` to __init__ (alongside other counters).
    Increment it when `self._last_ball_2d is None and not self._ball_track_suspended`,
    reset it to 0 when ball is found. Put increment/reset just after the ball tracking block.

    Note on yolo_results count: each entry in yolo_results is one person detection result.
    Use `len(yolo_results)` as person count proxy (already available at this point in run()).
  </action>
  <verify>
    <automated>conda run -n basketball_ai python -c "from src.data.nba_enricher import build_live_mask; m = build_live_mask('0022200001'); print('build_live_mask OK, sample keys:', list(m.items())[:3] if m else 'empty (no cached pbp for this game_id)')" 2>&1</automated>
  </verify>
  <done>build_live_mask() importable and callable. Vision fallback code present in unified_pipeline.py __init__ and run() method. Tests still green after: `pytest tests/test_hardening.py tests/test_phase2.py -q`.</done>
</task>

<task type="auto">
  <name>Task 3: Update _bench_run.py (3600 default, live/dead split) + add tests + final commit</name>
  <files>_bench_run.py, tests/test_hardening.py</files>
  <action>
    PART A — _bench_run.py changes:

    1. Change `--frames` default from 300 to 3600:
       Find: `ap.add_argument("--frames",  type=int, default=300, ...)`
       Change to: `ap.add_argument("--frames",  type=int, default=3600, ...)`

    2. In evaluate_layers(), after computing L2_Ball, add live/dead split when game_id is present:
       ```python
       # Live/dead ball split (requires game_id for PBP mask)
       if game_id and ball_rows:
           try:
               from src.data.nba_enricher import build_live_mask
               live_mask = build_live_mask(game_id)
               if live_mask:
                   live_valid = sum(
                       1 for i, r in enumerate(ball_rows)
                       if live_mask.get(i, "unknown") == "live"
                       and float(r.get("ball_x", r.get("ball_x2d", 0)) or 0) > 0
                   )
                   live_total = sum(1 for i in range(len(ball_rows)) if live_mask.get(i, "unknown") == "live")
                   dead_valid = sum(
                       1 for i, r in enumerate(ball_rows)
                       if live_mask.get(i, "unknown") == "dead_ball"
                       and float(r.get("ball_x", r.get("ball_x2d", 0)) or 0) > 0
                   )
                   dead_total = sum(1 for i in range(len(ball_rows)) if live_mask.get(i, "unknown") == "dead_ball")
                   layers["L2_Ball"]["ball_valid_live"] = round(live_valid / max(1, live_total), 3)
                   layers["L2_Ball"]["ball_valid_dead"] = round(dead_valid / max(1, dead_total), 3)
                   layers["L2_Ball"]["live_frames"] = live_total
                   layers["L2_Ball"]["dead_frames"] = dead_total
           except Exception:
               pass  # non-fatal: live/dead split is diagnostic only
       ```

    3. In build_summary(), add live/dead metrics:
       ```python
       "ball_valid_live": layers.get("L2_Ball", {}).get("ball_valid_live", None),
       "ball_valid_dead": layers.get("L2_Ball", {}).get("ball_valid_dead", None),
       ```

    4. In the print output block at the bottom of main(), add:
       ```python
       live_pct = summary.get("ball_valid_live")
       dead_pct = summary.get("ball_valid_dead")
       if live_pct is not None:
           print(f"  {'Ball valid (live)':<22} {live_pct*100:>9.0f}%  ({layers.get('L2_Ball',{}).get('live_frames',0)} frames)")
           print(f"  {'Ball valid (dead)':<22} {dead_pct*100:>9.0f}%  ({layers.get('L2_Ball',{}).get('dead_frames',0)} frames)")
       ```

    PART B — tests/test_hardening.py — add two tests at the end of the file:

    Test 1: build_live_mask with a real cached PBP file (0022200001 exists):
    ```python
    def test_build_live_mask_real_cache():
        """build_live_mask returns dict with live/dead_ball/unknown values."""
        from src.data.nba_enricher import build_live_mask
        mask = build_live_mask("0022200001")
        # File exists so mask should be non-empty
        assert isinstance(mask, dict)
        if mask:
            values = set(mask.values())
            assert values <= {"live", "dead_ball", "unknown"}, f"unexpected values: {values}"
            # Should have at least some live frames for a real game
            live_count = sum(1 for v in mask.values() if v == "live")
            assert live_count > 0, "Expected at least some live frames"

    def test_build_live_mask_missing_game():
        """build_live_mask returns empty dict for unknown game_id."""
        from src.data.nba_enricher import build_live_mask
        mask = build_live_mask("NONEXISTENT_GAME_ID_XYZ")
        assert mask == {}

    def test_vision_fallback_imports():
        """Vision-based fallback attributes exist on UnifiedPipeline."""
        from src.pipeline.unified_pipeline import UnifiedPipeline
        import inspect
        src = inspect.getsource(UnifiedPipeline.__init__)
        assert "_no_ball_vision_streak" in src, "Missing _no_ball_vision_streak in __init__"
    ```

    PART C — Shot enrichment validation test (Step 6 from spec):
    ```python
    def test_bench_default_frames():
        """_bench_run.py default frames should be 3600."""
        import ast, os
        bench_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_bench_run.py")
        with open(bench_path) as f:
            src = f.read()
        assert "default=3600" in src, "Expected default=3600 in _bench_run.py --frames argument"
    ```

    PART D — After all changes, run full test suite and commit:
      conda run -n basketball_ai python -m pytest tests/test_hardening.py tests/test_phase2.py -q
      git add _bench_run.py tests/test_hardening.py src/data/nba_enricher.py src/pipeline/unified_pipeline.py
      git commit -m "feat(ball_track): build_live_mask, live/dead bench split, 3600 default, vision fallback"

    Then update CLAUDE.md — in the "Open Priority Issues" section, add note:
      "build_live_mask() added to nba_enricher.py — use with --game-id in _bench_run.py for live/dead split"
  </action>
  <verify>
    <automated>conda run -n basketball_ai python -m pytest tests/test_hardening.py -q -k "live_mask or vision_fallback or bench_default" 2>&1 | tail -10</automated>
  </verify>
  <done>All new tests pass. `--frames` default is 3600 in _bench_run.py. build_live_mask() returns live/dead/unknown keyed dict. Bench prints ball_valid_live and ball_valid_dead when game_id is present. Final commit made.</done>
</task>

</tasks>

<verification>
After all three tasks complete:

1. `conda run -n basketball_ai python -m pytest tests/test_hardening.py tests/test_phase2.py -q` — all green
2. `python -c "from src.data.nba_enricher import build_live_mask; print(type(build_live_mask('0022200001')))"` — returns `<class 'dict'>`
3. `grep "not _bbox_from_hough" src/tracking/ball_detect_track.py` — appears in Guard 2 elif
4. `grep "default=3600" _bench_run.py` — present
5. `grep "_no_ball_vision_streak" src/pipeline/unified_pipeline.py` — appears in __init__ and run()
6. `grep "ball_valid_live" _bench_run.py` — present in evaluate_layers and build_summary
</verification>

<success_criteria>
- All tests green (test_hardening.py + test_phase2.py)
- Guard 2 `not _bbox_from_hough` confirmed in elif — bos_mia regression fixed
- build_live_mask() in nba_enricher.py returns {frame_idx: "live"|"dead_ball"|"unknown"}
- _bench_run.py defaults to --frames 3600
- Vision fallback (_no_ball_vision_streak) present in unified_pipeline.py
- _bench_run.py evaluate_layers() computes ball_valid_live / ball_valid_dead when game_id present
- Two commits made: one for guard fixes, one for NBA API + bench + fallback
</success_criteria>

<output>
After completion, create `.planning/quick/1-ball-valid-80pct-nba-api-live-mask-guard/1-SUMMARY.md`
</output>
