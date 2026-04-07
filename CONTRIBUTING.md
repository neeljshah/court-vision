# Contributing

## Setup

```bash
git clone https://github.com/neeljshah/nba-ai-system.git
cd nba-ai-system
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt
cp .env.example .env
python -m pytest tests/ -q
```

## Pull Requests

1. Branch from `master`: `git checkout -b feat/your-feature`
2. Keep changes focused — one logical change per PR
3. All tests must pass: `make test`
4. Update `CLAUDE.md` open issues if your change closes one
5. No new files without a clear reason; prefer editing existing modules

## Code Style

- Python 3.9, PEP 8, max line length 120
- Type hints on all public functions
- Docstrings on classes and non-trivial functions
- Max 300 lines per file — split if needed
- No `cv2.imshow` or interactive display calls; pipeline runs headless

## What Not to Touch

- `src/tracking/` changes require re-running benchmarks (`make pipeline`)
- `data/models/` — model artifacts are gitignored; train locally
- `vault/` and `.planning/` — internal knowledge base, not part of the public interface

## Reporting Issues

Open an issue with: observed behavior, expected behavior, reproduction steps, and relevant log output.
