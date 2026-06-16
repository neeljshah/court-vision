.PHONY: test lint train predict pipeline api proofs proofs-fast

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

# Reproducible proof scoreboards on the REAL local corpora (data/domains/, gitignored).
# Beat-the-close (pregame quality) + in-game (conditional-vs-static) -- both call run()
# with no --corpus, so each per-sport proof resolves its real data/domains path.
proofs:
	$(PYTHON) -m scripts.platformkit.beat_the_close_scoreboard
	$(PYTHON) -m scripts.platformkit.ingame_scoreboard

# Fast, byte-committed reproducibility: run both scoreboards on the tiny fixture corpora
# (tests/fixtures/proof/<sport>/). Finishes in seconds; prints non-empty NBA+MLB rows. The
# --corpus flag sets PROOF_CORPUS_ROOT before build() per the shared corpus-override contract.
proofs-fast:
	$(PYTHON) -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
	$(PYTHON) -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof
