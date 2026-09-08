GAP S329 | sport wnba + mlb + soccer (in season now; nba when the season starts) | worktree a16 | log cx_s329_prospective_receipt_capture

**DATA-CAPTURE ROW (S register; the fix S320 / S328 / S321 all named: receipts can only be captured
PROSPECTIVELY, never backfilled). Codex PREPARES the capture job, tests and prereg; a finisher DEPLOYS it
to pod scratch and VERIFIES the first hours of capture.** `src/`, `kernel/`, `api/` and `intel/` are READ and
IMPORT only. Build in `scripts/platformkit/ingame/capture/`. NEVER write `data/registry/`, never flip a
flag, never claim an edge (calibration language only), never edit a landed memo, the registers or the
ledgers. Never invent a receipt time: every row's `received_at` is the wall clock of THIS process at the
moment the payload arrived, and `received_monotonic_ns` is the monotonic clock beside it.

**WHERE THIS ROW RUNS:** the pod, as ONE nohup capture process under `/workspace/wt/<wt>/receipts/`
(persistent volume; never `/tmp`; never under `/workspace/nba-ai-system`; never touch the track_daemon pid
1596016 or the guards pid 1519254; `nice -n 19`; bounded bandwidth: <= 1 request per source per 10 s per
live game; stop cleanly on a `STOP` file). Local: conda `basketball_ai` for tests and the verification
reads (batched).

**WHY THIS ROW EXISTS.** S321 attempt 2 stopped at D1: `nba_checkpoints_full.parquet` (465,249 ticks) carries
NO status and NO receipt column, so 0 ticks are admissible under the S309 mask and 312 of 1,593 tickers
resolve to no official game. S320 / S328 could falsify ORDERING only (no `received_at`). S327 measured
that no archive holds a trustworthy pre-start quote. Every direct-state model per sport is blocked on
the same missing field. The NBA season has not started (2026-09-08); WNBA, MLB and European soccer are
live now, so capture starts there and the NBA feed joins when its first game is scheduled.

**PREMISE (step 0, BINDING before-condition):** from the pod, one read-only probe per source (keyless, plain
urllib + UA, per the landed recipes: MLB GUMBO `statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live`; WNBA CDN
`cdn.wnba.com/static/json/liveData/boxscore/boxscore_{gid}.json` with Referer `https://www.wnba.com/`,
WAF detected by JSON-parse failure not status; FotMob `www.fotmob.com/api/data/matches?date=YYYYMMDD` +
`matchDetails?matchId=`; Kalshi public `trade-api/v2/markets?series_ticker=...` + `/markets/{ticker}/orderbook`
read-only) listing today's live or scheduled games and one quote source per sport with the HTTP status,
byte size and parse result. **If NO source returns a parseable in-play state from the pod's egress, the
premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE (name each source's failure mode).**

METHOD:
  1. **CAPTURE JOB (`receipt_capture.py`, <= 300 lines; sources as small adapters `src_mlb.py`, `src_wnba.py`,
     `src_fotmob.py`, `src_kalshi.py`, each <= 150 lines).** Loop: discover today's games per sport (schedule
     endpoints), poll each live game's state and each matching Kalshi market at the bounded cadence, and
     APPEND one row per payload to a daily parquet per sport (`receipts/<sport>/<YYYY-MM-DD>.parquet`,
     written via an atomic `.part` rename every N rows) with columns: `received_at_utc` (wall, ISO with
     microseconds), `received_monotonic_ns`, `source`, `source_game_id`, `official_game_id_hint`,
     `source_ts` (the payload's own timestamp when present, else empty), `http_status`, `payload_sha256`,
     `payload_bytes`, `state_json` (the minimal state fields the S323 adapter contract needs: clock, period,
     score, inning / base-out / count, minute, plus the raw quote fields) and `parse_ok`. Never rename or
     remove a column once the first parquet exists (B2). A per-source `status.json` heartbeat every 60 s.
  2. **RECEIPT INVARIANTS (tests, synthetic payloads):** `received_at_utc` is monotone non-decreasing per
     source; `received_monotonic_ns` strictly increasing; a replayed identical payload is stored again with
     its own receipt (never deduplicated at capture); a payload whose `source_ts` is LATER than
     `received_at_utc` is stored with `clock_skew_flag=1`, never dropped; the STOP file ends the loop
     within one cadence; a WAF HTML page is stored as `parse_ok=0` with the sha256.
  3. **S323 CONTRACT:** a reader `receipt_reader.py` (<= 150 lines) yields S323-contract frames from a
     receipts parquet with the as-of rule `received_at_utc <= state_ts - delay` (the S328 replay's join),
     so S328 can be re-run on captured data with REAL availability.
  4. **DEPLOY + VERIFY (finisher):** ship the package to `/workspace/wt/<wt>/capture/`, start it (nohup, nice,
     `OMP_NUM_THREADS=1`), record pid + UTC start; after >= 2 h read the parquets (batched): rows per source,
     live games seen, receipt cadence p50 / p95, parse_ok share, skew flags, bytes on disk and the projected
     daily footprint (must stay < 500 MB per day; else reduce the cadence, never the columns), and the share
     of rows the S309 mask would admit. Leave the job RUNNING (this is the standing capture the program
     needs; record the pid and the STOP recipe in the memo and in `docs/evidence/harness/S329_capture_status.md`).
  5. CHANGE NOTHING ELSE. No model, no scoring, no src hook.

**HONEST LIMITATIONS to state, not discover:** receipts from ONE vantage point (the pod's egress) measure
that vantage's availability, not the market's; NBA capture cannot start before the season; sources can
WAF-block (WNBA did from one egress); a 2 h verification is a smoke, not a season.

ACCEPTANCE RULE:
  metric        = premise probe table; the invariant tests; the deploy record (pid, UTC start, paths);
                  the 2 h verification table with n per source; the S309-admissible share
  before        = no archive carries received_at; S321 D1 admits 0 of 465,249 ticks
  bar           = >= 2 sources capturing live state with parse_ok >= 0.95; receipt cadence p95 <= 3x the
                  configured cadence; 0 dropped payloads (skew flagged, never dropped); daily footprint
                  < 500 MB; the reader yields S323-valid frames on the captured data; all tests pass; job
                  still running at the end of verification; 0 src edits; 0 flag flips
  n             = >= 2 h of capture; every live game seen; every payload
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, the daemon and guards, every landed
                  artifact, the registers and ledgers
  verdict       = **DONE** if the bar holds; **PARTIAL** naming the source or invariant that could not run;
                  **PREMISE FALSE** if no source is reachable from the pod.
EVIDENCE: `docs/evidence/harness/S329_prospective_receipt_capture_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game data | S329 | <finding with n> | <VERDICT>`) + `probe.csv`, `verification.csv` under
`docs/evidence/harness/S329_prospective_receipt_capture_2026-09-08/` (each <= 5 MB; integer cells
zero-padded; additive unit-suffixed columns) + `docs/evidence/harness/S329_capture_status.md` (pid, start,
paths, STOP recipe; updated by later rows, append-only).
TEST: `tests/platformkit/test_s329_receipt_capture.py` and `tests/platformkit/test_s329_receipt_reader.py`, each
alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the columns, the cadence, the
invariants, the footprint bound, the S309-admissibility rule), the capture job, the adapters, the reader,
the tests and the memo skeleton with the exact pod commands in `python3 -m` form, and exits with the line
`agent: PREPARED FOR FINISHER`; it must NOT deploy (Q1). Absent `data/registry` in the worktree is reported,
never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
