# CourtVision Project Plan

This is the canonical execution plan for taking CourtVision from advanced prototype to world-class system.

## Current Position

CourtVision has a real technical moat candidate:
- broadcast CV tracking transformed into spatial basketball features,
- broad model and simulation stack across game and prop surfaces,
- API and batch infrastructure already in operation.

CourtVision is not yet world-class because reliability and scientific rigor are not fully enforced as operating gates.

## Vision Lock (Do Not Drift)

Primary objective for the next 12 months:

**Deliver the best NBA prediction system by measurable, reproducible evidence across game and player-prop markets.**

All roadmap choices must serve this objective directly.

### In-scope

- Prediction quality (accuracy, calibration, uncertainty quality)
- Scientific integrity (leakage controls, drift controls, reproducibility)
- Execution quality (CLV discipline, risk-aware sizing, drawdown protection)
- CV coverage improvements that lift prediction performance

### Out-of-scope until objective is met

- Multi-sport expansion
- Non-essential frontend polish
- New product lines not tied to prediction quality or execution reliability

### 12-Month North Star Targets

- Zero leakage violations in official reports
- >=95% gate pass rate for drift/calibration/contract checks
- Stable positive CLV over rolling 90-day windows
- Statistically significant holdout lift from CV-derived features
- Release-grade evidence packet generated on schedule

## Live Execution + Frontend Program (Latency-Critical)

This program defines how auto-betting and the quant dashboard operate as one system.

### Architecture Decision

- Keep 3 APIs:
  - Prediction API (model outputs)
  - Betting API (execution + risk controls)
  - Quant API (dashboard aggregation and live stream)
- Frontend reads Quant API for most views and uses controlled actions for execution controls.
- Live game path uses precomputed CV-enhanced features + live market/context data (hybrid mode).

### Latency SLOs (System-Level)

- Prediction API: p95 <= 350 ms
- Risk + sizing decision: p95 <= 200 ms
- Bet cycle (line update -> execution decision): p95 <= 900 ms
- Dashboard event freshness: <= 1.0 s for critical widgets
- Kill-switch propagation: <= 1.0 s

### Mandatory Controls

- No execution when required gates are red.
- Every strategy/config change is versioned and auditable.
- Idempotent order handling with retry policy and dedupe keys.
- Stale-data guardrails (banner + optional execution freeze when feed lag breaches threshold).

### Build Sequence

1. **Phase L1 - Foundations (2-3 weeks)**
   - Define shared event schema (`prediction.created`, `line.updated`, `bet.placed`, `gate.failed`).
   - Implement quant read models and dashboard overview endpoints.
   - Add initial latency tracing and SLO dashboards.
2. **Phase L2 - Auto-Betting Core (2-4 weeks)**
   - Implement execution queue, risk checks, order lifecycle, and kill switch.
   - Add CLV-aware execution metrics and slippage accounting.
3. **Phase L3 - Quant Dashboard Control Plane (2-4 weeks)**
   - Strategy controls (edge thresholds, max stake, correlation cap) with dry-run mode.
   - Live monitoring panels (positions, risk, model health, gate status).
4. **Phase L4 - Hardening (ongoing)**
   - Latency regression tests, chaos/failure drills, runbooks, and autoscaling policies.

## World-Class Definition

CourtVision is world-class only when all are true:
1. CV quality is measured on fixed benchmark clips with enforced pass thresholds.
2. Backtests are fully point-in-time and never synthetic in official reports.
3. Calibration/drift checks can block model promotion automatically.
4. Production serving is secure, contract-safe, observable, and reproducible.
5. Prediction quality and operational uptime sustain over full-season workload.

## Strategic Priorities (Ordered)

1. **Integrity First:** remove schema/API drift and eliminate synthetic evaluation shortcuts.
2. **Scientific Rigor:** enforce calibration, leakage prevention, uncertainty, and drift controls.
3. **Moat Compounding:** expand A/B-grade CV coverage and CV registry density.
4. **Production Hardening:** auth, CORS policy, rate limiting, observability, and SLO operations.
5. **Commercial Readiness:** transition from internal toolchain to tenant-safe API/data product.

## 3-Phase World-Class Plan

### Phase 1 (0-30 days): Trust Foundation

- Fix contract drift between database schema and async prediction writers.
- Standardize one authoritative metric source for win prob, props, and CV quality.
- Disable synthetic fallback in official backtests; fail closed on missing data joins.
- Move API runtime to production-safe defaults and tighten CORS/auth baseline.

**Exit criteria**
- Zero critical schema/contract mismatches in CI.
- Official backtest report cannot generate from synthetic placeholders.
- Protected routes require auth and pass smoke tests.

### Phase 2 (31-90 days): Scientific + Ops Hardening

- Wire calibration and drift checks into retrain/promotion gates.
- Create fixed CV benchmark set with thresholds for tracking quality.
- Add structured logs, metrics, alerts, and runbook-linked incident response.
- Add confidence/quality metadata in prediction responses.

**Exit criteria**
- Calibration, drift, and quality checks run on every promote candidate.
- CI fails on CV benchmark regression above allowed threshold.
- API error budget and latency SLOs visible on dashboard.

### Phase 3 (3-12 months): Moat + Commercial Scale

- Grow CV coverage to target depth with stable quality distribution.
- Prove incremental lift from CV features on holdout evaluation slices.
- Implement fund-grade execution controls (limits, kill switch, audit trail).
- Add API product controls: tenanting, rate tiers, SLA instrumentation.

**Exit criteria**
- CV coverage and registry targets hit for consecutive monthly windows.
- Statistically significant holdout lift from CV feature set is documented.
- External-facing API passes security and reliability launch checklist.

## Operating Cadence

- Weekly: quality review (CV, model, API reliability, risk changes).
- Monthly: roadmap checkpoint against exit criteria and blockers.
- Quarterly: external-facing benchmark pack and commercialization readiness report.

## Success Criteria

- CourtVision demonstrates sustained quality, not one-off peaks.
- Every public claim has a reproducible artifact and timestamped evidence.
- A technical buyer can review docs and immediately see execution maturity.

## Stress-Test Failure Register (Added 2026-04-13)

These are additional institutional-grade failure points identified from architecture review. Each item is now part of the active plan and should be treated as a gating risk, not optional polish.

### A) CV / Tracking Integrity Risks

1. **Silent homography drift under prolonged occlusion and camera cuts**
   - Risk: coordinates can remain numerically plausible while becoming spatially wrong.
   - Plan action: define a hard drift SLA (court-landmark reprojection error threshold + max stale-frame budget), quarantine frames exceeding SLA, and block downstream feature writes.
   - Exit proof: per-game drift report artifact with pass/fail status in CI.

2. **Identity instability through dense overlap (ID switches)**
   - Risk: player-level features and shot ownership become corrupted.
   - Plan action: add ID-switch benchmark clips, measure IDS rate and track fragmentation, fail pipeline when thresholds are exceeded.
   - Exit proof: locked benchmark suite with IDS < target across A/B-grade clips.

3. **Calibration mismatch between tracker confidence and geometric truth**
   - Risk: high confidence scores can hide bad court-space mapping.
   - Plan action: add confidence calibration curves against geometric error bins and reweight or suppress low-reliability segments.
   - Exit proof: reliability diagram and expected calibration error (ECE) per model version.

4. **Partial-game corruption leakage into training corpora**
   - Risk: bad frames contaminate model training and create hard-to-debug drift.
   - Plan action: enforce quality tags on every frame/possession and exclude low-quality segments from official training sets.
   - Exit proof: dataset manifest shows quality-filtered row counts and exclusions.

### B) Modeling / Backtest Rigor Risks

5. **Point-in-time leakage in ensemble training and evaluation**
   - Risk: models can see future-derived signals through non-time-safe joins.
   - Plan action: mandate `as_of_ts` on every feature table and enforce walk-forward training (train <= T, evaluate > T) with purged windows.
   - Exit proof: leakage audit report showing no post-cutoff fields in any fold.

6. **Synthetic or proxy evaluation paths in official metrics**
   - Risk: reported edge can look strong without market-realistic inputs.
   - Plan action: keep official backtests fail-closed when real market lines are missing; route proxy paths to "research-only" reports.
   - Exit proof: official report schema includes `data_source=real_market_only`.

7. **Weak uncertainty discipline across 90-model stack**
   - Risk: overconfident predictions inflate Kelly stakes and drawdowns.
   - Plan action: require calibrated predictive intervals and per-model uncertainty diagnostics before promotion.
   - Exit proof: interval coverage and sharpness metrics meet gate thresholds by market.

8. **Regime-shift fragility (roster changes, injuries, coaching shocks)**
   - Risk: stale models degrade fast out-of-distribution.
   - Plan action: add regime detectors and conditional retrain triggers tied to performance decay alarms.
   - Exit proof: documented retrain events with pre/post uplift and alert traces.

### C) Betting Edge / Portfolio Construction Risks

9. **Static Pearson correlation underestimates tail co-movement**
   - Risk: same-game and lineup-linked props can co-fail, causing hidden concentration.
   - Plan action: move to regime-conditional covariance with shrinkage and uncertainty haircuts for stake sizing.
   - Exit proof: stress test shows controlled drawdown under correlated downside scenarios.

10. **Execution slippage vs modeled edge**
    - Risk: model edge does not survive line movement and fill latency.
    - Plan action: enforce edge-after-slippage and CLV gates at execution time, not just post-hoc analytics.
    - Exit proof: realized CLV and execution quality dashboards by book/time bucket.

11. **Portfolio-level kill switch not tied to causal risk indicators**
    - Risk: drawdown limits alone can react too late.
    - Plan action: add proactive throttles for correlation spikes, uncertainty spikes, and market microstructure instability.
    - Exit proof: simulated shock tests trigger throttles before max drawdown breach.

### D) Platform / Product Trust Risks

12. **Data lineage and reproducibility gaps across artifacts**
    - Risk: investor or auditor cannot replay an exact result set.
    - Plan action: stamp each prediction/backtest with immutable dataset hash, model hash, and config hash.
    - Exit proof: one-command replay reproduces benchmark metrics within tolerance.

13. **Contract drift between API, DB, and offline jobs**
    - Risk: silent schema mismatch corrupts downstream consumers.
    - Plan action: contract tests as required release gate for DB writers, API payloads, and feature schemas.
    - Exit proof: CI contract suite green on every release branch.

14. **Operational blind spots during long-running GPU batch jobs**
    - Risk: throughput collapse or data loss without immediate detection.
    - Plan action: add run-level SLOs (fps, throttling, write success, checkpoint age) with alerting and auto-recovery runbooks.
    - Exit proof: on-call dashboard with alert-to-resolution drill logs.

### Program-Level Integration

- These 14 items are now mandatory quality gates under "Integrity First" and "Scientific Rigor."
- No "world-class" or investor-facing performance claim should be made unless corresponding gate evidence is attached.
- Weekly review must include a traffic-light status for each failure point and owner assignment until all are green.

## Execution Matrix (Allocator-Grade Controls)

This matrix turns the risk register into operating controls. A claim is valid only if the linked artifact exists for the same release.

| Risk Domain | Primary Metric | Gate Threshold | Owner | Cadence | Evidence Artifact |
|---|---|---|---|---|---|
| Homography drift | Court landmark reprojection error | p95 <= 2.0 ft, max <= 4.0 ft | CV Lead | Per processed game | `data/model_reports/cv_drift/<game_id>.json` |
| Tracking identity | ID switch rate (IDS / 1k frames) | <= 5 on locked benchmark suite | Tracking Lead | Weekly + release | `data/model_reports/cv_ids/benchmark_report.json` |
| Tracking reliability | Confidence calibration ECE | <= 0.05 on A/B clips | CV QA Owner | Weekly | `data/model_reports/cv_calibration/ece_report.json` |
| Dataset quality | Low-quality row contamination | 0 rows in official train manifests | Data Platform | Per training run | `data/model_reports/data_quality/train_manifest.json` |
| Leakage control | Post-cutoff feature violations | 0 violations | Research Platform | Per fold + release | `data/model_reports/leakage/leakage_audit.json` |
| Backtest realism | Official reports with proxy lines | 0 official reports | Research Platform | Release | `data/model_reports/backtests/source_audit.json` |
| Uncertainty validity | Interval coverage (90% PI) | 88-92% by market | Modeling Lead | Per retrain | `data/model_reports/uncertainty/coverage.json` |
| Regime robustness | OOS performance decay vs baseline | <= 10% relative drop before retrain trigger | Model Ops | Daily monitor | `data/model_reports/regime/drift_alerts.json` |
| Correlation risk | Stress drawdown under correlated shock | <= policy limit (8% day / 15% month) | Portfolio Lead | Daily + monthly | `data/model_reports/risk/stress_test.json` |
| Execution quality | CLV positive rate | >= 55% rolling 30 days | Trading Infra | Daily | `data/model_reports/execution/clv_30d.json` |
| Kill switch readiness | Simulated trigger latency | <= 60s detection-to-halt | Trading Infra | Monthly drill | `data/model_reports/risk/kill_switch_drill.json` |
| Reproducibility | Replay match rate | 100% metric replay within tolerance | MLOps | Release | `data/model_reports/repro/replay_check.json` |
| Contract safety | API/DB schema compatibility failures | 0 on release branch | Backend Lead | CI + release | `data/model_reports/contracts/compat_report.json` |
| Batch operations | Lost-checkpoint incidents | 0 unrecoverable runs | Pipeline Ops | Per run + weekly | `data/model_reports/pipeline/reliability.json` |

## Leakage Zero-Trust Protocol (Mandatory)

No model metric is publishable unless all checks pass:

1. **As-of contract:** every feature row carries `as_of_ts`; joins require `feature_ts <= as_of_ts`.
2. **Fold isolation:** walk-forward folds with purge windows; no overlap leakage across train/validation windows.
3. **Artifact freeze:** each fold pins dataset hash, feature config hash, model hash, and code commit SHA.
4. **Feature blacklist:** post-game or resolution-derived columns are blocked by schema policy for pre-game models.
5. **Red-team check:** independent leakage scan runs before report generation.
6. **Publish gate:** if any leakage check fails, report is marked `research-only` and cannot appear in investor materials.

## Portfolio Risk Policy (Capital Protection Standard)

Hard rules for live deployment:

- **Single-position cap:** max 4% bankroll per bet, quarter-Kelly ceiling.
- **Cluster cap:** max 10% bankroll per correlated cluster (same game/team dependency set).
- **Daily loss guard:** auto-throttle at -4%, hard halt at -8%.
- **Monthly drawdown guard:** hard halt at -15% until IC review.
- **Uncertainty throttle:** if uncertainty coverage breaches gate for 2 consecutive windows, reduce stake multipliers by 50%.
- **Correlation shock throttle:** if estimated tail co-movement exceeds policy bands, suspend same-game parlays and reduce correlated props.
- **Kill-switch authority:** automated trigger + manual override by Portfolio Lead; all events logged with RCA within 24 hours.

## Monthly IC Packet Template (Investor-Facing Evidence)

Deliver this packet monthly and before any major capital scale-up:

1. **Performance quality**
   - ROI, CLV, hit rate by market and edge decile
   - Calibration and uncertainty coverage by model family
2. **Scientific integrity**
   - Leakage audit summary (must be zero violations)
   - Data source audit (official reports must be real-market-only)
3. **CV quality**
   - Drift SLA adherence, IDS benchmark trend, registry growth
4. **Risk controls**
   - Stress test outcomes, drawdown distribution, kill-switch drill results
5. **Reproducibility + operations**
   - Replay checks, contract test pass rates, pipeline reliability incidents
6. **Action log**
   - Top regressions, corrective actions, owners, due dates, and expected impact

## 14-Day Execution Sprint (Default Operating Queue)

This section is the default "what to do next" queue. Refresh every Monday. If a task is not here, it is not a priority.

### Must-Win Outcomes (Next 14 Days)

1. **Leakage gate wiring (Owner: Research Platform, ETA: Day 5)**
   - Add `as_of_ts` enforcement check in training/backtest pipeline.
   - Produce first `leakage_audit.json` artifact on a recent fold.
2. **CV drift benchmark v1 (Owner: CV Lead, ETA: Day 7)**
   - Lock benchmark clips and emit first drift report (`p95/max`).
   - Fail training data export when drift SLA is breached.
3. **Quality-filtered dataset manifest (Owner: Data Platform, ETA: Day 9)**
   - Tag low-quality rows and exclude from official train manifests.
   - Emit `train_manifest.json` with exclusion counts.
4. **Execution quality baseline (Owner: Trading Infra, ETA: Day 11)**
   - Generate rolling CLV dashboard artifact and edge-after-slippage summary.
5. **Release-gate dry run (Owner: MLOps, ETA: Day 14)**
   - Run a full mock release and verify all required gate artifacts are present.

### Kill List (Do Not Start Until Sprint Items Are Green)

- New model families not tied to an active gate.
- UI polish or dashboard redesign work that does not improve validation or reliability.
- Large refactors without direct linkage to leakage/drift/contract/risk controls.
- New external data integrations unless they unblock one of the five must-win outcomes.

### Definition of Done (Per Task Type)

- **Build:** code path implemented and exercised locally.
- **Validate:** metric threshold or pass condition demonstrated on real data.
- **Evidence:** artifact written to `data/model_reports/` and linked in task notes.
- **Docs:** brief note added to weekly changelog or decision log.
