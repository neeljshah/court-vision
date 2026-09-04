# S218 NBA live-field census - attempt 2b - 2026-09-04

## Scope and method

This is a local, read-only construct census. It made no network call and wrote
nothing under `data/`. The census opens one JSON payload, records fixed presence
facts, releases it, then opens the next. It never materializes a payload store.

The construct denominator is exactly 8 candidate fields x 2 parsers = 16 cells.
A cell is `KEPT`, `PRESENT_BUT_DROPPED`, or `ABSENT_FROM_PAYLOAD`.

## Attempt 1

Attempt 1 treated CDN routes as absent. That was a store-visibility artefact,
not an archive fact. Its no-payload conclusion is retracted.

## Attempt 2

Attempt 2 corrected ESPN traversal but hardcoded all eight CDN cells as
`NO_PAYLOAD_ON_DISK`. It also reported 2026-06-23 as the summary end date and
removed `LIMIT_VERDICT` and `PARSER_OUTPUT_FACTS`.

## Attempt 2b correction

The default inventory now traverses all archived ESPN and WNBA CDN routes.
CDN cells are measured from payloads. `LIMIT_VERDICT` and
`PARSER_OUTPUT_FACTS` are restored. Summary header dates remeasure to
2024-10-22 through 2026-06-14; both summary date cells below use that end date.

## Classification rules resolved before the grid

Sibling-route rule: a candidate on an archived sibling route is
`PRESENT_BUT_DROPPED` for the named parser when that parser does not consume the
sibling route. Thus CDN substitutions are `PRESENT_BUT_DROPPED`: all 168
play-by-play payloads contain a substitution action, while `boxscore_read.py`
does not consume that route.

Semantic alias rule: a name counts only when it represents the current
on-floor five. ESPN `active` is roster availability, not an on-floor-five
alias. An explicit `oncourt` key would be an on-floor alias and yield
`PRESENT_BUT_DROPPED` unless retained. No archived ESPN payload has that key.
Every archived CDN boxscore has `players[].oncourt`, so its CDN cell is
`PRESENT_BUT_DROPPED`, not absent.

## Premise re-measurement

No parser was edited. `boxscore_read.py:159-178` emits CDN period, clock,
running score, and per-player `pf`; `pf` derives from `foulsPersonal` at line
137. `ingame_live_state.py:291,299,373` emits ESPN period, clock, and running
score. Its event list comes from the scoreboard route at line 469.

## Archived raw-payload inventory

| Archive path | Payloads | Bytes | Date range in payload | Scan basis |
| --- | ---: | ---: | --- | --- |
| `data/cache/nba_pbp_wallclock_raw/scoreboard/*.json` | 398 | 40,942,864 | 2024-10-22 through 2026-06-14 | ESPN `events[]`, one file at a time |
| `data/cache/nba_pbp_wallclock_raw/summary/*.json` | 1,610 | 736,578,812 | 2024-10-22 through 2026-06-14 | ESPN `header.competitions[]`, one file at a time |
| `data/cache/nba_pbp_wallclock_raw` total | 2,008 | 777,521,676 | 2024-10-22 through 2026-06-14 | metadata plus independent JSON opens |
| `data/domains/wnba/cdn_backfill/*/boxscore.json` | 168 | 5,579,672 | 2026-04-25 through 2026-07-04 | CDN `game`, one file at a time |
| `data/domains/wnba/cdn_backfill/*/playbyplay.json` | 168 | 62,159,595 | 2026-04-25 through 2026-07-04 | CDN `game.actions`, one file at a time |

## Full candidate-field by parser grid

| Field | Parser | Classification | Exact payload denominator | Parser source line |
| --- | --- | --- | --- | --- |
| on_court_five | nba_cdn_boxscore | PRESENT_BUT_DROPPED | 168/168 CDN boxscore payloads | boxscore_read.py:159-178 does not retain this field |
| on_court_five | espn_live_state | ABSENT_FROM_PAYLOAD | 0/2,008 ESPN payloads | n/a: absent from archived ESPN payloads |
| substitution_event | nba_cdn_boxscore | PRESENT_BUT_DROPPED | 168/168 CDN play-by-play sibling payloads | sibling CDN play-by-play route; boxscore reader does not consume it |
| substitution_event | espn_live_state | PRESENT_BUT_DROPPED | 1,606/1,610 ESPN summary payloads | ingame_live_state.py:469 |
| personal_fouls_per_player | nba_cdn_boxscore | KEPT | 168/168 CDN boxscore payloads | boxscore_read.py:137 |
| personal_fouls_per_player | espn_live_state | PRESENT_BUT_DROPPED | 1,610/1,610 ESPN summary payloads | ingame_live_state.py:469 |
| team_fouls | nba_cdn_boxscore | ABSENT_FROM_PAYLOAD | 0/336 CDN payloads | n/a: absent from archived CDN boxscore and sibling play-by-play |
| team_fouls | espn_live_state | PRESENT_BUT_DROPPED | 1,606/1,610 ESPN summary payloads | ingame_live_state.py:469 |
| in_bonus | nba_cdn_boxscore | PRESENT_BUT_DROPPED | 168/168 CDN boxscore payloads | boxscore_read.py:159-178 does not retain this field |
| in_bonus | espn_live_state | ABSENT_FROM_PAYLOAD | 0/2,008 ESPN payloads | n/a: absent from archived ESPN payloads |
| timeouts_remaining | nba_cdn_boxscore | PRESENT_BUT_DROPPED | 168/168 CDN boxscore payloads | boxscore_read.py:159-178 does not retain this field |
| timeouts_remaining | espn_live_state | ABSENT_FROM_PAYLOAD | 0/2,008 ESPN payloads | n/a: absent from archived ESPN payloads |
| period_clock | nba_cdn_boxscore | KEPT | 168/168 CDN boxscore payloads | boxscore_read.py:163,164 |
| period_clock | espn_live_state | KEPT | 337/398 ESPN scoreboard payloads | ingame_live_state.py:291,299 |
| running_score | nba_cdn_boxscore | KEPT | 168/168 CDN boxscore payloads | boxscore_read.py:167,168 |
| running_score | espn_live_state | KEPT | 337/398 ESPN scoreboard payloads | ingame_live_state.py:373 |

Class counts: `KEPT=5`, `PRESENT_BUT_DROPPED=7`,
`ABSENT_FROM_PAYLOAD=4`. Denominator: 16 cells. Unclassified: 0.

## Verdict

**ACCEPT: CONSTRUCT CENSUS COMPLETE; ARCHIVED ROUTES MEASURED.** This census
adds no extraction, feature, endpoint, calibration, or prediction claim.

## Not verified

- Whether current live ESPN or CDN endpoints differ from these archived shapes.
- Whether CDN `oncourt` identifies exactly five players per side at every
  capture instant; this is payload presence and parser retention only.
- Whether ESPN `active` semantics change on a current endpoint.
- Any downstream feature, calibration, or prediction effect.

## Summary JSON

```json
{"candidate_fields": 8, "class_counts": {"ABSENT_FROM_PAYLOAD": 4, "KEPT": 5, "PRESENT_BUT_DROPPED": 7}, "denominator": 16, "parsers": 2, "unclassified": 0, "verdict": "ACCEPT: CONSTRUCT CENSUS COMPLETE; ARCHIVED ROUTES MEASURED"}
```

Q9 note: this is an unscored source census, not a paired-loss comparison.

## Reproduction

```text
python -m pytest scripts/platformkit/ingame/test_s218_nba_live_field_census.py -q -p no:cacheprovider
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.live_field_census
```

Attempt 2b test results: `4 passed in 0.86s` and `1 passed in 2.20s`.
