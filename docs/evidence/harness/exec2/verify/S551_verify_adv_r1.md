VERDICT: REJECT
S551 adversarial verifier, round 1 (Opus; codex down). Candidate: uncommitted files in C:/Users/neelj/nba-harness-h222 (not edited).
Scratch artifacts: s551adv_setup.py (builds a mirror), s551adv_mut.py (mutations), s551adv_trunc.py, s551adv_oldsnap.py, s551adv_rss.py, s551adv_real2/ (exploratory 09-24 run).

## Reproduction
- Candidate tests, one file at a time: cancel_policy 17 passed, replay 12 passed, prereg_report 10 passed.
- Real day 2026-09-24, EXPLORATORY, output under scratchpad: rc 0; 4 games OK, 3 tape-complete, 1 tape_provisional; every cell INSUFFICIENT; peak RSS 335.8 MiB (psutil poll at 0.2 s); wall 39.7 s.

## BLOCKING
B1. In displayed_depletion, a quote with a refused snapshot silently reads its queue from an OLDER snapshot. Spec item 6 says the replay never passes an older row, and item 1 says refusals are counted.
- Where: exec_policy_replay.game_inputs (lines 219-228) drops a to_fill_snapshot (and to_mark_tick) refusal with no counter. phase2 then passes the snapshots of the other quotes' decision instants. simulate_fills._queue takes the latest ts <= submit, so a quote with no snapshot of its own inherits an earlier quote's queue instead of the UNKNOWN sentinel.
- Construction (s551adv_oldsnap.py): a valid snapshot at 0 s has yes 49 x 5. The 60 s snapshot has the same touch, but its ladder repeats level 49 with sizes 5 and 900. to_quote_book accepts that row and to_fill_snapshot refuses it (conflicting_level_size).
- Result: counters {}; fill_snaps holds only instant 0; the 60 s quote FILLS touch_queue with queue_ahead_at_submit "5". With the sentinel it would not fill.
- Reachable on any malformed ladder. Real-day incidence: 0 of 7073 accepted snapshots on 2026-09-24.
- Fix, about 3 lines plus one test: count `fill_snapshot_refused` and `mark_tick_refused`. For each decision instant without its own snapshot, pass {ts, ticker, yes: [], no: []} so that _queue returns the sentinel.

## Checks that held (evidence)
1. Causality:
   - phase1 never sees prints or fills.
   - My raw-row truncation (s551adv_trunc.py) re-parses books and state truncated to receipt <= t, recomputes game_inputs, and re-runs phase1. It found 0 mismatches over 40 random instants x 3 arms.
   - Mutation M7 (decide on the next book) is killed by case 20.
2. Order-book mechanics:
   - Pending-cancel fill: 105.9 fills, 106.0 does not. Mutation M1 (cancel effective at decision) is killed by 4 tests.
   - Priority loss on replace holds (case 15).
   - C <= S is enforced, with bounds (0, 600].
   - simulate_fills takes min(old end, new submit + C), so a replace never extends the TTL.
3. Pairing:
   - There is one simulate_fills call per (arm, scenario, game).
   - The eligibility and eligible_us set is computed once and shared.
   - Mutation M4 (all arms in one call) is killed by cases 27, 28, 29 and the pooling test.
4. Seal:
   - verify() recomputes the seal, compares the body to the code constants and requires attest "resolved".
   - A game is scored only if its first-play-receipt date is > D_seal. Mutation M3 (skip the date check) is killed.
   - Prior receipts must carry the same sha and seal.
   - Holm runs over the 4 cells in both directions.
   - INSUFFICIENT unless every cell has >= 30 paired games. Mutations M5 (floor 29) and M6 (no Holm) are killed. M9 (cool-down off) is killed.
5. Hygiene: the largest module is 280 LOC; all files are ASCII; g334 word and number gate: 0 hits in 12 files; .gitattributes adds exactly 3 lines.

## NOTE
N1. Test power: a tape-driven trigger survives test_s551_replay.py.
   - The mutation injects trade rows as state triggers, by created_time (M2a) or by receipt (M2b). Cases 20 and 21 both pass.
   - The garbage trades keep their receipts, and the dense tape saturates the trigger in both runs, so the two runs match.
   - Only the self-generated pins (cases 27-29) kill it.
   - Suggested fix: case 21 should also drop or shift the trade receipts and assert the trigger set.
N2. Mutation M8 (BEHIND on the unadjusted p) survives every test. The code correctly uses the Holm p; add a BEHIND case where Holm changes the result.
N3. The window end is a lookahead: the final-row receipt, or the last state row when a game has no final row. It is shared by all arms and only trims submissions at the tail. Case 20 passes the full window.
N4. RSS:
   - 335.8 MiB reproduced; the import baseline is 24 MiB.
   - load_day holds every served ticker's rows for D and D+1 at the same time, about 78 MiB per game.
   - A day with 5 or more served games would exit 5 with no receipt. That is fail-closed, not silent.
   - No multi-day growth: priors read only the small sidecars.
   - The memo does not record the peak.
N5. quoted_us is clipped to the grid span, but eligible gaps are capped at 10 s, so uptime can exceed 1 when capture gaps exceed 10 s. Observed values were 0.38 to 0.98.
N6. Exit codes and missing inputs:
   - An IO.Refused on input data exits 2 ("bad_argument").
   - Missing input files give a 0-game exit-0 receipt; the files are recorded with exists False.
N7. Stripping raw_market follows the landed precedent at live_shadow_quoter.py:125. The static_touch oracle reads the top-level touch fields and agrees.
The rest of the disclosed NOT VERIFIED list (partial-write lockout, self-generated pins) is accurate.
