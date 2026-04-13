# Contributing to CourtVision

Thanks for contributing. This project combines computer vision, data engineering, and sports modeling, so clarity and reproducibility are required for every change.

## Principles

- Keep changes focused and testable.
- Prefer incremental improvements over broad rewrites.
- Preserve pipeline reliability and data quality first.
- Document any behavior changes that affect outputs or API contracts.

## Development Setup

```bash
git clone https://github.com/neeljshah/nba-ai-system.git
cd nba-ai-system
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt
cp .env.example .env
python -m pytest tests/ -q
```

## Branch and PR Workflow

1. Create a focused branch from your main working branch.
2. Implement one logical change per PR.
3. Add or update tests for behavior changes.
4. Update relevant docs (`README.md`, `PLAN.md`, `docs/`) when interfaces or workflows change.
5. Open a PR with:
   - problem statement
   - implementation summary
   - validation evidence (tests, benchmarks, sample output)

## Code Standards

- Python 3.9
- Type hints on public functions
- Docstrings for public classes/functions
- Avoid hidden side effects and implicit globals
- Prefer explicit error handling over blanket exception swallowing
- Keep files manageable; split modules when responsibilities diverge

## CV and Pipeline Rules

- Headless operation only for video processing (no `cv2.imshow`).
- Do not regress pipeline throughput without benchmark evidence.
- Any tracking logic changes should include:
  - quality validation against representative clips
  - notes on expected runtime impact

## API Contract Rules

- Treat endpoint request/response shapes as contracts.
- Avoid breaking response keys without versioning or migration notes.
- Add integration tests when router-to-model interfaces are modified.

## Testing Expectations

Run at minimum:

```bash
python -m pytest tests/ -q
```

For changes in high-risk areas (tracking, orchestration, contracts), include targeted tests and describe validation in PR notes.

## Repo Hygiene

- Avoid adding one-off root files when they belong in `docs/`, `scripts/`, or archived directories.
- Prefer canonical paths and avoid duplicate module surfaces.
- Do not commit secrets, credentials, or large generated artifacts.

## Issue Reports

When filing issues, include:

- observed behavior
- expected behavior
- reproduction steps
- relevant logs or traceback excerpts
- environment details (OS, Python, GPU if relevant)
