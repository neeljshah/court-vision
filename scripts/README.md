# Scripts Directory Guide

This folder contains operational scripts used to run, validate, and maintain the CourtVision pipeline.

## Common Script Types

- Batch processing: season and multi-game runners
- Validation: thresholds, quality gates, game checks
- Training/retraining: model and feature refresh workflows
- Data operations: fetch, backfill, enrich, and migration tasks
- Infrastructure helpers: RunPod and environment setup

## Usage Principles

- Prefer scripts in this directory over ad hoc root-level scripts.
- Keep scripts single-purpose and idempotent when possible.
- Document non-obvious inputs/outputs inside each script docstring or header.
- Avoid committing generated outputs from script execution.

## Quick Examples

```bash
python scripts/run_phase_g.py --parallel 4
python scripts/batch_season.py --season 2025-26
python scripts/validate_game.py --game-id 0022400430
```
