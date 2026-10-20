<!-- Tracked twin of the local memo docs/research/QUALIFICATION_CENSUS_2026-10-20.md (go session, 2026-10-20 ~17:5xZ); register intake row S831; read-only census, no desk file was changed. -->

# Qualification census, served games 2026-10-06 .. 2026-10-16 (as of 2026-10-20)

PAPER ONLY. Read-only census for improvement-map item 3 (`docs/research/PROJECT_IMPROVEMENT_MAP_20261020.md`
section 2). Operations and calibration language only: qualification grades the captured tape, not the
model, and nothing here is a forecast-quality or money figure. Every count below is read from a file
named beside it; the extraction script (stdlib, read-only) was run from the session scratchpad and its
logic is described in section 6 so the counts can be reproduced.

**Answer in one paragraph.** 113 games were served 10-06..10-16 (`schedules/<D>_maker_forward.json`).
79 of them were never judged: three qualification steps were killed before writing a receipt
(10-07, 10-08, 10-09; 45 games), the 10-10 receipt was refused `undeclared_sport` (26 games) and night
10-15 never ran (8 games). Of the 34 served games that were judged, 11 had no capture at all because
the laptop was asleep, and **the other 23 games, which had live capture, all fail COVERAGE_LOW**. The
best covered game since 10-06 reached 80.5 pct, below the 90 pct floor. After S767 (half-tick repoll,
adopted 10:49Z 10-06), the median book gap fell from about 5.2 s to 2.45 s. On those
nights a game with no concurrent rival covers almost exactly one book gap per qualified decision, and
about half of its decisions are RESERVATION_INVALID. That pattern caps coverage near 47 pct. No register
row owns that coverage pattern today. Host uptime, S825 and S827 change whether nights run and
whether the scoreboard scores. None of them can qualify a game while COVERAGE_LOW fails on every
captured game.

Two different "30-game" gates are in play, and the receipts keep them separate:

- **Qualification (S362 Amendment 2, spec S390)** decides PASS or FAIL per game. Its constants are
  frozen in `scripts/platformkit/execution/forward_replay_qualification.py:15-25`, and the receipts are
  `qualification/<D>.json`. A sport needs 30 qualified games plus 30 fill-bearing games (`SPORT_GAMES`,
  `FILL_GAMES`) and a weekly family floor of 4 (`WEEK_GAMES`). That is the "0 of 31" figure.
- **Scoreboard (sealed `scoreboard/PREREG_2026-10-07.json`, amendment S492)** puts each cell (sport x
  segment x target x arm) at INSUFFICIENT until it holds 30 games
  (`ingame_scoreboard_rules.py:135`). The scoreboard does **not** read qualification. Arm A was scored
  on unqualified games (for example, 10-08 nba 6 games), so a game that fails qualification can still
  count toward a scoreboard cell.

The "0 of 31" figure in `JOB_EVIDENCE_PACKET.md` section 5 counts every game row in the 10-06, 10-12, 10-13
and 10-14 receipts: 3 + 8 + 14 + 6 = 31. That total includes 7 rows with `served: false`. This census
counts served games and adds the 10-16 receipt (9 served of 13 rows), so 34 served games were judged.

## 1. The rule set (what one game needs to PASS)

The source is `forward_replay_qualification.py` (frozen constants, lines 15-25; game tests, lines 74-79; decision
checks, lines 56-60). The constants as each receipt declares them are in `qualification/<D>.json` under
`declared_constants`: `window_s` 3600, `focus_tick_s` 5, `reservation_ttl_s` 5, `global_cap` "1",
`max_order_qty` "1". Each game is judged over `[scheduled_start, scheduled_start + 3600 s)`.

| Level | Rule (receipt key in `games[].reason_counts`) | Fails when | Receipt fields that show it |
|---|---|---|---|
| game (fails the game) | COVERAGE_LOW | covered seconds < 90 pct of 3600 s (3,240,000 ms) | `covered_ms`, `total_ms` |
| game | DECISIONS_LOW | qualified decisions < 480 | `qualified_decisions` |
| game | BOOK_CADENCE | book-receipt gap median > 45 s, or p95 > 90 s, or max > 120 s | `book_gap_median_ms`, `book_gap_p95_ms`, `book_gap_max_ms` |
| game | STATE_GAP | max gap between linked state rows > 30 s | `state_gap_max_ms` |
| game | TAPE_INCOMPLETE | union of valid trade-tape closures != the whole window | `reason_counts.TAPE_INCOMPLETE` (also counts invalid closures, so it cannot separate the test from a counted closure) |
| game (fatal) | HOST_GAP / TRADE_GAP | a declared outage overlaps the window | `reason_counts.HOST_GAP`, `TRADE_GAP` (none in 10-06..10-16) |
| decision (does not fail the game alone) | BOOK_STALE | book age > 5 s at the decision | `reason_counts.BOOK_STALE` |
| decision | STATE_STALE | state age > 15 s | `reason_counts.STATE_STALE` |
| decision | ADAPTER_REFUSED | capture adapter refused the book (touch / conversion) | `reason_counts.ADAPTER_REFUSED` |
| decision | LINKAGE_INVALID | book row's ticker or game is not the selected one (sibling tickers count here) | `reason_counts.LINKAGE_INVALID` |
| decision | NOT_LIVE | latest state status is not `live` (pregame, breaks) | `reason_counts.NOT_LIVE` |
| decision | RESERVATION_INVALID | `last_reservation_end` is None or <= decision time | `reason_counts.RESERVATION_INVALID` |
| receipt | refusal | the whole night is refused, so no game is judged | `refused`, `refusal_reason` |
| sport floor | 30 qualified games and 30 fill-bearing games | `weeks().sports[s].qualified_game_floor` | the fill-bearing list is written empty (`fill_bearing_game_ids=[]`, line 250: "explicit unassessed projection"), and fill realism runs `mode: COUNTS ONLY` (`fill_realism/<D>.json`) |

How coverage is built (lines 186-199) decides the result. A decision with no failing check adds the
interval `[at, min(at + 5 s, state_at + 15 s, reservation_end, window end))`. **Every** later book
decision for the game calls `cut()`, refused ones included, so it ends the earlier interval. A refused
decision adds no interval of its own. Coverage therefore comes to roughly (qualified decisions) x (book
gap) whenever every second decision is refused.

A decision-level reason does **not** fail a game by itself. It removes decisions and coverage. The
packet line "all 31 failing games carry ... LINKAGE_INVALID" is true, but LINKAGE_INVALID is not a game
gate. It is also counted for sibling-ticker book rows; for example, all three soccer games on 10-12 carry
exactly 1,518.

## 2. Night by night, then game by game

### Nights (from `nights/<D>.json` step records and `qualification/<D>.json`)

| Night | Served (schedule) | Qualification step | Receipt | Games judged (served) | Other step failures |
|---|---|---|---|---|---|
| 10-06 | 3 | RAN 559 s | written | 3 (3) | fill_realism and e KILLED at deadline |
| 10-07 | 7 | KILLED step_deadline_exceeded 900.5 s | none | 0 | fill_realism, e KILLED |
| 10-08 | 19 | KILLED ceiling_exceeded 829 s | none | 0 | e KILLED |
| 10-09 | 19 | KILLED step_deadline_exceeded 902.7 s | file is 0 bytes | 0 | fill_realism, e KILLED (run 10-12 at 1.7-2.3 GB free) |
| 10-10 | 26 | RAN 0.5 s, child_nonzero_exit | refused `undeclared_sport` (ncaaf), 71 scheduled rows | 0 | capture dark 10-10 01:56Z..10-12 13:26Z |
| 10-11 | no schedule | - | - | - | laptop dark |
| 10-12 | 7 | RAN 546 s | written | 8 (7) | none (COMPLETE) |
| 10-13 | 9 | RAN 358 s | written | 14 (9) | scoreboard KILLED 900 s (S824 / S825) |
| 10-14 | 6 | RAN 205 s | written | 6 (6) | scoreboard KILLED 900 s |
| 10-15 | 8 | night never ran | none | 0 | host dark 10-16 03:56Z..10-19 15:15Z; afterwards free RAM 0.4-1.5 GB against the 2.5 GB floor |
| 10-16 | 9 | RAN 273 s (run 10-19 15:59Z) | written | 13 (9) | none (COMPLETE, but scoreboard with a bare --history: S827) |
| 10-19 (outside window) | 4 | RAN 806 s, child_nonzero_exit | refused `step_budget_exceeded` (`input_counts.StepBudgetExceeded` 1) | 0 | new: qualifier's internal step budget |

The qualification kills on 10-07..10-09 were bounded by S805 and S806 (landed 10-09). Every night from
10-12 on ran the step in 205-546 s, until 10-19 hit the new `step_budget_exceeded` refusal.

### Game by game (113 served games)

Columns come from `qualification/<D>.json` `games[]`: cov pct is `covered_ms` / 36,000, then
`qualified_decisions`, `book_gap_median_ms` / `book_gap_max_ms`, `state_gap_max_ms`, and
`reason_counts.RESERVATION_INVALID` / `NOT_LIVE`. The fill realism mode comes from `fill_realism/<D>.json`
`mode`; on 10-06, 10-07 and 10-09 the step was KILLED, so no receipt exists. "Ticks captured" is shown as
qualified decisions and covered seconds, the receipt's own window measure. Per-game scoreboard tick
counts are not split out per game in a form this census reads cheaply (see section 5). "First rule" is
the earliest failing game rule in pipeline order: state stream, then book stream, then tape, then
decision count, then coverage. The receipts report all failures together and do not rank them. The
root-cause labels are assigned by this census using the rules in section 6.

| # | day | sport | game ticker | start UTC | cov pct | qual. decisions | book gap med / max ms | state gap max ms | RES_INV | NOT_LIVE | fill realism | game rules failed | first rule (order STATE_GAP, BOOK_CADENCE, TAPE, DECISIONS, COVERAGE) | root cause |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10-06 | mlb | KXMLBGAME-26OCT052000NYYTB-TB | 00:00 | 80.5 | 630 | 5187 / 31153 | 28039 | 40 | 1 | absent (KILLED) | TAPE_, COVER | TAPE_INCOMPLETE | coverage ceiling ~81%: state-change cuts + receipt gaps (pre-S767 5 s cadence) |
| 2 | 10-06 | nfl | KXNFLGAME-26OCT05ATLNO-NO | 00:15 | 24.8 | 186 | 5182 / 31147 | 61946 | 484 | 32 | absent (KILLED) | STATE, TAPE_, DECIS, COVER | STATE_GAP | global cap 1: lost the shared reservation to a concurrent game |
| 3 | 10-06 | mlb | KXMLBGAME-26OCT061800LADATL-ATL | 22:00 | 47.3 | 710 | 2437 / 3970 | 12479 | 730 | 0 | absent (KILLED) | COVER | COVERAGE_LOW | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767) |
| 4 | 10-07 | nba | KXNBAGAME-26OCT06NOPOKC-OKC | 00:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 900.5 s (nights/2026-10-07.json) | step deadline (qualification, pre-S805/S806) |
| 5 | 10-07 | nba | KXNBAGAME-26OCT06DENUTA-UTA | 01:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 900.5 s (nights/2026-10-07.json) | step deadline (qualification, pre-S805/S806) |
| 6 | 10-07 | mlb | KXMLBGAME-26OCT062130MILSD-SD | 01:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 900.5 s (nights/2026-10-07.json) | step deadline (qualification, pre-S805/S806) |
| 7 | 10-07 | nba | KXNBAGAME-26OCT06LALGSW-GSW | 02:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 900.5 s (nights/2026-10-07.json) | step deadline (qualification, pre-S805/S806) |
| 8 | 10-07 | mlb | KXMLBGAME-26OCT071600CLECWS-CWS | 20:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 900.5 s (nights/2026-10-07.json) | step deadline (qualification, pre-S805/S806) |
| 9 | 10-07 | mlb | KXMLBGAME-26OCT071800LADATL-ATL | 22:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 900.5 s (nights/2026-10-07.json) | step deadline (qualification, pre-S805/S806) |
| 10 | 10-07 | nba | KXNBAGAME-26OCT07MININD-IND | 23:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 900.5 s (nights/2026-10-07.json) | step deadline (qualification, pre-S805/S806) |
| 11 | 10-08 | mlb | KXMLBGAME-26OCT072000TBNYY-NYY | 00:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 12 | 10-08 | nba | KXNBAGAME-26OCT07MILOKC-OKC | 00:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 13 | 10-08 | nba | KXNBAGAME-26OCT07ORLMEM-MEM | 00:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 14 | 10-08 | mlb | KXMLBGAME-26OCT072200MILSD-SD | 02:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 15 | 10-08 | nba | KXNBAGAME-26OCT07GSWPOR-POR | 02:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 16 | 10-08 | tennis | KXATPMATCH-26OCT06HURDUC-HUR | 05:30 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 17 | 10-08 | tennis | KXATPMATCH-26OCT06NAVCAR-NAV | 05:30 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 18 | 10-08 | tennis | KXATPMATCH-26OCT06TIRMED-TIR | 05:30 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 19 | 10-08 | tennis | KXATPMATCH-26OCT06GIRBAE-GIR | 07:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 20 | 10-08 | tennis | KXATPMATCH-26OCT06LANSTR-LAN | 07:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 21 | 10-08 | tennis | KXATPMATCH-26OCT06MARSVA-MAR | 07:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 22 | 10-08 | tennis | KXATPMATCH-26OCT06KOPBER-KOP | 08:30 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 23 | 10-08 | tennis | KXATPMATCH-26OCT06VANMER-VAN | 08:30 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 24 | 10-08 | tennis | KXATPMATCH-26OCT06VANYUN-VAN | 10:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 25 | 10-08 | tennis | KXWTAMATCH-26OCT07ALEAND-ALE | 11:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 26 | 10-08 | tennis | KXATPMATCH-26OCT08NORSVR-NOR | 11:30 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 27 | 10-08 | nba | KXNBAGAME-26OCT08BOSCLE-CLE | 23:00 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 28 | 10-08 | nba | KXNBAGAME-26OCT08NOPMIA-MIA | 23:30 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 29 | 10-08 | nba | KXNBAGAME-26OCT08PHIBKN-BKN | 23:30 | - | - | - | - | - | - | COUNTS ONLY | - | no receipt: qualification KILLED ceiling_exceeded (nights/2026-10-08.json) | memory ceiling (qualification, pre-S805/S806) |
| 30 | 10-09 | mlb | KXMLBGAME-26OCT081700CLECWS-CWS | 00:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 31 | 10-09 | nba | KXNBAGAME-26OCT08ATLSAS-SAS | 00:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 32 | 10-09 | nfl | KXNFLGAME-26OCT08TBDAL-DAL | 00:15 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 33 | 10-09 | nba | KXNBAGAME-26OCT08SACLAL-LAL | 02:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 34 | 10-09 | tennis | KXATPMATCH-26OCT09BERNAK-BER | 05:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 35 | 10-09 | tennis | KXATPMATCH-26OCT09HALBLO-HAL | 05:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 36 | 10-09 | tennis | KXATPMATCH-26OCT09HANTIA-HAN | 05:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 37 | 10-09 | tennis | KXATPMATCH-26OCT08DAVBRO-DAV | 07:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 38 | 10-09 | tennis | KXATPMATCH-26OCT09DEMOL-DE | 07:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 39 | 10-09 | tennis | KXATPMATCH-26OCT09KHAFER-KHA | 07:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 40 | 10-09 | tennis | KXATPMATCH-26OCT09BUBMAC-BUB | 08:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 41 | 10-09 | tennis | KXATPMATCH-26OCT09CERSAF-CER | 08:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 42 | 10-09 | tennis | KXATPMATCH-26OCT09KECMEN-KEC | 08:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 43 | 10-09 | tennis | KXATPMATCH-26OCT08DJOHUR-DJO | 10:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 44 | 10-09 | tennis | KXWTAMATCH-26OCT07MERSWI-MER | 11:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 45 | 10-09 | tennis | KXATPMATCH-26OCT09ZHOMUS-ZHO | 11:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 46 | 10-09 | nba | KXNBAGAME-26OCT09HOUDAL-DAL | 12:00 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 47 | 10-09 | soccer | KXBUNDESLIGAGAME-26OCT09BVBSVW-BVB | 18:30 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 48 | 10-09 | soccer | KXLIGUE1GAME-26OCT09RCLOL-RCL | 18:45 | - | - | - | - | - | - | absent (KILLED) | - | no receipt: qualification KILLED step_deadline_exceeded 902.7 s; receipt file 0 bytes | step deadline (qualification, pre-S805/S806) |
| 49 | 10-10 | nba | KXNBAGAME-26OCT09MEMCHI-CHI | 00:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 50 | 10-10 | ncaaf | KXNCAAFGAME-26OCT09IOWAWASH-WASH | 01:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 51 | 10-10 | ncaaf | KXNCAAFGAME-26OCT09WSUUSU-USU | 01:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 52 | 10-10 | ncaaf | KXNCAAFGAME-26OCT09ISUBYU-BYU | 02:15 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 53 | 10-10 | tennis | KXATPMATCH-26OCT08SVRETC-SVR | 05:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 54 | 10-10 | tennis | KXATPMATCH-26OCT08YUNRUU-YUN | 05:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 55 | 10-10 | tennis | KXATPMATCH-26OCT08TIESVA-TIE | 07:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 56 | 10-10 | tennis | KXATPMATCH-26OCT09FILKOT-FIL | 07:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 57 | 10-10 | tennis | KXATPMATCH-26OCT08BUSBER-BUS | 08:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 58 | 10-10 | tennis | KXATPMATCH-26OCT08PAUVAL-PAU | 08:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 59 | 10-10 | tennis | KXATPMATCH-26OCT09DARTSI-DAR | 08:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 60 | 10-10 | soccer | KXEPLGAME-26OCT10ARSLEE-ARS | 11:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 61 | 10-10 | soccer | KXSERIEAGAME-26OCT10GENFIO-GEN | 13:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 62 | 10-10 | soccer | KXBUNDESLIGAGAME-26OCT10FCABMU-FCA | 13:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 63 | 10-10 | soccer | KXLALIGAGAME-26OCT10ALAATM-ALA | 14:15 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 64 | 10-10 | soccer | KXLIGUE1GAME-26OCT10LILHAC-LIL | 15:15 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 65 | 10-10 | ncaaf | KXNCAAFGAME-26OCT10ARIZWVU-WVU | 16:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 66 | 10-10 | soccer | KXBUNDESLIGAGAME-26OCT10RBLSGE-RBL | 16:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 67 | 10-10 | soccer | KXLIGUE1GAME-26OCT10ASMTFC-ASM | 18:45 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 68 | 10-10 | ncaaf | KXNCAAFGAME-26OCT10BUFFTOL-TOL | 19:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 69 | 10-10 | ncaaf | KXNCAAFGAME-26OCT10MDOSU-OSU | 20:15 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 70 | 10-10 | ncaaf | KXNCAAFGAME-26OCT10TENNARK-ARK | 20:15 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 71 | 10-10 | ncaaf | KXNCAAFGAME-26OCT10SDSUORST-ORST | 22:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 72 | 10-10 | nba | KXNBAGAME-26OCT10LACTOR-TOR | 22:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 73 | 10-10 | nba | KXNBAGAME-26OCT10ATLIND-IND | 23:00 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 74 | 10-10 | ncaaf | KXNCAAFGAME-26OCT10AFANIU-NIU | 23:30 | - | - | - | - | - | - | COUNTS ONLY | - | receipt refused: refusal_reason undeclared_sport (qualification/2026-10-10.json) | schedule refusal (ncaaf undeclared) + capture dark from 10-10 01:56Z |
| 75 | 10-12 | soccer | KXSERIEAGAME-26OCT12ATAVEN-ATA | 16:30 | 47.6 | 698 | 2468 / 2946 | 60150 | 742 | 56 | COUNTS ONLY | STATE, COVER | STATE_GAP | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767) |
| 76 | 10-12 | soccer | KXSERIEAGAME-26OCT12TORUDI-TOR | 18:45 | 45.4 | 664 | 2471 / 2713 | 60082 | 776 | 71 | COUNTS ONLY | STATE, COVER | STATE_GAP | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767) |
| 77 | 10-12 | soccer | KXEPLGAME-26OCT12COVNEW-COV | 19:00 | 14.0 | 199 | 2480 / 2741 | 11085 | 1241 | 19 | COUNTS ONLY | DECIS, COVER | DECISIONS_LOW | global cap 1: lost the shared reservation to a concurrent game |
| 78 | 10-12 | mlb | KXMLBGAME-26OCT122000LADMIL-MIL | 21:00 | 47.0 | 718 | 2461 / 4203 | 10048 | 722 | 0 | COUNTS ONLY | TAPE_, COVER | TAPE_INCOMPLETE | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767) |
| 79 | 10-12 | nba | KXNBAGAME-26OCT12BKNWAS-WAS | 23:00 | 36.2 | 538 | 2484 / 5142 | 60141 | 901 | 275 | COUNTS ONLY | STATE, TAPE_, COVER | STATE_GAP | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767); NBA pregame NOT_LIVE 275 decisions |
| 80 | 10-12 | nba | KXNBAGAME-26OCT12OKCATL-ATL | 23:00 | 2.3 | 33 | 2482 / 5136 | 60141 | 1406 | 275 | COUNTS ONLY | STATE, TAPE_, DECIS, COVER | STATE_GAP | global cap 1: lost the shared reservation to a concurrent game; NBA pregame NOT_LIVE 275 decisions |
| 81 | 10-12 | nba | KXNBAGAME-26OCT12MINNYK-NYK | 23:30 | 24.5 | 365 | 2483 / 2761 | 10892 | 1075 | 298 | COUNTS ONLY | TAPE_, DECIS, COVER | TAPE_INCOMPLETE | global cap 1: lost the shared reservation to a concurrent game; NBA pregame NOT_LIVE 298 decisions |
| 82 | 10-13 | mlb | KXMLBGAME-26OCT122000CLETB-TB | 00:00 | 43.1 | 645 | 2478 / 56137 | 10898 | 773 | 0 | COUNTS ONLY | TAPE_, COVER | TAPE_INCOMPLETE | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767) |
| 83 | 10-13 | nfl | KXNFLGAME-26OCT12BUFLAR-LAR | 00:15 | 11.6 | 172 | 2478 / 354337 | 356235 | 1127 | 34 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | capture hole inside window (book gap max 354 s; cause not in receipt) |
| 84 | 10-13 | nba | KXNBAGAME-26OCT12SASUTA-UTA | 01:00 | 0.0 | 0 | 2467 / 3053999 | 3056609 | 219 | 219 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-13 01:09Z..20:01Z (daily/2026-10-13.md); NBA pregame NOT_LIVE 219 decisions |
| 85 | 10-13 | soccer | KXUCLGAME-26OCT13RCLSPO-RCL | 16:45 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-13 01:09Z..20:01Z (daily/2026-10-13.md) |
| 86 | 10-13 | soccer | KXUCLGAME-26OCT13SBHSLA-SBH | 16:45 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-13 01:09Z..20:01Z (daily/2026-10-13.md) |
| 87 | 10-13 | soccer | KXUCLGAME-26OCT13ARSLIL-ARS | 19:00 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-13 01:09Z..20:01Z (daily/2026-10-13.md) |
| 88 | 10-13 | soccer | KXUCLGAME-26OCT13ATMMUN-ATM | 19:00 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-13 01:09Z..20:01Z (daily/2026-10-13.md) |
| 89 | 10-13 | nba | KXNBAGAME-26OCT13CLEORL-ORL | 23:00 | 37.4 | 550 | 2438 / 5750 | 64990 | 887 | 286 | COUNTS ONLY | STATE, COVER | STATE_GAP | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767); NBA pregame NOT_LIVE 286 decisions |
| 90 | 10-13 | nba | KXNBAGAME-26OCT13NYKTOR-TOR | 23:00 | 1.8 | 26 | 2441 / 5765 | 64990 | 1411 | 322 | COUNTS ONLY | STATE, DECIS, COVER | STATE_GAP | global cap 1: lost the shared reservation to a concurrent game; NBA pregame NOT_LIVE 322 decisions |
| 91 | 10-14 | mlb | KXMLBGAME-26OCT132000CLETB-TB | 00:00 | 46.4 | 680 | 2437 / 6695 | 16237 | 759 | 1 | COUNTS ONLY | TAPE_, COVER | TAPE_INCOMPLETE | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767) |
| 92 | 10-14 | nba | KXNBAGAME-26OCT13INDOKC-OKC | 00:00 | 2.6 | 38 | 2440 / 22887 | 52223 | 1391 | 260 | COUNTS ONLY | STATE, DECIS, COVER | STATE_GAP | global cap 1: lost the shared reservation to a concurrent game; NBA pregame NOT_LIVE 260 decisions |
| 93 | 10-14 | nba | KXNBAGAME-26OCT13GSWLAL-LAL | 02:00 | 35.7 | 529 | 2462 / 2821 | 224949 | 911 | 278 | COUNTS ONLY | STATE, TAPE_, COVER | STATE_GAP | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767); NBA pregame NOT_LIVE 278 decisions |
| 94 | 10-14 | nba | KXNBAGAME-26OCT13PORSAC-SAC | 02:00 | 4.2 | 62 | 2458 / 2835 | 224949 | 1379 | 251 | COUNTS ONLY | STATE, DECIS, COVER | STATE_GAP | global cap 1: lost the shared reservation to a concurrent game; NBA pregame NOT_LIVE 251 decisions |
| 95 | 10-14 | nba | KXNBAGAME-26OCT14BKNMIA-MIA | 23:30 | 35.2 | 531 | 2446 / 3451 | 60854 | 909 | 277 | COUNTS ONLY | STATE, TAPE_, COVER | STATE_GAP | coverage ceiling ~50%: 5 s reservation TTL vs 2.5 s repoll cadence (post-S767); NBA pregame NOT_LIVE 277 decisions |
| 96 | 10-14 | nba | KXNBAGAME-26OCT14CHABOS-BOS | 23:30 | 3.4 | 49 | 2454 / 3439 | 60854 | 1391 | 277 | COUNTS ONLY | STATE, TAPE_, DECIS, COVER | STATE_GAP | global cap 1: lost the shared reservation to a concurrent game; NBA pregame NOT_LIVE 277 decisions |
| 97 | 10-15 | mlb | KXMLBGAME-26OCT142000MILLAD-LAD | 00:00 | - | - | - | - | - | - | absent (night not run) | - | no receipt: night 10-15 never ran (no nights/2026-10-15.json) | host asleep 10-16 03:56Z..10-19 15:15Z, then low RAM |
| 98 | 10-15 | nba | KXNBAGAME-26OCT14CHIMIL-MIL | 00:00 | - | - | - | - | - | - | absent (night not run) | - | no receipt: night 10-15 never ran (no nights/2026-10-15.json) | host asleep 10-16 03:56Z..10-19 15:15Z, then low RAM |
| 99 | 10-15 | ncaaf | KXNCAAFGAME-26OCT14WKUSHSU-SHSU | 00:00 | - | - | - | - | - | - | absent (night not run) | - | no receipt: night 10-15 never ran (no nights/2026-10-15.json) | host asleep 10-16 03:56Z..10-19 15:15Z, then low RAM |
| 100 | 10-15 | nba | KXNBAGAME-26OCT14DENLAC-LAC | 02:30 | - | - | - | - | - | - | absent (night not run) | - | no receipt: night 10-15 never ran (no nights/2026-10-15.json) | host asleep 10-16 03:56Z..10-19 15:15Z, then low RAM |
| 101 | 10-15 | mlb | KXMLBGAME-26OCT151800TBCLE-CLE | 22:00 | - | - | - | - | - | - | absent (night not run) | - | no receipt: night 10-15 never ran (no nights/2026-10-15.json) | host asleep 10-16 03:56Z..10-19 15:15Z, then low RAM |
| 102 | 10-15 | nba | KXNBAGAME-26OCT15TORNYK-NYK | 23:30 | - | - | - | - | - | - | absent (night not run) | - | no receipt: night 10-15 never ran (no nights/2026-10-15.json) | host asleep 10-16 03:56Z..10-19 15:15Z, then low RAM |
| 103 | 10-15 | ncaaf | KXNCAAFGAME-26OCT15ECUUAB-UAB | 23:30 | - | - | - | - | - | - | absent (night not run) | - | no receipt: night 10-15 never ran (no nights/2026-10-15.json) | host asleep 10-16 03:56Z..10-19 15:15Z, then low RAM |
| 104 | 10-15 | ncaaf | KXNCAAFGAME-26OCT15GASOODU-ODU | 23:30 | - | - | - | - | - | - | absent (night not run) | - | no receipt: night 10-15 never ran (no nights/2026-10-15.json) | host asleep 10-16 03:56Z..10-19 15:15Z, then low RAM |
| 105 | 10-16 | mlb | KXMLBGAME-26OCT152000MILLAD-LAD | 00:00 | 20.9 | 307 | 2465 / 977149 | 11079 | 413 | 0 | COUNTS ONLY | BOOK_, DECIS, COVER | BOOK_CADENCE | capture hole inside window (book gap max 977 s; cause not in receipt) |
| 106 | 10-16 | ncaaf | KXNCAAFGAME-26OCT15CSUTXST-TXST | 00:00 | 0.0 | 0 | 2493 / 1167137 | 3600000 | 720 | 720 | COUNTS ONLY | STATE, BOOK_, DECIS, COVER | STATE_GAP | adapter refusal (ADAPTER_REFUSED 332) + no live state |
| 107 | 10-16 | nfl | KXNFLGAME-26OCT15SEADEN-DEN | 00:15 | 12.6 | 188 | 2462 / 903700 | 60635 | 892 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | capture hole inside window (book gap max 903 s; cause not in receipt) |
| 108 | 10-16 | soccer | KXLIGUE1GAME-26OCT16MANTFC-MAN | 18:45 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-16 03:56Z..10-19 15:15Z (JOB_EVIDENCE_PACKET s5) |
| 109 | 10-16 | soccer | KXSERIEAGAME-26OCT16FROSAS-FRO | 18:45 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-16 03:56Z..10-19 15:15Z (JOB_EVIDENCE_PACKET s5) |
| 110 | 10-16 | mlb | KXMLBGAME-26OCT161800TBCLE-CLE | 22:00 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-16 03:56Z..10-19 15:15Z (JOB_EVIDENCE_PACKET s5) |
| 111 | 10-16 | nba | KXNBAGAME-26OCT16BOSPHI-PHI | 23:00 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-16 03:56Z..10-19 15:15Z (JOB_EVIDENCE_PACKET s5) |
| 112 | 10-16 | nba | KXNBAGAME-26OCT16MIAORL-ORL | 23:00 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-16 03:56Z..10-19 15:15Z (JOB_EVIDENCE_PACKET s5) |
| 113 | 10-16 | ncaaf | KXNCAAFGAME-26OCT16MEMTULN-TULN | 23:30 | 0.0 | 0 | 3600000 / 3600000 | 3600000 | 0 | 0 | COUNTS ONLY | STATE, BOOK_, TAPE_, DECIS, COVER | STATE_GAP | host asleep / capture dark: host asleep 10-16 03:56Z..10-19 15:15Z (JOB_EVIDENCE_PACKET s5) |

Legend for "game rules failed": STATE = STATE_GAP, BOOK_ = BOOK_CADENCE, TAPE_ = TAPE_INCOMPLETE, DECIS = DECISIONS_LOW, COVER = COVERAGE_LOW.

## 3. Pareto

### 3a. By first-failing rule (34 served games that were judged)

| First rule (pipeline order) | Games | Reading |
|---|---|---|
| STATE_GAP | 26 | 11 are the host-asleep games: every rule fails, and the state stream is first in the order. The other 15 are captured games whose state stream had a gap > 30 s; 9 of the 10 captured NBA games show a recurring gap of about 60 s (60.1 / 65.0 / 60.9 s) |
| TAPE_INCOMPLETE | 5 | mostly MLB games with a single window (NYYTB 10-06, LADMIL 10-12, CLETB 10-13, CLETB 10-14) plus NBA MINNYK 10-12 |
| DECISIONS_LOW | 1 | soccer COVNEW 10-12 (concurrent with TORUDI) |
| BOOK_CADENCE | 1 | mlb MILLAD 10-16 (book gap max 977 s inside the window) |
| COVERAGE_LOW | 1 | mlb LADATL 10-06: **the only game that fails nothing except coverage** (47.3 pct) |
| refused or no receipt | 79 | 10-07 (7), 10-08 (19), 10-09 (19), 10-10 (26), 10-15 (8) |

Number of judged games failing each rule (one game can fail several): COVERAGE_LOW 34, STATE_GAP 26,
DECISIONS_LOW 23, TAPE_INCOMPLETE 22, BOOK_CADENCE 15. **Among the 23 games with live capture:
COVERAGE_LOW 23, STATE_GAP 15, TAPE_INCOMPLETE 13, DECISIONS_LOW 12, BOOK_CADENCE 4.** The highest
coverage any captured game reached is 80.5 pct (NYYTB 10-06, before S767). Across all served receipts
from 10-02 on, the highest is 81.2 pct (CWSCLE 10-05).

### 3b. By root cause (all 113 served games)

| Root cause | Games | By sport | Evidence |
|---|---|---|---|
| Qualification step killed (deadline / memory, before S805/S806) | 45 | tennis 23, nba 13, mlb 6, soccer 2, nfl 1 | `nights/2026-10-07/08/09.json` qualification step_status KILLED |
| Host asleep (no capture, or the night never ran) | 42 | soccer 13, ncaaf 11, nba 8, tennis 7, mlb 3 | 10-10 (23 games after 01:56Z), 10-13 01:09Z..20:01Z (`daily/2026-10-13.md`), 10-16 from 03:56Z, night 10-15 never ran; judged ones show `covered_ms` 0 and `book_gap_max_ms` >= 3,000,000 |
| Reservation-refusal coverage ceiling (S767 cadence; no row owns it) | 10 | mlb 4, nba 4, soccer 2 | `qualified_decisions` close to RESERVATION_INVALID; coverage close to decisions x book gap (see 4a) |
| Global cap 1 contention (a concurrent game holds the one reservation) | 8 | nba 6, nfl 1, soccer 1 | the losing game of a concurrent pair covers 1.8-4.2 pct (NBA) with RESERVATION_INVALID 1,379-1,411 |
| Capture hole inside the window | 3 | nfl 2, mlb 1 | `book_gap_max_ms` 354 s (BUFLAR 10-13), 977 s (MILLAD 10-16), 903 s (SEADEN 10-16); the cause is not in the receipts |
| Schedule refusal only (`undeclared_sport`, before the 10-10 dark spell) | 3 | ncaaf 2, nba 1 | `qualification/2026-10-10.json` refusal_reason |
| Adapter refusal | 1 | ncaaf 1 | CSUTXST 10-16: ADAPTER_REFUSED 332, NOT_LIVE / STATE_STALE 720 |
| State-change cut ceiling (pre-S767, 5 s cadence) | 1 | mlb 1 | NYYTB 10-06: 80.5 pct, the known 13.4 + 4.8 pct split (memory qualification_path, S767 motivation) |

The causes in the brief map onto these rows as follows:

- **Host asleep:** 42 games.
- **Low-RAM refusal:** folded into host asleep. It is the reason night 10-15 stayed unrun after the 10-19
  wake (free RAM 0.4-1.5 GB against the 2.5 GB floor).
- **Step deadline:** 45 games. The deadlines were on *qualification* and *fill_realism*, not on the
  quadratic scorer. The quadratic scorer (S824 / S825) killed only the *scoreboard* step on 10-13 and
  10-14, so it cost no qualification receipt and **0 games** in this census.
- **Tape hole:** a contributing failure on 13 captured games. It is never the only failure.
- **Adapter refusal:** 1 game. The S732 fix took it from 421-490 per MLB game on 10-03 to 0 after 10-05.
- **Counts-only fill realism:** 0 games by itself. It blocks the *sport floor* (30 fill-bearing games)
  later, not a game verdict.
- **Schedule or pointer refusal:** 3 games as the only cause, and 26 as a receipt-level cause on 10-10.
- **NBA warmup:** 0 games. Warmup governs the fitted scoreboard arms B / C / D, not qualification.

## 4. The one change

### 4a. The coverage mechanism, measured from the receipts

- **The cadence changed when S767 was adopted.** The S767 adoption tick was 10:49:29Z on 10-06 (register
  row S767). Every game before it has a book gap median of 5,060-5,303 ms. Every game after it has a
  median of 2,437-2,484 ms, starting with LADATL 10-06 22:00Z.
- **Before S767, a game with no rival covered about 81 pct.** NYYTB 10-06 had 630 qualified decisions, 40
  RESERVATION_INVALID and 80.5 pct coverage, which is 4,601 ms covered per qualified decision.
- **After S767, the same kind of game covers about 47 pct.** These are the MLB games with no concurrent
  rival:

  | Game | Qualified decisions | RESERVATION_INVALID | Coverage | Covered per decision |
  |---|---|---|---|---|
  | LADATL 10-06 | 710 | 730 | 47.3 pct | 2,399 ms |
  | LADMIL 10-12 | 718 | 722 | 47.0 pct | 2,357 ms |
  | CLETB 10-13 | 645 | 773 | 43.1 pct | 2,403 ms |
  | CLETB 10-14 | 680 | 759 | 46.4 pct | 2,458 ms |

  Covered per decision equals one book gap. About half of all decisions are RESERVATION_INVALID, and the
  `cut()` rule ends each valid interval at the next decision, refused or not.
- **Soccer and NBA games that won the reservation show the same pattern.** ATAVEN 10-12 had 698 decisions
  and 742 RESERVATION_INVALID. BKNWAS 10-12 had 538 and 901, and its NOT_LIVE count is separate.
- **Conclusion.** S767 was built to recover the 13.4 pct "waiting for the next book after a state change".
  The half-tick books it added mostly land as RESERVATION_INVALID decisions. Those decisions truncate
  coverage instead of adding to it, so post-S767 coverage is lower than before (about 47 against 81 pct).
- **Not proven from receipts.** Which code path makes every second decision fail is not settled here. One
  candidate: `policy.consider` raises a cap refusal while the previous quote is still pending, so
  `last_reservation_end` stays at `issued_at + 5 s` (`forward_replay_policy.py:183,199`). Another: the
  quote's `pulled` return skips the update. Settling it needs a scratch replay of one game, for example
  LADMIL 10-12, with a scratch ledger and a fresh nonce (the method in memory qualification_path).
  That replay was not run here, because the host must stay quiet.

### 4b. Candidate changes and the number of games each would have qualified (10-06..10-16)

| Change | Owner row | Games it qualifies alone | Why |
|---|---|---|---|
| Host uptime (no manual sleeps; recorder up) | owner / S823 adoption | **0** | 42 more games would have been judged, but every captured game fails COVERAGE_LOW |
| S825 landing (per-fold fit cache, seal A) | S825 (parked lead/s825 4cf2e260c) | **0** | scoreboard step only; qualification never reads it |
| S827 (history fallback after a missed night) | S827 (landed 8df48aec4) | **0** | scoreboard fitted arms only |
| Make a decision inside a live reservation count as covered, so the half-tick repoll adds coverage (replay or policy side; measure first) | **none; next free id S829** | **1** (LADATL 10-06, which fails nothing else). Also necessary for all 23 captured games | coverage would roughly double from about 47 pct (decisions would roughly double), which projects at or above 90 pct for a game with no rival. This is unverified until the replay |
| + tape closure continuation (S733 follow-up) | S733 family | +4 MLB games (NYYTB, LADMIL, CLETB x2) | these fail only TAPE_INCOMPLETE + COVERAGE_LOW |
| + NBA state cadence (recurring gaps of about 60 s; state gap max > 30 s on 9 of 10 captured NBA games) | none found | NBA unlocks only with this and the two below | ESPN state feed gap; cause not in receipts |
| + NBA pregame window | none found (S561 is the books live flag, a different fix) | - | NOT_LIVE 251-322 decisions x about 2.45 s = 615-789 s, which is 17-22 pct of the 3,600 s window; NBA coverage stays below 90 pct even with perfect cadence while the window opens at `scheduled_start` |
| + global cap 1 | frozen capture constant (`declared_constants.global_cap` "1") | - | with 4-6 NBA tips per regular-season evening at 23:00-23:30Z, at most one game per overlapping hour can hold the reservation |

**Recommendation.** The one change is the reservation and coverage fix, filed as a new row (S829 is the
next free id; `NEXT_GAP_ID` header in `docs/evidence/HARNESS_GAPS_2026-09-03.md`). It is the only gate
that 23 of 23 captured games fail, and no current row owns it. Start with the scratch replay in 4a. Then
pass the fix through a tier ruling: `forward_replay_qualification.py` is frozen S362 Amendment 2
arithmetic, so the fix belongs in the consumer (`forward_replay.py` / `forward_replay_policy.py`), and
whether that counts as a change of identity has to be ruled. On the window's evidence, the fix alone
qualifies about 1 game in 11 days. With the S733 tape follow-up it qualifies about 5, all MLB, and the MLB
season is in its last postseason days. NBA needs three more changes besides it: state gap, pregame window
and concurrency. Host uptime is the largest lever on volume, but it cannot help until this fix exists.

### 4c. Earliest plausible 30-game dates (arithmetic)

Two facts set the frame:

- **Per-night scoreboard cells cannot reach 30.** A scoreboard cell is per night, and no night has held
  more than 6 games for one sport (10-08 nba 6). A 30-game cell needs the pooled reader (S721, PROPOSED)
  or the S503 cumulative evaluator (no sealed window file; "never run", `cumulative/2026-10-16.md`).
- **The qualification sport floor cannot be dated.** It needs 30 qualified games and 30 fill-bearing
  games. 0 games qualify, and the fill-bearing list is written empty while fill realism is COUNTS ONLY.

The table therefore gives the pooled descriptive count, at two rates:

- **Full rate:** every night runs, at the served rate per schedule day observed 10-06..10-16.
- **Observed yield:** games actually scored per calendar day, 10-06..10-19. This is the maximum
  `n_games` per arm-A or arm-C outcome cell per night, summed over 14 calendar days, from
  `scoreboard/<D>.json`.

| Sport | Served per schedule day | Arm A games scored (yield per day) | Arm C games under the current seal | Earliest plausible date for 30 C-and-A games |
|---|---|---|---|---|
| nba | 32 / 10 = 3.2 | 10 / 14 = 0.71 | 0 (fitted arms in warmup: about 20 settled regular-season games needed, packet section 5) | full rate: warmup 20 / 3.2 = 6.3 d gives about 10-26, then 30 / 3.2 = 9.4 d gives **about 11-05**. Observed yield: 20 / 0.71 = 28 d plus 30 / 0.71 = 42 d gives about 12-29. Arm-A-only (the mid's own cell, not a model verdict): 10-29 at full rate, 12-01 at observed yield |
| soccer | 18 / 10 = 1.8 | 8 / 14 = 0.57 | 0 (fitted arms dark: model_not_reconstructible / fit_missing) | only after the fitted arms reconstruct (S827 + S823); from 10-21: 30 / 1.8 = 16.7 d gives about 11-07 at full rate, 30 / 0.57 = 53 d gives about 12-13 at observed yield |
| mlb | 15 / 10 = 1.5 | 10 / 14 = 0.71 | 1 (seal 806fa58a, `cumulative/2026-10-16.md`) | not in 2026: 29 more games are needed and the 2026 postseason ends by early November. The desk's own projection is 2027-05-04/05 |
| nfl | 4 / 10 = 0.4 | 3 / 14 = 0.21 | 0 | outside pooled_reader.CORPUS (789 rows skipped), so no pooled count exists. Even if added: 30 / 0.4 = 75 d gives about 2027-01-04 at full rate, and 143 d at observed yield, which is past the season |
| ncaaf, tennis | 14 / 10; 30 (tennis left the tuple 10-11) | 0 | 0 | none: outside CORPUS, or not served |

For qualification (30 qualified NBA games), the earliest date is no sooner than about 9.4 days of full
nights after the coverage fix, the NBA state-gap fix and the pregame-window fix all land. None of the
three has a row today.

## 5. What the receipts cannot tell us

1. Which code path makes about half of post-S767 decisions RESERVATION_INVALID. This needs a
   per-decision scratch replay; the receipts hold counts only.
2. Whether NBA `NOT_LIVE` (251-322 decisions a game) is pregame time or also covers period breaks. The
   receipts do not split NOT_LIVE by state status.
3. Why NBA and soccer state rows show recurring gaps of about 60 s, and whether they come from ESPN
   poll cadence or the recorder writing only on change.
4. For TAPE_INCOMPLETE, whether the closure-union test failed or an invalid closure was counted. Both
   write the same key (`forward_replay_qualification.py:177`).
5. The cause of the in-window capture holes on BUFLAR 10-13, MILLAD 10-16 and SEADEN 10-16, which were
   354-977 s while the host was up.
6. Per-game verdicts for the 45 games of 10-07..10-09, the 26 games of 10-10 and the 8 games of 10-15.
   No receipt exists, and the D+1 shards may have rotated since, so a retrospective run may not
   reproduce them.
7. Why night 10-15 was not run retrospectively after the 10-19 wake. Four of its games (22:00Z and
   23:30Z) had the host up.
8. What the 10-19 `step_budget_exceeded` refusal costs from 10-20 on. It is a new qualifier-side budget
   (806 s wall), and its trigger is not in the receipt.
9. Per-game scoreboard tick counts per window. Scoreboards carry tick rows, and this census did not
   aggregate them per game, to keep the host load light.
10. Whether a coverage fix lifts a game with no rival to 90 pct or more. The doubling projection is
    arithmetic, not a replay.
11. Fill-bearing games. They are an explicit "unassessed projection" (`fill_bearing_game_ids=[]`), so no
    receipt says how many qualified games would also be fill-bearing.

## 6. Method (reproducible, read-only)

- Served games are the rows of `schedules/<D>_maker_forward.json` for D = 10-06..10-16 (no 10-11 file),
  113 in total. They are matched by `ticker` to `qualification/<D>.json` `games[]`.
- Game rules are the reason keys among COVERAGE_LOW, DECISIONS_LOW, BOOK_CADENCE, STATE_GAP,
  TAPE_INCOMPLETE, HOST_GAP and TRADE_GAP. The code forces each failed game test to a count of at least 1
  (lines 80-83).
- Root-cause labels are assigned in this order:
  1. No receipt: the night's step record.
  2. `covered_ms` 0 and `book_gap_max_ms` >= 3,000,000: host asleep, cross-checked against the dark
     spells in `daily/2026-10-13.md`, `daily/2026-10-14.md`, `daily/2026-10-15.md` and the packet.
  3. ADAPTER_REFUSED > 0: adapter refusal.
  4. `book_gap_max_ms` > 120,000: capture hole.
  5. A served game overlapping within 1 h has higher coverage while this game's RESERVATION_INVALID
     exceeds its qualified decisions: global cap contention.
  6. `book_gap_median_ms` < 3,000: post-S767 reservation ceiling.
  7. Otherwise: pre-S767 ceiling.
- Night 10-10 games are labelled host asleep if they start at or after 01:56Z, and schedule refusal
  otherwise.
- Nothing under `docs/evidence/forward/` or the register was edited.
