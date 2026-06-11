# Known Limitations

Concrete operational state of CourtVision as of **2026-06-11**. This file is kept honest so
that the README and ARCHITECTURE don't have to litter their headline sections with caveats.
Audit trail of fixes: [`../CHANGELOG.md`](../CHANGELOG.md). Live operational state:
[`CLAUDE-state.md`](CLAUDE-state.md).

The philosophy: surface the gaps explicitly so external readers (interviewers, collaborators,
future contributors) can calibrate trust. Nothing is hidden; nothing is sugar-coated.

---

## Retracted numbers — the discipline headline

These are the most important entries in this file. The validation harnesses were built to
*refute* the headlines, not confirm them. When they didn't survive, the honest version was
written here and the inflated one was retired.

| Retracted | Root cause | Honest version |
|---|---|---|
| **+18.38% ROI vs real closing lines** | Market-follow grading artifact: grader bets the market's own devigged direction, never reads the model; priced at flat -110 fiction; filters in-sample tuned | Break-even-minus-vig overall (~-2% to -5%); AST ~+4–5% is the one durable edge |
| **endQ3 Brier 0.1191 "Pinnacle-class"** | Two features computed from Q4 data (`halftime_pace_shift`, `trailing_team_q4_usg_hhi`) cause the model to peek at the quarter it predicts; cited source file actually reads 0.1354 | Leak-free ~0.141 after removing the Q4-derived features |
| **+54%/78% in-play ROI on 55,073 bets** | Settled against an L5 rolling-average line proxy, not real sharp closes | L5-proxy model-quality ceiling only; real estimate +15–25% |
| **Full-season spread/total edge** | Full-season WF backtest (truncation-invariance proven): CLV ≈ 0 (corr-with-outcome = 0.001; explains 0.13%/0.29% of the move) | Market is efficient on closing lines; AST is the only measured edge |
| **In-series win-prob edge** | PBP Finals replay (G1–G3): pooled win-prob Brier **0.34–0.40** (worse than a coin flip) | No pregame edge in playoffs; NYK/SAS coin flip at ~47–50% |

Full proof artifacts and source-code root causes: **[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**.

---

## Validation gaps

### Sharp-book CLV — first reading October 2026

No historical Pinnacle closing-line archive exists publicly. The Pinnacle scraper daemon
(`scripts/pinnacle_scraper.py`) accumulates closes from Oct 2026 onward; the first real
sharp-book CLV reading is therefore ~4 months out. Until that gate runs, no real-money
execution is justified.

What exists at real closes (partial-season, DK/FD/MGM/BetRivers archives via public repos):
8,360+ walk-forward bets — sufficient for the current honest read (break-even-minus-vig) but
not a multi-season sample. Consolidated report: `data/models/gate1_results_summary.json`.

### L5 line proxy ≠ real closes

The 55,073-bet in-play backtest settles against an **L5 rolling-average line proxy**, not real
Pinnacle/DK closes. L5 lines are softer than sharp closes. Best estimate of compression when
re-evaluated against real lines: **+54% paper → +15–25% real**. The +54% is a model-quality
ceiling, not a deployment forecast.

### Market efficiency (the honest finding)

The full-season walk-forward backtest proves the system is **well-calibrated but does not beat
the close** (season Brier 0.208 vs close Brier 0.198). Spread/total pregame CLV ≈ 0; the model
explains 0.13%/0.29% of the line move. Freshness (betting openers before news) reaches ~58%
ATS but the model captures none of that — it is a speed edge, not a model edge.

### Possession sim — structure validated, betting edge NOT claimed

The player-level possession Monte Carlo and its same-game-parlay layer (`sgp_from_sim.py`)
are validated on **structure**, not profit:

- Teammate-ρ ≈ −0.10 emerges correct (no hand-tuned matrix); `validate_joint_calibration`
  grades the sim-joint vs outcomes on historical games.
- **No SGP ROI is claimed.** The repo has no real same-game-parlay price capture to grade
  against; SGP pricing is structurally correct, not a demonstrated edge.
- **Team totals run high.** The player-level scoring pie over-allocates slightly; trust the
  side more than the over.

---

## Data coverage limits

### CV coverage

- **~85 games tracked** in `data/tracking/` (YOLOv8 + SIFT + OSNet output)
- **7 games with full feature extraction** (defender_distance / spacing / fatigue end-to-end)
- **Target: 80 CLEAN** for the production CV-feature gate (Tier 3/4 model retrain)
- Some games have `ball_valid_pct = 0%` because `ball_track_suspended` stays True — known fix
  queued after the 80-game push
- **Per-player CV attribution: ~4% accuracy** — slot identities not stable across long
  occlusions; aggregate team-level / position-level CV features are ship-ready

### CV signal lift in production — SHAP ≈ 0

Every CV feature carries **SHAP importance ≈ 0.0** in production prop models today
(`cv_lift_report.json: has_cv_data: false`). The plumbing is complete; the lift is unproven.
Do not claim a CV predictive edge until the 80-game retrain clears.

### Sportsbook scraper coverage

| Book | Live scraper status |
|------|---------------------|
| Pinnacle | Running (closes accumulate from Oct 2026) |
| Bovada | Running |
| FanDuel | Running |
| PrizePicks | Running |
| DraftKings | IP-blocked in production |
| Caesars | IP-blocked in production |
| BetMGM | IP-blocked (live); historical closes used in Gate 1 archives |

### Free-archive coverage gap

Not in any free public archive (would require ~$30/mo Odds API):
- Full 2024-25 regular season
- Early 2025-26 (Oct 2025 – Jan 28 2026)
- 2025 NBA playoffs

The 8,360-bet historical sample is **partial-season**, not multi-season.

### NBA data feeds

- `nba_api`: 30 seasons of box / PBP / lineups — available
- `cdn.nba.com`: live boxscore + PBP — available
- ESPN injury feed + NBA official injury report — available
- Lineup-projection feed: **partial** — `nba_lineup_daemon` runs but coverage is uneven
  (some games miss starting lineups until tip)

---

## Model limitations

### Underprediction bias

All prop models predict slightly below closing line on average (~-0.45 PTS systematic
under-bias). Calibration layer is scaffolded (`src/prediction/quantile_calibration.py`) but
not yet trained on enough real-close data to apply asymmetrically per stat.

### `sim_win_prob` polarity inversion (unpatched)

`sim_win_prob` (used as `pregame_win_prob` feature) is **polarity-inverted at the source**.
`PossessionSimulator.simulate_game()` produces essentially random output (~50/50 for any
matchup); `_SIM_CACHE` freezes the first noisy result; corr(sim_win_prob, home_won) = **−0.194**.

- **v1 LGB models learned to flip internally during training** → fine in production.
- **v2/v3 in-play heads blend 85% raw inverted signal × 15% model output** → silent ROI bug.
- **Estimated CLV impact when patched: +1.5pp to +3.5pp.**
- **Why unpatched:** patch requires coordinated v1-LGB retrain cascade, gated behind that work.
- Full audit: `vault/Models/Polarity Bug Audit 2026-05-27.md` (local-only vault).

Surfacing this publicly because it's a real, measurable, unfixed bug that affects in-play CLV.

### AST edge breaks in playoffs

The one durable model edge (~+4–5% ROI on assists) is **regime-dependent and breaks in
playoffs**. The in-series PBP replay (Finals G1–G3) confirms no model edge in playoff games.
Size conservatively; do not bet AST in playoffs.

### Recency vs volume

NBA roster turnover / scheme changes make 4+ seasons of training data *worse* than 2 seasons.
Current stack uses 2023-24 + 2024-25 by default. This is intentional but means ~2 seasons of
training data — more sensitive to regime changes than a longer-window model.

### Quantile coverage

q10/q90 bands calibrated to 80% empirical coverage on training set. Real-data coverage drifts
on small-N stats (BLK/STL) where the q10 floors at zero.

---

## Open technical gaps

### Fresh-clone verify drift

- `verify_production_mae.py` crashes with an 85-vs-129 feature mismatch.
- `verify_winprob.py` reads an uncommitted cache file and fails from a fresh clone.
- Training data is gitignored.

Do not invite a live repro from a fresh clone until these are patched.

### Kelly correlation matrix unpopulated

`src/prediction/betting_portfolio.py` Kelly correlation matrix is empty. Until populated via
`python scripts/compute_kelly_corr.py`, Kelly sizing assumes independent bets — overstates
max-loss risk on correlated slates.

---

## Operational fragility

### Daemon stability

Of the 9 production daemons, **multiple go red intermittently** (Railway deploy in rollback
loop at last check; scraper heartbeats go stale on IP rotation events). Architecture is
production-ready in source; deployment ops surface is a known weakness.

Known fragile services:

- `vault_dashboard_daemon` — depends on Railway deploy health
- `clv_tracker_daemon` — requires Pinnacle archive (not yet available)
- `bov_scraper`, `fd_scraper`, `pinnacle_scraper` — go yellow on IP rotation events
- `line_move_detector` — depends on three-book consensus; partial during off-season

### Test surface gaps

- **~7,400 tests collected**; ~97–98% pass locally with a documented tail.
- Critical-path: 48/48 pass (gate1, devig, kelly, clv, calibration). In-play subset: 63/63 pass.
- Some suites fail transiently on Windows (cp1252 encoding) and RunPod (missing pyarrow on
  fresh pods). Not prediction-critical.
- No formal CI end-to-end integration gate (CV → features → predict → place); each stage has
  unit tests only.

---

## Commercial readiness

- **Zero real money placed.** By design. Gated behind Pinnacle Gate 1 + CV depth + deploy stability.
- **No SLA, no on-call rotation.** Solo build; uptime guarantees are premature.
- **API contract is unstable** — endpoints can change between releases; not versioned for external consumers.
- **Onboarding flow** is internal-only — no turnkey "drop in your bankroll, get bets" surface.

---

## Communication policy

When discussing CourtVision publicly:

- **No absolute claims.** "Guaranteed edge", "always profitable", "perfect calibration" are off-limits.
- **All public metrics dated and reproducible.** Numbers in README/ARCHITECTURE come from committed JSON
  artifacts; if a verifier disagrees with the README, the README is wrong.
- **Caveat scope.** Real-money L5-proxy gap, Pinnacle-archive gap, partial-season validation,
  CV-depth gap, and market-efficiency finding are all disclosed in headline sections — not buried
  in footnotes.
- **No real money has been placed.** Zero. Until Pinnacle Gate 1 runs.

---

*Last verified: 2026-06-11. Audit trail: [`../CHANGELOG.md`](../CHANGELOG.md).*
