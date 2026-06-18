# CUT-vs-PUSH SCORECARD -- one page, every (sport, market), the reallocation call

_Part of the edge-intelligence corpus (`_proof/`). The companion to `edge-ledger.md`: that file
tracks the proof-STATE of each edge; THIS file makes the resource-allocation CALL per (sport,
market) so effort flows unambiguously to the beatable pockets and away from the efficient ones.
Grounded in `_framework/cut-list-no-edge.md` + the measured ledger. "CUT" never means "delete the
predictor" -- it means STOP hunting a $-edge there and keep it only as calibrated decision-support.
No $-edge is claimed anywhere. ASCII only._

> Call key: **PUSH** = beatable pocket, concentrate data+modeling+CLV effort here.
> **CUT** = efficient / measured-no-edge / overfit-prone; keep calibrated-only, stop hunting $.
> **HOLD** = built but data-blocked; cheap to keep, do not invest until the corpus grows.

---

## THE SCORECARD

| Sport | Market | CALL | Reason (measured / structural) | Ledger refs |
|-------|--------|------|--------------------------------|-------------|
| **WC soccer** | Saves prop | **PUSH** | Only CALIBRATION-PROVEN stat (bss +0.337). Capture CLV + 2nd corpus to graduate. | #1 |
| WC soccer | Shots / SOT props | CUT (re-test) | NULL (bss +0.0076 / +0.0049, < proven 0.05). Need structural shot model, not pooling. | #13,#14 |
| WC soccer | Fouls / Fouls Drawn | HOLD | Marginal (+0.034 / +0.026); only data away from a verdict. | #15 |
| WC soccer | Cards / Assists / Goals / Offsides / G+A | **CUT (hard)** | REJECTED, measured negative skill (Cards -0.108, Assists -0.074). Irreducible per-match noise. Do NOT paper-bet. | #16,#18,#19,#20 |
| WC soccer | opponent-adjustment lever | HOLD | Measured NULL (+0.11 overall); table too thin. Re-test per matchday. | #12,#17 |
| WC soccer | isotonic recal | **CUT** | OOS overfit (gap +0.010); DEFERRED. Refit only as data grows. | #21 |
| WC soccer | 1X2 / O-U-2.5 / BTTS mainlines | CUT | Sharp pregame mainline -> efficient; keep as CLV yardstick. | #24 |
| **MLB** | Pitcher-Ks / Hits / Outs / Walks props | **PUSH** | Soundest Poisson shape; engine ready but **n=0** today. Backfill gamelogs -> first BSS. | #5 |
| MLB | Total Bases / RBIs / Runs / H+R+RBI props | **CUT (until compound model)** | Poisson on a weighted/correlated sum is mis-specified -> fabricates fat-tail edges. Display-only. | #25 |
| MLB | SP-aware Elo offset (moneyline) | **PUSH** | Validated in proof layer, NOT delivered. Wire into predictor, re-score vs close. Biggest unserved MLB variable. | #6 |
| MLB | season-priors rate layer | **PUSH** | MLB rewards volume (unlike NBA); strong low-variance prior. Highest structural ceiling. | #11 |
| MLB | moneyline / run-line / totals mainlines | CUT | Efficient; books see lineup+SP+weather. Match the close; CLV yardstick only. | #24 |
| MLB | in-game team win-prob | HOLD/PUSH | Repricer built; per-inning curve in-sample (OOS deferred to curve_oos). Calibration win, not $. | #2 |
| **NBA** | AST pregame prop | **PUSH (re-verify)** | The ONLY historically-claimed model edge (~+7%, both ways, never playoffs). Re-measure on fresh season. | #4 |
| NBA | PTS / REB / team pregame markets | **CUT (hard)** | At historical-data ceiling; 6 archs + 4 levers REJECT; recency>volume; 17 feature reverts. | #23 |
| NBA | h2h / spread / total mainlines | CUT | Cleanest efficiency proof (CLV ~ 0). Keep calibrated-only. Never reprint +18.38%. | #24, R1 |
| NBA | in-game team win-prob conditioning | **PUSH (calibration only)** | Cleanest principled win (Brier ~0.159 vs ~0.209); but real-corpus OOS still PENDING. End the flag. | #2,#3 |
| NBA | in-game player props (SBS) | **PUSH (gated)** | Routed MAE 1.01 vs 1.87 on one grid; default-OFF. Prove cross-corpus, promote per cell. | #7 |
| NBA | momentum / hot-hand bet signals | **CUT (hard)** | Worse than null (z -1.75). Form as a rate input only. | #22 |
| **Tennis** | set-level in-game win-prob | HOLD | Analytic race-to-N built (dodges MAE artifact); no game/point engine; 0 settled. | (dd11) |
| Tennis | pregame match mainlines | CUT | Efficient; match the close. | #24 |
| **Cross-sport** | live/in-game lag (all) | **PUSH (calibration)** | The decisive combinable lever; books lag realized state. Forecaster quality, NOT $ (book sees score too). | #2,#7 |
| Cross-sport | prediction-market vs book divergence | **PUSH (measure first)** | Two crowds; unmeasured. Log paired lines, measure convergence + CLV. | #9 |
| Cross-sport | stale-line / soft-book line-shopping | **PUSH (execution)** | Model-free best-price edge; prove via realized CLV. | #10 |
| Cross-sport | correlated SGPs | **PUSH (build joint)** | Books misprice correlation; we can price the joint. Validate full stat-pair surface. | #8 |
| Cross-sport | arbitrage as a profit center | **CUT** | Rare, fragile, limit-bound. Keep DETECTION as a free flag only. | #26 |

---

## THE ONE-LINE REALLOCATION

**CUT** all sharp pregame mainlines (NBA/MLB/soccer h2h/spread/total), NBA team PTS/REB pregame,
momentum bet signals, the negative-skill WC rare-event props (Cards/Assists/Goals/Offsides),
in-sample-only recal, mis-specified multi-value MLB props, and arbitrage-as-income. **PUSH** the
six beatable pockets: (1) soft/DFS player props in PROVEN/sound stats (WC Saves; MLB
K/Hits/Outs/Walks), (2) live/in-game conditioning (calibration), (3) stale-line/soft-book
line-shopping, (4) prediction-market divergence, (5) correlated SGPs, (6) DEEPER DATA in those
pockets (MLB gamelog backfill, season priors, more WC matchdays, a live minutes/usage feed) --
because data depth is the only lever that actually moves the ceiling.

## THE ENABLING UNBLOCK (do this regardless of pocket)

Capture closing lines (`prop_line_history` has 1 row; 0/14 settled bets carry a real CLV) and
forward-accrue settled outcomes toward `dm.n>=200`. Without CLV capture, NO push pocket can ever
graduate past CALIBRATION-PROVEN -- the entire scorecard stays calibration-only until the ledger
fills. This is an ops/cadence fix, not a modeling one, and it is the single highest-leverage action.

## HONESTY FOOTER

PUSH pockets are where the data-to-edge chain CAN complete -- not where profit is proven (it
isn't, yet; CLV-PROVEN is empty). CUT is reallocation, not defeatism. Every CUT is backed by a
measured null/reject in `edge-ledger.md`. Markets are mostly efficient; the north star is
calibration vs the devigged close.
