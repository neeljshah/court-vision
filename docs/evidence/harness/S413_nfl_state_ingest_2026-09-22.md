# S413 -- NFL state ingest: situation fields declared and counted, nothing scored

Row: S413 (harness register). Spec: `docs/evidence/tracking/specs/S413_spec.md` (worktree copy byte-identical to
master at build time; the spec now carries AMENDMENT 1 and AMENDMENT 2, see FIX 1b and FIX 1c). Lane: build, worktree `nba-harness-h73`, base master `4f66acfb5`.

This row PREPARES only. NO NFL corpus is joined, scored, calibrated or charged by this row. No CORPORA entry, no
prereg, no ledger row, no price comparison. Q1/Q2/Q4/Q5/Q9 do not apply (no scored comparison exists).

## 1. Premise re-measured (Q8)

- `FEATURES` in `scripts/platformkit/ingame/baseline_four_arm_features.py` on master has keys `mlb`, `soccer`,
  `nba` (lines 13-19) plus `nba_enriched` (line 31). There is NO `nfl` key. CONFIRMED.
- `docs/evidence/ingame/S348_coverage_nfl_2026-09-21.json`, block `sports.nfl.inputs.state`:
  `"present": false, "file_count": 0, "distinct_games": 0, "rows": 0, "status": "ABSENT"`; `price_series` also
  `"status": "ABSENT"`; `books` `"status": "PARTIAL"`, `"rows": 3151`, first/last date `2026-09-21`. CONFIRMED.

The premise holds; the row proceeds.

## 2. Before-condition quotes (master, this tree)

Line numbers drifted from the spec's citations; the drift is named at each quote.

(a) `scripts/platformkit/ingame/local_state_capture_sources.py`
- :34-35 (spec cited :33, :36-37 -- now one expression):
  `SPORTS_AVAILABLE: List[str] = (["mlb", "nba", "soccer"] + ["tennis"] * (_tennis_parse_scoreboard is not None)`
  `+ ["nfl", "ncaaf"] * (_nfl_normalize_scoreboard is not None))` -- nfl / ncaaf join only when the adapter imports
  (:10-14, `from domains.nfl.ingest_nfl_states import normalize_scoreboard as _nfl_normalize_scoreboard`).
- :262-263 (spec cited :190-192): `_NFL_TOP_LEVEL_KEYS = {"espn_event_id", "kickoff_utc", "home_abbr", "away_abbr",
  "status", "source_ts", "request_start_utc", "response_end_utc", "http_status"}`
- :264-294 (spec cited :194-232), `_nfl_league_poll`: refuses a response lacking any of request_start_utc /
  response_end_utc / http_status (`missing_receipt`), then per event emits
  `game_key` (`_identity(...)`), `_missing_game_id`, `home_abbr`, `away_abbr`, `_start` (the event, for schedule),
  `status` (`_NFL_STATUS.get(row.get("status"), "pre")`), `source_ts`, `state` =
  `{k: v for k, v in row.items() if k not in _NFL_TOP_LEVEL_KEYS}`, `raw`, `receipt` (`dict(receipt)`), then
  `unique_games(...)` resolves `scheduled_start_utc` / `scheduled_start_source` / `date`.

(b) `domains/nfl/ingest_nfl_states.py`
- :199-227, the normalized row: espn_event_id, kickoff_utc, home_abbr, away_abbr, status, period,
  clock_seconds_remaining, game_seconds_remaining, home_score, away_score, possession_team, down, distance,
  yardline_100 (`None`), yardline_100_status (`"semantics_unverified"`), yard_line_raw, possession_text_raw,
  down_distance_text_raw, possession_team_id_raw, is_red_zone, home_timeouts, away_timeouts, last_play_id,
  source_ts, request_start_utc, response_end_utc, http_status. Note: the spec's list ends with `receipt`; the
  adapter row carries the receipt FLATTENED (request_start_utc / response_end_utc / http_status, all in
  `_NFL_TOP_LEVEL_KEYS`), and the poller attaches `receipt` itself. So `state` holds exactly the 18 keys the test
  pins as `ADAPTER_STATE_KEYS`.
- :126-147 and :166-172, why yardline_100 is always None: `yardline_100_from` is "NOT wired into
  normalize_scoreboard yet. ESPN's own field-side pairing ... was never observed live -- no game was in progress
  at S350 smoke time"; the docstring states a guessed conversion is worse than a missing one.

(c) `scripts/platformkit/ingame/local_state_capture.py` :23-40 `_build_row` (spec cited :28-45) returns exactly:
sport, game_key, request_start_utc, response_end_utc, http_status, source_ts, state, state_changed, date,
home_abbr, away_abbr, status, capture_ts, tick_start_ts, raw_sha256, capture_version, scheduled_start_utc,
date_reason, scheduled_start_source (default `'unavailable'`). `state_changed` is None on a game's first row.

(d) `baseline_four_arm_features.py` :13-35 on master: FEATURES (mlb, soccer, nba; nba_enriched at :31) and CORPORA
(mlb, mlb_clean, soccer_intl, nba, nba_checkpoints with '', '_segmented', '_segmented_r3'; nba_checkpoints_r1;
nba_state_enriched_r1). No nfl anywhere.

(e) The S348 nfl coverage block: quoted in section 1.

(f) `docs/direction/game_supply_2026-09-22.md` :33-43: "`data/nfl/schedules.parquet` (7,548 rows; `season`
1999-2026 ...)"; Oct-Dec 2026 per ISO week wk40..wk52 = 16, 15, 14, 14, 14, 15, 14, 13, 16, 14, 15, 16, 16
("Thirteen full weeks, every one >= 4"); Kalshi `KXNFLGAME`, `KXNFLSPREAD` at local_capture_runner.py:20.

## 3. The declared entry

```
FEATURES['nfl'] = ('score_diff', 'period', 'game_seconds_remaining', 'down', 'distance',
                   'possession_is_home', 'home_timeouts', 'away_timeouts')
```

- Declared before any read of a real NFL row. `CORPORA` gains NO nfl entry; `sport_for('nfl')` raises
  `unmapped corpus` (tested), and `state_eligibility(..., 'nfl')` raises `unknown sport`, so nothing NFL is
  scoreable through the four-arm layer.
- Helper `nfl_state(state, home_abbr, away_abbr)` beside `state_fields` returns `{field: (status, int|None)}`
  with status one of present / null / absent / refused:
  - absent = key missing from `state` (or `state` not a dict); null = key present with value None;
    refused = not a strict int (bool, float and str are refused) or outside `NFL_BOUNDS`
    (scores 0-200, period 0-10, game_seconds_remaining 0-3600, down 1-4, distance 0-99, timeouts 0-3).
  - `score_diff` = home_score - away_score only when both are present; otherwise the worse of the two statuses
    (refused > absent > null).
  - `possession_is_home` = 1 when possession_team equals home_abbr, 0 when it equals away_abbr; refused when the
    team matches neither, an abbreviation is missing, or home and away share one abbreviation.
  - Nothing is zero-filled. A zero appears only when the source itself emits zero (e.g. ESPN's pre-game period 0).
- `yardline_100` is NOT declared: the adapter always emits it None with `yardline_100_status =
  "semantics_unverified"`, because ESPN's field-side pairing was never observed on an in-progress payload. A
  guessed field-side conversion would read the wrong side of the field on half the snaps; its absence is named
  here and never inferred.
- File-size note: to keep `baseline_four_arm_features.py` at 300 lines, five double blank lines between existing
  functions became single blank lines (no code change).

Emitted-vs-declared note: the adapter emits explicit None for every situation field on a pre-game payload, so the
census counts those as `null`, not `absent`; both are "not present" and neither is ever zero. `absent` is
reserved for a key the row does not carry at all.

## 4. The census

`scripts/platformkit/ingame/nfl_state_field_census.py` (`--root <capture output root> --date YYYY-MM-DD --out`)
reads only `<root>/state/nfl/<date>.jsonl` and writes counts: per declared field present / null / absent / refused;
rows; distinct game_keys; status mix; state_changed (true / false / null / refused); scheduled_start_source mix;
receipt causality (later / not_later / source_ts_null / unparseable) and `source_ts_later_than_response_end`.
Malformed lines and non-nfl rows are counted, not read. A row whose receipt time is missing or invalid is refused
first and counted in `receipt_time_invalid`; it is never grouped. Valid rows are grouped by (game_key, canonical
raw JSON of response_end_utc): identical rows under one key count once (extra copies in `duplicate_identical`);
rows that differ under one key are all excluded (every row in `duplicate_conflict`); distinct raw receipt values
are never merged. The result is identical under row permutation (tested both orders).
Every count is checked as a non-negative strict int. `--out` under data/registry or data/cache is refused
(case-insensitive); the output is written tmp + fsync + os.replace. It opens no book, ledger or joined corpus.

## 5. Finding from construct tests (not live-checked)

The landed schedule resolver (`local_state_capture_dates.venue_instant`) returns None for a minute-precision
start such as `2026-09-27T17:00Z` and parses `2026-09-27T17:00:00Z`. If ESPN's NFL event `date` uses the
minute-precision form on real payloads, every NFL state row lands with `scheduled_start_utc = None` and
`scheduled_start_source = "unavailable"`. The test
`test_minute_precision_start_lands_unavailable_with_the_same_key_set` pins the current behaviour; no capture code
was changed (out of scope, byte-identity required). The orchestrator's probe should read the
`scheduled_start_source_mix` count to settle it.

## 6. Price series NFL has

Kalshi `KXNFLGAME` and `KXNFLSPREAD`: `scripts/platformkit/ingame/local_capture_runner.py:20`
(`SERIES_BY_SPORT["nfl"] = ("KXNFLGAME", "KXNFLSPREAD")`); `KXNFLGAME` also in
`scripts/platformkit/execution/forward_schedule_writer.py:26` (spec cited :27; one-line drift). This row reads
neither.

## 7. Tests (per file, one at a time)

- NEW `tests/platformkit/ingame/test_nfl_state_ingest.py`: 15 passed.
- Landed, unchanged: test_state_capture_sources.py 240 passed; test_local_state_capture.py 19 passed.
- Landed importers of baseline_four_arm_features / baseline_four_arm: test_paper_sizing_inputs.py 22,
  test_baseline_four_arm.py 53, test_baseline_four_arm_eligibility.py 45, test_baseline_four_arm_nba.py 134,
  test_baseline_four_arm_period.py 72, test_four_arm_output_audit_nba.py 30, test_intel_prior_feature.py 16,
  test_nba_four_arm_primary_contrast.py 278, test_nba_state_enrichment.py 80,
  test_nba_state_enrichment_archive.py 10, test_forward_qualification_daily.py 31 -- all passed.

## REAL-ROW PROBE (orchestrator step)

PLACEHOLDER -- to be filled by the orchestrator: run the census ONCE, read-only, over the captured shard of a
Sunday slate; record the date, the row count and the per-field counts here. An empty shard is reported plainly --
the S348 ABSENT status stands until a run contradicts it. Nothing is scored, joined or charged.

## CORRECTIONS (tier 2, 2026-09-24)

1. `scripts/platformkit/ingame/nfl_state_field_census.py:35-42` -- `refuse_out` now checks both the abspath parts
   and the `Path(path).resolve()` parts, case-insensitively, so a junction or symlink that points into data/registry
   or data/cache is refused. Every text form that was refused before is still refused, and `data/registryX` is still
   allowed. Tests: `test_out_through_junction_into_data_cache_refused` (a real `mklink /J` junction, skipped only if
   the junction cannot be created) and `test_out_registryx_allowed`.
2. `scripts/platformkit/ingame/nfl_state_field_census.py:143-153` -- the atomic write is wrapped so that on any
   BaseException `<out>.tmp` is unlinked (missing_ok=True) before re-raising, and the target is never created.
   Test: `test_failed_write_leaves_no_tmp`.
3. `tests/platformkit/ingame/test_nfl_state_ingest.py:17-18` -- LANDED_KEYS is no longer a typed-out copy. It is
   computed at test time from the landed code as `set(_build_row('mlb', {'game_key': 'x'}, 'a', 'b', 'c', {}))`.

Re-run on 2026-09-24, one file at a time: test_nfl_state_ingest.py 18 passed (0 skipped),
test_state_capture_sources.py 240 passed, test_local_state_capture.py 19 passed.

## FIX 1b (AMENDMENT 1)

(a) Duplicate receipt keys. `scripts/platformkit/ingame/nfl_state_field_census.py:101-111` groups the parsed rows by
(game_key, response_end_utc) and compares each row's canonical JSON (sort_keys). A key whose rows are all identical
keeps one row; the extra copies are counted in `duplicate_identical`. A key whose rows differ is excluded from every
field count; every row involved is counted in `duplicate_conflict`. Both are strict ints beside `rows` (lines
126-128); the old `rows_duplicate_receipt_refused` key is gone. Tests:
`test_duplicate_identical_rows_count_once` (two identical rows with down 1 give rows 1, down present 1,
duplicate_identical 1; plus a mixed shard in both orders) and `test_duplicate_conflict_rows_excluded` (downs [1, 2]
under one key give rows 0, duplicate_conflict 2, in both orders). `test_census_reproduces_hand_counts` (both orders)
now asserts duplicate_identical 0 and duplicate_conflict 2 for rows E and F.

(b) Output under the capture root. `nfl_state_field_census.py:46-55` adds `refuse_out_under_root`: --out is refused
with `out_under_capture_root` when any of its abspath or resolved forms (normcased) is at or beneath any abspath or
resolved form of --root. `run` calls it after the data/registry and data/cache check (line 161). Test:
`test_out_under_capture_root_refused` (--root <tmp>/capture with --out capture/state/nfl/2026-09-27.jsonl, a
`..` path into the root, and the root itself; all refused; the shard's sha256 is identical after the runs and no
`.tmp` is left). The other tests now use <tmp>/capture as --root (helper `_write_shard`, test file line 171), so
their --out paths are outside the root.

Census file 197 lines, ASCII. Re-run on 2026-09-24, one file at a time: test_nfl_state_ingest.py 23 passed,
test_state_capture_sources.py 240 passed, test_local_state_capture.py 19 passed.

## FIX 1c (AMENDMENT 2)

(a) Duplicate key identity. `scripts/platformkit/ingame/nfl_state_field_census.py:115` keys duplicates by
(game_key, `json.dumps(response_end_utc)`), the canonical raw JSON value; the old `_label` form collapsed every
non-string (ints 1 and 2 both became `non_string:int`). Before grouping, lines 109-110 refuse a row whose receipt
time is invalid and count it in `receipt_time_invalid` (strict int beside `rows`, line 139). A VALID receipt time
is one `scripts.platformkit.execution.venue_time.parse_venue_time` accepts (lines 63-65): a zoned ISO string with
seconds, or a finite int/float epoch; bool, null, missing, unzoned or unparseable values are refused. Values are
never coerced: 1 and 1.0 are distinct keys, and so are `...18:00:00Z` and `...18:00:00+00:00`. Choice note: the
lane brief said to refuse non-strings, but the binding AMENDMENT 2 example requires ('g1', 1) and ('g1', 2) to give
rows 2, so numeric epochs accepted by the shared parser are valid. Regression in
`test_duplicate_conflict_rows_excluded` (both orders, test file lines 276-285): (1, 2), (1, 1.0) and the two ISO
spellings each give rows 2, duplicate_conflict 0, down present 2; True, '1', null, 'noon', [1] and a missing key
give rows 0, receipt_time_invalid 6, duplicate_conflict 0, duplicate_identical 0.

(b) Atomic replace covered. `nfl_state_field_census.py:187` runs `os.replace(tmp, out)` inside the guarded try,
so a failing replace also unlinks `<out>.tmp` (lines 188-190). Test `test_failed_write_leaves_no_tmp` (test file
line 234, now parametrized over json.dump and os.replace) patches `os.replace` to raise: no `.tmp` is left and the
target is absent.

Tests re-run on 2026-09-24, one file at a time: test_nfl_state_ingest.py 24 passed, test_state_capture_sources.py
240 passed, test_local_state_capture.py 19 passed. Test file 297 lines.

(c) This memo: line 3 now records AMENDMENT 1 and 2; section 4 states the final duplicate rules.

Census file 210 lines, ASCII.

## NOT VERIFIED

- No real NFL row was read by this lane. Every test payload is synthetic; the ESPN `situation` field paths (down,
  distance, possession, homeTimeouts, awayTimeouts) remain unobserved on a live payload (S350 NOT VERIFIED stands).
- Whether real ESPN NFL event dates use the minute-precision form that the schedule resolver leaves unavailable
  (section 5).
- `NFL_BOUNDS` ranges are declared from the rules of the game, not measured; an in-range but wrong value is not
  detected.
- Whether ESPN reports period 0 pre-game on a real payload (the construct fixture assumes it).
- The census `--root` layout (`state/nfl/<date>.jsonl`) is taken from `local_state_capture_io.py:142`; it was not
  run against the live capture root.
- The real-row probe (section above) has not been run.
- ncaaf rows (same poller) are not declared or counted by this row.
