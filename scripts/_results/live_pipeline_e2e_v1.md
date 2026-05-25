# Live Pipeline E2E Integration -- v1

Tier 4 integration (loop 5, 2026-05-24)

## Purpose

Loop 5 has shipped 14+ live-system components (cycles 88a-n, 89b-93e, plus
Tier 1.1/2.5/2.6/2.7/2.8/3.10/3.11/3.12). Each one was tested in isolation
but they had never been exercised together as a single pipeline. This deliverable
fills that gap with:

* `tests/test_live_pipeline_e2e.py` -- pytest integration test
  (`test_live_pipeline_end_to_end`) that walks the entire happy path
  with mocked I/O so it can run anywhere, anytime.
* `scripts/run_live_pipeline_smoke.py` -- operator CLI that runs the same
  9 steps with verbose stdout. Exit code 0 = all green; non-zero = step #
  that broke.

Run:

```
python -m pytest tests/test_live_pipeline_e2e.py -q
python scripts/run_live_pipeline_smoke.py            # green summary
python scripts/run_live_pipeline_smoke.py --verbose  # show payloads
```

## Component Dependency Diagram

```
                 +-----------------------------------+
                 |   scripts/live_game_poll.py (88a) |
                 |   (snapshot writer, NOT exercised |
                 |    by smoke test -- mocked)       |
                 +-------------------+---------------+
                                     |
                                     v writes JSON
                          +----------+---------+
                          |   data/live/*.json |    schema-of-record
                          +----------+---------+
                                     |
                                     v
        +----------------------------+----------------------------+
        |             src/data/live.py    (canonical loader)      |
        |   load_live_state, is_live, find_player, parse_clock    |
        +----+-----------------+--------------+-------------------+
             |                 |              |
             v                 v              v
   +---------+---+    +--------+-----+    +---+-----------------+
   | live_engine |    | live_edge    |    |  save_live_         |
   | (95c)       |    | _eval (88j)  |    |  predictions (88n)  |
   |             |    |              |    |                     |
   | project_    |    | evaluate_all |    |  append_to_ledger   |
   | from_snap-  |    | -> action    |    |  data/predictions/  |
   | shot ->     |    | bands        |    |  <date>_inplay.csv  |
   | 14 rows     |    |              |    |                     |
   +-----+-------+    +------+-------+    +---------------------+
         |                   |
         v                   v
   +-----+----------+   +----+-----------------------------------+
   | data/lines/    |   | webhook_alerts.WebhookNotifier         |
   | <date>_dk.csv  |   | (Slack/Discord, ba548e1c)              |
   | (8d40558a)     |   |                                        |
   |                |   |   send(EDGE_FLIP, ...) -> urlopen()    |
   | fetch_live_    |   +----+-----------------------------------+
   | prop_lines.py  |        |
   +--------+-------+        v
            |          operator sees alert -> places bet on book
            |                |
            v                v
   +--------+----------------+------------------------------------+
   |  src/betting/pnl_ledger.py (8762cd94)                        |
   |    place_bet     -> bet_id, deducts stake                    |
   |    settle_bet    -> won/lost/push, P&L, bankroll             |
   |    pnl_summary   -> win_rate, roi, total_profit              |
   |  data/pnl_ledger.csv (manual single source of truth)         |
   +--------+-----------------------------------------------------+
            |
            v
   +--------+-----------------------------------------------------+
   |  src/betting/clv.py (Tier 2.7, commit 7ccca701)              |
   |    compute_clv(bet_row, closing_line, closing_odds) ->       |
   |       clv_line, clv_odds, clv_percent, beat_close, notes     |
   |    find_closing_line(book, game_id, player_id, stat, side,   |
   |       asof) -> joins data/lines/<date>_<book>.csv snapshots  |
   +--------------------------------------------------------------+
```

## "If something breaks on game day, where to look"

The smoke CLI fails with the offending step number. Each alert / failure
type below maps to the root cause module(s):

| Alert / failure                                  | Look first at                                                       |
| ------------------------------------------------ | ------------------------------------------------------------------- |
| Step 1 fails (snapshot reload)                   | `scripts/live_game_poll.py` (writer), `src/data/live.py` (loader)   |
| Snapshot has zero players                        | `live_game_poll` boxscore parser; check `data/live/<game>_*.json`   |
| Step 2 fails (projection)                        | `src/prediction/live_engine.py`; underlying `scripts/predict_in_game.py`; `src/prediction/live_factors.py` (foul_trouble_factor table) |
| Wrong row count (!= 2 * 7)                       | `scripts.predict_in_game.project_snapshot` STATS tuple              |
| Step 3 fails / no lines                          | `scripts/fetch_live_prop_lines.py`; `src/data/props_scraper.py` (Odds API quota / DK/FD block / `BlockedByBook`) |
| Lines stale by minutes                           | `--interval-min` flag on the daemon; cron / nohup log               |
| Step 4 fails / no edge action                    | `scripts/live_edge_eval.py` (`HEDGE_THRESHOLD`, `LET_IT_RIDE_THRESHOLD`); name matching via `src/data/live.find_player` |
| Edge says NOT PLAYING for a confirmed starter    | `_name_key` diacritic normalisation in `src/data/live.py`; snapshot's `players[*].name` vs bet log `player` field |
| Step 5 fails to POST                             | `src/notifications/webhook_alerts.py`; env vars `SLACK_ALERT_WEBHOOK` / `DISCORD_ALERT_WEBHOOK`; check `_post` log line |
| Webhook 4xx                                      | webhook URL revoked / changed in Slack/Discord; rotate              |
| Step 6 fails (bet placement)                     | `src/betting/pnl_ledger.py`; concurrent lock (`pnl_ledger.csv.lock` stale > 30s); permissions on `data/`         |
| Bankroll math off                                | `pnl_ledger._append_bankroll`; `current_bankroll`; check `data/pnl_bankroll.csv` |
| Step 7 fails (settlement)                        | `pnl_ledger._resolve_status` (push tolerance), `_compute_profit`; `auto_settle_date` if using gamelog auto-resolve |
| Status WRONG (lost vs won)                       | Side field on the bet row; cycle-88j action vs actual book ticket   |
| Step 8 fails (CLV import / compute)              | `src/betting/clv.py` (Tier 2.7); closing snapshots at `data/lines/<date>_<book>.csv`; check `_name_key` + `_book_canon` for join |
| beat_close=False / null on every bet             | Closing snapshot missing -- daemonise `python scripts/fetch_live_prop_lines.py --interval-min 10` so a "30 min before tip" snapshot exists |
| Step 9 wrong roi / win_rate                      | `pnl_ledger.pnl_summary` filters (`date_range`, `filter_by`); status filter (`won`/`lost`/`push` only -- `voided` excluded) |

### Cross-component gotchas

* The snapshot's `players[*].name` must round-trip through accent normalisation
  -- bug surfaces as "NOT PLAYING" at step 4 even though the player IS in
  the snapshot. Owner: `src/data/live._name_key`.
* `pnl_ledger.LEDGER_CSV` / `BANKROLL_CSV` / `LOCK_PATH` are module-level
  constants. Tests + this smoke CLI **must** repoint them via `monkeypatch.setattr`
  (test) or direct assignment after `importlib.reload` (CLI) -- otherwise
  the run pollutes the real `data/pnl_ledger.csv`.
* `live_edge_eval.evaluate_bet` calls `pig.foul_trouble_factor(pf, period)` --
  the cycle-89b table is the single canonical version. If you see a foul-
  trouble penalty that doesn't match the dashboard, check that all three
  importers (`predict_in_game`, `live_player`, `save_live_predictions`)
  defer to `src/prediction/live_factors.py`.

## Test inventory

* `test_live_pipeline_end_to_end` -- the actual 9-step walk-through. PASS.
* `test_each_step_has_meaningful_assertion_message` -- meta-test: every
  `assert` in the e2e function carries an explanatory failure message
  (otherwise pytest output is useless on real failures). PASS.

## Ship history

* v1 shipped 2026-05-24 (loop 5, tier4-int). Initial 9-step happy-path walk.
  Test files first landed in commit `cb39cbd6` (mixed batch-12 commit); this
  follow-up doc revision formalises the tier4-int attribution.

## Ship verification

```
$ python -m pytest tests/test_live_pipeline_e2e.py -q
..                                                                       [100%]
2 passed in 0.41s

$ python scripts/run_live_pipeline_smoke.py
=== LIVE PIPELINE E2E SMOKE  (2026-05-24T20:06:13) ===
[1/9] Snapshot ingest          OK  -- snapshot written + reloaded (2 players)
[2/9] Projection               OK  -- projected 14 (player, stat) rows
[3/9] Line scrape (mocked)     OK  -- wrote 1 synthetic prop line
[4/9] Edge re-evaluation       OK  -- proj=29.33 new_ev=+0.124 action=LET IT RIDE
[5/9] Webhook alert (mocked)   OK  -- webhook POST captured
[6/9] Bet placement            OK  -- bankroll=950.00
[7/9] Settlement               OK  -- WON P/L=+$43.48 bankroll=$1043.48
[8/9] CLV                      OK  -- beat_close=True clv_line=1.5
[9/9] P&L summary              OK  -- win_rate=1.00 roi=+0.8696 profit=$+43.48
=== ALL 9 STEPS GREEN ===
```
