# CourtVision for a trading desk -- the one-page brief

**Neel Shah** -- three years of data-science coursework at the University of Iowa -- [resume (PDF)](assets/NeelShahResume.pdf) -- [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com) -- [GitHub](https://github.com/neeljshah/court-vision) -- [LinkedIn](https://linkedin.com/in/neeljshah22) -- [live analytics site](https://neeljshah.github.io/court-vision/analytics/)

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

| Sport | Market | Metric | Devig method | N | Model | Close | Gap | Standing |
|---|---|---|---|---|---|---|---|---|
| NBA | moneyline | Brier | Shin | 372 | 0.1735 | 0.1666 | +0.0069, 95% CI [-0.0038, +0.0175], DM p 0.20 | MATCHES_CLOSE (CI includes 0; underpowered: MDE 0.0152) |
| NBA | total O/U | RMSE | not recorded | 372 | 19.17 | 18.11 | +1.06 | BEHIND (freshness) |
| MLB | moneyline | Brier | proportional | 13,992 | 0.2429 | 0.2390 | +0.0039, 95% CI [+0.0028, +0.0051], DM p 3.6e-12 | TRAILS_CLOSE (small, measurable) |
| MLB | total O/U | RMSE | not recorded | 1,679 | 4.72 | 4.44 | +0.28 | BEHIND (freshness) |
| Soccer | O/U 2.5 | Brier | proportional | 7,558 | 0.2465 | 0.2390 | +0.0076, 95% CI [+0.0059, +0.0092], DM p 1.1e-19 | TRAILS_CLOSE (small, measurable) |
| Tennis (ATP) | match-win | Brier | not recorded | 7,374 | 0.2177 | 0.2028 | +0.0149 | BEHIND (freshness) |

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
  a truncation-invariance leak test on streaming features, acceptance only when a change improves on the
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

## Forward record update (2026-10-19)

The forward paper series has run daily since 2026-10-06 (the 2026-10-05 version of this page said it had
not started). All numbers come from
[JOB_EVIDENCE_PACKET.md section 5](JOB_EVIDENCE_PACKET.md#5-forward-paper-record-2026-10-06--2026-10-16-as-of-2026-10-19), which carries the receipt paths under
`docs/evidence/forward/`. PAPER ONLY.

- **Served:** 113 Kalshi in-game games on prospective schedules over 2026-10-06 to 2026-10-16 (mlb 15,
  nba 32, nfl 4, soccer 18, tennis 30, ncaaf 14). There was no schedule on 10-11, 10-17 or 10-18:
  the laptop was dark.
- **Nights:** 9 receipts, 2 COMPLETE (10-12, 10-16) and 7 PARTIAL. 10-13 and 10-14 lost their scoreboard
  at the 900 s step deadline, because the sealed scorer's refit grows with the history. The
  deadline was raised to 3,600 s (S824, 10-15); the real fix (S825) is open. Night 10-15 was not run;
  10-16 ran COMPLETE after the 10-19 relaunch (packet section 5).
- **Scoreboard:** every cell is INSUFFICIENT against the 30-game floor. Arm A is the venue mid, not
  a devigged price. The fitted arms scored ticks on two nights only. Pooled C-minus-A Brier for MLB
  (descriptive, no interval; positive means the model trails the mid): +0.2073 on 4 games, -0.0648
  on 3 and +0.0283 on 1, across three seals. That is no verdict in either direction.
- **Qualification:** 0 of 44 judged games passed (through 2026-10-16). Every one failed the coverage and linkage checks. The receipts name no single cause; the contributors in the period were
  tape and state gaps, laptop sleeps and a live shadow recorder down since 10-13.
- **Fill realism:** counts only, unqualified tape: 106 fills credited at a 5 s quote life and 452 at
  30 s (10-08 to 10-14). There is no markout and no fee netting.
- **NBA from 2026-10-20:** NBA is served and scored under the sealed 2026-10-07 pre-registration (arm A
  and B_lag cells so far, every cell INSUFFICIENT); the fitted arms B / C / D are in warmup until about 20
  regular-season games settle, so opening-week quotes are the mid and arm A only. No NBA-specific
  pre-registration document exists.
- **Gate G6** (eight weeks of fee-netted shadow markout) has not started as of 2026-10-19 (zero weeks collected): the
  desk runs, but fill realism is counts-only and no markout series exists. Qualified decisions are 0 on
  every sport.

## 3. What is not shown -- read before the call

- **No edge against the close pregame, and no established edge against the live market in-play.**
  The one MODEL_SHARPER_PROVISIONAL row (MLB total runs, n=49-55) is a small-sample retrospective
  diagnostic recorded in EVIDENCE.md; it is not treated here as evidence of market outperformance. No dollar,
  ROI or return figure is claimed; retracted figures appear only inside retraction framing. Six
  earlier headline figures were retracted after the project's own instruments traced each one to
  a leak, a grading artifact, an overfit or regime dependence
  ([the retraction record](evidence/retraction-story.md)).
- **Forward record: running since 2026-10-06, no verdict yet.** 113 prospective games served through
  2026-10-16, every scored cell below its 30-game floor (details in the update above). The consolidated
  scoreboard pre-registration, `PREREG_2026-10-07.json`, was sealed 2026-10-07 and covers every served
  sport, NBA included. Six go-live gates were pre-registered on 2026-09-17
  ([GO_LIVE_GATES.md](GO_LIVE_GATES.md)). Gate G6 requires at least eight consecutive weeks of
  shadow maker quoting, fee-netted markout positive with a game-clustered 95 percent interval
  excluding zero, on at least two independent market families, with a pre-registered single-game and single-week
  concentration check and a calendar-half sign-flip reject. Gate G6 itself (eight weeks of fee-netted
  shadow markout) has not started as of 2026-10-19 (zero weeks collected). The fee-aware paper sizing policy returns
  zero because every cell is refused (the in-game result is underpowered, the second corpus is
  unsealed); it has no caller ([S400 memo](evidence/harness/S400_paper_sizing_2026-09-22.md)).
- **No live order path exists.** No real order has ever been placed.

## 4. What runs next, with dates

- In-game capture (Kalshi order books plus game state) is scheduled under prospective, committed
  schedule files; the earliest records its selection at 2026-09-22T03:03Z
  ([schedules](evidence/forward/schedules/)).
- NBA in-game scoring runs under the consolidated scoreboard pre-registration `PREREG_2026-10-07.json`,
  sealed 2026-10-07, which covers every served sport (arm A and B_lag cells so far; every cell below
  the 30-game floor). The NBA-specific draft ([S382 draft r1](evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md))
  was not sealed on its own.
- The G6 maker-quoting series (eight weeks, fee-netted markout) has not started as of 2026-10-19 (zero weeks collected): a
  markout series needs qualified tape, and 0 of 44 judged games have qualified (through 2026-10-16). Its verdict is published on
  schedule whether or not the gate is met; the pre-registered expected year-end outcome is
  "G6 not met, N weeks collected" ([GO_LIVE_GATES.md](GO_LIVE_GATES.md)).

## 5. How to read the rest

[EVIDENCE.md](../EVIDENCE.md) is the claim-to-artifact index. [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)
is the adversarially audited narrative with the retired-figures list. [RECEIPTS.md](../RECEIPTS.md) holds
every generated number verbatim, and [REPRODUCE.md](../REPRODUCE.md) lists the commands that re-check
them on a fresh clone.

## 6. Five-minute verification (public clone, no private data)

Run from the repository root of a fresh clone with Python 3.10+, numpy and pytest. Each command was
re-run on 2026-10-20 on a fresh public clone (and on 2026-10-06 against a copy of the public allowlist,
`scripts/hooks/public_allowlist.txt`); each finished in under 20 seconds, and the expected output is beside it.

| # | Command | Expected | What it checks |
|---|---|---|---|
| 1 | `python -m scripts.platformkit.eval_gate.claim_consistency --repo-root .` | `claim_consistency: 0 finding(s)`, exit 0 | every figure in [CANONICAL_FIGURES.json](evidence/CANONICAL_FIGURES.json) agrees across every tracked markdown page under docs/ (guide included) plus README and EVIDENCE; no retracted figure outside retraction framing |
| 2 | `python -m pytest scripts/platformkit/eval_gate/test_claim_consistency.py -q` | `7 passed` | the gate covers the full page set and catches a changed interval, a changed verdict and the pre-correction wording, and each canonical figure matches its source memo |
| 3 | `python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q` | `4 passed` | the game-clustered Diebold-Mariano recompute behind the pregame table, on fixtures (the real recompute reads private corpora; its printed rows are in the [recompute memo](evidence/pregame/DM_RECOMPUTE_2026-09-24.md)) |
| 4 | `python -m pytest scripts/platformkit/eval_gate/test_shin.py -q` | `7 passed` | the Shin (1992) devig used for the NBA close |
| 5 | `python -c "from scripts.platformkit.execution.venue_fees import fee_kalshi_maker as m, fee_kalshi_taker as t; print(m(10, 0.50), m(1, 0.50), t(10, 0.50))"` | `0.05 0.01 0.18` | the venue fee schedule in [KALSHI_NOTE.md](KALSHI_NOTE.md): rounding once per order, maker coefficient a quarter of the taker one |

Not runnable on the public subset: the markout, paper-maker and CLV-ledger modules are published as
readable source but import private-tree modules; their definitions are on
[CLV_AND_MARKOUT.md](CLV_AND_MARKOUT.md). `scripts/platformkit/test_clv_ledger_io.py` is in the
allowlist but fails to import there for the same reason.

---
**Navigate:** [README](../README.md) - [Evidence index](../EVIDENCE.md) - [Job Evidence Packet](JOB_EVIDENCE_PACKET.md) - [Doc map](INDEX.md)
