# Contributing to CourtVision

> **Repository layout note (2026-09-17).** The public repository is the evidence surface: the analytics site, the documentation, the evidence artifacts, the eval gate and the sport-blind kernel. The production engine, adapters, API, operational tooling and bulk corpora (`src/`, `api/`, `domains/`, most of `scripts/` and `tests/`, `data/`) are kept in a private repository; reviewers can request read access. A path cited below that is not in this tree resolves there at tag `pre-minimize-2026-09-17`.

> The setup and test commands below describe the full private tree. On this public tree the runnable commands are the ones in [REPRODUCE.md](REPRODUCE.md).

This project combines computer vision, data engineering, statistical modeling, and agentic infrastructure. Contributions are welcome -- clarity, reproducibility, and honesty about results are the non-negotiables.

---

## How this repository was built

This repository was built by one person directing coding agents. The owner set the goals, the validation rules, and the acceptance bars; agents wrote most of the code, tests, and documentation, and a second agent reviewed each landed change against those bars. Counted from git log at commit 4f033b5a5 on 2026-10-21, 1,620 of the 6,556 commits on the public master branch (24.7%) carry a Co-Authored-By trailer naming Claude or Codex (`git rev-list --count 4f033b5a5`; `git log 4f033b5a5 -i --grep='^Co-Authored-By:.*\(Claude\|Codex\)' --format=%H | wc -l`). The true agent-authored share is higher, because older and automated commits carry no trailer. One person directed, reviewed, and is accountable for every change; most lines were not hand-written, and nothing here claims otherwise. What the owner owns is the specification, the leak-free evaluation design, and the decisions to keep, reject, or retract results.

Retractions are part of the audit trail, not something hidden. The full tree holds 157 retract or revert commits, and 23% of public commits mention fix, revert, or retract. Find them with `git log -i --grep="retract\|revert" --oneline`. The system is a calibrated forecaster, not a profit claim. Every number links to a committed artifact; start from [EVIDENCE.md](EVIDENCE.md).

Note: some non-master branches and older commits predate the public/private split (2026-09-17) and still contain earlier engine and working files; the maintained public tree is `master`, and the full engine lives in a private repository.

## Commit messages

- The first line says what changed and why, in words a reader outside the project understands.
- A register id (an `S` or `G` number such as `S317`) is only a pointer. Any commit that names one must follow it with a plain-English clause, for example `S317: verifier memo accepts the fill-realism check`, never the bare id.
- Prefer `area(scope): what changed and the measured result`.
- A `(PAPER ONLY)` tag at the end means the change touches paper-trading or calibration material only: no order was placed on any venue and nothing in it is a return figure.
- Terms and ids are defined in [docs/GLOSSARY.md](docs/GLOSSARY.md).

## Development Setup

```bash
git clone https://github.com/neeljshah/court-vision.git
cd court-vision
conda create -n basketball_ai python=3.10 -y
conda activate basketball_ai
cp .env.example .env

# product (predictor platform) -- slim install:
pip install -r requirements-predictor.txt    # or: pip install -e .  -> cv-matchup / cv-predict / cv-live
# full NBA computer-vision lineage:
# pip install -r requirements.txt

# run tests PER FILE (never the unscoped full suite -- it freezes on a local box):
python -m pytest tests/test_ingame_leak_free.py -q
```

Environment: Python 3.10.20, conda env `basketball_ai`, CUDA 11.8, RTX 4060 8GB (local); RunPod is Python 3.12. Video processing requires a CUDA-capable GPU; most tests and prediction work run CPU-only.

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

- Python 3.10.20 (local); RunPod runs 3.12
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
2. **Multi-corpus** -- calibration must improve on raw on >=2 independent OOS corpora
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


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](docs/INDEX.md) - [Home](README.md) - [Glossary](docs/GLOSSARY.md)
