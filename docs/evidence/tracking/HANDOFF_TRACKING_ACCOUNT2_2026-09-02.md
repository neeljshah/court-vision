# Handoff: TRACKING session (second Claude account) -- 2026-09-02 night

Paste the OPENING PROMPT below into a Claude Code session opened in
C:\Users\neelj\nba-ai-system on the second account. This session (account 1)
keeps the harness/system planning; account 2 owns TRACKING tonight.

## Division of ownership (binding for both sessions tonight)
- Account 2 OWNS: docs/evidence/tracking/** (registers, ledger, memos),
  scripts/platformkit/tracking/**, domains/*/tracking/**, the codex worktrees
  /c/Users/neelj/nba-track-a2..a9, the pod (ssh -p 40048 root@213.192.2.83),
  and the memory file tracking_week_program_2026_09_01 (append only).
- Account 1 OWNS: docs/research/organization-sprint/**, docs/evidence/
  HARNESS_GAPS_2026-09-03.md, SYSTEM_GAPS, .planning/NOW.md header, everything
  under scripts/platformkit/eval_gate, combo, ingame, execution.
- Shared modules need the shared-module token (rule 4): track_daemon.py,
  tracking_schema.py, tracking_harness.py, footage_census.py, the ingest gate.
  Tonight the token is with ACCOUNT 2. Account 1 will not touch them.
- Git: both commit with explicit pathspecs; before every push run
  `git fetch origin master && git rebase origin/master` on a clean tree (never
  --force); secrets-scan the range; never data/ or vault/.
- Pod: account 2 may deploy landed tracking files (git archive, md5 check) and
  restart the keeper+daemon per docs/evidence/tracking/pod_deploy_2026-09-01.md
  (write the keeper name as keep_track_daemo?.sh in any ssh line -- the keeper's
  pgrep self-clean kills a command line that contains its own name). Never kill
  the MLB book capture (pid 3040635) or the G31 training (pid 3077867).

## OPENING PROMPT (paste verbatim)

You are the TRACKING orchestrator for CourtVision tonight (2026-09-02, ~2-3
hours, then stop cleanly). Read, in order: the memory file
C:\Users\neelj\.claude\projects\C--Users-neelj-nba-ai-system\memory\tracking_week_program_2026_09_01.md
(the loop, invariants, five binding rules, session-start recipe),
docs/evidence/tracking/HANDOFF_TRACKING_ACCOUNT2_2026-09-02.md (this file: your
ownership + work order), docs/evidence/tracking/TRACKING_PROGRAM_STATE_2026-09-02.md,
docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md (the queue; NEXT_GAP_ID in
the header is yours to allocate tonight), docs/evidence/tracking/RESULTS_LEDGER.md,
docs/evidence/tracking/VERIFIER_CONTRACT.md (B1-B10 + Q1-Q6),
docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md, and run
`sh scripts/platformkit/tracking/loop_status.sh`. Then arm the loop: a
persistent Monitor on /c/Users/neelj/AppData/Local/Temp/cx_g*.log (DONE = an
EXIT: line; seed it with already-done logs) and a 29-minute fallback cron.
Roles: you (the orchestrator) adjudicate and allocate gap ids only; Opus agents
write specs from the template and verify (per-file test + render-and-look,
git archive from the worktree into master, pathspec commit, register row,
ledger line); codex edits and measures via `~/bin/codex-sport aN <log> -- '<spec>'`
(rewritten: detached, cookie jar provisioned, EXIT written into the log); the
pod does all heavy compute (own nohup jobs, unique /tmp logs, never kill
anything, no git on the pod). Max 6 codex jobs, 2 Opus verifiers at a time.
Every landing = ledger line + register row. Work the ORDER below; when a gap
lands or rejects, the verifier's "not verified" items become new rows. At the
end: stop dispatch, land what is verified, push (fetch+rebase first), append a
3-line note to the memory file and to .planning/NOW.md under
"## SESSION 2026-09-01 5h autonomous".

## Tonight's work order (tracking only; each item = one codex job + one verifier)
1. G26 tennis player selection: codex a5 is RUNNING (cx_g26_tennis_player_select.log);
   when DONE verify: same 15 sequential ranges, pass fractions before 5/5,1/5,4/5
   -> after, oob per range, coverage IDENTICAL (solver untouched), 8 renders viewed.
   If it fails B1-B10, redispatch ONCE with the template (limit-first STOP).
2. G31 tennis keypoint model: pod training fold 0 running (/tmp/g31_fold0.log,
   ckpt data/models/tennis_keypoints_fold0.pt; trainer committed in worktree a6
   as b78d8cb46). When fold 0 ends: launch fold 1; evaluate PCK@7px at 1280x720,
   median px, and the >=4-keypoints-within-7px solve proxy on the HELD-OUT
   MATCH per fold; 12 renders per fold viewed; compare to classical coverage on
   the same ranges (/tmp/g18_seqplan JSONs); memo; commit in a6; verify.
   Acceptance is honesty, not a number: below the 0.933 / 2.83 px ceiling is
   expected; the question is whether it solves frames the classical fails on.
3. G25b basketball floor gate fix (worktree a9, commit 93e8dcd69 rejected):
   per-game mask sanity -> when the learned hardwood mask covers < 15 pct of
   frames on more than half the game, emit mask_unreliable and tag NO rows;
   add a second reference (court-line density) as an AND condition for
   nonfloor; re-measure the 8 games; the wnba_01/04 two-tone floors are the
   test. Acceptance: no game with mask_unreliable has nonfloor tags; render
   tally >= 90 pct on 24 evenly spaced frames across 3 arenas.
4. G28b resolution siblings (worktree a2, commit 9ba9d395e rejected): prefer
   the LONGEST duration then the highest height; explicit variant key (never
   strip a suffix from an id that has no sibling); keep the daemon landmine
   comments; additive columns only. Acceptance: the 4 sibling groups pick the
   long copy; single-variant ids unchanged; 28 daemon tests + 2 plan tests
   green. SHARED MODULE: track_daemon.py is now at 300 LOC -- extract a helper.
5. G17 v3 soccer role classifier (worktree a4 or a8): NOT color heuristics.
   Design first: a 3-class crop classifier (player / referee / other) on
   self-labeled crops from the 100 packet frames + the G08 stream windows
   (Opus labels 300 crops by eye into docs/evidence/tracking/soccer_roles_labels/),
   torchvision resnet18 (BSD), 5-fold CV on crops, then re-run the paired
   delta on the n=100 packet. Acceptance: crop accuracy >= 0.90 on held-out
   crops AND |paired delta| < 1.0 with < 10 pct render disagreement. S1 is
   never re-adjudicated.
6. G12 corpus growth (worktree a4): 8 more official MLB day broadcasts via the
   bridge (cookie jar is provisioned by the wrapper); keep >= 6/12 field view;
   push kept clips to the pod bridge; report ledger rows after 10 minutes.
7. If time remains: G32 is LOW; instead run a GAP-FINDER Opus lane over the
   newest memos' "not verified" sections and the pod ledger, add 3 measured rows.

## Deep planning for tracking (Opus lane, in parallel with the codex jobs)
Write docs/evidence/tracking/TRACKING_DEEP_PLAN_2026-09-03.md (tracked):
per sport, the full path from today's rung to the achievable limit with
broadcast footage only, as ordered single-problem rows with acceptance
rules and the teacher feature each unlocks (tennis: court_feet on sequential
play across matches -> serve/return positions -> rally geometry; baseball:
validated scale > 60 pct of segments -> command miss + glove travel -> framing
prereg M1; basketball: floor gate -> producer human-apply -> identity via
jersey/role classifier -> pace/lineup teachers; soccer: churn -> role classifier
-> self-label calibration set (SCCvSD BSD-2 route) -> pressing/block-depth
teachers; football: paused, re-entry condition = licensed field-view source).
Each row cites the memo that measured the current state. Append new rows to
TRACKING_GAPS with the NEXT ids and bump the header.

## Rails (binding)
Harness thresholds never move; denominators = decoded frames; render-and-look
before any claim (evenly spaced, never head slices); honest FAIL/REJECT rows are
successes; image_px rows never pass court_feet; src/ kernel/ api/ intel/ are
human-gated (PROPOSED diffs only); per-file tests only (a full pytest freezes
the box); ASCII stdout; no dollar/edge claims; commit with explicit pathspecs;
never git reset/checkout -- on the main tree; scp to the pod only the module
under test (never track_daemon.py or shared modules) until a verifier lands it.
