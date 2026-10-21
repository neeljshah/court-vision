# On a fresh book the mid is the model: in-game state models against the live venue price

Neel Shah, CourtVision. Calibration readout; paper only. Drafted 2026-10-20 from committed artifacts
dated 2026-09-03 .. 2026-10-16. No new computation: every number below is copied from the file named
beside it; the only arithmetic done for this page is two ratios of published Brier scores (marked).

**Summary.** On identical in-play ticks, is an in-game win-probability model closer to the
outcome than the contemporaneous Kalshi mid? Gate A-0 scored the per-tick paired Brier gap, model
minus mid, with a game-clustered bootstrap 95% interval, on Kalshi MLB (227 games) and international
soccer (51 games) captured 2026-06-20 to 2026-07-12. Both read BEHIND: each interval excludes zero
on the market's side. Both corpora later failed a join-integrity check; after the S541 hygiene
re-derivation MLB still reads BEHIND (+0.01696 [0.00834, 0.02542], 177 games), and soccer was not
re-established. Six probe families found nothing closer than a fresh mid. One sealed replay held,
status: accept (staleness backstop only): closer than our stale copy of the book, never ahead
of a fresh price.

## 1. The question and why it is hard

On identical in-play ticks, is the model or the venue mid closer to the outcome (Brier, log loss,
game-clustered interval)? The reason to expect "no" is structural. The venue mid already conditions on the realized state: the
people quoting it watch the same scoreboard, plausibly sooner; P1 indicates most of the move is in the book before our receipt, at INSUFFICIENT n. Most of what an
in-game model gains over a pregame prior is that scoreboard. The project's own three-arm
decomposition ([`docs/INGAME_PROOF.md`](../INGAME_PROOF.md) section 2a) shows this:

| Sport | Static prior Brier | Score-only (rating-blind) | Prior + state | Mechanical share of the gain |
|---|---|---|---|---|
| NBA | 0.209 | 0.172 | 0.159 | -0.037 of -0.050 (~73%) |
| MLB | 0.241 | 0.128 | 0.126 | -0.113 of -0.115 (~99%) |

These are improvements against a STATIC pregame prior, labelled calibration, not a market comparison.
Anyone watching the game, a live book included, gets the mechanical share for free. So the bar for an
in-game model is not the prior; it is the live price on the same tick.

## 2. Data and corpora

| Corpus | Venue | Sport | Window | Games | Ticks | Source |
|---|---|---|---|---|---|---|
| mlb_clean (Gate A-0) | Kalshi | MLB | 2026-06-20..2026-07-12 | 227 | 78,986 | [`gate_a0_summary.md`](../evidence/ingame/gate_a0_summary.md) |
| soccer_intl (Gate A-0) | Kalshi | international soccer | 2026-06-22..2026-07-12 | 51 | 9,003 | same; measured before the join-integrity repair; not re-established after it (section 2) |
| mlb_clean after S541 hygiene | Kalshi | MLB | same | 177 | 30,940 | [`S541 memo`](../evidence/harness/S541_gate_a0_rederive_2026-09-29.md) |
| nba_checkpoints_r1 (P5, S542) | Polymarket | NBA | 2024-25 and 2025-26 | 656 + 937 | 465,249 rows | [`S542 replay`](../evidence/harness/S542_anchor_projection_replay_2026-09-29.md) |
| capture_view_v2, Sept (P1-P4, S542 MLB) | Kalshi | MLB | 2026-09-22..09-29 | 15-47 per probe | per probe | [`INGAME_MODEL_2_PLAN`](../evidence/harness/INGAME_MODEL_2_PLAN_2026-09-29.md) section 2 |

**Join integrity.** Both Gate A-0 corpora later failed the project's own join-integrity check. Two
independent repairs keep the MLB verdict: the site's per-game segmentation (2026-09-16; 178 of 227 MLB
files, 27,351 ticks; 27 of 51 soccer files; rebuilt MLB Brier skill score against the reference quote
-0.1043, before -0.1502, [`mlb-ingame-regeneration.json`](../../webapp/public/data/audits/mlb-ingame-regeneration.json))
and the S541 clock-and-state hygiene filter (177 games, section 3.2). Neither is a new trial.

## 3. The finding

### 3.1 Gate A-0: model versus the contemporaneous Kalshi price

Design: per-tick paired Brier and log loss (model minus market) on identical ticks; game-clustered
bootstrap, 2,000 resamples, seed 13; a cell is BEHIND when the interval excludes 0 with the market
favoured, UNDERPOWERED when n_games < 30 or the interval contains 0
([`GATE_A0_2026-09-14.md`](../evidence/ingame/GATE_A0_2026-09-14.md), as of 2026-09-14).

| Sport | Ticks | Games | Model Brier | Market Brier | Delta (model - market) | 95% CI | Log-loss delta | Verdict |
|---|---|---|---|---|---|---|---|---|
| MLB | 78,986 | 227 | 0.23768 | 0.20665 | +0.03103 | [0.01704, 0.04535] | +0.10624 | BEHIND |
| Soccer (intl) | 9,003 | 51 | 0.22789 | 0.14273 | +0.08516 | [0.04876, 0.12696] | +0.40488 | BEHIND |

Source: [`gate_a0_summary.md`](../evidence/ingame/gate_a0_summary.md). Rounded to four decimals these
are the canonical rows `mlb_ingame_vs_kalshi_mid` and `soccer_ingame_vs_kalshi_mid` in
[`CANONICAL_FIGURES.json`](../evidence/CANONICAL_FIGURES.json). No cell in either corpus has the model ahead of the market (interval excluding zero on the model's side). By
phase the MLB gap widens late (innings 1-3 +0.01812, 4-6 +0.02874, 7-9+ +0.07411, all BEHIND). The
model changes on 8.3 pct of MLB ticks (only at parsed state transitions); the market changes on 25.0
pct (GATE_A0 verdict section).

### 3.2 S541: the same comparison after corpus hygiene

The Model 2.0 probes found that mlb_clean carried prior-game ticks before first pitch: 21,064 ticks in
115 of 177 games carried the previous day's state (plan section 2, P4 row). S541 re-derived Gate A-0
with a sealed hygiene rule and published the result beside the original
([`S541 memo`](../evidence/harness/S541_gate_a0_rederive_2026-09-29.md), as of 2026-09-29):

| Run | Ticks | Games | Model Brier | Market Brier | Delta | 95% CI | Verdict |
|---|---|---|---|---|---|---|---|
| MLB original | 78,986 | 227 | 0.23768 | 0.20665 | +0.03103 | [0.01704, 0.04535] | BEHIND |
| MLB cleaned | 30,940 | 177 | 0.16912 | 0.15216 | +0.01696 | [0.00834, 0.02542] | BEHIND |
| Soccer cleaned | 1,704 | 11 | 0.06538 | 0.12651 | -0.06113 | [-0.11039, -0.01152] | UNDERPOWERED, not quotable |

Why the MLB figure changed: the clock window dropped 33,332 pre-start rows and 14,695 empty-state rows
were removed (S541 exclusion census); 50 games kept no rows. Many of the removed rows carried the
previous game's state before first pitch (plan section 2, P4 row). Removing them shrinks the gap from
about 15.0 pct to about 11.1 pct of the market's Brier (ratios computed for this page:
0.03103 / 0.20665 and 0.01696 / 0.15216), and the interval still excludes zero. The cleaned MLB figure
is the one to quote; the original stays published beside it (superseded by adding, never deleted).

The soccer cleaned row is not a reversal. Only 11 games carry a usable regulation label, all 11 label
0 (no home win), and the cell is below the 30-game floor by construction; S541 states that no soccer
number from it may be quoted elsewhere. The soccer_intl outcome field was not a binary home-win label
(draws 0.5, knockout advances 1.0; plan section 1).

S541 also relabels the Gate A-0 "minutes_to_close" split: close_ts is the last captured tick in 227
of 227 games, so that split is minutes to CAPTURE end, not to the end of the game (plan AMENDMENT 1,
A8). The MLB "last 10 minutes" cells cannot be read as late-game cells.

## 4. Six Model 2.0 probe families (S540), each recorded as a result

The Model 2.0 plan ([`INGAME_MODEL_2_PLAN_2026-09-29.md`](../evidence/harness/INGAME_MODEL_2_PLAN_2026-09-29.md),
section 2 table and AMENDMENT 1) ran six probe families under binding rails
([`PROBE_RAILS.md`](../evidence/harness/ingame_model_2_probes/PROBE_RAILS.md)): anything fitted is
walk-forward by date, as-of joins only, game-clustered bootstrap (2,000, seed 13), delta = loss
(candidate) - loss(comparator) with negative = candidate better, and any cell under 30 games is
INSUFFICIENT with no verdict. Under those rails one decision rule applies to every family: a
candidate survives only if its paired interval against the mid excludes zero on the candidate's side
on at least 30 games. Scripts, stdout copies and JSON outputs are in
[`ingame_model_2_probes/`](../evidence/harness/ingame_model_2_probes/).

**P1, state-event response (MLB Kalshi, Sept).** Does the book still move after OUR feed reports a
score or an out? Our feed reaches us p50 17.9 s / p90 31.1 s after the play. On fresh books only
(K_FRESH15, max receipt gap <= 15 s; 197 events / 15 games) the move after our receipt is
post_120 -0.023 pp [-0.557, +0.399]; most of the move is already in the book before our receipt
(pre +1.145 pp [+0.586, +1.662]). Kill: under 30 games, interval contains 0, so no post-receipt
window is measurable: INSUFFICIENT. The SCORE-only subset points the other way (+0.968 [+0.017,
+1.618], 12 games; AMENDMENT 1, A8), so "already repriced" is an indication, not a measurement. Files: `probe_p1_event_response.py`, `probe_p1_out.json`.

**P2, price source (MLB Kalshi focus snapshots, 2,020 ticks / 15 games).** Is a better summary of the
book available than the raw mid? Brier deltas versus MID: microprice +0.00002 [-0.00065, +0.00037],
last trade -0.00105 [-0.00267, +0.00165], one-receipt lag +0.00022 [-0.00000, +0.00067], two-ticker
pair +0.00026 [-0.00006, +0.00051]. Kill: every interval contains 0 and n < 30: INSUFFICIENT; keep the
raw mid. Spread p50 = p90 = 0.010. Files: `probe_p2_price_source.py`, `probe_p2_out.json`.

**P3, mid recalibration (MLB, June-July corpus J and Sept corpus K).** Is the mid miscalibrated in a
way a walk-forward recalibration fixes out of time? J ECE 0.0591. Walk-forward Platt with a late-phase
term on J: +0.00582 [-0.00337, +0.01559] (196 games); fit on J, scored on K, Platt: +0.02098 (15
games). Kill: every point estimate worse than the raw mid and every interval contains 0: REJECT. The
late underdog tail on J is priced above realized (inning >= 8, mid < 0.10: priced 0.0445, realized
0.0084, 70 games); see section 4.1 for what became of it. Files: `probe_p3_mid_calibration.py`,
`probe_p3_out.json`.

**P4, win-expectancy and stale-delta features (MLB J cleaned, walk-forward, 124 games / 11,748
ticks).** Does a well-shaped state feature add to the mid? Versus the mid-only logistic (arm B):
mid + logit WE +0.00052 [-0.00040, +0.00145]; mid + STALE_DELTA +0.00001 [-0.00006, +0.00008]; the
landed raw-state arm C +0.00162 [-0.00083, +0.00434]; fitted coefficient on logit WE 0.0404. Kill:
no interval excludes zero on the candidate's side: REJECT as a residual feature; the formula is well
scaled on its own (WE-only slope 1.2429) but redundant given the mid. The cross-corpus form (fit J,
score K, 32 games) has intervals containing 0. P4 also found the mlb_clean defect that S541 fixed.
Files: `probe_p4_we_feature.py`, `probe_p4_we_feature_out.json`.

**P5, market-anchored state projection (NBA Polymarket, 1,593 games, two seasons).** Keep the
market's implied strength at the last traded tick and move it through the state change (PROJ). As
first scored: against the previous tick carried forward, -0.00177 [-0.00263, -0.00100] (closer);
against the fresh price on state-changed ticks, +0.00073 [+0.00021, +0.00115] (trails). Kill against
a fresh price: the interval excludes zero on the market's side: REJECT as a fresh-book model; retained
only as a staleness-backstop candidate, which S542 then tested under a sealed rule (section 5). Two
P5 readings were retracted: see 4.1. Files: `probe_p5_nba_projection.py`, `probe_p5_out.json`.

**P6, after-goal response (soccer_intl, 29 usable of 51 games).** Does the soccer price lag goals?
Tick gap p50 29 s; 47 goals in 24 games; the signed price change at the first tick showing the goal
is +0.1248 [+0.0910, +0.1622], and the median share of the total move already present at that tick is
0.890. Kill: under 30 games: INSUFFICIENT; repricing is done within one tick at this cadence, so no
lag is visible to model. 12 of 29 labels disagreed with the final score (fed into S541). Files:
`probe_p6_soccer_goal_response.py`, `probe_p6_out.json`.

### 4.1 A worked retraction: the NBA late tail

The first plan draft reported one structured miscalibration: late in the game the mid looked less
extreme than the state implied, and a shrink model looked closer to the outcome than the fresh price
on NBA 2025-26. Both readings were retracted the same night by the project's adversarial critique
tier ([`critique_opus_r1.md`](../evidence/harness/ingame_model_2_probes/critique/critique_opus_r1.md);
plan AMENDMENT 1, A1). P5 had not applied the S148 live rule (live when period < 4 or game clock > 0;
[`S148_live_requote_2026-09-03.md`](../evidence/harness/S148_live_requote_2026-09-03.md)), and
244,183 of the 465,249 r1 rows are post-final-buzzer dead ticks. On live ticks only, 2025-26: clipped
anchors PROJ - FRESH -0.00270 [-0.01057, +0.00377]; all live ticks SHRINK - FRESH -0.00047
[-0.00126, +0.00032] (critic) and -0.00045 [-0.00132, +0.00031] (S542 before-probe). Both intervals
contain zero. The late-tail candidate was withdrawn; on MLB it rests on one corpus with no game-end
filter possible (S541), and the Gate A-0 "last 10 minutes" cell it once cited is capture end
(section 3.2). The lesson the project kept: no residual on a fresh mid is proposed without the live
rule and a delayed-state replay.

## 5. The staleness backstop (S542): when the mid is NOT fresh

A3 of AMENDMENT 1 fixed a double count: a fresh book can reprice before our feed reports the play, so
the projection is EVENT-AWARE. If the mid has changed at or after the play time of the latest known
state change, the output is the mid itself; only when the mid has not moved since the play is the
state change projected. S542 then ran a live-like replay with the state delayed by L seconds, under a
prereg sealed before the first metric
([`S542_prereg.json`](../evidence/harness/S542_prereg.json), seal `95e9cfa5...dbec29`).

Pre-specified verdict rule (verbatim in substance from the prereg): fewer than 30 population games per
season -> INSUFFICIENT; if the share of projected ticks whose state differs at L = 18 is below 0.20
in either season, or the canary interval's upper bound is not below 0 in both -> status: inactive (replay status: the delayed-state replay did not exercise the projection enough to judge it); else if in
BOTH seasons the PROJ - STALE interval at L = 18 and the real-versus-placebo interval both have upper
bound < 0 -> status: accept (staleness backstop only); otherwise REJECT.

Result ([`S542_anchor_projection_replay_2026-09-29.md`](../evidence/harness/S542_anchor_projection_replay_2026-09-29.md)
and its `.json`, as of 2026-09-29): status: accept (staleness backstop only).

| Cell (NBA, L = 18 s, projected ticks) | Games | Ticks | PROJ - STALE | PROJ - FRESH | Placebo contrast |
|---|---|---|---|---|---|
| 2024-25 | 656 | 55,224 | -0.00157 [-0.00194, -0.00121] | +0.00058 [+0.00025, +0.00089] | -0.00374 [-0.00424, -0.00325] |
| 2025-26 | 937 | 79,891 | -0.00200 [-0.00296, -0.00127] | +0.00006 [-0.00088, +0.00077] | -0.00378 [-0.00421, -0.00337] |

Brier deltas; negative = PROJ closer to the outcome. Cross-fit sigma 22.0 in both seasons (not at a
grid boundary); share of projected ticks with a changed state at L = 18: 0.66984 / 0.66380.

How to read it:

- Against a stale copy of the book the projection is closer to the outcome in both seasons, and a
  real state change does better than a same-cell placebo, so the gain comes from the state change.
- Against a fresh price it is never ahead: +0.00058 (behind) and +0.00006 (interval contains 0).
- The recovered share of the staleness loss decays with delay (plan AMENDMENT 2): 0.73 / 0.97 at
  18 s, 0.52 / 0.81 at 31 s, near 0 at 60 s (2024-25 L = 60: R +0.01750 [-0.01694, +0.05096]).
- MLB, September, against OUR OWN previous receipt (not a venue staleness), 34 games projected:
  -0.00422 [-0.00980, -0.00046]; descriptive only (one window, own receipts).

NBA is single-venue (Polymarket) and its 18 s delay is a scenario; MLB's measured state delay is
p10/p50/p90 11.1 / 18.9 / 34.2 s (2,823 state changes, replay `mlb_lag_distribution`).

**How the desk guards it.** The prospective read-out S544 (prereg
[`PREREG_M2.json`](../evidence/forward/model2/PREREG_M2.json), effective 2026-10-01) uses arm M2 = the
venue mid when OUR receipt age is <= 15 s, the event-aware projection otherwise, scored against the
mid on identical rows. Every cell is labelled "vs our own stale receipt copy of the venue mid"; no
M2 cell is a statement about the venue. As of the 2026-10-16 night, every sport's cell is
INSUFFICIENT (MLB 11 games, by declaration through 2026; NBA at most 9 games per cell, below the 30-game floor)
([`HISTORY.md`](../evidence/forward/model2/m2/HISTORY.md)); no verdict exists yet.

## 6. Implications for pricing

These are design implications from the readouts above, not tested trading rules; no order has been placed.
- **On a fresh book, use the mid.** Nothing tested here is closer to the outcome than a fresh mid
  (sections 3-4); on a fresh book an in-game model should reproduce the mid.
- **The freshness argument.** The only measured value of a state model is when OUR view of the book
  is older than the state: then carrying the market's implied strength through the state change is
  closer to the outcome than the stale copy (section 5). That is robustness of our own read-out,
  not information the venue lacks.
- **Quote protection keys off the venue, not our feed.** Our MLB feed lags the play by about 18-22 s
  at p50 (P1; S542; plan AMENDMENT 2, M4), and on the books we capture, a mid change precedes our state receipt on about half of events (INPLAY_LATENCY_2026.md Table 2; interval contains 0.5). Protection should react
  to mid changes and trade prints (plan section 5).
- **Do not** describe any in-game model as sharper than the live price, quote the static-prior gain
  as a market comparison, or quote the cleaned soccer row.

The MLB total-runs CRPS row labelled MODEL_SHARPER_PROVISIONAL in [`EVIDENCE.md`](../../EVIDENCE.md)
section B (n = 49-55) is, as [`docs/QUANT_BRIEF.md`](../QUANT_BRIEF.md) section 3 says, a small-sample
retrospective diagnostic; it is not treated here as evidence of market outperformance, and it is a
different market (totals CRPS, not win-probability Brier on paired ticks).

## 7. What is not claimed

- No in-game model here is closer to the outcome than a fresh venue price on any resolved cell.
- No return, gain, or money result of any kind; no order has been placed on any venue; forward work
  is paper only.
- The cleaned soccer row (11 games, all one label) is not quotable and is not a reversal.
- The S542 MLB cell and every S544 cell are against our own receipts, not venue staleness.
- Two earlier in-play figures were retracted (a hit rate graded against a soft proxy line; an
  end-of-Q3 Brier with a Q4 feature leak); they are not repeated here
  ([`docs/JOB_EVIDENCE_PACKET.md`](../JOB_EVIDENCE_PACKET.md) section 4).

## 8. Limitations

- **One capture window per Gate A-0 corpus** (2026-06-20..07-12) and one venue (Kalshi). How model_prob was produced is not audited by Gate A-0 or S541 (both memos say so), so whether the Gate A-0 models were trained walk-forward is not established here; only the Model 2.0 probes are walk-forward by date (PROBE_RAILS).
- **The reference is a raw mid, not a de-vigged close.** Each tick is compared with the venue mid on that tick (Kalshi; Polymarket for the NBA replay). No de-vig is applied and it is not "the close" ([`DEVIG_METHODS.md`](../evidence/method/DEVIG_METHODS.md)); P2 found no better summary of the book than the mid.
- **Join integrity.** Both corpora failed the project's join-integrity check after publication (section 2). The segmented revision keeps the MLB verdict (178 of 227 files, 27,351 ticks, Brier skill score -0.1043, before -0.1502) and keeps 27 of 51 soccer files; the soccer BEHIND row was measured before the repair and not re-established after it (11 labelled games after S541).
- **Staleness versus skill.** Our MLB state arrives a nightly median p50 of 18.5 s after the play ([`INPLAY_LATENCY_2026.md`](INPLAY_LATENCY_2026.md) Table 1, ledgers through 2026-10-16), and the venue book often moves inside that window. A model priced from that view is older than the mid, so BEHIND measures freshness as much as model quality; this paper does not separate the two. The S542 gain is likewise against our own stale copy, not a venue weakness.
- **No game-end timestamp on disk** for mlb_clean, so no post-final trim is possible (S541 NOT VERIFIED).
- **NBA backstop evidence is single-venue Polymarket** with unverified price-point semantics and clock alignment; the 18 s delay is a scenario.
- **Multiplicity.** Gate A-0 splits, six probe families and the S542 cells are many comparisons with no correction across them. Only S542 is counted as a finding, and it was tested under a prereg sealed before the first metric, in two seasons; every other family is reported as REJECT or INSUFFICIENT. One survivor among this many tests should be read with that in mind.
- **Most probe cells are INSUFFICIENT** (P1, P2, P6 under 30 games); their reading is "no difference visible at this n", not "no difference".

## 9. What would change the conclusion (stated before any new data)

- A fresh-book candidate whose paired Brier interval against the venue mid excludes zero on the
  candidate's side, on at least 30 games in each of two independent corpora, walk-forward, with the
  S148 live rule applied and a single-game concentration check, under a prereg sealed before scoring.
- For the backstop: an S544 cell reaching its 30-game floor with an interval that does not exclude
  zero (or excludes it on the mid's side) would withdraw the backstop for that sport.
- A live venue showing our feed ahead of the book on a measured share of events would reopen P1.

## 10. Reproduce

The tick corpora are private (`data/`), so the Gate A-0, S541 and S542 tables do not reproduce from a public clone; test counts are as recorded in the memos, not re-run for this page.

| # | Command | Expected | Needs |
|---|---|---|---|
| 1 | `python -m scripts.platformkit.eval_gate.claim_consistency --repo-root . docs/papers/INGAME_VS_MARKET_2026.md` | `claim_consistency: 0 finding(s)` | repo only |
| 2 | `python -m pytest tests/platformkit/ingame/test_gate_a0_rederive.py -q` | `10 passed` (S541 memo) | repo only |
| 3 | `python -m pytest tests/platformkit/ingame/test_s542_replay.py -q` | `16 passed` (S542 memo) | repo only |
| 4 | `python -m scripts.platformkit.ingame.gate_a0_rederive` / `...anchor_projection_replay` | the S541 table / the S542 replay | private corpus |

Source files (sha256 of the committed blob at 4272dee34, via `git show HEAD:<path> | sha256sum`):

```
9eaffe5fe9a4c70165a9e5d3eff8dd5144232c957052ea947fefbdb55a2bd3f3 docs/evidence/ingame/GATE_A0_2026-09-14.md
4c881041f54c8dfbc0fe18774e13249264d48884c60805e0e86e8bac0342117a docs/evidence/ingame/gate_a0_summary.md
6a42a50f544db8e50d95fe84fba78bb8f183d338ef2ca5270ef7cf91d45889c9 docs/evidence/ingame/gate_a0_mlb_clean.json
51f33f47a56681673daaceb160a8f569b31ad870d36c7f0815212386e75c5d8e docs/evidence/ingame/gate_a0_soccer_intl.json
68dd3a74f70e9f83050e67423d3fba4ceeb4b28a5d4d596bd0cb834778ef4fa6 docs/evidence/harness/S541_gate_a0_rederive_2026-09-29.md
6d900a5063fda4f535386c70a2c0701c381aaa810e32009e91cd2dded9f1ce5c docs/evidence/harness/S542_anchor_projection_2026-09-29.md
36ade6ced3c044cf34b2eb18d147b14d3b1f8616374f3afadc18aa36cdd62489 docs/evidence/harness/S542_prereg.json
e7b4366332313011b563512dbe87ddb053f5169d6d563985796d366029cae3a9 docs/evidence/harness/S542_anchor_projection_replay_2026-09-29.json
cb493a52db15dc9d7421461d5c2e26869dd5583ddec0afb40a045cf0345f02f7 docs/evidence/harness/S542_anchor_projection_replay_2026-09-29.md
7fe5b902afbae59053c2be00316ee524d0987342c920fd02113ce62f2e03fbcb docs/evidence/harness/INGAME_MODEL_2_PLAN_2026-09-29.md
527a32999594678dcc20ce095fb7393c289cc08beee82f904b508c31dfd1acef docs/evidence/harness/S148_live_requote_2026-09-03.md
40c8a1b6085a7ff6d649f5ccd539505c25775e92968067d3110fd44a2b8c6b03 docs/evidence/harness/ingame_model_2_probes/critique/critique_opus_r1.md
98a6e44a4de6aee485d9dea5235534df763e878c62cf4643217f284045751975 webapp/public/data/audits/mlb-ingame-regeneration.json
```
