# Tracking day-1 execution plan (2026-09-04) -- dispatch-ready, planning session only

Authored in a PLANNING-ONLY session (logical program day 2026-09-03; the box
clock reads 2026-09-01, doc names in this program run on the logical day).
Nothing was dispatched, no codex job was started, no tracking module was
edited. Everything below was measured today with a read-only tool call.

**What this file is.** The single document the next session reads to start
dispatching inside five minutes. It carries the re-measured premises, the lane
allocation, the blockers already resolved, the wave schedule, and the arming
recipe. The paste-ready codex specs live beside it in
`CODEX_SPECS_2026-09-04.md`. The queue of record is still
`TRACKING_GAPS_2026-09-01.md`; this file does not replace it.

**Read order tomorrow:** this file -> `CODEX_SPECS_2026-09-04.md` ->
`sh scripts/platformkit/tracking/loop_status.sh` -> dispatch wave A. Do not
re-read the whole register first; section 1 below already carries every
correction the register and the state doc need.

---

## 1. PREMISE LEDGER (contract Q8: re-measure the fact the row rests on)

Twelve premises re-measured today. Five were false. A falsified premise is a
valid result; each one is corrected in place below and in the register.

| # | premise as written | where it is written | measured today | verdict |
|---|---|---|---|---|
| 1 | a5 holds UNCOMMITTED G26 work; commit before any sync or a `reset --hard master` destroys it | STATE 2b item 0, register audit, memory | a5 tree CLEAN; `master..HEAD` = 2 commits (948122992 wip, a60b4268a evidence) | **FALSIFIED** -- the work is committed and safe. Item 0 of the queue is DONE. |
| 2 | a2 holds the G28 rejected work at 9ba9d395e; G28b builds on it | STATE 2b, register G28 row | a2 HEAD = 8ca8f1e93 (master's G15b sha), `master..HEAD` EMPTY. 9ba9d395e is a live object with NO branch pointing at it | **CHANGED** -- it was dangling and one `git gc` from gone. Tagged today as `g28-reject-9ba9d395e`. G28b cherry-picks the tag. |
| 3 | G31 fold-0 checkpoint must be confirmed; /tmp does not survive a pod stop | memory MORNING FIRST TASK, register G31 | the pod was never stopped. `data/models/tennis_keypoints_fold0.pt` EXISTS, 46,735,897 bytes, Sep 2 03:20. `/tmp/g31_fold0.log` complete, 30/30 epochs, metrics line written | **CONFIRMED** -- and the result is already in hand (row 4). |
| 4 | (no doc records fold-0 numbers) | new measurement | held_out=tennis09, **PCK@7px 0.0774**, **median_px 17.395**, **frames_ge_4_in_7 0.0**, train 1713 / test 300 frames, 2013 unique of 2209 raw, final train loss 0.000007 | **NEW** -- fold 0 is a near-null on the held-out match and the train loss says heavy overfit. Zero frames reach the >=4-in-7px solve proxy. This is a strong CLOSED-AT-LIMIT signal before fold 1 runs. |
| 5 | T3 = leave-one-match-out, **3 folds** over 3 matches | PLAN_TRACKING_RESEARCH T3, handoff item 2 | `tennis_keypoint_train.py:190` argparse `choices=(0,1)`; `split_fold():45` `held_out = ("tennis09","tennis10")[fold]`. **nyYk is never held out** | **FALSIFIED** -- 2 folds exist, not 3. Either accept a 2-fold result or extend `split_fold` (an additive change, new work). |
| 6 | the shipped stack uses permissive licences only; torchvision ImageNet weights are research-only and forbidden | PLAN section 4 S1, G09 licence research | `tennis_keypoint_train.py:112-115` defaults `pretrained=True` with `ResNet18_Weights.IMAGENET1K_V1`; fold 0 downloaded `resnet18-f37072fd.pth` | **CONFLICT** -- G31 as trained is under the exact rail the soccer row forbids. A `--no-pretrained` flag already exists. Adjudicate before any ship claim (section 4.3). |
| 7 | T2 / K3 / S2 and the shot-type denominator run on CLIP zero-shot | PLAN sections 1,3,4; day item 7 | pod: no `open_clip`, no `clip`, no `transformers`. `torch 2.8.0+cu128`, cuda True | **BLOCKED as written** -- and "zero new dependencies" is a standing default. Resolved by design change, section 4.1. |
| 8 | reach the pod through the `config.pod` ssh alias, never a hardcoded port | STATE section 5.5, memory pod_tracking_ops | `~/.ssh/config` has NO pod alias. `-p 40048` is what answers today (loop_status reached the daemon through it) | **FALSIFIED** -- the alias does not exist, so the runbook line is unexecutable. Section 4.4. |
| 9 | pod state | loop_status | `daemon_alive`, `capture_alive`, GPU **0 pct / 1 MiB** (nothing training), disk 64 pct | CONFIRMED. The GPU is free for wave A. |
| 10 | nothing is dispatched | register audit | 14 `cx_g*.log` files, every one DONE(orphan); newest 25 min old at read time | CONFIRMED. |
| 11 | `track_daemon.py` is at the 300 LOC cap so G28b must extract a helper | handoff item 4 | `scripts/platformkit/track_daemon.py` = **exactly 300 lines** | CONFIRMED. |
| 12 | T3's inputs sit only in `/tmp` and must be copied to docs/evidence first | PLAN T3 | `docs/evidence/tracking/tennis_sequential_plan_2026-09-01/` already holds `tennis_09.json`, `tennis_10.json`, `tennis_nyYk2nPZAwY_720p.json` + `overlays/`. `/tmp/g18_*` also still alive on the pod | **FALSIFIED (favourably)** -- already satisfied, no copy step needed. |

Also confirmed, no change: `scripts/platformkit/eval_gate/student_gate.py` is
ABSENT (S04 has not been built, so no teacher claim may be made);
`docs/evidence/tracking/soccer_roles_labels/` is ABSENT (item 5 creates it);
repo `unpushed=0`, tip `9481d5299`; register `NEXT_GAP_ID: G33`.

**Worktree state, re-measured today (this table supersedes STATE section 2b):**

| wt | `master..HEAD` | dirty | what it holds | safe to reset? |
|---|---|---|---|---|
| a2 | 0 | no | nothing -- it was reset; the G28 work is only at tag `g28-reject-9ba9d395e` | yes |
| a3 | 3 | no | content landed as G01c 4212afa1e | yes, after content-identity check |
| a4 | 2 | no | content landed as G15b 8ca8f1e93 | yes, after content-identity check |
| a5 | 2 | no | **the G26 work (live)** | no |
| a6 | 1 | 2 untracked | **G31 trainer b78d8cb46 (live)**; the 2 dirty files are `findings.md` / `task_plan.md`, planning-skill scratch, not work | no (but the scratch files are disposable) |
| a7 | 2 | no | content landed as G29b 7daae6c7c | yes, after content-identity check |
| a8 | 2 | 2 untracked | content landed as G08 f07c71cd7; same 2 scratch files | yes, after content-identity check |
| a9 | 1 | no | **G25 rejected work 93e8dcd69 (live, G25b builds on it)** | no |

Net: **no uncommitted real work exists anywhere.** The single at-risk item
found today was the dangling G28 commit, now tagged.

---

## 2. Ownership and the counters (say this out loud in the first turn)

- This session is the **TRACKING orchestrator** and **holds the tracking
  `NEXT_GAP_ID` counter**. Account 1 holds the harness `S` counter. One
  counter, one holder (the G23/G25 collision is why).
- Owned here: `docs/evidence/tracking/**`, `scripts/platformkit/tracking/**`,
  `domains/*/tracking/**`, worktrees a2-a9, the pod, the shared-module token.
- Not touched here: `src/ kernel/ api/ intel/` (human-gated, PROPOSED diffs
  only), `scripts/platformkit/eval_gate|combo|ingame|execution`,
  `docs/research/organization-sprint/**` except the one appended amendment block.
- **Account 1 is active in this repo right now.** Uncommitted at the time of
  writing: `scripts/hooks/pretooluse_guard.py` (+23 lines),
  `docs/evidence/SHARED_MODULE_TOKEN.md`, `.agents/`, `.codex/`, and
  **`docs/evidence/tracking/specs/`** holding harness specs S01, S02 and S04.
  That last one is harness work written into a tracking-owned directory. It is
  not a filename collision (this plan uses `specs_2026-09-04/`), so nothing is
  broken, but the two registers should not share a `specs/` directory. Raise it
  with account 1 rather than moving their files.
- Ids allocated today: **G33, G34, G35, G36**. `NEXT_GAP_ID` moves G33 -> **G37**,
  leaving G37+ for the rows the gap-finder files.

---

## 3. Lane allocation (max 6 codex, 2 verifiers)

| item | gap | sport | worktree | codex log | compute | blocks on |
|---|---|---|---|---|---|---|
| 1 | G26 attempt 2 (LIMIT) | tennis | **a5** (holds the work) | `g26b_tennis_player_limit` | pod | -- |
| 2 | G31 fold 1 + held-out eval | tennis | **a6** (holds the trainer) | `g31b_tennis_fold1_eval` | pod GPU | -- |
| 3 | G25b floor gate mask sanity | basketball | **a9** (holds G25) | `g25b_bb_mask_sanity` | pod | -- |
| 4 | G28b sibling duration-first | all | **a2** (cherry-pick the tag) | `g28b_siblings_duration` | local | **shared-module token** |
| 5 | G17 v3 role classifier (LIMIT) | soccer | **a8** | `g17c_soccer_role_limit` | pod GPU | 300 Opus labels |
| 6 | **G33** baseball scale-failure bins | baseball | **a7** | `g33_baseball_scale_bins` | local | -- |
| 7 | **G34** view-share denominator | 3 sports | **a3** | `g34_view_denominator` | local | -- |
| 8 | **G35** gap-finder pass | all | none (Opus lane) | none | local | -- |
| spare | **G36** baseball day-corpus growth | baseball | a4 | `g36_baseball_day_corpus` | local dl | a free slot |

**Shared-module token holder for the day: item 4 (G28b), worktree a2.** It is
the only job that touches `track_daemon.py`. No other item in this plan touches
`track_daemon.py`, `tracking_schema.py`, `tracking_harness.py`,
`footage_census.py`, the ingest gate, or the ledger schema. If a later job needs
one, it waits for a2 to land.

The token is no longer a prose convention: account 1 created
`docs/evidence/SHARED_MODULE_TOKEN.md` while this plan was being written, and it
defines the real mechanism -- fetch and rebase on a clean tree, edit only that
file, commit only that file, push, and **the push is the lock**; release by
setting `holder: none`; an expired token may be overwritten. Take it before
dispatching item 4, in that exact form:
`holder: account2 | gap: G28b | taken: <ISO> | expires: +4h`. Its module list is
wider than the tracking one (it also covers `eval_gate/ledger.py`,
`backtest_runner.py`, `combo/fwer_budget.py`), which is correct: it is one token
across both registers, not one per account.

---

## 4. Blockers resolved in advance (decide these now, not at 2am)

### 4.1 CLIP is not installed, and the denominator does not need it
Three research questions (T2, K3, S2) and day item 7 were written around "CLIP
zero-shot shot-type classification". The pod has no `open_clip`, no `clip`, no
`transformers`, and "zero new dependencies" is a standing default.

**Decision: drop CLIP; the hand labels ARE the measurement.** The 300 hand
labels were only ever the validation set for CLIP; a seeded, evenly spaced
census of 300 frames per sport measures the rally / wide-view share directly and
reports it with a Wilson 95 pct interval, which is exactly what every later
coverage denominator needs. CLIP was a scaler, not the measurement. G34 is
therefore a pure labeling-and-counting lane with no dependency, no GPU and no
licence question, and it can run on day 1 instead of waiting on an install
decision. If whole-match scaling is wanted later it becomes its own row with an
explicit dependency decision attached.

### 4.2 Rule 2 (two attempts per gap) vs G17 v3 and G26 attempt 2
Rule 2: two attempts per gap, the second a LIMIT measurement. G17 has had two
attempts (colour heuristics, both rejected). PLAN section 4 calls v3 "the third
and last attempt by design", which reads as a rule-2 violation.

**Adjudication: G17 v3 IS the limit measurement, so rule 2 holds.** Attempts 1
and 2 were designs measured against no ground truth. v3 builds the 300-crop
labeled role set that has never existed and measures the achievable ceiling of
role classification on this footage. Failure closes G17 **AT LIMIT** and S1 is
never re-adjudicated. Same shape for G26: attempt 1 was a design (a stipulated
rectangle), attempt 2 measures where real-player feet actually land and derives
the prior from that. Both are second-and-final by the rule.

### 4.3 G31 is trained on ImageNet weights, which the sellable rail forbids
`tennis_keypoint_train.py` defaults to `ResNet18_Weights.IMAGENET1K_V1`; the
soccer row in the same program explicitly forbids torchvision ImageNet weights
and flags them research-only. Fold 0's checkpoint carries them.

**Decision: fold 1 runs unchanged so the two folds stay comparable, and the
memo carries a LICENCE line reading "research-only, ImageNet weights, not
shippable as trained".** The ship question is deferred to a separate row rather
than mixed into a measurement. Given fold 0's numbers (PCK 0.0774,
`frames_ge_4_in_7` 0.0), the likely honest outcome is CLOSED AT LIMIT, in which
case no shippable model is needed and the licence question dissolves. A
`--no-pretrained` re-run is only worth an id if fold 1 contradicts fold 0.

### 4.4 The `config.pod` ssh alias does not exist
The state doc forbids hardcoded ports and mandates an alias that is not in
`~/.ssh/config`. Today `-p 40048` answers.

**Decision: create the alias as the first act of tomorrow's session** -- a
`Host config.pod` block in `~/.ssh/config` carrying the host, port and user
(take the current values from `HANDOFF_TRACKING_ACCOUNT2_2026-09-02.md`; they
are not repeated here, see 4.6) -- then use the alias everywhere. Until it
exists, the hardcoded port is the only working route and the runbook line is
aspirational. The port has drifted once already, so the alias is the fix, not a
preference. Write the keeper name as `keep_track_daemo?.sh` in any ssh line; its
own pgrep self-clean kills a command line containing its name.

### 4.6 The pod host and port are published on the public origin
Measured today: the pod IP and SSH port appear in **14 tracked files** under
`docs/evidence/`, and this repo pushes to a public recruiter-facing origin. That
is a root SSH endpoint published in the clear. It is pre-existing, not
introduced by this plan, and this plan deliberately adds no fifteenth copy.

**Decision: do not fix it inside a tracking lane and do not quietly scrub it.**
Scrubbing 14 memos rewrites evidence artifacts, and the endpoint is already
public, so removal alone buys nothing without a key rotation and an access
policy. Route it to Neel as an ops decision and, once decided, to the harness
register (the `S` series, which owns the pre-push secrets hook at S28). Note it
in the day note so it does not get lost. The `config.pod` alias in 4.4 also
helps here: an alias is the mechanism that lets future docs stop naming the
host at all.

### 4.5 G31's fold count
The trainer supports folds 0 and 1 only; nyYk is never held out. **Decision:
report the 2-fold result honestly as a 2-fold result.** Do not silently call it
3-fold, and do not extend `split_fold` inside this lane -- if a third fold is
wanted after fold 1 lands, it is a new row.

---

## 5. The eight items (what each one must produce)

Each item's paste-ready spec is in `CODEX_SPECS_2026-09-04.md`. What follows is
the adjudication context the specs compress: why the item exists, what closes
it, and exactly what the verifier will apply.

### Item 1 -- G26 attempt 2, tennis player selection LIMIT (a5, pod)
Attempt 1 stipulated a court prior of x=[-6,84], y=[-4,40] ft. It drove oob to
0.0000 on all 15 ranges and 12 of 13 render-checked selections were real
players, but pass fractions collapsed 5/5,1/5,4/5 -> 1/5,0/5,1/5 because **real
players project outside that rectangle** and the frozen two-player coverage gate
then fails. The rectangle was guessed, not measured.

Attempt 2 measures it. On the 15 sequential ranges, dump every candidate's
projected foot point in court feet, hand-attribute the real players by render,
and take the prior from the empirical distribution of REAL-player feet (a
quantile envelope, not a guess). Then re-run the same 15 ranges.

**Acceptance (verifier applies exactly this):** pass fractions on the same 15
ranges not below **5/5 nyYk, 1/5 tennis09, 4/5 tennis10**; oob 0.0000 on all 15;
solver coverage **identical** per range to the attempt-1 table (proving the
solver was untouched); >=30 attributed foot points; 8 renders evenly spaced over
the still-failing ranges, never a head slice.
**Must not move:** every harness threshold, the seed 20260901, range count 5,
frame count 300, and the court solver / camera lock.
If the measured envelope cannot restore the before-fractions, that is
**CLOSED AT LIMIT** for a geometric prior and the honest finding is that
selection needs a role signal, not geometry.

### Item 2 -- G31 fold 1 and the held-out-match evaluation (a6, pod GPU)
Fold 0 is **already done** and its numbers are in section 1 row 4. The lane
starts at fold 1, not at fold 0. The question is not whether the model beats the
published 0.933 / 2.83 px ceiling -- at ~2k labels it will not, and that is
expected. The question is **whether it solves any frame the classical fails**.

**Acceptance:** a 2-fold table (held_out tennis09 and tennis10) of PCK@7px at
1280x720, median px, and the >=4-keypoints-within-7px solve proxy; the count of
frames solved by the model AND NOT by the classical on the same ranges, from the
committed `tennis_sequential_plan_2026-09-01/*.json`; 12 renders per fold,
evenly spaced; a LICENCE line naming the ImageNet weights as research-only; the
fold count reported as 2 with nyYk never held out.
Fold 0 already returns `frames_ge_4_in_7 = 0.0`, so the expected verdict is
**CLOSED AT LIMIT** at ~2k pseudo-labels. Report that plainly if fold 1 agrees.
Do not lower the 7px bar to manufacture a number.

### Item 3 -- G25b basketball floor-gate mask sanity (a9, pod)
G25 was rejected because the module trusts a mask it never checks. wnba_01 gets
99.18 pct of rows stamped `nonfloor` while 2,998 of 2,998 frames are flagged
tight_shot, and Climate Pledge Arena's two-tone floor makes the hue mask keep a
hardwood sliver and drop the green apron.

**Change:** per-game mask sanity. When the learned hardwood mask covers under
**15 pct** of the frame on more than **50 pct** of the game's frames, emit
`mask_unreliable` for that game and **tag nothing**. Add court-line density as a
second reference, ANDed with the hue mask before any `nonfloor` tag.
**Acceptance:** no game carrying `mask_unreliable` has a single `nonfloor` tag;
`containment_all` byte-identical before and after on all 8 games
(0.9827/0.9749/0.9424/0.9370/0.9489/0.9672/0.9576/0.9493); **24 renders across 3
arenas** including wnba_01, which had zero renders last time; additive only.
**Must not move:** the 15 pct and 50 pct constants once written, every harness
threshold, and `containment_all`.

### Item 4 -- G28b resolution siblings, duration first (a2, local, holds the token)
G28 was rejected because `max(source_height)` is height-only while 3 of the 4
real sibling pairs differ in DURATION: football 964.5 s (720p) vs 300.1 s
(1080p), wnba_01 962.1 vs 600.1, ncaa IB-_u4gW3ds 960.2 vs 600.1. Only
tennis_nyYk is time-aligned. The height-first rule would enqueue the short clip
and lose 664 / 362 / 360 seconds. Second defect: `canonical_game_id()` re-keys
the 4 single-variant suffixed clips and collapses a 300 s clip onto a 964 s
identity, where the "already tracked and passing" veto shadows it permanently.

**Change:** prefer **longest duration, then greatest height**; an **explicit
variant key** (never strip a suffix from an id that has no sibling); keep the
daemon landmine comments; additive columns only; **extract a helper** because
`track_daemon.py` is at exactly 300 lines.
**Acceptance:** all 4 sibling groups pick the long copy; the 4 single-variant
suffixed ids are unchanged; 28 daemon tests + 2 plan tests green;
`track_daemon.py` <= 300 lines after the change. `n = 4 (CONSTRUCT)` for the
sibling groups -- every case is enumerated, so the `n >= 30` sampling rail does
not apply (contract Q7).
**Start by cherry-picking tag `g28-reject-9ba9d395e`** -- a2 no longer points at
that work.

### Item 5 -- G17 v3 soccer role classifier, the LIMIT measurement (a8, pod GPU)
Two colour-heuristic attempts failed against no ground truth (delta -1.23 ->
+2.26, then +0.90 at 11.4 pct render disagreement against a 10 pct bar). v3
builds the ground truth first.

**Opus labels 300 crops by eye** into `docs/evidence/tracking/soccer_roles_labels/`
(3 classes: player / referee / other) drawn from the 100 packet frames and the
G08 stream windows, then codex trains a resnet18 with 5-fold CV and re-runs the
paired delta on the n=100 packet.
**Acceptance (pre-stated, never moved):** held-out crop accuracy **>= 0.90**
AND paired delta **|d| < 1.0** AND render disagreement **< 10 pct**. All three,
or the verdict is **CLOSED AT LIMIT** and S1 is never re-adjudicated.
**Licence:** do NOT use torchvision ImageNet weights (the same rail as 4.3) --
train from scratch or use a DINO (Apache) backbone. Anything SoccerNet-derived
entering the pipeline is a licence breach and an automatic reject.

### Item 6 -- G33 baseball scale-failure bins (a7, local)
9 of 36 pitch segments (25.0 pct) validate against the two-reference gate
(mound chord vs 24 in rubber, same image row, 10 pct). Nobody knows why the
other 27 fail, so nobody knows whether more day footage would help.

**Change: measurement only, no code change and no tolerance change.** Render 3
evenly spaced frames per segment (**108 renders**) and bin every one of the 27
failures into exactly one of: chord off dirt / rubber occluded / row mismatch /
not pitch view / 360p.
**Acceptance:** every one of the 27 failures carries exactly one bin; bins
reported as counts; the 10 pct tolerance byte-identical; renders evenly spaced
over all 36 segments, not the first 36 frames. `n = 27 (CONSTRUCT)`.
**This is the gate on G36:** if the bins are mostly 360p, more day broadcasts
buy nothing until the HLS route works (G27 recorded that access limit), and G36
should not be dispatched at all.

### Item 7 -- G34 view-share denominator, 3 sports (a3, local)
Every coverage number in this program is quoted against decoded frames, but a
fixed-camera lock only ever applies to rally / wide frames. Without the view
share, no limit is quotable. See 4.1: this is hand labels, not CLIP.

**Change:** a seeded, evenly spaced census of **300 frames per sport** (tennis
rally / non-rally; basketball wide / pan / tight; soccer wide / non-wide),
hand-labeled by Opus, reported as a share with a **Wilson 95 pct interval**.
**Acceptance:** 300 labels per sport, the sampling seed and frame indices
recorded so the census is reproducible, share + CI per sport, and an explicit
statement of which later denominators change. No model, no dependency, no GPU.
This is the row every future coverage claim cites.

### Item 8 -- G35 gap-finder pass (Opus lane, no worktree)
Sweep every "NOT VERIFIED" section in the memos landed since 2026-09-01 plus
the pod ledger, and file measured rows for what nobody has checked. Known
candidates already visible today: the 24 unviewed G08 renders and its
persistent-identity tally; whether the pod actually took the G22 deterministic
branch (the manifest records a static string, not the branch); the G12 keeps'
`coordinate_contract passed:false` cause strings (plan row B5); the stale G29
register row, which still reads OPEN although G29b landed at 7daae6c7c.
**Acceptance:** at least 3 new rows, each carrying a measured number and an
evidence path, allocated from `NEXT_GAP_ID` (G37+) by the orchestrator only.

---

## 6. Wave schedule

**Wave A, dispatch together at session start (6 codex, the cap):** items 1
(a5), 2 (a6), 3 (a9), 4 (a2), 6 (a7), 7 (a3). None of these blocks on another
and only item 4 touches a shared module. Confirm log growth within 2 minutes of
each dispatch; a log that never grows means the wrapper died, not that the job
is thinking.

**In parallel, Opus lane 1:** label the 300 soccer role crops for item 5. This
is the only thing gating wave B, so it starts immediately and does not wait for
a codex result.

**Opus lane 2 stays free as the verifier slot** (2 verifiers maximum, 1
preferred). Verify in completion order, not plan order.

**Wave B, as slots free:** item 5 (a8) once the 300 labels exist; item 8 (G35)
whenever an Opus lane idles; item 9 / G36 (a4) **only if** item 6's bins say
360p is not the dominant failure.

Sizing from the measured history: codex 15-50 min per job, verifier 5-25 min.
Six wave-A jobs plus six verifications is a full day. The budget numbers in the
five rules are ceilings, not targets: 8-12 codex jobs is a realistic day 1.

---

## 7. Arming recipe (first five minutes)

1. Create the `config.pod` ssh alias (4.4), then confirm the pod through it.
2. `sh scripts/platformkit/tracking/loop_status.sh` -- confirm daemon alive,
   capture alive, GPU free, `unpushed` count, and that no `cx_g*.log` is ALIVE.
3. Persistent **Monitor** on `/c/Users/neelj/AppData/Local/Temp/cx_g*.log`,
   DONE = an `EXIT:` line, **seeded with the 14 already-done logs** so their
   completion does not re-fire. An orphaned wrapper writes no `EXIT:`; that log
   is DONE when it has a `tokens used` line and has been quiet 4 minutes.
4. Fallback **cron every 29 minutes**: land DONE jobs (one verifier at a time),
   refill to at least 3 live codex jobs from the order in section 3, turn new
   "not verified" items into register rows, secrets-scan and push every third
   tick, check the pod daemon is alive. **Session crons expire after 7 days --
   re-arm every morning rather than assuming yesterday's survived.**
5. Dispatch wave A. Every landing writes one `RESULTS_LEDGER.md` line and one
   register row, no exceptions.

Sync a worktree before dispatch, and remember the amended rule 3: refuse the
reset on a **dirty** tree as well as on a non-empty `master..HEAD`, and lift the
refusal for a3/a4/a7/a8 once their commits are confirmed content-identical to
what already landed. Today all four are content-identical and all four are
clean, so all four are safe.

---

## 8. Stop runbook (end of day)

1. Delete the cron and the Monitor. Let running codex jobs finish or leave them;
   worktree commits survive a closed session.
2. Land anything a verifier can finish in under 20 minutes; mark the rest
   AWAITING VERIFIER in the register.
3. `git status` (nothing from `data/` or `vault/`), secrets-scan the range,
   `git fetch origin master && git rebase origin/master` on a clean tree, then
   `git push origin master`. **Never `--force`, never `git add -A`.**
4. Three-line note to `.planning/NOW.md` and to memory
   `tracking_week_program_2026_09_01`. Keep `MEMORY.md` under 200 lines / 25 KB.
5. Update `PLAN_TRACKING_RESEARCH_2026-09-03.md` with what actually moved.
6. Leave the pod daemon and the MLB book capture running. Never kill them.
7. Back up `data/cache/eval_gate/backtest_fwer.jsonl` (harness row S29).

---

## 9. What must not happen

Harness thresholds and gate values never move; a bar that cannot be met is
reported CLOSED AT LIMIT, never lowered. Denominators are decoded frames unless
a row says otherwise. Render-and-look before any claim, evenly spaced, never a
head slice. `image_px` rows never pass `court_feet`. No file reaches the pod
before a verifier accepts it (contract B5). `src/ kernel/ api/ intel/` are
human-gated: PROPOSED diffs only, and the basketball producer fix (G03) is
Neel's to apply, nobody else's. Per-file tests only; a full `pytest tests/`
freezes the box. ASCII on stdout. Explicit pathspec commits. No dollar, ROI,
profit or "edge" language anywhere, including in a memo aside. An honest FAIL,
REJECT, NULL or CLOSED AT LIMIT is a success and gets its own ledger line.
