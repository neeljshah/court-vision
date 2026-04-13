# CourtVision Project Plan

This is the canonical execution plan for taking CourtVision from advanced prototype to world-class system.

## Current Position

CourtVision has a real technical moat candidate:
- broadcast CV tracking transformed into spatial basketball features,
- broad model and simulation stack across game and prop surfaces,
- API and batch infrastructure already in operation.

CourtVision is not yet world-class because reliability and scientific rigor are not fully enforced as operating gates.

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
