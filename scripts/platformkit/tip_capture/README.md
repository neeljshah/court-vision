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

## ingame_capture -- live tick capture

Companion daemon for games already IN PROGRESS (`ingame_capture.py`). Every
~60s it captures every currently-live NBA/WNBA/MLB game (via the existing
`ingame.ingame_live_state.live_states()` ESPN live-scoreboard reader -- no new
transport) and appends one row to
`data/cache/tip_capture/<sport>/ingame_<date>.jsonl` (date=capture date UTC):
```json
{"capture_ts": "...", "sport": "nba", "game_id": "...", "home": "...",
 "away": "...", "period": 3, "inning": null, "clock": 411.0,
 "score_home": 58, "score_away": 55, "source": "ingame_capture",
 "model_sha": "<git HEAD sha>",
 "payload": {"winprob": {...}, "market": {...}, "pbp_tail": {...}}}
```
`period`/`clock` are basketball-only (nba/wnba); `inning` is mlb-only -- the
other is `null` rather than fabricated. `payload.winprob` re-prices
`answers.winprob_dispatch.dispatch()` off the live score/clock/inning state.
`payload.market` reuses `capture.capture_market` byte-identical to the
pregame daemon. `payload.pbp_tail` is the last ~5 ESPN plays (via
`espn_wp_reference.fetch_summary`'s `plays[]`), with `on_floor` participant
names when the feed carries them.

Own singleton lock (`ingame_capture.lock`) and heartbeat
(`data/cache/daemon_heartbeats/ingame_capture.txt`) so this runs alongside
`daemon.py` without contention. Run:
`python -m scripts.platformkit.tip_capture.ingame_capture --once` (cron) or
bare (60s loop, `--tick-sec` to override).
