# Research slate 2026-09-30 (research director, read-only pass)

Paper-only desk. Calibration and execution-quality language only (Brier, log loss, cents per
contract, markout, fill rate). No money claim is made or implied anywhere below. Provisional ids
R1, R2, ... are NOT register ids; nothing here allocates an S-row. The files this pass read were
not changed; this file is the only file written.

Method: every number is quoted from a committed memo, receipt or probe stdout, cited by path and
line or by register row. Minimum detectable effects (MDE) are derived from the published CIs as
MDE ~= 2.8 x SE with SE = (CI95 half-width) / 1.96 (80 pct power, two-sided 5 pct). That is a
back-of-envelope rule, not a re-run. UNVERIFIED marks anything this pass could not check.
Data shards were not read beyond the first 200 lines of one shard per sport. Series and cadence
facts drawn from those samples are labelled as samples.

---

## 1. Power audit of the rejected Model 2.0 families

Sources: `docs/evidence/harness/INGAME_MODEL_2_PLAN_2026-09-29.md:49-63` (probe table),
`:159-177` (AMENDMENT 1 retractions), `:254-255` (S541/S542 results), probe stdouts in
`docs/evidence/harness/ingame_model_2_probes/`.

| family | target scored | unit of inference | games | CI quoted | approx MDE | reading |
|---|---|---|---|---|---|---|
| P1 post-receipt state reaction (MLB K) | signed MID MOVE 5-120 s after OUR state receipt (descriptive; no predictor, no arm) | event, game-clustered | pooled 40 games / 1,107 events; fresh-book subset K_FRESH15 15 games / 197 events | pooled post_120 +0.464 pp [+0.113, +0.839]; fresh post_120 -0.023 pp [-0.557, +0.399] (plan :51-52) | pooled ~0.52 pp; fresh ~0.68 pp | the fresh-book subset is INSUFFICIENT (15 games); it cannot see a sub-0.7 pp post-receipt drift |
| P2 price summaries MICRO / LAST / LAG / PAIR vs MID | final outcome (Brier) | tick (one per 30 s), game-clustered | 15 games / 2,020 ticks | MICRO +0.00002 [-0.00065, +0.00037]; LAST -0.00105 [-0.00267, +0.00165]; PAIR +0.00026 [-0.00006, +0.00051] (plan :55) | MICRO ~0.0007; LAST ~0.0031; PAIR ~0.0004 | underpowered for LAST; MICRO / PAIR can only rule out gains above ~0.0004-0.0007 Brier. The main-line spread was 1 c at p50 and p90, so MICRO has little room by construction |
| P3 recalibrating the mid (Platt, Platt + late, isotonic) | final outcome (Brier, log loss, ECE) | tick (one per 60 s), game-clustered | J walk-forward 196 games; J->K 15 games | J-WF Platt+late +0.00582 [-0.00337, +0.01559]; J->K (ii) +0.02008 [-0.02618, +0.04828] (`probe_p3_stdout.txt:64,75`) | J-WF ~0.0135; J->K ~0.053 | WEAK reject. Every point estimate is worse than the raw mid (the direction is informative), but the design could not detect a realistic recalibration gain of 0.001-0.003 Brier |
| P4 WE and STALE_DELTA residual features | final outcome (Brier) | tick (one per 60 s), walk-forward, game-clustered | J 124 games / 11,748 ticks; J->K 32 games | W vs B +0.00052 [-0.00040, +0.00145]; S vs B +0.00001 [-0.00006, +0.00008]; J->K W vs B -0.00636 [-0.01504, +0.00131] (plan :57-58) | W ~0.0013; S ~0.0001; J->K ~0.012 | STRONG reject for STALE_DELTA (MDE 0.0001) and adequate for WE on J. The cross-corpus cell is underpowered and leans the other way |
| P5 NBA market-anchored projection (PROJ) vs FRESH | final outcome (Brier) | per-minute tick, game-clustered, season split | 1,593 games (656 + 937); S542 live-like replay on the same corpus | S542 PROJ-FRESH +0.00058 [+0.00025, +0.00089] / +0.00006 [-0.00088, +0.00077] (plan :255) | ~0.0005 (2024-25) | well powered: PROJ is not ahead of a fresh price. Its only role is the staleness backstop (verdict ACCEPT_STALENESS_BACKSTOP_ONLY) |
| P6 soccer after-goal response | mid response at the goal tick (descriptive) + minute-band Brier | goal event / tick | 24 games / 47 goals; 11 labelled games, all label 0 (plan :63, :208) | at-goal +0.1248 [+0.0910, +0.1622] | n/a | UNDERPOWERED by construction (label defect, S541) |

The retracted NBA late-tail reading (plan :159-169) was a post-final-buzzer artifact. It is not
a family here and must not be re-quoted.

**Answer to the last question.** No Model 2.0 probe used a short-horizon mid change (5 s to
5 min ahead) as the scored target of a predictive arm. Every arm in P2-P5 was scored against the
final outcome. Short-horizon mid moves appear only descriptively:
- P1 measured the mid move 5-120 s after our state receipt, with no predictor.
- P5 ran a secondary direction check. On state-changed ticks, the next per-minute price change
  had corr 0.64 with PROJ-STALE (`probe_p5_stdout.txt:94-96`). That was at zero state delay,
  and AMENDMENT 1 A2 (plan :171-177) calls it an upper bound. It measures our stale copy, not
  the venue.
- Outside the block, three pieces touch short horizons:
  - S100 (`S100_microstructure_2026-09-03.md:107-130`) tested next-tick sign from depth
    imbalance and flow on the July corpus. It is a null: one cell of eight at p = 0.0499, with
    depth a median 194 s stale.
  - S435 / S457 event-response measure the mid at 5 / 30 / 120 s after events, report only.
  - The S550 / S551 execution receipts score markouts at 5-300 s. They are exploratory,
    INSUFFICIENT, and use no predictor.

So the short-horizon target is open. It is NOT untouched, though: S100 is a weak null on stale
depth, and S551's exploratory book-move cancel arm scored worse than static touch
(-2.01 c vs -1.90 c at +60 s, 3 games; register row S551).

---

## 2. What the archive holds

Sources: directory listing of `data/cache/ingame_books_local/` and `data/cache/ingame_capture_view_v2/`
(sizes via du), the first 200 lines of each 2026-09-29 Kalshi shard, the schedule censuses in
`docs/evidence/forward/schedules/*_full_selection.json.census.json`, the S550 receipts in
`docs/evidence/forward/exec_quality/`, and register rows S550 / S556 / S598 / S600.

### Kalshi (books root; capture_view_v2 mirrors the same sizes)

| sport | shards (dates) | size | series seen in the 200-line sample | depth | tape | games |
|---|---|---|---|---|---|---|
| MLB | 9 daily shards 09-21..09-30 | 1,480 MB | KXMLBGAME plus derivatives KXMLBF3, F5, F5SPREAD, F5TOTAL, F7, EXTRAS (all snapshot_bulk in the sample) | focus snapshots carry a top-5 ladder, ONLY in the first focus hour (S550 memo :174; S598) | trades by backfill for served tickers, per-game p50 259-3,981 s late (S556, S597) | served 3-6 per day (schedules); linked live games in Sept 47, settled linked 37, focus books on 15 (plan :32); S550 OK 8 of 19 served (09-22..09-26) and 2 of 3 (09-27..09-29) |
| NFL | 9 shards 09-21..09-30 | 615 MB | KXNFLGAME, KXNFLSPREAD (bulk) | served only | served only | 2 live linked games (M4 map :70); every ESPN state row has null start/date, which blocks linking (S502) |
| NBA | 9 shards | 22 MB | KXNBAGAME, KXNBA1STTEAM (bulk) | none yet | none | 0 live regular-season rows; one census game (S494) |
| WNBA | 3 shards 09-28..09-30 | 23 MB | KXWNBAGAME (bulk) | none | none | playoffs; 0 usable live rows (M4 map :70) |
| Soccer | 5 shards 09-25..09-30 | 43 MB | EPL, La Liga, Serie A, Bundesliga, Ligue 1 GAME (bulk; 3-way) | none (three-outcome events are refused from focus, S531) | none | 0 live rows in v2 (plan :73) |
| Tennis | 9 shards | 2,785 MB | KXATPCHALLENGERMATCH, KXATPSETWINNER, KXWTAMATCH; focus `snapshot` rows with market_state live and inline `trade` rows in the sample | UNVERIFIED (focus snapshots present in the sample; ladder depth not checked) | yes, inline trades in the sample | games_seen 391 on 09-23 (census); linked 0; count of live matches with focus books UNVERIFIED |

State archive: MLB 7 shards (105 MB; statsapi, source clock present). NFL 56 MB (0 of 1,516 live
rows carried a source clock before S595). Tennis 3,163 MB (sets only). NBA, WNBA and soccer have
no live rows.

**What Kalshi lists that the desk does not capture or serve:**
- Derivative series are captured only as bulk snapshots. They are never served or focused, so
  they get no depth and no tape. The D1 writer ignored 1,583 MLB derivative records and 855 NFL
  derivative records on 09-30 (`2026-09-30_run.json`, `record_counts.derivative_series_ignored`).
  On 09-26 it ignored 1,234 MLB, 470 NFL and 39 NBA.
- Most listed games are unserved:
  - MLB games_seen versus served: 15 vs 3 (09-23), 16 vs 3 (09-25), 14 vs 6 (09-26).
  - Tennis: 391 seen, 0 linked.
  - NFL: 16 seen, 0 linked (09-23), because of S502.
- Bulk cadence per ticker is about 11-30 s (one measurement quoted in NOW.md; per-series
  cadence UNVERIFIED).
- Player-prop series (KXNBAPTS / REB / AST / 3PT, KXMLBPITCH) are referenced in code. Whether
  the archive holds them is UNVERIFIED: no series census exists. Building one is step 0 of R3.

### Polymarket

- Live: only an `mlb` directory exists (6 shards, 09-24..09-30, 803 MB), with CLOB books and
  trades (S397).
- One polymarket tick lasts about 22 min over 1,177 markets, so each market is revisited only
  about every 20 min (S600, measured 03:59Z). P1 measured the home-token receipt gap at p50
  1,329 s (`probe_p1_stdout.txt:182`).
- That capture is unusable for any in-game timing question until S600 PART C (served-first,
  bounded markets per tick) lands.
- Historical:
  - NBA checkpoints: 1,593 games of per-minute candles, with traded=True hard-coded
    (plan :173).
  - The `data/cache/inplay_odds` store holds Kalshi MLB moneyline, spread and total series with
    minute-quantized Kalshi timestamps. S99 found 99 MLB games with at least two market types
    and 96 soccer_intl games (`S99_cross_market_2026-09-03.md:37-40`).
  - A cross-venue panel of 279 MLB and 40 NBA events has lead-lag UNDETERMINED because of
    minute quantization (`MASTER_PLAN_2026-09-14.md:133-141`).

---

## 3. Candidate directions

### (a) Short-horizon mid-move prediction for a resting maker quote

- **Tested or specced:**
  - Partially. S100 (null, July, stale depth).
  - S460 arm E carries touch_imbalance, signed_flow_60s, spread and quote age as features, but
    scores them against the final OUTCOME, not markout (`microstructure_features.py:15-16`).
    Its nights read `config_not_effective` (`registry_e/2026-09-26.json`).
  - S551 is the only markout-scored policy comparison. Its arms are static / book-move /
    state-receipt cancels. It is sealed with a floor of 30 paired games, and S557 projects the
    look as unreachable on MLB alone.
  - No row predicts the markout from book state or tape.
- **Testable on the existing archive:** yes, for the MLB served games with depth in their first
  focus hour. The base is S550: 8 OK games, 2,064 touch join instants, 676 fills at 60 s, and
  15,654 tape prints at 60 s (`exec_quality/2026-09-22_2026-09-26.json`). Tennis probably adds
  far more matches with focus books and inline trades, but that is UNVERIFIED; R1 step 0
  settles it.
- **The measured baseline the predictor must beat:** a static touch fill captures +0.40 c
  against the prior mid at fill, [0.30, 0.48] (touch|60s|vs_mid_at_fill). Its markout at +60 s
  is -0.67 c per contract, fee excluded, ci90 [-0.86, -0.50] over 7 games and 676 fills
  (touch|60s|mo60). The maker fee is 1 c at interior prices under the repo's rounding
  assumption (receipt note:fee). So about 1.07 c of adverse movement arrives within 60 s of a
  touch fill.
- **Power:** the per-game SD of the paired markout is about 0.29 c (from the ci90 half-width
  0.18 on 7 games). The MDE is about 0.26 c at 10 games and about 0.15 c at 30 games per
  stratum.
- **What must be built:** a causal feature snapshot at each join instant; a fixed-sign or
  frozen-coefficient score; arms reusing `tape_fill_sim` / `markout_causal` read-only; a seal.
- **What a REJECT teaches:** touch adverse selection on Kalshi is not forecastable from the
  displayed book and tape at our cadence. Then:
  - The main-line maker arm stays fee-dead (1 c spread, 1 c fee).
  - S552 / S554 / S555 lose their premise.
  - S597 part 2 (real-time tape) has no measured decision value.

### (b) Derivatives and multi-outcome sets from one latent object

- **Tested or specced:**
  - S99 tested a season-rate Poisson model against in-play derivatives. It was BEHIND on both
    MLB legs: moneyline -0.0404 [-0.0696, -0.0112], total -0.0206 [-0.0351, -0.0061], 52 games
    (`S99_cross_market_2026-09-03.md:104-110`).
  - Its market-coherence number (0.26 mean inconsistency) was a joint statement driven by a
    fixed, wrong-shaped split (:153-161), not a market defect.
  - What S99 did NOT test is the anchored version: solve both run rates from the liquid
    moneyline mid plus the total-ladder median, then price the derivatives from those.
- **Landed but never run on a market:**
  - S339 sum-to-one coherence audit ("NO REAL CAPTURE CONSUMED").
  - S368 structural coherence scanner ("nothing measured on a market").
  - The MLB in-play derivative channel `scripts/platformkit/ingame/inplay_derivative_mlb.py`
    exists, but its output directory `data/cache/ingame_grade_deriv/` does not exist, so it
    never ran.
- **Testable:** yes, on two corpora. One is the July inplay_odds store (99 MLB multi-market
  games, minute timestamps). The other is the Sept-Oct live archive (bulk F3 / F5 / F5TOTAL /
  F5SPREAD / F7 / EXTRAS). Per-game derivative coverage in the live archive is UNVERIFIED.
- **Power:** at 99 games and a tick-level Brier target, the MDE should be about 0.002-0.004,
  by analogy to P4's J->K cell at 32 games (~0.012) scaled by sqrt(99/32).
- **What must be built:** the anchored latent pricer (reuse `domains/mlb` repricer /
  negbinom_engine and `mlb_deriv_align` read-only), a streaming parquet reader with column
  projection, a residual scorer, and a seal.
- **What a REJECT teaches:** Kalshi derivative prices are coherent with the main line within
  our pricer's error. That closes Gate C of the master plan (`MASTER_PLAN_2026-09-14.md:331-334`)
  at current model quality.

### (c) Late-game Kalshi calibration (both signs)

- **Status:**
  - The NBA Polymarket read (Q12) did not replicate the insurance distortion at exploitable
    size, and at 3-6 min it ran the opposite way (`MASTER_PLAN_2026-09-14.md:110-119`).
  - The NBA P5 tail was retracted as a post-buzzer artifact (plan :159-169).
  - The surviving evidence is MLB J only. With inning >= 8, the <0.10 band was priced 0.0445
    against realized 0.0084 (70 games), and the 0.10-0.20 band priced 0.1445 against realized
    0.0634 (48 games) (plan :56).
  - J has no game-end filter (plan :168), so the J tail carries the same post-final
    contamination risk that killed the NBA reading. It is exploratory only.
- **Games the archive holds now:**
  - Fresh late-game Kalshi books: essentially none. The focus window closes 3,600 s after each
    served start (NOW.md 09-23 delta; S459 census: no in-window observation in innings 7-9).
    K late inning >= 8 has 3 games (`probe_p3_stdout.txt:17`).
  - Bulk mids at about 11-30 s cadence exist for every listed MLB game through the end. That
    cadence is enough for a calibration question (not an execution question), but a
    per-game count of bulk late ticks is UNVERIFIED.
  - NBA books are treated as pregame while games are played until S561 is adopted (S561 row).
- **When it reaches power:** the estimand is the losing-side band distortion D. The per-game SD
  of D is about 0.27 at p ~ 0.08, so the MDE is about 14 pp at 30 band-games and about 5 pp at
  250. A J-sized effect (4-8 pp) therefore needs roughly 250 or more band-games per sport.
  - MLB postseason: at most 49 games remain (S557), so MLB alone never reaches it.
  - NBA with bulk capture of every game through the final buzzer: about 8 games per night, and
    perhaps half entering the band (that rate is UNVERIFIED), gives about 60 nights, so late
    December 2026.
  - The 30-game floor alone is reachable in about the first week of the NBA season. It only
    detects gross (>= 14 pp) distortions.

### (d) Cross-venue lead-lag (S436 / S441)

- **Status:**
  - S397 capture runs for MLB, so S436's premise ("whether the landed capture runner already
    serves Polymarket") is answered: yes, MLB only.
  - S398 pairing and coherence counts are landed.
  - S441 is DEFERRED by astra because 1 s ordering is not established under the Polymarket
    cadence and the 5 s pairing skew.
- **What is measured now is worse than the deferral assumed:** a Polymarket market is revisited
  about every 20 min (S600), and P1 measured a p50 receipt gap of 1,329 s. Lead-lag is
  unmeasurable on the current archive.
- **What is missing, in order:**
  1. S600 PART C (served-first, bounded per-tick markets).
  2. A Polymarket book socket, or a sub-10 s served poll.
  3. The S442 Kalshi socket adopted, for sub-second Kalshi ordering.
  4. Polymarket capture for any sport other than MLB.
- **Verdict:** this candidate is killed on the current archive. Re-open it after PART C is
  adopted and a census shows a Polymarket served-market cadence of 10 s or better.

### (e) Latency: what S593 would buy

- In the desk's own measured terms (`INGAME_M2_LATENCY_VALUE_MAP_2026-09-30.md:42-48, 76-79`),
  cutting the MLB state delay from about 21 s to 5-10 s moves PROJ's recovery of the staleness
  gap:
  - 2024-25: from about 0.64 to 0.82-0.91;
  - 2025-26: from about 0.84 to 1.03-1.11;
  - that is roughly +0.2 to +0.3 of the gap.
- In Brier on all ticks this is PROJ-STALE going from about -0.00095 to about -0.00123 /
  -0.00136 (2024-25). That is an incremental ~0.0003 Brier, and only against OUR stale receipt
  copy. It is an NBA-to-MLB transfer, not an MLB measurement.
- Against a fresh book the value is zero: "a fresh anchor needs no projection" (:77-79).
- For execution, the book had already moved before our receipt on 0.509 of plays, against a
  matched control of 0.438 (S550 receipt, ev_play and ctl before_receipt). The push socket
  arrives about 7.5 s after the play (S592/S593), so it would move some plays from "book first"
  to "trigger first". That share is unmeasured.
- The MLB season ends about 11-01, so a 2026 build buys at most a few weeks.
- **Verdict:** wait, unless R1 shows that state-event recency carries markout information
  beyond the book.

### (f) NBA opener readiness (regular season from 2026-10-20 per S494)

Must be done before the first regular-season game so that NBA nights count:
1. S561 (NBA books live window) adopted. The 08:37Z 09-30 one-shot status is UNVERIFIED at
   writing. Without it, NBA books are pregame-classed while games are played.
2. S494 adopted (season_type labels through the 07:57Z state2 one-shot, UNVERIFIED), so
   preseason never pools into B/C history. S580 is landed.
3. S502 fix plus a state2 restart. Every ESPN-sourced NBA row has a null start and date, which
   blocks linking. The register targets TNF 10-02; for NBA it is a hard prerequisite.
4. S562: NBA added to D1 sports (paper-desk-improve), by the D1 run of 10-19.
5. S557: the NBA addendum to S551, sealed ALONE before the 10-19 D1 run. It needs S561, S562
   and the capacity precondition (<= 4 served per date or a measured < 400 MiB peak).
6. The seal chain S469 (10-01/10-02) and S625 (10-02/10-03). S625 excludes post-final-buzzer
   ticks for NBA, which is exactly the retracted-artifact class.
7. S564 (live possession / foul enrichment) and S596 (nba_pbp primary with a source clock).
   S564's own deadline is before 10-20. S596 is blocked until NBA games are live; preseason
   games are the measurement window.
8. S594 (serial state tick stalls). NBA state shares the tick with tennis at 1.08 GB/day. It
   should land before the opener, after the S535 adoption.
9. R2 (below), if pursued: sealed before 10-20.

Already sealed or not needed before the opener:
- S544 PREREG_M2 is effective from 10-01, and NBA cells start at the opener (plan :257).
- S482 (NBA PREREG_E) by its own rule waits for the first live-night census, so NBA arm E will
  not count on the first nights. That is by design.
- S518 NBA shadow: land after the 10-01 read-out, adopt after S561 plus the KXNBAGAME gap probe.
  Whether S519's seal admits NBA nights is UNVERIFIED; the row reads MLB.

### (g) Higher information per unit of effort than (a)-(f)

1. **Run the landed coherence scanners (S339, S368) on the Sept archive.** Both are landed and
   tested and have never consumed a real capture. A counts-only, fee-netted, streaming run over
   the MLB, NFL and tennis bulk ladders costs almost nothing. It answers whether any structural
   incoherence exists before R3 builds a latent pricer. This is R3's step 0.
2. **Bulk mids for all listed games.** Calibration questions (not execution questions) can use
   the bulk snapshots of every listed game at about 11-30 s cadence, not only the 3-6 served
   games. That roughly triples MLB N per night (games_seen 14-16 against 3-6 served), provided
   book age is labelled per tick. R2 depends on this.
3. **Tennis as the high-N microstructure corpus.** The markout question in (a) needs neither
   state nor outcome, only books plus tape. Tennis is the largest shard family (2.8 GB) and
   carries focus snapshots and inline trades. If step 0 confirms 30 or more live matches with
   depth and tape, it gives R1 its independent second corpus within days rather than a
   postseason.

---

## 4. Ranked slate

Ranked by expected information about the objective (calibrated in-game prediction and execution
quality) per unit of cost:

| rank | id | direction | cost | time to a verdict | prior of REJECT |
|---|---|---|---|---|---|
| 1 | R1 | short-horizon markout predictability for a resting touch quote (MLB plus tennis) | medium (reuses S550 / S551 loaders and simulators) | days to 2 weeks if tennis qualifies; else 2027 | about 70 pct (about 90 pct that nothing makes the MLB main line fee-inclusive non-negative) |
| 2 | R2 | late-game Kalshi calibration, both signs, game-end filtered, bulk mids for all games | low (one reader plus a seal) | the 30-game floor in about the first NBA week; power for J-sized effects about late December | about 70 pct |
| 3 | R3 | anchored latent pricer: derivative coherence residual as a predictor of the derivative's later mid and outcome (MLB) | medium-high | about 2 weeks for the historical corpus; the second corpus accrues through the postseason | about 80 pct |
| 4 | S557 | NBA admission for S551 (enabling, not new research) | low | seal before 10-19 | n/a |
| 5 | (d) | cross-venue lead-lag | blocked | after S600 PART C plus a cadence census | n/a |
| 6 | (e) | S593 push socket | medium plus a new process | 2027 value | n/a |

### R1 sketch: markout predictability for a resting touch quote

- **Estimand.**
  - Primary: the per-opportunity markout of a 1-contract order joined at the touch at 30 s grid
    instants (the S550 touch arm), marked at the first focus snapshot in [t_fill + 60, +70] s,
    fee excluded, in cents per contract. Unfilled opportunities score 0, so arms that skip
    quotes are compared fairly.
  - Primary contrast: arm P minus arm S, as the mean over games of the paired per-game
    per-opportunity markout.
  - Secondaries: per-fill markout at +5 / +30 / +300 s, fill rate, fee-inclusive markout at
    +60 s, and the adverse tail (p10 per-fill markout).
- **Inputs.**
  - Kalshi focus `snapshot` rows (touch and top-5 ladder), `trade` rows (created_time,
    taker_side, count_fp), and MLB state receipts.
  - Features at decision instant t, each causal at receipt time:
    - touch_imbalance and top-5 depth imbalance;
    - spread in cents;
    - seconds since the last mid change;
    - quote age;
    - signed trade count over the last 60 s, in two variants: T_asrecv uses prints whose
      capture receipt is at or before t (what the desk sees today); T_rt uses prints whose
      created_time is at or before t (the upper bound, which is the value of S597 part 2);
    - for MLB, seconds since the last state receipt carrying a play.
  - Polymarket is excluded; its cadence is ~20 min (S600).
- **Exclusion rules.**
  - Games in TAPE_MISSING / NO_DEPTH / NO_LIVE_STATE (S550 census). NO_LIVE_STATE applies to
    MLB only; tennis runs book-only.
  - Crossed or empty books; book age above 5 s at t.
  - The first 60 s after a focus window opens; any instant after the last out or final (S625
    rule).
  - Block trades; prints with receipt before created (counted, as in S550).
  - Games with fewer than 20 join instants.
  - A census reports every exclusion.
- **Arms.**
  - S: static touch (baseline).
  - B: cancel on book move (the S551 parameters, sealed values).
  - P_book: skip or cancel when a FIXED-SIGN score s = z(imbalance against our side)
    + z(seconds-since-mid-change inverse) exceeds a threshold. The threshold is chosen on the
    development window only (archive dates up to the seal date) at the skip share that keeps
    fill rate at or above 0.7 x S.
  - P_asrecv: P_book plus T_asrecv.
  - P_rt: P_book plus T_rt. This arm is an upper bound, never a policy.
  - Coefficients and thresholds are frozen in the seal. No refit after the seal.
- **Decision rule, both signs.** Per sport stratum, game-clustered bootstrap (2,000 draws,
  seed fixed in the seal), Holm over the four contrasts P_book-S, P_asrecv-S, P_rt-S, B-S:
  - BETTER if the CI95 lower bound is above 0;
  - WORSE if the CI95 upper bound is below 0;
  - otherwise MATCH.
  A BETTER is reported as an execution-quality improvement in cents per opportunity. It is
  called "fee-inclusive non-negative" only if the fee-inclusive per-fill markout CI also
  excludes 0 on the positive side. No money language.
- **Sample floors.** 30 paired games AND 300 fills per arm per sport. The master plan asks
  for >= 300 fills and >= 50 games per class (`MASTER_PLAN_2026-09-14.md:125-126`), so a
  CONFIRMATORY look waits for 50 if reachable within 60 days of the seal. Two corpora: MLB and
  tennis, never pooled. A BETTER must replicate in both, or it is labelled single-corpus.
- **Step 0 (before the seal, counts only).** Stream the tennis and NFL shards through the S550
  loader with a status census. It reports live matches with focus depth plus tape per day. If
  tennis gives fewer than 30 OK matches by the seal date plus 14 days, R1 runs MLB-only and is
  declared underpowered through the World Series (S557 arithmetic).
- **Memory budget.** Stream one (sport, day) shard at a time through `exec_quality_audit_io`
  (S550 peak 52-96 MB; S551 peak 336 MiB per replay day). Keep per-game sufficient statistics
  only. Use a psutil check every 10,000 lines and exit 5 above 400 MiB with no receipt.
  Tennis day shards are about 300 MB on disk, so streaming is mandatory.
- **New files.** Under `scripts/platformkit/execution/`:
  - `markout_predict_r1.py` (features plus arms, pure);
  - `markout_predict_r1_io.py` (streaming, receipt, census);
  - `markout_predict_r1_prereg.py` (seal writer and `--check`);
  - tests `tests/platformkit/execution/test_markout_predict_r1.py` and `_io.py`;
  - the seal `docs/evidence/forward/exec_policy/PREREG_R1.json`, committed alone.
  It imports `tape_fill_sim`, `markout_causal`, `exec_quality_audit_io` and `venue_fees`
  read-only. It touches none of `ingame_scoreboard*.py`, `baseline_four_arm*.py`,
  `paper_night*.py`, the S519-pinned live-shadow files, or `quote_engine.py`.
- **Honest prior.** About 70 pct that P_book and P_asrecv are MATCH or WORSE. S100 was null;
  S551's book-move arm was already worse on 3 games; the MLB main-line spread is 1 c at p50 and
  p90 (microstructure census 09-22), which leaves little room. About 90 pct that no arm makes
  fee-inclusive MLB main-line markout non-negative. The P_rt minus P_asrecv gap is the most
  decision-relevant output either way: it prices S597 part 2 before anyone builds it.

### R2 sketch: late-game Kalshi calibration

- **Estimand.**
  - Primary: the losing-side band distortion D = mean over games of (the per-game mean mid of
    the side priced in [0.02, 0.20]) minus (that side's realized outcome), inside the final
    window.
  - The final window is: NBA period >= 4 with game clock <= 600 s, and OT; MLB inning >= 8
    (J comparability), with inning >= 9 as the pre-declared sensitivity.
  - Secondary: the same for [0.80, 0.98] (symmetric); the Platt slope of outcome on logit(mid)
    in the window (H0 slope = 1); Brier of the mid in the window.
- **Inputs.**
  - Kalshi `snapshot` and `snapshot_bulk` rows for KXNBAGAME / KXMLBGAME, for ALL listed games,
    not only served ones. Mid = (yes_bid + yes_ask) / 2.
  - Tick age is labelled from the receipt; one tick per 30 s per game.
  - State from capture_view_v2 is joined as-of by receipt. The outcome comes from the final
    state row.
- **Exclusion rules.**
  - Ticks at or after the last out or final buzzer (S625 rule).
  - Games with no final row; preseason (S494 season_type); doubleheader key failures (counted).
  - Crossed or empty books; book age above 30 s; spread above 10 c.
  - Games whose first window tick has the losing side outside the band.
- **Arms.** A = the raw mid. There is no fitted arm; the test is calibration of the venue price
  itself. A secondary arm applies an a-priori Prelec form with gamma = 0.8 (fixed in the seal,
  not fitted) and is scored against A as a direction check only.
- **Decision rule, both signs.** Game-clustered bootstrap CI95 on D per sport:
  - OVERPRICED_LOSER (the paper's sign) if the lower bound is above 0;
  - UNDERPRICED_LOSER (the Q12 3-6 min sign) if the upper bound is below 0;
  - CALIBRATED otherwise.
  A non-CALIBRATED verdict is labelled "actionable-size" only if |D| exceeds the median window
  half-spread plus 1 c. Otherwise it is "calibration finding, below spread plus fee".
- **Sample floors.** 30 band-games per sport for any verdict. The seal also records the MDE
  table: about 14 pp at 30, about 8 pp at 90, about 5 pp at 250. Every verdict is printed with
  it, so an early CALIBRATED is never read as "no distortion".
  - Corpus 1: NBA 2026-27 from 10-20.
  - Corpus 2: MLB postseason from the S598 adoption (10-01), with bulk mids for non-served
    games.
  - J (June-July) is exploratory only, because it has no game-end filter.
- **Memory budget.** A line-streaming reader filtered on the `series` field before JSON decode
  of the whole row (a prefix check), holding per-game running sums only. It is under 100 MB and
  capped at 400 MiB by the same psutil rule.
- **New files.**
  - `scripts/platformkit/ingame/late_game_calibration_r2.py` (pure);
  - `late_game_calibration_r2_io.py`;
  - tests `tests/platformkit/ingame/test_late_game_calibration_r2.py`;
  - the seal `docs/evidence/forward/late_game/PREREG_R2.json`, committed alone before
    2026-10-20, effective at the first regular-season game.
  It reads S625's terminal rule by import, and does not edit it.
- **Honest prior.** About 70 pct CALIBRATED. Q12 did not replicate on NBA Polymarket; the NBA
  P5 tail was an artifact; the J tail has no game-end filter. A REJECT closes master plan 2b.1
  and removes the last structured in-game miscalibration candidate. An OVERPRICED_LOSER that
  replicates on both sports is the first venue-level calibration finding the desk would have.

### R3 sketch: anchored latent pricer and derivative coherence (MLB)

- **Step 0 (counts only, no build).** Run the landed S368 structural coherence scanner and the
  S339 sum-to-one audit over the Sept archive's MLB, NFL and tennis bulk ladders. Also run a
  streaming series census: per series, per day, tickers, rows, and median receipt gap. If the
  census shows fewer than 30 games per derivative family in the live archive by the World
  Series, corpus 2 is declared INSUFFICIENT up front.
- **Estimand.**
  - Latent object: at each tick t, solve the home and away remaining-run rates so that the
    model reproduces BOTH the liquid KXMLBGAME mid and the full-game total ladder's 50 pct
    strike (two constraints, two unknowns; identified, unlike S99's fixed split). Then price
    each derivative contract (F5 winner, F5 total strikes, F5 spread, off-median total strikes,
    run line).
  - The residual is r = derivative mid minus latent price.
  - Primary: the slope beta of the derivative's signed mid change over [t, t + 15 min] on r
    (the coherence-reversion slope), game-clustered.
  - Secondary: horizons of 5 and 30 min; Brier of mid versus mid + k r against settlement, with
    k fitted on corpus 1 only and frozen.
- **Inputs.**
  - Corpus 1: `data/cache/inplay_odds` MLB multi-market games (99; July; minute timestamps),
    with outcomes from `games_current` (S99 settlement rule `final total >= strike` reproduces
    1.000).
  - Corpus 2: the live archive's bulk derivative snapshots, from the seal date through the
    World Series.
  - The latent pricer reuses `domains/mlb` repricer / negbinom_engine and `mlb_deriv_align`
    read-only.
- **Exclusion rules.**
  - Ticks where the moneyline cannot be reproduced within 0.02 (S99 saw 20.5 pct of MLB
    ticks); counted, not dropped silently.
  - Derivative book age above 60 s against the anchor; spread above 10 c; post-final ticks.
  - Doubleheader keys that fail the parser (S99 defect 4).
- **Arms.**
  - A: derivative mid.
  - C: mid + k r.
  - Placebo P: r computed from an anchor lagged 30 min. It must NOT show the same slope, or
    the effect is staleness, not coherence.
  - The strata stale / fresh derivative book (age above or at most 30 s) are pre-declared.
    A result on stale books only is labelled a freshness effect of OUR capture, not a venue
    statement.
- **Decision rule, both signs.**
  - REVERTS if the beta CI95 lies entirely in (0, 1] and exceeds placebo beta by a CI
    excluding 0.
  - DIVERGES if the beta CI upper bound is below 0.
  - otherwise NO_SIGNAL.
  - For Brier, C minus A as BETTER / WORSE / MATCH.
  - Both corpora must agree for any non-null verdict.
- **Sample floors.** 30 games per derivative family per corpus. Families below the floor print
  INSUFFICIENT.
- **Memory budget.** Parquet via pyarrow `iter_batches` with column projection (the store is
  about 13.47M rows for MLB per S637). Rows are sorted and grouped per game from a
  pre-computed game index, holding one game at a time. JSONL is line-streamed. Cap 400 MiB.
- **New files.**
  - `scripts/platformkit/ingame/deriv_coherence_r3.py` (latent solve plus residual, pure);
  - `deriv_coherence_r3_io.py`;
  - `deriv_series_census_r3.py` (step 0);
  - tests `tests/platformkit/ingame/test_deriv_coherence_r3.py`;
  - the seal `docs/evidence/forward/deriv/PREREG_R3.json`, alone.
  No edit to `inplay_derivative_mlb.py` or to the domains pricer.
- **Honest prior.** About 80 pct NO_SIGNAL or MATCH. Kalshi derivatives are most likely priced
  off the same main line by the same makers. S99's large inconsistency was shown to be our
  model's shape. Minute-quantized corpus-1 timestamps blur 5-min horizons. A REJECT closes the
  derivative value surface at current model quality. A REVERTS confined to stale bulk books
  says our capture is late, not the venue.

---

## 5. Backlog verdicts

- **S469:** build now. It is already built (h163) and sits in the seal chain (commit A 10-01,
  B 10-02); proceed as scheduled.
- **S498:** wait for arm E to become effective (caller policy) and for NBA volume. Land it
  between nights before S482 seals. Postseason MLB slates of at most 4 games stay well under
  the quadratic scan's pain point.
- **S504:** build now, merged with S641. Both are the same served-surface honesty defect
  (stale as_of). Small and scripts/platformkit-only; no research value, but it stops served
  numbers from reading as current.
- **S516:** drop from this list. It is LANDED (fa99c29cd, 2026-09-29).
- **S546:** wait for S502 linking, S595 adoption, and more than 2 linked live NFL games.
- **S547:** wait for S531 / S534 and live fixtures (~10-09). Low priority: P6 shows soccer
  repricing completes within one tick, so the staleness backstop has little to recover.
- **S557:** build now. It is the only path to S551's look, and its seal deadline is before the
  10-19 D1 run.
- **S558:** build now (hand the PROPOSED diff to paper-desk-improve). Receipts that do not run
  unattended do not accrue games.
- **S588:** wait for a RAM window at or above the fault-matrix bar. The code is written but not
  run; this is ops, not research.
- **S593:** wait. Its value against a fresh book is zero, and against our stale copy it is
  about +0.2-0.3 of the staleness gap (NBA-transferred). The MLB season ends about 11-01.
  Revisit for 2027 or if R1 shows state-event recency carries markout information.
- **S594:** build now, after the S535 adoption and before the NBA opener. It stalls every
  ESPN sport, NBA included.
- **S597 part 2:** wait for S598 adoption (its own gate) AND for R1's P_rt minus P_asrecv gap.
  If that gap is MATCH, drop it.
- **S600 part B:** build now; it rides the S598 books restart.
- **S600 part C:** build after S598 lands. It is the prerequisite for any Polymarket in-game
  use, including (d).
- **S637:** wait for a RAM window. Test hermeticity, and one case reads 1.5 GB.
- **S640:** build now. The test self-heals the REAL CLV ledger, a data-integrity landmine; do
  not run the file until fixed.
- **S641:** build now, together with S504.
- **S642:** build now. One invalid event silently drops later issue batches, a data-loss path
  in the issue ledger.

---

## 6. What this pass did not verify

- The count of tennis live matches with focus depth plus tape, and whether tennis ladder depth
  is populated (R1 step 0).
- Per-series presence and per-ticker bulk cadence of derivative and prop series (R3 step 0).
- Whether the 07:57Z (state2) and 08:37Z (books, S561) one-shots of 09-30 fired.
- Whether S519's seal admits NBA nights.
- The NBA losing-side band entry rate used in R2's power arithmetic (the 0.5 figure is an
  assumption).
- Whether Kalshi trades are captured for unserved or derivative tickers.
