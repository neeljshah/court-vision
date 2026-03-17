---
phase: 02-tracking-improvements
verified: 2026-03-16T22:30:00Z
status: gaps_found
score: 3/6 requirements verified
gaps:
  - truth: "Players are classified into two distinct teams (team_a / team_b) — NOT all-green"
    status: failed
    reason: "advanced_tracker.py line 438-439 explicitly converts all 'white' detections to 'green': `if team == 'white': team = 'green'`. The all-green bug is structurally present in the tracker loop and was never removed."
    artifacts:
      - path: "src/tracking/advanced_tracker.py"
        issue: "Lines 438-439 unify 'white' team into 'green' pool. All 10 on-court players share the same team label. REQ-02A is not satisfied."
    missing:
      - "Remove or conditionally gate the `if team == 'white': team = 'green'` unification at line 438-439"
      - "Preserve two separate team labels (e.g. team_a / team_b or the actual color keys) in the output CSV"
      - "Ensure _match_team() separates detections by true team before Hungarian matching"

  - truth: "EventDetector fires shot events — at least 1 shot per minute of broadcast footage"
    status: partial
    reason: "EventDetector code was rewritten and is logically sound, but REQ-02F (re-processing all 17 clips) was never completed. CLAUDE.md still shows '0 shots detected across all clips'. No evidence clips were re-processed after EventDetector rewrite."
    artifacts:
      - path: "src/tracking/event_detector.py"
        issue: "Implementation is present and non-stub, but no evidence of validation on actual clips. CLAUDE.md dataset status still shows 0 shots detected."
    missing:
      - "Process at least one real clip end-to-end and confirm shot events fire (requires --game-id)"
      - "Update CLAUDE.md dataset status with verified shot count after re-processing"

  - truth: "Clip duration validator rejects clips under 60 seconds as insufficient for analytics"
    status: failed
    reason: "No clip duration validator exists anywhere in the codebase. No file, function, constant, or test references clip duration validation. REQ-02E was not addressed by any plan."
    artifacts: []
    missing:
      - "Implement a clip duration check in run_clip.py or UnifiedPipeline — reject (or warn on) clips under 60 seconds"
      - "Add test coverage for the duration validator"

  - truth: "All 17 existing clips re-processed through fixed tracker with non-zero shots and both teams present"
    status: failed
    reason: "REQ-02F requires re-processing all 17 clips. The all-green bug (REQ-02A) is still in the tracker, so re-processing would still produce all-green output. CLAUDE.md dataset status was not updated after any plan. This cannot be satisfied until REQ-02A is fixed first."
    artifacts:
      - path: "CLAUDE.md"
        issue: "Dataset status still shows: 'Tracking rows: 29,220 — all players labeled green', 'Shots detected: 0'. No evidence clips were re-processed."
    missing:
      - "Fix REQ-02A (team color separation) first"
      - "Re-process all 17 clips with corrected tracker"
      - "Verify output: both teams present in team column, shot count > 0 per minute of footage"
---

# Phase 2: Critical Tracker Bug Fixes — Verification Report

**Phase Goal:** Fix the two critical bugs that make all existing CV tracking data unreliable: team color separation (all players currently labeled 'green') and event detection (0 shots, 0 dribbles detected across all 17 clips).

**Verified:** 2026-03-16T22:30:00Z
**Status:** GAPS FOUND
**Re-verification:** No — initial verification

---

## Requirement ID Mapping

The phase plans used internal IDs (REQ-04 through REQ-08b) that do NOT map to the canonical Phase 2 requirements in REQUIREMENTS.md. The user-specified requirement IDs for this phase are REQ-02A through REQ-02F. Cross-referencing:

| Canonical ID | Description | Plan Coverage |
|---|---|---|
| REQ-02A | Team color separation — both teams in output, not all-green | Not addressed by any plan |
| REQ-02B | Shot events fire (≥1 per minute) | EventDetector rewritten; no clip validation run |
| REQ-02C | Dribble events fire (ball_pos not None in 2D) | EventDetector rewritten; no clip validation run |
| REQ-02D | Pass events fire on ball transfer | EventDetector rewritten; no clip validation run |
| REQ-02E | Clip duration validator rejects < 60-second clips | Not built by any plan |
| REQ-02F | All 17 clips re-processed with non-zero shots + both teams | Requires REQ-02A fix first; not done |

The plans (02-01 through 02-05) focused on: jersey OCR, player identity, k-means re-ID tiebreaker, referee filtering, PostgreSQL persistence, and video download loop. These are real improvements but they address enhancement work, not the two declared critical bugs that are the stated phase goal.

---

## Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Players classified into two distinct teams (not all-green) | FAILED | `advanced_tracker.py` lines 438-439 force `team = "green"` for all "white" detections |
| 2 | EventDetector fires shot events (≥1 per minute of footage) | UNCERTAIN | EventDetector code rewritten and substantive; no re-processing validation run; CLAUDE.md still shows 0 shots |
| 3 | EventDetector fires dribble events (ball_pos not None in 2D) | UNCERTAIN | Code looks correct; requires live clip run to confirm |
| 4 | Pass events fire on possession transfer | UNCERTAIN | Logic present; requires live clip run to confirm |
| 5 | Clip duration validator rejects clips < 60 seconds | FAILED | No validator exists anywhere in codebase |
| 6 | All 17 clips re-processed with non-zero shots, both teams present | FAILED | REQ-02A still broken; CLAUDE.md dataset status unchanged |

**Score: 0/6 truths fully verified (3 uncertain, 3 failed)**

---

## Required Artifacts

### REQ-02A — Team Color Separation

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/tracking/advanced_tracker.py` | Two distinct team labels in output | STUB | Lines 438-439: `if team == "white": team = "green"` — deliberate unification of all non-referee players into "green" pool |
| `src/tracking/color_reid.py` | TeamColorTracker updates per-team EMA signatures | VERIFIED | Exists, substantive, imported and used in `advanced_tracker.py` via `self._color_tracker` |

**Root cause:** The `TeamColorTracker` and similar-color detection infrastructure is in place, but the actual team label assignment in `get_players_pos()` overrides it. After HSV classification assigns a player to "white", line 439 immediately reassigns `team = "green"`. The `_match_team()` loop at line 470 still iterates over `("green", "white", "referee")` but all detections are labeled "green" — the "white" bucket is always empty. This means the 96/99-dim appearance embeddings carry team color information but the output CSV's `team` column always shows "green" for all players.

### REQ-02B/02C/02D — EventDetector

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/tracking/event_detector.py` | Fires shot/dribble/pass events with 2D ball position | VERIFIED (code) | Rewritten with full state machine; handles pixel_vel fallback; possessor_pos guard present at line 146-155 |

**Note:** The EventDetector code is substantive and logically correct for dribble detection (requires both `ball_pos is not None` and `possessor_pos is not None`). This is an improvement over the prior broken state. However, no evidence exists that this was validated against actual clips after the rewrite. CLAUDE.md dataset status still reads "Shots detected: 0."

### REQ-02E — Clip Duration Validator

| Artifact | Expected | Status | Details |
|---|---|---|---|
| Clip duration validator (any file) | Rejects/warns clips < 60 seconds | MISSING | grep across entire src/ and run_clip.py found no references to clip duration validation, min duration, or 60-second threshold |

### REQ-02F — Re-processing All 17 Clips

| Artifact | Expected | Status | Details |
|---|---|---|---|
| CLAUDE.md dataset status | Updated counts: non-zero shots, two teams | UNCHANGED | CLAUDE.md still shows "All players labeled 'green'" and "Shots detected: 0" |

---

## Key Link Verification

### Link: color_reid.py → advanced_tracker.py (ISSUE-005)

| From | To | Via | Status |
|---|---|---|---|
| `advanced_tracker.py` | `color_reid.py` | `TeamColorTracker` updates per detection | WIRED but INEFFECTIVE |

The `TeamColorTracker.update()` is called at line 464-465 for each detection, updating per-team EMA color signatures correctly. The `similar_colors` flag is checked at lines 295-299 in `_match_team()` to increase appearance weight. **However**, because all non-referee detections are already relabeled to "green" at line 439 before `self._color_tracker.update()` is called (line 464), both "teams" are fed into the same team bucket. The `TeamColorTracker` receives only `team="green"` updates and never sees `team="white"`, so `similar_colors` will only become True if two players on the same "green" team have different jersey colors — which is the wrong comparison entirely. The similar-color detection is bypassed by the upstream team label collapse.

### Link: EventDetector ball_pos path

The dribble fix targeted by ISSUE-011 was: "ball_pos None in 2D path". The current `event_detector.py` `_classify()` method at lines 146-155 does guard `if ball_pos is not None and possessor_pos is not None` before computing distance. This is a correct fix. The guard was verified in the code.

---

## What the Plans Actually Delivered (vs Phase Goal)

The six plans delivered real work that enhances the tracker, but it is categorically different from the stated phase goal:

| Plan | What it built | Maps to Phase Goal? |
|---|---|---|
| 02-00 | pytest infrastructure, test stubs | No — test scaffolding only |
| 02-01 | Jersey OCR (EasyOCR), JerseyVotingBuffer, fetch_roster | No — new feature, not bug fix |
| 02-02 | k-means re-ID tiebreaker (REID_TIE_BAND), reset_slot | No — re-ID enhancement, not team separation fix |
| 02-03 | Referee filtering in feature_engineering + shot_quality | Partial — removes one category of corruption but not the all-green bug |
| 02-04 | PostgreSQL connection helper, player_identity_map, run_clip wiring | No — persistence layer, not bug fix |
| 02-05 | Video downloader batch + loop_processor | No — data acquisition infrastructure |

None of the six plans removed or modified the `if team == "white": team = "green"` line that is the root cause of the all-green bug (REQ-02A). The plans also do not include any work on REQ-02E (clip duration validator) or REQ-02F (re-processing all 17 clips).

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/tracking/advanced_tracker.py` | 438-439 | `if team == "white": team = "green"` — intentional team label collapse | BLOCKER | Directly causes REQ-02A failure. All 10 on-court players output "green" as team label. The comment says "Unify all non-referee players into the 'green' pool so all 10 unified player slots can be used regardless of jersey color" — this was likely added as a workaround for a slot-count issue but it defeats the phase goal entirely. |
| `src/tracking/advanced_tracker.py` | 470 | Hungarian matching still iterates `("green", "white", "referee")` | WARNING | The "white" pass in `_match_team()` always finds 0 detections because all white-labeled detections are renamed "green" at line 439. Dead code path. |

---

## Human Verification Required

### 1. EventDetector Validation on Real Clip

**Test:** Run `python run_clip.py --video data/videos/<clip>.mp4 --frames 300` on any existing broadcast clip and inspect `data/shot_log.csv` row count.
**Expected:** At least 1 shot event per minute of footage; at least occasional dribble events in `data/tracking_data.csv` event column.
**Why human:** Cannot run video processing on this machine per CLAUDE.md rule.

### 2. Team Separation After Fix

**Test:** After fixing the team label unification, run a clip and verify `data/tracking_data.csv` has both "team_a" (or "green") and "team_b" (or "white") rows — not all one label.
**Expected:** Two distinct non-referee team labels each present in >= 30% of non-referee tracking rows.
**Why human:** Requires video processing.

---

## Gaps Summary

Two categories of gaps block phase goal achievement:

**Category 1 — Structural bug not fixed:** The all-green bug (REQ-02A) that is the #1 stated goal of this phase is still present. `advanced_tracker.py` line 439 collapses all "white" team detections into "green". This one line defeats team separation. It was introduced as a deliberate workaround (comment at line 437 explains the intent: use all 10 unified slots regardless of jersey color). This workaround needs to be removed and replaced with proper dual-team slot management.

**Category 2 — Requirements not planned:** REQ-02E (clip duration validator) was never included in any of the six plans. REQ-02F (re-processing 17 clips) cannot be done until REQ-02A is fixed. The event detection improvements (REQ-02B/02C/02D) need runtime validation against actual clips.

**Category 3 — Scope drift:** The six plans focused on jersey OCR, player identity, PostgreSQL persistence, and video acquisition — genuinely valuable work that will benefit later phases, but it is Phase 3/6 work that was built instead of the Phase 2 critical bug fixes.

---

_Verified: 2026-03-16T22:30:00Z_
_Verifier: Claude (gsd-verifier)_
