# PLANNER A: in-game models, predictions and signals (Fable, 2026-09-29 ~23:4xZ; window ~00:00Z-05:00Z 09-30)

Calibration language only. Paper only. Facts come from this session's reads (register, plan docs, S542 replay, sweep, issue queue).

## State
- S439 has one receipt (09-24, MLB, 4 games, all INSUFFICIENT, B/C/D not reconstructible). The first FITTED night is 09-30, scored ~06:05Z 10-01; the 09-29 night refuses amendment_mismatch by design.
- S542 sealed verdict ACCEPT_STALENESS_BACKSTOP_ONLY: PROJ recovers staleness loss, never beats a fresh price. Recovery R decays with feed lag. NBA 2025-26 / 2024-25: L0 1.20 / 0.99; L18 0.89 / 0.69; L31 0.70 / 0.45; L60 0.30 / 0.02.
- Our state receipt lags the play by p50 21.4 s (p90 33.5 s). The book moved before our receipt on 50.4 pct of plays (control 42.9 pct).
- S544 (the sealed M2 reader of S439 outputs) is specced and amended; the Model 2.0 lead is building it. Arm E is effective 09-30, with the first fit ~10-04.
- NEW RISK: test_ingame_scoreboard_night_e2e.py::test_policy_fresh_process_byte_identity is RED on master.
  - Sweep 20:55Z: 1 failed / 7 passed, 192 MB, 40 s; the night's seal/legacy path; NOT in the quality lead's S570-S578 lists.
- Today's landings (S490 S494 S560 S580) left the 6 amendment IMPLEMENTATION_FILES untouched. S490 and S560 did touch S490-addendum dependency files (cross_venue_link, local_state_capture_sources, game_market_link).

## Work packages (ranked)

**M1 [P0] First-fitted-night pre-flight + identity freeze.** S439 support; the red test becomes S579 (quality block).
- Goal: 09-30 scores B/C/D, or the record says in advance why not.
- Executors: M1a = the QUALITY LEAD. M1b-d = ORCHESTRATOR 2, as an interrupt between rows, before 03:00Z. Fallback: a NEW Opus steward, only if free RAM >= 1.8 GB.
- (a) Classify the red test: stale fixed-base pin (landing lesson) or a real seal/legacy regression. Fix a real one before 06:05Z 10-01, two-commit rule only.
- (b) Run the read-only verify_amendment for nights 09-30 (PREREG + S490 addendum) and 10-01 on master HEAD. Paste ok or the named file.
- (c) Dry-run scoreboard_history --for-night 2026-09-30 into a scratch root. The window 09-23..09-26 overlaps the 09-25..28 outage; record completeness and rows per class. If it refuses, write "09-30 will be A-only because X" in NOW.md now.
- (d) Put an identity FREEZE in NOW.md until the 10-01 read-out (~07:00Z). Covered: the 6 identity files, the addendum dependencies, team_labels.py and the E-sealed modules. S498 lands after the read-out.
- Time 1:00. Done: (a) green or a root-cause row; (b) output pasted; (c) scratch receipt; (d) freeze line. RAM: test at free >= 1.5 GB; dry-run streams, 300 MB RSS cap, alone.

**M2 [P0] Morning read-out chain.** Rows S545 (landed), S544, S503.
- Executor: the MODEL 2.0 LEAD, after S544 lands (or while it is in verify).
- Command list in NOW.md "FOR paper-desk-improve / morning", in order: the S545 audit per receipt; the S544 reader after its seal; the S503 cumulative after it lands.
- Request that the scheduled-task owner add it to paper-desk-morning (12:51Z); never self-edit the task. Idempotence: rerun S545 on the 09-24 receipt; it must be byte-equal to the landed audit (RECONCILED 48/48).
- Time 0:40. Done: list committed, byte-equal rerun shown, request logged. RAM < 200 MB (streaming); after 06:00Z if free < 1.5 GB.

**M3 [P1] Seal S544 early.**
- Executor: the MODEL 2.0 LEAD, 0:30, after two tiers ACCEPT.
- Commit A = PREREG_M2 alone on UTC 09-30, effective 10-01 (10-18 stays the latest date); code in commit B. Proves the pipeline on MLB postseason nights before the NBA opener.
- MLB cells stay INSUFFICIENT by declaration through 2026 (A4): descriptive only, "vs own stale receipt".
- Done: the seal commit lands alone; the night 10-01 reader output exists on the 10-02 morning. RAM: construct tests.

**M4 [P1] Value-of-latency map (new, doc only).**
- Executor: the MODEL 2.0 LEAD, 0:30, handed to the CAPTURE-LATENCY LEAD.
- Map per-sport lag (S592 census; else the S550/S551 MLB numbers, others NO_DATA) onto the S542 R(lag) grid.
  - PROJ-STALE Brier, 2025-26: L0 -0.00181, L18 -0.00134, L31 -0.00106, L60 -0.00045.
  - Output: expected recovered staleness loss at a lag of 5 / 10 / 21 s for S593 (MLB push socket), S596 (NBA pbp primary) and S595 (NFL clock).
- It must state that PROJ trails a fresh price (L18 PROJ-FRESH +0.00046 [+0.00026, +0.00066]), so the fix is cadence, not a model.
- Done: a one-page table in docs/evidence/harness/, linked from S592. RAM < 100 MB.

**M5 [P1] S469: decouple the scoreboard seal from the live FEATURES dict.**
- Executor: ORCHESTRATOR 2, after S503 (S503 coordinates with S469).
- Goal: S482 / S487 / S546-S547 / E-block landings never kill a night with prereg_mismatch.
- Scope (register): a frozen literal snapshot in a sibling module. Constructs: a new FEATURES key does not move the seal; an arms/floor change does. PREREG_E follows.
- Build and verify tonight, park the commit; land after the 10-01 read-out (commit A alone on UTC day X-1). Time 2:30 (spec 0:40, build 1:00, two Opus tiers 0:50). Spec-only if S503 is not landed by 02:30Z.
- Done: two-tier ACCEPT on the parked sha; land dates in NOW.md. RAM < 200 MB.

**M6 [P2] Model 2.0 follow-up specs (S546-S549).**
- Executor: the MODEL 2.0 LEAD, 1:30.
- S546 NFL WP: a-priori (score difference, clock, down, distance, yardline). No fit until > 2 games (TNF 10-01, 10-04). Needs S502 and S595.
- S547 soccer Poisson remaining goals: 3-way, draw included. S490 and S541 have landed; fixtures resume ~10-09.
- S548 WNBA constants: WITHDRAW to 2027 (season ending; S491 deferred).
- Done: two specs with pre-build Opus critic verdicts; register updated. RAM: specs only; probes capped at 200 MB before 06:00Z.

**M7 [P2] Served-surface staleness truth (S504, orchestrator 2's block).**
- Executor: ORCHESTRATOR 2, after M5, 0:45. Dropped first if the current rows run long.
- Problem: MCP win_probability serves MLB Elo frozen at 07-12; served latest.json files are 07-19..07-27; predict_service cycle_count is 0.
- Fix: every envelope carries as_of plus a sealed-threshold STALE status. Edits only in scripts/platformkit/mcp_server; api/ changes go as a PROPOSED diff.
- Done: a construct test in which mlb returns as_of 2026-07-12 and status stale.

**M8 [P3, optional] Signal test-path manifest (doc).**
- Executor: whichever lead finishes early, 0:45.
- Map the 86 registry rows and 60 SPA classes to their only valid test path (an S439 C/E block via S503, pregame DM vs close, or NOT_TESTABLE); residual features on a fresh mid are already rejected (S540 P4). Done: zero rows without a path.

## Totals and deferrals
- Totals:
  - ORCHESTRATOR 2 (after its S496/S498/S502/S503): M1b-d 0:30 + M5 2:30 + M7 0:45 = 3:45.
  - MODEL 2.0 LEAD (after S544): M2 + M3 + M4 + M6 = 3:10.
  - QUALITY LEAD: M1a 0:30.
  - No new lead unless M1 misses 03:00Z (RAM: about 1.3 GB free, 6 leads).
- NOT TONIGHT:
  - S482 NBA arm E (needs an NBA live-night census; E unproven until ~10-04); S487 (deferred).
  - M2 live serving in the S515 recorder: after the seal and the owner's start.
  - predict_service relaunch and S448 (owner decisions); real-archive runs over 200 MB (S498 census, replays) wait until after 06:00Z.

## Top 3 failure modes and guards
1. **The 09-30 first fitted night comes out A-only or refused again.**
   - Causes: seal identity drift (the red test; S498 or other identity/addendum/E-file landings); an outage-hit history window; the RAM floor; an OS-sleep capture death.
   - Guards: M1 (verify_amendment, history dry-run, freeze); S501 deferral and the S500 tick relaunch; M5 for later nights.
2. **Latency-contaminated or mislinked ticks are read as signal.**
   - Causes: state 21.4 s late, with the book moving first on 50.4 pct of plays; terminal ticks scored 'late' (S545: 9 on 09-24); ESPN rows with null start/date linking on teams alone (S502; TNF 10-01, soccer).
   - Guards: the S545 audit on every receipt (M2); S544 fresh/stale labelled "our receipt age"; the event-aware anchor (M2 = mid when the book moved after the play); S502 before 10-01; M4 aims the latency work.
3. **Over-reading 3-4 MLB games a night.**
   - Causes: arm A called devigged; ACCEPT_STALENESS_BACKSTOP_ONLY read as beating the market.
   - Guards: unchanged 30-game / 5-cluster floors; MLB M2 INSUFFICIENT by declaration through 2026; S503 SINGLE-WINDOW labels; S495 relabel; every memo says PROJ trails a fresh price; the no-edge rule.
