# S502 -- ESPN minute-precision schedule starts (build memo, candidate)

Row: S502 (register docs/evidence/HARNESS_GAPS_2026-09-03.md). Spec: docs/evidence/tracking/specs/S502_spec.md
with AMENDMENT 1 (binding). Worktree nba-harness-h342, branch harness-h342.
Verification base (pinned, full sha): 9cfb62412cebf7ec5e4046121a28e5f8be101e2e.
Rebased onto master e8cf0ae04 (intervening commits touch the spec, the paper-desk ledger and governance tests
only; `git diff --quiet` shows both capture modules unchanged since the pinned base the before fixture keeps). Commit 1 (data/fixture): a3892a0f221b9950e1a0c26b85b9689039156645. Commit 2:
be46464168e23a8b8d9618d17d61577d5a24b1a4. The AMENDMENT 3 commit (tests, generator text, memo) is
reported by `git rev-parse HEAD` in the hand-back; a commit cannot name its own sha.
Candidate HEAD vs verification base: NOT EQUAL (two commits on top, unlanded, PARKED per clause (O)).

## What changed

- NEW scripts/platformkit/ingame/schedule_instant.py `normalize_start(raw, event, comp) -> (value, refusal)`.
  A str that fullmatches the ASCII pattern YYYY-MM-DDTHH:MMZ gets ':00' seconds before the Z; every other
  value is returned unchanged. A rewritten value whose event or competition says timeValid false is
  refused as 'schedule_time_unconfirmed' (value None). The helper does not select the start field.
- local_state_capture_dates.py `schedule()`: one call to the helper after the landed selection line; a
  refusal is reported once through the landed `report`, and no timestamp_parse_errors is counted on that path.
- local_state_capture_sources.py `_evidence`: its landed selection expression is wrapped by the helper
  (same line); the dates import line gains the helper import. It never reports. Line count stays three hundred.
- venue_instant, venue_time.py, forward_schedule_sources.py, local_state_capture.py, game_market_link.py,
  forward_capture_bridge.py, microstructure_features.py, registry_scorer_e_*.py are unchanged.

## Acceptance: thirty-six of thirty-six ids pass after; before measured by the power run

Before = the new test files run against the pre-edit blobs of dates.py and sources.py at the base sha
(swapped in, then restored; tree clean). After = the candidate.

| id | before | after |
|---|---|---|
| n_minute_z | FAIL | PASS |
| n_seconds_identity | PASS (unchanged, not claimed) | PASS |
| n_fractions_one_to_nine | PASS (unchanged) | PASS |
| n_offset_minute_refused | PASS (unchanged) | PASS |
| n_shape_refused | PASS (unchanged) | PASS |
| n_calendar_refused | PASS (unchanged) | PASS |
| n_calendar_boundaries_accepted | FAIL | PASS |
| n_non_str_passthrough | PASS (unchanged) | PASS |
| s_no_zone | FAIL | PASS |
| s_minute_equals_seconds | FAIL | PASS |
| s_dst_boundaries | FAIL | PASS |
| s_invalid_zone | FAIL | PASS |
| s_official_date | FAIL | PASS |
| s_precedence | FAIL | PASS |
| s_time_unconfirmed | FAIL | PASS |
| s_unzoned_local_seconds | PASS (unchanged) | PASS |
| r_equal_minutes | FAIL | PASS |
| r_minute_vs_seconds | FAIL | PASS |
| r_different_minutes_conflict | FAIL | PASS |
| r_rank | FAIL | PASS |
| r_partial | FAIL | PASS |
| r_merge_schedule | FAIL | PASS |
| r_tbd_transition | FAIL | PASS |
| f_nfl | FAIL | PASS |
| f_nba | FAIL | PASS |
| f_wnba | FAIL | PASS |
| f_soccer | FAIL | PASS |
| f_tennis | FAIL | PASS |
| f_ncaaf_route | FAIL | PASS |
| f_mlb_unchanged | PASS (unchanged) | PASS |
| w_forward_writer_byte_equal | PASS (unchanged) | PASS |
| l_keyed | PASS (unchanged) | PASS |
| l_keyless_no_date | FAIL | PASS |
| l_bridge_metadata | PASS (unchanged) | PASS |
| q_serialization_round_trip | FAIL | PASS |
| q_partial_failure_and_types | FAIL | PASS |

Totals: before twenty-five FAIL and eleven PASS; the eleven unchanged ids are byte-equality guards and are
not claimed as fixes of this row. After: twenty-three passed (test_schedule_instant.py) and thirteen passed
(test_schedule_instant_e2e.py).

Real-fixture facts (from the tests, verbatim tracked payloads): every nfl, nba, wnba and soccer row now has a
start, date None and date_reason missing_local_timezone (none of these payloads carries a zone). Tennis atp:
fifty-three competitions with timeValid false are refused (schedule_time_unconfirmed fifty-three times), the
other sixty-six get their competition start, never an event (tournament) date; stripping the competition
starts leaves every tennis start None. The s430 nfl file stores {US date: [events]} and is wrapped as a
scoreboard (events verbatim). f_ncaaf_route is an adapter-route proof (the nfl payload through ncaaf_poll,
same `_nfl_league_poll` code), not an ncaaf payload. Every poll requested only scoreboard URLs.

## Adversarial mutants (sixteen run, sixteen killed; killer ids)

- fullmatch to match: n_shape_refused
- [0-9] to \d: n_shape_refused
- normalize offset minute forms: n_offset_minute_refused
- accept lowercase z: n_shape_refused
- fix schedule() only: r_different_minutes_conflict, r_minute_vs_seconds, r_partial, r_tbd_transition
- fix `_evidence` only: n_minute_z, n_calendar_boundaries_accepted, s_* (seven ids), r_* (seven ids), f_* (six ids), l_keyless_no_date, q_* (two ids)
- drop the timeValid refusal: s_time_unconfirmed, r_tbd_transition, f_tennis
- apply timeValid to seconds forms: s_time_unconfirmed, w_forward_writer_byte_equal
- read comp.timeValid only: s_time_unconfirmed, r_tbd_transition, f_tennis
- read event.timeValid only: s_time_unconfirmed, r_tbd_transition
- also count timestamp_parse_errors on refusal: s_time_unconfirmed
- do not report the refusal: s_time_unconfirmed, f_tennis
- rewrite fraction forms: n_fractions_one_to_nine
- default a zone (America/New_York) when none is declared: over twenty ids incl. f_nfl, l_keyed, w_forward_writer_byte_equal
- swap date and startDate order: s_precedence
- fall back past a truthy unparseable value: s_precedence, s_time_unconfirmed, n_* (four ids), s_unzoned_local_seconds

AMENDMENT 3 (b): mutant x3 (`_evidence` normalises only when neither event nor competition has a timeValid
key) survived round one; two timeValid-true rows (event and competition, the real ESPN shape) were added to
r_different_minutes_conflict and r_minute_vs_seconds, and x3 is now killed by both ids ("2 failed, 21 passed"
in test_schedule_instant.py). AMENDMENT 3 (a): the generator writes the fullwidth-digit case with
backslash-u escapes; s502_before.json regenerated byte-identical (LF sha256
c0f7dfa21623155e37a5f7ec1840a4fb88de3d42f4b4ad0ec03b83d55068565a before and after).

Not run: "skip calendar validation" (the helper performs none; venue_instant judges the rewritten form,
guarded by n_calendar_refused), "report from `_evidence`" (guarded by r_tbd_transition, which asserts the
shared SOURCE_METRICS is unchanged by `_evidence`), "share the comp guard" (the helper takes the comp each
caller already built; s_precedence pins the landed AttributeError for competitions [None]).

## Seals (clause L)

No committed seal or identity list names a file this row modifies: PREREG_* (ingame_scoreboard*,
walkforward, baseline_four_arm*), PREREG_E_2026-09-25 (ingame_scoreboard, microstructure_features), the
S490 dependency addendum (cross_venue_link, game_market_link, soccer_aliases, soccer_crosswalk),
BLOCK_CONFIG_E_* and CALLER_POLICY_E_2026-09-30 (no file names), arm E IMPLEMENTATION_FILES, the S475
list, m2_readout_io PINNED / PROVENANCE. tests/platformkit/ingame/fixtures/s542_seal.json is the S542
build's landing-time must-not-move list and no test reads it; its dates.py pin moves to NOT EQUAL as its
sources.py and local_state_capture.py pins already did after S595 and S606. s494_evidence.py names
venue_instant, which is byte-identical.

## Population disclosure (clause M)

From adoption, ESPN state rows carry starts, so the landed bridge rule (two different non-missing starts
within one game drop the key as conflicting_state_linkage, forward_capture_bridge `_metadata`) applies to
ESPN sports as it already does to MLB (l_bridge_metadata). A null row next to a started row never conflicts,
so the adoption boundary is safe. Keyed linkage itself reads neither the start nor the date (l_keyed: old null
rows and new rows give the same key and reason no_game_date), but a game whose ESPN start changes within one
night is dropped from the keyed population by the landed bridge rule (forward_capture_bridge.py: two different
non-missing starts give conflicting_state_linkage, then state_key_conflicted); before this row that could not
happen for ESPN sports because every start was None. Second disclosure: an ESPN game whose time flips to TBD
(timeValid false) keeps its remembered start, marked partial, under the landed local_state_capture
`_merge_schedule` memory rule (checked on the candidate: remembered start kept, verdict partial). Third: in the
live D1 schedule writer, a minute-Z startDate behind a falsy date would now parse where it read None before
(forward_schedule_sources normalises only the date field); no tracked fixture has that shape, so
w_forward_writer_byte_equal does not exercise it. This row creates no dates; the register's date=null
half stays open. The declared-zone fill of S477 (read side) dates a fixed row: America/Chicago gives
2026-09-28 for the Eagles at Bears start (l_keyless_no_date).

## Landing without adoption (clause P)

Grep of scripts/ for importers of local_state_capture_dates / local_state_capture_sources: the non-capture
ones are forward_schedule_sources.py (imports schedule and venue_instant), nba_history_filter.py,
registry_scorer_e_night_fields.py, game_market_link.py, microstructure_features.py (venue_instant only,
unchanged), cross_venue_pairs.py (`_MLB_STATUS` only), s494_evidence.py / soccer_s490_* / s481_memo_facts.py
(file names in evidence tooling). `_evidence` has no caller outside local_state_capture*.py (nba_pbp_starters
has its own unrelated `_evidence`). So the only non-capture caller of schedule() is forward_schedule_sources.py,
and w_forward_writer_byte_equal shows its rows and counters byte-equal over every tracked ESPN fixture.
Landing alone therefore changes no value computed from archived rows by the paper night, the scoreboard,
arm E, the D1 schedule writer or the tick; the running capture keeps the old code until restarted.

## Rulings (AMENDMENT 2) and remaining notes

1. Per AMENDMENT 2, three landed test files that pinned the pre-fix behaviour joined the owned list with
   minimal edits (commit 2): test_nfl_state_ingest.py (the minute-start test now expects the parsed start,
   renamed ..._parses_with_the_same_key_set), test_wnba_registration.py test_real_pre_state (the two verbatim
   WNBA rows now carry their starts), test_soccer_capture_fix1b.py (the "missing" row's real competition
   minute starts are also nulled so it stays start-less, restoring that test's premise).
2. Per AMENDMENT 2, the relaunch script also changes the launch message text (it named S535); its header is seven lines.
3. Per AMENDMENT 2, an int start (5) is read as an epoch by the landed parser before and after;
   q_partial_failure_and_types pins it unchanged rather than refused.
4. Memo numbers are quoted from the test runs of this candidate, not from a separate generator script.
5. Pre-existing on the base, not caused here: test_nba_pbp_starters.py test_i03 byte-pins
   local_state_capture.py and fails on 9cfb62412 as well.

## Landing plan (AMENDMENT 3 (d))

After S492 commit B lands: `git rebase master` in h342 (union-merge .gitattributes: keep every master line and
add this row's line; test_nfl_state_ingest.py merges cleanly per merge-tree); re-run per file
test_nfl_state_ingest.py, the two new test files and the three spec-body files; a short contract-tier r2
(rebase-only check); then land by hand (per-file tests, preflight gated on zero FAIL lines, cherry-pick of the
commits, per-file tests on main), register and ledger, and an adoption item under PENDING ADOPTIONS with the
06:00Z-16:00Z rule and the post-adoption check below.

## Adoption (clause K; not run by the build)

docs/operations/relaunch_state2_s502_2026-10-01.ps1, argv identical to the s535 script (tennis ON). Owner or
session cron, between games, 06:00Z-16:00Z, never a scheduled task. Record: supervisor child_start; per ESPN
sport the first shard row after it with a start, date None, date_reason missing_local_timezone; heartbeat
timestamp_parse_errors no longer equal to rows_written per ESPN sport; schedule_time_unconfirmed per sport;
the next night's conflicting_state_linkage and state_rows_missing_start per ESPN sport.

## NOT VERIFIED

- Live rows after adoption for every ESPN sport (the capture was not restarted by the build).
- Live ncaaf payload shape (no tracked ncaaf scoreboard; adapter route proven only).
- Live nba payload shape this season (NBA regular season starts later in October).
- Tennis live refusal volume (fixture shows fifty-three of one hundred nineteen refused).
- No archived row was changed; link rates on real nights were not re-measured.
