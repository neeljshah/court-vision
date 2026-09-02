# Tracking loop -- measured audit and optimal design (2026-09-02)

Audit of the autonomous tracking-improvement loop as it ran the night of
2026-09-01. Read with TRACKING_PROGRAM_STATE_2026-09-02.md (state) and
RESULTS_LEDGER.md (what landed). Section 1 is measured from disk -- codex log
birth/modify times, each log's own 'tokens used' line, the ledger rows, and
`git log`; nothing is estimated unless the row says so. Windows: codex logs
19:18-20:43 local (85 min); ledger 18:00-20:43 (163 min, also covering the
pre-codex Claude-lane work).

## 1. Measured

### 1.1 Per codex job

Wall minutes = log birth -> last write; a blank token cell = still running at
20:43. Causes: SPEC (the verifier's rule was never written down), DESIGN (the
approach is wrong -- an honest null), DATA (an input was absent), PROCESS (loop
machinery cost the job).

| gap(s) | log cx_* | tokens | start | end | min | outcome | cause |
|---|---|---:|---|---|---:|---|---|
| G18 | g18_tennis_seqplan | 152,672 | 19:18 | 19:43 | 25 | LANDED c57bcb85e | - |
| G11 v1 | g11_night_pitchview | 206,126 | 19:24 | 19:33 | 9 | REJECT (verifier) | DESIGN |
| G17 v1 | g17_soccer_role_filter | 161,623 | 19:41 | 19:48 | 7 | REJECT (by codex) | DESIGN |
| G19 | g19_bb_coast_tag | 132,859 | 19:42 | 19:51 | 9 | REJECT (verifier) | SPEC |
| G11 v2 | g11b_composed_pitchview | 461,559 | 19:44 | 20:07 | 23 | REJECT (verifier) | PROCESS |
| G22+G17b | g22_g17b_soccer_determinism | 172,114 | 19:48 | 19:58 | 10 | LANDED 639336c44 (G22 ACCEPT, G17 NOT VALIDATED) | DESIGN (G17) |
| G01 | g01_ingest_regate | 291,201 | 19:50 | 20:08 | 18 | REJECT (verifier) | SPEC |
| G15 | g15_daemon_done_verdict | 171,083 | 19:51 | 20:02 | 11 | REJECT (verifier) | SPEC |
| G04 | g04_bb_imagepx_features | 136,072 | 19:51 | 20:00 | 9 | LANDED ef0b5e152 | - |
| G12 | g12_more_real_baseball | 97,955 | 19:59 | 20:06 | 7 | BLOCKED (no cookie jar) | DATA |
| G23 | g23_tennis_pseudolabels | 256,013 | 20:00 | 20:15 | 15 | LANDED 45b60357f | - |
| G20+G21 | g20_g21_cleanup | 138,652 | 20:01 | 20:08 | 7 | LANDED 77539bc9d (+verifier fix 321c589a1) | - |
| G08 | g08_soccer_stream_packet | (running) | 20:03 | 20:43+ | 40+ | RUNNING | - |
| G24 | g24_ext_packet_determinism | 75,879 | 20:05 | 20:11 | 6 | LANDED 3e55c2c62 | - |
| G12b | g12b_more_real_baseball | 156,107 | 20:06 | 20:38 | 32 | AWAITING VERIFIER | - |
| G11 v3 | g11c_geometry_first | 319,259 | 20:07 | 20:23 | 16 | REJECT; G11 closed at limit | PROCESS |
| G26 | g26_tennis_player_select | (running) | 20:10 | 20:43+ | 33+ | RUNNING | - |
| G25 | g25_bb_nonfloor_detections | (running) | 20:12 | 20:43+ | 31+ | RUNNING | - |
| G29 | g29_ball_telemetry_flag | 142,303 | 20:14 | 20:27 | 13 | AWAITING VERIFIER | - |
| G28 | g28_highres_siblings | 153,881 | 20:16 | 20:29 | 13 | AWAITING (pod pre-copy warning) | - |
| G27+G30 | g27_g30_reingest_360p | 234,948 | 20:17 | 20:43 | 26 | AWAITING VERIFIER | - |
| G01b | g01b_ingest_regate_fix | 122,141 | 20:24 | 20:32 | 8 | AWAITING VERIFIER | - |
| G31 | g31_tennis_keypoint_train | (running) | 20:28 | 20:43+ | 15+ | RUNNING | - |

23 jobs, 26 gap-attempts; 19 finished, 5 running at the audit point. Codex
tokens over the 19 finished: **3,582,447** (mean 188,550, median 156,107, max
461,559 on G11 v2, min 75,879 on G24). Durations min 6, median 13, max 40 min.

### 1.2 Verifier outcomes and defects codex missed

11 Opus verifier passes, reconstructed independently from the register rows
(G11 v1/v2/v3, G22+G17, G19, G04, G24, G01, G20+G21, G15, G23) -- matching the
state record's count of 11.

| pass | verdict | what the verifier caught that codex missed |
|---|---|---|
| G01 ingest re-gate | REJECT | title_rejection() quarantines on EMPTY metadata, so a direct MP4 never reaches the 90 s probe -- the deciding condition; and the required-keyword whitelist kills real games ('Yankees vs Red Sox condensed game', 14/15 npb full archives, 7/7 tennis 'Full Match 2025 US Open'). Codex's own 4 test files all passed (2+3+3+4). |
| G15 daemon done | REJECT | non-additive ledger rename (tracked/thin -> done/unadjudicated, failures -> failure_heads) silently zeroes night_report.py:126-133; and retain() stops deleting on OSError, so claimable() re-claims and re-tracks the same game forever. |
| G19 coast tagging | REJECT | circular metric: the tables carry no bbox columns, so only the off-frame rule could fire and containment_observed 0.9991-1.0000 is true by construction -- yet the manifest emits verdict_observed on that number and names no coasted_rule. |
| G11 v1 night gate | REJECT | codex sampled renders from a head slice; an evenly-spaced sample put night new-accept precision at 25/32 = 0.78 (under the 0.80 bar) and the frames the mode ADDS on day at 0/8. |
| G23 pseudo-labels | ACCEPT w/ corrections | 2,209 rows are only 2,013 UNIQUE frames (196 double-labeled by two overlapping tennis10 ranges); fresh/reuse recount 2,052/157 not 2,048/161; the residual field is a self-fit, not independent line evidence; the 14-point convention is 10 canonical + 4 derived. |
| G21 script retirement | ACCEPT + fix | two orphaned tests left behind (1 collection error, 1 failure); verifier reproduced and retired both. |
| G28 high-res siblings | AWAITING | codex scp-ed daemon files to the pod BEFORE verification, so pod on-disk differs from master while the running daemon still holds old code. |
| G22 / G24 determinism | ACCEPT | reproduced the numbers independently (2 processes identical on 10 frames; 17/64 EXT seal drift) -- confirmation, not a catch. |
| G04 image_px features | ACCEPT | named the unverified residue: 30 fps assumed not measured, pan heuristic unvalidated, only wnba_01 rendered. |

**Verification's highest-value output is new gaps, not verdicts:** 8 open gaps
(G22, G24, G25, G26, G27, G28, G29, G30) were raised by a verifier or the
verifier-run gap finder. G25 came from the verifier's own measurement
(6,624/32,355 emitted foot points = 20.5 pct in the top fifth of frame), which
also killed the track-level metric as degenerate (10 recycled ids/game).

### 1.3 Process defects that cost time

| defect | measurement | cost |
|---|---|---|
| Orphaned wrapper: EXIT impossible | **0 of 23 logs** contain an EXIT: line. ~/bin/codex-sport echoes EXIT to the WRAPPER's stdout, after the redirect closes -- it never enters the log. Both the memory recipe and the state record define DONE as an EXIT: line in the log. | The documented completion signal could not fire all night; every finish was found by tailing. |
| Cookie jar missing in worktrees | G12: "this worktree has no usable YouTube cookie jar", then failed Chrome/Edge/Firefox exports. Redispatched as G12b. | 97,955 tokens + 7 min wasted, plus a 156,107-token / 32-min redo and one orchestrator cycle. |
| Retry without a limit-first pass | G11 ran 3 attempts (206,126 / 461,559 / 319,259) before v3 answered the question v1 should have asked -- can any detector see the mound at night. Verdict: closed at limit. | 986,944 tokens, 48 min, 3 verifier passes, for a null the loop's own limit-first rule reaches in one. |
| Gap ids allocated by lanes | The G22 register row still points at "G23" for the ext-packet follow-on, which was filed as G24 while G23 went to tennis pseudo-labels. (The state record reports the collision as G25; the artifact on disk is the stale G23 reference.) | A dangling cross-reference in a tracked register -- high confusion cost on a cold resume. |
| Monitor scope | 244 `cx_*.log` files in Temp; 23 are tonight's. The Monitor pattern matches all 244, de-flooded only by a 6 h age filter, not by scope. | Flood risk on any session started >6 h after the last run. |
| Multi-gap job logs | 3 of 23 logs bundle 2 gaps (g20_g21, g22_g17b, g27_g30). | The log name no longer maps 1:1 to a register row, so a completion event cannot say which gap finished. |
| Verifier auth / session-cap failures | NOT MEASURED from disk. NOW.md records "RATE-LIMIT LEFTOVERS (agents died at session cap)" for the earlier 5 h session; no artifact for tonight's verifiers. | Unknown -- reported, not reproduced. |

### 1.4 Throughput and spend

| metric | codex window (1.42 h) | ledger window (2.72 h) |
|---|---:|---:|
| landings (ACCEPT/LANDED to master) | 8 | 13 |
| landings per hour | 5.6 | 4.8 |
| honest rejects / FAIL / NOT VALIDATED / AMBIGUOUS | 8 | 11 |
| rejects per hour | 5.6 | 4.0 |
| new gaps opened | 8 | 8 |
| codex jobs dispatched | 23 | 23 |

Concurrency minute by minute over the 85-min window -- 1 job: 14 min; 2: 11;
3: 7; 4: 2; 5: 18; 6: 13; 7: 10; 8: 10. **25 of 85 minutes (29.4 pct) had
fewer than 3 codex jobs alive, and every one of those minutes is in the first
25.** Zero minutes had none alive; past 5 concurrent it never fell below 4.

Token spend -- every finished job in exactly one bucket, summing to 3,582,447:

| bucket | jobs | tokens | share |
|---|---:|---:|---:|
| landed work (G18, G22/G17b, G04, G23, G20/G21, G24) | 6 | 931,402 | 26.0 pct |
| honest nulls that had to be measured (G11 v1, G17 v1) | 2 | 367,749 | 10.3 pct |
| awaiting verifier at stop (G12b, G29, G28, G27/G30, G01b) | 5 | 809,380 | 22.6 pct |
| **rework the loop caused itself** | **6** | **1,473,916** | **41.1 pct** |

Rework itemised: SPEC rejects G19 + G01 + G15 = 595,143; the G11 v2+v3 retries
a limit-first v1 would have made unnecessary, 780,818; the G12 cookie block
97,955. **41 pct of codex spend was avoidable by a spec rule, a stop rule, or
one copied file.**

## 2. Defects, ranked by cost

1. **Specs carried no acceptance rule, so the verifier's bar arrived after the work.** 3 of 8 rejects (G19 circular metric, G01 empty-metadata fall-through, G15 non-additive rename) died on a rule nobody wrote down: 595,143 tokens, 3 verifier passes, 1 redo.
2. **No stop rule on a failing mechanism.** G11 burned 986,944 tokens over 3 attempts to reach a null; the register's own limit-first rule was enforced by nothing.
3. **Worktrees are not provisioned.** One missing gitignored file cost 254,062 tokens and 39 minutes.
4. **Completion detection is fictional.** The documented DONE signal cannot occur (0/23), part of why ramp-up to 3 concurrent took 25 min.
5. **Gap ids and job logs are allocated ad hoc.** Stale G23 cross-reference, 3 logs bundling 2 gaps, Monitor matching 244 files.

## 3. Optimal loop design

### 3.1 Spec template

Artifact `docs/evidence/tracking/specs/<GID>_spec.md`, copied into the worktree
before dispatch (docs/research and .planning are gitignored there), 40 lines
hard cap. Template text:

```
GAP <GID> | sport <sport> | worktree a<N> | log cx_<gid>_<slug>
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check
against every line of section B before you report.
PREMISE (step 0): <the one measurement that proves the gap is real today>. If
falsified, STOP, write the memo, commit, report FALSIFIED -- a valid result
that earns its own register row.
LIMIT (step 1): <the measurement that bounds what is achievable>. If the limit
is below the acceptance bar, STOP and report CLOSED AT LIMIT. Do not fix.
CHANGE (step 2): <the smallest change>. Additive only: new columns, new opt-in
modes, new files. Renaming or removing an existing field, column or status
value is an automatic reject -- if unavoidable, keep the old name as an alias
in the same commit and name every reader you checked.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = <name + exact denominator: decoded frames/rows/segments>
  before        = <measured today, with n>
  bar           = <the number "after" must beat; fixed now, never moved>
  n             = <>= 30>
  eye check     = <k renders EVENLY SPACED over the decision set, no head slice>
  must not move = <thresholds/files that must be byte-identical after>
NON-TAUTOLOGY: state which rows the metric covers and which are excluded. If
excluding the failing rows is what makes the number good, the metric is
circular -- say so and report REJECT yourself.
EVIDENCE: docs/evidence/tracking/<gid>_<slug>_2026-09-02.md -- before/after
table, n, denominator, render tally, and a "NOT VERIFIED" list.
TEST: exactly one new per-file test; run only that file.
POD: heavy compute only; own nohup setsid nice job, unique /tmp log, never
kill anything, no git on the pod, and NO scp of any module until the verifier
accepts. Report the files you would deploy; do not deploy them.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha.
NEVER PARK: poll your own jobs in a blocking loop; never end waiting.
```

### 3.2 VERIFIER_CONTRACT.md (new file, cited by both sides)

```
# Verifier contract -- what every tracking landing must survive
Codex self-checks section B before reporting. The verifier applies A and B and
nothing else. A rule absent from the spec's ACCEPTANCE RULE cannot be used to
reject -- if the verifier needs one, it files a new gap instead.

## A. The verifier's own work (not the lane's)
A1 Re-run the lane's single per-file test in MASTER, not the worktree.
A2 Recompute the headline metric from the artifact yourself; never quote the lane's number without reproducing it.
A3 Sample renders EVENLY over the decision set. Head slices are how G11 v1 showed 0.93 where the honest number was 0.78.
A4 Count uniqueness -- G23 reported 2,209 rows that were 2,013 unique frames.
A5 Grep every reader of any field the diff touches (G15 broke night_report).
A6 Land by `git -C <wt> archive <sha> -- <paths> | tar -x -C <repo>`, explicit pathspec commit, then append the RESULTS_LEDGER line and the register row.

## B. Automatic reject conditions (codex: check before you report)
B1  CIRCULAR METRIC -- computed after excluding the rows that would fail it, or the excluded set is unnamed. (G19)
B2  NON-ADDITIVE SCHEMA -- a column, status value or field renamed/removed without an alias, or a reader unchecked. (G15)
B3  FALL-THROUGH LOSS -- a gate quarantines on ABSENT evidence instead of passing the item on. Missing != bad. (G01)
B4  RE-CLAIM LOOP -- a failure path leaves an item claimable forever. (G15)
B5  PRE-VERIFICATION DEPLOY -- any file copied to the pod before ACCEPT. (G28)
B6  ORPHANS -- a moved/retired module leaves a test, import or -m reference behind. (G21)
B7  HEAD-SLICE EVIDENCE -- renders or rows sampled from the start of the set.
B8  SELF-FIT AS INDEPENDENT -- a residual against the same points used to fit is not evidence. (G23)
B9  DEGENERATE DENOMINATOR -- the metric's unit is recycled or trivially constant, e.g. 10 recycled track ids per game. (G25)
B10 MOVED BAR -- any harness threshold or gate value differs from master.

## C. Verdicts
ACCEPT (land) | ACCEPT WITH CORRECTIONS (land; ledger carries the corrections)
| NOT VALIDATED (land as unused/opt-in with zero callers, honest row)
| REJECT (do not merge; queue a named fix pass) | CLOSED AT LIMIT (no retry).
Every verdict writes one RESULTS_LEDGER line and one register row.
```

### 3.3 Gap-id allocation -- orchestrator only

The orchestrator appends the register row FIRST (status OPEN, no owner), then
dispatches. A lane or verifier finding a new gap reports `NEW GAP: <one line>`
and the orchestrator assigns the number. One id = one register row = one job
log = one ledger line. Multi-gap jobs only when the gaps share one diff; the
log takes the lowest id and the register row names the others.

### 3.4 Worktree provisioning script

Artifact `scripts/platformkit/tracking/provision_worktree.sh` (~20 lines), run
before every dispatch wave, per worktree a1/a2/a3/a5/a7/a8/a9:

```
git -C <wt> checkout -- . && git -C <wt> clean -fd && git -C <wt> reset --hard master
mkdir -p <wt>/data/videos <wt>/docs/evidence/tracking/specs
cp data/videos/youtube_cookies.txt <wt>/data/videos/    # gitignored both sides
cp docs/evidence/tracking/VERIFIER_CONTRACT.md <wt>/docs/evidence/tracking/
cp docs/evidence/tracking/specs/<GID>_spec.md <wt>/docs/evidence/tracking/specs/
test -s <wt>/data/videos/youtube_cookies.txt || echo "WARN cookie jar empty"
```

Measured justification: the one missing file cost 254,062 tokens. It also
closes Gotcha 4 (stale worktree) and Gotcha 5 (spec doc never arrives).

### 3.5 Codex wrapper -- EXIT survives the parent

Write EXIT INTO the log from the wrapper itself and detach the wrapper so a
dying parent shell cannot orphan it. Keep `< /dev/null` -- the stdin-hang fix.

```
#!/bin/sh
H="$1"; LOG="$2"; shift 2
WT="/c/Users/neelj/nba-track-$H"; L="/c/Users/neelj/AppData/Local/Temp/cx_$LOG.log"
[ -d "$WT" ] || exit 3
cd "$WT" || exit 1
setsid nohup sh -c '
  CODEX_HOME="'"/c/Users/neelj/.codex-$H"'" codex exec --skip-git-repo-check \
    --sandbox danger-full-access "$@" < /dev/null >> "'"$L"'" 2>&1
  echo "EXIT:$? gap='"$LOG"' at $(date -Is)" >> "'"$L"'"
' _ "$@" >/dev/null 2>&1 &
echo "DISPATCHED $LOG -> $L"
```

Completion = whichever comes first: (a) an `EXIT:` line in the log, now
actually possible; (b) a `tokens used` line AND no write for 4 minutes. Never
use process liveness -- pgrep/pkill silently no-op on Windows python.

### 3.6 Per-sport daily cadence

Parallel-safe, because the sports touch disjoint adapters: a5 tennis
(domains/tennis/** only), a2 basketball (domains/basketball_nba/** only),
a1/a8 soccer (domains/soccer/**, scripts/platformkit/soccer_*), a7/a4 baseball
(domains/baseball/**), a9 cross-cutting read-only measurement and docs.

Serialized, one at a time, never two in flight: anything touching
`track_daemon.py`, `tracking_harness.py`, `tracking_schema.py`,
`footage_census.py`, the ingest gate, or the ledger schema. G28 and G15b
already collide on track_daemon.py -- exactly this class. A shared-module gap
holds a token; the next dispatches only after the previous is ACCEPTED or
REJECTED. Steady state = 5 sport slots + 1 shared-module slot = 6 concurrent
codex jobs, reached within 10 minutes of start (cost of not doing this,
measured: 25 idle-ish minutes out of 85).

## 4. Runbooks

**Nightly STOP.** (1) Stop dispatching -- delete the session cron and the codex Monitor. (2) Do NOT wait for running codex jobs; their worktree commits survive, so record each running gap's worktree + log name in its register row as RUNNING. (3) Land only what a verifier can finish in <= 20 min; everything else becomes AWAITING VERIFIER with the unmerged sha in the register row. (4) `git status` (nothing from data/ or vault/), secrets-scan, targeted `git add`, `git push origin master` -- master is 6 commits ahead tonight. (5) Append the 3-line note to .planning/NOW.md and update the state section of memory tracking_week_program_2026_09_01. (6) Pod: leave the daemon and capture running, never kill; note in the register that the pod still runs pre-G15/G28/G29 code.

**Morning START.** (1) Read this file, TRACKING_PROGRAM_STATE, the register's "Next single-problem lanes" line, and the RESULTS_LEDGER tail. (2) Triage overnight logs -- `ls -t Temp/cx_g*.log | head -12`, then per log `grep -c EXIT:` and the 'tokens used' line; tokens-used plus 4 quiet minutes = DONE regardless of EXIT. (3) Provision all worktrees (3.4) BEFORE dispatching anything. (4) Verify overnight DONE jobs first, one Opus verifier at a time, oldest first. (5) Dispatch to 6 concurrent inside 10 minutes (5 sport slots + 1 shared module), confirming each log grows within 2 minutes. (6) Arm the Monitor on `cx_g*.log` only -- not `cx_*.log` -- plus the age filter, and the 29-min fallback cron. (7) Push after the first landing.

## 5. Usage budget

Codex is the cheap side: 3.58 M codex tokens bought 8 landings, 8 honest nulls
and 8 new gaps in 85 minutes. Opus verifiers are the cost and the quality --
11 passes caught 5 defects every codex test suite had passed. Spend codex
freely; ration Opus.

| tier | when | what it costs |
|---|---|---|
| REQUIRED | any commit that changes a metric, gate or threshold or how a number is computed; adds/changes a column, status value or ledger field; touches the daemon, harness, schema, ingest gate or corpus; produces a number quoted in the ledger or register; writes labels or training data (G23-class); or claims any before -> after improvement | full pass, 15-25 min, includes render-and-look |
| LIGHT | evidence-only commits whose numbers the reported pod job already reproduced, plus a diff under 50 LOC with a passing per-file test (G12b is the example) | 10 min, no render pass |
| SKIP | docs/evidence-only commits carrying no new number (a memo of an already-verified measurement, register bookkeeping, this file); a pure file move or retirement WITH a proven-zero reference sweep the orchestrator runs itself, tests included (G21 is the trap -- skip only if the sweep covers tests); a test-only addition pinning existing behaviour; a research/licence memo with no code (G09-class) | orchestrator lands it and still writes the ledger line |

Shape per 8-hour day: ~30-40 codex jobs, 12-18 full verifier passes, 6-8 light
passes, 6-10 skips. Fable adjudicates only -- big calls, register order, and
anything where the contract and the evidence disagree.

## 6. Open questions for the user (defaults apply if you say nothing)

| # | question | default |
|---|---|---|
| 1 | Codex concurrency cap -- peak was 8, the design above is 6. | 6 concurrent codex jobs; 1 Opus verifier at a time, 2 max. |
| 2 | Attempt cap per gap -- G11 took 3 attempts and 986 k tokens to reach a null. | 2 attempts; the second must be a limit measurement, not a third design, and a failed second closes the gap AT LIMIT. |
| 3 | Cookie jar handling -- provisioning copies a gitignored credential file into 7 worktrees. | Do it (gitignored in every worktree, never committed). Say so if you would rather confine download jobs to one designated worktree. |
| 4 | Pod deploy authority -- G28's lane scp-ed daemon files pre-verification. | No lane may scp anything; the verifier deploys after ACCEPT and the daemon restart is a separate orchestrator step. |
| 5 | Hard nightly stop, or keep running while you sleep? | Hard stop per section 4, with the pod daemon and capture left running 24/7. |

---
Written by the loop-audit lane, 2026-09-02. No code changed; no push.
