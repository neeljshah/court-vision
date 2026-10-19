# S775 / S776 / S777 -- paper result ledger (spec, 2026-10-06)

PAPER ONLY. A paper result is a count of simulated maker fills and their settled
result in cents per contract. It is NOT a verdict, not a claim about any market,
and not evidence of anything beyond what the simulation credited on one night.
Units: counts, contracts, cents per contract. Author: paper track-record lead.

## Step 0 premise check (fresh reads, 2026-10-06 00:4xZ)

1. `scripts/platformkit/execution/fill_receipts.py` (S443 step 0, 297 lines) writes
   per fill: quote_id, game_key, event_ticker, ticker, sport, side, qty, trade_id,
   submit_ts, fill_receipt, cancel_ts, mark_30/120/300. It does NOT write the fill
   price, the fee, the fill basis or the quote life. Its `_capture` takes no S473
   `night` (no as_of window), captures only the declared ttl at multiplier 1, and its
   `main()` delegates to `fill_realism.main()` without `--as-of/--night-date`.
   So it cannot reproduce a past night's credited set or price a fill as it stands.
2. The raw fill record from `tape_fill_sim.simulate_fills` DOES carry `price`
   (integer cents on the quoted side: yes = yes bid; no = 100 - yes ask, i.e. the no
   price), `qty` (Decimal string), `fee_units` (fee increment for this fill, float,
   whole currency units, 2 dp, `venue_fees.fee_kalshi_maker`, schedule
   `venue_fees:kalshi-maker:2026-09-01:0.0175`) and `fill_basis` (through / touch_queue).
   `fill_realism_markout.accept_fee` is the landed rule for accepting fee_units as an
   exact Decimal (fee_source_float_exact / fee_source_decimal / fee_zero_increment).
3. No per-fill file exists on disk: no `docs/evidence/forward/fills/`, no
   `paper_result/`, nothing fill-shaped under data/cache/ (find over both trees).
4. `docs/evidence/forward/fill_realism/<D>.json` is COUNTS ONLY and records the exact
   night inputs (books = trades shards, state shards, schedule) plus `night.as_of`,
   `declared_ttl_s` (5) and `window_s`; quote lives run are {5, 30, declared}.
   2026-10-03 at ttl 30 x1: 23 fills credited, 7 on served tickers, 16 on not-served
   tickers (KXMLBF3 / F5TOTAL / the other GAME ticker).
5. Scoreboard `docs/evidence/forward/scoreboard/<D>.json`: `settlement` is one row per
   SERVED schedule entry: sport, game_key, status (settled / conflict / unsettled),
   outcome (0/1 for that entry's OWN ticker: y=1 only if that ticker's team won; a tie
   is 0, ingame_scoreboard_rules.ticker_outcome), close_ts, finals, ticks. The ticker
   lives in the same file's `games` list (schedule entries). Nothing settles a
   not-served ticker. 10-03: 849829 settled outcome 0, 849828 and 849835 unsettled.
   10-04: 849830 settled outcome 1, four unsettled.
6. `settlement_witness.py` (S440) is a report-only census over served identities; no
   real witness run is on disk (ledger line 2026-09-24: construct only).
7. Register: S443 LANDED 3d5de3ff9 construct only, "no real receipts yet" (ledger
   2026-09-25); S440 LANDED construct only; S444 seal provenance LANDED, no real seal;
   S445 paper account LANDED, no real receipts; S411 fill realism LANDED (counts);
   S412 microstructure licence LANDED; S422 Decimal fee chain LANDED (opt-in decimal
   fields; the night does not request them, so fee_units is the float-exact path).

## S775 -- paper result ledger CLI (build tonight)

`python -m scripts.platformkit.execution.paper_result_ledger --date D --repo-root .`

Inputs (all read-only): the night's own `fill_realism/D.json` (inputs list, night.as_of,
declared_ttl_s, window_s), the shards it names, `scoreboard/D.json`.

1. Refusals before any shard read (exit 3, nothing written, reason printed):
   `fill_realism_absent`, `fill_realism_no_night` (no as_of), `input_absent:<path>`,
   `scoreboard_absent`, `day_already_in_ledger` (a second run for a date already in
   LEDGER.jsonl writes nothing).
2. Fill export: re-run `fill_realism_io.run_files` with the report's books/trades/state,
   ttl, window, schedule and `make_night(D, as_of)`, capturing every quote life at
   multiplier 1 with the S443 monkeypatch technique (fill_realism.py and fill_receipts.py
   are not edited; fill_receipts' qty validation and row builder are reused). Each row
   = the S443 receipt fields + price_cents, fee_units (accept_fee Decimal string),
   fee_outcome, fill_basis, quote_life_s. Written to `docs/evidence/forward/fills/D.jsonl`
   (header row + one row per fill, ASCII, atomic). Reconciliation: per quote life, rows +
   refused == the report's grid["1"].fills_credited; mismatch is recorded
   (`reconciled: false`), never hidden.
3. Settlement join: fill (sport, ticker) -> scoreboard `games` entry with that ticker
   -> settlement row (sport, game_key). Counted refusals, never guessed:
   `ticker_not_served` (no scoreboard entry settles that ticker; no complement rule),
   `unsettled`, `conflict` (any status other than settled, or outcome not 0/1),
   `fee_refused:<accept_fee outcome>`.
4. Result per settled fill, exact Decimal: settle_cents = 100*outcome (yes) or
   100*(1-outcome) (no); fee_cents = fee_units*100;
   result_cents = qty*(settle_cents - price_cents) - fee_cents;
   result_cents_per_contract = result_cents / qty. Serialized as Decimal strings.
5. Day file `docs/evidence/forward/paper_result/D.json` (schema below) and one appended
   line in `docs/evidence/forward/paper_result/LEDGER.jsonl`:
   {date, fills, settled_fills, unsettled_fills, contracts, result_cents, fee_cents,
   cumulative_result_cents, day_sha256, as_of, quote_life_s}. Ledger totals use ONE
   quote life (the night's declared ttl) so lives are never summed together.

### Day file schema (for the dashboard reader)

```
{ "schema": "S775.paper_result.v1", "mode": "PAPER ONLY", "note": "paper result, not a verdict",
  "date": D, "as_of": ..., "declared_ttl_s": "5", "ledger_quote_life_s": "5",
  "fills_file": {"path", "sha256", "rows"},
  "inputs": {"fill_realism": {path, sha256}, "scoreboard": {path, sha256}},
  "reconciliation": {life: {"report_fills_credited", "rows", "refused", "reconciled"}},
  "fills": [ {quote_life_s, ticker, sport, game_key, side, price_cents, qty, fee_cents,
              fill_receipt, fill_basis, status, outcome, result_cents,
              result_cents_per_contract, refusal} ],
  "by_quote_life": {life: TOTALS}, "by_sport": {life: {sport: TOTALS}},
  "by_game": {life: {game_key_or_ticker: TOTALS}}, "by_side": {life: {yes|no: TOTALS}},
  "refusals": {life: {reason: count}} }
TOTALS = {fills, settled_fills, unsettled_fills, contracts, result_cents, fee_cents}
```
All cents are Decimal strings; counts are ints. `unsettled_fills` = every fill
without a result (any refusal reason).

Acceptance: per-file test `tests/platformkit/execution/test_s775_paper_result_ledger.py`
(result arithmetic both sides, fee subtraction, each refusal reason, ledger append +
cumulative + duplicate-date refusal, ASCII + vocabulary scan of the written files);
first real run on 2026-10-03 and 2026-10-04 (free RAM >= 3000 MB, one process, not
during live games), day files and LEDGER lines committed.

Known limits (stated, not fixed): only served tickers settle (most fills on not-served
tickers stay refused until a settlement source covers them, see S777 c); the fill set is
the simulation's, not a venue's; fee is the float-exact path (S422 decimal fields off).

## S776 -- night wiring + morning-task call (spec only, not built tonight)

Run the S775 CLI as a separate child AFTER the night's fill_realism and scoreboard
steps, without editing paper_night.py / paper_night_steps.py (LOC-pinned, see the
paper_night edit-pins note): the paper-desk tick (or the morning scheduled task)
invokes `python -m scripts.platformkit.execution.paper_result_ledger --date D
--repo-root .` once both D files exist, under the same RSS-capped child launcher and
admission (>= 2.5 GiB free) as the light steps, outside focus hours, never after
05:20Z. Exit 3 refusals are logged as a counted skip, not a failure; the day file and
LEDGER line are committed with the night's evidence. Interim (until S776 lands): the
dispatcher runs the CLI by hand after each night.

## S777 -- weekly roll-up + seal (spec only)

(a) `paper_result/weeks/<iso_week>.json`: sum of the week's day files at the ledger
quote life, by sport and side, with every day's sha256 listed; (b) sealed under the
existing prereg discipline (S444 seal provenance: the roll-up rule is committed before
the first counted week, the week file is attested by commit sha); (c) a settlement
source for not-served tickers (S440 witness over every ticker with a fill, or venue
market result receipts) so the refused `ticker_not_served` fills can be settled.

## AMENDMENT 1 (2026-10-06 01:4xZ): LF hashes, --rerun, S777(c) built

1. Every sha256 in the day file and the LEDGER `day_sha256` is computed over
   LF-normalized bytes (CRLF -> LF) via `paper_result_ledger_io.lf_sha256`, so a
   Windows checkout with core.autocrlf hashes the same as the committed bytes. The
   day file states `"sha256_rule": "LF-normalized bytes"`. Test: a day file rewritten
   with CRLF still matches its ledger line.
2. `--rerun`: replaces that date's day file and fills file and rewrites that date's
   LEDGER line in place; `cumulative_result_cents` is recomputed over the whole file in
   file order. A plain run for a date already in the ledger stays refused (exit 3).
3. S777(c) BUILT as `scripts/platformkit/execution/paper_result_settlement.py`:
   streams the night's books shards (the fill_realism inputs) and settles every
   filled ticker from the venue's own `raw_market` block on snapshot / snapshot_bulk
   rows. A ticker settles only when a record visible at as_of (record
   response_end_ts <= as_of AND raw_market.settlement_ts <= as_of) has status
   settled/finalized and result yes (outcome 1) or no (outcome 0). Counted reasons
   otherwise: unsettled_at_as_of (includes "determined"), result_missing,
   result_not_binary (e.g. scalar), status_void, conflict, ticker_not_in_archive.
   Merge: the served scoreboard settles first; the venue record settles every other
   ticker; a ticker both settle with different outcomes becomes conflict
   (scoreboard_venue_disagree), agreement is counted (scoreboard_venue_agree).
4. Schema v2 additions: per fill `settlement_source` (served_scoreboard |
   venue_archive | null); day file `venue_settlement` {ticker: {status, outcome,
   reason, settlement_ts, record_ts}}, `scoreboard_venue` {agree/disagree counts},
   `settlement_sources` {life: {served_scoreboard, venue_archive}} over settled
   fills, `sha256_rule`; `schema` = "S775.paper_result.v2". A fill refused by the venue
   rule carries that reason as its `refusal`.

## AMENDMENT 2 (2026-10-06 01:4xZ): read-only tier corrections (ACCEPT WITH CORRECTIONS)

1. A settled fill whose fill_receipt is at or after the settlement close_ts is
   refused `fill_after_close` (scoreboard close_ts; venue raw_market.close_time,
   falling back to settlement_ts). Index tuples are now
   (game_key, status, outcome, source, close_ts).
2. Every JSON input (fill_realism report, schedule, scoreboard) is parsed and checked
   in load_night before anything is written; a 0-byte / corrupt / non-ASCII file
   refuses `fill_realism_unreadable` / `schedule_unreadable` / `scoreboard_unreadable`
   (exit 3, no fills file, no day file, no ledger line).
3. TOTALS `result_cents` and `fee_cents` are null (not "0") when settled_fills == 0.
4. The fills-file header and every LEDGER line carry `"mode": "PAPER ONLY"` and
   `"note": "paper result, not a verdict"`.
5. The LEDGER line is the declared quote life only (5 s on every night so far);
   other lives appear only inside the day file. Every cents / contracts string has
   two places ("-63.00"); per-contract figures are rounded half-even to 0.01.
6. A non-settled status that is missing or blank refuses `status_missing`.
7. `.gitattributes`: `docs/evidence/forward/paper_result/**` and
   `docs/evidence/forward/fills/**` are `text eol=lf` (in addition to the LF-normalized
   hash).
