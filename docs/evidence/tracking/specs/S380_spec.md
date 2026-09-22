GAP S380 | sport nfl | worktree harness-h36 (master-based) | log cx_s380_nfl_live_situation
# NFL live situation-field verification from archived live rows (design: ASTRA_ROUND13 section 1 row 10)

SINGLE PROBLEM: domains/nfl/ingest_nfl_states.py (row S350) leaves yardline_100 as None with status "semantics_unverified" and the
possession / down / distance / timeout mappings have only ever seen fixtures. NFL late-game cohorts and any state-dependent replay
need those fields, and a wrong orientation would silently mirror the field.

BINDING BEFORE-CONDITION: `ls domains/nfl/verify_live_situation.py` fails. Read domains/nfl/ingest_nfl_states.py and quote how
each raw field is produced (the live state capture that calls it is not on master yet; the row below is its real output).

REAL ROW, VERBATIM (data/cache/ingame_books_local/state/nfl/<date>.jsonl; this one is a finished game, so the situation fields are
null -- LIVE rows carry them): {"away_abbr":"IND","capture_ts":"2026-09-21T22:08:52.844622Z","capture_version":
"local_state_capture_v1","date":"2026-09-21","game_key":"401872945","home_abbr":"KC","http_status":200,"raw_sha256":"c101...",
"request_start_utc":"2026-09-21T22:08:52.844622Z","response_end_utc":"2026-09-21T22:08:53.210435Z","source_ts":null,"sport":"nfl",
"state":{"away_score":30,"away_timeouts":null,"clock_seconds_remaining":0,"distance":null,"down":null,"down_distance_text_raw":
null,"game_seconds_remaining":0,"home_score":33,"home_timeouts":null,"is_red_zone":null,"last_play_id":null,"period":5,
"possession_team":null,"possession_team_id_raw":null,"possession_text_raw":null,"yard_line_raw":null,"yardline_100":null,
"yardline_100_status":"semantics_unverified"},"state_changed":false,"status":"final"}

CHANGE (NEW files only; the S350 adapter is NOT edited -- wiring is a later row):
1. domains/nfl/situation_normalize.py (<= 300 LOC): pure functions. `parse_down_distance(text) -> (down, distance) | None`;
   `yardline_100_under(hypothesis, yard_line_raw, possession_text_raw, possession_team, home_abbr, away_abbr) -> int | None` for the
   declared hypotheses H_OWN_GOAL (raw counts from the offense's own goal line), H_HOME_GOAL (raw counts from the home goal line),
   H_TEXT ("KC 35" style text: side-of-field abbreviation + yard number). Missing or contradictory inputs -> None, never a guess.
2. domains/nfl/verify_live_situation.py (<= 300 LOC): `--state-file <jsonl> [...] --out <json>`; per game, order rows by
   response_end_utc (ties by capture_ts; conflicting rows with one receipt identity are counted and skipped) and test each
   hypothesis against OBSERVED transitions only: (a) within one possession and one drive, a play that reduces `distance` by d with
   the same series must move yardline_100 by about d toward the goal; (b) a touchdown (+6 to the possessing team) must come from a
   small yardline_100 on the previous live row or be flagged as a long score, never assumed; (c) is_red_zone true must agree with
   yardline_100 <= 20; (d) a possession change must flip the orientation under H_OWN_GOAL and not under H_HOME_GOAL; (e) timeouts
   never increase within a half; (f) the clock never increases within a period. Output: per hypothesis support / contradiction /
   untestable counts, games and distinct possessing sides that contributed, and a verdict VERIFIED only when one hypothesis has zero
   contradictions, at least 30 supporting transitions, at least 2 games and BOTH home and away possessions; otherwise UNVERIFIED with
   the reason. Counts only; strict ints; order-independent; no score prediction of any kind.
3. tests/domains/nfl/test_verify_live_situation.py and tests/domains/nfl/test_situation_normalize.py (mirror the existing tests
   layout for domains/nfl; if none exists use tests/platformkit/ingame/ and say so): a synthetic drive under each hypothesis, a
   mirrored-field trap that must produce contradictions, null situation rows (pre / final) are untestable not contradicting,
   threshold edges, order independence.
4. Memo docs/evidence/harness/S380_nfl_live_situation_2026-09-21.md (the orchestrator runs the real archive after tonight's game).

CONTROLS: PREPARE only, NEW files only, construct tests, no network, no real archive run by the builder. ACCEPTANCE: per-file tests
pass; --help works; diff = NEW files only; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list.

AMENDMENT 1 (2026-09-22 01:1xZ; binding; from the first two runs on REAL live rows). (a) The state capture writes status "live"
for an in-progress game (vocabulary: pre / live / final); "in" is kept only if the S350 adapter emits it; any other status is a
counted refusal. (b) The archive carries NO drive, series or play-type field, so the tool INFERS them, deterministically, from
consecutive live rows of one game ordered by response_end_utc: a DRIVE is a maximal run of rows with the same possession_team and
no change in either score; a SERIES inside a drive starts at every row whose down == 1 and ends before the next such row; a
PLAY is any change of (down, distance, yard_line_raw, last_play_id) between consecutive rows; rows with a null possession_team,
down, distance or yard_line_raw are untestable for the situation checks but still count for clock and timeouts. (c) The distance
check runs INSIDE a series: for consecutive plays with the same possession and down increasing by exactly one, distance must
decrease by exactly the yardline_100 movement toward the goal under the hypothesis (|delta_distance - delta_yardline| <= 1 yard
supports; a larger disagreement contradicts; a new first down or a possession change ends the series and is not a contradiction).
(d) The possession_change check: at the first row of a new drive, compare yardline_100 under the hypothesis with the last row of
the previous drive: under the own-goal hypothesis the value must flip to about 100 minus the previous value (within 3 yards, or
after a kickoff / punt any value is untestable); under the home-goal hypothesis it must NOT flip; the text hypothesis is judged
by whether "<TEAM> <yards>" resolves consistently for BOTH teams' possessions. (e) The touchdown check: a +6 (or +7 / +8 with the
conversion) for the possessing team between consecutive rows must follow a row whose yardline_100 <= 40 under the hypothesis or
be counted as long_score (never a contradiction). (f) `games` and `sides` in the report count the games and possessing sides that
contributed at least one testable situation transition (not clock / timeout support). (g) The real fixture
tests/domains/nfl/fixtures/s380_real_live_rows_2026-09-22.jsonl must produce a NON-ZERO testable count for distance,
possession_change and touchdown under at least one hypothesis, or the memo must state exactly which inference rule the real rows
defeat and why. Thresholds for VERIFIED are unchanged.

AMENDMENT 2 (2026-09-22 01:3xZ; binding; clarifies AMENDMENT 1(a), which a verifier read as 'only live and in are accepted').
The ACCEPTED status set is exactly {pre, live, in, final}: pre and final rows are accepted rows (they bound games and drives and
count for nothing else -- untestable for every check), live and in rows are the live rows the checks run on, and any status
outside that set is a counted refusal (`status_refused`). A row with a missing status is refused and counted. This is what the
fix-2a / 2b candidate implements; no code change is required by this amendment beyond a test that names the accepted set.

