# S249 NBA CDN liveData capture - premise remeasurement - 2026-09-04

## Verdict

**FALSIFIED.** The exact S249 binding before-condition does not hold: its
declared ESPN payload game-date end is `2026-06-23`, while the required
schema-specific remeasurement found `2026-06-14`. Per S249 step 0, work stops
here. No CDN endpoint was contacted, no deployment was performed, no capture
helper or test was created, and no scored comparison was made.

## Binding before-condition output

The first sequential byte-pattern pass printed the following output. It opened
one JSON payload at a time and did not materialize a store.

```text
S249_BINDING_BEFORE
ESPN_SCOREBOARD_FILES=398
ESPN_SUMMARY_FILES=1610
ESPN_TOTAL_FILES=2008
ESPN_TOTAL_BYTES=777521676
ESPN_DATE_RANGE=2024-10-22..2026-07-08
NBA_CDN_CANDIDATE_PATHS=data\domains\nba\cdn_backfill=ABSENT,data\domains\nba\cdn_livedata=ABSENT,data\cache\nba_cdn=ABSENT,data\cache\nba_livedata=ABSENT
NBA_CDN_RAW_JSON_FILES=0
ON_COURT_FIVE_ESPN=0/2008
SUBSTITUTION_EVENT_ESPN_SUMMARY=1606/1610
```

The date-token scan is intentionally not used for the verdict because it sees
non-game dates elsewhere in payloads. The required schema-specific recheck then
read only `events[].date` from scoreboards and
`header.competitions[].date` from summaries, one file at a time:

```text
S249_BINDING_DATE_RECHECK
ESPN_GAME_DATE_RANGE=2024-10-22..2026-06-14
ESPN_GAME_DATE_COUNT=3513
```

The binding condition specified `2024-10-22..2026-06-23`; `2026-06-14` is the
measured game-date maximum. This difference falsifies the premise regardless of
the matching count and field cells, so S249's mandatory stop applies.

## Inputs opened

| Full path | Files | Bytes | Resolution | Access |
| --- | ---: | ---: | --- | --- |
| `data/cache/nba_pbp_wallclock_raw/scoreboard/*.json` | 398 | 40,942,864 | n/a_json | Sequential, one JSON payload at a time |
| `data/cache/nba_pbp_wallclock_raw/summary/*.json` | 1,610 | 736,578,812 | n/a_json | Sequential, one JSON payload at a time |

Source inventory output:

```text
S249_SOURCE_INVENTORY
SCOREBOARD_PATH=data/cache/nba_pbp_wallclock_raw/scoreboard/*.json
SCOREBOARD_FILES=398
SCOREBOARD_BYTES=40942864
SUMMARY_PATH=data/cache/nba_pbp_wallclock_raw/summary/*.json
SUMMARY_FILES=1610
SUMMARY_BYTES=736578812
RESOLUTION=n/a_json
```

## Contract self-check

- B1-B10: no metric, schema change, data write, deployment, or scoring occurred.
- Q1 and Q4-Q5-Q9: no scored comparison occurred; no preregistration was needed.
- Q2: no charged trial occurred; no ledger was read or modified.
- Q3: no bar was changed.
- Q6: this memo makes no calibration result claim.
- Q7: this is a premise census, not a sampled or scored metric.
- Q8: the binding premise was remeasured before dispatching any route probe or
  implementation work.

## Not verified

- Live NBA CDN endpoint reachability from the pod egress.
- Capture-helper behavior, manifests, restart handling, or backoff behavior.
- Any raw NBA CDN liveData payload capture.

## Summary JSON

```json
{"espn_payloads": 2008, "espn_bytes": 777521676, "measured_game_date_range": "2024-10-22..2026-06-14", "named_game_date_range": "2024-10-22..2026-06-23", "nba_cdn_raw_json_files": 0, "on_court_five_espn": "0/2008", "substitution_event_espn_summary": "1606/1610", "verdict": "FALSIFIED"}
```
