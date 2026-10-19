GAP S624 | nfl (per-sport serving, 10-04 slate) | scratch root only (no worktree; no production edit) | builder-measurer: NFL-SUNDAY lead (Opus)
# NFL Sunday 10-04 serves 5 of 13 UTC-day NFL games under the global two-starts-per-rolling-hour rule; a measured proposal for the S531 landing: a sport-blind BINARY lane of N = 9 starts per rolling hour serves 13 of 13 (plus the NLDS G2) at zero extra request rate and ~zero extra RAM, with the cost moved to mid freshness of the non-focus served games

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md A, B, Q (S-row). PAPER ONLY; calibration and execution-quality language only. This row never edits schedule_d1.py, capture_scheduler.py or any production module; the LANDING is S531's (docs/evidence/tracking/specs/S531_spec.md + AMENDMENTS 1-2).

BEFORE (MEASURED, 2026-09-30 ~02:1xZ, master f3377a802, all read-only, probe RSS <= 41 MB):
- Slate: ESPN https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=20261004 (default urllib headers, HTTP 200, 248,927 bytes) lists 14 games: IND@WSH 13:30Z (London); ARI@NYG, DAL@HOU, GB@TB, JAX@CIN, LAR@PHI, NE@BUF, NYJ@CHI, TEN@BAL at 17:00Z; MIA@MIN 20:05Z; DEN@SF, KC@LV, LAC@SEA 20:25Z; DET@CAR 00:20Z 10-05. D1(2026-10-04) keeps UTC-day rows only (forward_schedule_writer.py:195, :203-204), so DET@CAR is outside_utc_date and belongs to D1(10-05): the UTC-day NFL denominator is 13.
- Kalshi public events (no auth): KXNFLGAME open 31, of which 14 are 26OCT04 (incl. -26OCT04INDWAS, -26OCT04JACCIN, -26OCT04DETCAR). KXMLBGAME open 6, none dated 26OCT04: the NLDS G2 at MIL 20:00Z (ESPN "Padres/Cubs @ MIL", away TBD) is NOT listed; it is modeled as listed in the tables below as a second case.
- Rule: schedule_d1._subset (:97-120) keeps a row iff fewer than 2 are kept or start - kept[-2].start >= 3600, globally across sports; capture_scheduler.schedule_rows (:111-113) raises 'schedule exceeds two games per hour' on any three consecutive starts spanning < 3600 s. Equivalent form (verified by the probe's assert on every scenario): keep iff the number of kept rows a with s - a < 3600 is < 2.
- Planner capacity (capture_scheduler.py, code-read): budget = rate x 5 s = 15 requests per tick at the 3 req/s ceiling (:145-147), FLAT, one runner for all sports; focus capacity = 15 x 45 // 100 = 6 tickers = 3 binary games (:179); a served game gets focus priority only in [start-120, start+3600) (:123); every tracked event is in the bulk rotation whether served or not (:201); non-focus markets get trades only when market_state == 'live' (:200).

10-04 SERVED TABLE (probe output, fixture tests/platformkit/execution/fixtures/s624/slate_2026-10-04.json; rows built as the writer writes them, see DISCLOSURES)
| S613 alias | NLDS G2 20:00Z | (a) landed global rule | (b) per-sport 2/h | (f) PROPOSED sport-blind binary N=9/h |
|---|---|---|---|---|
| OFF | unlisted (as on 09-30) | NFL 4/11: 17:00 ARI@NYG, DAL@HOU; 20:05 MIA@MIN; 20:25 DEN@SF | 4/11 (same) | NFL 11/11 |
| OFF | listed (modeled) | NFL 3/11 + MLB 1: ARI@NYG, DAL@HOU, NLDS 20:00, MIA@MIN | NFL 4/11 + MLB 1 (adds DEN@SF) | NFL 11/11 + MLB 1 |
| ON | unlisted | NFL 5/13: 13:30 IND@WSH; 17:00 ARI@NYG, DAL@HOU; 20:05 MIA@MIN; 20:25 DEN@SF | 5/13 (same) | NFL 13/13 |
| ON | listed (modeled) | NFL 4/13 + MLB 1: IND@WSH, ARI@NYG, DAL@HOU, NLDS 20:00, MIA@MIN | NFL 5/13 + MLB 1 (adds DEN@SF) | NFL 13/13 + MLB 1 |
Without S613, IND@WSH and JAX@CIN are refused missing_directional_team_evidence (denominator 11). Excluded by (a) with S613 ON, NLDS unlisted: GB@TB, JAX@CIN, LAR@PHI, NE@BUF, NYJ@CHI, TEN@BAL (17:00Z), KC@LV, LAC@SEA (20:25Z).
Other variants (S613 ON, NLDS unlisted; NFL served of 13; full lists in the probe output):
- (c) per-sport N per rolling hour: N=3 7, N=4 9, N=5 10, N=6 11, N=7 12, N=8 13.
- (d) sport-blind cap on simultaneously LIVE games (NFL 3.5 h, MLB 3.0 h): K=3 4, K=4 5, K=5 6, K=6 7, K=7 8, K=8 9. Worst family: a 3.5 h live window blocks the whole 20:05/20:25 slot behind the 17:00 slot.
- (e) sport-blind served-window cap (count of kept rows with s - a < 3720, the priority window): K=3 7, K=4 9, K=5 10, K=6 11, K=7 12, K=8 13 (identical to (c) on an NFL-only day).
Per-sport (b)/(c) gains only where MLB and NFL collide (+1 NFL on the NLDS case); it does not bound the shared resource, which is ONE runner's focus and bulk queue across sports.

PROPOSAL (for S531 to land; owned by S531, NOT this row). Binary lane = the landed comparison with 2 replaced by one constant, sport-blind:
- capture_capacity.py: BINARY_PER_HOUR = 9. served_subset binary part: `if len(kept_binary) < BINARY_PER_HOUR or s - kept_binary[-BINARY_PER_HOUR].start >= 3600: keep` (today: 2). check() binary part: `any(b - a < 3600 for a, b in zip(starts, starts[BINARY_PER_HOUR:]))` -> BINARY_ERROR (today: starts[2:] at capture_scheduler.py:113). BINARY_ERROR text unchanged ('schedule exceeds two games per hour'; stale wording disclosed, as S531 A14 does for RULE) so schedule_pointer :91 / CAPACITY_ERRORS keep matching.
- schedule_d1.py: _subset :117-119 goes through served_subset (S531 already moves it). RULE text byte-identical (S531 A14); the capacity note gains key binary_per_hour: 9 ONLY when BINARY_PER_HOUR != 2, so paper_desk_schedule.validate (:67-73, the paper-desk owner's copy, already in S531 A6's three-place change) recomputes with note.get('binary_per_hour', 2): committed 2-rule publications keep validating, new ones validate at 9.
- Why 9, sport-blind: the constraint is shared (focus 3 games + served-first bulk, one runner). Nine is the largest NFL kickoff slot seen (9 at 17:00Z on 09-27, fetched, and on 10-11 per S531 text; 8 on 09-20 and 10-04, fetched). With S531 B4 served-first bulk (bound 10 s x Q, Q = served non-focus games in window), 10-04 peaks at Q = 5 (50 s); the 10-11 model (NFL + S531's 16 soccer kickoffs) peaks at Q = 11 at 17:00Z (110 s), inside S531's 120 s bar. N = 8 serves 12/13 on 10-11 (Q 10); N = 10 adds nothing on any fetched slate.
- Why not a live-game cap (d): it blocks the late slot for 3.5 h behind 17:00Z although focus priority ends at start+3600; freshness pressure is a first-hour quantity in this planner.

COST (MEASURED unless labelled)
- Request rate: delta 0 per served game. The books budget is flat (15 per tick); serving only reorders focus and (after S531) bulk. Live heartbeat (global runner, 3 samples 02:1xZ 09-30): current_req_per_sec 3.0, n_requests_10min 1505-1524 (2.51-2.54 req/s), requests_by_class per tick focus_books 6, trades 5, bulk 1, discovery 0-1, reserve 0; n_events_tracked 47, n_markets_tracked 468. State side (code-read, local_state_capture_sources.py:264-296, espn_play_clock.py:142-190): NFL costs ONE ESPN scoreboard GET per poll for all games plus one play-clock GET per new play id per LIVE game, for every live game whether served or not; serving adds 0 ESPN requests.
- RAM: delta ~0 per served game (INFERRED from code: every event is tracked and bulk-rotated regardless of serving; serving adds a schedule row and a schedule_ids entry). Live psutil RSS, read-only, 3 samples 02:1xZ 09-30 (no game live): local_capture_runner pid 24724 265.4 MB, polymarket_live_capture pid 11340 263.6 MB, local_state_capture pid 20108 83.8-84.1 MB, 6 supervisors/launchers 1.7-5.1 MB each; available 1490-2036 MB of 15481 MB. S531 recorded the runner at 711 MB (one sample, ~21:30Z 09-29, MLB live): RSS varies with other state, not with the served count.
- Freshness, the real cost (books archive, scratch books_age.py, streamed, probe RSS 21 MB): focused served NFL game (MNF 09-29 PHI@CHI, in-game [kickoff, +3.5 h)): refresh gap p50 5.1 s, p90 5.6 s, max 8.0 s (n 1382). Bulk-only NFL game (TNF 09-25 ATL@GB): p50 1167.8 s, p90 1426.4 s (n 22). Busiest real multi-game window in the archive (MLB 09-22 UTC): 11 in-game events, peak 8 concurrent (23:50Z), focus rows for at most 2 events in any 10-min bucket; focus p50 5.2 s / p90 5.8 s; bulk p50 1094.4 s / p90 2044.1 s. So today a served game outside focus is scored from mids ~18-34 min old; the S531 B4 bound (10 s x Q) is arithmetic, not observed.
- No real multi-game NFL window exists in the archive: books NFL starts 2026-09-21 (Sunday 09-20 afternoon absent), Sunday 09-27 is in the 09-25..28 outage, and SNF 09-21 / 09-28 have 0 in-game snapshot rows.
- RAM budget: ~1.5-2.0 GB free with live captures; N = 9 does not add a process, a tracked event or a request.

CASES for S531 to adopt (bar = all pass)
1. Construct: 9 binary rows at one instant -> 9 kept; a 10th -> dropped; [0 x 9, 3600] -> 10 kept; [0 x 9, 3599] -> 9 kept and check raises BINARY_ERROR on the 10-row list.
2. Construct: BINARY_PER_HOUR = 2 reproduces today's _subset on every committed full selection 2026-09-22..09-30 (served lists equal); with 9, 09-24/26/29/30 are unchanged (full == served) and 09-22/23/25 grow 3 -> 6 (history is never rescored).
3. Real fixture (S613 alias applied, NLDS unlisted): 13 UTC-day NFL rows -> served 13; landed rule 5 exactly [IND@WSH, ARI@NYG, DAL@HOU, MIA@MIN, DEN@SF]; without the alias 11 rows -> 11; with the modeled NLDS row -> 14.
4. Planner: a schedule of 8 NFL rows at one start -> focus_games 3 (6 tickers), scheduled_not_admitted 5, no refusal; the 5 lead served-first bulk (S531 B4) within 10 s x 5.
5. Pointer + old reader: the base-commit schedule_rows raises on the case-3 served file; the new check passes (relaunch evidence, S531 A4).
6. paper_desk_schedule.validate: a committed 2-rule publication (no binary_per_hour key) still validates; a 9-rule publication with binary_per_hour 9 validates; a 9-rule served file with the key missing -> invalid_capacity_subset.
7. Mixed lanes on 10-11 model: NFL 9 x 17:00Z + soccer windows -> binary served counts equal N-rule counts computed without soccer (no cross-lane displacement).

DISCLOSURES
(a) Rows are built by the probe from the fixture (game_id = Kalshi event, ticker = event + '-' + HOME Kalshi code, selected_at 2026-10-03T12:00:00+00:00), matching the committed *_maker_forward.json shape and the writer's team-set link path; build_schedule itself was NOT run for 10-04 (the combined mlb+nfl writer run exceeded 400 MB in S531). S613 case 5 confirms the two alias links on the landed _choose.
(b) The NLDS G2 row is modeled (ticker KXMLBGAME-26OCT041600TBDMIL, invented shape; no event is listed).
(c) Timing: D1(10-04) runs at 12:00Z 10-03 and S531's deadline is 10-07. 10-04 benefits ONLY if S531 (binary part), the paper-desk three-place change and the relaunch of BOTH the books runner and polymarket_live_capture land between games before 12:00Z 10-03 (safe window about 04:00Z 10-02 .. 12:00Z 10-03, after TNF and around the 10-03 ALDS games). Otherwise 10-04 serves 5/13 (S613 on) or 4/11 (off).
(d) NFL in-game snapshot rows carry market_state 'pregame' (MNF 09-29, 1384 rows): NFL is absent from kalshi_series_scope.TYPICAL_DURATION_SEC (default 150 min), so non-focus served NFL games get no trades for much of the game (capture_scheduler.py:200). S561 territory; not changed here.
(e) A regular-season MLB day can now serve up to 9 starts per hour (real peak 8 concurrent on 09-22), raising Q on those days; the 120 s arithmetic bound holds only while Q <= 12 across lanes.

NOT VERIFIED
- No multi-game NFL capture window exists (09-20 absent, 09-27 outage); the NFL freshness numbers are single-game windows plus the MLB 09-22 multi-game proxy.
- The 10 s x Q bound depends on S531 B4, not yet built; the 10-11 Q = 11 is a model from S531's listed kickoffs.
- RSS during a live NFL Sunday is unmeasured; the samples are off-hours.
- No code in this row was run against a live runner; no test file was added (S531 owns them).

FOR the soccer-readiness lead (S531)
1. Parameterise the binary lane: BINARY_PER_HOUR = 9 in capture_capacity (served_subset uses kept[-N], check uses starts[N:]); error text unchanged.
2. Evidence: 10-04 NFL served 5/13 -> 13/13 (S613 on), + NLDS G2 if listed; request delta 0; RAM delta ~0; cost = bulk-age of served non-focus games.
3. Q bound with soccer: 10-04 peak Q 5 (50 s); 10-11 model peak Q 11 (110 s) <= your 120 s bar. N=8 gives 12/13 on 10-11.
4. Your byte-identity days 09-26/29/30 are unchanged at N=9 (full == served).
5. Note key binary_per_hour only when != 2; paper_desk_schedule.validate reads it with default 2 (add to your A6 owner change).
6. Relaunch books runner AND polymarket before the first N=9 D1 publication (old :113 refuses the whole pointer).
7. If you land after 12:00Z 10-03, 10-04 stays at 5/13; the first NFL Sunday with the rule is 10-11.
8. Fixture: tests/platformkit/execution/fixtures/s624/slate_2026-10-04.json (sha256 c58b1144...f81c9; add `text eol=lf`).
9. Probe: docs/evidence/harness/S624_serving_probe.py (asserts sport-blind N=2 == landed _subset).
