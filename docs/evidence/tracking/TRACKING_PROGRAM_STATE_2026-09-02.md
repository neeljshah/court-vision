# Tracking program -- state record and nightly runbook (2026-09-02)

Read with: TRACKING_GAPS_2026-09-01.md (the queue), RESULTS_LEDGER.md (what
landed, with numbers), and the memory file tracking_week_program_2026_09_01.
Everything below is measured tonight unless marked PLAN.

## 1. Where each sport stands (broadcast footage only)
| sport | rung reached | measured state | blocker now | next single problem |
|---|---|---|---|---|
| tennis | COURT_FEET on sequential play | camera-lock 0.10 -> 0.20 (sampled plan); sequential 300-frame ranges 0.897 coverage, harness PASS; 3 matches 5/5, 1/5, 4/5 ranges PASS; lines on lines 12/12; 2,013 unique pseudo-labeled frames | detect_players picks courtside non-players (staff/umpire/ball kids) -> oob on 5/15 ranges (G26, codex running); first learned keypoint model training (G31, pod GPU) | G26 land -> re-run 15 ranges -> G31 held-out-match PCK |
| baseball | METRIC_LOCAL | 4 real MLB day broadcasts; every pitch segment carries scale; two-reference validation keeps 9/36 segments (25 pct); night gate closed at limit after 3 designs (detectors fail at night) | corpus size (G12b acquiring 8 more); validated-scale fraction 25 pct; 360p re-ingest (G27) | more day broadcasts -> raise validated-scale fraction -> command/glove teacher features (M1) |
| basketball | IMAGE_PX_DECLARED | producer wrote minimap px (fixed by post-processing, 8 games 0.94-0.98 inside frame; src producer fix PROPOSED for human apply); containment gate at intake; image_px teacher proxies landed; 20.5 pct of foot points in the top fifth of frame = non-floor detections (G25 floor gate, codex running) | producer fix needs human apply in src/; non-floor detections; only 10 recycled track ids per game (identity is not tracked) | G25 land -> human applies producer diff -> re-track 11 games -> pace/lineup teachers |
| soccer | S0 (no verdict) | n=100 blind verdict AMBIGUOUS (manual pct>=14 0.49); detector over-counts humans (refs/staff); detector made deterministic (0/100 drift on repeats; sealed counts had drifted 27/100 and 17/64); role filter not validated (11.4 pct disagreement vs 10 bar) | count-based verdict needs a player-role classifier better than color heuristics; stream packet for churn (G08 running); learned calibration needs self-labels (SCCvSD BSD-2 is the only clean model) | G08 churn numbers -> role classifier (jersey template or detector class) -> self-label calibration set |
| football | PAUSED | motion-energy snap detection structural REJECT (13-15 pct precision); numeral OCR terminal; 6/9 clips are 360p; 4 mislabeled clips quarantined | no licensed field-view source; broadcast camera motion | re-enter only with a licensed All-22/field-view source |
| all | corpus | census + quarantine live; 12 junk clips quarantined; 25/61 clips 360p; 5 high-res siblings never enqueued (G28 landing); ball_valid failed by construction on 94 pct of tables (G29 landing); daemon done-definition rejected once (G15b fix pass queued); ingest re-gate redo done (G01b awaiting verifier) | pod daemon still runs pre-G15/G28/G29 code (deploy + restart after they land) | land G28/G29/G01b -> G15b -> deploy + daemon restart |

## 2. What needs to be done (the queue, severity first)
G26 tennis player selection (running) -> G31 keypoint model (running) -> G25
basketball floor gate (running) -> G28/G29/G01b verifiers -> G15b daemon fix
pass -> pod deploy + daemon restart -> G12b/G27 corpus growth (running) ->
G08 soccer churn (running) -> G17 role classifier v3 (jersey template / detector
class, not color) -> G09 soccer self-label calibration -> G32 night detector
(low) -> G16 teacher->student gate module (harness burst, H04) -> basketball
producer fix HUMAN APPLY (docs/research/organization-sprint/PROPOSED_basketball_producer_2026-09-01.md).

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
5. Append the day's 3-line note to .planning/NOW.md and update the state
   section of memory tracking_week_program_2026_09_01.
6. Pod: leave the daemon and capture running (they are 24/7); never kill.

## 5. Morning START runbook
1. Read memory tracking_week_program_2026_09_01 (recipe) + this file + the
   register order line + `ls -t Temp/cx_g*.log | head` (overnight codex
   finishes have a 'tokens used' line, no EXIT line if the wrapper died).
2. Arm the Monitor (cx_g*.log, seeded) and the 29-min cron.
3. Verify overnight DONE jobs first (Opus, <=2 at a time), then dispatch the
   next OPEN rows to free worktrees (sync to master; copy the cookie jar for
   download jobs; scp only the module under test to the pod).
4. Push after the first landings.

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
What is LOST on stop: running processes only -- track_daemon (pid 3047270 via
keeper /workspace/keep_track_daemon.sh), MLB book capture (pid 3040635), and
any in-flight tracking jobs (at wind-down 2026-09-02 ~21:30 local: G31 tennis
keypoint train fold 0 at epoch 5/30 -> rerun both folds tomorrow; G25
basketball floor gate; G26 tennis sequential rerun). /tmp is also lost:
anything a job left only under /tmp (g18/g23/g25/g26/g31 outputs) must be
scp-ed to docs/evidence before stop if it is needed; the labeled JSONL for G23
is already committed under docs/evidence/tracking/tennis_pseudolabels_2026-09-02/.

RESTART (in this order, after the pod is up and `ssh -p <port> root@<ip>` works;
the port drifts -- see memory pod_tracking_ops):
  cd /workspace/nba-ai-system
  nohup setsid bash /workspace/keep_track_daemon.sh > /workspace/keep_track_daemon.log 2>&1 < /dev/null &
  CV_CAPTURE_POD=1 CV_MLB_BOOK_ARCHIVE_LIVE=1 CV_GUMBO_PACE_SEC=0.25 nohup setsid nice -n 10 python -c "from scripts.platformkit.ingame.mlb_book_capture import run_pod_capture; run_pod_capture(stop=lambda: False)" > /workspace/mlb_book_capture.log 2>&1 < /dev/null &
  # verify: ls /proc/$(cat /workspace/track_daemon.pid); tail -2 /workspace/mlb_book_capture.log
Then deploy master to the pod BEFORE any new tracking job (git archive of the
landed files; CRLF-normalised md5 check) -- G15b/G29b/G01c land after this
record was written and the daemon must be restarted on the new code.
