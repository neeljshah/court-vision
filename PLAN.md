# CourtVision Project Plan

This plan is the working blueprint to finalize CourtVision for public showcase quality while preserving its research velocity.

## Current State

CourtVision already delivers meaningful end-to-end capability:

- GPU-based CV pipeline for broadcast video tracking and event extraction.
- Multi-source data enrichment and feature engineering for model inputs.
- Broad prediction surface across game and player contexts.
- FastAPI serving layer with multiple prediction and analytics routers.
- Large, active test suite and operational batch scripts for seasonal workflows.

The project demonstrates strong technical breadth and real domain depth, especially in the CV + sports intelligence overlap.

## Internal Audit Summary: Key Gaps

### Reliability and Error Handling

- Heavy use of broad `except Exception` paths can hide degraded outputs.
- Degrade-gracefully behavior is useful, but success criteria are not always explicit.
- Some API responses depend on fallback defaults without clear quality metadata.

### API and Contract Consistency

- Router-to-model interface drift risk exists in parts of the API/model boundary.
- Endpoint schemas are not consistently centralized/versioned.
- Mixed compatibility layers and re-export patterns increase maintenance overhead.

### Performance and CV Throughput

- Core performance work is active, but benchmark enforcement is uneven.
- Stage-level latency visibility can be improved for decode/detect/re-ID/OCR.
- Opportunity remains to formalize regression checks before merge/deploy.

### Security and Production Hardening

- CORS posture is currently permissive.
- Container startup uses development-style settings in default paths.
- API-level auth/rate-limit strategy is not uniformly enforced.

### Documentation and Discoverability

- Rich internal docs exist, but public-facing architecture and operation docs are fragmented.
- Duplicate/legacy artifacts in root and parallel folders reduce clarity.
- New contributor onboarding can be more explicit and role-oriented.

### Repository Hygiene

- Multiple folders appear to represent historical experiments, prototypes, or alternate fronts.
- Root contains one-off operational text files better moved under structured `docs/ops/` or archived.
- Public showcase readiness requires clearer "source of truth" paths.

## Roadmap (Prioritized Upcoming Features)

## Phase 1: Showcase Foundation (Immediate)

- Publish clean narrative docs (`README.md`, `PLAN.md`, `CONTRIBUTING.md`).
- Establish canonical architecture map and ownership boundaries by directory.
- Add explicit quality bar for "public showcase ready" build status.

## Phase 2: Stability and Contract Safety

- Normalize API contracts using shared schema models.
- Add integration tests that validate real router-model signatures (not only mocks).
- Introduce standardized error envelopes for prediction endpoints.

## Phase 3: Security and Runtime Hardening

- Tighten CORS and environment-specific runtime defaults.
- Add authentication strategy for non-public/internal endpoints.
- Introduce request throttling and structured access logs.

## Phase 4: Data and Model Governance

- Add model metadata manifests: version, feature schema hash, data window.
- Promote drift and data-quality checks into hard release gates.
- Formalize retrain/promotion/rollback workflows.

## Phase 5: CV Performance and Operational Excellence

- Instrument stage-level timing and bottleneck diagnostics.
- Enforce repeatable benchmark suite for pipeline performance regressions.
- Standardize long-run job health metrics and artifact sync safeguards.

## Phase 6: Repository Reorganization

- Consolidate duplicate/legacy paths and archive non-essential artifacts.
- Standardize import paths and remove avoidable path hacks.
- Group scripts by purpose (`ingest`, `train`, `batch`, `validate`, `ops`).

## Proposed Clean Structure (Target)

```text
api/
  main.py
  routers/
  schemas/
  deps/
  middleware/
src/
  tracking/
  pipeline/
  data/
  ingest/
  fusion/
  features/
  prediction/
  simulation/
  analytics/
scripts/
  ingest/
  train/
  batch/
  validate/
  ops/
docs/
  architecture/
  api/
  operations/
  models/
  roadmap/
tests/
infra/
  docker/
  nginx/
```

## Tech Specs (Professional Overview)

- Language: Python 3.9
- CV/ML: PyTorch, YOLOv8, OpenCV, EasyOCR, scikit-learn, XGBoost, LightGBM
- Serving: FastAPI + Uvicorn
- Data systems: PostgreSQL, Redis
- Packaging/runtime: Docker, docker-compose
- Frontend surfaces: React-based dashboards and prototype UIs
- Quality controls: pytest suite, planned contract/integration hardening

## Execution Notes

- No destructive cleanup should occur without preserving an archive path.
- Reorganization should happen in small, verifiable phases to reduce breakage.
- Each reorg phase must include import updates and test checkpoints.

## Success Criteria

- Clear public showcase narrative and architecture documentation.
- Reduced repository ambiguity (single source of truth paths).
- Higher confidence in runtime behavior through contract and quality gates.
- Cleaner contributor experience with predictable workflows.
