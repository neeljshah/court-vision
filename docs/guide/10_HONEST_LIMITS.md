# 10 - Honest Limits: What May and May Not Be Claimed

> **Single truth source.** Every claim in this guide traces back to
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md), the adversarially-audited
> record. Read it first. When in doubt, defer to it.
>
> **Honesty rule.** The retracted numbers (+18.38% / 0.119 / +54% / 78.11 / 8.94 / 54.57)
> are measurement artifacts. They appear here ONLY inside the retraction section below,
> never as live results. Rule source: [.claude/rules/no-edge-claims.md](../../.claude/rules/no-edge-claims.md).

---

## The single most important statement in this guide

The calibrated model **MATCHES** the Shin-devigged closing line within noise on team-strength
markets (NBA/MLB moneyline, soccer O/U). It does **NOT beat** the close pregame. The market
is efficient; every candidate pregame edge was tested on >= 2 independent corpora and
correctly REJECTED. This is the expected, correct result for an efficient market, and the
instrument that proves it is the credential, not a failure.

---

## What you MAY claim (verified, leak-free, scoped)

### 1. Pregame calibration: we MATCH the efficient close

A 4-sport / 6-corpus real-data edge hunt ran every candidate signal through the full
leak-free gate (expanding walk-forward, truncation-invariance, null-shuffle permutation,
Benjamini-Hochberg FDR, clustered Diebold-Mariano vs the close, >= 2 independent corpora).
The results:

```
Sport       Market        Metric  N       Our model   Close     Gap       Standing
---------------------------------------------------------------------------
NBA         moneyline     Brier   372     0.1735      0.1672    +0.0063   MATCH
MLB         moneyline     Brier   13,992  0.2429      0.2390    +0.0039   MATCH
Soccer      O/U-2.5       Brier   7,558   0.2465      0.2390    +0.0076   MATCH
NBA         total O/U     RMSE    372     19.17       18.11     +1.06     BEHIND (freshness)
MLB         total O/U     RMSE    1,679   4.72        4.44      +0.28     BEHIND (freshness)
Tennis ATP  match-win     Brier   7,374   0.2177      0.2028    +0.0149   BEHIND (freshness)
```

Team-strength win markets MATCH within sampling noise. Totals and ATP trail only by the
**freshness gap** -- same-day information (injuries, starting pitchers, weather) the model
cannot see; this is a data-bound limit, not a model defect.

**Claim this as:** "The calibrated model matches the sharp devigged close on team-strength
markets across three sports. MATCH is the honest best case for an efficient market -- beating
it would imply information the close lacks."

### 2. In-game conditioning: the one measured calibration win

Fusing the pregame rating prior with the realized mid-game state sharpens the win-probability
forecaster:

- NBA: Brier 0.209 -> 0.159 (real-corpus OOS)
- MLB: Brier 0.241 -> 0.126 (real-corpus OOS)

Proof files: `scripts/platformkit/ingame_scoreboard.py`,
`scripts/platformkit/proof_nba/ingame_accuracy.py`,
`scripts/platformkit/proof_mlb/ingame_accuracy.py`. `edge_claimed = False` throughout.

**Important scope:** this is forecaster quality / calibration, not a dollar edge. A live
book also sees the score. No DM-vs-close test is applied and no $ claim follows.

**Claim this as:** "In-game conditioning is the one measured, calibrated win: fusing the
pregame prior with mid-game state sharpens the win-prob forecaster by ~0.05-0.12 Brier
(real-corpus OOS). Calibration only -- the book sees the score too."

### 3. Full-season walk-forward: well-calibrated but does not beat the close

The 2025-26 season backtest (truncation-invariance proven) shows:

- Model Brier: 0.208 vs close Brier: 0.198
- Spread/total pregame CLV ~= 0 (corr-with-outcome = 0.001; explains 0.13%/0.29% of the move)

This is the cleanest market-efficiency proof in the system.

**Claim this as:** "The full-season walk-forward proved the model is well-calibrated (Brier
0.208 vs close 0.198) but does not beat the market. CLV ~= 0. An honest validation framework
is supposed to produce this result."

### 4. Every candidate signal correctly REJECTED

Every schedule / fatigue / form / h2h / totals candidate was REJECTED on >= 2 independent
corpora. Signals that looked positive full-sample **sign-flipped** out-of-sample -- the
overfit signature, caught in real time by the gate.

This is a SUCCESS: it means the gate works and the surviving claims can be trusted.

### 5. Prop MAE (leak-free walk-forward, ~51k held-out player-games per stat)

- PTS MAE ~4.83, REB ~1.92, AST ~1.39, FG3M ~0.89 (re-measured 2026-07-20 on the grown
  corpus by `scripts/verify_production_mae.py`; earlier smaller-corpus figures were
  4.58/1.90/1.34/0.88)

These are competitive with published prop-model benchmarks. Small consistent under-bias
(~-0.45 PTS). Source: `data/cache/pregame_oof.parquet`; OOF predictions are byte-identical
to the calibration frame (max abs diff 0.0 over 319,081 rows).

---

## What you may NOT claim (retracted -- measurement artifacts)

The table below states what happened, why it failed, and what to say instead. The retracted
numbers appear here to quarantine them; they do **NOT** appear anywhere else in this guide as
live results.

| Retracted number | Root cause | What to say instead |
|---|---|---|
| **+18.38% pregame ROI** (also +15.04% flat; per-stat splits BLK +26% / STL +17%) | Market-follow grading artifact. The grader bets the market's own devigged direction, never reads the model. Priced at flat -110 fiction. Filters tuned in-sample on the same file. Model vs real closes: ~-2% unfiltered (`gate1_full_analysis.json`). | "Break-even-minus-vig vs real closes (~-2% to -5%). No dollar/ROI edge is claimed -- the earlier 'AST ~+4-5% durable edge' is retracted (2026-07-21, regime-dependent)." |
| **endQ3 in-play Brier 0.1191 "inside Pinnacle's range"** | Two features computed from Q4 data (`halftime_pace_shift`, `trailing_team_q4_usg_hhi`) let the model peek at the quarter it predicts. Cited source file actually reports 0.1354, not 0.1191. | "Leak-free walk-forward endQ3 Brier ~0.141, after removing a Q4 feature leak I found in my own pipeline." |
| **+54.57% ROI / 78.11% hit rate on 55,073 in-play bets** | Graded against an L5 rolling-average line proxy, not real sharp closes. L5 lines are softer than Pinnacle/DK. | "L5-proxy model-quality ceiling only. No realized-ROI estimate quoted; nothing counts until graded against real closing lines (first real CLV Oct 2026). Not a tradeable result." |
| **+8.94pp aggregate CLV** | Circular: computed on the same model-unused, devig-direction corpus. No Pinnacle closing-line archive existed at computation time. | Do not quote a CLV figure. "Real sharp-book CLV can't be measured yet; I built the methodology that will measure it." |

Root causes documented in `docs/KNOWN_LIMITATIONS.md` (retraction table). Proof artifacts
in `docs/JOB_EVIDENCE_PACKET.md` section 4.

---

## Validation gaps: what is NOT yet measured

### Sharp-book CLV -- first reading October 2026

No historical Pinnacle closing-line archive is publicly available. The Pinnacle scraper daemon
(`scripts/pinnacle_scraper.py`) accumulates closes from October 2026 onward. Until that gate
runs, **vs-close CLV is UNPROVEN**. No real-money bet is justified on unverified CLV.

What exists now: a walk-forward graded against DK/FD/MGM/BetRivers archives (8,360+ bets),
sufficient for the current honest read (break-even-minus-vig) but not a multi-season sharp-line
sample.

### The in-play CLV gap

NBA offseason means no liquid in-play closing prices exist at testing time. In-game
conditioning is proven on calibration (Brier lift, OOS real-corpus) but **not** on
vs-close CLV for the in-game layer. The distinction matters: calibration shows the
forecaster is sharper; CLV would show whether that sharpness translates to a market
advantage when a live book also sees the score. That test awaits in-season liquid prices.

### CV features: plumbing built, edge NOT demonstrated

CV-derived features (spatial / behavioral / biomechanical from broadcast video) are wired
into the feature matrix and fully plumbed. They do **NOT** yet move the model:
`cv_lift_report.json: has_cv_data = false`; SHAP ~= 0 in production prop models.

The moat thesis is the **cost barrier** (~$0.10/game vs six/seven-figure optical-tracking
contracts), not a demonstrated predictive edge. Per-player CV attribution is ~4% accurate;
MOTA/IDF1/positional-RMSE are not benchmarked against labeled ground truth.

**Do not claim:** "CV features are a betting edge sportsbooks lack."  
**Do claim:** "CV features are wired in as a credible future edge; they don't yet move the
model (SHAP ~0). Complete plumbing and an honest thesis, not a demonstrated advantage."

### Possession sim: structure validated, betting edge NOT claimed

The player-level possession Monte Carlo (`src/sim/basketball_sim.py`) is validated on
structure -- teammate correlation rho ~= -0.10 emerges correct from the mechanics without a
hand-tuned matrix. Same-game-parlay pricing is structurally coherent. **No SGP ROI is
claimed.** No real SGP price capture exists to grade against.

---

## Execution layer: paper only, real-money default-DENY

All sizing, routing, and P&L tracking runs in **paper / units only**. No real money has
been placed. The system's real-money gate is hard-coded default-DENY:

- `src/prediction/betting_portfolio.py`: fractional-Kelly sizing, drawdown kill-switch,
  correlation-penalty, isotonic-calibrated inputs -- all wired but gate is DENY.
- `src/betting/pnl_ledger.py`: append-only ledger, cross-platform file locking, atomic
  writes. Records paper outcomes only.
- `api/risk/status`: live drawdown kill-switch, engages automatically.
- Human gates required before any real-money flip: verified sharp-book CLV over a
  multi-season sample, real-money review, autostart confirmation.

**Do not imply any P&L track record.** There is no verified leak-free profitable edge
and zero real money placed.

---

## The self-caught leaks ARE the pitch

Every item above is evidence of senior validation discipline, not a failure:

- Built three independent harnesses that **debunked the +18.38% ROI** and traced the artifact
  to specific lines of grader code.
- Found and removed a **Q4 lookahead leak** in the win-prob features; documented it.
- Caught a **0.79-CV vs 0.06-holdout overfit**; hard-corrected it in
  `src/prediction/prop_cv_split.py`.
- Ran a **full-season walk-forward + PBP replay** that produced two clean negative results
  (market efficiency) and documented them.
- Ran a **4-sport / 6-corpus edge hunt** that caught own full-sample lifts sign-flipping
  out-of-sample -- and published the REJECT table.

The pitch: "I build ambitious systems and then build the instruments that disprove my own
hype. Here is exactly what works and exactly what I have not yet validated."

---

## Summary: the three-sentence honest position

1. **Pregame:** markets are efficient; the calibrated model matches the devigged close on
   team-strength markets, does not beat it; every candidate edge was correctly REJECTED on
   >= 2 corpora.
2. **In-game:** the one measured calibration win is in-game conditioning (NBA Brier 0.159
   vs pregame 0.209; MLB 0.126 vs 0.241); calibration only, `edge_claimed=False`, vs-close
   CLV is unproven pending liquid in-season prices.
3. **Execution:** paper/units only; real-money gate is default-DENY; no P&L track record.

---

## Where to look in the repo

- `docs/JOB_EVIDENCE_PACKET.md` -- the single truth source; every claim + do-not-claim list.
- `docs/KNOWN_LIMITATIONS.md` -- retraction table + validation gaps.
- `docs/MARKET_EFFICIENCY_PROOF.md` -- the 4-sport / 6-corpus efficiency proof + REJECT table.
- `.claude/rules/no-edge-claims.md` -- the calibration-not-edge honesty rule.
- `scripts/platformkit/edge_hunt_scoreboard.py` -- reproduce the pregame REJECT table.
- `scripts/platformkit/beat_the_close_scoreboard.py` -- reproduce the MATCH/BEHIND table.
- `scripts/platformkit/ingame_scoreboard.py`,
  `scripts/platformkit/proof_nba/ingame_accuracy.py`,
  `scripts/platformkit/proof_mlb/ingame_accuracy.py` -- the in-game calibration win.
- `src/prediction/walk_forward_backtester.py` -- per-fold leak guard.
- `tests/test_ingame_leak_free.py` -- truncation-invariance leak test.
- `scripts/validate_calibration_multicorpus.py` -- multi-corpus calibration gate.
- `src/loop/gate.py` -- the ship gate (WF + permutation + ablation + FDR).
- `src/prediction/prop_cv_split.py` -- the self-caught 0.79-vs-0.06 overfit and fix.
- `data/cache/gate1_full_analysis.json` -- the -2.00% unfiltered vs-close result.
- `data/cache/pregame_oof.parquet` -- the prop MAE source (byte-verified OOF predictions).
