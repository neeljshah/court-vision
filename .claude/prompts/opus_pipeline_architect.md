# Opus: Pipeline Architecture Audit (Low Usage)

You are a platform architect. Your job: read the current state, identify gaps, output a requirements doc + generate a detailed Sonnet prompt.

## Read These Files (Skim, Don't Summarize)
1. `CLAUDE.md` — scroll to "Current State" + "Open Priority Issues"
2. `scripts/batch_season.py` — understand the loop structure (40 lines max)
3. `src/pipeline/unified_pipeline.py` — read the return statement (what outputs exist?)
4. `scripts/select_season_games.py` — what does it output?

## Your Job: Output Two Sections

### Section A: Requirements Document (Bulleted, Not Prose)
Format:
```
CURRENT STATE:
• Batch scripts exist: batch_season.py, select_season_games.py
• Games processed: 6 with full data
• Season target: 50 games (2 per team)
• Batch output: individual game dirs (tracking_data.csv, possessions.csv, features.csv per game)
• Known gaps: [list exact gaps from CLAUDE.md issues + code inspection]

MISSING LAYERS:
1. [Name] — Why: [1 line] — Input: [X] Output: [Y]
2. [Name] — Why: [1 line] — Input: [X] Output: [Y]
... (5-7 items max)

BUILD ORDER:
[numbered dependencies]

SUCCESS CRITERIA:
• Can load all 50 games into unified DFs in <10s
• Can run Season 2025-26 batch end-to-end unsupervised
• Can validate quality (80% enrichment threshold met)
• No manual intervention
```

### Section B: Sonnet Prompt
Generate a complete prompt for Sonnet. Format:
```
# Sonnet: Build Full NBA Season Pipeline

## Exact Requirements
[Copy from Section A, Requirements Document]

## Build These Files (In Order)
1. scripts/consolidate_season.py
   • Input: data/games/*/tracking_data.csv, possessions.csv, features.csv
   • Output: data/tracking_all.csv, possessions_all.csv, features_all.csv
   • Logic: [specific patterns from existing code]

2. scripts/validate_season.py
   • Input: data/season_batch_log.csv, data/games/*/
   • Output: data/season_validation_report.csv
   • Thresholds: [exact values from CLAUDE.md]

3. scripts/run_season_batch_full.py
   • Orchestrates: select → download → pipeline → consolidate → validate
   • Logging: append to vault/Sessions/season_batch_YYYYMMDD.md
   • Resume on failure: [checkpoint logic]

4. [Any other missing layer from Section A]

## Exact Code Patterns
[Copy 3-5 working patterns from unified_pipeline.py or batch_season.py showing]

## Tests Required
• test_consolidate_all_games.py
• test_validate_season.py
• [exact test names]

## Success Check (Sonnet runs this last)
```bash
python -m pytest tests/test_consolidate_all_games.py -v
python scripts/run_season_batch_full.py --dry-run
```

## Constraints
• No re-reading files unless Sonnet asks
• Use existing patterns from batch_season.py, unified_pipeline.py
• All CSVs UTF-8 encoded
• Log all runs to vault/Sessions/
• No breaking changes to Phase G scripts
```

---

## Rules for Output
- Keep both sections short (Section A: <200 tokens, Section B: <400 tokens)
- Be specific: exact file paths, exact column names, exact error thresholds
- Assume Sonnet reads the actual files once (don't repeat file paths in every task)
- Sonnet will ask clarifying questions — answer them instantly with code snippets
