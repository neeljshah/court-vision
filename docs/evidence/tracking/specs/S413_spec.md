GAP S413 | sport nfl | worktree harness-h73 (master-based) | log cx_s413_nfl_state_ingest
# NFL state ingest: the situation fields declared and counted as receipt-causal state rows, nothing scored

SINGLE PROBLEM: NFL has no state corpus. `docs/evidence/ingame/S348_coverage_nfl_2026-09-21.json` records the nfl
inputs.state block as status ABSENT (file_count 0, rows 0, distinct_games 0) and price_series ABSENT, with books PARTIAL
(one day 2026-09-21, 3,151 rows). The poller and the adapter already exist, but no FEATURES entry declares nfl for the
four-arm layer (baseline_four_arm_features.py:12-17 has no 'nfl' key) and no run has ever recorded what the situation
fields actually carry on a real slate. NFL cannot be a forward family until both are true
(.planning/DIRECTION_2026-09-22.md section 7, Session F; game_supply_2026-09-22.md:33-43).

BINDING BEFORE-CONDITION: quote from master (a) local_state_capture_sources.py:33 (`SPORTS_AVAILABLE: List[str] =
["mlb", "nba", "soccer"]`), :36-37 (extended with nfl / ncaaf only when the adapter imports), :190-192
(`_NFL_TOP_LEVEL_KEYS`), :194-232 (`_nfl_league_poll` and what it emits today: game_key, home_abbr, away_abbr,
schedule(...), status, source_ts, state, raw, receipt -- `state` being every adapter row key NOT in
_NFL_TOP_LEVEL_KEYS); (b) domains/nfl/ingest_nfl_states.py:199-227 (the normalized row: period,
clock_seconds_remaining, game_seconds_remaining, home_score, away_score, possession_team, down, distance, yardline_100,
yardline_100_status, yard_line_raw, possession_text_raw, down_distance_text_raw, possession_team_id_raw, is_red_zone,
home_timeouts, away_timeouts, last_play_id, source_ts, receipt) and :126-147 (why yardline_100 is always None with
status "semantics_unverified"); (c) local_state_capture.py:28-45 (`_build_row` -- the additive row schema carrying
scheduled_start_utc and date_reason from S393); (d) baseline_four_arm_features.py:12-25 (FEATURES, CORPORA); (e) the
S348 nfl coverage block above; (f) game_supply_2026-09-22.md:33-43 (data/nfl/schedules.parquet, 7,548 rows, thirteen
full ISO weeks Oct-Dec 2026, each >= 4 games; KXNFLGAME / KXNFLSPREAD at local_capture_runner.py:20).

CHANGE (owned: baseline_four_arm_features.py, NEW scripts/platformkit/ingame/nfl_state_field_census.py, NEW
tests/platformkit/ingame/test_nfl_state_ingest.py, memo docs/evidence/harness/S413_nfl_state_ingest_2026-09-22.md;
local_state_capture.py, local_state_capture_sources.py, domains/nfl/** and every landed test file stay byte-identical --
the poller already emits a stable key set, so this row changes no capture code):
1. DECLARED BEFORE ANY READ. `FEATURES['nfl']` is added with the adapter's own emitted names plus two derived fields:
   score_diff, period, game_seconds_remaining, down, distance, possession_is_home, home_timeouts, away_timeouts.
   score_diff and possession_is_home are derived in a small declared helper beside `state_fields` from home_score /
   away_score and possession_team against home_abbr. `yardline_100` is NOT declared while its status is
   semantics_unverified: a guessed field-side conversion reads the wrong side of the field, so its absence is named in
   the memo, never inferred. No declared field is ever zero-filled -- a missing field is counted absent. `CORPORA` gains
   NO nfl entry, so this row makes nothing scoreable.
2. THE CENSUS. NEW `nfl_state_field_census.py` (<= 300 LOC, `--help` works): given a state shard root, a date and an
   `--out` JSON path, it reads the emitted rows and writes counts only -- per declared field present / absent / null;
   rows; distinct game_keys; the status mix; state_changed transitions; the scheduled_start_source mix; and the
   receipt-causality count of rows whose `source_ts` is later than their own `response_end_utc`. No probability, no
   loss, no model, no comparison against any price. It refuses an `--out` under data/registry or data/cache, and opens
   no book, ledger or joined corpus.
3. TESTS (construct, injected payloads, no network): a synthetic ESPN NFL scoreboard payload driven through `nfl_poll`
   with a fake `get` and a receipt and then through `_build_row`, asserting every declared field reaches `state`, that
   scheduled_start_utc / scheduled_start_source / date_reason are present (the S393 schema) and that the row's top-level
   key set equals the landed key set EXACTLY (no new key); a pre-game payload with an empty `situation` counts each
   declared field absent and never zero; a payload with possession on the away team; a payload missing `home_timeouts`;
   the census over a small synthetic shard reproducing counts computed by hand in the test; an `--out` under
   data/registry refused; the landed test_state_capture_sources.py and test_local_state_capture.py pass unchanged.
4. THE REAL-ROW PROBE (orchestrator step, not the build lane): the census run ONCE, read-only, over the captured shard
   of a Sunday slate, recorded in the memo as per-field counts with the date and the row count. An empty shard is
   reported plainly -- the S348 ABSENT status stands until a run contradicts it. Nothing is scored, joined or charged.
5. MEMO: the before-condition quotes; the declared FEATURES['nfl'] entry and why yardline_100 is excluded; the probe
   counts; the price series NFL has (Kalshi KXNFLGAME and KXNFLSPREAD, local_capture_runner.py:20, KXNFLGAME also in
   forward_schedule_writer.py:27); the plain statement that NO NFL corpus is joined, scored, calibrated or charged by
   this row; ends with NOT VERIFIED.

CONTROLS: PREPARE only -- no NFL corpus joined or scored, no CORPORA entry, no charge, no ledger row, no network in
tests; construct fixtures plus one read-only census; never write data/registry or data/cache; never touch a running
capture, its output root or a STOP file; never edit a gated path. ACCEPTANCE: per-file tests pass one at a time;
`--help` works; <= 300 LOC per file; ASCII; contract Q6 vocabulary; landed capture tests pass; memo ends NOT VERIFIED.

AMENDMENT 1 (2026-09-24 18:4xZ; binding; round 1 on the build candidate: codex gpt-5.6-sol REJECT (two blockers; its sandbox could not run the tmp_path tests -- the orchestrator ran them: 18 / 240 / 19 passed), Opus tier 2 ACCEPT WITH CORRECTIONS (three corrections already applied: resolved-path refusal of --out, tmp cleanup on a failed write, LANDED_KEYS derived from the landed _build_row)): (a) DUPLICATE RECEIPT KEYS: two rows sharing (game_key, response_end_utc) must not erase the census -- rows with IDENTICAL content under one key are counted ONCE in every field count and reported as duplicate_identical (strict int); rows with DIFFERING content under one key are excluded from the field counts and reported as duplicate_conflict (strict int, counting every row involved); both diagnostics sit beside `rows` in the artifact and never inside it; regression: two identical valid rows with down 1 -> rows 1, down present 1, duplicate_identical 1; two rows same key downs [1, 2] -> rows 0, duplicate_conflict 2. (b) OUTPUT UNDER THE CAPTURE ROOT: --out that resolves (abspath AND Path.resolve) to any path beneath --root is refused with reason out_under_capture_root, in addition to the data/registry and data/cache refusals; regression: --root capture --out capture/state/nfl/2026-09-27.jsonl refused and the input file byte-identical after the run. (c) the stray pytest-of-neelj/ temporary tree in the worktree was never part of the candidate; nothing in it is staged or restored.

AMENDMENT 2 (2026-09-24 19:3xZ; binding; round 2 on fix 1b: codex gpt-5.6-sol REJECT (one blocker, two corrections); the orchestrator ran the tests 23 / 240 / 19): (a) DUPLICATE KEY IDENTITY: the duplicate grouping key must preserve the canonical raw JSON value of response_end_utc (and game_key), never a coerced or stringified form that can collapse distinct values -- rows ('g1', 1) and ('g1', 2) are DISTINCT keys (rows 2, duplicate_conflict 0, down present 2); an invalid or missing receipt time is refused and counted BEFORE duplicate classification (receipt_time_invalid, strict int) and never grouped; regression added to test_duplicate_conflict_rows_excluded. (b) ATOMIC REPLACE COVERED: os.replace(tmp, out) runs inside the guarded block so a failing replace also unlinks <out>.tmp; regression with os.replace patched to raise -> no .tmp left, target absent. (c) MEMO: line 3 no longer says the spec has no amendments; the duplicate-key paragraph describes the final rules (identical counted once with duplicate_identical, conflicting excluded with duplicate_conflict, distinct raw receipt times never merged).
