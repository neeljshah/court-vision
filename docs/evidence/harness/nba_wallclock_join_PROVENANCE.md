# NBA wall-clock join provenance

The following is the verbatim module docstring from pre-S145 commit
`333af3149fde92cca7b0b8dd95dae94fde97bafa`.

```python
"""scripts.platformkit.venue_history.nba_wallclock_join -- NBA GOAL 1b: join historical play-by-play GAME STATE to historical Kalshi MARKET PRICE by real WALL-CLOCK time -> the first NBA checkpoint parquet (state x prob).  WHY WALL-CLOCK: pbp_states_2025_26.parquet (domains.basketball_nba. ingest_pbp_states) carries only game-clock -- no UTC. cdn.nba.com's liveData feed is WAF-BLOCKED here (backfill_pbp_espn.py). ESPN's free summary endpoint's ``plays[]`` DOES carry an absolute ``wallclock`` ISO8601 field per play (verified live 2026-07-09, event 401869406 BOS@PHI) -- used directly as the join key, no derived clock-to-UTC conversion.  SOURCES: data/venue_history/kalshi/nba/KXNBAGAME-*.jsonl (106 files = 53 distinct 2026-playoff events, read-only). Kalshi tail = AWAY+HOME concatenated, no delimiter; every NBA tricode is exactly 3 chars, so the split is always at position 3. outcome_home_win comes from the HOME-side ticker's own settled ``result`` field -- NOT games.parquet, which stops at the regular season (max date 2026-04-12, zero playoff rows).  ESPN event id resolution: scoreboard fetch for the ticker's date (+/-1 day fallback), abbreviations normalized via espn_nba_bridge._norm_abbr, matched on (away, home). Politeness: 1 req/s, on-disk cache under data/cache/nba_pbp_wallclock_raw/{scoreboard,summary}/ (resumable).  JOIN: pd.merge_asof(candles, states, on='ts', direction='backward') -- a candle at T gets the LATEST state with ts<=T, never future state (no leak).  OUTPUT: data/cache/inplay_odds/nba_checkpoints_2025_26_playoffs.parquet -- game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_ticker, market_prob, traded, outcome_home_win. game_id/ts are int64.  CALIBRATION substrate only -- no $ field, no edge claim; a join, not a model. INVARIANTS: platformkit-only; <=300 LOC; ASCII only; local commits only; never writes data/registry/; never flips a flag.  Per-file test: python -m pytest scripts/platformkit/venue_history/test_nba_wallclock_join.py -q CLI: python -m scripts.platformkit.venue_history.nba_wallclock_join """
```

S145 moved this provenance out of the module to keep the module within its 300-LOC rail.
S141 subsequently added the 300-second staleness rail; its current behavior and replay are
recorded in `S141_nba_wallclock_tolerance_2026-09-03.md`. The historical text above remains
unchanged so its source can be compared directly with git history.
