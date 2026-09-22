GAP S348 | sport all captured | worktree harness-h3 | log cx_s348_coverage_matrix
# Capture-to-scoring coverage matrix: every captured sport gets a denominator or an exact missing-input status (astra round 10 rank 8)

SINGLE PROBLEM: capture breadth exceeds model and join coverage and nothing states it. scripts/platformkit/ingame/
inplay_capture_loop.py:93 lists seven sports (mlb, soccer_intl, tennis, wnba, npb, kbo, nba) while :99 dispatches a model for
three; NFL has no adapter; no artifact says, per sport, which of {state, book, prints, model, settlement} exist on disk.

BINDING BEFORE-CONDITION (re-run, quote): `grep -n "^DEFAULT_SPORTS\|^_MODEL_SPORTS" scripts/platformkit/ingame/inplay_capture_loop.py`
shows 7 vs 3; `ls scripts/platformkit/ingame/coverage_matrix.py` fails.

CHANGE (NEW files only):
1. scripts/platformkit/ingame/coverage_matrix.py (<= 300 LOC, stdlib + pyarrow only if already imported elsewhere in
   scripts/platformkit/ingame; stream, never load a store over 300 MB, stay under 500 MB RSS): a read-only census with CLI
   `python -m scripts.platformkit.ingame.coverage_matrix --out <path.json> [--sports ...]`. For each sport in DEFAULT_SPORTS plus
   nfl, nhl, ncaaf, ncaab: per input class -- state (data/cache/ingame, domains/<sport> ingest outputs), price series
   (data/cache/inplay_odds/*_price_series.parquet, nba_checkpoints_full.parquet), books (data/cache/book_depth,
   data/cache/depth_history, data/cache/ingame_books, data/cache/ingame_books_local), prints (any per-trade tape), model
   (module path that returns a live probability, or none), settlement (result field or settlement join), joined scoring corpus
   (data/cache/ingame_grade_joined/<sport>*) -- report: present yes/no, path, file count, distinct games, first and last date,
   bytes. Cell status is one of AVAILABLE / PARTIAL / ABSENT, and each sport row ends with a scoring route: SCORABLE_NOW,
   or MISSING:<exact input list>. A store that is absent in the worktree but present under the main repo data tree is reported
   through the path the CLI was given (`--data-root`, default repo-relative data/), never guessed.
2. tests/platformkit/ingame/test_coverage_matrix.py: construct a tiny fake data root under tmp_path (two sports, one with every
   class, one with only a price series) and assert the statuses, counts, date ranges and the MISSING list.
3. Memo docs/evidence/harness/S348_coverage_matrix_2026-09-21.md: the design, the status vocabulary, and the exact command the
   FINISHER runs on the main data tree. The builder does NOT run the census on real data (the sandbox worktree has no data/).

CONTROLS: read-only census; counts and dates only, no calibration number. ACCEPTANCE: per-file test passes; `--help` works;
diff = NEW files only. Vocabulary follows contract Q6; automated scan required. Memo ends with a NOT VERIFIED list.
The pod is OFF: ignore any pod instruction.
