# Night-loop experiment backlog

The loop runs the FIRST unchecked `[ ]` item, records a verdict to RESULTS.md, checks it off `[x]`,
records any CANDIDATE/notable finding to ~/.claude memory, then runs the next. When the queue gets low
(<3 unchecked), the loop APPENDS new experiments (more sweeps, finer grids around any candidate, new
signal measurements) — it never stops improving the system. Discipline: NEVER auto-apply a param change
to the engine; record candidates for human review. Score RMSE/bias+coverage, not MAE-only. Keep prints ascii.

Format: `- [ ] ID | <shell command from repo root> | <what it tests / why>`

## Parameter tuning sweeps (fast GPU, ~2-4 min each)
- [x] S01 | python scripts/team_system/nightloop/sweep.py --const RECENCY_W --values 0.3,0.45,0.6,0.75,0.9 | recency blend weight (playoff bias vs MAE)
- [x] S02 | python scripts/team_system/nightloop/sweep.py --const RIM_ANCHOR_SLOPE --values 0.005,0.007,0.009,0.011 | anchor rim-defense strength
- [x] S03 | python scripts/team_system/nightloop/sweep.py --const PERIM_ANCHOR_SLOPE --values 0.002,0.004,0.006 | anchor perimeter-defense strength
- [x] S04 | python scripts/team_system/nightloop/sweep.py --const DEF_RIM_SLOPE --values 0.0018,0.0024,0.0030,0.0036 | per-shot rim suppression
- [x] S05 | python scripts/team_system/nightloop/sweep.py --const DEF_PERIM_SLOPE --values 0.0009,0.0013,0.0017 | per-shot perimeter suppression
- [x] S06 | python scripts/team_system/nightloop/sweep.py --const DISP_BASE --values 0.14,0.20,0.26 | dispersion base sigma (coverage)
- [x] S07 | python scripts/team_system/nightloop/sweep.py --const DISP_MINUTE --values 0.45,0.60,0.75 | dispersion minute sigma (bench coverage)
- [x] S08 | python scripts/team_system/nightloop/sweep.py --const REF_RIM_D --values 62,65,68 | anchor rim-D centering
- [x] S09 | python scripts/team_system/nightloop/sweep.py --const REF_PERIM_D --values 62,65,68 | anchor perim-D centering
- [x] S10 | python scripts/team_system/nightloop/sweep.py --const P_STEAL_ON_TOV --values 0.45,0.55,0.65 | steal-credit share on forced TO

## Regression / validation guards (run periodically; confirm board stays green)
- [x] G01 | python scripts/team_system/validate_fast_sim.py | fidelity + defense + GPU==CPU board
- [x] G02 | python -m pytest tests/test_sim_engine.py -q | pytest regression (Brunson 26.1 anchor, coherence, rho)
- [x] G03 | python scripts/team_system/walkforward_backtest.py | leak-free defense walk-forward (team MAE/RMSE)
- [x] G04 | python scripts/team_system/walkforward_recency.py | leak-free recency vs flat (playoff bias)
- [x] G05 | python scripts/team_system/calibration_sim.py --minmin 25 | distribution calibration (coverage, team bias)
- [x] G06 | python scripts/team_system/measure_ft_defense.py | re-validate FT-defense signal (bias correction)
- [x] G07 | python scripts/team_system/measure_clutch.py | re-validate clutch trait
- [x] G08 | python scripts/team_system/backtest_sim_accuracy.py | anchor-strength sweep (raw vs anchored)

## New-signal explorations (measure-first; build a quick test, validate leak-free, record verdict)
- [x] N01 | python scripts/team_system/nightloop/measure_signal.py rest_days | does days-of-rest move shooting (team-identity, leak-free)?
- [x] N02 | python scripts/team_system/nightloop/measure_signal.py upper_tail | star >q90 over-rate: size a right-skew dispersion fix
- [x] N03 | python scripts/team_system/nightloop/measure_signal.py paint_rate_def | opponent paint-rate forced (shot-location defense, beyond make%)
- [x] N04 | python scripts/team_system/nightloop/measure_signal.py three_var | team 3PA-volume variance regime (live-or-die shooting)
- [x] N05 | python scripts/team_system/nightloop/measure_signal.py assist_2nd | 2nd-order assist network depth (who-feeds-the-feeder)

## Bias/coverage-aware re-sweeps (added 06-07; sweep.py verdict now surfaces min-|bias| + best-coverage)
- [x] S11 | python scripts/team_system/nightloop/sweep.py --const RECENCY_W --values 0.6,0.7,0.8,0.9 | recency high-range: does more recency cut playoff PLAYER+TEAM bias further (recency's real metric, not MAE)?
- [x] S12 | python scripts/team_system/nightloop/sweep.py --const REF_RIM_D --values 64,65,66,67,68 | rim-D centering: S08 MAE-best was 68 (noise) -- check if it actually moves player-pts BIAS
- [x] S13 | python scripts/team_system/nightloop/sweep.py --const DISP_BASE --values 0.14,0.20,0.26,0.32 | dispersion base: COVERAGE is the real metric (MAE is flat by design -- means re-pinned)
- [x] S14 | python scripts/team_system/nightloop/sweep.py --const DISP_MINUTE --values 0.45,0.60,0.75,0.90 | bench dispersion: COVERAGE of sub-20mpg players (MAE flat by design)
- [x] S15 | python scripts/team_system/nightloop/sweep.py --const USAGE_CONCENTRATION --values 1.1,1.25,1.4,1.55 | usage concentration: bias/cov around seed-optimal 1.25 (star routing)
- [x] S16 | python scripts/team_system/nightloop/sweep.py --const RIM_ANCHOR_SLOPE --values 0.005,0.007,0.009,0.011 | anchor rim-D slope: S02 MAE-best 0.005 (noise) -- check BIAS direction
- [x] S17 | python scripts/team_system/nightloop/sweep.py --const REF_PERIM_D --values 64,65,66,67,68 | perim-D centering finer + bias/cov view (S09 was MAE-only on 62/65/68); perim analog of S12
- [x] S18 | python scripts/team_system/nightloop/sweep.py --const PERIM_ANCHOR_SLOPE --values 0.002,0.004,0.006,0.008 | anchor perim slope + bias/cov view (S03 was MAE-only) -- does it move player BIAS?
- [x] S19 | python scripts/team_system/nightloop/sweep.py --const MIN_MPG --values 4,6,8 | rotation-floor sensitivity (untested structural constant): does eligibility cutoff move starter bias/coverage?

## Periodic stability guards (sweep space exhausted -- ride the night confirming the board stays green)
- [x] G09 | python scripts/team_system/validate_fast_sim.py | board re-check: fidelity + defense + GPU==CPU
- [x] G10 | python -m pytest tests/test_sim_engine.py -q | pytest regression re-check (anchor/coherence/rho)
- [x] G11 | python scripts/team_system/calibration_sim.py --minmin 25 | calibration re-check (coverage near 80% on betting-relevant pop)
- [x] G12 | python scripts/team_system/validate_fast_sim.py | board re-check (periodic): fidelity + defense + GPU==CPU
- [x] G13 | python -m pytest tests/test_sim_engine.py -q | pytest regression re-check (periodic)
- [x] G14 | python scripts/team_system/walkforward_recency.py | leak-free recency re-check (periodic)
- [x] G15 | python scripts/team_system/calibration_sim.py --minmin 25 | calibration re-check (periodic)
- [x] G16 | python scripts/team_system/validate_fast_sim.py | board re-check (periodic): fidelity + defense + GPU==CPU
- [x] G17 | python -m pytest tests/test_sim_engine.py -q | pytest regression re-check (periodic)

## Deep-analysis harnesses (built 06-07 active session; re-run on FRESH data after each Finals game via update.py)
## Findings recorded in memory project_monte_carlo_engine_2026-06-06; NONE applied to the engine (human review).
- [ ] A01 | python scripts/team_system/nightloop/measure_skew.py | upper-tail = minutes-conditioning artifact (reg vs playoff bias, oracle-minutes); REFUTED as a dispersion defect
- [ ] A02 | python scripts/team_system/nightloop/measure_noise.py --seeds 6 | MC noise floor (pts-MAE 2sigma ~0.002) -> confirms sweep deltas are subsample-overfit not signal
- [ ] A03 | python scripts/team_system/nightloop/measure_corr.py --stride 1 --ming 12 | same-player cross-stat joint: pts-reb UNDER-correlated (+0.19 real vs +0.03 sim) = CANDIDATE
- [ ] A04 | python scripts/team_system/nightloop/measure_teammates.py --stride 1 --ming 15 | teammate pts-pts joint = CALIBRATED (confirms canary), not a candidate
- [ ] A05 | python scripts/team_system/nightloop/measure_corr_fix.py --stride 1 --ming 12 | sandbox: shared shock sigma~0.15 fixes same-player under-correlation (fix sized, not applied)
- [ ] A06 | python scripts/team_system/nightloop/measure_winprob.py --stride 1 | sim pregame win-prob UNDER-CONFIDENT for elite teams; isotonic recal fixes OOS (Brier 0.226->0.203) = CANDIDATE
- [ ] A07 | python scripts/team_system/nightloop/measure_corr.py --stride 1 --ming 20 | robustness: same-player under-correlation restricted to well-sampled players (>=20 games)
