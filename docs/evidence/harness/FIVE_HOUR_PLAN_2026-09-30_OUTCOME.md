# Five-hour plan 2026-09-30 00:00Z-05:00Z: outcome scorecard

Scores docs/evidence/harness/FIVE_HOUR_PLAN_2026-09-30.md against master
`git log --since=2026-09-30T00:00Z` (commit dates print as -05:00 local; 19:00-05:00 = 00:00Z),
.planning/NOW.md lines 6205-end, and the nba-harness-h* worktrees. Written by O8 in a
9-minute wrap-up: cells marked UNKNOWN were not resolvable from those sources in time.
PAPER ONLY; calibration and execution-quality language only.

## Package table

| package | executor | planned outcome | ACTUAL | evidence |
|---|---|---|---|---|
| B1 | EXEC-LIVE | bounded live recorder run if RAM >= 2 GB and classifier allows | UNKNOWN (S517 AMENDMENT 1 cites "capacity record from the bounded B1 run"; whether it ran or skipped is not stated in a subject) | 0abd6a4be |
| B2 | EXEC-LIVE | S517 launcher review + capacity record | LANDED (launcher committed, owner-run) | bd5caac48, 0abd6a4be |
| B3 | EXEC-LIVE | seal S519 prereg alone | LANDED (sealed alone) | e0e8a3c35, register 8f426ca3d |
| B4 | EXEC-LIVE | S558 PROPOSED diff wiring receipts into the tick | SPEC ONLY (S558 registered as PROPOSED; no diff commit found) | 4ac765fad |
| B5 | EXEC-LIVE | first PROVISIONAL S516 receipt if B1 ran | UNKNOWN (no master commit; S516 builder wt h181 3ba0cb30e predates the plan) | /c/Users/neelj/nba-harness-h181 |
| B6 | EXEC-LIVE | S550 rolling receipt 09-27..29 | LANDED | 36f098e9b |
| B7 | EXEC-LIVE | S551 reachability projection | LANDED as a register finding (look unreachable on MLB alone) -> S557 SPEC ONLY + AMENDMENT 1 | 4ac765fad, c7fb7c028, cfb02653e |
| (extra) S518 | EXEC-LIVE | not in plan | VERIFIED+PARKED h281 22b05fb04 (land after 10-01 read-out) | 0bfba7745 |
| C1 | RELIABILITY | heartbeat truth in capture_watchdog | LANDED S601 d248930ea (DONE-check 6063f8544); follow-on S607 LANDED 181e18e51 | 72b046457, f6dabe0ac |
| C3 | QUALITY | 13 unrowed non-green files | LANDED as triage memo (776 swept, 50 non-green all classed); fixes S578 ca6f67866, S634 7216e1813, S636 aeb504c5c, S638 1d9de93e7 LANDED | ab76a6555, 92b8535f5, 19003dd36 |
| C4a | CAPTURE-LATENCY | S563 probe >= 03:30Z | SKIPPED: closed not reproduced (WNBA finals delivered by default scoreboard) | 1d996bd75 |
| C4b | CAPTURE-LATENCY | S595 spec (NFL play clock) | LANDED (went beyond spec) 0f37baf85 + fix-forward 1952b3f58 | a3b20a33e |
| C4c | CAPTURE-LATENCY | S597 spec (real-time tape) | SPEC ONLY (part 2 measurement gate) | e21c084da |
| C4 books RSS | CAPTURE-LATENCY | books-runner memory growth | LANDED S599 part 1 914d743a5 | 1bf69decc |
| C4 specs | CAPTURE-LATENCY | specs only S593/S596/S564 | SPEC ONLY (all three) | fb610147c, e21c084da |
| C5 | SYSTEM-TEST | cases (a)(c)(d) + low-RAM night rehearsal | LANDED S581 f4169ddfe (34 fault cases); cases 18/23/28 still DEFECT -> S585-S587; S588 extension SPEC ONLY, parked | 5547259e5, 3a47241a1, ffaec924d |
| C6 | RELIABILITY | link P1s; legacy census exclusion; orphan_writer re-poll; past-day schedule_missing close | LANDED: S602 ed0826e56, S603 f5f32d00c, S604 dae935680, S605 30f398b41 | 1fe76ba9b, edf444714, 4edfb2633, f3dabc597 |
| C7 | RELIABILITY | "what survives the app closing" table | LANDED in NOW.md (read-only for O8) | .planning/NOW.md "WHAT SURVIVES THE APP CLOSING (C7)" |
| (extra) S606 | RELIABILITY->capture | UTC-rollover state stall (found 00:1xZ) | LANDED dd9867dea | 8f1913698 |
| R1 | READINESS | commit-B pre-flight candidate, not landed | VERIFIED+PARKED h300 2aee65757 (gated on 10-01 receipt + S503 parser fix) | .planning/NOW.md (09-30 block) |
| R2 | READINESS | cross-sport served-capacity table 10-01..10-06 | LANDED (with correction: D1 days are UTC dates); S611 67d45f4f5, S612 148dee461 LANDED; S613 PARKED h320 a1205d333 | eb15edcb2, 081b68ea6, 5148b6695 |
| R3 | READINESS | scratch D1 rehearsal soccer+nba with isolation proof | UNKNOWN (eb15edcb2 mentions "rehearsal D1 10-01"; no soccer/nba rehearsal artifact found) | eb15edcb2 |
| R6 | READINESS | tennis go/no-go | LANDED: NO-GO, S493 tennis deferred to 2027 | 364a28fba |
| R7 | READINESS | NBA preseason checklist to capture-latency | UNKNOWN | - |
| M1(a) | QUALITY | classify red scoreboard-night e2e before 03:00Z | LANDED (S579 RECORDED) | 3a3024e8e |
| M1(b) | dispatcher | seal selection | DONE before window (ruling 2) | FIVE_HOUR_PLAN_2026-09-30.md |
| M1(c) | ORCH 2 | scratch history dry-run for 09-30 | LANDED (2,585 mlb training rows from 6 games) | 2cac212ca |
| M2 | MODEL 2.0 | read-out chain S545 -> S544 -> S503 | S545 built h212 bcd8787be (landed state UNKNOWN from subjects); S503 LANDED e50e1873f; S544 LANDED | e50e1873f, b71de346d |
| M3 | MODEL 2.0 | seal S544 alone, effective 10-01 | LANDED commit A 03c288979 (PREREG_M2 alone) + commit B 885f7dde6 | b71de346d |
| M4 | MODEL 2.0 | value-of-latency map | LANDED e76c38ae8 | docs/evidence/harness/INGAME_M2_LATENCY_VALUE_MAP_2026-09-30.md |
| M5 | ORCH 2 | S469 built, verified, PARKED | SPEC ONLY (REVISION 2 + AMENDMENT 1; build not seen) ; companion S625 VERIFIED+PARKED h322 5893deb5f | 34b319dc7, a8aa28b8a, 4fbb66e96 |
| M6 | MODEL 2.0 | S546 + S547 specs; S548 withdrawn | SPEC ONLY (both + AMENDMENT 1); S548 WITHDRAWN | 147ecb556, b6e7d8827, 87252c50c |
| M7 | ORCH 2 | S504 staleness envelopes | NOT STARTED (no S504 commit or wt found) | - |
| M8 (S503 loss interface for S519) | ORCH 2 | publish per-game loss interface | UNKNOWN (S503 LANDED e50e1873f; interface publication not separately evidenced) | e50e1873f |
| S498 | (freeze: build+park) | build, verify, PARK | NOT STARTED (no commit or wt found) | - |
| S561 | CAPTURE-LATENCY | 08:37Z one-shot cherry-pick | VERIFIED+PARKED h232 c4bd924c4 (rebased; one-shot 08:37Z) | /c/Users/neelj/nba-harness-h232 |
| S598 | CAPTURE-LATENCY | after S561 | VERIFIED+PARKED h271 (AMENDMENT 4 c590c4c5f; ff helper committed bb778d15f) | bb778d15f |
| S531 | SOCCER | acceptance incl. no MLB/NFL displacement via R2 | SPEC ONLY for the input (S624 NFL serving proposal posted FOR S531); S531 itself not landed | 7ffd36f4f, 4fbb66e96 |
| S535 | SOCCER | per-route ESPN deadline ahead of TNF | LANDED e4753a05d | 79a36baea |
| S534 | SOCCER | verify S490 addendum covers 10-01 seal | VERIFIED, NOT LANDED (land window 07:00Z 10-01 .. before 10-08) | f20a967ae |
| S594 | CAPTURE-LATENCY | only after S535 | NOT STARTED (no commit found) | - |
| dispatcher R5 / heartbeat | Fable dispatcher | seal-drift check, heartbeat ages, RAM windows | UNKNOWN per beat (heartbeat cron f2aaebe0 listed in C7 table; no per-beat receipt found) | .planning/NOW.md C7 table |

## Calendar deltas
- 04:37Z state2 adoption of S490/S494 MISSED: the one-shot never fired (session busy; MLB BOS@NYY still live at 04:51Z). Re-armed 07:57Z via relaunch_state2_s535_2026-09-29.ps1, which also adopts S535 + S606.
- S561 rebased to c4bd924c4 (the old sha conflicted on .gitattributes); one-shot stays 08:37Z.
- The plan's "22:00Z CWS@HOU" is 21:00Z in the served schedule (plan calendar already says 18:00Z and 21:00Z Game 2s).

## Carried to the improve run (ordered)
1. Protect the 06:05Z 10-01 first fitted night; then S492 commit B from h300 2aee65757 (after the receipt + S503 parser fix).
2. Confirm the 07:57Z state2 adoption and the 08:37Z S561 books restart; then S598 (h271), then S531; S594 after S535.
3. Post-read-out landings under the two-commit pattern: S518 (h281), S625 (h322), S469 (build still owed), S498 (not started), S534, S613 (h320).
4. S581 DEFECT cases 18/23/28 -> S585-S587; S588 extension build.
5. S504 staleness envelopes; S558 PROPOSED diff; S557 build after capacity precondition; S516 provisional receipt.
6. Resolve the UNKNOWNs: B1 ran/skipped, R3 soccer/nba rehearsal, R7 checklist, S545 landing, S503 loss interface.
7. S642 issue-ledger replay skip-and-count (opened 23:08-05:00); S637/S640/S641 specs.

## Needs the owner (plan list; changes marked)
1. Commit and run docs/operations/relaunch_live_shadow_2026-09-29.ps1 before 18:00Z 09-30 with free RAM >= 2 GB. CHANGED: the S517 launcher is now committed (bd5caac48); the owner still runs it.
2. Keep the app open and laptop awake through 08:37Z 09-30, or run the relaunch scripts by hand 04:00Z-16:00Z. CHANGED: the 04:37Z one-shot missed; state2 now re-armed for 07:57Z.
3. Leave RAM free for the 06:05Z 10-01 first fitted night. Unchanged.
4. Optionally set sleep = never on AC and/or WakeToRun for the tick. Unchanged.
5. Log codex back in before 10-05. Unchanged.
