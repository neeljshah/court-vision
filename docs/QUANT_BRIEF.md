# CourtVision for a trading desk -- the one-page brief

**Neel Shah** -- [resume (PDF)](assets/NeelShahResume.pdf) -- [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com) -- [GitHub](https://github.com/neeljshah/court-vision) -- [LinkedIn](https://linkedin.com/in/neeljshah22) -- [live analytics site](https://neeljshah.github.io/court-vision/analytics/)

CourtVision is a calibrated pricing engine for NBA, MLB, soccer and tennis, built with walk-forward
validation and paper-only execution controls. This page says, in desk terms, where the engine
prices within noise of the market, where it trails, and what has not been measured. Every number is
transcribed from [EVIDENCE.md](../EVIDENCE.md), [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md),
[MARKET_EFFICIENCY_PROOF.md](MARKET_EFFICIENCY_PROOF.md), [GO_LIVE_GATES.md](GO_LIVE_GATES.md) or a memo
linked beside the number. Nothing here is a betting-edge, ROI or dollar claim, and the CI fails a build on edge
language or a retracted figure outside retraction framing.

## 1. Pricing quality against the market

**Pregame, leak-free walk-forward, scored against the devigged close on the same outcomes**
(source: [MARKET_EFFICIENCY_PROOF.md](MARKET_EFFICIENCY_PROOF.md) for the rows; the game-clustered
intervals, Diebold-Mariano p-values and verdicts for the three win-market rows are from the
[2026-09-24 recompute memo](evidence/pregame/DM_RECOMPUTE_2026-09-24.md), which reproduces each row to four decimals from the harness's own
functions before attaching the interval; the NBA close is Shin-devigged there, 0.1666, where the proof
page prints the proportional-devig close, 0.1672, on the same 372 scored games):

| Sport | Market | Metric | N | Model | Close | Gap | Standing |
|---|---|---|---|---|---|---|---|
| NBA | moneyline | Brier | 372 | 0.1735 | 0.1666 | +0.0069, 95% CI [-0.0038, +0.0175], DM p 0.20 | MATCHES_CLOSE (CI includes 0; underpowered: MDE 0.0152) |
| NBA | total O/U | RMSE | 372 | 19.17 | 18.11 | +1.06 | BEHIND (freshness) |
| MLB | moneyline | Brier | 13,992 | 0.2429 | 0.2390 | +0.0039, 95% CI [+0.0028, +0.0051], DM p 3.6e-12 | TRAILS_CLOSE (small, measurable) |
| MLB | total O/U | RMSE | 1,679 | 4.72 | 4.44 | +0.28 | BEHIND (freshness) |
| Soccer | O/U 2.5 | Brier | 7,558 | 0.2465 | 0.2390 | +0.0076, 95% CI [+0.0059, +0.0092], DM p 1.1e-19 | TRAILS_CLOSE (small, measurable) |
| Tennis (ATP) | match-win | Brier | 7,374 | 0.2177 | 0.2028 | +0.0149 | BEHIND (freshness) |

Reading: the model trails the sharp close by small margins everywhere and beats it nowhere. On NBA
moneyline the gap is not distinguishable from zero, but the row is underpowered (a deficit the size
of the MLB one could not be detected at n=372). On MLB moneyline and soccer O/U 2.5 the close is
measurably sharper: the gaps are 1.6 percent and 3.2 percent of the close's Brier, with intervals
that exclude zero (the proof page's MATCH label there was a fixed-threshold rule, not an interval;
the recompute memo records this). On totals and ATP it trails by more, by the freshness the close
has (injuries, lineups, starters, weather) and a public box-score model does not. Every candidate signal (rest, back-to-back, travel, altitude, form,
head-to-head, MLB open-to-close CLV capture) was scored with a game-clustered Diebold-Mariano test
and REJECTED (the MLB CLV-capture reject is on a confidence interval, not DM). On the NBA schedule signals (scored on the two calendar halves of the 2026 season),
positive full-sample lifts reversed sign across halves; the MLB, soccer and tennis candidates
failed on both of their corpora or on the null-shuffle / Benjamini-Hochberg test
([the reject table](MARKET_EFFICIENCY_PROOF.md), [the multiplicity memo](evidence/MULTIPLICITY_MEMO_2026-09-22.md)).

**In-game, against the live market reference on paired ticks** (source: [EVIDENCE.md](../EVIDENCE.md) sections B and C):

| Checkpoint | Model vs market | Verdict |
|---|---|---|
| NBA end of Q1, win probability | Brier 0.2006 vs 0.1922, delta -0.0084 [-0.0161, -0.0008], n=1,592 | MARKET_SHARPER_PROVISIONAL |
| NBA halftime / end Q3 / Q4 under 5:00 | deltas -0.0040 / +0.0011 / +0.0019, all CIs include 0, n=1,593 | UNDERPOWERED |
| MLB total runs, end of innings 6 / 7 / 8, CRPS | deltas 0.6392 / 0.7327 / 1.4201, CIs exclude 0, n=49-55 | MODEL_SHARPER_PROVISIONAL (a small-sample retrospective diagnostic, transcribed from EVIDENCE.md; not treated here as evidence of market outperformance) |
| Soccer home-win probability, minute 60 / 75 | Brier deltas -0.0931 / -0.1075 (market closer), n=22 / 17 | UNDERPOWERED |
| Kalshi in-play paired ticks (Gate A-0), MLB win probability | Brier 0.2377 vs 0.2067, delta +0.0310 [0.0170, 0.0454], 227 games | BEHIND (measured on a corpus that later failed the join-integrity check; the per-game segmented revision, 178 games, keeps the verdict) |
| Kalshi in-play paired ticks (Gate A-0), soccer | Brier 0.2279 vs 0.1427, 51 games | BEHIND (same corpus caveat: the soccer corpus also failed the join-integrity check, 27 of 51 files kept after segmentation) |
| Against a STATIC pregame prior (not the market) | NBA Brier 0.209 to 0.159; MLB 0.241 to 0.126 | sharper than a static prior; not a market comparison |

Sign convention follows each source artifact: in the NBA, MLB and soccer rows a negative delta
means the market is closer; in the Gate A-0 rows a positive delta means the market is closer.

**Player props, NBA, production model, chronological holdout of 20,354 player-games:** MAE PTS 4.83,
REB 1.92, AST 1.39, FG3M 0.89. Accuracy only; no market comparison exists for these.

## 2. What exists, and what it is evidence of

- **An independent reference line from public box-score and schedule data:** gaps of +0.0069,
  +0.0039 and +0.0076 Brier to the devigged close on NBA moneyline, MLB moneyline and soccer O/U 2.5
  respectively; the NBA gap is indistinguishable from zero at n=372, the MLB and soccer intervals
  exclude zero, and totals and ATP trail by more
  ([recompute memo](evidence/pregame/DM_RECOMPUTE_2026-09-24.md), [MARKET_EFFICIENCY_PROOF.md](MARKET_EFFICIENCY_PROOF.md)).
- **In-game win-probability and MLB total-runs models,** sharper than a static pregame prior;
  where a live market exists it is sharper than they are ([EVIDENCE.md sections B and C](../EVIDENCE.md)).
- **Devig:** four methods implemented from scratch, including the Shin (1992) model through a
  stable bisection solver, wired into the private engine's API (source not in this repository;
  [JOB_EVIDENCE_PACKET section 2C](JOB_EVIDENCE_PACKET.md)).
- **Validation instruments a desk would recognize** ([eval_gate/](../scripts/platformkit/eval_gate/) is public): walk-forward with a per-fold date assertion,
  a truncation-invariance leak test on streaming features, acceptance only when a change beats
  baseline on at least two independent corpora, game-clustered Diebold-Mariano, Benjamini-Hochberg
  FDR, a post-hoc minimum detectable effect published for every market-relative row
  ([power page](evidence/POWER_PAGE_2026-09-22.md)), thresholds pre-registered with their
  registration date in code ([thresholds.py](../scripts/platformkit/execution/thresholds.py)).
- **Execution controls, paper only, published as readable source (not runnable from this
  repository):** a full order lifecycle whose live path is unreachable behind three independent
  refusals, a venue fee model that fails closed, a circuit breaker gated on the median, a CLV ledger that filters off-market prices without
  mutating the record and whose writer is proven race-safe across two OS processes
  ([EVIDENCE.md section G](../EVIDENCE.md)); the API kill switch that fails closed is in the
  private engine, status in [GO_LIVE_GATES.md](GO_LIVE_GATES.md) G4.
- **An honesty CI:** the build fails when a retracted figure appears outside retraction framing
  ([HONESTY_SYSTEM.md](HONESTY_SYSTEM.md)).

## 3. What is not shown -- read before the call

- **No edge against the close pregame, and no established edge against the live market in-play.**
  The one MODEL_SHARPER_PROVISIONAL row (MLB total runs, n=49-55) is a small-sample retrospective
  diagnostic recorded in EVIDENCE.md; it is not treated here as evidence of market outperformance. No dollar,
  ROI or return figure is claimed; retracted figures appear only inside retraction framing. Six
  earlier headline figures were retracted after the project's own instruments traced each one to
  a leak, a grading artifact, an overfit or regime dependence
  ([the retraction record](evidence/retraction-story.md)).
- **Forward record: zero weeks.** Six go-live gates were pre-registered on 2026-09-17
  ([GO_LIVE_GATES.md](GO_LIVE_GATES.md)). Gate G6 requires at least eight consecutive weeks of
  shadow maker quoting, fee-netted markout positive with a game-clustered 95 percent interval
  excluding zero, on at least two independent market families, with a pre-registered single-game and single-week
  concentration check and a calendar-half sign-flip reject. It has not started. The fee-aware paper sizing policy returns
  zero because every cell is refused (the in-game result is underpowered, the second corpus is
  unsealed); it has no caller ([S400 memo](evidence/harness/S400_paper_sizing_2026-09-22.md)).
- **No live order path exists.** No real order has ever been placed.

## 4. What runs next, with dates

- In-game capture (Kalshi order books plus game state) is scheduled under prospective, committed
  schedule files; the earliest records its selection at 2026-09-22T03:03Z
  ([schedules](evidence/forward/schedules/)).
- The NBA in-game preregistration is a draft, not yet sealed; the seal waits on named amendments
  ([S382 draft r1](evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md)).
- The forward maker paper series has not started. When it does, the G6 verdict is published on
  schedule whether or not the gate is met; the pre-registered expected year-end outcome is
  "G6 not met, N weeks collected" ([GO_LIVE_GATES.md](GO_LIVE_GATES.md)).

## 5. How to read the rest

[EVIDENCE.md](../EVIDENCE.md) is the claim-to-artifact index. [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)
is the adversarially audited narrative with the do-not-claim list. [RECEIPTS.md](../RECEIPTS.md) holds
every generated number verbatim, and [REPRODUCE.md](../REPRODUCE.md) lists the commands that re-check
them on a fresh clone.

---
**Navigate:** [README](../README.md) - [Evidence index](../EVIDENCE.md) - [Job Evidence Packet](JOB_EVIDENCE_PACKET.md) - [Doc map](INDEX.md)
