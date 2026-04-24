# Known Limitations

This document lists current known constraints to keep public communication accurate and trustworthy.

## Product Stage

- CourtVision is an advanced in-progress system, not a fully finished commercial product.
- Some roadmap components are still under active implementation and hardening.

## Data and Coverage Constraints

- CV coverage quality is uneven across historical video sources.
- Registry density for CV-identified player-game records is still growing.
- Some feature/model quality varies by market and data availability.

## Modeling Constraints

- Not all prediction surfaces have equally strong signal quality.
- Certain prop targets remain harder to model robustly than others.
- Performance can vary during regime shifts (injuries, roster moves, coaching changes).

## Operational Constraints

- Full-speed CV processing depends on GPU availability and tuned runtime settings.
- Long-running batch workflows require strict persistence/sync discipline.
- Some workflows are currently optimized for internal operation rather than turnkey external onboarding.

## Interface and Commercial Readiness Constraints

- Public API and dashboard capabilities are present but still evolving toward hardened external SLAs.
- Contract stability, release gates, and observability are actively being strengthened.

## Communication Policy

- Avoid absolute claims ("perfect", "guaranteed edge", "always profitable").
- Use reproducible, dated evidence when presenting model quality.
- Disclose scope and caveats for any external-facing metric.

