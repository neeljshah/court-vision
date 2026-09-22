GAP S377 | sport nba | worktree harness-h34 (master-based) | log cx_s377_nba_corpus_readiness
# NBA joined corpus readiness census: counts only, NO scorer edit, NO score (design: docs/evidence/harness/ASTRA_NBA_SECOND_CORPUS_AUDIT_2026-09-21.md)

SINGLE PROBLEM: S360 wrote data/cache/ingame_grade_joined/nba_checkpoints_r1 (1,593 games, 465,249 ticks) but the design audit
found it is not yet a usable second corpus: post-final rows repeat the final score, 61 percent of ticks sit in period 4, half the
ticks have no model side, the model side's half was ALREADY scored once by row S86, and nobody has counted what survives a dated
walk-forward with an embargo. A prereg cannot be drafted without these denominators.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/ingame/nba_corpus_readiness.py` fails. DO NOT edit baseline_four_arm*.py or
nba_checkpoints_to_joined.py: the sealed MLB trial pins the scorer and has not run yet.

REAL ROW, VERBATIM (first line of one corpus file; note state_summary is a STRING of space-separated key=value pairs, not an object,
and model_prob may be null): {"close_ts":"2026-03-15T01:10:22.000000+00:00","game_id":"401810825","market_prob":0.8049999999999999,
"market_ticker":"nba-mil-atl-2026-03-14","model_prob":null,"outcome":1.0,"seconds_since_last_trade":0.0,"side":"home","sport":"nba",
"state_summary":"home_score=0 away_score=0 quarter=1 seconds_remaining=2880","traded":true,"ts":"2026-03-14T19:10:33.000000+00:00"}
The directory also holds census.json and manifest.json written by the converter: skip them as data, and report whether the
converter's manifest agrees with the manifest this tool computes. An unparseable state_summary is a counted refusal, never a zero.

CHANGE (NEW files only):
1. scripts/platformkit/ingame/nba_corpus_readiness.py (<= 300 LOC, stdlib, streams one file at a time): `--corpus-dir <dir>
   [--exposed-ids <csv of previously scored game ids>] --out <json>`. Counts ONLY: files, bytes, a per-file SHA-256 manifest and its
   own SHA-256; ticks; unique (game_id, ts) keys; identical-duplicate keys; CONFLICTING duplicate keys (same key, different
   payload); per-game outcome consistency; non-finite or out-of-(0,1) probabilities; post-final rows (quarter >= 4 and
   seconds_remaining == 0) and how many games have more than one; ticks and games per period 1-4 and overtime; model coverage per
   game (all / some / none) and per period; first-tick UTC date per game -> date folds, games per fold, and, for a symmetric
   three-day embargo with an expanding window, the number of warm-up folds with no eligible training game and the post-warm-up game
   and tick denominators, each computed twice (all ticks; live ticks only); games whose close_ts is not the maximum ts; exposure:
   how many games and ticks appear in --exposed-ids. No loss, no fit, no calibration statistic, no price summary of any kind.
   Every count is a strict int; every refusal reason is counted; results are independent of file and row order.
2. tests/platformkit/ingame/test_nba_corpus_readiness.py: synthetic corpora for each count above, order independence, a conflicting
   duplicate, a post-final run, a missing model side, an embargo warm-up case worked by hand in the test docstring.
3. Memo docs/evidence/harness/S377_nba_corpus_readiness_2026-09-21.md (the builder does NOT run the real corpus; the orchestrator
   does and records the counts in the ledger).

CONTROLS: PREPARE only, NEW files only, construct tests, no real archive, no network. ACCEPTANCE: per-file test passes; --help
works; diff = NEW files only; <= 300 LOC; ASCII; contract Q6 vocabulary (assemble retracted-figure literals from single digits);
the memo ends with a NOT VERIFIED list. The pod is OFF.
