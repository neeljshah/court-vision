# Known Limitations

Concrete operational state of CourtVision as of **2026-05-27**. This file is kept honest so that the README and ARCHITECTURE don't have to litter their headline sections with caveats. Audit trail of fixes: [`../CHANGELOG.md`](../CHANGELOG.md). Live operational state: [`CLAUDE-state.md`](CLAUDE-state.md).

The philosophy: surface the gaps explicitly so external readers (interviewers, collaborators, future contributors) can calibrate trust. Nothing is hidden; nothing is sugar-coated.

---

## Validation gaps

### Pinnacle Gate 1 — NOT YET RUN (sharp-book CLV)

No historical Pinnacle closing-line archive exists publicly. The Pinnacle scraper daemon (`scripts/pinnacle_scraper.py`) accumulates closes from Oct 2026 onward; the first real sharp-book CLV reading is therefore ~2 months out from any production deployment. Until that gate runs, no real-money execution is justified.

What we *do* have at real closes (8,360 walk-forward bets, partial-season): DK / FanDuel / MGM / BetRivers archives via `reisneriv/NBA_Player_Props` (2024 playoffs) and `benashkar/nba_gambling` (2025-26 mainline). Both committed to repo. Consolidated report: [`../data/models/gate1_results_summary.json`](../data/models/gate1_results_summary.json).

### L5 line proxy ≠ real closes

The 90,846-bet in-play backtest settles against an **L5 rolling-average line proxy**, not real Pinnacle/DK closes. L5 lines are softer than sharp closes; paper ROI compresses materially when re-evaluated against real lines. Best estimate of compression: **+54% paper → +15–25% real**. The +54% is a model-quality ceiling, not a deployment forecast.

### Free-archive coverage gap

What's NOT in any free public archive (would require $30/mo Odds API):
- Full 2024-25 regular season
- Early 2025-26 (Oct 2025 – Jan 28 2026)
- 2025 NBA playoffs

The 8,360-bet historical sample is **partial-season**, not multi-season.

---

## Data coverage limits

### CV coverage

- **85 games tracked** in `data/tracking/` (YOLOv8 + SIFT + OSNet output)
- **7 games with full feature extraction** (defender_distance / spacing / fatigue computed end-to-end)
- **Target: 80 CLEAN** for the production CV-feature gate (Tier 3/4 model retrain)
- Some games have `ball_valid_pct=0%` because `ball_track_suspended` stays True — known fix on the queue, after the 80-game push
- Per-player attribution at 4% accuracy (slot identities not stable across long occlusions); aggregate team-level / position-level CV features are ship-ready

### Sportsbook scraper coverage

| Book | Live scraper status |
|------|---------------------|
| Pinnacle | ✅ Running (closes accumulate from Oct 2026) |
| Bovada | ✅ Running |
| FanDuel | ✅ Running |
| PrizePicks | ✅ Running |
| DraftKings | 🔴 IP-blocked |
| Caesars | 🔴 IP-blocked |
| BetMGM | 🔴 IP-blocked (live); historical closes used in Gate 1 archives |

DK/Caesars/MGM-equivalent coverage at sharp closes is partial — the historical 8,360-bet archive used DK/FD/MGM/BetRivers closes that were publicly accessible.

### NBA data feeds

- `nba_api`: 30 seasons of box / PBP / lineups ✅
- `cdn.nba.com`: live boxscore + PBP ✅
- ESPN injury feed ✅
- NBA official injury report ✅
- Lineup-projection feed: **partial** — `nba_lineup_daemon` runs but coverage is uneven (some games miss starting lineups until tip)

---

## Model limitations

### Underprediction bias

All 7 prop models predict slightly below closing line on average. Calibration layer is scaffolded (`src/prediction/quantile_calibration.py`) but not yet trained on enough real-close data to apply asymmetrically per stat. PTS specifically loses **−8.62% ROI** at sharp 2025-26 DK/FD/MGM closes; calibration is the next pin.

### Quantile coverage

q10/q90 quantile bands calibrated to **80% empirical coverage** on the training set. Real-data coverage drifts on small-N stats (BLK/STL) where the q10 floors at zero. Asymmetric calibration branch handles this case; not all consumers route through it.

### `sim_win_prob` polarity inversion (unpatched)

`sim_win_prob` (used as `pregame_win_prob` feature) is **polarity-inverted at the source**. `PossessionSimulator.simulate_game()` is essentially noise (~50/50 for any matchup); `_SIM_CACHE` freezes the first noisy result; corr(sim_win_prob, home_won) = **−0.194**.

- **v1 LGB models learned to flip internally during training** → fine in production.
- **v2/v3 in-play heads blend 85% raw inverted signal × 15% model output** → silent ROI bug.
- **Estimated CLV impact when patched: +1.5pp to +3.5pp.**
- **Why unpatched:** patch requires coordinated v1-LGB retrain cascade, gated behind that work.
- Full audit: `vault/Models/Polarity Bug Audit 2026-05-27.md` (gitignored vault — the audit notes are local-only).

Surfacing this publicly because it's a real, measurable, unfixed bug that affects in-play CLV. Hiding it would compromise the "all caveats disclosed in headline sections" policy below.

### CV signal at scale — unproven

The defender_distance / spacing / fatigue features are computed correctly on the 7 full-feature games, but **whether they improve prop MAE materially at the 80-game gate is unverified**. The current Tier 3/4 model retrain is gated on hitting 80 CLEAN tracked games.

### Recency vs volume

NBA roster turnover / scheme changes / rule emphasis shifts make 4+ seasons of training data *worse* than 2 seasons. The current stack uses 2023-24 + 2024-25 by default. This is a feature, not a limitation — but it means the model has only 2 seasons of training data and is correspondingly more sensitive to a regime change.

---

## Operational fragility

### Daemon stability

Of the 9 production daemons, **multiple go red intermittently** (last morning brief: 13/14 daemons red — Railway deploy in rollback loop, scraper heartbeats stale). The architecture is production-ready in source; the deployment ops surface is uneven and a known weakness. Tracking issues:

- `vault_dashboard_daemon` — depends on Railway deploy health
- `clv_tracker_daemon` — requires Pinnacle archive (not yet available)
- `bov_scraper`, `fd_scraper`, `pinnacle_scraper` — go yellow on IP rotation events
- `line_move_detector` — depends on three-book consensus, partial coverage during off-season

### Railway deploy

The Railway production deploy is currently in a post-health-check rollback loop. Source is correct; deploy isn't serving live. Workaround: run the live engine locally (`python -m src.prediction.live_engine_v2 --serve`). Tracking note: `vault/Reports/MORNING_HANDOFF_2026-05-27.md`.

### `kelly_corr` not populated

`src/prediction/betting_portfolio.py` Kelly correlation matrix is empty. Workflow to populate: `python scripts/build_residuals.py` then `python scripts/compute_kelly_corr.py`. Until then, Kelly sizing assumes independent bets within a slate — overstates max-loss risk on correlated slates.

---

## Test surface gaps

- **4,100+ tests collected.** Critical-path: 48/48 pass (gate1, devig, kelly, clv, calibration). In-play subset: 63/63 pass.
- **Some test suites fail transiently** on Windows (cp1252 encoding) and RunPod (missing pyarrow on fresh pods). Failures are tracking-suite + transient infra, not prediction-critical.
- **No formal CI gate yet** for end-to-end pipeline (CV → features → predict → place). Each stage has unit tests; the integration gate runs locally on `swish_demo.py` but is not part of the PR check.

---

## Commercial readiness

- **Zero real money placed.** By design. Gated behind Pinnacle Gate 1 + CV depth + production deploy stability.
- **No SLA, no on-call rotation.** This is a solo build; uptime guarantees would be premature.
- **API contract is unstable** — `api/main.py` endpoints can change between releases. Not yet versioned for external consumers.
- **Onboarding flow** is internal-only — there's no turnkey "drop in your bankroll, get bets" surface.

---

## Communication policy

When discussing CourtVision publicly:

- **No absolute claims.** "Guaranteed edge", "always profitable", "perfect calibration" are off-limits.
- **All public metrics dated and reproducible.** Numbers in README/ARCHITECTURE come from committed JSON (`data/models/gate1_results_summary.json`, `quantile_pergame_metrics.json`, `win_prob_metrics.json`); if a verifier disagrees with the README, the README is wrong.
- **Caveat scope.** Real-money L5-proxy gap, Pinnacle-archive gap, partial-season validation, and CV-depth gap are all disclosed in headline sections — not buried in footnotes.
- **No real money has been placed.** Zero. Until Pinnacle Gate 1 runs.

---

*Last verified: 2026-05-28. Audit trail: [`../CHANGELOG.md`](../CHANGELOG.md).*
