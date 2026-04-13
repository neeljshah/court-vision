# Demo Guide

This guide provides a deterministic, public-friendly walkthrough for evaluating CourtVision quickly.

## Prerequisites

- Python 3.9
- A virtual environment (conda recommended)
- Dependencies installed from `requirements.txt`

## Setup

```bash
git clone https://github.com/neeljshah/nba-ai-system.git
cd nba-ai-system
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt
cp .env.example .env
```

## Validation Step (Required)

Run tests first to validate environment integrity:

```bash
python -m pytest tests/ -q
```

## API Demo (No Custom UI Needed)

Start the API:

```bash
uvicorn api.main:app --reload --port 8000
```

Then open:

- `http://localhost:8000/docs`

Use Swagger to inspect and call available endpoints.

## Prediction Script Demo

Run one script-level prediction example:

```bash
python src/prediction/game_prediction.py --predict GSW BOS
```

Expected outcome:

- Command executes without import/runtime failures.
- A prediction payload (or score/probability output) is returned.

## Optional CV Pipeline Demo (GPU Recommended)

```bash
python scripts/run_clip.py --video data/videos/game.mp4 --no-show
```

Notes:

- Requires a valid local video file.
- Must run headless (`--no-show`) in accordance with project rules.

## What To Review After Demo

- `README.md` for architecture and status.
- `docs/PUBLIC_EVIDENCE.md` for claim standards.
- `docs/KNOWN_LIMITATIONS.md` for current constraints and risk transparency.

