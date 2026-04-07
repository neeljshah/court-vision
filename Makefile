.PHONY: test lint train predict pipeline api

PYTHON = python
PYTEST = python -m pytest
UVICORN = uvicorn

# Run test suite (excludes GPU-dependent tracking tests)
test:
	$(PYTEST) tests/ -q --ignore=tests/test_tracking.py

# Lint with flake8 (max line length 120, skip noqa)
lint:
	flake8 src/ api/ scripts/ --max-line-length=120 --exclude=__pycache__

# Train all Tier 1 models
train:
	$(PYTHON) src/prediction/win_probability.py --train
	$(PYTHON) src/prediction/player_props.py --train
	$(PYTHON) src/prediction/xfg_model.py --train

# Predict tonight's slate
predict:
	$(PYTHON) scripts/daily_pipeline.py

# Run full game pipeline (requires video + GPU)
pipeline:
	$(PYTHON) scripts/run_phase_g.py

# Start FastAPI server
api:
	$(UVICORN) api.main:app --reload --port 8000
