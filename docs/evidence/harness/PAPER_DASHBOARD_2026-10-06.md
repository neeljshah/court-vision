# PAPER DASHBOARD (2026-10-06) -- schema, meaning, and what is not shown

PAPER DESK -- paper only, simulated maker quotes on the recorded Kalshi tape; not a verdict.

One local page for the owner: the paper quotes, the served games, the paper result in venue units,
and the desk status. It reads receipts already on disk; it never re-simulates, never writes under
`docs/evidence/forward/`, and never starts or stops anything.

## Run

    python -m scripts.platformkit.ops.paper_dashboard --repo-root . --out data/cache/paper_desk/dashboard.html

Writes `dashboard.html` and `dashboard.json` (same directory, gitignored, local-only). Exit code is
always 0; anything missing or unreadable is counted under `unknowns` inside the json. The desk
watchdog (`.planning/codex_push_2026-10-02/watchdog.sh`, local-only) re-runs it every 5 minutes outside
the night quiet hours (05:30Z-08:45Z), never while a paper night runs and never while a served game is
inside its first-hour focus window. The page itself carries a 5-minute meta refresh.

Files: `scripts/platformkit/ops/paper_dashboard.py` (CLI), `paper_dashboard_data.py` (collector, receipts
to one plain dict), `paper_dashboard_html.py` (dict to a self-contained HTML string; pure, no data shaping).

## Units

- 1 unit = 1 contract. Kalshi prices are 1-99 cents per contract.
- Markouts in the fill-realism receipt are in probability points per contract (`units: probability_points`),
  fee-netted on entry (`markout_causal`: yes scores mid - price - fee). The page shows them x 100 as
  cents per contract.
- "paper result (contracts x cents, after the maker fee schedule in the receipt)" = sum over scored
  fills of (1 contract x markout at the 120 s horizon in cents). Only fills that have a qualifying mark
  at 120 s are scored; the count behind it is printed next to it. It is a markout, not a settled result.

## Dict schema (`dashboard.json`)

| key | meaning | source |
|---|---|---|
| `generated_at_utc`, `generated_at_local` | build time, UTC and America/Chicago | clock |
| `header` | the paper-only line above | constant |
| `health.captures.{books,state2,polymarket}` | `age_s` since the capture supervisor heartbeat file was written; `level` green < 60 s, amber < 300 s, red otherwise or missing | `data/cache/capture_supervisor/supervisor_<n>.heartbeat.json` (mtime) |
| `health.tick` | last desk tick `decision`, `reason`, `ts`, `age_s` | `data/cache/paper_desk/status.json` key `tick` |
| `health.free_ram_mb` | `tick.free_ram_after` / 2^20 at the last tick | same |
| `games.today_utc`, `games.tomorrow_utc` | UTC day boundaries used | clock |
| `games.rows[]` | one per served game starting today or tomorrow (UTC): `sport`, `matchup` (parsed from the ticker), `ticker`, `game_id`, `start_utc`, `start_local`, `local_day`, `status` (scheduled / in focus window = start-2 min to start+60 min / done), `last_book_row_s`, `book_rows_5min` (counted only inside the last 200 KB of the day's books shard, so a floor not a total), `night` (per-game fills and 120 s markout from that schedule day's fill-realism receipt, or `"night pending"`) | `docs/evidence/forward/schedules/<D>_maker_forward.json`, `data/cache/ingame_books_local/kalshi/<sport>/<D>.jsonl` (tail), `fill_realism/<D>.json` |
| `games.missing_schedules` | UTC days with no schedule file yet (the next day's file is written about 14:00Z the day before) | schedules dir |
| `bets.to_date`, `bets.last_7` | over nightly fill-realism receipts (`fill_realism/<YYYY-MM-DD>.json` only; the 09-22 `_after2`/`_ttl5` variants are excluded, as the cumulative roll-up does). `last_7` = the 7 calendar days ending on the newest receipt date. Fields: `nights`, `quotes_placed` (TTL 30, grid 1), `fills_ttl30`, `fills_ttl5` (receipt headline = min over size grids, the number the cumulative roll-up sums), `grid1_fills_ttl30`, `by_side`, `by_fill_basis`, `quote_life_expiry`, `markout[h]` = {`n`, `mean_cents`} for h in 30/120/300 s, `paper_result_120` = {`value`, `n_scored`} | `fill_realism/<D>.json` `quote_life[ttl].grid["1"]` |
| `bets.grid_table[]` | per TTL x size grid (1/2/4/8 contracts): quotes placed and fills credited, to date | same |
| `bets.realized_note` | realized per-fill paper result status | see below |
| `status` | `served`/`qualified`/`settled` per sport to date, `nights` (count, complete, partial, days without receipt), `floor_games`, `open_floors`, `coming` (sports and since-date from the desk config), `facts` (one-liners, every number read from a receipt) | `cumulative/<latest>.json` `to_date`, `last_7`, `floor_games`, `open_floors`; `docs/operations/paper_desk_config.json`; `qualification/<D>.json` (best coverage = max covered_ms/total_ms over games) |
| `nights[]` | one row per night since 2026-09-22: `date`, `served` (schedule rows), `status` (night receipt; `absent` when there is none), `fills_ttl30`, `fills_ttl5`, `markout_120_cents`, `latency_p50_s` (cumulative per_night latency, first non-null), `coverage_refusals` (sum) | schedules, `nights/<D>.json`, `fill_realism/<D>.json`, cumulative `per_night` |
| `ledger.cumulative` | v2: last line of the S775 ledger (`cumulative_result_cents` at the declared quote life, cents per contract) plus fills / settled / unsettled summed over its lines; `null` and `unknowns.ledger_missing` when absent | `paper_result/LEDGER.jsonl` (schema `docs/evidence/harness/S775_PAPER_RESULT_LEDGER_SPEC_2026-10-06.md`) |
| `ledger.nights[]` | v2: per night and quote life (30 / 5 s): fills, settled, result_cents, unsettled + reasons, settlement source split | `paper_result/<D>.json` `by_quote_life`, `refusals`, `settlement_sources` |
| `ledger.latest_fills` | v2: per-fill rows (ticker, side, price, contracts, fee, outcome, result or refusal, source, life) of the newest night with fills, capped at 50 | `paper_result/<D>.json` `fills` |
| `unknowns` | counter of receipts that were missing, 0 bytes or unreadable, by kind | collector |
| `sources` | every receipt path read | collector |

## Missing-data policy

Every missing, 0-byte or unreadable receipt is counted in `unknowns` and shown as `unknown` / `-` on
the page, never as a measured zero. A 0 is printed only when a receipt on disk says 0 (for example a
night whose receipt credits no fills shows `0 (no fills credited)`).

## What is NOT shown, and why

- (v1 note, superseded by the v2 ledger card when LEDGER.jsonl exists) Realized per-fill paper result: the fill-realism receipt is COUNTS ONLY and
  `docs/evidence/forward/markouts/` is empty; `exec_quality/` holds tape markouts (every print a
  hypothetical fill), not desk fills. A realized result needs the per-fill receipt export
  (`scripts/platformkit/execution/fill_receipts.py`, opt-in) run per night; it has not been run. The page
  says so in one line and shows the markout-based paper result instead.
- Per-game quotes placed: the receipt counts quotes per night, not per game. Per-game fills come from
  the per-market markout blocks (markets whose ticker starts with the game id).
- The floor of 20 settled games after a new seal: no sealed file on disk carries it yet; the page shows
  the sealed floor from the cumulative roll-up (`floor_games`).
- Cell verdicts beyond INSUFFICIENT and any pooled contrast numbers: they are development reads, not
  verdicts, and do not belong on an at-a-glance page.
