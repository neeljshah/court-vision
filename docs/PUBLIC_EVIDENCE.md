# Public Evidence Packet

This document is the public-facing proof summary for CourtVision.

Use it for partner, recruiter, and investor conversations that need quick, reproducible signal quality evidence.

## Current Snapshot

- System scope: computer vision tracking + feature engineering + NBA data enrichment + model stack + simulation + API.
- Development stage: advanced build and validation.
- Goal: demonstrate leakage-safe, reproducible prediction quality and reliable execution controls.

## What Is Measured

The following are the primary quality dimensions used in public claims:

- Out-of-sample model performance (accuracy/error metrics by market).
- Calibration and uncertainty quality.
- CV-derived feature lift versus non-CV baselines.
- Execution quality proxies (including CLV and slippage-aware evaluation when available).
- Reliability metrics for long-running processing and serving.

## Evidence Standards

A claim is considered publishable only when:

1. It is generated from reproducible pipeline runs.
2. Inputs are point-in-time consistent for the target task.
3. The report includes timestamp/version context.
4. Known caveats are disclosed in `docs/KNOWN_LIMITATIONS.md`.

## Reproducibility Checklist

Before sharing any metric externally, verify:

- Test suite passes in CI.
- Data path is explicit (real or research-only).
- Evaluation split and time window are specified.
- Metric definitions are included.
- Artifacts are retained (report files, configs, commit SHA).

## Current Public Positioning

- CourtVision should be presented as an in-progress but operationally serious intelligence engine.
- External statements should emphasize rigor and trajectory, not "finished product" claims.
- "Differentiated by proprietary spatial CV features" is valid; avoid absolute superiority claims without benchmark artifacts.

## Recruiter/Partner Summary

If you need a short summary:

- The system is end-to-end and production-minded.
- The moat is CV-derived spatial signal not present in commodity datasets.
- The roadmap is governance-based with reliability and scientific gates.

