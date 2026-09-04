# S215 Tennis In-Play Census

## Verdict

CLOSED AT LIMIT on the state side. The price-side denominator is exhaustively
classified; no named tennis state source has a tick-joinable timestamp, so no
in-play price row can receive an as-of state without interpolation.

## Inputs and bounded read method

The census ran locally from the `track-a13` worktree. It opened each source
read-only. The price store was processed one Parquet row group at a time (10
row groups; no whole-store materialization). State inputs were schema metadata
only, one file at a time. Grade input was processed one JSONL file at a time.

| Input | Bytes | Resolution / rows | Read purpose |
|---|---:|---|---|
| `C:\Users\neelj\nba-ai-system\data\cache\inplay_odds\tennis_price_series.parquet` | 4,948,107 | 1,854,100 rows; 10 row groups | exhaustive price census |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame\tennis_states__atp.parquet` | 783,216 | 40,516 rows; 1 row group | timestamp schema check |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame\tennis_states__wta.parquet` | 285,269 | 14,559 rows; 1 row group | timestamp schema check |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame\tennis_gamestate__atp.parquet` | 557,856 | 48,512 rows; 1 row group | timestamp schema check |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame\tennis_gamestate__wta.parquet` | 196,262 | 14,559 rows; 1 row group | timestamp schema check |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame\tennis_setdetail__atp.parquet` | 4,319,245 | 30,616 rows; 1 row group | timestamp schema check |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame\tennis_setdetail__wta.parquet` | 1,240,709 | 11,270 rows; 1 row group | timestamp schema check |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame_grade\tennis` | directory | 1,255 JSONL rows | premise re-measure |

## Premise re-measurement

The price-store metadata reports 1,854,100 rows. Exhaustive row-group scanning
finds 986 distinct `event_key` values and 1,864 distinct `ticker_or_slug`
values. Thus S80's 986 is the measured event-key count and S81's 1,864 is the
measured ticker-or-slug count; the figures differ because they count different
fields, not because either is an in-play count.

The grade directory re-measures as 1,255 rows: 1,237 `FINAL` rows and 18 rows
with `market_prob`. The required 1,255 / 1,237 / 18 premise is confirmed.

## Classification

For a nonempty `event_key` with parseable `ts` and `close_time`, a tick before
`close_time` is `PRE_MATCH`; a tick at or after it is `IN_PLAY_NO_STATE` unless
a timestamped as-of state is available. None is available here. `POST_MATCH`
requires a terminal timestamp field; the price schema contains none, so it is
zero rather than inferred from `result_where_known`. Blank keys or unparseable
times would be `UNRESOLVED_KEY`. No state was interpolated.

| Class | Rows |
|---|---:|
| PRE_MATCH | 1,851,294 |
| IN_PLAY_JOINED | 0 |
| IN_PLAY_NO_STATE | 2,806 |
| POST_MATCH | 0 |
| UNRESOLVED_KEY | 0 |
| Total denominator | 1,854,100 |

All 1,854,100 rows are in exactly one class; unclassified rows are 0. The
resolved-event count is 986. The archived per-event summary permits an
independent recomputation of all five class counts and that resolved count.

## State join attempt

| State source family | Potential key | Tick-joinable timestamp columns | Recoverable rows |
|---|---|---|---:|
| `tennis_states__{atp,wta}` | `game_id` | none; `asof_idx` is ordinal | 0 |
| `tennis_gamestate__{atp,wta}` | `game_id` | none; `asof_idx` is ordinal and `date` is day-grain | 0 |
| `tennis_setdetail__{atp,wta}` | `event_id` | none | 0 |

The recoverable-state count is 0. This is an expected valid limit result: no
state table carries a timestamp that can be compared at or before a price tick.

## Archived outputs

- [Summary JSON](S215_tennis_inplay_census_2026-09-04_summary.json)
- [Per-event summary CSV](S215_tennis_inplay_census_2026-09-04_per_event.csv)
- [Read-only census module](../../../scripts/platformkit/ingame/s215_tennis_inplay_census.py)

## NOT VERIFIED

- A state identity match alone is not enough to make a state as-of a tick; no
  timestamped state source exists on disk for this census.
- A post-match boundary cannot be derived from the price schema because it has
  no terminal timestamp. No post-match rows are asserted.
- This census is not a scored comparison and does not alter any model or
  calibration result.
