# Live Operator Runbook

Single source of truth for game-day operations. Walk top-to-bottom on a slate day.

Assumes `conda activate basketball_ai` and `cd C:\Users\neelj\nba-ai-system`.

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
# 1. In-play snapshot daemon (5-min cadence, fires alerts on +EV moves)
nohup python scripts/live_inplay_daemon.py --interval-min 5 --trigger-alerts &

# 2. Watch the live console dashboard
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
  - `tail -f data/lines/*.log` — line-scraper output

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
