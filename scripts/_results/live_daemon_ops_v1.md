# live_inplay_daemon — operations guide (v1)

Cycle 93e (loop 5). Operational glue between cycle-88a (`live_game_poll.py`)
and cycle-88n (`save_live_predictions.py`).

The daemon polls every active NBA game every N minutes, writes per-game
snapshots to `data/live/`, then appends one row per (player, stat) per
snapshot to `data/predictions/<date>_inplay.csv`. Cycle-89e
(`probe_inplay_vs_pregame.py`) is the downstream consumer.

## How to launch (game day)

```bash
nohup python scripts/live_inplay_daemon.py --interval-min 5 \
    > data/live_daemon.log 2>&1 &
```

CLI flags:
- `--interval-min N`  poll interval in minutes (default 5)
- `--max-iterations M`  stop after M iterations (default infinite)
- `--auto-stop-iters K`  quit after K consecutive iterations with zero
  active games (default 6 -> ~30 min idle @ 5-min interval; pass 0 to disable)
- `--dry-run`  discover the slate + log the plan, write nothing
- `--date YYYY-MM-DD`  override today's date

## How to monitor

```bash
tail -f data/live_daemon.log
```

Each iteration prints one INFO line:

```
[2026-05-24] active=4 snapshots=4 inplay_rows=112
```

The log rotates at 2 MB (`logging.handlers.RotatingFileHandler`, 3 backups).

## How to stop

Graceful:

```bash
pkill -f live_inplay_daemon
```

The daemon traps `KeyboardInterrupt` and writes
`data/live_daemon.stopped` containing the shutdown timestamp. Absence of
that file after a `pkill` means it didn't shut down gracefully — check
the tail of `data/live_daemon.log` for a stack trace.

## How to verify accumulation (after game day)

```bash
ls data/predictions/*_inplay.csv
wc -l data/predictions/$(date +%F)_inplay.csv
```

Then run the probe:

```bash
python scripts/probe_inplay_vs_pregame.py --date $(date +%F)
```

Expected: per-quarter MAE rows in `scripts/_results/inplay_vs_pregame_<date>.md`.

## Offseason behavior

When `scripts.live_game_poll.discover_games_for_today` returns `[]` the
iteration is a clean no-op (no snapshot writes, no ledger writes). After
`--auto-stop-iters` (default 6) empty iterations, the daemon exits — so
launching with `--auto-stop-iters 0` is required if you want it to stay up
through the offseason (not recommended; just relaunch on game day).

## Error handling

Each network step (slate discovery, poll_once) is wrapped in a single
30-second retry. A second failure logs `[ERROR]` and the iteration is
counted as had_error=True; the daemon stays up and tries again on the
next tick. No transient API blip crashes the daemon.

## Files touched per iteration

- Writes: `data/live/<game_id>_<unix_ms>.json` (one per LIVE+PRE_GAME+FINAL
  snapshot returned by the CDN — cycle-88a behavior, unmodified).
- Appends: `data/predictions/<date>_inplay.csv` (only LIVE snapshots
  contribute rows).
- Touches: `data/live_daemon.log`, `data/live_daemon.stopped` (on exit).

## Smoke test

```bash
python scripts/live_inplay_daemon.py --dry-run --max-iterations 1 \
    --auto-stop-iters 0
```

Expected output: one `daemon start`, one `no slate today` (offseason) OR
one `[dry-run] would poll N games`, one `max_iterations reached`, one
`daemon stop`. Exit code 0.
