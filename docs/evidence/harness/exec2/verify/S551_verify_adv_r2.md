VERDICT: ACCEPT
S551 adversarial verifier, round 2 (Opus; codex down). Candidate: uncommitted files in C:/Users/neelj/nba-harness-h222 at fb59f6fff. I did not edit the candidate; every mutation ran on a copy under the scratchpad.
Scratch artifacts: s551adv2_mut.py (11 new mutants), s551adv2_fuzz.py (uptime brute-force), s551adv2_dup.py (equal-receipt probe), s551adv2_real/ (exploratory 09-24 run).

## Reproduction
- Per-file tests (run_files.py): cancel_policy 20 passed, replay 14 passed, prereg_report 10 passed.
- s551adv_oldsnap.py (the round-1 BLOCKING repro) now gives counters {fill_snapshot_refused: 1} and no fill. In round 1 it filled touch_queue with queue_ahead "5". FIXED.
- Round-1 mutants: all of M1-M9 die, including M2a and M2b, which case 21 now kills. The builder's F1, F1b, F2, F3 and F6 also die.
- s551_expected.json against s551_expected_r1.json: the only changes are quote_uptime and quoted_us for static_touch and cancel_on_book_move (both scenarios, all four views), plus the new zero keys pair_no_mark60, fill_snapshot_refused and mark_tick_refused. No fill, markout, fee, fill-rate or verdict value changed. This matches the memo.

## Attack results
1. Empty-level snapshot path: SAFE.
   - phase1 submits only at instants that carry a dict book (replay.py:172), and CONFLICT instants never submit.
   - So every decision instant either has its own snap or had its own snap refused. The level-less entry therefore appears only where a refusal was counted.
   - When nothing is refused, the snapshots passed to phase 2 are identical to round 1. The unchanged fills on the fixture and the 0 refusals on the real day confirm this.
   - A later valid snapshot stays reachable: the test's 10 s trade still reads queue "5" from the 0 s snapshot.
   - _queue selects by decision time, not arrival time (tape_fill_sim.py:155,167).
2. Uptime is in [0, 1] and credited exactly.
   - Fuzz: 400 random games x 3 arms, with gaps from 1 to 90 s, random eligibility and random windows.
   - Brute force on a per-second basis matches quoted_us exactly (0 mismatches). No same-side overlap was found. Maximum uptime was 0.958.
   - Quoted time is credited only inside eligible spans. It is always credited while the order is live, from arrival to end (the spec wording).
   - Real 09-24 uptime ranges from 0.40 to 0.96.
3. The oracle is independent.
   - It imports only landed, tracked modules (make_quotes, simulate_fills, events_for, to_mark_tick, resolve_marks, markout_strict, fee_kalshi_maker, from_s341_trade), and none of them imports an exec_policy or exec_cancel_policy module.
   - It re-derives the fill set, the per-fill fee (asserted), the fill rate, the +60 s mean and the missing share (0.285714, which is non-zero, so it has power).
4. The new tests have power. Every one of my mutants on copies dies:
   - A1: covered_us drops the prior-span overlap.
   - A3: every snapshot is level-less. The replay tests kill it (cases 15 and the refused test).
   - A4: p10 without the fee.
   - A5: missing_qty is never added.
   - A6: BEHIND uses the ahead-direction Holm p.
   - A7: Holm uses m-1.
   - A8: the gap cap is set to 30 s.
   - A9: quoted time is counted from the decision instead of arrival.
   - A10: the fee is subtracted twice.
   - A11: fills60 is taken from +30 s.
   - A2 (quoted time uses the other side's spans) survives replay and prereg but is killed by cancel_policy.
5. No regressions.
   - Every module is 300 lines or fewer (test_s551_prereg_report.py is exactly 300).
   - All files are ASCII-only.
   - The vocabulary and retracted-number grep over the modules, tests and memo is clean.
   - .gitattributes adds exactly 3 lines.
   - The memo records the 336 MiB peak, the window-end rule and the regenerated inventories, and ends with a NOT VERIFIED list.
6. Exploratory real-day run (2026-09-24): rc 0, peak RSS 337.0 MiB, wall 17.6 s.
   - 4 games, 3 of them tape-complete; every cell INSUFFICIENT.
   - fill_snapshot_refused 0, mark_tick_refused 0, pair_no_fill 0, pair_no_mark60 0.

## NOTE (non-blocking)
N1. Equal-receipt rows that share a touch but have different ladders are treated as `equal_receipt_duplicate`, so the first row wins, and the outcome depends on row order.
- Probe (s551adv2_dup.py): valid-then-refused fills at queue "5" and never counts the refused ladder. Refused-then-valid reads UNKNOWN and does not fill.
- This behaviour predates AMENDMENT 2, where round 1 also kept the first row. It is outside the "nothing else changes" fix list. It was seen 0 times on the fixture and on 09-24 (equal_receipt_duplicate = 0).
- Suggested follow-up: when the fsnap ladders differ, drop the snap and count a refusal.

## NOT VERIFIED
- Py3.12.
- The committed-on-master test run (the candidate is uncommitted).
- The real PREREG seal commit.
- A day with 5 or more served games (the exit-5 memory path was exercised only by the construct test).
