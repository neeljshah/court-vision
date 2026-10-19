# Live paper betting, per sport: measured chain and plan (2026-09-29)

Opus orchestrator 4. Three read-only Sonnet sweeps (execution chain, per-sport capture and model, live-shadow design inputs), load-bearing facts re-checked by the orchestrator at about 17:30Z. PAPER ONLY: nothing here places, routes or authenticates an order. Calibration language only; arm A is the raw venue YES mid, never "devigged" (S495). Register ids S515-S519 are reserved for this plan.

## Bottom line

- **Nothing in the paper-betting chain runs live during games today.** The only processes running near it are the three capture supervisors and their children (books `local_capture_runner`, state `local_state_capture`, `polymarket_live_capture`; about 400 MB RSS together at 17:30Z). They write `data/cache/ingame_books_local/` and `data/cache/ingame_state_local_v2/` and nothing else.
- **Everything downstream is a post-hoc nightly replay:** `paper_night.py` runs qualification (forward_replay), fill_realism, week, scoreboard, history and arm E as one-shot children over whole captured shards.
- **Every replayed quote anchors on the observed mid.** `quote_engine.py:3-5` makes the contemporaneous mid the documented default, and forbids a standalone model value as the default anchor. `fill_realism.py:94` and `forward_replay_policy.py:145,151` pass `anchor=None`. No model probability reaches any paper quote today.
- **Receipts are MLB-only and stale.** fill_realism newest `2026-09-24.json` (counts only), qualification `2026-09-22.json` (the 09-24 file is 0 bytes), scoreboard `2026-09-24.json` (every cell INSUFFICIENT, B/C/D `model_not_reconstructible`), nights 09-24..09-26 all PARTIAL (RAM floor), `markouts/` EMPTY, registry_e 09-26 REFUSED `config_not_effective`.
- **The only real-time paper-quote code path is dormant legacy:** `ingame/inplay_capture_loop.py:52` -> `inplay_daytrader.on_tick` -> `execution/paper_maker.py:182` (fair_prob = model prob, MockKalshiExchange). No ProcSpec starts it; heartbeats `m2_inplay*` last written 2026-07-27. It does its own ESPN polling (duplicate network load) and is not reused here.
- `exec_quality_daemon.py` is measurement-only (docstring :23), not running (heartbeat 2026-07-17). `executor/lifecycle.py:115-133` raises on any live exchange. `venue_eligibility.py` has no execution caller.

## Per-sport table (live today = something runs during the game)

| Sport | Live today? | Captured live (09-29, ~17:30Z) | Live-callable model prob | Served schedule | Missing | Blocker |
|---|---|---|---|---|---|---|
| mlb | Capture only | Books `kalshi/mlb/2026-09-29.jsonl` 4,203 rows (KXMLBGAME snapshot_bulk + 2,112 trades); Polymarket 38,520 rows; state 1,572 rows (all pre so far; PHI@ATL 18:00Z, CWS@HOU 21:00Z, BOS@NYY 00:00Z tonight). State carries inning/half/outs/bases/score, real `scheduled_start_utc`. | `mlb_live_model.mlb_home_prob({p0,state_diff,frac_elapsed})` (:87), pure, no I/O, never raises. p0 via `live_p0_resolved` reads `data/frontend/predict_service/mlb/latest.json` = 2026-07-27, so every postseason game falls to BASE_FALLBACK (p0 None) -> None. | 2 games 09-29, 3 games 09-30 (pointer day 09-30) | A live quoter; a causal p0 (the stale store gives none); a live fill receipt. | S515 (recorder), S516 (fills). p0 decision below. |
| nfl | Capture only | Books 82,723 rows (KXNFLGAME, KXNFLSPREAD), 103 MB; state 17,680 (MNF 1,047 live). | NONE (no nfl in-game model; not in scoreboard CORPUS, `ingame_scoreboard_rules.py:140`). | MNF 09-29 done; next NFL 10-02 (TNF) | Model; ESPN rows have `scheduled_start_utc=null` (S502) | S492 (improve run), S502. Mid-only shadow arm possible after S515. |
| soccer | Capture only | Books 2,928 rows, 6 leagues, no trades; state 320 rows all final, EPL-only. | NONE live per-tick (pregame prior only). | none served 09-29/09-30; first fixtures ~10-09 | Model, league identity, trades | S490 (orch 1), S502, S531. |
| nba | Capture only | Books 685 rows (preseason); state 393 all pre. | `nba_logistic_pricer.get_pricer().price(margin, frac_elapsed, prior_prob)`, frozen artifact, cheap; needs p0. | none (season opens 10-20) | p0 source, season type | S494 (orch 1), S482, S502. |
| wnba | Capture only | Books 130 rows (KXWNBAGAME), no trades; state 786 all pre. | `wnba_ingame_shadow.get_shadow().shadow_prob(sport,home,away,state)`, but it builds an adapter from a parquet (not pure; RAM unmeasured). | none served (GS@DAL 09-30 not served) | Served schedule slot, trades | S491, S502, S531 (served cap). |
| tennis | Capture only | Books 157,579 rows, 247 MB; state 1,026,432 rows, 741 MB (3,048 live), sets only. | `tennis_point_recursion.match_win_prob` (:200) pure recursion; state has sets only, so set-level precision. | none served | games/points/server; RAM (a whole-shard read is unsafe) | S493, S502. Tail-only reads mandatory. |

## What a light LIVE SHADOW paper quoter needs (design, measured inputs)

Every N seconds (default 15) during a served game it reads the newest captured book row and state row, computes a model probability, records the maker quotes it WOULD post, and writes nothing else. Fills are computed afterwards against the captured tape.

1. **Inputs, tail-only.** Book and state shards are append-only JSONL, one `os.write` per row with per-tick fsync (`local_capture_writer.py:110-160`), so a concurrent reader is safe if it drops a trailing partial line. `capture_watchdog.tail_rows(path, errors, limit)` (:51-72) already reads the last N bytes. Tail 2-4 MB; also read the previous UTC day's shard across midnight. Never load a whole day (NFL 108 MB, tennis 247/741 MB).
2. **Linkage.** Served schedule files `docs/evidence/forward/schedules/<D>_maker_forward.json` (entries carry sport, game_key, ticker, scheduled_start). Read D = today and tomorrow UTC (the pointer is D1). Match state rows by `game_key` and book rows by `ticker`.
3. **Causality.** Decision instant t = wall-clock UTC at the tick. Only rows with `response_end_ts <= t` (the capture clock; never `request_start_ts` or `tick_start_ts`). Record each source row's `response_end_ts` and `raw_sha256`/line hash. Refuse the quote (record the reason) when book age or state age exceeds a freshness bar, the market is not active, or the game is final (`paper_maker.py:15-19` markers). Trades are never read while recording.
4. **Model probability, MLB.** `mlb_home_prob` with state_diff = home - away runs and frac_elapsed from inning/half (18 half-innings, `ingame_live_state._frac_elapsed` convention). **p0 decision:** the predict_service store is dark (07-27), so p0 = the venue YES mid of the last book row observed while the state status was `pre` and before `scheduled_start` (a causal, market-anchored prior, labelled `p0_source=venue_pregame_mid`; this is the "market anchor + state residual" shape, not an independent model). No p0 -> model arm refuses `p0_missing`; never a fabricated 0.5. The recorder persists p0 into its own output so a restart can recover it.
5. **Two quote arms from `quote_engine.make_quotes`.** Arm `mid` = policy default (`anchor=None`). Arm `model` = anchor model_prob x 100 cents, labelled a shadow comparison arm only (the docstring forbids the model as the DEFAULT anchor; it is not the default here). Same caps for both: max_order_qty 1, fixed paper rooms of 1 contract per side, inventory 0 (fills are unknown live; this is an intent log, not a position book, disclosed).
6. **Output.** Append-only JSONL `data/cache/live_shadow/<sport>/<D>.jsonl`, one row per (tick, game, arm) including no-quote decisions with reasons; heartbeat `data/cache/live_shadow/_heartbeat.json`. Each quote row carries quote_id (day + run nonce + seq, globally unique; see AUDIT_EXEC_CHAIN finding 3), ticker, game_id, side, price cents, qty, submit_ts = t; the next tick's row for the same arm cancels it (cancel_ts).
7. **Fills afterwards (S516).** `tape_fill_sim.simulate_fills(quote_events, trades, book_snapshots, params)` (:76) accepts exactly this contract; trades come from the same books shard (`record_type=="trade"`, normalized by `tape_fill_adapters.from_s341_trade` on `created_time`), marks from `markout_causal.markout_strict` (mark strictly after fill). Receipt `docs/evidence/forward/live_shadow/<D>.json`: quotes, fills, fill rate and fee-netted markout per arm with game-cluster intervals, INSUFFICIENT under n >= 30 games (Q7). Counts and calibration only; no $ language (Q6).
8. **Process.** Stdlib + quote_engine + capture_book_adapter + mlb_live_model; no pandas, no network, no venue client, no executor import (a test asserts this). Bounded modes `--max-ticks` / `--until`. It is NOT started as a long-running process until its RSS peak is measured over a live window and recorded; then it runs under its own `capture_supervisor --name live_shadow` (one supervisor per child, `capture_supervisor.py:278-296`; STOP file `STOP_live_shadow`), launched by a committed `docs/operations/relaunch_live_shadow_<date>.ps1`, never by touching the capture supervisors.

## RAM budget on this laptop

- Measured today: captures about 400 MB total (books 126 MB, state2 64-72 MB, polymarket 208 MB, supervisors 3-5 MB each); free RAM 2,649-2,780 MB at 17:30Z; paper night bar 629 MB peak for arm E (C20 measured 244 MB), qualification stream 132 MiB.
- Shadow quoter bar: **peak RSS <= 120 MiB** (measured by psutil over a bounded live run of >= 30 min with 2+ live games), tail reads <= 4 MB per shard per tick, CPU < 5% average. It yields: at free RAM < 1,500 MB it skips the tick and records `low_ram_skip` (never a partial row).
- The shadow quoter and the paper night never overlap in a bad way: the night runs about 06:00Z after the last game; the quoter idles (300 s sleep) when no served game is inside [scheduled_start - 15 min, +5 h].

## Leak and causality rules (binding for S515/S516)

- As-of every row: `response_end_ts <= t`; state as of the book row's clock or earlier is not required, but both ages are recorded and bounded.
- p0 strictly from rows before `scheduled_start` and while status `pre`.
- No settlement, trade or future row on the recording path; the filler reads trades only after the game is final.
- Truncation invariance: re-running the recorder's decision function on the shard truncated at t gives the identical row (test).
- Append-only; never rewrite a past row; a restart continues with a new run nonce.

## Ranked rows (S515-S519)

1. **S515 LIVE SHADOW QUOTE RECORDER (MLB first).** New `scripts/platformkit/execution/live_shadow_quoter.py` (+ an io helper if needed, each <= 300 LOC) with the design above; bounded CLI; construct tests + a real-row replay test on the 2026-09-26 MLB shards (truncation invariance); a measured bounded live run on tonight's MLB games (RSS, rows). Not supervised yet.
2. **S516 SHADOW FILL RECEIPT.** Offline filler over the recorder JSONL + captured trades via `simulate_fills` and `markout_strict`; receipt per night; optional paper_night step later (improve-run-owned file, so a PROPOSED diff only).
3. **S517 SUPERVISED LAUNCH + CAPACITY RECORD.** `docs/operations/relaunch_live_shadow_*.ps1`, owner-visible record under `docs/evidence/forward/live_shadow/CAPACITY_<date>.md` from S515's measured run; start only with the recorded peak under the bar.
4. **S518 SPORT EXTENSION.** NBA (logistic pricer, p0 = venue pregame mid), WNBA (shadow_prob; RSS measured first), tennis (set-level recursion; tail-only), NFL and soccer as mid-only arms. Each needs S502 (null ESPN start/date) first for linkage beyond teams; a served schedule slot (S531).
5. **S519 reserved** for astra-found items.

## Astra critique folded in (2026-09-29, docs/evidence/harness/astra/ASTRA_LIVE_PAPER_PLAN_2026-09-29.md)

- 21 findings (15 BLOCKING for the S515/S516 design). S515-relevant items are AMENDMENT 1 of `docs/evidence/tracking/specs/S515_spec.md`: dual state clocks must agree; newline-terminated records only, no quarantine reads; a tail-window miss is its own refusal; schedules D-1/D/D+1; p0 joins a pre state observed at or before the book row, is frozen once emitted, refuses above 3,600 s of age; a pre/live/final status enum (the model sees only live); the model arm is renamed `venue_prior_state_blend` with a run-identity row; `independent_intent_zero` inventory policy; per-side quote ids (NO bid = 100 - ask) with an expiry on every intent.
- S516-relevant items (independent per-arm simulation, explicit intervals, receipt vs venue trade times with a completeness cutoff, unknown queue depth labelled, cents and whole-fill-fee unit conversion to markout_strict) are in the S516 register row.
- Correction to the table: tennis stays MID-ONLY until a valid model-input contract exists (the recursion needs games, points, server and serve probabilities; state carries sets only). Keyed linkage (game_key, ticker) already exists without S502; S502 adds date corroboration.
- Added row S519: a sealed prospective cumulative comparison of the two recorded probabilities with archived per-game paired losses (the nightly floor of 30 games never clears on 2-4 MLB games; see S503).
- Re-ranked: S515, S516, S517, S519, S518.
- Process census (astra could not enumerate processes): at 17:30Z the python processes were the three capture supervisors, their three children, hidden_launch wrappers, mcp_server and codex/pytest lanes; no quoting, sizing or paper-order process.

## Not done here

No process started. No flag flipped. No capture touched. No order code path touched.
