GAP S358 | sport mlb + nfl + ncaaf + soccer + nba + tennis | worktree harness-h16 (master-based, COPY of the untracked main-tree files) | log cx_s358_state_capture_integrity
# Local live-STATE capture (row S352): data-integrity requirements after an independent REJECT (this file is the authority)

CONTEXT: scripts/platformkit/ingame/local_state_capture.py, local_state_capture_sources.py, game_market_link.py and
tests/platformkit/ingame/test_local_state_capture.py are a credential-free ESPN / MLB Stats API state capture ALREADY RUNNING on the
owner's laptop beside the S341 book capture. An independent review (codex gpt-5.6-sol) REJECTED it. Every item below is binding.
Mirror the structure the S341 rebuild uses (read scripts/platformkit/ingame/local_capture_client.py, local_capture_limiter.py,
local_capture_writer.py, local_capture_metrics.py, local_capture_time.py on master) and REUSE those row-owned modules by import
where they fit -- do not write a second limiter, writer or time parser.

Q1 TIMESTAMPS ARE TRUE: request_start_utc is read IMMEDIATELY before the HTTP call, AFTER any rate-limit wait; response_end_utc
   after the body is consumed. capture_ts equals response_end_utc; the tick start, if kept, goes in a NEW field tick_start_ts. No
   row may carry a time taken before its request was sent. (The review sampled rows whose capture_ts preceded request_start.)
Q2 state_changed IS HONEST: it is null (not true) for the FIRST observation of a game in this process AND for the first observation
   after a restart unless the last canonical state was recovered from the archive; otherwise it compares (status, normalized
   state) with the previous row of the same game, so a status-only transition (pre -> live, live -> final, delayed) IS a change. On
   startup the last row per game is recovered from today's shard (and yesterday's for games spanning UTC midnight).
Q3 THE LINKER NEVER GUESSES: game_market_link matches BOTH teams (away to away, home to home), the LOCAL scheduled game date, and
   -- when more than one market matches (doubleheaders) -- an explicit start-time discriminator; anything else is unmatched with a
   reason. A single matching team is never a match (the review matched BAL-NYY to BAL-TOR). NBA and every other ESPN sport take
   the game date from the event payload, never from the current UTC clock.
Q4 NOTHING FAILS SILENTLY: every except clause increments a named per-source heartbeat counter; the heartbeat reports per source
   attempts, successes, rows written, drops by reason, last actual WRITE time (not merely last HTTP success), current request
   rate and the 10-minute 429 / 403 rates. In-memory maps (last_state, mlb_games, per-event dictionaries) are pruned when a game
   goes final and at the UTC day boundary.
Q5 WRITES ARE CRASH-SAFE AND SINGLE-WRITER: reuse the S341 writer -- exclusive process lock, one os.write per record on an O_APPEND
   descriptor, fsync at most once per tick, torn final line quarantined on startup, write failures counted, daily shard chosen
   from response_end_utc.
Q6 RATE CONTROL CANNOT BURST: reuse the S341 limiter (next-send deadline reserved under the lock; Retry-After in both forms).
   ESPN returns 403 for ANY custom User-Agent (measured): never set one. An unknown status never maps to live.
Q7 VENUE TIMES are parsed with the shared parser only (0 to 9 fractional digits, trailing Z, offsets); Python 3.10 safe.
Q8 KEEP what works: mlb via the Stats API schedule + feed/live, nba / soccer / tennis / nfl / ncaaf via the ESPN scoreboards, the
   NFL adapter called with a REAL receipt (domains.nfl.ingest_nfl_states.normalize_scoreboard(payload, receipt)), existing row
   field names and the archive root data/cache/ingame_books_local/state/<sport>/<date>.jsonl (ADD fields, never rename: contract
   B2), the stop file STOP_STATE, the raw-body sha256. ADD the same CLI as S341: --output-root (env LOCAL_STATE_ROOT, the flag
   wins), --max-ticks, --sports.
Q9 SCOPE: row-owned files only (the four above plus new row-owned modules). Never edit a pre-existing module, never edit the S341
   modules (import them). No credentials. Each file <= 300 lines, stdlib + requests.

TESTS (offline only, fake sessions): request stamp after a limiter sleep; state_changed null on first sight and after an unseeded
restart, true on a status-only transition, false on an identical repeat; archive recovery of the last state; linker -- both teams
required, one-team near-miss unmatched, doubleheader needs a start time, date from the payload around UTC midnight; every
swallowed exception increments a counter; map pruning at final and at the day boundary; CLI precedence; NFL adapter with a receipt.
ACCEPTANCE: per-file tests pass; the memo docs/evidence/harness/S358_state_capture_integrity_2026-09-21.md maps each Q item to code
lines and tests, gives the exact side-by-side smoke command, and ends with a NOT VERIFIED list. Vocabulary follows contract Q6;
automated scan required; assemble retracted-figure literals from single digits.

AMENDMENT 1 (orchestrator, 2026-09-21, after the independent verifier REJECT; binding; makes Q4 + Q5 explicit for the write path).
VERIFIER FINDING (codex gpt-5.6-sol): local_state_capture.py swallows append failures (~line 152) and prunes FINAL games (~156-157)
although no row was archived; sync failures are swallowed (~169) AFTER the remembered state and the final pruning have already
advanced, and the inherited writer then stays permanently failed. One disk fault leaves a live process losing every later row,
and an MLB final may never be retried.
BINDING RULE -- COMMIT-THEN-PROMOTE: within a tick, (1) rows are appended; (2) writer.sync() is called; (3) ONLY IF both succeed are
the per-game remembered state (the state_changed baseline) promoted and final games pruned. On an append or sync failure the
failure is COUNTED in the heartbeat (named counter + last error text) and then RE-RAISED to the tick loop, which (a) does not
promote state and does not prune, (b) rebuilds the writer on the next tick (a permanently failed writer is never reused), (c)
retries the same games, and (d) after N consecutive failed ticks (default 5) exits nonzero with a clear message so a supervisor or
the watchdog can see it -- a process that cannot write must not look alive. A row that was appended but whose sync failed may be
re-appended on the retry: de-duplicate on (sport, game_key, response_end_utc) at recovery time and state that rule.
Required tests: append failure on a FINAL game -> the game is retried next tick and only then pruned; sync failure -> no state
promotion, no pruning, the writer is rebuilt; N consecutive failures -> nonzero exit; heartbeat counters for both; no duplicate row
after a failed-then-successful tick.
