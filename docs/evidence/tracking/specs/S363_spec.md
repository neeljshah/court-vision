GAP S363 | sport all captured | worktree harness-h21 (master-based) | log cx_s363_capture_watchdog
# Capture watchdog + daily coverage report: a running process that collects nothing must be visible within minutes

SINGLE PROBLEM: audit 04 capability 11 -- "no alert on capture stopped / ledger stopped growing"; forward capture once sat dead for
seven weeks unnoticed. On 2026-09-21 three silent failures were found only by hand: the book capture wrote zero trades for 1.5 h,
the state capture wrote zero NFL rows with a healthy heartbeat, and after a redeploy NFL trades froze behind max_pages_exceeded.

BINDING BEFORE-CONDITION (re-run, quote): `ls scripts/platformkit/ingame/capture_watchdog.py` fails.

CHANGE (NEW files only; read-only over the archives; no network; stdlib only):
1. scripts/platformkit/ingame/capture_watchdog.py (<= 300 LOC): CLI `--root data/cache/ingame_books_local [--json out] [--max-age-s
   300]`. Reads every _heartbeat.json under <root>/kalshi/<sport>/ and <root>/state/<sport>/ and the tail of today's shard per
   sport (seek from the end; never load a whole file). Per source it reports OK / STALE / SILENT / DEGRADED with reasons:
   heartbeat older than max-age; last_write_ts older than max-age while games are live; rows_written_total unchanged between two
   heartbeats read N seconds apart (`--watch-s`); any error counter growing (max_pages_exceeded, write failures, adapter errors,
   seed failures); 429 / 403 rate over 1 pct; trades_written_total flat while live winner markets exist; state rows flat while
   n_games_live > 0; process lock file present but no heartbeat progress. Exit code 0 only when every source is OK; 1 otherwise;
   one line per source on stdout (ASCII).
2. scripts/platformkit/ingame/capture_coverage_daily.py (<= 300 LOC): COUNTS ONLY per UTC date and sport: games with books /
   with trades / with state / with all three (linked through scripts/platformkit/ingame/game_market_link.py when importable,
   otherwise ticker-level counts only), snapshot cadence per live winner ticker (median, p95), trade_gap records and their total
   seconds, touch-size availability share. It prints the running total of games per sport that have all three inputs -- the
   number a forward replay prereg needs (>= 30 per sport). Reads timestamps and PRESENCE of fields only; never a price value.
3. tests/platformkit/ingame/test_capture_watchdog.py + test_capture_coverage_daily.py: synthetic roots for every status and
   reason; tail-reading works on a large file without loading it; exit codes; counts-only guarantee (no price field accessed:
   assert via a dict subclass that raises on price keys).
4. Memo docs/evidence/harness/S363_capture_watchdog_2026-09-21.md with the two finisher commands.

CONTROLS: read-only, counts only, no measured calibration number. ACCEPTANCE: both per-file tests pass; `--help` works for both
CLIs; diff = NEW files only. Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals from
single digits. Memo ends with a NOT VERIFIED list. The pod is OFF.
