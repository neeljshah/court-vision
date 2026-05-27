# /quant-refresh — pre-interview repo & numbers refresh

Goal: in one autonomous pass, verify every load-bearing claim in the README is still
true, frame it in proper quant statistics, update the public README, and push to
master. Treat this like a sharp interviewer asking "prove this number" for each
metric on the page.

**Authorization:** the user has pre-authorized `git push origin master` for this
command. Do NOT push if any verification step fails.

---

## Step 1 — Pre-flight

```bash
cd C:\Users\neelj\nba-ai-system
git status --short | head -10
git log --oneline -5
```

Verify:
- HEAD is on `master`
- Working tree is reasonably clean OR all dirty files are pre-existing data
  artifacts (`data/cache/**`, `data/lines/**`, runtime files) and NOT source code.
  If source code is dirty, STOP and ask the user.
- Last commit message looks coherent (no half-finished work)

If anything looks off, STOP and report. Don't proceed blind.

---

## Step 2 — Full test suite

```bash
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest tests/ -q --tb=short 2>&1 | tail -25
```

Acceptance:
- Zero failures on the in-play validation subset (always): `test_shadow_logger.py`,
  `test_settlement.py`, `test_snapshot_replay.py`, `test_decision_engine_gates.py`,
  `test_pregame_ev_engine.py`, `test_live_v2_app.py`, `test_calibration.py`,
  `test_daily_roi.py`.
- Full suite ≥ 99% pass (some legacy tests may bitrot — acceptable if isolated).
- Note count: passed / failed / errored / skipped.

If the in-play subset has ANY failure, STOP. Diagnose and fix before continuing.

---

## Step 3 — Re-run backtest (if stale)

Check `vault/Reports/backtest_<latest>.md` modification time. If older than 48h,
re-run:

```bash
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe scripts/run_backtest.py --n-games 50
```

This takes 10-15 minutes. Run it in the background and continue with Step 4
against the existing settled CSV in parallel. When the backtest finishes, refresh
the numbers in Step 5.

---

## Step 4 — Compute quant statistics on the calibrated emit set

Load `data/shadow/settled_<latest>.csv` with pandas. Filter to the calibrated
emit set (`gate_status == "passed"` AND `raw_ev >= 0.04` AND `tier in {"S","A"}`
AND `outcome in {"hit","miss","push"}`). Compute the following — these are the
numbers a quant interviewer will press on:

**1. Hit rate with Wilson score 95% CI**
```python
from statsmodels.stats.proportion import proportion_confint
n = len(emit_set)
wins = (emit_set.outcome == "hit").sum()
hit_rate = wins / n
lo, hi = proportion_confint(wins, n, method="wilson", alpha=0.05)
```
Report: `hit_rate = X.X% (95% Wilson CI [Y.Y%, Z.Z%], n=N)`

**2. ROI with per-bet sigma + standard error of mean**
```python
returns = emit_set["realized_return_$1"].values
roi_mean = returns.mean()
roi_sigma = returns.std(ddof=1)
roi_sem = roi_sigma / np.sqrt(len(returns))
t_stat = roi_mean / roi_sem
```
Report: `ROI = +X.X% per $1 (per-bet σ = $A.AA, SEM = $B.BB, t-stat vs 0 = T.T)`.
A t-stat above ~2.5 is your "this is not noise" line.

**3. Sharpe ratio of per-bet returns**
```python
sharpe = roi_mean / roi_sigma  # per-bet, not annualized
```
Report: `per-bet Sharpe = X.XX (1.0+ is institutional-grade for a single bet)`.
Bets aren't time-indexed so you can't annualize cleanly; per-bet Sharpe is the
honest stat.

**4. Calibration RMSE across predicted-EV deciles**
```python
emit_set["decile"] = pd.qcut(emit_set.raw_ev, 10, labels=False, duplicates="drop")
cal = emit_set.groupby("decile").agg(pred=("raw_ev","mean"),
                                      real=("realized_return_$1","mean"),
                                      n=("raw_ev","size"))
rmse = np.sqrt(((cal.pred - cal.real)**2).mean())
```
Report: `calibration RMSE = X.XXX across 10 deciles (lower = model is honest)`.
Print the decile table too — interviewers love staring at it.

**5. Per-tier breakdown with sample sizes**
For each tier in {S, A, B, C} × each quarter in {endQ1, endQ2, endQ3}: compute
n, hit_rate, ROI, Wilson CI. Surface the lowest-confidence cells (smallest n).

**6. Backtest vs SAS@OKC live-game out-of-sample check**
Run `python scripts/replay_last_night.py` (or equivalent for whatever was last
night's NBA game — query cdn.nba.com scoreboard for the date). Settle the
emitted bets against the final box score. Report the n=8-ish single-game
record and frame it as: "in-sample backtest is +X.X% ROI, out-of-sample single
game went Y-of-N at +Z.Z% — consistent / inconsistent with backtest distribution
at p=___".

**7. Drawdown analysis**
Compute the worst rolling-100-bet PnL window from the settled CSV. This is the
"how ugly does it get?" number an interviewer will ask. Report max drawdown in
$ on $100/bet flat AND as % of starting bankroll under 25% portfolio Kelly.

---

## Step 5 — Cross-check against vault reports

Read `vault/Reports/backtest_<latest>.md`, `filter_calibration_<latest>.md`,
`daily_roi_<latest>.md`. Verify:
- The numbers in your Step 4 computation MATCH the report (±0.5% drift OK from
  rounding)
- If they don't match, the report or your computation is stale — investigate
  before updating README

Also pull:
- Calibrated EV emit floors from `src/prediction/decision_engine.py` constants
  (`TIER_B_EV`, `_EMIT_FLOOR_BY_PERIOD`, `_EV_CEILING_BY_PERIOD`) — confirm
  they match what the README claims
- Walk-forward MAE from `data/models/quantile_pergame_metrics.json` — confirm
  the README's MAE table matches
- Win-prob accuracy from `data/models/win_prob_metrics.json` — confirm match

If anything drifted, note it for the README update.

---

## Step 6 — Update README

Read current `README.md`. For each table/number that drifted in Step 5, update
in place. Add a quant-framed section at the TOP of "The Headline" if not already
there:

```markdown
### Statistical confidence

| Metric | Value | 95% CI / signal |
|--------|-------|-----------------|
| Hit rate (calibrated emit set) | X.X% | Wilson [Y.Y%, Z.Z%], n=N |
| ROI per $1 flat | +X.X% | σ=$A.AA, SEM=$B.BB, t-stat=T.T (p<0.001) |
| Per-bet Sharpe | X.XX | institutional bar is ~1.0 |
| Calibration RMSE | 0.XXX | across 10 EV deciles |
| Worst 100-bet drawdown | −$X | on $100/bet flat |
```

Honesty rules:
- NEVER claim a Sharpe or t-stat that wasn't actually computed in Step 4
- Always include n alongside ROI/hit rate
- Always include the L5-proxy caveat — "real-money ROI will be lower"
- If t-stat < 2.0, lead with "directionally consistent but not statistically
  significant at p<0.05 yet"
- If sample is < 1,000 for any cell, mark with † and add a footnote

Update the `*Last verified: YYYY-MM-DD*` footer.

---

## Step 7 — Final acceptance gate before push

ALL of these must be green:
- `pytest tests/test_shadow_logger.py tests/test_settlement.py tests/test_snapshot_replay.py tests/test_decision_engine_gates.py tests/test_pregame_ev_engine.py tests/test_live_v2_app.py tests/test_calibration.py tests/test_daily_roi.py -q` returns 0 failures
- Hit rate, ROI, Sharpe, calibration RMSE all positive-direction (no regression
  from prior README values by more than 5%)
- README diff is purely numerical updates + caveats — no architectural claims
  invented
- `git diff README.md` is reviewable in under 60 seconds

If ANY of these fail, STOP. Report the failure verbatim and exit without pushing.

---

## Step 8 — Commit + push

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): refresh quant statistics for <date> verification

- Hit rate / ROI / per-bet Sharpe / t-stat from <n>-bet calibrated emit set
- Calibration RMSE across EV deciles
- Cross-checked against backtest_<date>.md and filter_calibration_<date>.md
- (any other specific changes)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin master
```

Report the commit SHA + GitHub URL.

---

## Step 9 — One-page interview cheat-sheet

Print to stdout (also save to `vault/Reports/interview_cheatsheet_<date>.md`):

```
=== INTERVIEW CHEAT-SHEET — <date> ===

THE NUMBER:
  X.X% hit on N bets (Wilson 95% CI [..., ...])
  +X.X% ROI per $1 flat, t-stat T.T (p<0.001)
  Per-bet Sharpe X.XX

WHY IT'S REAL:
  - Calibration deciles 1→9 monotonic, RMSE 0.XXX
  - 50 finalized games, cdn.nba.com box-score settlement
  - Tier S endQ3: 93% hit on 5,088 bets — concentrated edge where it should be
  - Pre-calibration was −4.25% — filter audit identified Tier C as poison;
    raising EV floor flipped aggregate by +51pp

HOW IT'S BUILT:
  - 120 prediction modules, NNLS stacking, q50 quantile heads
  - Walk-forward season-purged validation (48hr same-team purge)
  - Shadow logger captures EVERY evaluated bet incl. blocked → audit trail
  - 9-daemon execution stack, fractional Kelly + correlation shrinkage

CAVEATS THE INTERVIEWER WILL PRESS ON (be honest):
  - L5 line proxy, not real Pinnacle closes. Real-money ROI estimate: +15–25%
  - Zero real money placed; gated behind Oct 2026 preseason
  - 50-game sample at endQ3 — wider variance than n=5,000 sounds like
  - Single-night PnL is high-variance (SAS@OKC went 6-of-8 yesterday)

ONE-LINER:
  "Solo-built NBA quant stack. 90K-bet in-play backtest hits 78% at +54% ROI
  on a well-calibrated model. Real-money validation gates open Oct 2026."

WHAT TO DEFLECT TO IF ASKED ABOUT WEAKNESSES:
  - CV depth (7/80 CLEAN games) → "next milestone, gated on RunPod budget"
  - PTS calibration (49% beat at sharp closes) → "the next pin per CHANGELOG"
  - Live execution proof → "designed for it, awaiting season — see 9 daemons,
    decision engine, shadow logger, settlement, daily ROI CLI"
```

This is what you walk into the interview with. Memorize the top three lines.

---

## Hard rules

- Never invent numbers — every value in the README must come from a JSON file,
  a settled CSV, or a Step 4 computation
- Never push if any test fails
- Never claim statistical significance below t-stat 2.0 — say "directional" instead
- Never delete the existing caveats; sharpen them if they're stale
- Never touch architecture claims, only refresh numbers
- Never push to remote `main` — only `master`
- If the backtest regresses by > 5% vs prior README values, STOP and surface it;
  don't quietly update with worse numbers
- Always include the L5-proxy disclaimer somewhere visible
