# Live Operator Runbook

Single source of truth for game-day operations. Walk top-to-bottom on a slate day.

Assumes `conda activate basketball_ai` and `cd C:\Users\neelj\nba-ai-system`.

> **What you are operating:** the pregame numbers come from the
> [possession Monte-Carlo simulator](architecture/possession-simulator.md); during a
> game they are repriced by the in-game engine (pregame prior x realized state,
> elapsed-weighted) documented in [LIVE_ENGINE_V2.md](LIVE_ENGINE_V2.md). The
> always-on browser UI is [LIVE_ENGINE_V2_WEB.md](LIVE_ENGINE_V2_WEB.md). Full doc
> map: [INDEX.md](INDEX.md).
>
> **HONESTY RAIL:** every live number is forecaster CALIBRATION, not a dollar edge --
> a live book sees the same game state you do. The in-game grade loop below measures
> CLV in probability space only (`edge_claimed=False`); no `$`/ROI/edge is claimed.
> Truth source for any number: [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) /
> [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

---

## Pre-game (morning of game day)

Run 30 minutes before tip-off of the first game.

```bash
# 1. Today's pre-game predictions (every rostered player on the slate)
python scripts/predict_slate.py --date YYYY-MM-DD

# 2. Verify roster / injury status (pulls latest inactives)
python scripts/update_inactives.py --date YYYY-MM-DD

# 3. Start live line scraper as a background poller (10-min cadence)
nohup python scripts/fetch_live_prop_lines.py --interval-min 10 &

# 4. Generate the pre-game bet shortlist against DK
python scripts/compare_to_lines.py --date YYYY-MM-DD --book DK
```

Place pre-game bets manually via the DK app, then record each in the ledger:

```bash
python scripts/place_bet.py --strategy pregame --game GAME_ID --player PLAYER_ID \
  --stat PTS --line 22.5 --side over --book DK --odds -110 --stake 25
```

---

## During games

```bash
# 1. Live Engine v2 orchestrator (event-driven, sub-30s reactive re-projection --
#    replaces the old 5-min-cadence live_inplay_daemon.py; see LIVE_ENGINE_V2.md)
python scripts/live_orchestrator.py --game-id GAME_ID --enable-dashboard

# 2. (alt) Watch the live console dashboard standalone
python scripts/live_dashboard.py

# 3. Halftime bet window (~end of Q2)
python scripts/recommend_endQ2_bets.py --date YYYY-MM-DD
#   - Viable at halftime: REB, AST, FG3M, STL, BLK
#   - Tag halftime bets with --strategy endQ2 in place_bet.py
#   - PTS and TOV need end-of-Q3 info — rerun the same recommender after Q3
```

If a line moves dramatically against an open bet, size a hedge:

```bash
python scripts/live_hedge_calc.py --stake 25 --open-odds -110 --live-odds +145
```

---

## What the halftime / endQ3 recommender is doing

`recommend_endQ2_bets.py` and the post-Q3 rerun are not new models -- they call the
same in-game repricer at a snapshot BOUNDARY. The engine blends the pregame prior
with realized box state, elapsed-weighted, and stacks only the boundary-specific
detail layers that PASSED the held-out-Brier gate
(`scripts/platformkit/ingame/ingame_layer_gate_nba.py`). Practical consequences:

- Viable at halftime (endQ2): REB, AST, FG3M, STL, BLK -- 24 minutes of remaining
  signal is enough for these.
- PTS and TOV need end-of-Q3 info -- rerun the recommender after Q3 (12 minutes
  remaining, where linear extrapolation of the box is already near-optimal).
- `q50` is the point; the q10/q90 bands are advisory and never move it.

## In-game grade loop (measure CALIBRATION, never claim edge)

Closing the honesty loop on live games: at each tick `live_grade.capture_pair_once`
pairs OUR model's P(home win) with the REAL captured venue in-play implied P(home)
for the SAME side (HOME), and stores the pair. Both probs were computed live from
state-as-of-that-tick, so replaying the stored model prob at grade time is leak-free.

The capture + grade entry points live in
`scripts/platformkit/ingame/live_grade.py` (`capture_pair_once` per tick,
`grade_game` over a settled game's `data/cache/ingame_grade/<sport>/<game_id>.jsonl`),
driven by `scripts/platformkit/ingame/live_loop.py`.

Binding rules the loop enforces (do not work around them):
- A SINGLE partial game is NEVER a beat -- below `min_ticks` pairs the verdict is
  `INSUFFICIENT_DATA`. The real test is aggregating MANY settled games.
- A missing or misaligned (wrong-side / out-of-range) prob is SKIPPED, not graded --
  a misaligned pair manufactures fake CLV.
- Output is CLV in probability space with `edge_claimed=False`. No `$`/ROI/stake.

## Post-game / settlement

```bash
# 1. Stop background pollers (Windows: use Stop-Process or close consoles)
pkill -f live_inplay_daemon
pkill -f fetch_live_prop_lines

# 2. Auto-settle every open bet for the date
python scripts/settle_bet.py --auto --date YYYY-MM-DD

# 3. Rolling P&L by strategy
python scripts/pnl_report.py --range 7d --by strategy

# 4. Closing-line value report
python scripts/clv_report.py --range 7d --by stat
```

---

## Monitoring

- Alert webhooks (set in shell or `.env`):
  - `SLACK_ALERT_WEBHOOK` — Slack incoming webhook URL
  - `DISCORD_ALERT_WEBHOOK` — Discord channel webhook URL
  - Wired in `src/notifications/webhook_alerts.py`
- Logs:
  - `tail -f data/live_daemon.log` — in-play poll loop
  - Line-scraper output: `fetch_live_prop_lines.py` logs to stdout only (no
    log file) -- redirect it yourself, e.g. `... >> vault/Improvements/live_prop_scraper.log 2>&1`;
    its data output lands in `data/lines/<date>_<book>.csv`

---

## Failure recovery

- **NBA snapshot poll fails** (Stats API down/429): the daemon already retries; if persistent, backfill the missed window from the boxscore endpoint via `scripts/aggregate_quarter_boxscores.py` and re-run `scripts/retro_inplay_mae_v2.py` to confirm no gap in features.
- **Line scraper blocked (403)**: stop `fetch_live_prop_lines.py`, switch the source flag to a backup (Action Network), or pause and resume after the cooldown window.
- **P&L ledger corrupted**: ledger lives at `data/pnl_ledger.csv` with timestamped backups `data/pnl_ledger.csv.backup-<ts>`. Copy the latest backup over the live file and re-run `scripts/pnl_report.py` to confirm.

---

## Off-day maintenance

```bash
# Re-aggregate quarter-level boxscores (in-play feature inputs)
python scripts/aggregate_quarter_boxscores.py

# Retroactive in-game system MAE — tracks live-system performance over time
python scripts/retro_inplay_mae_v2.py

# Refresh the season game cache
python scripts/fetch_season_games_2025_26.py --refresh
```

---

## Convenience wrappers

- `scripts/operator_morning.sh DATE` — runs the four pre-game steps in order.
- `scripts/operator_settle_eod.sh DATE` — stops daemons, settles, and prints P&L + CLV.

Both accept `--dry-run` to print the planned command sequence without executing.


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
