# Switch prep 2026-10-06 (switch 2 tennis, switch 3 ncaaf) -- PREPARED, NOT LANDED

PAPER ONLY. Coverage language only. Prepared by the switch-prep lead ~03:00Z-05:20Z 10-06.
Nothing here changes the live config on master; master keeps switch 1 (aa8b4b586).

## Premise check (fresh reads 03:00Z)
- master c43b5a72c contains aa8b4b586 (switch 1). docs/operations/paper_desk_config.json on master:
  sports mlb, nba, nfl, soccer; sports_since nba/soccer 2026-10-07; capacity_rule live_concurrency since 2026-10-07.
- private/adopt/tennis-2026-10-08-r3 = 0a1a974f2 on 5ca3dad7f (switch 1 r4); private/adopt/ncaaf-2026-10-10-r3 = 1a1fe8958 on 0a1a974f2.
- master...tennis-r3: paper_desk_config.json (+12/-1, includes switch 1) and test_s709_desk_root.py (pin).

## Branches (pushed to private only; never origin, no forced push)
- switch 2 = adopt/tennis-2026-10-08-r4 @ e21de8805 (worktree C:/Users/neelj/wt-switch2), `git rebase master`.
  5ca3dad7f was skipped as already applied (identical patch to aa8b4b586); no conflicts.
  Diff vs master: config sports + tennis, sports_since tennis 2026-10-08; CONFIG_SHA re-pin.
- switch 3 = adopt/ncaaf-2026-10-10-r4 @ 6b99f87bb (worktree C:/Users/neelj/wt-switch3), rebased onto switch 2 r4
  (a fast-forward of it). Diff vs master: config sports + ncaaf, tennis; sports_since ncaaf 2026-10-10, tennis 2026-10-08;
  books argv + `--sports mlb,soccer,tennis,nba,wnba,nfl,ncaaf`; test_paper_desk_start.py expects that argv; CONFIG_SHA re-pin.
- CONFIG_SHA check in both worktrees: sha256 of the LF-normalized config equals the pinned value (True, True), the same
  rule test_premise_counts_and_config_pin applies (switch 1 re-pinned the same way in aa8b4b586). The r3 pins carried
  over unchanged because the rebased config bytes are identical to r3's.
- Landing (dispatcher): switch 2 after switch 1's first clean D1 (12:00Z 10-06 publication of 10-07): `git merge --ff-only
  adopt/tennis-2026-10-08-r4` if master has not moved, else rebase again in wt-switch2 and re-run the tests. Switch 3 the
  day after, then ONE books restart on its own UTC date (the argv only takes effect at a books restart).

## Tests (one file per process, RAM gate >= 2500 MB free)
All run 03:06Z-03:08Z 10-06, one pytest process per file, free RAM 2,739-3,207 MB at launch, all green:
- wt-switch2 (e21de8805): test_s709_desk_root 36 passed, test_paper_desk_s562 11, test_paper_desk_tick 14,
  test_paper_desk_s520_schedule 18, test_paper_desk_scope_s736 14 = 93 passed, 0 failed.
- wt-switch3 (6b99f87bb): the same five 36/11/14/18/14 plus test_paper_desk_start 34 = 127 passed, 0 failed.

## (a) What the first tennis D1 would serve (switch 2)
- kalshi/tennis/_heartbeat.json (last_write 03:01:50Z 10-06) carries no per-event list: n_events_tracked 159,
  n_markets_tracked 318, scheduled_games_total 0, n_429_total 0, n_errors_total 0.
- Newest shard kalshi/tennis/2026-10-06.jsonl (11.5 MB, streamed) and the last 60 MB of 2026-10-05.jsonl: event tickers
  dated 26OCT05 and 26OCT06 only (138 distinct 26OCT06 events in the 10-06 tail; series KXATPCHALLENGERMATCH,
  KXATPMATCH, KXATPSETWINNER, KXWTAMATCH). ZERO events dated 26OCT08 or 26OCT09 are listed yet.
- So the first tennis D1 (12:00Z 10-07 publishes day 10-08) serves whatever the venue lists by then; nothing for
  10-08/10-09 exists to check today. The only measured shape is the scratch D1 for 10-06 with all sports: tennis 9/11.
  Tennis competes for the same 6 focus tickers under live_concurrency (floor one game per sport).

## (b) ncaaf load on the books REST budget (switch 3)
- No KXNCAAF* shard exists (books has never run ncaaf; kalshi/ holds mlb nba nfl soccer tennis wnba only), so no
  discovery rows. MEASURED instead with one public read-only events GET at ~03:1xZ 10-06 (series KXNCAAFGAME, status
  open, nested markets, 2 pages): 215 open events, 430 distinct tickers (2 per event). By ticker date: 10-06 1, 10-07 2,
  10-08 4, 10-09 6, 10-10 91, 10-13 2, 10-14 2, 10-15 3, 10-16 37, 10-17 67. Agrees with S739's 211 events
  (10-05 18:5xZ); the DESK_STATE "~420, NOT MEASURED" is now measured: 430.
- Budget (forward_capture_profile in the mlb heartbeat: anonymous_rate_ceiling 3, focus_tick_s 5, focus_share 45):
  15 requests per 5 s tick, split by capture_scheduler.SHARES (45/35/10/5/5) = focus 6, trades ~5, bulk ~1.5,
  discovery ~0.75, reserve. The limiter caps the request RATE at 3/s whatever the sports list is, so ncaaf adds no
  requests per second and does not touch the focus share: served_concurrency TICKER_CAPACITY = 6 (three 2-ticker games)
  is unchanged.
- Cost: bulk refreshes one non-focus GAME per request in rotation (local_capture_runner bulk branch). Tracked events now
  (heartbeats 03:0xZ): mlb 39, nfl 31, nba 60, soccer 142, tennis 159, wnba 4 = 435. +215 ncaaf -> ~650 (+49 pct), so at
  ~1.5 bulk requests per tick each non-focus game's bulk refresh interval grows from ~24 min to ~36 min (rollover from
  unused shares shortens both; arithmetic, NOT MEASURED live). Discovery gains one series key (2 pages per pass).
  Verdict: fits the REST budget (no rate increase, focus unchanged); the price is staler bulk books for non-focus
  games, heaviest on Saturdays (91 ncaaf events on 10-10).

## NOT verified
- No books restart on the switch 3 argv (live only); the bulk interval figures are arithmetic, not a heartbeat reading.
- No D1 rehearsal on the r4 heads; no tennis or ncaaf paper night.
- Tennis 10-08/10-09 listing unknown until the venue lists it.
