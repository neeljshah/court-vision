# Tracking program -- state record and nightly runbook (2026-09-02)

Read with: TRACKING_GAPS_2026-09-01.md (the queue), RESULTS_LEDGER.md (what
landed, with numbers), and the memory file tracking_week_program_2026_09_01.
Everything below is measured tonight unless marked PLAN.

## 1. Where each sport stands (broadcast footage only)

STALENESS NOTE 2026-09-03: every "(codex running)" / "(running)" / "(landing)" in
the table below was true at the 09-02 wind-down and is FALSE now -- codex was
stopped and nothing is dispatched. Read section 2b for the actual worktree state.
Two more corrections to the "all / corpus" row: the pod deploy IS done (ledger row
G14b, 48 files, 2026-09-02 ~22:05, daemon 3127047), and G01b landed as G01c
(4212afa1e). The rung, measured-state and blocker columns are still accurate.
| sport | rung reached | measured state | blocker now | next single problem |
|---|---|---|---|---|
| tennis | COURT_FEET on sequential play | camera-lock 0.10 -> 0.20 (sampled plan); sequential 300-frame ranges 0.897 coverage, harness PASS; 3 matches 5/5, 1/5, 4/5 ranges PASS; lines on lines 12/12; 2,013 unique pseudo-labeled frames | detect_players picks courtside non-players (staff/umpire/ball kids) -> oob on 5/15 ranges (G26, codex running); first learned keypoint model training (G31, pod GPU) | G26 land -> re-run 15 ranges -> G31 held-out-match PCK |
| baseball | METRIC_LOCAL | 4 real MLB day broadcasts; every pitch segment carries scale; two-reference validation keeps 9/36 segments (25 pct); night gate closed at limit after 3 designs (detectors fail at night) | corpus size (G12b acquiring 8 more); validated-scale fraction 25 pct; 360p re-ingest (G27) | more day broadcasts -> raise validated-scale fraction -> command/glove teacher features (M1) |
| basketball | IMAGE_PX_DECLARED | producer wrote minimap px (fixed by post-processing, 8 games 0.94-0.98 inside frame; src producer fix PROPOSED for human apply); containment gate at intake; image_px teacher proxies landed; 20.5 pct of foot points in the top fifth of frame = non-floor detections (G25 floor gate, codex running) | producer fix needs human apply in src/; non-floor detections; only 10 recycled track ids per game (identity is not tracked) | G25 land -> human applies producer diff -> re-track 11 games -> pace/lineup teachers |
| soccer | S0 (no verdict) | n=100 blind verdict AMBIGUOUS (manual pct>=14 0.49); detector over-counts humans (refs/staff); detector made deterministic (0/100 drift on repeats; sealed counts had drifted 27/100 and 17/64); role filter not validated (11.4 pct disagreement vs 10 bar) | count-based verdict needs a player-role classifier better than color heuristics; stream packet for churn (G08 running); learned calibration needs self-labels (SCCvSD BSD-2 is the only clean model) | G08 churn numbers -> role classifier (jersey template or detector class) -> self-label calibration set |
| football | PAUSED | motion-energy snap detection structural REJECT (13-15 pct precision); numeral OCR terminal; 6/9 clips are 360p; 4 mislabeled clips quarantined | no licensed field-view source; broadcast camera motion | re-enter only with a licensed All-22/field-view source |
| all | corpus | census + quarantine live; 12 junk clips quarantined; 25/61 clips 360p; 5 high-res siblings never enqueued (G28 landing); ball_valid failed by construction on 94 pct of tables (G29 landing); daemon done-definition rejected once (G15b fix pass queued); ingest re-gate redo done (G01b awaiting verifier) | pod daemon still runs pre-G15/G28/G29 code (deploy + restart after they land) | land G28/G29/G01b -> G15b -> deploy + daemon restart |

## 2. What needs to be done (the queue, severity first)

REWRITTEN 2026-09-03 by the roadmap audit. The previous queue line marked five
jobs "(running)" and listed six items that had since landed; codex was stopped
the night of 09-02 and NOTHING is running. Nine of the fourteen entries were
stale. The live queue is the one in the register's "Next single-problem lanes"
block; it is reproduced here only so the two files cannot drift apart again:

0. **Commit the uncommitted G26 work in worktree a5 before any worktree sync.**
   a5 holds a modified `domains/tennis/tracking/adapter.py` plus untracked
   `player_select.py` / `test_player_select.py`, and `git log master..HEAD` there
   is EMPTY -- so loop rule 3's refusal does NOT fire and a routine
   `reset --hard master` would delete the work.
1. G26 verify (or one re-dispatch) -> 2. re-run the 15 tennis sequential ranges
-> 3. G31 fold-0 checkpoint check, then fold 1 and the held-out-match evaluation
-> 4. G25b mask-sanity fix pass -> 5. G28b duration-first sibling fix pass (holds
the shared-module token) -> 6. G17 v3 role classifier (jersey template or a
detector class, NOT colour) -> 7. G03 basketball producer diff, HUMAN APPLY by
Neel only, then re-track 11 games -> 8. a NEW id for further baseball corpus
growth (G12 is CLOSED) -> 9. G09 soccer self-label calibration -> 10. G32 night
detector (LOW).

The teacher->student gate is NOT a tracking job: G16 is SUPERSEDED BY harness row
S04 and is built there. The pod deploy backlog named in the old line is CLEARED
(ledger row G14b, 2026-09-02 ~22:05); what is outstanding is G08 and anything
landed from 2026-09-03 forward, tracked as S21.

## 2b. WORKTREE STATE, measured 2026-09-03 (read before syncing anything)
| wt | unmerged `master..HEAD` | dirty | what it is | safe to reset? |
|---|---|---|---|---|
| a5 | (none) | YES -- 1 modified + 2 untracked | the G26 work | **NO -- commit first** |
| a6 | b78d8cb46 | no | G31 trainer + test (memory says "uncommitted"; wrong) | no, it is live work |
| a9 | 93e8dcd69 | no | G25 rejected work; G25b builds on it | no |
| a2 | 9ba9d395e | no | G28 rejected work; G28b builds on it | no |
| a3 | b2ddcc1ec + 2 | no | content already landed as G01c 4212afa1e | yes, after confirming content-identity |
| a4 | ebc82a15e + 1 | no | already landed as G15b 8ca8f1e93 | yes, after confirming content-identity |
| a7 | 72de73265 + 1 | no | already landed as G29b 7daae6c7c | yes, after confirming content-identity |
| a8 | b020b6715 + 1 | no | already landed as G08 f07c71cd7 | yes, after confirming content-identity |

TWO AMENDMENTS TO LOOP RULE 3, both forced by the table above:
(a) the refusal must ALSO fire on a dirty tree (`git status --porcelain`
non-empty), not only on a non-empty `master..HEAD` -- as written it protects a
committed WIP and silently destroys an uncommitted one, which is exactly the case
a5 is in today;
(b) the refusal must be LIFTABLE when every commit in `master..HEAD` is
content-identical to something already on master, or a4/a7/a8/a3 can never be
synced again and the fleet loses four lanes to bookkeeping.

## 3. What the loop did tonight (measured)
- Codex jobs dispatched: 24; landed after verification: 12; rejected: 8
  (honest: role filter x2, night gate x3, coast tagging, ingest gate v1,
  daemon done v1); blocked once (cookie jar missing in worktree); 4 running.
- Opus verifiers: 11; every landing carried a per-file test line and a
  render-and-look tally; verifiers found 6 new gaps (G22, G24, G25, G26, G27-30).
- Rejects were caught by the verifier 6 times and by codex itself 4 times.
- Time per codex job: 15-50 min; verifier 5-25 min.

## 4. Nightly STOP runbook (do this to stop cleanly)
1. Stop dispatching: delete the session cron and the codex Monitor.
2. Let running codex jobs finish (log gains a 'tokens used' line and goes
   quiet 4 min) or leave them -- they are cheap and their worktree commits
   survive; nothing is lost if the session closes mid-job.
3. Land what is done if a verifier can run in <=20 min; otherwise mark the
   register rows AWAITING VERIFIER (already the convention).
4. `git status` (nothing from data/ or vault/), secrets-scan, `git push origin master`.
   MECHANISE THIS -- harness row S28 turns it into a pre-push hook, because a step
   that lives only in prose is the step a long night skips, and the failure (a
   leak to the public origin) is irreversible. Until S28 lands, do it by hand and
   never with `git add -A` / `git add .` / `commit -a`.
5. Append the day's 3-line note to .planning/NOW.md and update the state
   section of memory tracking_week_program_2026_09_01. Keep MEMORY.md under 200
   lines / 25 KB (measured 2026-09-03: 129 lines / 18.3 KB -- inside the cap;
   check, do not assume, and use the `memory-curate` skill if it is over).
6. Pod: leave the daemon and capture running (they are 24/7); never kill.
7. Back up the gitignored audit trail (`data/cache/eval_gate/backtest_fwer.jsonl`,
   13 rows today) -- harness row S29. It is what every deflated p is computed
   against, it is pod-authoritative, and nothing copies it anywhere.

## 5. Morning START runbook
0. (added 2026-09-03) Say OUT LOUD which ownership model is in force today -- one
   session, or the two-account split in HANDOFF_TRACKING_ACCOUNT2_2026-09-02.md --
   and who holds the NEXT_GAP_ID counters. Two sessions incrementing the same
   header independently is the G23/G25 collision that made ids orchestrator-only.
   Then check section 2b and commit any dirty worktree BEFORE syncing it.
1. Read memory tracking_week_program_2026_09_01 (recipe) + this file + the
   register order line + `ls -t Temp/cx_g*.log | head` (overnight codex
   finishes have a 'tokens used' line, no EXIT line if the wrapper died).
2. Arm the Monitor (cx_g*.log, seeded) and the 29-min cron. Session crons expire
   after 7 days -- re-arm every morning rather than assuming yesterday's survived.
3. Verify overnight DONE jobs first (Opus, <=2 at a time), then dispatch the
   next OPEN rows to free worktrees (sync to master; copy the cookie jar for
   download jobs; scp only the module under test to the pod).
4. Push after the first landings.
5. Pod: reach it through the `config.pod` ssh alias, never a hardcoded port --
   the port drifts (memory pod_tracking_ops records 40045 -> 40048, and the
   handoff doc still hardcodes 40048). If the alias does not answer, fix the
   alias; do not guess a port. Confirm the daemon and capture pids from `/proc`,
   never `pgrep` (it matches the checking command itself on this box).

## 6. PLAN: what would make this loop optimal (to be refined by the audit lane)
- Fewer, sharper rejects: every spec carries the exact acceptance rule and the
  verifier's checklist up front (missing-metadata fall-through, additive
  schema, no tautological metrics, no pre-verification pod copies).
- Verifier as a fixed contract file the spec and the verifier both cite, so
  codex self-checks before reporting.
- Gap ids allocated by the orchestrator only (two lanes collided on G25).
- Worktrees pre-provisioned with data/videos/youtube_cookies.txt.
- Codex wrapper writes EXIT even when the parent dies (setsid/nohup the
  wrapper itself), so completion detection never depends on the session.
- One verifier per landing, two at most; codex up to 6; Fable only
  adjudicates and writes register rows.
- Every night: stop runbook; every morning: start runbook; the ledger is the
  only progress report.

## 7. POD STOP / RESTART (RunPod can be stopped at any time after this)
What persists on the /workspace network volume: repo copy, data/footage_corpus,
data/footage_bridge, data/models (incl. tennis_keypoints_fold*.pt when saved),
data/cache (book capture archive, ledgers), /workspace/track_daemon_ledger.
What is LOST on stop: running processes only -- track_daemon (pid **3127047** as of
the 2026-09-02 22:05 deploy, keeper 3127042; the 3047270/3047264 pair below was the
pre-deploy generation) via keeper /workspace/keep_track_daemon.sh, MLB book capture
(pid 3040635), and
any in-flight tracking jobs (at wind-down 2026-09-02 ~21:30 local: G31 tennis
keypoint train fold 0 at epoch 5/30 -> rerun both folds tomorrow; G25
basketball floor gate; G26 tennis sequential rerun). /tmp is also lost:
anything a job left only under /tmp (g18/g23/g25/g26/g31 outputs) must be
scp-ed to docs/evidence before stop if it is needed; the labeled JSONL for G23
is already committed under docs/evidence/tracking/tennis_pseudolabels_2026-09-02/.

RESTART (in this order, after the pod is up and the `config.pod` ssh alias answers;
the port drifts -- 40045 -> 40048 so far, see memory pod_tracking_ops. Resolve it
through the alias and fail loud if the alias is wrong; never hardcode a port in a
runbook line, which is what HANDOFF_TRACKING_ACCOUNT2 still does):
  cd /workspace/nba-ai-system
  nohup setsid bash /workspace/keep_track_daemon.sh > /workspace/keep_track_daemon.log 2>&1 < /dev/null &
  CV_CAPTURE_POD=1 CV_MLB_BOOK_ARCHIVE_LIVE=1 CV_GUMBO_PACE_SEC=0.25 nohup setsid nice -n 10 python -c "from scripts.platformkit.ingame.mlb_book_capture import run_pod_capture; run_pod_capture(stop=lambda: False)" > /workspace/mlb_book_capture.log 2>&1 < /dev/null &
  # verify: ls /proc/$(cat /workspace/track_daemon.pid); tail -2 /workspace/mlb_book_capture.log
Then deploy master to the pod BEFORE any new tracking job (git archive of the
landed files; CRLF-normalised md5 check). CORRECTED 2026-09-03: G15b/G29b/G01c
were deployed on 2026-09-02 ~22:05 and the daemon was restarted on that code
(ledger row G14b, commit c7816aecd). The outstanding deploy is **G08
(f07c71cd7)** plus everything landed from 2026-09-03 forward -- that is what
harness row S21 covers.
