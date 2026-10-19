# In-game Model 2.0 plan (2026-09-29, Fable lead; rows S540-S549)

Calibration language only. Every number below was printed by the probe script named next to it
(scripts, stdout copies and JSON summaries in `docs/evidence/harness/ingame_model_2_probes/`; they
read the capture archives read-only and write only next to themselves). Delta = loss(candidate) -
loss(comparator); negative = candidate better. CIs are game-clustered bootstraps (2000, seed 13).
Cells under 30 games are INSUFFICIENT and carry no verdict.

## 1. Verdict first

- When the venue book is FRESH, the mid is the model. Six new probe families (P1-P6) found no
  residual, recalibration, price summary or state feature that improves on a fresh mid. This
  confirms S115, S277, S347, Q17 and Gate A0 on new corpora and new mechanisms.
- Our state feed is late. The MLB feed reaches us p50 17.9 s / p90 31.1 s after the play (P1), and a
  fresh Kalshi book has usually repriced by then. No post-receipt window is measurable (P1, K_FRESH15).
- The measurable value of a state model is as a STALENESS BACKSTOP. The market-anchored state
  projection (PROJ) keeps the market's implied strength and moves it through the state change. On
  NBA (1,593 games, two seasons) it recovers 0.396-0.440 of the staleness loss. It still trails a
  fresh price (P5).
- One structured miscalibration recurs: the LATE-GAME TAIL. Late in the game the mid is less extreme
  than the state implies. The evidence:
  - MLB J late bands (P3).
  - The Gate A0 MLB late insurance cells.
  - NBA 2025-26 clipped-anchor and final-minute ticks (P5).
  It does NOT replicate cleanly on NBA 2024-25 (CI crosses 0), and a candle-timing artifact is not
  excluded. It is a pre-registration candidate only, to be measured prospectively.
- Two corpus defects change historical headline inputs (P4, P6). Both need re-derivation before any
  number built on them is quoted again (row S541).
  - mlb_clean: 21,064 ticks in 115 of 177 games sit before first pitch and carry the previous day's
    state.
  - soccer_intl: the outcome label is not a binary home-win label.
- Data coverage, not modelling, is the binding constraint on MLB. Only 15 of 37 settled live Sept
  games had live focus books. The capacity rule serves about 3 games a day; the rest refresh through
  the bulk snapshot only.

So Model 2.0 is a market-anchored, freshness-aware composite:

`p = sigmoid(a + b * logit(anchor_mid) + c * (logit PROJ(state_now; mu_clipped(anchor)) - logit(anchor_mid)))`

- The anchor is the last mid change.
- PROJ equals the anchor exactly when the state is unchanged and mu is unclipped.
- The c term is non-zero only when the book is stale relative to the state, or when the book's
  implied strength is outside the clip late in the game.
- a, b and c are fitted walk-forward and frozen in a prospective seal. The WP/WE formulas use
  a-priori constants.

## 2. Probe results (S540)

| probe | sport / corpus | measured | numbers | reading |
|---|---|---|---|---|
| P1 event response | MLB Kalshi K (Sept, 47 linked games) | signed home-mid move around OUR state receipt; SCORE and OUT events | cadence p50 5.18 s; feed lag p50 17.9 s p90 31.1 s; K pooled 1107 events / 40 games: pre +0.205 pp [+0.017,+0.386], post_120 +0.464 [+0.113,+0.839], share 0.693, book unchanged 0.888 | contaminated by bulk-only games (22 of 37 settled linked games) = OUR receipt floor, not venue lag |
| P1 fresh books | K_FRESH15 (max receipt gap <= 15 s) | same, fresh books only | POOLED 197 events / 15 games: pre +1.145 [+0.586,+1.662], post_120 -0.023 [-0.557,+0.399], share -0.020; SCORE 31 / 12: post_120 +0.968 [+0.017,+1.618] | INSUFFICIENT; the fresh book has already moved when our feed arrives |
| P1 Polymarket | MLB P (09-24..09-29) | same | home-token receipt gap p50 1329 s; 511 events / 19 games | receipt floor; unusable for this |
| P1 NFL | 2 live games | descriptive | cadence p50 5.16 s; 18 SCORE events post_120 +0.556 pp | descriptive only |
| P2 price source | MLB K focus snapshots, 2020 ticks / 15 games | MICRO, LAST, LAG, PAIR vs MID (Brier) | MICRO +0.00002 [-0.00065,+0.00037]; LAST -0.00105 [-0.00267,+0.00165]; LAG +0.00022 [-0.00000,+0.00067]; PAIR +0.00026 [-0.00006,+0.00051]; spread p50 = p90 = 0.010 | INSUFFICIENT; no candidate differs from MID; keep the raw mid |
| P3 mid calibration | MLB J (June-July, 224 games) + K | reliability; late bands; recalibration J walk-forward and J->K | J ECE 0.0591; J late (inning>=8, 147 games) <0.10 priced 0.0445 realized 0.0084 (70 games), 0.10-0.20 priced 0.1445 realized 0.0634 (48 games); J-WF Platt+late +0.00582 [-0.00337,+0.01559] (196 games); J->K Platt +0.02098 (15 games) | recalibrating the mid: REJECT (all point estimates worse, CIs include 0); late underdog tail priced above realized |
| P4 WE feature | MLB J cleaned, walk-forward, 124 games / 11,748 ticks | arm W (mid + logit WE), S (mid + STALE_DELTA), WS, C vs arm B | W vs B +0.00052 [-0.00040,+0.00145]; S +0.00001 [-0.00006,+0.00008]; C +0.00162 [-0.00083,+0.00434]; coef on logit WE 0.0404 | REJECT as a residual feature: redundant given the mid; WE_ONLY slope 1.2429 = formula well scaled |
| P4 cross-corpus | fit J, score K (32 games) | same arms | W vs B -0.00636 [-0.01504,+0.00131]; K mid Brier 0.25706, ECE 0.128 | CIs include 0; K mid itself poorly calibrated on 32 games |
| P4 data defect | mlb_clean | pre-first-pitch prior-game ticks | 21,064 ticks / 115 of 177 games; 26,340 empty-state rows | S541 |
| P5 NBA projection | Polymarket checkpoints r1, 1,593 games, per-minute last-trade candles | PROJ vs STALE (previous tick carried) and vs FRESH | all ticks: PROJ-STALE -0.00177 [-0.00263,-0.00100], PROJ-FRESH -0.00019 [-0.00102,+0.00052]; state-changed: PROJ-FRESH +0.00073 [+0.00021,+0.00115]; staleness gap recovered 0.396 / 0.411 / 0.440 | staleness backstop: YES; against a fresh price: trails |
| P5 sigma | chosen on 2024-25 only | grid 10..16 | Brier falls monotonically, 16.0 chosen at the grid boundary; 2025-26 PROJ-FRESH -0.00115 [-0.00257,-0.00000] | the grid must be extended (boundary choice) |
| P5 shrink | logistic trained 2024-25, scored 2025-26 (937 games) | [logit STALE, logit PROJ - logit STALE] | vs FRESH all ticks Brier -0.00157 [-0.00300,-0.00031], log loss -0.00431 [-0.00882,-0.00027]; state-changed -0.00066 [-0.00158,+0.00017]; coef delta 0.4205 | driven by clipped-anchor (late) ticks: -0.01360 [-0.02318,-0.00445] (862 games); 2024-25 clipped -0.00227 [-0.00573,+0.00074] = does NOT replicate; candle timing unverified |
| P6 soccer | soccer_intl, 29 usable of 51 games | after-goal response | tick gap p50 29 s; 47 goals / 24 games: at-goal-tick +0.1248 [+0.0910,+0.1622], share already present median 0.890; 12 of 29 labels disagree with the final score | INSUFFICIENT; repricing done within one tick; label defect (S541) |

## 3. Per-sport design table

| sport | anchor | backstop (stale anchor) | late regime | data status (09-29) | first measurable |
|---|---|---|---|---|---|
| MLB | Kalshi KXMLBGAME home-ticker mid | PROJ with normal-approximation WE (0.5 runs / half-inning, var 1.0, RE24 current half, var 2*RE, tie 0.5) | shrink coefficient c frozen from J-cleaned walk-forward; prospective only | 47 live games linked Sept; focus books on ~3 served games/day; feed lag p50 17.9 s | postseason nights from the seal date; 30 games ~mid-Oct |
| NBA | Kalshi KXNBAGAME mid (Polymarket as second venue) | PROJ with Stern WP; sigma chosen on 2024-25 over an extended grid | c from the 2024-25 fit (frozen) | 0 live rows (offseason); 1,593-game history | regular season ~10-21 onward |
| WNBA | Kalshi KXWNBAGAME mid | PROJ with Stern WP (40-minute clock, sigma from WNBA history) | none until measured | playoffs; 0 live rows in the archive | S491 owner first; research only here |
| NFL | Kalshi KXNFLGAME mid | an NFL WP formula (down, distance, yardline, clock) is needed; not built | none | 2 live games in the archive | after S492 (other owner) + more games |
| Soccer | Kalshi league GAME mids (3-way) | a Poisson remaining-goals projection is needed; repricing is within one tick | late level-score draw behaviour (14 games, INSUFFICIENT) | 0 live rows in v2; the historical label is defective | after S490 (other owner) + S541 labels |
| Tennis | Kalshi match mid | point-level state is absent (sets only) | none | state lacks games/points | S493 set-state (other owner) |

## 4. Ranked rows (allocated from the reserved block S540-S549)

1. **S540: probe evidence (this document + probes).** Docs only. It records the REJECTs as successes:
   - recalibrating the mid (P3);
   - WE and STALE_DELTA as residual features on a fresh mid (P4);
   - price summaries MICRO / LAST / PAIR (P2);
   - a post-receipt state reaction on fresh books (P1).
   Status: LANDED with this commit.
2. **S541: corpus hygiene and Gate A0 re-derivation.**
   - Scope: a PREPARE module `scripts/platformkit/ingame/corpus_hygiene.py` with tests on verbatim
     rows. It covers mlb_clean pre-first-pitch prior-game ticks, empty-state rows, the soccer
     regulation label from the final score, and a label audit.
   - Then re-derive Gate A0 (MLB, soccer_intl) and publish the corrected numbers beside the
     originals (supersede by adding; never delete).
   - Why: Gate A0 (0.2377 vs 0.2067) is quoted in the quant gap list and in memory. If the
     contamination moved it, the record must say so.
3. **S542: anchor projection model (PREPARE, research).**
   - Scope: `scripts/platformkit/ingame/anchor_projection.py` (PROJ, mu inversion with clip, shrink
     fit/predict) plus per-sport WP/WE formulas (MLB normal approximation; NBA/WNBA Stern).
   - Walk-forward evidence:
     - NBA: fit 2024-25, score 2025-26, sigma from an extended grid chosen on 2024-25 only.
     - MLB: J-cleaned walk-forward by date.
   - Required before-condition: establish the NBA checkpoint price-timestamp semantics (candle
     open / close / VWAP versus the state join) from the builder code and 3 verbatim rows. If the
     price is older than the state within a tick, the late-tail result is an artifact, and the
     row says so.
4. **S543: anchor freshness census (nightly CLI, PREPARE).**
   - Scope: `scripts/platformkit/ingame/anchor_freshness.py`. For each sport and night it reports:
     live games; linked games; focus versus bulk receipt cadence; the fraction of live time with a
     receipt gap of at most 15 s; crossed or empty books; MLB feed lag (capture_ts - last_play_ts).
   - Output: `docs/evidence/forward/model2/freshness/<D>.json`, with real runs for 09-22..09-29.
   - Why: it makes the #1 constraint (focus coverage) visible every night. It gives the paper desk a
     "fresh anchor" test, and it supplies the fresh/stale split the M2 scorer segments on.
5. **S544: Model 2.0 prospective night scorer and seal.**
   - Scope: `scripts/platformkit/ingame/model2_night.py` (+ history aggregator).
     - Arms: A (raw mid) and M2 (the formula above, coefficients frozen), scored per sport against
       settlement.
     - Segments: fresh / stale anchor (S543) and late / not late.
     - Statistics: game-clustered CIs, the 30-game floor, a cumulative multi-night history.
   - Output: `docs/evidence/forward/model2/<D>.json`.
   - Seal `PREREG_M2_<X>.json`: module hashes + constants + coefficients, landed with the two-commit
     pattern (seal alone first, effective X = commit day + 1).
   - It does NOT touch the sealed S439 identity files or paper_night*.py; it imports the S439
     helpers read-only. Wiring it into the nightly run is a request to the paper-desk owner.
   - Depends on S542 and S543.
6. S545-S549 are reserved for follow-ups:
   - an NFL WP formula once NFL has more than 2 games;
   - a soccer Poisson projection after S541 labels and S490;
   - the late-tail rule's prospective read-out;
   - the WNBA Stern constants.

## 5. Hand-offs (other owners; not built here)

- **Focus-book coverage.** Owner: capture / paper desk, orchestrator 1 and the paper-desk-improve
  run. The capacity rule ("any three consecutive starts must span >= 3600 s") serves about 3 MLB
  games a day. The other live games refresh only through bulk snapshots. Every in-game verdict on
  MLB K is INSUFFICIENT until more live games carry focus books. The postseason slate is small
  (<= 4 games a day), so all of them could be focused.
- **Execution 2.0 (S550-S559 lead).** Our state feed trails a fresh Kalshi book, which has
  usually repriced before our feed reports the event (P1: feed lag p50 17.9 s). Quote protection
  must key off the venue book (mid change, trade prints), not off our state feed.
- **S439 scoreboard owners.** The historical J corpus defect (S541) may affect any arm-C result
  scored on mlb_clean rows (S347, Q17). The prospective scoreboard reads capture_view_v2, not
  mlb_clean.

## 6. What the next nights measure

- S439 (unchanged, other owners): arms A, B, B_lag, C and D, first fitted MLB/soccer night 2026-09-30.
- M2 (S544, after its seal): arms A and M2 per sport, segmented fresh/stale and late/not late,
  cumulative until each cell reaches 30 games. MLB postseason first; NBA from the regular season.
- Freshness census (S543): nightly focus coverage and feed lag, the prerequisite read-out for every
  other in-game number.

## 7. AMENDMENT 1 (2026-09-29 ~21:0xZ): two critique tiers folded in

Both critic tiers ran as Opus agents. The codex astra lane failed `turn.failed` twice (tags
ingame2_astra1 and ingame2_astra2, about 50 s and at once), so per the landing lessons it was not
retried again. The tiers were:
- an adversarial tier: `ingame_model_2_probes/critique/critique_opus_r1.md`, verdict REVISE;
- a contract tier: `critique/critique_contract_r1.md`, verdict REVISE.
Their probe scripts sit beside them (p5_dead.py, p4_window.py, astra_tail.py, s542_before_probe.py).
This block governs where it conflicts with sections 1-6.

**A1. RETRACTED: the NBA late-tail reading and "SHRINK beats FRESH".**
- Both were post-final-buzzer artifacts. P5 applied no live rule: S148 says live when period < 4
  or clock > 0, and 244,183 of 465,249 r1 rows are dead.
- On live ticks only:
  - 2025-26 clipped: PROJ - FRESH -0.00270 [-0.01057, +0.00377]; final-minute live cell
    +0.00730 [-0.00028, +0.01580].
  - All live 2025-26: SHRINK - FRESH -0.00047 [-0.00126, +0.00032] (critic).
  - Same cell recomputed by the S542 before-probe: -0.00045 [-0.00132, +0.00031].
- The late-tail candidate now rests on MLB J alone (one corpus, no game-end filter possible,
  S541). It is WITHDRAWN from the reserved follow-ups. The mu clip stays only as an a-priori
  numerical guard, and its branch contributes nothing to c.

**A2. The NBA corpus hides feed delay.**
- The state is ESPN wallclock joined as-of backward with zero delay.
- traded=True is hard-coded (nba_checkpoints_full.py:134).
- On LIVE consecutive ticks the price is unchanged 0.273 of the time; the pooled 0.652 includes dead
  ticks.
- So the P5 recovery fractions (0.396-0.440; 0.362 / 0.415 on live ticks at zero lag) are an upper
  bound. S542 becomes the live-like replay that decides whether any mechanism survives (S542
  AMENDMENT 1).

**A3. Formula correction (double count).**
- A fresh book can reprice before our feed reports the play. An anchor at the last mid change then
  already contains the event, and backing mu out of it with the pre-event state would apply the
  event twice.
- EVENT-AWARE ANCHOR: the c term applies only when no mid change falls at or after the play time
  of the latest known state change. Otherwise the output is the mid itself.
- With a fresh book and an unchanged state, the output is the mid exactly (a = 0, b = 1), never a
  Platt recalibration. P3 and P5's RECAL_FRESH control reject that.
- c is venue-specific. A Kalshi anchor uses c = 0 until c is fitted on Kalshi rows.

**A4. S544 is DEFERRED and rescoped.**
- It becomes a sealed READER of S439 night outputs, not a second shard scorer. Those outputs carry
  mid, mid_age_us, state, ts, book_ts and segment, so M2 gets the identical tick set and
  settlement.
- Arm A is the venue mid. Any cell whose staleness is our own receipt age is labelled "vs own stale
  receipt". No M2 < A cell is ever quoted as a statement about the venue.
- Seal by 2026-10-18, effective 10-19, before the NBA opener, and ONLY if S542 returns ACCEPT.
  Otherwise S544 is withdrawn.
- MLB S544 cells are pre-declared INSUFFICIENT through the 2026 World Series (at most ~53 games, and
  the stale segment empties as focus coverage grows).

**A5. S541 scope confirmed.**
- It adds a state-based guard and a no-initial-state fallback, relabels minutes_to_close as
  minutes to capture end, and never edits gate_a0_ingame_vs_market.py.
  baseline_four_arm_eligibility.py imports its EPS, N_MIN_GAMES and DATA_ROOT, so an edit would
  move the sealed S439 path.
- The spec writer could not reproduce the adversarial critic's "697 contaminated ticks in 7 games".
  The clock rule removes every stateful pre-start row, and the state guard is expected to drop 0.
- soccer_intl has 11 labelled games, all label 0, so soccer is UNDERPOWERED by construction.
- The re-derivation re-quotes a published number with a hygiene filter; it is not a new trial.

**A6. S543 is WITHDRAWN.**
- It duplicates the execution lead's S550 / S553 / S556 and the landed night_coverage_census.py
  and event_latency_census.py.
- Fresh/stale for M2 comes from S439's mid_age_us, labelled as OUR receipt age.

**A7. NEW row S545: S439 integrity audit (read-only).**
- The contract critic measured three problems on capture_view_v2:
  - MLB post-last-out ticks are scored. After the last out the frozen end state lasts 26-126 s
    before the first 'final' receipt: 09-24 p50 62 s / p90 243 s (17 rows); 09-25 p50 67 s
    (20 rows / 9 games); 09-26 p50 115 s (13 rows). 'End' maps to the next top half, so these ticks
    land in 'late'.
  - NBA end-of-period receipts map to 'live' (local_state_capture_sources.py:32-33). The segment
    accepts period 4 with clock 0, so post-buzzer receipts could score as late. This is unverified:
    there are no NBA live rows yet.
  - Arm A is scored on every tick, but B/C/D only where tick_row rebuilds the state (3 outs and
    empty states refused). So A and C cells cover different rows; only C_minus_B is paired.
- The audit re-summarises every arm on the paired intersection beside the sealed cells. It also
  counts terminal ticks per sport and splits by mid_age at 15 s.
- It never rewrites S439 output. It runs on the 09-24 output and from the first fitted night
  (2026-09-30) on.
- S546-S549 stay reserved (NFL WP formula; soccer Poisson projection after S490/S541; WNBA constants).

**A8. Wording corrections.**
- Section 1 "a fresh book has usually repriced by then" is an INSUFFICIENT indication (K_FRESH15,
  15 games); its SCORE subset points the other way (+0.968 [+0.017, +1.618], 12 games).
- The Gate A0 "minutes_to_close < 10" cell is the last 10 minutes of CAPTURE (close_ts = the last
  captured tick in 227 of 227 games), not the end of the game. The plan's MLB late-tail citation of
  it is withdrawn.

**A9. Order now.**
1. Build S541 and S542 in parallel (Opus builders in fresh worktrees).
2. Spec, then build, S545.
3. Two-tier verify, then land each.
4. The S542 replay runs on the real archive after landing and prints the verdict.
5. S544 waits for that verdict.

## 8. AMENDMENT 2 (2026-09-30 ~01:5xZ): what landed, and what the next nights measure

All rows below were verified by two Opus tiers (contract + adversarial), because codex was down; every landing ran
its per-file tests on main.

| row | landed | result |
|---|---|---|
| S541 corpus hygiene + Gate A0 re-quote | de9ebc332 | mlb_clean cleaned to 30,940 ticks / 177 games: model-minus-market Brier +0.01696 [+0.00834, +0.02542], still BEHIND (the original +0.03103 included 21,064 prior-game ticks); the minutes_to_close cell is minutes to CAPTURE end; soccer_intl 11 labelled games, all label 0, UNDERPOWERED and not quotable |
| S542 anchor projection + sealed live-like replay | 42d75dff4, replay 429a8e271 | verdict ACCEPT_STALENESS_BACKSTOP_ONLY. NBA 656 + 937 games, state delayed 18 s: PROJ minus STALE on projected ticks -0.00157 [-0.00194, -0.00121] / -0.00200 [-0.00296, -0.00127]; real state change beats a same-cell placebo (-0.00374 / -0.00378); canary and active-delay pass; cross-fit sigma 22 / 22. PROJ never ahead of a fresh price: +0.00058 [+0.00025, +0.00089] / +0.00006 [-0.00088, +0.00077]. Recovery of the staleness loss 0.73 / 0.97 at 18 s, 0.52 / 0.81 at 31 s, near 0 at 60 s (2024-25). MLB Sept, vs our own stale receipt, 34 games: -0.00422 [-0.00980, -0.00046], descriptive |
| S545 S439 integrity audit | e236a13dd, first audit 4a4eac39f | 09-24 RECONCILED 48 of 48; 9 post-last-out ticks (26-67 s before the first final receipt) scored 'late' by A and B_lag; 25 ticks unpaired (missing B_lag); rerun byte-equal |
| S544 Model 2.0 prospective read-out | seal A 03c288979 (PREREG_M2 alone, effective 2026-10-01), code B eb15edcb2 | arm M2 = A on fresh ticks (our receipt age <= 15 s), the event-aware projection on stale ticks; scored vs A on identical rows; HISTORY lists every night >= 10-01; MLB INSUFFICIENT by declaration through 2026; NBA from the opener. Every cell is vs our own stale receipt copy of the venue mid |
| M4 latency value map | e76c38ae8 | MLB state delay p50 21.8 s = about 5 s poll wait + about 17 s feed-timestamp-to-receipt; the S432 block is no faster; R(lag) grid for the capture-latency lead |
| S546 NFL WP, S547 soccer Poisson | specs b6e7d8827 (AMENDMENT 1 folded) | PREPARE-only formulas; no fit, no scoring; S546 waits on S502 (linking) and > 2 live games; S547 waits on live fixtures (~10-09) and a three-ticker anchor design in a new seal row |
| S548 WNBA constants | withdrawn to 2027 | |
| S543 | withdrawn | duplicate of S550 / S553 / S556 |

What the next nights measure:
- S439 (other owners): arms A, B, B_lag, C, D from the 2026-09-30 night.
- S545: every receipt, per the morning chain in NOW.md (terminal and post-final ticks, paired intersection, receipt-age split).
- S544: nights from 2026-10-01; MLB descriptive; the first NBA verdict cell needs 30 games after the opener.

Honest summary for the record: on a fresh venue book the mid is the model, and no candidate tested today beats it. The
Model 2.0 pieces that landed make the in-game read-out robust when OUR copy of the book is stale (a measured backstop),
make the sealed scoreboard's numbers auditable every night, and correct two historical corpora. None of them is a
statement about the venue.
