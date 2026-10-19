# Five-hour plan, 2026-09-30 00:00Z-05:00Z (Fable synthesis of four Fable planners)

The owner asked (2026-09-29): "use a lot of Fable next 20 minutes to plan ... what needs to be done ... then keep working with Opus to do everything that was planned, work hard for the next 5 hours."

The four sections are verbatim in this folder:
- FIVE_HOUR_PLAN_2026-09-30_A.md: in-game models and signals.
- FIVE_HOUR_PLAN_2026-09-30_B.md: execution and live paper.
- FIVE_HOUR_PLAN_2026-09-30_C.md: capture, reliability, quality.
- FIVE_HOUR_PLAN_2026-09-30_D.md: per-sport readiness calendar.

This file is the binding merge: the dispatcher's rulings, the executors, the order, the RAM windows and the freeze. PAPER ONLY; calibration and execution-quality language only.

## The one thing that matters most
The 09-30 night runs at ~06:05Z on 10-01. It is the first night whose fitted in-game arms (B/C, mlb and soccer under PREREG_2026-09-30) are scored, and the first night arm E is effective. Its successful receipt gates S492 commit B (NFL), and NFL fitting from 10-04 depends on commit B. Every package below either protects that night or does not risk it.

## Dispatcher rulings (checked in code or on master this session)
1. **The supervisor's `--min-free-mb` measures FREE DISK, not RAM** (`capture_supervisor.py:74`, `:205`, shutil.disk_usage).
   - Sections C and D said "supervisors refuse children below 2,000 MB RAM". That is WRONG, and so is D's R4 proposal to raise restart gates to 2.1 GB RAM because of it.
   - The restart RAM gates stay at 1.5 GB. C5(b) is dropped as a fault case.
2. **Seal selection on master (read-only select(), 23:5xZ):**
   - 2026-09-29 refuses amendment_mismatch (by design, expected).
   - 2026-09-30 selects PREREG_2026-09-30 [mlb, soccer].
   - 2026-10-01 selects PREREG_2026-09-30, until commit B adds the PREREG_2026-10-01 entry.
   - D also verified the identity files match both seals under CRLF normalisation.
   - So M1(b) is DONE. The red test (`test_ingame_scoreboard_night_e2e.py::test_policy_fresh_process_byte_identity`) is most likely a stale pin, but M1(a) classifies it and it must not be assumed.
3. **Live recorder B1.** The owner approved a start only once the recorder is landed, measured at 150 MB or less, AND free RAM is at least 2 GB. It is also after 00:00Z (the first pitch was 00:00Z), and the classifier blocked the last lead's launch attempt.
   - So EXEC-LIVE runs B1 only if free RAM >= 2 GB AND the classifier allows the bounded run. Otherwise it skips B1 and records why.
   - Supervised live recording for 09-30 PHI@ATL (18:00Z) needs the OWNER to run the committed launcher.
4. **IDENTITY FREEZE, from now until the 10-01 read-out (~07:00Z 10-01):**
   - No landing may touch the 6 scoreboard identity files, the S490 dependency-addendum files, team_labels.py, or arm-E-sealed modules.
   - S498 and S469 build and verify, then PARK. They land after the read-out with the two-commit pattern.
5. **Capture-file landing order (binding):**
   - S561 (the 08:37Z one-shot cherry-pick), then S598 (rebased onto the S561 commit), then S531.
   - S594 only after S535.
   - One capture restart per capture per window, only 06:00Z-16:00Z, only with no served game within 60 min.
6. **RAM windows.** Pause every lead process over 200 MB, and the per-file sweep, during:
   - 04:20Z-04:50Z: the state2 restart adopting S490/S494;
   - from 05:40Z until docs/evidence/forward/nights/2026-09-29.json exists undeferred;
   - 08:20Z-08:50Z: the S561 books restart.
   The sweep's remaining files run only 06:00Z-18:00Z with a 2.5 GB start gate.

## Executors and packages, ranked. Each executor's total is at most 5 h.

**NEW Opus EXEC-LIVE lead.** Owns S517-S519 and S557-S559 (transferred from the finished orchestrator 4 and Execution 2.0).
- B1: conditional, per ruling 3.
- B3: seal the S519 prereg, alone.
- B4: an S558 PROPOSED diff wiring S516/S551/S550 receipts into the tick. Tick files are not edited.
- B7: the S551 reachability projection.
- B6: the S550 rolling receipt for 09-27..29.
- B2: S517 launcher review plus the capacity record; the owner commits and runs it if the commit is blocked.
- B5: the first PROVISIONAL S516 receipt, if B1 ran.

**NEW Opus RELIABILITY lead.** New ids S601-S610.
- C1: HEARTBEAT TRUTH in capture_watchdog.py: `now` taken after the read, a null last_adapter_error treated as no error, a byte-bounded books tail.
- C6: queue hygiene. Link every P1, and write specs for the improve run: a dated legacy exclusion for the 09-24/25 census, an orphan_writer re-poll, a terminal close for past-day schedule_missing.
- C7: the "what survives the app closing" table.

**NEW Opus READINESS lead.** New ids S611-S620.
- R1: a commit-B pre-flight candidate in a NEW worktree, merging the test_s485_baseline_contract re-pin with BOTH S501 and S496 edits. It does not land.
- R2: the cross-sport served-capacity table for 10-01..10-06 plus the "if necessary" games. It goes to the soccer lead's S531 acceptance.
- R3: a scratch D1 rehearsal for soccer and nba, with a per-sport isolation proof. The config diff is posted FOR paper-desk-improve, advised to land 10-02..10-05.
- R6: tennis go/no-go.
- R7: an NBA preseason checklist, handed to the capture-latency lead.

**ORCHESTRATOR 2, next packages** after its current rows:
- M1(c): a scratch dry-run of the scoreboard history step for 09-30 (the window overlaps the 09-25..28 outage). Streaming, 300 MB cap, outside the RAM windows.
- M5: S469 built, verified and PARKED.
- M7: S504 staleness envelopes.
- Publish the S503 per-game loss interface for S519.

**MODEL 2.0 lead (Fable), next:**
- M2: the morning read-out chain (S545, then S544, then S503), requested FOR paper-desk-morning.
- M3: seal S544 early, alone, effective 10-01.
- M4: the value-of-latency map, handed to the capture-latency lead.
- M6: specs for S546 (NFL WP) and S547 (soccer Poisson). S548 is withdrawn to 2027.

**QUALITY lead, next:**
- M1(a): classify the red scoreboard-night e2e test before 03:00Z (S579).
- C3: the 13 unrowed non-green files, in night-path order. The live_edge files only after 06:00Z.
- Pause the sweep in the RAM windows.

**CAPTURE-LATENCY lead, next:**
- Follow the ruling-5 order.
- C4a: the S563 probe at 03:30Z or later.
- C4b: the S595 spec (the NFL play clock, from MNF 401872963).
- C4c: the S597 spec (real-time tape).
- The books-runner memory growth: 61 MB to 691 MB in 9.5 h.
- R7's preseason checklist.
- Specs only for S593, S596 and S564.

**SYSTEM-TEST lead, next:** C5 cases (a), (c) and (d), plus a low-RAM night rehearsal. Case (b) is dropped per ruling 1.

**SOCCER-READINESS lead, next:**
- Pull S535 (the per-route ESPN deadline) ahead of TNF 10-02.
- S531 acceptance must include "no MLB/NFL displacement", using R2's table.
- S534: verify the S490 addendum still covers the 10-01 seal, after S560 refreshed its cross_venue_link hash.

**DISPATCHER heartbeat, each beat until commit B:**
- R5: seal-drift check. select() for 09-30 and 10-01 must still pick the expected seals.
- Read the heartbeat-file ages directly; the watchdog verdict is blind until C1.
- Enforce the RAM windows.
- Log the 09-29 night's amendment_mismatch as EXPECTED.

## Calendar (UTC; from section D)
- 04:37Z 09-30: state2 adopts S490/S494.
- 06:05Z: the 09-29 night.
- 08:37Z: S561 plus the books restart.
- 12:00Z: the tick writes D1(10-01).
- 18:00Z and 21:00Z: MLB Game 2s.
- 06:05Z 10-01: the FIRST FITTED NIGHT, which gates S492 commit B (target 10-01 14:07Z, hard stop 10-04 06:05Z).
- 10-02: TNF.
- 10-05: the first fitted NFL night.
- 10-08 12:00Z: soccer config, S531 and S535 adopted.
- 10-09..12: soccer.
- 10-19 12:00Z: S562 and S564.
- 10-20: NBA.
- Tennis blocked; WNBA 2027.

## Needs the owner
1. Commit and run docs/operations/relaunch_live_shadow_2026-09-29.ps1 before 18:00Z 09-30, with free RAM >= 2 GB.
2. Keep the app open and the laptop awake through 08:37Z 09-30 (the session one-shots), or run those relaunch scripts by hand between 04:00Z and 16:00Z.
3. Leave RAM free for the 06:05Z 10-01 first fitted night.
4. Optionally set sleep = never on AC and/or WakeToRun for the tick.
5. Log codex back in before 10-05.
