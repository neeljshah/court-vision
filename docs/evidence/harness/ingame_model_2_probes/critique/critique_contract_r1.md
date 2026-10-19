VERDICT: REVISE

Contract critic r1 (replaces the codex astra tier) of INGAME_MODEL_2_PLAN_2026-09-29.md (8854814f0) plus the lead's intended (a)-(e). This builds on critique_opus_r1.md and does not repeat it. Short version: (a), (c), (d) and (e) are right. (b) is right in shape, but its verdict rule is not yet well-posed (findings 1-3). One new row is worth more than anything else for the next nights: an S439 late-cell integrity side-audit (finding 6), because the first fitted S439 night is 09-30.

1. BLOCKING. In the S542 replay, dead ticks must be judged on the TRUE state at the tick, not the delayed state.
   - With the state delayed by L, a tick up to L seconds after the final buzzer carries a pre-buzzer state (period 4, clock > 0). The S148 rule (s148_live_requote.py:12-14) would then call it LIVE.
   - That re-admits exactly the ticks Opus showed drive the artifact (-0.04340 on dead clipped ticks).
   - Rule: compute the live/dead mask ONCE from the undelayed state at t, freeze it, and apply the same row set at L = 0/18/31/60. The row count per L must be identical and reported.
   - Also, S148 marks a TIED P4 clock-0 tick dead, but that game goes to OT. Declare whether tied ticks are kept; recommended: dead iff period >= 4, clock == 0 and scores unequal. Report the count either way.

2. BLOCKING. The verdict statistic is ill-posed as a ratio. Put the verdict on the paired difference.
   - The recovery fraction is (L_STALE - L_PROJ) / (L_STALE - L_FRESH). Its denominator is small: Opus hand-checked 0.396 = 0.00051/0.00128. A game-clustered bootstrap ratio becomes unstable whenever resampled denominators come near 0.
   - Rule: the verdict is on the numerator, D_L = L_PROJ - L_STALE (paired by tick, clustered by game). At L = 18, PROJ survives only if the D_18 CI upper bound is < 0 in BOTH seasons. Report the ratio descriptively, and only when the denominator CI lower bound is > 0. Otherwise print "ratio not estimable".
   - Score on the state-changed subset only. Everywhere else PROJ equals STALE by construction (plan:41), so pooling all ticks dilutes the signal and inflates N.
   - Sigma was chosen on 2024-25 (plan:61), so a 2024-25 verdict is in-sample for sigma. Either fix sigma a priori before running (one literature constant, stated in the row) or cross-fit it (sigma from the other season). Pre-declare which.

3. BLOCKING. The 18 s delay can be a partial no-op at per-minute candles. Pre-declare an active-delay check plus two controls.
   - Prices are per-minute last-trade candles. Delaying the state by 18 s changes the attached state only when a state change falls in (t-18, t].
   - Rough scale (my estimate, not measured): about 85 score changes over about 8,600 s of wall clock gives about 0.17 of all candles, or roughly 35-40 pct of state-changed ticks. That is not a no-op, but it must be measured.
   - Active-delay check (pre-declared): report the share S_L of state-changed ticks whose delayed state differs from the undelayed one. If S_18 < 0.20, the L = 18 test is INACTIVE. S544 stays withdrawn and is not rescued by L = 0.
   - Control 1, permutation placebo: take the state delta from a different game at the same period and clock bucket and the same anchor-price decile, then apply PROJ. Expected D <= 0 gain, meaning it must NOT beat STALE. This isolates the mechanical extremizing that produced the retracted tail. If the placebo also "recovers", PROJ has no information content.
   - Control 2, leak canary: L = -18 (a future state). It must beat L = 0 clearly. If it does not, the replay harness cannot see state information at all, and the L = 18 null means nothing.
   - Event-aware anchor at candle resolution: a price change inside the candle that contains t_play cannot be ordered against the play. Treat it as AFTER the play (c = 0 and M2 = the mid), as the conservative direction. forced traded=True (Opus 2) means "no change" cannot distinguish no-trade from a same-price trade. State this.
   - L grid provenance: 17.9/31.1 s are MLB statsapi lags (plan:14, P1). The NBA ESPN lag is unmeasured. Label L as "borrowed from MLB" until S553 (EXECUTION_2_PLAN:77) prints an NBA row. NBA preseason ESPN state is already being captured (state/nba/2026-09-28.jsonl, 2026-09-29.jsonl exist, status pre so far), so S553 can measure it before 10-20.

4. NOTE. (a) Retracting the late tail is right. Two follow-ons are needed.
   - The c-term "clip branch" (plan:42-43, "outside the clip late in the game") now has no evidence. Keep the mu clip only as a numerical guard, fixed a priori (not the fitted boundary), and set c's clip-region contribution to 0.
   - The reserved follow-up "late-tail rule's prospective read-out" (plan:124) must be withdrawn or restated as MLB-only, pending the S541 game-end filter. P3 J is a single corpus.

5. NOTE. (c) Cutting S543 is right. Nothing new is needed for the fresh/stale split either.
   - S553 covers per-sport lag and cadence, S550 the per-game coverage census, and S556 focus/bulk capture gaps (EXECUTION_2_PLAN:74,77,80). night_coverage_census.py and event_latency_census.py already exist.
   - The one S543 output S544 needed, a per-tick anchor age, is already in S439: mid_age_us = state receipt minus used book receipt (ingame_scoreboard.py:204, POLICY :36), with quantiles reported per cell (:241).
   - Caveat carried from Opus 4: that is OUR receipt age, not venue staleness.

6. BLOCKING (new row). S439 prospective cells can score post-game and unpaired ticks. The single most valuable additional row is a read-only side-audit.
   - (i) MLB post-last-out ticks are scored.
     - The scorer skips only status == 'final' receipts (ingame_scoreboard.py:199). Every earlier 'live' receipt is a tick, with the latest book at or before T and no age cap (:201-204, POLICY :36).
     - statsapi abstractGameState maps to final only on "Final" (local_state_capture_sources.py:27,180).
     - Measured on capture_view_v2, excluding capture-outage games: the terminal state, frozen at 2 outs or at 'End'/3 outs in the 9th, persists 26-126 s before the first final receipt. Per night: 09-24 p50 62 s / p90 243 s (17 tail rows); 09-25 p50 67 s (20 rows / 9 games); 09-26 p50 115 s (13 rows).
     - 'End' maps to the next top (ingame_scoreboard_rules.py:44,52), so these land in 'late'.
     - The effect is small but signed: the mid is near 0/1 while a 2-outs-bottom-9 state model is not, so it biases against C/D. Opus's P5 magnitudes show a few ticks per game can move a late cell by about 1e-4.
   - (ii) NBA Q4-end ticks will be scored.
     - ESPN STATUS_END_PERIOD maps to 'live' (local_state_capture_sources.py:32-33). segment() accepts period 4 at clock 0 (rules:53-55).
     - So any post-buzzer receipt before STATUS_FINAL is a 'late' tick. This is the S146 defect, now in the prospective scorer.
     - Unverified frequency: there are no NBA live rows yet.
   - (iii) Arm cells are not paired.
     - Arm A is scored on every tick (ingame_scoreboard.py:219). B/C/D are scored only where tick_row reconstructs the state (:129-131, :239). tick_row refuses outs = 3 (rules:157) and empty 'pre' states.
     - So the A cell includes the near-certain terminal and pre-live ticks, and the B/C/D cells do not. Only C_minus_B is paired (:231).
     - Comparing an A cell with a C cell mixes different row sets.
   - (iv) Pre-first-pitch: 'pre' receipts go to the 'pre-live' segment (rules:46), which is correct and separate.
     - Warmup receipts (abstractGameState Live before the first pitch, e.g. game 823897 on 09-23: 82 receipts at inning 1 Top, 0 outs, 0-0) are scored as 'early' with a true state. That is harmless.
     - The mlb_clean prior-day defect cannot occur here: identity is game_pk per schedule entry (:184,190), and training history is prior nights' own scoreboard rows (paper_night_budget.json:20), not mlb_clean. Plan:137-139 holds.
   - Row text is under PROPOSED AMENDMENT A-S546 below.

7. NOTE. (e) S541 is right, with two contract additions.
   - (1) Do not edit gate_a0_ingame_vs_market.py. baseline_four_arm_eligibility.py:11,118,184 imports its EPS, N_MIN_GAMES and DATA_ROOT, so an edit silently changes the sealed S439 path. The re-derivation must be a new module that imports it read-only.
   - (2) State the fallback for the state-based carry-over filter: a game with no inning-1 state after scheduled start. Recommended: drop ticks before the first state change after scheduled start, and count them separately. Do not silently drop the whole game.
   - The re-derived Gate A0 is a re-quote of a published number, not a new test. It cannot move any claim beyond "trails / matches".

8. NOTE. (d) Deferring S544 is right. The cheaper honest vehicle is a sealed READER of S439 night outputs, not a second shard scorer.
   - S439 output already carries per tick: mid, mid_age_us, state, ts, book_ts and the segment (ingame_scoreboard.py:208-210).
   - M2 computed from those rows gets the identical tick set, receipts and settlement for free. It removes Opus-4 comparator ambiguity for the receipt-copy arm (arm A is the same number).
   - Seal deadline: commit by 10-18 so that effective X = 10-19 precedes the NBA opener (about 10-20).
   - Seal contents: the S542 verdict artifact sha, sigma, c with c = 0 for NBA per Opus A6, a=0/b=1 on unchanged state, the dead-tick rule, the pairing rule, the fresh cutoff on mid_age_us, and the vocabulary reused from rules:128-137 (SINGLE-WINDOW until 2 corpora).

9. NOTE. Settlement close is the LATEST final receipt, max(finals) (rules:182), not the first.
   - Any "time to close" derived from S439 output overstates the post-game window. The audit row must recompute the first-final instant from the state shards.

PROPOSED AMENDMENT (append to section 7, after the Opus A1-A6)

C1 (S542 verdict rule, replaces the ratio rule).
- Row set: NBA r1, S148-live on the UNDELAYED state. A tied P4 clock-0 tick is kept. The mask is frozen across L.
- Scored subset: state-changed ticks. Sigma is a priori (or cross-fitted, declared in the row).
- For L in {-18, 0, 18, 31, 60}: D_L = Brier(PROJ_L) - Brier(STALE) and log-loss likewise, paired, game-clustered, 2000 resamples, seed 13.
- Also report S_L, the share of state-changed ticks whose state is changed by the delay.
- PROJ PASSES only if ALL of the following hold:
  - S_18 >= 0.20;
  - the D_{-18} CI upper bound < the D_0 point estimate (the canary);
  - the D_18 Brier CI upper bound < 0 in 2024-25 AND 2025-26;
  - the placebo D_18 CI does not lie wholly below the real D_18.
- Otherwise PROJ is REJECTED (or INACTIVE if S_18 < 0.20), and S544 is withdrawn.
- The recovery ratio is printed only when the STALE-FRESH CI lower bound > 0.
- An in-candle price change is ordered after the play. L is labelled MLB-borrowed until S553 prints NBA lag.

C2. c clip branch set to 0. The mu clip is an a-priori numerical guard. The plan:124 late-tail read-out is withdrawn (MLB-only if revived after S541).

C3. S543 CUT. The fresh/stale split = S439 mid_age_us <= 15 s, labelled "own receipt age".

C4. S544 (deferred, conditional on C1 PASS) is a sealed reader of S439 night outputs. It never reads shards itself. Seal committed by 10-18.

C5. S541 never edits gate_a0_ingame_vs_market.py (imported by baseline_four_arm_eligibility.py:11). A no-inning-1 game falls back to the first post-start state change, with a separate count.

A-S546 (new, PREPARE, read-only, <= 300 LOC, per-file test on verbatim rows).
- Module: scripts/platformkit/ingame/s439_integrity_audit.py. It reads each S439 night output plus the same state shards and writes docs/evidence/forward/model2/s439_audit/<D>.json. It never rewrites S439 output.
- Per sport and segment:
  - (1) Terminal-tick census.
    - MLB: live receipts from the first terminal-consistent state (inning >= 9 with 3 outs/'End' and scores unequal, or the frozen state preceding the first final receipt) to the first final receipt.
    - NBA: period >= 4, clock 0, scores unequal.
    - Soccer: live after minute >= 90 with a later final.
  - (2) Every arm cell re-summarised on the PAIRED intersection (all active arms present, terminal ticks excluded), printed beside the sealed cell with both N.
  - (3) mid_age_us <= 15 s vs > 15 s split.
- Vocabulary: rules:128-137. Descriptive until each cell reaches 30 games.
- First run: nights 09-30 onward, plus a replay of 09-22..09-29.
