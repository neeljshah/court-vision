# tier1-1 (loop 5) - live DK/FD prop line scraper v1

## What shipped

- `scripts/fetch_live_prop_lines.py` - LIVE per-book per-minute snapshotter.
  Wraps `src.data.props_scraper.get_current_props` (the existing three-tier
  Odds-API -> direct-scrape -> seed-file chain from cycle 59) so we layer on
  top of the already-debugged auth/header pile instead of re-implementing
  requests.
- `tests/test_fetch_live_prop_lines.py` - 6 tests, all passing.
- Daemon mode for continuous polling under `nohup`.

## Endpoints used (verified existing infra, replicated, not re-discovered)

| Tier | Endpoint | Notes |
|------|----------|-------|
| 1 | `https://api.the-odds-api.com/v4/sports/basketball_nba/events`            | requires `ODDS_API_KEY`. Free tier = 500 req/mo. Most reliable. |
| 1 | `https://api.the-odds-api.com/v4/sports/basketball_nba/events/<id>/odds`  | one call per game, all markets bundled. |
| 2a | `https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/42648/categories/<cat>` | DK public; cat 1215=pts, 1216=reb, 1217=ast, 1218=threes, 1220=stl, 1221=blk. Often 403s. |
| 2b | `https://sbapi.fanduel.com/api/content-managed-page?...&customPageId=nba` | FD public; markets `PLAYER_POINTS`, `PLAYER_REBOUNDS`, `PLAYER_ASSISTS`, `PLAYER_3_POINTERS`, `PLAYER_STEALS`, `PLAYER_BLOCKS`. Often 403s. |
| 3 | `data/props/props_<YYYY-MM-DD>.json` seed file                            | hand-injected fallback. |

These are the SAME endpoints `scripts/poll_line_movement.py` (cycle 88g) and
`scripts/fetch_dk_props.py` (cycle 59) consume. No new endpoint hits were
introduced - we reuse the cached + retried `get_current_props` helper.

## Sample lines

```
$ python scripts/fetch_live_prop_lines.py --once --book dk --stats pts
[2026-05-24T19:48:55] books=['dk'] stats=['pts'] date=2026-05-24
No props fetched from draftkings (all sources exhausted)
[2026-05-24T19:48:55] dk: 0 props returned (blocked, off-season, or empty)
[2026-05-24T19:48:55] done. total new rows: 0  per-book: {'dk': 0}
```

**Off-season note:** Today's date is 2026-05-24 - NBA Finals over, no
preseason scheduled yet. Endpoints respond but return empty event lists. The
scraper handles this gracefully (no crash, no CSV created, exit code 0). Real
sample lines will populate on the first preseason game (early Oct 2026).

When the season is live, expected output:
```
2026-10-25_dk.csv (first preseason day, hypothetical):
captured_at,book,game_id,player_id,player_name,team,stat,line,over_price,under_price,market_status
2026-10-25T18:30:00,draftkings,,,"Nikola Jokic",,pts,28.5,-115,-105,open
2026-10-25T18:30:00,draftkings,,,"Nikola Jokic",,reb,11.5,-110,-110,open
...
```

## Rate-limit observations

- Cycle 59 + 88g empirically found Odds API tolerates ~1 req / 0.4 s; we
  inherit that pacing via `props_scraper._fetch_odds_api_props`.
- Direct DK/FD scrape: `_fetch_dk_all_props` uses 1.0s between calls
  (one per stat category). We add a further `_INTER_BOOK_PAUSE_SEC = 1.0`
  between books inside a single fetch cycle.
- 429 handling: backoff 30s + retry ONCE; if still rate-limited, skip that
  book for that cycle (daemon survives, next cycle reattempts).
- 403/IP-block: log + skip + continue (no crash).

## Recommended daemon cadence

| Mode | Cadence | Why |
|------|---------|-----|
| All-day passive | `--interval-min 15` | conserves Odds API quota (96 cycles/day x 12 events <= 1152 calls; over the 500/mo free tier on a per-day basis, but acceptable for active game days only) |
| Pre-game window (3h before tip) | `--interval-min 10` | catch line moves at the standard line-firming windows |
| Live games | `--interval-min 5` | sharp money + injuries reprice fastest in-game |
| Quota-tight | `--interval-min 30` | safest for free Odds API tier |

**Launch:**
```bash
nohup python scripts/fetch_live_prop_lines.py --interval-min 10 \
    > vault/Improvements/live_prop_scraper.log 2>&1 &
```

**Quota math (Odds API free tier, 500 req/mo):**
- 1 events-list call + ~12 per-event calls = ~13 calls per `fetch_once`
- 10-min cadence = 144 cycles/day = 1872 calls/day -> blows free tier in 8h
- Recommendation: enable only during 4h game-window (pre-tip -> last final
  buzzer), or upgrade Odds API quota, or rely on tier-2 direct scrape during
  off-window polls

## Schema (data/lines/<date>_<book>.csv)

`captured_at, book, game_id, player_id, player_name, team, stat, line,
 over_price, under_price, market_status`

- `game_id`, `player_id`, `team` are best-effort blanks - re-joined by
  `compute_clv.py` / `clv_tracker.py` at backtest time via player_name + date.
- Dedup key: `(player_name_lower, stat, captured_at[:16])` - rounds to minute,
  daemon idempotent under crash + restart.

## Tests (6/6 passing)

```
tests/test_fetch_live_prop_lines.py::test_dk_two_players_three_stats_writes_six_rows PASSED
tests/test_fetch_live_prop_lines.py::test_fd_two_players_three_stats_writes_six_rows PASSED
tests/test_fetch_live_prop_lines.py::test_dedup_same_player_stat_minute_keeps_one_row PASSED
tests/test_fetch_live_prop_lines.py::test_empty_returns_no_crash_and_zero_rows PASSED
tests/test_fetch_live_prop_lines.py::test_429_triggers_backoff_then_retry_then_skip PASSED
tests/test_fetch_live_prop_lines.py::test_csv_schema_exact_match PASSED
```

## Open follow-ups (for next cycle)

- Wire `compute_clv.py` to read `data/lines/*_dk.csv` and `*_fd.csv` directly
  (currently reads the cycle-59 `data/lines/<date>.csv` daily-snapshot file).
- Add `--book consensus` mode that emits a 3rd file with min-over / max-under
  across all books per (player, stat) to surface the sharpest line.
- Once 7+ days of live data accumulate, run `backtest_vs_closing_lines.py`
  against real closes instead of the L5-baseline proxy.
