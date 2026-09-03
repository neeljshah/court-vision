# Model-quality program -- per sport, per phase (2026-09-04)

Scope: make the PREDICTOR better, per sport, in both phases (pregame prior; in-game conditional).
Calibration language only (Q6). Every number below is quoted from a named artifact with its as-of;
no number appears without a citation. The market is efficient pregame -- matching the devigged close
within noise is the ceiling we claim, never beating it. An honest REJECT or a retraction is a win.

Sources read: docs/JOB_EVIDENCE_PACKET.md, docs/MARKET_EFFICIENCY_PROOF.md,
docs/evidence/calibration-decomposition.md, docs/evidence/ingame-conditioning.md,
docs/evidence/harness/{S05_calibration_report, S82_ingame_screen, S80_player_grain,
INGAME_SIGNAL_PROGRAM, REDTEAM_SIGNAL_FACTORY, S108_pregame_full_model, S88_phase_recal,
wnba_ingame_census, new_gap_harvest}, docs/evidence/HARNESS_GAPS_2026-09-03.md, and the sourced method
menu docs/research/model_quality_methods_2026-09-04.md.

**Where this program uses that method menu.** Its item 12 (regime-key leak) is already allocated as
S200 and is not duplicated here; note that the menu calls item 12 "blocked on S44", and S44 has since
landed an `event_date` column on all four gate corpora, so the block is lifted. Item 9 (market-anchored
residual) is called BLOCKED on a missing close join; that premise is false on disk and S204 records it.
Items 3, 2 and 1 (bakeoff, temperature, beta) become S205; item 5 (Stern 1994) is the candidate arm in
S206; item 10 (freshness stratification) is the third axis in S207. Items 6, 7, 8 (MLB Markov,
Dixon-Coles, tennis point-level Markov) and item 11 (hierarchical shrinkage) are NOT proposed this
round: 6/7/8 are L-effort mechanism models and 11 sits downstream of the S205 bakeoff.

---

## 1. PREGAME -- current honest state per sport

| sport | corpus (rows) | ECE before -> after | market reference on disk | measured gap vs the close | source |
|---|---|---|---|---|---|
| nba | gate_corpus_nba 1,814 | 0.053328 -> 0.024843 | p_close non-null 563/1,814 | close beats Elo +0.025606 Brier (0.211728 -> 0.186122, n 351) | S05 table; measured 2026-09-04; S112 register row |
| mlb | gate_corpus_mlb 39,162 | 0.005918 -> 0.008077 (WORSE) | p_close non-null 910/39,162 | close beats Elo +0.007269 Brier (n 276) | S05 table; measured 2026-09-04; S112 |
| soccer | gate_corpus_soccer 25,834 | 0.106927 -> 0.009302 | devigged close joined 16,322/16,322 | Brier close 0.239460 vs p_base 0.262703 = +0.023243 | S05 table; S02 memo |
| tennis | gate_corpus_tennis 41,886 | 0.038691 -> 0.008403 | close joined 33,685 states, vintage SYNTHETIC | S108 elastic net vs the close -0.000058 (n 14,873) | S05 table; S03; S108 |
| wnba | NO gate corpus on disk | n/a | n/a | n/a | data/cache/combo listing 2026-09-04 |

Verdict on all four scored sports is FLATTENED, never IMPROVES: per-regime isotonic buys calibration
and pays resolution every time (nba -0.0026823, soccer -0.0005781, tennis -0.0006802), and on mlb it
made BOTH ECE and Murphy reliability worse (S05 section 2). `reproduction_max_abs_diff` = 0.0 on all
four, 0 rows dropped.

**Two corrections already measured that the published table does NOT yet carry:**
- S50 (LANDED 12db4d4f5, opt-in, default OFF): a per-corpus_unit event_date walk moves ece_after on
  all four -- nba 0.024843 -> 0.026583, mlb 0.008077 -> 0.012666, soccer 0.009302 -> 0.028722,
  tennis 0.008403 -> 0.015403; tennis splits ATP 0.039461 -> 0.012985 / WTA 0.038484 -> 0.023195
  ("the whole S05b cost was WTA calibrated on a decade of future ATP history"). No caller switched
  yet (batch_gate.py:193 still walks row order).
- S200 (OPEN, queued): the regime KEY is fitted on the scored row, so all four after-ECEs rest on a
  whole-corpus tercile ranking. Until S200 lands, quote the four after-ECEs as provisional.

**Best available predictor to match:** the Shin-devigged close. Where it is joined, the public
scoreboard (docs/MARKET_EFFICIENCY_PROOF.md lines 29-34) reads NBA moneyline Brier 0.1735 vs 0.1672
(n 372, MATCH), MLB moneyline 0.2429 vs 0.2390 (n 13,992, MATCH), soccer O/U-2.5 0.2465 vs 0.2390
(n 7,558, MATCH), tennis ATP 0.2177 vs 0.2028 (n 7,374, BEHIND -- freshness).

**Named causes of the pregame gap.**
1. The gate-corpus predictor is a rating prior, not a market-anchored model: `p_base == p_elo`
   byte-identically on nba (S98), and the same Elo family on mlb/tennis; soccer's is a Poisson
   `p_over25` baseline. That is why the close is +0.0256 (nba) / +0.0073 (mlb) ahead of it.
2. More features do not close it. S108 fit every numeric as-of column the corpora supply
   (178 / 22 / 54 / 178 for nba/mlb/soccer/tennis) with logit(incumbent) as a true offset and
   nested walk-forward: elastic net +0.001360 (nba, n 619), +0.000061 (mlb, n 16,791),
   -0.000033 (soccer, n 6,562), -0.000058 (tennis, n 14,873); 0 of 8 arms clear +0.004, and the
   inner CV drove EVERY coefficient to zero in 20 of 23 outer folds.
3. The residual is freshness/information (resolution), not miscalibration, on totals and ATP
   (MARKET_EFFICIENCY_PROOF lines 141-142).

**Ranked pregame levers (leak-free OOS calibration: reliability bins + ECE + Brier + log-loss,
walk-forward, >= 2 corpora, n >= 30 clusters, truncation-invariant).**
1. Score the forecaster AND the close on IDENTICAL rows with reliability bins, ECE, Brier and
   log-loss. This has never been done: S05 states "No sport is compared to a market close -- no gate
   corpus carries one", yet soccer (16,322), tennis (33,685) and partial nba/mlb close columns are on
   disk today. -> **S204**.
2. Change the CALIBRATOR, not the features. Three of four sports lose resolution to isotonic; a
   controlled isotonic / temperature / beta bakeoff under the sealed rule is the only untried way to
   flip FLATTENED to IMPROVES (items 3, 2 and 1 of the methods note). -> **S205**.
3. Land the honest key (S200) and switch the per-unit walk (S50) before quoting any pregame number.

**Not possible on disk (blockers named).**
- WNBA pregame: no `gate_corpus_wnba.parquet` and no wnba entry in the gate loader -- nothing to score.
- MLB 2022-2025 close: S10 CLOSED AT LIMIT (modern join 8.17 pct, 913/11,179; per-season 2022-2025
  all 0.00 pct); S52 CLOSED on licence -- no free 2022-2025 MLB moneyline close is acquirable.
- NBA close coverage: measured 2026-09-04, 563 of 1,814 rows carry `p_close`, and 343 of those are
  `first_inplay_tick` (not a pregame close) against 220 `pregame_last_tick_before_commence`.
- Tennis close vintage is SYNTHETIC (`state_ts` constructed as `<game_date>T12:00:00`, S03), and WTA
  is a disjoint key space from ATP (soccer_tennis_corpus_wiring_blockers memo).

---

## 2. IN-GAME -- current honest state per sport

| sport | tick corpus | model vs market (in-play) | source |
|---|---|---|---|
| nba | 465,249 ticks / 1,593 games (S86) | halftime as-of: model 0.171360 vs market 0.164777, -0.006583, CI [-0.011503, -0.001664], BEHIND, 0 of 2 units | S58 trial B |
| mlb | 78,986 rows / 227 files; scored 47,104 / 158 games | screen side market 0.195704 vs null 0.201671 vs e4 0.208211; 0 of 14 features clear +0.004 | S82 |
| soccer | 9,003 ticks / 51 games; usable 29 games / 3,658 ticks | market 0.157753 vs best candidate 0.258641; scored 163 ticks / 2 clusters | S117 |
| tennis | tennis_states__atp 40,516 rows; ingame_grade/tennis 1,255 rows, 0 settled, 18 priced | NO in-play close on disk | S82 section 0; INGAME_SIGNAL_PROGRAM rank 8 |
| wnba | 186,736 in-play moneyline ticks / 85 games; 18,650 state-joined | NEVER SCORED (before = 0) | wnba_ingame_census 2026-09-04 |

Published static -> conditional pairs (the project's flagship model-quality numbers): NBA Brier
0.209 -> 0.159, MLB 0.241 -> 0.126 (docs/evidence/ingame-conditioning.md), with ~73 pct of the NBA
lift and ~99 pct of the MLB lift attributed to the realized score alone and the model prior worth
~0.014 (NBA) / ~0.001 (MLB). SIGNAL_INVENTORY_REDTEAM line 199 records that both pairs were READ
from that page, not re-run.

**Where the in-game gap lives (the one decomposition on record, calibration-decomposition.md):**
mlb n 78,986 model 0.237684 vs market 0.206653, gap +0.0310 = reliability +0.0066 and resolution
-0.0235; soccer_intl n 9,003 model 0.227887 vs market 0.142726, gap +0.0852 = reliability +0.0394,
resolution -0.0446. n-weighted ECE mlb model 0.079 vs market 0.0591; soccer_intl 0.3609 vs 0.2511.
NBA and WNBA have never been decomposed at all.

**Named causes.**
1. NBA: the in-play line is a near-martingale with a slow mid. Every arm conditioning ON the line is
   NULL -- S94 early shrinkage NEGATIVE (market ECE P1|close 0.055593, P2|close 0.064157), S96 no
   overshoot (slopes positive in 31 of 33 cells), S97 Kalman +0.000003 with 90 pct coverage 0.08,
   S98 the prior is not the crude half, S101 conformal coverage 0.936-0.980, S102 576-hypothesis
   sweep SCREEN_NULL, S103 wide sigma grid worth +0.000261.
2. The model's defect is premature confidence on the eventual loser: model > 0.8 on the loser in
   11.4 pct of lost NBA games vs the market's 5.6 pct (S58 trial B); the same tail defect on MLB
   (S43). JP's max-loser-WP diagnostic is degenerate on the pregame corpora (S43: one row per
   event_id) and has never been run on a tick stream, which is its correct input.
3. MLB: power, not features. Every in-game CI half-width is near 0.005 against a +0.004 bar
   (S93 CLOSED AT LIMIT), and the corpus is 74.97 pct held market / 91.71 pct held model ticks
   (S87), 144 of 227 files spanning over 6 h with several real games merged (S106/S107).

**Ranked in-game levers.**
1. Per-phase recalibration is the ONE in-game method that has produced a CI excluding zero: S88 on
   MLB gives late|leading_big +0.031643 [0.0088, 0.0572] IMPROVED and mid|trailing -0.011964
   [-0.0232, -0.0010] WORSE, pooled -0.002890 [-0.0114, 0.0052] NO_CHANGE, over 15 buckets with NO
   multiple-comparison correction, single window. NBA was excluded for want of a leak-free incumbent
   -- S123 has since landed `foundry/ingame_incumbent_nba.py`, so the method can now run on the
   1,593-game corpus, the most powerful in-game denominator in the repo. -> **S208** (nba),
   **S209** (mlb: BH across the 15 buckets + a second unit).
2. Score WNBA at all: 18,650 state-joined ticks over 85 game clusters, state age median 15 s, p90
   132 s, 0 above 300 s, 84 of 85 games with at least 100 in-span ticks. Largest unscored
   denominator on disk. -> **S206**.
3. Decompose the gap per sport at tick grain before proposing another feature: reliability tells you
   recalibration can pay, resolution tells you nothing on disk will. -> **S207**.
4. Re-label the NULL pile honestly: at these cluster counts most standing in-game NULLs are
   UNDERPOWERED, not refuted, and the program should stop spending lanes on them. -> **S210**.
5. Re-derive the two flagship pairs with archived per-game differentials (Q9). -> **S211**.

**Not possible on disk (blockers named).**
- Tennis in-game market-relative verdict: no in-play close exists (0 priced settled ticks).
- Soccer in-game: CLOSED AT LIMIT on corpus size (S117) -- 2 scored game clusters after the tier's
  own MIN_TRAIN floor.
- MLB pitch-grain members (`pitch_velocity`, `pitch_loc_x/y`, `velo_decline_vs_early`,
  `atbat_pitch_number`): no pitch-grain feed is joined to the tick store (S119).
- 89.6 pct of WNBA in-play ticks fall outside their play-by-play wallclock span and cannot be given
  state (S199, OPEN, censuses the ceiling).

---

## 3. Proposed rows, ranked across sports by expected calibration effect per unit of work

| rank | id | sport / phase | slug | why here |
|---|---|---|---|---|
| 1 | S200 (queued) | all / pregame | regime_key_oof | every published four-sport ECE rests on a key fitted on the scored row; cheapest possible retraction-or-confirmation of the whole pregame table |
| 2 | S204 | all / pregame | close_reference_calibration | the target metric has never been computed: model AND close on identical rows with bins, ECE, Brier, log-loss. All inputs on disk; modules exist |
| 3 | S208 | nba / in-game | nba_phase_recal | the only in-game method with a proven CI excluding zero, run for the first time on the 1,593-cluster corpus; ~40x the game clusters MLB has |
| 4 | S199 (running) | wnba / in-game | wnba_state_ceiling | bounds the WNBA denominator S206 then scores |
| 5 | S206 | wnba / in-game | wnba_ingame_first_score | first calibration number for a whole sport; 85 clusters clears every n rail |
| 6 | S205 | all / pregame | calib_bakeoff | isotonic vs temperature vs beta under the sealed rule: the only untried way to flip a published FLATTENED to IMPROVES |
| 7 | S207 | all / in-game | ingame_gap_decomposition | tells every later in-game lane whether model work can pay at all; nba and wnba have never been decomposed |
| 8 | S202 (queued) | all / harness | two_way_neff | every clustered CI above is a lower-bound correction until this lands |
| 9 | S201 (queued) | nba / in-game | nba_fatigue_conditioned | one more conditioned form on a surface already exhaustively NULL |
| 10 | S209 | mlb / in-game | mlb_phase_recal_fwer | corrects and replicates the one measured in-game positive |
| 11 | S210 | all / in-game | ingame_power_audit | stops the program spending lanes on questions the corpora cannot answer |
| 12 | S211 | all / in-game | ingame_headline_rederive | the flagship pairs are quoted everywhere and were never re-run |
| 13 | S203 (queued) | all / harness | replication_wiring | labelling hygiene; no metric moves |

Why the top three come first: S200 decides whether the published pregame table is honest at all, and
it is a few hours of work on code that already exists. S204 is the first measurement of the quantity
the whole program optimises -- the calibration gap to the best available predictor -- and every input
is already joined. S208 takes the single method that has ever produced an in-game effect with a CI
excluding zero and runs it where the statistical power actually exists; MLB's 41-88 game clusters can
never resolve a +0.004 bar (S93), NBA's 1,593 can.

---

## 4. NOT VERIFIED

- No number in this memo was re-run by me; every one is a read of a committed artifact or register
  row, plus two counts I measured today from parquet metadata (nba p_close 563/1,814 with 343
  `first_inplay_tick` + 220 `pregame_last_tick_before_commence`; mlb p_close 910/39,162). Those two
  are the only fresh measurements here, and they disagree in denominator with S112's scored n of
  351 / 276, which I did not reconcile.
- The S05 after-ECEs are provisional pending S200 (regime key) and are positional-order pending the
  S50 switch; both corrections are measured but neither is the published default.
- The four-sport public scoreboard (MARKET_EFFICIENCY_PROOF) and the gate-corpus calibration report
  are DIFFERENT models on DIFFERENT row sets; their numbers are not interchangeable and no row here
  treats them as such.
- The static -> conditional pairs (0.209 -> 0.159, 0.241 -> 0.126) and the ~73 pct / ~99 pct
  mechanical attribution are read from the page, never re-derived (SIGNAL_INVENTORY_REDTEAM line 199).
- WNBA's absence from the pregame gate loader was inferred from the `data/cache/combo` listing, not
  from reading the loader source.
- Rank order in section 3 is my judgement of effect-per-work, not a measurement.
