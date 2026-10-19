# NBA opening-night readiness 2026-10-19 (for regular-season day 2026-10-20)

PAPER ONLY. This report is about calibration and coverage. It makes no ROI, edge or dollar claim.
Author: the NBA readiness lead (Opus). Run clock 15:26Z-16:1xZ 10-19. No code changed, no night run by hand,
no capture relaunched. The one write was the 10-20 D1 schedule (see row 1).

## Verdict

The 10-20 schedule, state capture and scoring of the nba cell are READY. Books polling is READY only while the runner stays up (see the addendum: since 15:59Z the 10-20 rows are carried in memory only). The live shadow
recorder is DEGRADED (see row 5), and the 10-19 recovery (row 2) depends on the next tick. The real risks for
10-20 are free RAM and the box going to sleep in the evening. The code paths are fine.

## Table

| Component | Verified how (artifact + as_of) | Status | Fix landed / proposed |
|---|---|---|---|
| 10-20 schedule, nba rows | The tick's own D1 (10-20) TIMED OUT at 607 s (status.json `schedule_attention`, seq 6, subject 2026-10-20, child_timeout; free RAM fell from 3.7 GB to 0.7 GB during the run). With no tick or schedule_d1 running and 1,412 MB free, I re-ran it ONCE with the tick's exact argv (`--now 2026-10-19T15:31:51Z`). Before: no 2026-10-20_* files, pointer on 10-16. After: WRITTEN in 2 m 20 s, exit 0, full 4 / served 4, `not_served` empty; pointer `day 2026-10-20 sha f321510a... written_at 15:34:12Z`. nba rows: KXNBAGAME-26OCT20BOSDET-DET (event 401909088, 19:00Z, season_type 2) and KXNBAGAME-26OCT20PHINYK-NYK (401909089, 23:00Z, season_type 2). Third game OKC@SA (401909090, tips 2026-10-21T01:30Z) refused `outside_utc_date`. | READY | none needed |
| Tip times | ESPN scoreboard?dates=20261020 (GET 10-19 about 15:38Z, timeValid true): BOS@DET 19:00Z = "3:00 PM EDT", PHI@NY 23:00Z, OKC@SA 01:30Z 10-21. Kalshi raw_market for the same events: close_time 10-22T19:00Z / 10-22T23:00Z / 10-23T01:30Z (tip + 48 h), expected_expiration 22:00Z / 02:00Z / 04:30Z. The schedule matches both sources, so the 19:00Z tip is real (an afternoon opener). | READY | none needed |
| Late tips (after 00:00Z) | Preseason schedules 10-12..10-16: post-midnight tips are served on the NEXT UTC day's schedule, so they are deferred, not lost. Examples: 26OCT12SASUTA (01:00Z) served on 10-13; 26OCT13GSWLAL / PORSAC (02:00Z) served on 10-14; 26OCT14DENLAC (02:30Z) served on 10-15. Some were unserved only by the live_concurrency capacity (10-15: four games at 00:00Z, one served; 10-16: OKCHOU 00:30Z unserved). So OKC@SA is covered only if the tick writes D1(10-21) on 10-20, before 01:30Z 10-21. | READY (conditional) | none. On full slates (8+ games from 23:00Z to 02:30Z), capacity (focus_game_capacity 3, max_live_overlap 2) will leave most games unserved. That is by design (S742). |
| 10-19 recovery (S715) | status.json `schedule:2026-10-19` = `deferred_low_ram` at 15:15Z (521 MB free; the light admission floor is 640 MiB = max_rss_mib.schedule 512 + LIGHT_RESERVE_MIB 128, paper_desk_limits.py). schedule_recovery/missing_dates.json was empty. No 10-19 schedule exists, so nothing is served today except what the 10-20 file holds: KXMLBGAME-26OCT192008CLETB-TB at 00:08Z 10-20 is on the 10-20 schedule. I did not run the 10-19 recovery: it is tick-owned and the next tick retries it. | READY (after the 15:56Z tick) | none; see the addendum |
| Books polling (kalshi nba) | kalshi/nba/_heartbeat.json (15:35Z): schedule_pointer_day 2026-10-20, scheduled_games_total 2, pointer_rows 4; the runner snapshotted `_schedule_f321510a...json` with no restart (local_capture_runner re-reads the pointer every tick via capture_schedule_loader). 10-min window: 753/753 book polls, n_429_10min 0. Preseason check: qualification 10-12/13/14 book_gap_p95 is 2,609-2,700 ms on every scheduled KXNBAGAME ticker inside its window. | READY | none |
| State capture (nba) | local_state_capture (pid 19012, --sports mlb,nba,soccer,tennis,nfl,ncaaf,wnba) polls the ESPN nba scoreboard by date. There is no preseason-only flag: rows carry ESPN's own season_type (1 preseason, 2 regular), and the 10-20 schedule rows already read season_type 2. 00:00Z boundary: MIA-BKN (tip 23:30Z 10-14) has live rows in 2026-10-15.jsonl from 00:00:05Z on. The per-day gaps (10-14 03:29Z-15:30Z, 10-15 00:33Z-15:42Z) are Windows sleeps (System event 42, reason 4, at 03:29Z 10-14 and 00:33Z 10-15), not capture failures. heartbeat 15:29Z fresh, 0 errors. | READY | none |
| Live shadow recorder + nba fit | DOWN since 10-13 01:08Z (supervisor_live_shadow.jsonl, last child_start 10-12 15:02Z). The recipe is docs/operations/relaunch_live_shadow_s780_2026-10-07.ps1 -Sports mlb,nba,nfl,soccer,tennis (dry-run command recorded). It needs at least 2,000 MB free (an owner condition, and also the supervisor's --min-free-mb). Free RAM was 1,339-1,648 MB, so a guarded watcher (launch only at >= 2,000 MB, with no live_shadow or paper_night process running, before 18:50Z) was armed at 15:37Z. Fit decision for 10-20 nba: `fit_missing` (live_shadow_fit_fallback reads 10-20, 10-19, 10-18; _fits/nba newest is 10-14). Every nba fit on disk (10-07..10-14) is `fit_warmup`, because nba history is `regular_only_v1` (nba_history_filter.py) and preseason rows never train. So nba quotes on arm A plus mid only, which is the correct state for opening night. mlb has no fits; nfl/soccer/tennis newest is 10-13, so they are also `fit_missing` for 10-20 until nights 10-17..10-19 run. | DEGRADED | none (RAM); see the addendum |
| Scoreboard nba scoring | nba IS scored. Night 10-12 (COMPLETE) ran ingame_scoreboard_night with --sports mlb nba soccer; scoreboard/2026-10-12.json has nba cells for arms A/B/C/D/B_lag/C_minus_B. Arm A and B_lag: 3 games, 3,431 ticks, INSUFFICIENT. B/C/D: `no_eligible_ticks` (counts model_not_reconstructible:B/C/D 10,624 for all sports, because TRAIN_FLOOR_GAMES = 20, embargo 3 d). The training manifests (scoreboard/training/2026-10-15.manifest.json) carry `nba_season_policy regular_only_v1`. PREREG_2026-10-07 says "nba already model-optional". Nights 10-13 and 10-14: the scoreboard was KILLED (step_deadline_exceeded) for every sport, the S824 issue, not nba-specific. | READY (arms B/C/D warmup until about 20 regular-season games settle) | none; no nba pre-registration is needed, so PREREG_NBA_PROPOSED was NOT written |
| Qualification expectations | qualification 10-12 / 10-13 / 10-14: all 11 nba served games FAIL (3 + 3 + 5). Best-covered game per slot: qualified_decisions 529-550, covered 1.27-1.35 M of 3.6 M ms. When two games share a slot, the second has 26-62 decisions, mostly RESERVATION_INVALID (global_cap 1); 26OCT12SASUTA had 0 (BOOK_CADENCE, state gap 3,056 s). Every game shows LINKAGE_INVALID about 720-770, NOT_LIVE 250-320, STATE_STALE 15-218 and STATE_GAP 1 (state_gap_max about 52-65 s; 225 s on 10-14 late games; 3,056 s on SASUTA). Expect the same FAIL shape on 10-20 (BOS-DET is alone in its slot; PHI-NYK overlaps the ncaaf row). | known FAIL (consumer side) | none new (existing rows) |
| fill_realism expectations | fill_realism 10-12/13/14 (COUNTS ONLY): nba intents 2,960-13,109 per night. All credited nba fills sit on NOT-served complement tickers (for example KXNBAGAME-26OCT12BKNWAS-BKN when -WAS was served). No served nba ticker is listed with a credited fill. Expect few or zero served-ticker nba fills on 10-20. | as expected | none |
| Nights backlog (tick-owned) | No night receipt for 10-15..10-18 (nights/ holds 10-14 as the newest). status.json `night` was last 10-16 03:56Z (night_skipped 10-15); census:2026-10-13 deferred_low_ram 15:15Z. Nights admit at 1,200 MiB (HEAVY_ADMISSION_MIB) plus their budget. Fits for 10-18..10-20 come only from those nights. | DEGRADED (tick-owned) | none |

## Focus windows (no python load from agents inside these; start - 5 min to start + 65 min)

- KXMLBGAME-26OCT192008CLETB-TB: 00:03Z-01:13Z 10-20 (tonight local)
- KXNBAGAME-26OCT20BOSDET-DET: 18:55Z-20:05Z 10-20
- KXNBAGAME-26OCT20PHINYK-NYK: 22:55Z 10-20 - 00:05Z 10-21
- KXNCAAFGAME-26OCT20USAMRSH-MRSH: 23:25Z 10-20 - 00:35Z 10-21
- OKC@SA (01:30Z 10-21): served only if D1(10-21) lands; window 01:25Z-02:35Z 10-21

## OWNER NEEDED (only things an agent cannot do)

1. FREE RAM. The tick admits schedule/census at 640 MiB free, nights at 1,200 MiB plus budget, and capture
   relaunch at 1,000 MiB (ongoing_min_free_ram_mib). The recorder relaunch needs 2,000 MB. Free RAM sat at
   300-1,650 MB this afternoon with the ChatGPT desktop app (5 processes, about 1.8 GB) and six claude
   sessions resident. Closing the ChatGPT app before 18:50Z 10-20 lets the recorder start and the backlog
   nights run. Agents must not close user apps.
2. KEEP THE BOX AWAKE 10-20 15:00Z through 10-21 03:00Z. Every recent evening ended in a reason-4
   (Application API) sleep: 03:29Z 10-14, 00:33Z 10-15, 03:59Z 10-16, 00:26Z 10-17. A sleep at about 00:30Z
   would cut PHI-NYK (23:00Z) at the half and lose OKC@SA (01:30Z) entirely.

## Rows needed

None allocated or invented. Every gap found is either tick-owned or an owner action.

## Addendum 16:10Z (after the 15:56Z tick)

- 10-19 recovery LANDED (tick-owned): status.json `schedule` = `schedule_complete`, 204.8 s, exit 0, D1 2026-10-19,
  full 4, served 3 soccer (KXSERIEAGAME-26OCT19MONCAG-MON 16:30Z, -PARTOR-PAR 18:45Z, KXEPLGAME-26OCT19TOTCOV-TOT
  19:00Z), 1 unserved (KXLALIGAGAME-26OCT19GETRVC, cap_concurrency). No nba on 10-19.
- POINTER MOVED BACK. The recovery republished maker_forward_pointer.json to day 2026-10-19 (written_at
  15:59:56Z). kalshi/nba heartbeat: schedule_pointer_day 2026-10-19, pointer_rows 0, carried_rows 7,
  scheduled_games_total 2. The 10-20 rows are still polled, but only as IN-MEMORY carry (schedule_pointer.py:
  `carry = [r for r in prior if _open(r)]`). After any books restart, the runner seeds from its CLI `--schedule`
  (the 2026-09-26 file) plus the current pointer, so the 10-20 rows would be dropped. That stays true after the
  tick writes D1(10-21) on 10-20 about 12:00Z, which moves the pointer to 10-21. This is the known "books restart
  drops same-day games" landmine, and today the pointer is behind the rows that matter. Books status for nba
  10-20: READY while the runner stays up, BLOCKED by any restart. Dispatcher decision: after the last 10-19
  served window closes (20:05Z 10-19), either republish the pointer at 2026-10-20 through the sanctioned path,
  or accept the in-memory carry and keep the box awake (OWNER NEEDED 2). The durable fix (seed a restarted runner
  from every still-open schedule on disk, not only the pointer) needs a row. I did not touch the pointer or the
  runner.
- A tick-owned backlog night is running: paper_night --date 2026-10-16 (pid 19328, started after 15:56Z).
  The backlog is moving.
- Recorder watcher: free RAM 1,087-1,379 MB at 16:03-16:09Z with the night running (busy=1), so not launched.
  The watcher is a background loop of this session and may stop when this session ends. The dispatcher should
  re-arm it, or launch with the recipe after the night ends, when free RAM is at least 2,000 MB and the time is
  outside 18:55Z-20:05Z / 22:55Z-00:35Z 10-20.
