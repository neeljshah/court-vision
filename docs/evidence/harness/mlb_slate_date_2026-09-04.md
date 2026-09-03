# S184 MLB slate-date construct evidence

## Acceptance metric

This is an exhaustive, network-free construct enumeration. For each UTC hour
00 through 23 on 2026-09-02, `capture_once` receives a fixed aware UTC `now`
and a fake `live_games_fn`. The fake records only the date string resolved by
`capture_once` and returns no games. The comparison date is the established
Gumbo baseball-date rule, UTC minus 10 hours. No capture output is inspected.

`n = 24 (CONSTRUCT)`: all hours are enumerated and none are excluded.

| UTC hour | before resolved | Gumbo default | before mismatch | after resolved | after mismatch |
| --- | --- | --- | --- | --- | --- |
| 00Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 01Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 02Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 03Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 04Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 05Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 06Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 07Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 08Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 09Z | 2026-09-02 | 2026-09-01 | true | 2026-09-01 | false |
| 10Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 11Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 12Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 13Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 14Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 15Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 16Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 17Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 18Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 19Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 20Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 21Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 22Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |
| 23Z | 2026-09-02 | 2026-09-02 | false | 2026-09-02 | false |

Before: 10 of 24 mismatches, at 00Z through 09Z.

After: 0 of 24 mismatches.

Reproduction from a tracked tree is `python -m pytest
tests/platformkit/ingame/test_mlb_slate_date.py -q`. The test executes the
same 24-row fake-caller enumeration and asserts an empty mismatch set. It also
asserts that an explicit `date_str` remains authoritative.

## Tick-store exposure context

This is not the acceptance metric and does not re-score capture output. The
tick store clock distribution has 405 files and 79,566 rows with a parseable
timestamp. Of those rows, 41,202 (51.7834%) occur in a UTC hour that would have
had a mismatching UTC date before this correction. This is a proxy for capture
exposure only; it does not establish that the capture missed that percentage of
ticks.

| UTC hour | parseable-ts rows |
| --- | ---: |
| 00Z | 15,240 |
| 01Z | 11,510 |
| 02Z | 7,425 |
| 03Z | 4,806 |
| 04Z | 1,985 |
| 05Z | 236 |
| 06Z-11Z | 0 |
| 12Z | 1 |
| 13Z | 1 |
| 14Z | 2 |
| 15Z-23Z | 38,360 |

The historical store has 321 of 401 game ids with at least one such tick, and
118 of 401 game ids with only such ticks. The 00Z through 09Z band is
20:00 through 05:59 ET. The first hour is present at 23Z (15,595 rows), then
the prior UTC-date resolution changes at midnight while games may remain live.

## Not verified

- No pod deployment occurred before acceptance.
- The forward single-window watch is not assessed: the local
  `data/cache/ingame_books/mlb/` directory has no files. Its future readout is
  distinct game_pk count, with 12 or more on one live slate as the watch value.
- No live-slate capture outcome was observed by this construct test.
- The duplicate inline Gumbo rule remains a separate follow-up and was not
  changed here.
