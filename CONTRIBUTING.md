# Contributing to CourtVision

This project combines computer vision, data engineering, statistical modeling, and agentic infrastructure. Contributions are welcome -- clarity, reproducibility, and honesty about results are the non-negotiables.

---

## Development Setup

```bash
git clone https://github.com/neeljshah/court-vision.git
cd court-vision
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
cp .env.example .env

# product (predictor platform) -- slim install:
pip install -r requirements-predictor.txt    # or: pip install -e .  -> cv-matchup / cv-predict / cv-live
# full NBA computer-vision lineage:
# pip install -r requirements.txt

# run tests PER FILE (never the unscoped full suite -- it freezes on a local box):
python -m pytest tests/test_ingame_leak_free.py -q
```

Environment: Python 3.9, conda env `basketball_ai`, CUDA 11.8, RTX 4060 8GB (local). Video processing requires a CUDA-capable GPU; most tests and prediction work run CPU-only.

---

## Principles

- Keep changes focused and testable -- one logical change per PR.
- Prefer incremental improvements over broad rewrites.
- Preserve pipeline reliability and data quality above everything else.
- Document behavior changes that affect outputs or API contracts.
- **Validate honestly.** A correct rejection is not a failure; it is the gate working. See [docs/research/validation-methodology.md](docs/research/validation-methodology.md).

---

## Branch and PR Workflow

1. Create a focused branch from your main working branch.
2. Implement one logical change per PR.
3. Add or update tests covering the changed behavior.
4. Update relevant docs (`README.md`, `CHANGELOG.md`, `docs/`) when interfaces or workflows change.
5. Open a PR with:
   - **Problem statement** -- what is broken or missing
   - **Implementation summary** -- what you changed and why
   - **Validation evidence** -- test results, benchmark numbers, or sample output; if a metric changed, show walk-forward numbers, not single-split

---

## Code Standards

- Python 3.9
- Type hints on all public functions
- Docstrings for public classes and functions
- Avoid hidden side effects and implicit globals
- Prefer explicit error handling over blanket exception swallowing
- Keep files under 300 LOC; split modules when responsibilities diverge

---

## CV and Pipeline Rules

- Headless operation only for video processing (`--no-show`; never `cv2.imshow`)
- Do not regress pipeline throughput without benchmark evidence
- `_VRAM_FLUSH_INTERVAL` in `src/pipeline/unified_pipeline.py` **must remain 3000** -- setting it to 100 causes GPU OOM
- Tracking changes require quality validation against representative clips, with notes on runtime impact

---

## Validation Rules (ML / Prediction Changes)

Any change that affects model output, features, or prediction logic must clear the ship gate:

1. **Walk-forward CV** -- expanding window; all folds must improve; `max_train_date < min_test_date` asserted per fold
2. **Multi-corpus** -- calibration must beat raw on >=2 independent OOS corpora
3. **Truncation-invariance** -- features at time T are byte-identical with or without future events
4. Report walk-forward numbers in the PR, not single-split numbers alone
5. If a result does not clear the gate, document the rejection honestly -- do not drop it or bury it

---

## API Contract Rules

- Treat endpoint request/response shapes as contracts
- Avoid breaking response keys without versioning or a migration note
- Add integration tests when router-to-model interfaces are modified

---

## Testing Expectations

Run tests **per file** -- the unscoped full-suite collection (`pytest tests/`)
freezes on a local box, so never run it. Run the file(s) covering your change,
for example:

```bash
python -m pytest tests/test_ingame_leak_free.py -q
python -m pytest tests/test_devig.py -q
```

For changes in high-risk areas (tracking, orchestration, model contracts,
decision engine, predictor adapters), include targeted tests and describe
validation in the PR notes. Cite the relevant per-file predictor / proof tests
that pass for your change; do not submit a PR that reduces the passing count in
the files you touched without explicit justification. The full-pass accounting,
including the documented failing tail, lives in `docs/JOB_EVIDENCE_PACKET.md` and
`docs/KNOWN_LIMITATIONS.md`.

---

## Repo Hygiene

- Avoid one-off root files; use `docs/`, `scripts/`, or appropriate `src/` subdirectories
- Prefer canonical paths; avoid duplicate module surfaces
- Never commit secrets, credentials, model weights, data parquets, or large generated artifacts
- `data/`, `vault/`, `.planning/`, and `data/models/*.pkl` are gitignored -- keep it that way

---

## Issue Reports

When filing issues, include:

- Observed behavior
- Expected behavior
- Reproduction steps (minimal command that triggers the problem)
- Relevant logs or traceback excerpts
- Environment details: OS, Python version, GPU if relevant

---

*Last verified: 2026-06-15*
