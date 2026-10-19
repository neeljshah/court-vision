# PLAN B -- execution and live paper betting (Fable planner B, 2026-09-29 ~23:5xZ)

PAPER ONLY. Execution-quality and calibration language only. Every number below was re-read from a file this session.

## Where the area stands
- Execution 2.0 lead and orchestrator 4 are both DONE, so nobody owns S517-S519 or S557-S559. The dispatcher should transfer both blocks to ONE new Opus lead, "EXEC-LIVE", and record the transfer on the RESERVED BLOCKS line.
- Landed: S515 recorder (057cec920), S516 fill receipt (fa99c29cd), S550 ruler (receipt 2026-09-22_2026-09-26.json), S551 replay + PREREG_S551.json. The S551 prereg is sealed: first eligible date = seal UTC date + 1 = 2026-09-30; floor 30 paired games; exactly one confirmatory look; Holm over 4 arms.
- Nothing records live. data/cache/live_shadow/ and docs/evidence/forward/live_shadow/ do not exist on main. The launcher docs/operations/relaunch_live_shadow_2026-09-29.ps1 is untracked (the classifier denied running and committing it). The newest night receipt is 2026-09-26 (PARTIAL), and markouts/ is empty.
- Tonight's served game is mlb 849851 BOS@NYY, first pitch 2026-09-30T00:00Z. It is in the 09-30 schedule, so it is S551-eligible. CWS@HOU (21:00Z) may still be live at the start. On 09-30, PHI@ATL (18:00Z) and CWS@HOU (21:00Z) barely overlap.
- Red on master in this area with NO row (from the sweep file): test_live_shadow_fills_memo.py::test_case22_inventory (the S516 memo sha table), test_forward_capture_stream_integration.py [s389], and test_ingame_scoreboard_night_e2e.py::test_policy_fresh_process_byte_identity. S572 and S577 already cover capture_book_adapter, paper_account, focus_window and touch_queue.

## Work packages, ranked. Executor for all: the NEW Opus lead EXEC-LIVE (a single executor, sum 5:00)

B1 LIVE SHADOW RUN ON BOS@NYY (covers S515/S517). Time box 0:15, plus 4 checks of 5 min.
- FIRST ACTION, before 00:00Z (p0 freezes only from pre rows before first pitch): start this in the background, bounded, not via WMI:
  `python -m scripts.platformkit.execution.live_shadow_quoter --sports mlb --every-s 15 --until 2026-09-30T04:15:00Z --books-root data/cache/ingame_books_local --state-root data/cache/ingame_state_local_v2 --schedules-root docs/evidence/forward/schedules --out-root data/cache/live_shadow --min-free-mb 1500`
- Add a 10 s psutil sampler (peak RSS, CPU, loop latency) writing to a scratch file, and record the capture supervisor PIDs before and after. If the start slips past 00:00Z, run anyway: the mid arm is still valid, and the blend arm's p0_missing refusals are recorded as the honest outcome.
- Done when: rows for 849851 (and CWS@HOU if it is live) run from before first pitch to the final; refusals are tallied by a script; peak RSS <= 120 MiB; reads <= 4 MB per tick; capture PIDs are unchanged.
- RAM: about 70 MiB. Below 1,500 MB free, every tick becomes low_ram_skip, so the dispatcher must keep free RAM >= 1.6 GB from 00:00Z to 03:30Z.

B2 S517 FINISH: LAUNCHER REVIEW, AMENDMENT, CAPACITY RECORD (covers S517). Time box 1:30, split 0:45 during the game and 0:45 after B1 ends.
- Review the ps1 against the code:
  - Is $freeMb a RAM reading? capture_supervisor --min-free-mb is DISK free.
  - Does the entrypoint (live_shadow_quoter.py:288) reach the CLI main?
  - The OS single-instance lock collides with B1, so the owner launches only after B1's --until.
  - Check the python path, the STOP file and the stale-lock rename.
- AMENDMENT 1: the S517 criterion "2 simultaneous live games for >= 30 min" rarely occurs in the MLB postseason slate. Replace it with B1's observed live window plus a --replay-start 2-game load run over the 09-29 PHI@ATL and CWS@HOU shards.
- Done when: docs/evidence/forward/live_shadow/CAPACITY_2026-09-30.md is committed, every criterion marked PASS, FAIL or NOT-MEASURED from script tallies; two Opus tiers (contract + adversarial) ACCEPT; the ps1 is committed. If the classifier denies the commit, write OWNER NEEDED: commit and run the ps1 before 2026-09-30 17:40Z so PHI@ATL gets a pre-first-pitch p0.
- RAM: under 100 MB.

B3 S519 PREREG SEAL: prospective cumulative calibration of the two recorded probabilities (covers S519). Time box 1:15, from 00:15Z.
- Prereg content: arms = the recorded venue mid vs venue_prior_state_blend; per-game paired Brier and log-loss on the settled outcome; every decision and refusal counted independently of fills; dedupe by (game, arm, run identity); floor 30 games and at least 5 clusters; one confirmatory look; first eligible date = seal UTC date + 1.
- Reuse the S551 prereg shape and seal_provenance (the S591 fix has landed). The reader waits for S503's cumulative-evaluator interface (orchestrator 2), so S519 emits S503-shaped per-game losses instead of building a second evaluator.
- Done when: the prereg JSON is committed ALONE; the seal check returns rc 0; an Opus pre-build critique is folded in as AMENDMENT 1; the register row reads "SEALED <sha>; reader after S503". RAM: negligible.

B4 CONNECT THE EXECUTION RECEIPTS TO THE UNATTENDED DESK (new: S558). Time box 0:30.
- Today nothing runs S516, S551-scored or S550 nightly, and nothing watches a live_shadow heartbeat.
- Write a PROPOSED diff (tracked twin under docs/evidence/harness/) for the S500/S510-owned files, adding for D-1:
  1. the S516 receipt once the drain covers the window (a PROVISIONAL label is allowed);
  2. the S551 --mode scored run, only above the paper-night RAM gate (peak 336 MiB);
  3. a weekly S550 rolling receipt;
  4. a live_shadow heartbeat / tick-silence issue kind.
- Done when the proposal is committed, a FOR paper-desk-improve line is in NOW.md, and S558 is registered. Do NOT edit paper_desk_* or paper_night files.

B5 FIRST S516 RECEIPT FOR THE B1 RUN (covers S516). Time box 0:30, from about 04:15Z.
- Done when: docs/evidence/forward/live_shadow/2026-09-30.json is committed with per-arm quotes, fills and fee-netted markouts (PROVISIONAL expected: the tape lags about 2 h); a FOR paper-desk-improve line asks for the FINAL re-run after the drain; it is quoted only as "PROVISIONAL, n = 1 game, INSUFFICIENT".
- RAM: 27 MiB in the probe; full-night RSS is unmeasured, so record it.

B6 S550 ROLLING RECEIPT 2026-09-27..29 (covers S550). Time box 0:15, after 02:30Z (after the CWS@HOU tape drain).
- Done when: exec_quality/2026-09-27_2026-09-29.json is committed; two runs are byte-identical; the per-game census is included (PHI@ATL expected TAPE_MISSING, focus lost 18:59:58Z; this feeds S598). RAM: 52.5 MB.

B7 CAN S551 EVER REACH ITS ONE LOOK? (new: S557; fold S553). Time box 0:30. Dropped first if the lead runs over.
- Project tape-complete paired games per week from the served slate and the S550 census rate (8 OK of 11 in-game games; at most 2 served per hour).
- If fewer than 30 by the end of the MLB postseason: allocate S557 for an NBA prereg addendum sealed before the 10-19 D1. Mark S553 COVERED-BY S550 + S592, as S543 was.
- Done when the register carries the projected look date, or "never on MLB alone".

DEFERRED, with triggers:
- S552: once S551 has 30 or more tape-complete paired games.
- S554: stays OFF until S519 or S544 shows an in-game probability at least matching the mid prospectively (Gate A0 and S542 say it trails today).
- S555: after S552, plus verified fee precision (venue_fees.py:8).
- S518: NBA spec before 10-19.

HANDOFFS (NEXT packages of running leads):
- Quality lead: the 3 unrowed reds above.
- Capture-latency lead: S597 real-time tape gates any non-PROVISIONAL live fill receipt.
- Orchestrator 2: publish the S503 per-game loss interface for S519.

Order (UTC): 23:5x B1 | 00:15 B3 | 01:30 B4 | 02:00 B7 | 02:30 B6 | 02:45 B2a | 04:15 B2b, then B5.

## Highest-risk failure modes (tonight and 09-30)

1. RAM starvation.
   - The risk: about 1.3 GB free with 6 leads. B1 then records only low_ram_skip, and the 06:05Z 09-29 night defers (exit 4). S520(b) journals the deferral as child_failed with a 3 h backoff, so the receipt chain stalls again (the last COMPLETE night is before 09-24).
   - Guard: free RAM >= 1.6 GB from 00:00Z to 03:30Z. The heartbeat cron dispatches nothing new after 05:30Z until nights/2026-09-29.json exists undeferred. No S551 replay (336 MiB) runs in the window. Every EXEC-LIVE process stays under 120 MiB.
2. No live record on 09-30.
   - The risk: the supervised launch is owner-gated by the classifier. Without the ps1 run by 17:40Z, PHI@ATL gets no intents and no blend p0.
   - Guard: B2 fixes the ps1 before the owner sees it, and OWNER NEEDED carries the exact command and deadline. B1's --until frees the lock by 04:15Z. The mid-anchored nightly replay stays the labelled fallback record.
3. PROVISIONAL or exploratory numbers read as results.
   - The risk: the tape arrives about 2 h late, so S516 stays PROVISIONAL and S551 may never reach 30 paired games. That leaves a temptation to cite S550's 13.5 pct engine fill or S551's 09-24 -1.90c as findings.
   - Guard: only a sealed confirmatory look (S551, S519) is a result. Everything else is labelled exploratory, PROVISIONAL or INSUFFICIENT, with n. The preflight vocabulary gate runs on every memo and receipt. B7 says plainly when a look is unreachable. S597 owns the tape gap.
