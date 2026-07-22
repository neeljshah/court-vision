# Betting Decision Layer — CourtVision

Engineering documentation for the decision layer: how the system converts model
probabilities into bet-sizing recommendations, tracks closing line value, and
measures against real markets.

> **Disclaimer:** This describes engineering methodology for research purposes.
> Sports betting must comply with laws in your jurisdiction. No real money has
> been placed using this system. No profitable edge is claimed.

---

## What the Market Tells Us

The single most important result from backtesting against real closing lines is
negative: **the market is efficient.** Against DraftKings/FanDuel/MGM closing
lines, the model is roughly **break-even-minus-vig** overall (unfiltered figure
~-2.00% from `gate1_full_analysis.json`). No exception has survived leak-free
re-testing -- see the retracted AST row below.

**Why state a negative result prominently?** Because it required building three
independent grading harnesses to confirm, and because finding it is the whole
point. A system that can tell a real edge from a measurement artifact is more
valuable than one that claims profit it cannot substantiate.

### What is NOT claimed

| Retracted claim | Why it fails |
|---|---|
| **+18.38% ROI on 1,535 walk-forward bets** | Market-follow grading artifact. The grader read `devig(over_odds, under_odds)` — the market's own lean — and never read the model. Prices at a flat -110 fiction. Filters tuned in-sample. At real odds: ~-4%. |
| **endQ3 in-play Brier 0.1191** | Two Q4-derived features leaked into the model. Honest leak-free number is ~0.141. |
| **+54% ROI / 78% hit on 55K in-play bets** | Graded against an L5 line proxy, not real closing lines. A model-quality ceiling, not a realized edge. |
| **Assists (AST): ~+4-5% ROI "durable, book-robust edge"** | A 2026-06-27 leak-free re-test of `ast_rate_diff_asof` vs Elo found an HONEST REJECT: Brier delta -1.4e-5 (worse), DM p=0.78, fitted weight shrinks to -0.006. AST carries no incremental win-prob signal over Elo -- the earlier figure was a box/prop-grading artifact, not a team-win-prob edge. |
| **Real CLV measurement** | First real Pinnacle-close CLV reading is October 2026. None yet exists. |

These retractions are documented at the source-code level in
`docs/JOB_EVIDENCE_PACKET.md`.

---

## The Decision Layer (Engineering)

The decision layer is a sequence of pure, network-free transforms. The system
**bets on divergence, not on predictions**: a high model number is worthless on
its own -- the only thing that can be a bet is a model probability that *diverges
from the price the market is actually offering*. Everything below exists to (a)
measure that divergence honestly, (b) decide whether it clears a bar, and (c)
size it in UNITS (never dollars).

```
Model probability  (calibrated, walk-forward)
       |
De-vig             Shin-strip the book overround -> fair implied prob
       |
Line-shopping      take the BEST bettable price across books for that side
       |
Edge / EV          edge = model_prob - fair market_prob;  EV = p * decimal_odds - 1
       |
Tier floors        EV vs A/B/C floors (+0.01 if the close is a proxy)
       |            below the C floor -> NO BET (this is the common outcome)
Kelly sizing       flat 1u (for CLV) + capped quarter-Kelly u (for bankroll)
       |
CLV tracking       after close: did we hold a better number than the close?
```

The reference implementation of the decision step is
`frontend/exec_decision.py::decide_row` (pure, <=300 LOC, no `$` field by
construction). It reuses the vetted Shin devig + EV helpers from
`scripts/platformkit/odds_shop.py` rather than reimplementing them. The worked
math, tier table, and no-bet semantics are in
[docs/decisions.md](decisions.md); the units-only sizing and the paper loop are
in [EXECUTION_GUIDE](EXECUTION_GUIDE.md); the venue routing and account-health
layer are in [architecture/execution-engine](architecture/execution-engine.md).

> **Paper-only, units-only.** `ENABLED=False` / `LIVE_BETTING=0` is enforced in
> code (`bet_selector.py` exits non-zero if `LIVE_BETTING != 0`). Stakes are unit
> counts, never money. Real capital is **human-gated behind a recorded CLV track
> record** -- see the Real-Money Gate below. CLV (holding a better number than the
> close), not ROI, is the scoreboard.

---

## De-Vig

**Module:** `src/prediction/devig.py`

Converts vigged sportsbook prices to fair implied probabilities. Four methods
are implemented:

| Method | Implementation | Notes |
|---|---|---|
| Proportional | `proportional_devig()` | Simple: divide each prob by the overround. Biased on heavy-favourite markets. |
| Multiplicative | `multiplicative_devig()` | Power-renormalisation via bisection. More balanced. |
| Power | `power_devig()` | n-th root method. Cheap approximation. |
| **Shin (1992)** | `shin_devig()` | **Default.** Insider-trading model via stable bisection solver. Loads the vig asymmetrically onto the longshot, recovering the informed-flow fraction `z`. |

Shin is the theoretically grounded choice: it does not assume vig is split
evenly, so it returns higher probability for the favourite than proportional
on lopsided markets -- which is the direction most retail tools get wrong.

```python
from src.prediction.devig import shin_devig, american_to_prob

# -115 / -105 two-sided market
over_prob  = american_to_prob(-115)   # 0.535
under_prob = american_to_prob(-105)   # 0.512

fair_over, fair_under = shin_devig([over_prob, under_prob])
# fair_over ~= 0.511, fair_under ~= 0.489
# (vig removed asymmetrically)
```

The `POST /api/devig` endpoint defaults to `shin`.

---

## Kelly Criterion Sizing

**Module:** `src/prediction/betting_portfolio.py` -- `kelly_corr()`

Kelly sizing translates an edge into the mathematically optimal bankroll
fraction. The system uses fractional Kelly with hard caps and a drawdown
circuit breaker.

**The formula:**

```
full_kelly = edge / (decimal_odds - 1)

quarter_kelly = full_kelly x 0.25        # KELLY_FRACTION = 0.25
capped_kelly  = min(quarter_kelly, 0.04) # MAX_BET_PCT = 4% of bankroll
```

**Correlation penalty** (`kelly_corr`): when multiple props are in flight
simultaneously, a persisted correlation matrix (`data/models/prop_corr_matrix.json`)
shrinks stakes for positively-correlated bets. A teammate's pts/reb over are
positively correlated; the Kelly fraction for each is reduced so combined
exposure stays rational.

**Drawdown circuit breaker**: betting halts automatically when drawdown exceeds
`MAX_DRAWDOWN_PCT = 15%` of starting bankroll.

**Portfolio caps**: `MAX_OPEN_BETS = 20` in-flight at once.

Why quarter-Kelly and not full? Full Kelly maximises long-run growth in theory
but produces extreme variance in practice when edge estimates are noisy
(as they always are from a model). Quarter-Kelly captures most of the growth
benefit at a fraction of the variance.

### Two stakes, both in UNITS

The execution layer emits **two** unit figures per accepted bet, never a dollar
amount (`exec_decision.py`):

| Field | Value | Purpose |
|---|---|---|
| `flat_unit` | `1.0` | Flat-unit stake used for **CLV tracking** -- every accepted bet counts once so beat-the-close rate is unbiased by sizing |
| `kelly_units` | capped quarter-Kelly, `min(0.25 * f*, 4.0)` units | Bankroll-growth sizing; `f* = (p*b - (1-p))/b`, `b = decimal_odds - 1` |
| `stake_units` | `flat_unit + kelly_units` | Reported total; **a unit count, not money** |

`kelly_units` is floored at 0 (a non-positive-EV line is never staked) and hard-
capped at 4.0 units so one fat row cannot dominate the slate. The greedy
`betting_portfolio.kelly_corr` path (used by `bet_selector.py`) applies the same
quarter-Kelly fraction with a 4%-of-bankroll cap and the correlation penalty
above; `exec_decision.py` is the pure units-only restatement of the same math.

---

## Line-Shopping Across Books

Edge is always measured against the **best bettable price** for the side, not a
flat -110 fiction (paying a flat fiction is exactly what inflated the retracted
+18.38% figure). For each (market, side) the pipeline:

1. Collects every book's price for that side.
2. Shin-devigs each two-way market to a fair probability.
3. Routes to the book offering the **highest probability at acceptable vig**
   (`architecture/execution-engine` Routing Priority 1).
4. Computes `EV = model_prob * decimal_odds - 1` against *that* best price.

`betting_portfolio.detect_arb()` is the cross-book companion: when the best OVER
and best UNDER across books imply a total probability `< 1.0`, it reports the
guaranteed `arb_pct`. Arbitrage is a pricing-structure observation, not a claimed
income stream.

**Proxy vs true close.** When the line we can settle against is only a *proxy*
(e.g. an L5 line, not a true settled close), every tier floor is raised `+0.01`
(`PROXY_FLOOR_BUMP`) so a proxy must clear a stricter bar before it is a bet, and
the resulting CLV is flagged `clv_is_proxy=True`. A proxy CLV is a model-quality
ceiling, never a realized beat-the-close claim.

---

## Worked Example (UNITS only, never $)

A single `decide_row` evaluation, illustrative numbers only:

| Step | Value |
|---|---|
| Model probability (calibrated) | `p = 0.560` |
| Best bettable price across books | `+105` -> decimal `2.05` |
| Shin-devigged fair market prob | `market_prob = 0.515` |
| Edge | `0.560 - 0.515 = +0.045` |
| EV | `0.560 * 2.05 - 1 = +0.148` |
| Tier (true close, floors A>=0.08 / B>=0.04 / C>=0.02) | **A** (EV >= 0.08) |
| Kelly: `b = 1.05`, `f* = (0.56*1.05 - 0.44)/1.05` | `f* ~= 0.141` |
| `kelly_units = 0.25 * f*` (cap 4.0) | `~= 0.035 u` |
| `flat_unit` | `1.0 u` |
| `stake_units` | `~= 1.035 u` |

A below-floor counter-example: if the same model prob faced a `-120` price, the
fair edge and EV collapse below the `C` floor (`0.02`), `tier=None`, and the row
is returned as `decision="no_bet"` with `stake_units = 0.0`. **No-bet is the
modal outcome** -- the market is efficient and most candidates do not clear a
floor. See [docs/decisions.md](decisions.md) for the floor table and the
per-policy edge floors layered on top.

---

## Closing Line Value (CLV)

**Module:** `src/validation/clv_tracker.py`

CLV is the correct yardstick for edge quality, not win rate and not short-term
ROI.

```
CLV = closing_implied_prob - bet_implied_prob

Example:
  Bet placed at: player over at -110  ->  implied prob 52.4%
  Closing line:  same market at -130  ->  implied prob 56.5%
  CLV = 56.5% - 52.4% = +4.1%  (positive: you beat where the market settled)
```

Why CLV over ROI? The closing line aggregates all available public information.
If you consistently beat it, you had information or a process advantage that the
market did not have at bet time. If you win bets but lose to the close, you got
lucky on short-term variance -- the edge is not real.

`clv_tracker.py` exposes `compute_clv()` which handles American, decimal, and
implied-prob input formats, and removes vig via `vig_strip()` before comparing
sides.

### Sign convention (this has bitten the codebase before)

CLV is **positive when you held a better number than the close**. Two
implementations carry this and must agree:

| Source | Price-space (`clv_percent`) | Line-space (`clv_line`) |
|---|---|---|
| `src/betting/clv.py::compute_clv` | `closing_implied_prob - placement_implied_prob` (positive = close is shorter, you locked the longer price) | OVER: `closing_line - placed_line`; UNDER: `placed_line - closing_line` |
| `betting_portfolio.record_clv` | side-aware fraction of opening | OVER: positive when close > open; UNDER: positive when close < open |

The line-space sign is **side-dependent**: for an OVER, a *higher* closing line
means you locked the easier number (good CLV); for an UNDER, a *lower* closing
line is the good move. A historical reporting bug reported `beat_close` for both
directions; the corrected semantics are gated behind `CV_CLV_LINE_SIGN_FIX`
(default OFF for byte-identical legacy reports -- the price-based `clv_percent`
was always correct, so daily CLV is unaffected). Do not "re-fix" the sign without
reading `src/betting/clv.py` first.

"Closing" = the snapshot captured closest to `(tip - 30 min)` but strictly before
the bet's asof time; a snapshot older than 24h is treated as missing rather than
as a stale close.

### Paper-trade loop + ledger

The forward record is built by a manual-placement, no-API loop:

1. **Select** -- `bet_selector.select()` produces `bets_YYYYMMDD.json` (status
   `paper`) under the dual gate (`|edge| > edge_min` AND predicted CLV > `clv_min`).
2. **Place (record only)** -- `pnl_ledger.place_bet()` writes a row to the
   transactional, file-locked `data/pnl_ledger.csv`. The operator places any real
   bet manually; no sportsbook API is touched.
3. **Settle** -- `pnl_ledger.settle_bet()` (or `auto_settle_date()` from cached
   gamelogs) resolves won/lost/push from line vs actual and updates the bankroll
   log.
4. **Enrich** -- `clv.enrich_pnl_with_clv()` joins each settled bet to its closing
   snapshot and writes `data/pnl_ledger_clv.csv` with `clv_line / clv_percent /
   beat_close`.
5. **Aggregate** -- `clv.aggregate_clv()` reports `beat_close_rate`,
   `mean_clv_percent`, and the per-bet `clv_vs_roi_corr` (the honesty check: CLV
   should predict realized ROI). `pnl_summary()` reports win rate, ROI, and a
   per-bet Sharpe -- for diagnostics, not as a claim.

The ledger is the single source of truth, atomic (tmpfile + `os.replace`) and
guarded by a sidecar lockfile so concurrent writers cannot corrupt it.

**Current status:** the methodology and tooling are built; real forward CLV
against Pinnacle closing lines starts October 2026 (first regular-season closing
lines). The system cannot yet report a real CLV figure, only a methodology. No
real money has been placed.

---

## Prop Correlation Structure

**Module:** `src/prediction/betting_portfolio.py` -- `kelly_corr()`

The joint probability structure of multi-leg bets matters because sportsbooks
price parlays assuming independence. The simulation in `src/sim/basketball_sim.py`
samples from a shared scoring-pie model, so teammate correlations emerge from
the mechanics rather than from a hand-tuned matrix. Measured teammate
correlation is approximately −0.10 (realistic negative correlation from competing
for scoring opportunities), versus a prior simulator's +0.65 (wrong direction).

`sgp_from_sim.py` prices same-game parlays off the joint sample with a
`validate_joint_calibration` harness. **No SGP edge is claimed** -- the value
is the correct pricing structure, not a known market discrepancy.

---

## Walk-Forward Validation Architecture

The honest market-efficiency result required three independent harnesses:

1. `scripts/run_gate1_full_analysis.py` -- main walk-forward gate with per-stat splits
2. `scripts/gate1_filtered_vs_vegas.py` -- filtered-subset vs real closing lines
3. `scripts/reconcile_edge_source.py` -- root-cause audit of how the grader reads the model

All three agree: the model is approximately break-even-minus-vig overall. The
harnesses are in the public repo; the audit methodology is in
`docs/JOB_EVIDENCE_PACKET.md §3`.

Walk-forward protocol: expanding windows, `max_train_date < min_test_date`
asserted per fold, multi-corpus calibration acceptance gate (must beat raw on
>=2 independent corpora before a calibration ships), isotonic calibration on
win-probability inputs.

---

## Canonical Numbers

| Metric | Value | Source |
|---|---|---|
| Overall ROI vs real closing lines | ~-2% (break-even-minus-vig) | `gate1_full_analysis.json` |
| AST win-prob signal vs Elo | REJECTED (Brier delta -1.4e-5, DM p=0.78) | `docs/JOB_EVIDENCE_PACKET.md`, 2026-06-27 re-test |
| Prop MAE -- PTS | ~4.83 | `data/cache/pregame_oof.parquet`; re-measured 2026-07-20 on grown corpus (was 4.58) |
| Prop MAE -- REB | ~1.92 | Same (was 1.90) |
| Prop MAE -- AST | ~1.39 | Same (was 1.34) |
| Prop MAE -- FG3M | ~0.89 | Same (was 0.88) |
| Win-prob walk-forward accuracy | 0.709 | `winprob_walk_forward_results.json` |
| Win-prob walk-forward Brier | 0.193 | Same |
| endQ3 Brier (leak-free) | ~0.141 | After removing two Q4-derived features |
| Real CLV first reading | October 2026 | Not yet available |
| Real money placed | $0 | |

---

## Infrastructure Summary

| Component | Module | Status |
|---|---|---|
| Shin de-vig (4 methods) | `src/prediction/devig.py` | Built, 7 tests pass |
| Kelly sizing (corr-aware, drawdown-gated) | `src/prediction/betting_portfolio.py` | Built |
| CLV math (multi-format) | `src/validation/clv_tracker.py` | Built |
| Walk-forward backtester (assertion-level leak guard) | `src/prediction/walk_forward_backtester.py` | Built |
| Multi-corpus calibration gate | `scripts/validate_calibration_multicorpus.py` | Built |
| Shadow logger (all evaluated bets, pass and block) | `src/prediction/shadow_logger.py` | Built |
| P&L ledger (transactional, file-locked) | `src/betting/pnl_ledger.py` | Built |
| Real forward CLV pipeline | -- | October 2026 |

---

## The Real-Money Gate (human-gated)

Live capital is **off by default and human-gated**. Two independent locks:

- **Code flag.** `bet_selector.py` refuses to run unless `LIVE_BETTING=0`; the
  execution-engine adapters log intent and skip real orders under the same flag
  (`architecture/execution-engine` global dry-run gate). Flipping a flag ON is a
  human-gated action, never taken autonomously.
- **Evidence gate.** All of the following must pass *simultaneously* before a
  human may consider live capital (see [risk-framework](risk-framework.md) Live
  Capital Gate): >=50 settled paper bets, CLV beat rate >=55%, paper ROI >=3%,
  calibration drift <10% on every stat, backtest ROI >= 0.7x paper ROI, and zero
  circuit-breaker events in the last 7 days.

A partial pass does not unlock anything. The gate is conservative by design
(default-deny): the honest yardstick is a recorded positive-CLV track record, not
a backtested ROI number.

---

See also: [EXECUTION_GUIDE](EXECUTION_GUIDE.md)  -  [decisions](decisions.md)  - 
[risk-framework](risk-framework.md)  - 
[architecture/execution-engine](architecture/execution-engine.md)  - 
[label_strategy](label_strategy.md)  -  [docs/DATA.md](DATA.md)  -  [docs/DEMO.md](DEMO.md)  - 
[PREDICTIONS_QUICKSTART.md](../PREDICTIONS_QUICKSTART.md) ·
[docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
