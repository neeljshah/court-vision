# S314 TEACH-0 teacher packet qualification -- 2026-09-07 (ALIGNMENT HALF)

VERDICT: BLOCKED. The binding before-condition still does NOT hold after a successful play-by-play fetch: two of its five items were unblocked today (prior API history, final outcomes), three named items remain missing. Zero intervals staged, zero frames decoded, no signal qualified, no fraction scored. Spec `docs/evidence/tracking/specs/S314_spec.md` PREMISE: "If ANY item is missing, STOP and report BLOCKED naming the missing item". Calibration language only; no prediction-quality or teaching claim is made below. No prereg seal was written and none is owed (Q1: a seal precedes SCORING, and nothing was scored). No `pod_run` job ran -- pod access was read-only ssh, so there is no pod log tail and no pod code identity to record (A11). Census half: `S314_teach_packet_census_2026-09-07.md`.

## STEP 1 -- play-by-play fetch (the item the census named as missing): SUCCEEDED

Routing probed 2026-09-07 from this host: `stats.nba.com` read-timeout, `cdn.nba.com` 403, `site.api.espn.com` Akamai 403 "Access Denied" (so `memory/reference_live_data_routing.md` is now partly stale); `sports.core.api.espn.com` answered 200 and is the source used. `scripts/platformkit/espn_pbp_backfill.py` (225 lines, sha256 ad664d8c32cb1d5f9a0f29897cd90304b5100195615f446e7282e05bb7da056c) writes the EXISTING `data/nba/pbp_<game_id>_p<period>.json` layout in the schema `scripts/fetch_pbp_backfill_fast.py` emits, so no reader changes. URL patterns: events `.../nba/events?dates=YYYYMMDD`; plays `.../nba/events/<event>/competitions/<event>/plays?limit=1000`. Full provenance: `docs/evidence/harness/S314_pbp_fetch_provenance_2026-09-07.json`.

| game_id | date | home/away | ESPN event | as-of UTC | plays | rows p1/p2/p3/p4 | final home-away | derived / store home_win |
|---|---|---|---|---|---|---|---|---|
| 0022500575 | 2026-01-14 | DAL/DEN | 401810430 | 2026-09-07T22:52:12Z | 477 | 105/126/127/119 | 109-118 | 0 / 0 MATCH |
| 0022500594 | 2026-01-17 | ATL/BOS | 401810449 | 2026-09-07T22:52:25Z | 481 | 116/112/126/127 | 106-132 | 0 / 0 MATCH |
| 0022500630 | 2026-01-22 | DAL/GSW | 401810485 | 2026-09-07T22:52:41Z | 520 | 133/140/113/134 | 123-115 | 1 / 1 MATCH |

Each event id matched UNIQUELY by `AWAY @ HOME` against every event on its date (7, 9, 8 candidates; all listed in the provenance JSON). Every row carries period, elapsed `game_clock_sec` and source event order; strict clock decreases against ESPN `sequenceNumber` are 2/3/2 of 477/481/520 and are simultaneous-event ties, not reordering. Outcomes already existed in `data/nba/season_games_2025-26.json` (dated `home_win`), were NOT added, and all three agree with the fetched final score.
DEVIATION, declared: the spec BAN says "never write data/". The orchestrator dispatch explicitly authorised writing NEW fetched play-by-play into the gitignored `data/nba/` corpus cache as step 1. Writes are additive only (the module refuses to overwrite an existing period file), 12 new files; `data/registry/` untouched.

## STEP 0 re-measured -- the before-condition (pod snapshot 2026-09-07T22:57:46Z, read-only)

| item | 0022500575 | 0022500594 | 0022500630 |
|---|---|---|---|
| prior API history (PBP) | YES new today | YES new today | YES new today |
| final outcomes | YES home_win 0 | YES home_win 0 | YES home_win 1 |
| native source images | YES 11 mp4 segments | YES 10 mp4 segments | NO -- 0 mp4 |
| declared source PTS co-located with images | NO (item 2) | YES 2 segments | n/a no images |
| independent observation labels | NO (item 1) | NO (item 1) | NO (item 1) |

MISSING ITEM 1 -- independent observation labels, absent on all three; measured this session, not inherited. `tracking_capability.json` `ball_telemetry_available: false` (a PASS_NO_BALL corpus cannot qualify a ball signal); `resolver_debug.json` `slot_to_player_id` EMPTY, `assignment_active: false`, `roster_entries: 0`, every name `green#?` / `white#?` (no NBA player_id, so the P join key is unreachable); `team_colors.json` `{"green": "team_a", "white": "team_b"}` and `player_clip_stats.csv` `team_abbrev` EMPTY (colours are not authenticated team ids, so the S key is unreachable); `scoreboard_game_clock` populated in 0 of 46,791 tracking rows across all 18 segments; `scoreboard_period` populated but self-contradictory -- `0022500575_s2700` reports periods 1/2/3/4 inside a single ~152 s clip, so it is not a usable label; `harness_verdict.json` `passed: false`, `rung: IMAGE_PX_DECLARED`, `harness_coverage_pct: 0.0`.
MISSING ITEM 2 -- declared source PTS co-located with native images, absent for 0022500575: of its 11 mp4 segments only `_s1500` also has a tracking CSV, and that CSV declares `source_fps`, `source_height` and `source_duration` EMPTY. That broadcast has ZERO segments carrying images AND declared PTS AND tracking rows together.
MISSING ITEM 3 -- the ">= 2 broadcasts" count itself. Only 0022500594 has any such segment (`_s3900` 3,839 rows, `_s6600` 3,850 rows; both `source_fps` 30.0, `source_height` 360, `coordinate_space` `image_px`, `observation` `observed`). 1 broadcast < the 2 required, independently of item 1.

## Nested counts (strict nesting; denominators attempted, never surviving)

| stage | pod official ids | local union (census, inherited) | exclusion reason at this stage |
|---|---|---|---|
| N_footage | 3 tracked / 2 with native mp4 | 351 | 0022500630 has 0 mp4 at snapshot |
| N_API (PBP present) | 3 of 3 (was 0) | 22 (was 19) | none -- unblocked today |
| N_outcome (dated home_win) | 3 of 3 | 22 | none |
| N_images+declaredPTS+rows | 1 of 3 (0022500594) | not recomputed | 0022500575 `_s1500` declares no PTS; 0022500630 no images |
| N_qualified | 0 | 0 | no broadcast has independent observation labels |

ACCEPTANCE RULE, line by line: (a) ">= 90 pct of the 60 attempted intervals resolve uniquely ... within 1 game-clock second" -- UNMEASURED, N_attempted_intervals = 0 of 60, no interval table exists and no clock anchor was read; (a) "ZERO accepted replays" and "ZERO wrong-game joins" -- vacuous at n = 0, NOT reported as passes; (b) "labels agree >= 90 pct on the FULL attempted packet, abstentions counted as failures" -- UNMEASURED, no signal was preregistered because item 1 leaves no independent label to preregister. No bar was moved (Q3); the 90 pct bars and the 1-second tolerance are quoted from the spec unchanged.

## Tests

`python -m pytest tests/platformkit/test_espn_pbp_backfill.py -q` -> 10 passed in 0.47s (159 lines, sha256 54c344743538ac7472a4eb625f2e12a80424d655f2ddef39d48e1ef938477569).
Covers 3 of the spec's 5 fail-closed plants against the code actually shipped: WRONG GAME IDS (a no-match listing and an ambiguous two-match listing each raise, never fall back to a neighbouring event; correct-match and tricode-alias cases resolve uniquely), REVERSED CLOCK DIRECTION (ESPN reports seconds REMAINING, the local schema stores seconds ELAPSED; a reversed source is non-monotone against source order), REPEATED CLOCKS (identical clocks keep `sequenceNumber` order, never re-sorted by clock). Plus the additive-only overwrite rail and schema parity with `scripts/fetch_pbp_backfill_fast.py`.
Sign/units: `game_clock_sec` is integer seconds ELAPSED in period (tip-off 0, end of a regulation period 720, end of an overtime period 300); `score` is `home-away`; `score_margin` is home minus away. All three match the existing writer.

## NOT VERIFIED

- The CUT and REPLAY plants: they belong to the interval-alignment module, not built because step 0 blocked. No cut or replay was labelled or tested.
- Both acceptance fractions, per-signal `teacher_qualification`, frame identity, player continuity, every clock anchor. Nothing was decoded or OCR'd; EasyOCR was not run.
- Whether ffprobe of the mp4 containers could supply the PTS missing for `0022500575_s1500`. That is a re-derivation, not the producer declaration the spec asks for, and was not attempted -- but it is the cheapest named remediation path for MISSING ITEM 2.
- Box scores were NOT fetched (the before-condition does not name them); only PBP plus the pre-existing outcomes were used.
- ESPN `event_type` is a keyword heuristic over play type/text, not an NBA V3 code; not load-bearing for clock alignment and no claim rests on it. `player_name` (surname) and `team_abbrev` (tricode) come from ESPN athlete/team resolution and were not cross-checked against NBA ids.
- The corpus is LIVE, so these counts are a snapshot, not a frozen denominator: across two scans 8 minutes apart the pod gained a tracking segment (`0022500594_s6000`) and mp4 count moved 17 -> 21. A later scan may clear MISSING ITEM 2 for 0022500575 with no code change.
- The census's local-side figures (351 tracked, alias crosswalks, producer hashes) are inherited, not re-measured; only the three pod official ids were re-measured here.

## VERIFIER CORRECTION (added at landing, 2026-09-07; S314_VERIFY_2026-09-07.md)

The candidate snapshot above (18 CSVs / 46,791 rows / 1 broadcast with native
images plus declared PTS) was superseded by the verifier's re-measure of the
same pod official-id set: 21 CSVs / 54,722 rows, and all 3 broadcasts now carry
native images plus declared PTS. MISSING ITEM 2 and MISSING ITEM 3 are therefore
resolved; the count of still-missing items is 1, not 3 -- only MISSING ITEM 1
(independent observation labels, absent on all 3) still holds. The overall
verdict is unchanged: BLOCKED, N_qualified = 0, 0/60 intervals staged.
