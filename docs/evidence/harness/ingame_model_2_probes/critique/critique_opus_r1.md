VERDICT: REVISE

Opus tier-2 critique r1 of docs/evidence/harness/INGAME_MODEL_2_PLAN_2026-09-29.md (8854814f0). Default REFUTED for any "better than the venue mid" reading. The top-line verdict (a fresh mid is the model; state models trail it) survives. The NBA late-tail and SHRINK-beats-FRESH readings do not survive. They come from post-final-buzzer ticks.

1. BLOCKING. The P5 NBA late tail and SHRINK < FRESH come from post-final-buzzer ticks (the known S146/S148 defect).
   - probe_p5_nba_projection.py:114-117 filters only on anchor price and the reg/OT boundary. It never applies the S148 live rule (live iff period<4 or game_clock_s>0; scripts/platformkit/eval_gate/s148_live_requote.py:3-18).
   - nba_checkpoints_to_joined.py:149-177 carries dead ticks into nba_checkpoints_r1 unchanged (465,249 rows, the same count as the full parquet).
   - At s=0, wp() (probe:80-82, se=max(s,1)) gives PROJ = Phi(m*53.7/sigma), which is about 0 or 1 when the final margin is known. The lingering post-game price loses to it.
   - I reran the P5 selection with a dead flag (scratchpad/ingame2/p5_dead.py; it writes nowhere). 4,861 scored ticks in 479 games are dead.
     - 2025-26 clipped, all: SHRINK-FRESH -0.01360 [-0.02327,-0.00446]. This reproduces the plan -0.01360 [-0.02318,-0.00445]. PROJ-FRESH -0.01273 also reproduces.
     - 2025-26 clipped DEAD: PROJ-FRESH -0.04340 [-0.06774,-0.01996] (3,192 ticks, 270 games).
     - 2025-26 clipped LIVE: PROJ-FRESH -0.00270 [-0.01057,+0.00377]; SHRINK-FRESH -0.00397 [-0.00975,+0.00062]. Both CIs cross 0.
     - 2025-26 clipped LIVE, s<=60: PROJ-FRESH +0.00730 [-0.00028,+0.01580]. PROJ is WORSE here, the opposite of the claimed tail.
     - 2025-26 all LIVE: SHRINK-FRESH -0.00047 [-0.00126,+0.00032]. The headline was -0.00157 [-0.00300,-0.00031]. PROJ-FRESH is +0.00045 vs the headline -0.00069.
     - 2024-25 clipped DEAD: -0.01099 [-0.02383,-0.00113]; 2024-25 clipped LIVE PROJ-FRESH -0.00021 [-0.00237,+0.00204].
     So the artifact replicates in both seasons, and the live effect is null in both.
   - The plan text is therefore unsafe as written:
     - plan:24 ("NBA 2025-26 clipped-anchor and final-minute ticks") must be restated as an artifact.
     - plan:62 must be restated the same way.
     - plan:61 (sigma=16, 2025-26 PROJ-FRESH -0.00115) is unverified on live ticks.
     - The c coefficient 0.4205 (plan:62) was fit on data that includes dead ticks.
   - Unaffected: the noclip recovery fractions 0.396/0.411/0.440. Only about 16 dead ticks are unclipped. I checked 0.396 by hand: 0.00051/0.00128.

2. BLOCKING. Price-vs-state timing in the NBA rows (the S542 before-condition, plan:98-101), answered from code.
   - nba_wallclock_join.py:79-98 uses merge_asof(direction=backward) on the candle ts, so state_ts <= price_ts. The state is never from the future relative to the row ts.
   - The price can still be OLDER than the state in the same row:
     - nba_checkpoints_full.py:121-135 hard-codes traded=True for every Polymarket point ("no traded/stale flag", line 42-45).
     - seconds_since_last_trade=0 on all 465,249 rows (P5 stdout line 3) is a fabricated freshness value, not a measured one.
     - 65.2% of consecutive pairs have an unchanged price (stdout line 6). Many FRESH prices are therefore carried last trades that predate a newer ESPN play.
   - The state carries ESPN play wallclock (nba_wallclock_join.py:45-51) with zero feed latency. P1 measured our live feed lag at p50 17.9 s / p90 31.1 s.
   - Both effects favour PROJ over FRESH historically in a way that cannot be reproduced live. S542 must replay with the state shifted forward by the measured feed lag. Reuse state_lag_sensitivity.recover_state_lag (state_lag_sensitivity.py:68-80) to get the exact lag.

3. BLOCKING. The M2 formula double-counts events in live use (plan:38-43).
   - The anchor is "the last mid change". P1 K_FRESH15 shows the fresh book reprices BEFORE our feed reports the play: pre +1.145 pp [+0.586,+1.662].
   - So the anchor mid often already contains the event, while the state we attach to it is the pre-event state. Inverting mu absorbs the event, and PROJ(state_now) applies it a second time.
   - P5 cannot see this because its states carry zero lag (finding 2).
   - c must be defined on the state the market knew at the anchor time. At minimum, set c=0 whenever an anchor change falls inside [t_play, t_recv] of the latest state change.

4. BLOCKING. The S544 comparator is ambiguous and could become a disguised "beats the mid" claim (plan:109-114).
   - P1 says MLB staleness is mostly OUR receipt floor (bulk-only games), not venue staleness.
   - M2 beating arm A on the stale segment would therefore beat our stale copy of the mid, not the venue.
   - The seal must name arm A as the venue mid at t, reconstructed ex post from the full-resolution capture where one exists. Otherwise the segment is labelled "vs own stale receipt" and is never quoted as vs-market.
   - On the fresh segment with state unchanged, M2 = sigmoid(a+b*logit(mid)). That is the recalibration already REJECTED by P3 and P5 RECAL_FRESH (-0.00018 [-0.00066,+0.00027]). Pre-register a=0, b=1 there, or declare the expected null.

5. NOTE. The P4 J filter (probe_p4_we_feature.py:118-137) handles ET/EDT correctly for this corpus.
   - All tickers are JUN/JUL, so EDT at UTC-4 is right, and date rollover is correct because start = ticker date+HHMM+4h.
   - It removes no real in-game ticks.
   - It is time-based, so it KEEPS contaminated ticks. My check (scratchpad/ingame2/p4_window.py) finds 697 ticks in 7 games with an inning>=5 state before the first inning-1 tick after start-30min, from rain delays and the 30-minute window.
   - S541 should filter on state (the first inning-1 state at or after scheduled start), not on the clock.

6. BLOCKING for S541 scope. Gate A0 uses the contaminated rows, and its late cell is mislabelled.
   - scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:29-47 loads every row with non-null model_prob. There is no start filter, so the 21,064 prior-day ticks are inside 0.2377 vs 0.2067.
   - Its minutes_to_close uses close_ts. In mlb_clean, close_ts equals the LAST CAPTURE tick in all 227 games; 67 captures end before inning 9 and 49 end on an empty state.
   - "MLB minutes_to_close<10" is therefore "last 10 minutes of capture", not late game.
   - plan:23 cites that cell as late-tail evidence. Drop it.
   - P3 late bands (inning>=8) have a separate, unverified risk: post-final ticks with a frozen pre-final state. No outs=3 or walk-off state exists in mlb_clean, so the end of the game cannot be seen from state. S541 needs an ESPN game-end timestamp filter.

7. NOTE. Hand-off language overreaches.
   - plan:15 and plan:134-136 state "a fresh Kalshi book has usually repriced by then" as fact, from K_FRESH15. That cell is INSUFFICIENT (15 games).
   - Its SCORE subset post_120 is +0.968 [+0.017,+1.618] (12 games), which points the other way for scoring plays.
   - Restate as "not yet measurable; the pooled fresh cell points to pre-receipt repricing".

8. NOTE. c cannot be transferred as specified.
   - c=0.4205 is fitted on a 60-second EMULATED staleness with Polymarket last-trade candles.
   - The live NBA anchor is Kalshi (plan:70), with a different venue, cadence and staleness distribution.
   - Either refit c per venue and per staleness bucket, or freeze c=0 for NBA until Kalshi NBA live rows exist.

9. NOTE. Time and paths.
   - "30 games ~mid-Oct" (plan:69) applies to the whole MLB postseason. The stale x late cells will not reach 30 games this postseason, especially if all postseason games get focus books (plan:133), which empties the stale segment.
   - Pre-declare S544 MLB verdicts INSUFFICIENT through the World Series.
   - Paths: S541-S544 target scripts/platformkit/ingame/ and docs/evidence/forward/model2/. They touch no gated or S439 identity file, which is OK.
   - Confirm the docs/evidence/forward/ subfolders are not paper-desk owned. RUNNER.lock files exist in nights/ and registry_e/.
   - The 300-LOC and per-file-test rails are implicit only. State them in each row.

10. NOTE. The biggest miss is a live-realistic replay.
   - Every NBA staleness and late-tail number assumes the state arrives the instant ESPN stamps the play, and that dead ticks are in scope.
   - Before any M2 seal, rerun P5 (a) on live ticks only (S148 rule), (b) with state delayed by the measured feed-lag distribution, and (c) with the anchor defined as the last mid change before t_recv of the matching state.
   - If the recovery fraction does not survive (b) and (c), Model 2.0 has no measured mechanism.

PROPOSED AMENDMENT (append to section 7):
A1. The NBA late tail is RETRACTED as an artifact. Opus r1 reran P5 with the S148 live rule. Clipped-anchor 2025-26 PROJ-FRESH is -0.04340 on post-final-buzzer ticks and -0.00270 [-0.01057,+0.00377] on live ticks; clipped live s<=60 is +0.00730. All-ticks SHRINK-FRESH on live ticks is -0.00047 [-0.00126,+0.00032]. Remove NBA and the Gate A0 minutes_to_close cell from the late-tail evidence (plan:22-24). The late-tail candidate rests on P3 MLB J alone, which is single-corpus and pending a game-end filter.
A2. S542 before-condition, answered: state_ts <= price_ts (merge_asof backward, nba_wallclock_join.py:79-98). The price can still predate the state: forced traded=True (nba_checkpoints_full.py:134) and 65% carried prices. The state carries zero feed lag. S542 must (a) apply the S148 live filter, (b) replay with state delayed by 18 s and 31 s, and (c) refit sigma and c on live ticks only. Before any seal, it must report the recovery fraction under (b).
A3. M2 anchor rule: c is applied only when no mid change falls inside [t_play, t_recv] of the latest state change. Otherwise M2 = the mid. On fresh, unchanged-state ticks, a=0 and b=1 (recalibration is already rejected).
A4. S544 arm A = the venue mid at t from full-resolution capture. Any cell scored against our receipt copy is labelled "vs own stale receipt". No M2 < A cell is quoted as a statement about the venue (calibration language only).
A5. S541 filters on state and game end (first inning-1 state after scheduled start; ESPN final timestamp), not on ticker time alone. The Gate A0 re-derivation also relabels minutes_to_close as minutes to capture end.
A6. MLB S544 cells are pre-declared INSUFFICIENT through the 2026 World Series. NBA c is frozen at 0 until 30 Kalshi NBA live games exist.
