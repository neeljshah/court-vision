# tip_capture

Forward capture of tip-time info: for each upcoming NBA/WNBA/MLB game, at
T-60/T-30/T-5 min before tip, archive what was knowable *then* -- injuries,
schedule, our frozen win-prob prior, an optional market price. **Why**:
early in-game predictions look worse partly because we grade them with
hindsight the model never had at tip; a forward record fixes that. Data
capture only -- places nothing, flips no flag.

## Schema

`data/cache/tip_capture/<sport>/<date>.jsonl` (date=tip date UTC), one
append-only row per (game, capture_pass):
```json
{"capture_ts": "...", "sport": "nba", "game_id": "...", "home": "...",
 "away": "...", "tip_time": "...", "capture_pass": "T60|T30|T5",
 "source": "tip_capture", "model_sha": "<git HEAD sha>",
 "payload": {"injuries": {...}, "winprob": {...}, "market": {...}}}
```
`payload.injuries`=whole-sport ESPN injuries feed (no per-game filter; each
row carries its own team name). `payload.winprob`=`winprob_dispatch.dispatch()`
envelope. `payload.market`=best-effort Kalshi/Polymarket (`unavailable`/`error`
never blocks the row).

## Run

`python -m scripts.platformkit.tip_capture.daemon --once` (cron) or bare
(schedule-driven loop). Singleton via POSIX flock (no-op off-POSIX) at
`data/cache/tip_capture/tip_capture.lock`. Heartbeat:
`data/cache/daemon_heartbeats/tip_capture.txt`.
