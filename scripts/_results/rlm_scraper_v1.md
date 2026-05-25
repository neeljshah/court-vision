# RLM Scraper v1 — snap_action_network_bets (tier3-12, loop 5)

## Endpoint verification

**Verified live 2026-05-24:**
- `GET https://api.actionnetwork.com/web/v2/scoreboard/nba?period=game&bookIds=15&date=YYYYMMDD`
  -> returns list of NBA games with game-level moneyline/spread/total bet_info populated.
- `GET https://api.actionnetwork.com/web/v2/games/{game_id}/props`
  -> per-game per-player prop markets keyed by `core_bet_type_<id>_<stat>`. Verified payload contains `lines.15[over/under]` with `value` (the line) and `bet_info.tickets.percent` / `bet_info.money.percent` (the pct fields).

**Endpoint refresh procedure if it drifts:**
The script raises `EndpointUnavailable` on 403/404. Daemon logs a one-line WebSearch hint pointing operators to:
```
WebSearch 'action network v2 scoreboard nba endpoint'
```
Update `_AN_SCOREBOARD` and `_AN_GAME_PROPS` constants if AN changes paths again (last migration: v1 -> v2 in 2026-05).

## Sample data fetched

Real one-shot run on 2026-05-24 at 19:52 captured **121 prop rows** across today's NBA schedule from DraftKings (bookIds=15). Output written to `data/action_bets/2026-05-24_1952.csv`. Sample:

```
captured_at,game_id,player_id,player,stat,line_opening,line_current,pct_bets_over,pct_money_over,line_move_dir,rlm_flag
2026-05-24T19:52:15,291187,62837,De'Aaron Fox,pts,14.5,14.5,0,0,0,N
2026-05-24T19:52:15,291187,63465,Isaiah Hartenstein,pts,7.5,7.5,0,0,0,N
2026-05-24T19:52:15,291187,63495,Luke Kornet,pts,2.5,2.5,0,0,0,N
2026-05-24T19:52:15,291187,65129,Alex Caruso,pts,7.5,7.5,0,0,0,N
```

**Important caveat (already noted in `src/data/action_network.py`):** per-prop `pct_bets_over` and `pct_money_over` come back as **0** in the free tier — Action Network gates player-prop bet_info percentages behind PRO. Game-level percentages (moneyline / spread / total) ARE published and could be inherited per the existing `_game_rlm()` helper.

Implications for the accumulation workstream:
- Until PRO access is available, `rlm_flag` will stay `N` at the prop level by construction (the >=5pp money-vs-bets asymmetry can never trigger when both are 0).
- The **line-movement** half of the signal IS captured correctly — `line_opening` is persisted across polls in `data/action_bets/<date>_openings.csv` and subsequent snapshots compute `line_move_dir` correctly (verified by `test_opening_line_preserved_across_polls`).
- Future extension: layer the existing `src.data.action_network._game_rlm(game)` GAME-level flag onto each prop row to get a partial signal in the meantime.

## Daemon launch instructions

One-shot (for cron / ad-hoc):
```
python scripts/snap_action_network_bets.py --once
```

Daemon mode, every 15 minutes (matches AN's ~15-min cache TTL):
```
nohup python scripts/snap_action_network_bets.py --interval-min 15 \
    > vault/Improvements/rlm_scraper.log 2>&1 &
```

Per-date backfill (only useful within today's window — AN doesn't expose historical bet%):
```
python scripts/snap_action_network_bets.py --date 2026-05-24 --once
```

Polite-throttle: the script sleeps `_INTER_GAME_PAUSE_SEC` (1.0s) between per-game prop fetches, well under the 1 req/sec floor. Scoreboard endpoint is hit once per snap.

## How to compute residual ROI on RLM-flagged props after 30 game-days

After 30+ game-days of accumulated `data/action_bets/<date>_<HHMM>.csv` snapshots, the analysis script (not yet built — call it `scripts/backtest_rlm_residual_roi.py`) should:

1. **Aggregate to one row per (game_id, player_id, stat):** the final snapshot of the day (latest HHMM) gives the closing line, opening line, and final `rlm_flag`.
2. **Join to actual stat outcomes** from `data/season_games.parquet` or `data/player_quarter_stats.parquet` by `game_id + player_id + stat`.
3. **Compute the bet result:** under standard -110 / -110 American odds, the bet won iff (the side the SHARP money favored hit the line):
   - On `rlm_flag=Y` rows with money_on_over (pct_money_over > pct_bets_over): bet OVER, won iff `actual_stat > line_current`.
   - On `rlm_flag=Y` rows with money_on_under: bet UNDER, won iff `actual_stat < line_current`.
4. **Compute residual ROI:** `total_profit_units / total_risked_units` where `profit = +0.909` on a win and `-1.0` on a loss. Compare to a baseline of betting EVERY prop on the opening line (random side) — RLM residual ROI is the delta.
5. **Stratify** by `abs(line_current - line_opening)` (small move vs >=1.0 move) and by `abs(pct_money_over - pct_bets_over)` (5-10pp vs >=15pp) to find the cell where the signal is strongest.
6. **Statistical gate:** require N >= 200 RLM-flagged props in the cell AND `(roi - baseline_roi) / std_err >= 2.0` (Wald two-sigma). Below the gate, conclude "no signal".

Until per-prop pct_bets/pct_money becomes available (PRO subscription or fallback to game-level inheritance), the script's value is in **establishing the data ingestion pipe** so that the moment we have the data we already have history accumulating. Line-movement alone (no pct fields) is testable now via the same script — `line_move_dir` is populated correctly.

## Tests

`tests/test_snap_action_network_bets.py` — 6 tests, all passing in 0.24s:

1. `test_two_props_yields_two_rows` — mock AN response with 2 props -> 2 canonical rows
2. `test_rlm_flag_computation_matches_manual_logic` — 5 fixture scenarios covering the (money_side, line_move) truth table including the <5pp threshold edge case
3. `test_offseason_empty_schedule_no_crash` — empty `games: []` writes header-only CSV
4. `test_endpoint_unavailable_graceful_exit` — 403 raises `EndpointUnavailable`, daemon logs WebSearch hint, writes empty CSV, exits cleanly
5. `test_csv_schema_matches_spec` — canonical 11-column schema verified field-by-field
6. `test_opening_line_preserved_across_polls` — opening-line ledger correctly preserves the FIRST line seen across two polls separated by an hour

## Files added

- `scripts/snap_action_network_bets.py`  (script + CLI + daemon)
- `tests/test_snap_action_network_bets.py`  (6 tests, all pass)
- `data/action_bets/2026-05-24_1952.csv`  (first real snapshot, 121 props)
- `data/action_bets/2026-05-24_openings.csv`  (opening-line ledger)
