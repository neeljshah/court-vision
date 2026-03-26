# Contributing to CourtVision

Thank you for your interest in contributing to CourtVision. This document outlines the standards and workflow for making contributions to this project.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Issues](#reporting-issues)

---

## Code of Conduct

This project is maintained as a professional engineering codebase. Contributions should be technical, constructive, and focused on improving system performance, reliability, or clarity. Discussions about implementation decisions are welcome and encouraged.

---

## Getting Started

### Prerequisites

- Python 3.9 (via conda)
- CUDA 11.8 + cuDNN 8.9 (for tracking contributions)
- PostgreSQL 14+ (for database contributions)
- Familiarity with XGBoost, PyTorch, and the NBA API

### Setup

```bash
# Fork and clone the repository
git clone https://github.com/your-username/nba-ai-system.git
cd nba-ai-system

# Create environment
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt

# Copy environment config
cp .env.example .env

# Run tests to confirm baseline
python -m pytest tests/ -q
```

---

## Development Workflow

1. **Read the roadmap** — Check `.planning/ROADMAP.md` and `CLAUDE.md` open issues before starting work. Avoid duplicating efforts on planned phases.

2. **Create a feature branch** named after the component you're modifying:
   ```bash
   git checkout -b feat/prop-model-calibration
   git checkout -b fix/jersey-ocr-dark-uniform
   git checkout -b refactor/feature-engineering
   ```

3. **Make focused, atomic commits** — One logical change per commit. Avoid mixing refactoring with feature changes.

4. **Run the full test suite** before opening a PR:
   ```bash
   python -m pytest tests/ -q
   ```

5. **Open a PR** against the `main` branch with a clear description of what changed and why.

---

## Code Standards

### Style

- Follow **PEP 8**. Line length limit: **100 characters**.
- Use `black` for formatting: `black src/ tests/ api/`
- Use `isort` for imports: `isort src/ tests/ api/`
- Prefer explicit over implicit: no star imports.

### Structure

- **Max 300 lines per file.** Refactor into submodules if a file grows beyond this.
- Each module should have a single, clearly-defined responsibility.
- Keep `src/tracking/`, `src/prediction/`, `src/analytics/`, and `src/data/` strictly separated — no circular imports.

### Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Files | `snake_case.py` | `shot_quality.py` |
| Classes | `PascalCase` | `AdvancedFeetDetector` |
| Functions | `snake_case` | `compute_spacing_index()` |
| Constants | `UPPER_SNAKE` | `MAX_LOST = 90` |
| Model artifacts | `{name}_{version}.pkl` | `win_probability_v2.pkl` |

### Docstrings and Type Hints

All public functions and classes **must** have docstrings and type hints:

```python
def compute_spacing_index(positions: list[tuple[float, float]]) -> float:
    """Compute the convex hull area of player positions as a spacing proxy.

    Args:
        positions: List of (x, y) court coordinates for all 5 offensive players.

    Returns:
        Spacing index in square court units. Returns 0.0 if fewer than 3 players.
    """
    ...
```

### Error Handling

- Use specific exception types — avoid bare `except:` clauses.
- Log errors with `logging.getLogger(__name__)` — do not use `print()` in production code.
- All data fetching functions should have graceful fallbacks (cached result, empty return, or logged warning).

### Logging

```python
import logging
logger = logging.getLogger(__name__)

# Use appropriate levels
logger.debug("Processing frame %d", frame_num)
logger.info("Model trained: win_prob acc=%.3f", accuracy)
logger.warning("No shot dashboard data for %s — using fallback", player_name)
logger.error("Failed to connect to PostgreSQL: %s", e)
```

---

## Testing

### Running Tests

```bash
# All tests
python -m pytest tests/ -q

# Specific phase
python -m pytest tests/test_phase3.py -v

# Single test
python -m pytest tests/test_phase3.py::test_win_prob_train -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Writing Tests

- All new ML models **must** have a smoke test in `tests/test_new_models.py` or a new phase file.
- Use `monkeypatch` to avoid real NBA API calls in tests.
- Test files follow the naming pattern: `tests/test_{component}.py`.
- Keep tests fast — mock external APIs and file I/O where possible.

Example test pattern:

```python
def test_predict_props_returns_expected_keys(monkeypatch):
    """Smoke test: predict_props returns a dict with all stat keys."""
    monkeypatch.setattr("src.data.nba_stats.get_player_stats", lambda *a, **kw: MOCK_STATS)
    result = predict_props("Jayson Tatum", "MIA", "2024-25")
    assert "predictions" in result
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
        assert stat in result["predictions"]
```

---

## Submitting a Pull Request

### PR Checklist

- [ ] All existing tests pass (`python -m pytest tests/ -q`)
- [ ] New functionality has at least one test
- [ ] Docstrings and type hints added to all public functions
- [ ] No `print()` statements in production code — use `logging`
- [ ] Model artifacts (`.pkl`, `.json`) are saved to `data/models/`
- [ ] Data outputs are saved to `data/nba/` or `data/external/` with a TTL comment
- [ ] `CLAUDE.md` open issues updated if the PR resolves one

### PR Title Format

```
feat: add OSNet deep re-ID to AdvancedFeetDetector
fix: jersey OCR voting buffer off-by-one on frame reset
refactor: extract spacing_index into spatial_utils.py
test: add smoke tests for Phase 4.5 betting models
docs: update roadmap with Phase 6 game processing plan
```

### PR Description Template

```markdown
## What

Brief description of the change.

## Why

What problem does this solve? Reference open issue if applicable.

## How

Key implementation decisions. Why this approach over alternatives.

## Testing

How was this tested? What edge cases were considered?

## Performance Impact

If relevant: before/after metrics, FPS impact, model accuracy delta.
```

---

## Reporting Issues

Use the GitHub Issues tracker. Include:

- **Issue ID** (use next `ISSUE-0XX` from `CLAUDE.md` if none exists)
- **What happened** vs **what was expected**
- **Steps to reproduce** with exact commands
- **System info**: OS, GPU, conda env version
- **Relevant log output** (from `data/*.log` or console)

Label issues as: `bug`, `performance`, `data`, `model`, `tracking`, or `api`.

---

## Areas Most Needing Contribution (March 2026)

- **Phase F (NEXT):** Full-game video processing pipeline — `scripts/full_game_pipeline.py`
- **Phase G:** Cloud GPU processing (RunPod A100) — 50–100 full games
- **HSV re-ID:** Jersey confusion on similar-colored uniforms (ISSUE-005 partial fix exists)
- **Win probability:** Game prediction model needs real-time feature pipeline
- **Analytics dashboard:** Streamlit dashboards not yet connected to live predictions
