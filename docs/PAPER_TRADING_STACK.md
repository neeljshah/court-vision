# Paper execution: end to end -- CourtVision

> How a model probability becomes a paper ledger row, gets a realistic simulated
> fill, receives a true closing line, settles against the realized final score,
> and is graded -- with a fail-closed gate deciding what any of it is allowed to mean.
> For the model layer feeding this stack see [`docs/ML_MODELS.md`](ML_MODELS.md);
> for the ingest feeds it consumes see [`docs/INGEST_PIPELINES.md`](INGEST_PIPELINES.md).

**The contract, stated up front:** paper trading here is calibration and execution
research, in UNITS. Every ledger row is stamped `executed: false` and
`edge_claimed: false`. There is no dollar, ROI, or PnL field anywhere in the
schema -- the honesty rails are structural, not a convention. A positive units
figure is never surfaced without its channel's fail-closed greenlight verdict
(RED / AMBER / GREEN) alongside it. Real-money execution is a separate,
default-DENY gate this stack has no path to.

---

## The flow

```
  model snapshot (predict_service store)
        |
        v
  PLACEMENT          pm_trading/pm_game_placer.py      idempotent bet_id rows
        |
        v
  FILL SIMULATION    pm_trading/fill_sim.py            VWAP walk vs captured depth
        |
        v
  CLOSE CAPTURE      pm_trading/pm_close_capture.py    governed, bounded, confirmed-only
        |
        v
  SETTLEMENT         ingame/ingame_paper_settle.py     finals watermark + STUCK detector
        |
        v
  GRADING / CLV      paper/grade_predictions.py        true_close > proxy > no_close
        |
        v
  GREENLIGHT GATE    econ/edge_greenlight.py           7 criteria, RED/AMBER/GREEN
        |
        v
  ASKABLE ANALYTICS  intel_query/paper_analytics.py    every answer carries the gate
```

Everything appends to one canonical ledger: `data/frontend/clv_ledger.jsonl`
(append-only JSONL, streamed line-by-line by every reader, never whole-file loaded).

---

## 1. Placement -- `scripts/platformkit/pm_trading/pm_game_placer.py`

Prices live Kalshi (and Polymarket) game moneyline markets with the calibrated
model and paper-places the +EV side(s). Defaults: `DEFAULT_PM_GAME_SPORTS =
("mlb", "soccer_intl")`.

- **Matching, never guessing.** Kalshi city sides ("Toronto") bridge to model
  full names ("Toronto Blue Jays") via `_name_matches()`; national teams match
  only on the same canonical country code ("South Korea" == "Korea Republic",
  but Congo != DR Congo). No model match, or an un-modelable outright -> no bet.
- **Devig.** `market_prob` = the exchange YES price normalized against the other
  side (3-way soccer folds the draw into the field). `model_prob` = our
  calibrated pregame `home_ml`/`away_ml`. `ev = model_prob / market_prob - 1`.
- **Plausibility band (stale-quote guard).** `market_prob` outside `[0.05, 0.95]`
  or `ev > 1.0` (a ">100% edge") is a stale/thin quote or a model error, never a
  real liquid edge -- skipped, fail closed.
- **Idempotent.** `bet_id = "pm|<venue>|<game_id>|<side>"`; a bet_id already in
  the ledger is never re-written, so the placer can run on any cadence safely.

The ledger row (via `_ledger_row`) carries, among others:

```jsonc
{
  "bet_id": "pm|kalshi|KXMLBGAME-26JUL07...|home",
  "ts": "...", "sport": "mlb", "side": "home", "market_type": "moneyline",
  "taken_book": "kalshi", "taken_decimal": 2.08,
  "model_prob": 0.51, "market_prob": 0.48, "ev": 0.0625, "tier": "B",
  "stake_units": 1.0, "quarter_kelly": 0.31,       // UNITS, never dollars
  "status": "open", "channel": "paper_pm", "is_pm": true,
  "event_id": "KXMLBGAME-26JUL07...",              // Kalshi event ticker (close resolution)
  "clv_is_proxy": true, "clv_status": "INSUFFICIENT_DATA",
  "executed": false, "edge_claimed": false,
  // additive fill-simulation stamp (section 2):
  "fill_prob": 0.487, "n_filled": 100.0, "slippage_prob": 0.004,
  "book_age_sec": 41.2, "fill_quality": "book"
}
```

## 2. Realistic fill simulation -- `scripts/platformkit/pm_trading/fill_sim.py`

A paper bet recorded at the snapshot mid pretends execution is free. This module
prices it against **captured Kalshi order-book depth** instead
(`data/cache/depth_history/<sport>/<date>.jsonl`, full price ladders, ~20 min
per ticker measured cadence -- see [`INGEST_PIPELINES.md`](INGEST_PIPELINES.md)).

- `fill_price(side, stake_contracts, book_snapshot)` VWAP-walks the **opposite
  side's bid ladder** best-price-first (a resting NO bid at `p` fills a YES buy
  at `1-p`). Depth short of the order -> honest **partial fill** (`n_filled` <
  requested). One paper unit maps to `CONTRACTS_PER_UNIT = 100` contracts.
- **Fail closed on staleness.** A book older than `FILL_MAX_AGE_SEC = 120` s
  (or missing/empty/one-sided) returns `None` -- never a fabricated fill. The
  placement-path wrapper uses `LOOKUP_MAX_AGE_SEC = 1500` s, matched to the
  capture cadence, so a live bet is not spuriously stamped unfillable.
- **`no_book` honesty stamping.** `stamp_fill()` always returns the five
  additive fields `{fill_prob, n_filled, slippage_prob, book_age_sec,
  fill_quality}`. No usable book -> `fill_quality: "no_book"`; the bet is still
  written at its snapshot price but an unsimulated mid-fill is never dressed up
  as a book-fill. Existing ledger fields are untouched -- the stamp is additive.
- `event_side_tickers(event_ticker)` resolves a Kalshi game event to its
  per-side market tickers: markets are `<event>-<TEAMCODE>` and the event
  ticker ends with the HOME team code (verified against line_history home/away,
  2026-07-07), so the suffix the event ends with is the home side.

## 3. Close capture -- `pm_close_capture.py` + `pm_close_capture_runner.py`

Settled `paper_pm` rows are worthless for CLV until a **true closing price** is
attached. The M18 daemon sweeps every 900 s:

- Targets: `channel == "paper_pm"`, `status == "settled"`, has an `event_id`,
  no confirmed close yet. Idempotent -- a row already carrying a real
  (`clv_is_proxy: false`) close is skipped.
- **Only confirmed closes are written.** A still-open or inferred market is
  counted (`n_proxy`) and never stamped -- no fabricated closes, ever. A
  confirmed close gets `clv_status: "true_close"`, `close_source: "kalshi"`.
- **Governed and bounded.** The sweep registers a 0.15 share of the shared
  cross-process Kalshi rate budget (`odds_provider/kalshi_rate_governor.py`,
  `BASE_RPS = 15`) and caps itself at `CV_PM_CLOSE_MAX_ROWS = 40` rows/tick, so
  a 429-throttled sweep can never outlast the supervisor's heartbeat-freshness
  bar. Deferred rows resume on the next tick. (Before the share was registered,
  the unknown-caller default over-subscribed the ceiling on full slates --
  a 429 storm and a flapping heartbeat. The fix is a budget, not a retry.)
- **Memoized per-sweep, not just budgeted.** A second root cause behind the
  same m18 flap: the default resolver path built a fresh `KalshiProvider` and
  refetched the full market list for every target row -- a 40-row sweep meant
  40 identical fetches of the same 1-3 sports, self-inflicting 429s and
  stretching sweeps past the heartbeat threshold on its own. `pm_close_capture.py`
  now memoizes one governed fetch per sport per sweep (`_memoized_kalshi_fetch`,
  2026-07-15); the provider and governor caller are unchanged, only the
  redundant calls are gone.

## 4. Settlement -- `scripts/platformkit/ingame/ingame_paper_settle.py`

Settles OPEN `paper_ingame` bets against realized final scores. In-game rows are
keyed by the **Kalshi ticker**, not an ESPN id, so settlement dispatches on the
ticker's series prefix: `KXMLBGAME` -> MLB resolver, `KXWCGAME` -> soccer,
`KXATPMATCH`/`KXWTAMATCH` -> tennis, `KXWNBAGAME`/`KXNPBGAME`/`KXKBOGAME`
likewise. All resolvers read local parquet -- no network in the settle path.

Fail-closed design, three layers deep:

- **Ambiguity never settles.** `ingame_outcome_label.parse_mlb_ticker` splits
  the ticker's `AWAYHOME` team-code concatenation at the one position where both
  halves are valid abbreviations -- ambiguous split -> `None`, never a guess.
  **Doubleheaders:** a `G<n>` suffix picks the Nth game by start time; a
  doubleheader date with no game number is ambiguous and stays open. The
  date join tolerates +1 day only -- a box row dated *before* the ticker date is
  a different game (the guard added after a 07-08 bet nearly settled against
  07-07's just-finished game 1).
- **The finals watermark lesson** (`scripts/platformkit/autonomy/label_finals_refresh.py`).
  The finals ingests persist only games already FINAL at fetch time. A pure
  watermark ("re-fetch from max existing date + 1") therefore has a trap: the
  first final of day D advances the watermark to D and locks out the rest of
  D's games forever. Observed: exactly 1 of ~14 MLB games/day landed over four
  days -- 129 in-game paper bets unsettleable. The fix is
  `refetch_days = 3`: the trailing window is *always* re-fetched even when
  present (every wired ingest dedupes on game id, so this is idempotent).
  Refreshes are bounded (`max_dates_per_tick = 10`, bootstrap window 3 days,
  never an unbounded pull) and isolated per sport -- one failing fetch never
  blocks a sibling.
- **The STUCK detector.** `write_status()` counts consecutive ticks that had
  open bets but zero settles; at `INGAME_SETTLE_STUCK_TICKS = 24` (about 6 h at
  the 900 s cadence) the status file flips to `STUCK` so ops monitoring alerts.
  The incident that motivated it -- 63+ silent zero-settle ticks -- is now a
  visible state, not a log line nobody reads.

A game that is not yet final, or a ticker no resolver recognizes, simply stays
open. Nothing is ever force-settled.

## 5. Grading and CLV -- `scripts/platformkit/paper/grade_predictions.py`

Settled rows get an outcome (`win`/`loss`/`push`), a `unit_result` in flat
units, and a CLV stamp with explicit provenance: `true_close` (a quote captured
within the 30-minute lock window before tipoff in our own
`line_history`) beats `proxy` (a same-cycle snapshot) beats `no_close` (nothing
tradeable captured -- reported as such, never backfilled).
`paper/bankroll_daemon.py` folds settled rows into a flat-one-unit equity
series every 600 s, with a small-n floor: the CLV mean prints
`INSUFFICIENT_DATA` below the minimum sample rather than an unstable number.

**The honest nuance -- same-venue vs cross-venue basis.** A CLV number where the
taken venue differs from the close venue is a *basis measurement, not edge*. An
audit of the `paper_pm` channel found rows taken at Kalshi prices but scored
against a sportsbook's lock-window close: longshots showed strongly positive
"CLV" while the realized record ran *below* close-implied -- the signature of
adverse selection, not skill. The fix (forward-only, historical rows never
rewritten) is same-venue close capture (section 3) plus a `close_source` label
on every stamp. The discipline generalizes: positive mean CLV + record below
close-implied + CLV fattest on losers = basis, and the greenlight gate's
criterion (e) explicitly fails a channel whose same-venue CLV confidence
interval straddles zero.

## 6. The greenlight gate -- `scripts/platformkit/econ/edge_greenlight.py`

The gate is the product's answer to "when would a units number ever mean
anything?" -- seven pre-registered criteria per channel, evaluated nightly,
written to `data/frontend/ops/edge_greenlight.json`. It is a READ-ONLY report:
a GREEN verdict pages a human; it places no order and flips no flag.

| # | Criterion (all seven required for GREEN) |
|---|---|
| a | n >= 300 settled bets in the channel, >= 150 in each date-parity half |
| b | net units > 0 in BOTH independent halves |
| c | mean CLV vs true contemporaneous closes > the fee hurdle, 95% CI excluding 0, both halves |
| d | after-cost units > 0 in both halves |
| e | bet segments TRUSTED and the channel-trust gate GREEN (same-venue CLV CI must clear zero) |
| f | eval-gate green (no leak flag) and the cv-honesty-gate adjudicates NOT-REFUTED |
| g | excess win rate over close-implied, CI excluding 0 |

The halves are even/odd day-of-month -- a deterministic, leak-free split with no
hand-chosen fold boundary. Status logic: all pass -> GREEN; zero settled volume,
or actively net-negative on both the raw and after-cost record -> RED; real
volume blocked by specific named criteria -> AMBER. Criteria (e) and (f) are
fail-closed by construction: any missing, stale, or unreadable input reports
RED, never a bare pass. As of this writing every channel is RED or AMBER -- the
gate reporting honestly that no edge has been proven is the feature.

## 7. Worked example of fail-closed design: the cross-venue arb lane

`pm_trading/cross_venue_arb.py` (+ `run_cross_venue_arb.py`) scans for two-way
locks across venues: buying side X on venue A and the opposite side on venue B
locks a sure result iff `(1/dec_A + 1/dec_B) < 1` **after** each venue's
round-trip fee (`econ/cost_model.breakeven_edge_prob`) is subtracted.
Thresholds: quotes older than 120 s are skipped; locks under 0.3 pp after fees
are noise and dropped.

The instructive part is what it refuses to do:

- **The soccer draw guard.** `DEFAULT_SPORTS = ("mlb", "wnba")` -- soccer is
  deliberately excluded. Its moneyline is inherently three-way, and the cached
  feed does not reliably carry a draw row for every book; treating those books'
  home/away as a clean two-way market would silently invent fake locked profit
  (the draw probability the two-way math never subtracts is real weight, not
  free money). A "no draw key present" check cannot detect a draw missing from
  the *source* data, so the sport is fenced out at the default rather than
  patched over. Within eligible sports, any book whose snapshot includes a
  draw/tie side is likewise dropped from that game's pairing.
- **Fees are subtracted, not asserted.** Kalshi taker fee per contract is
  `ceil_to_cent(0.07 * P * (1-P))` (maker 0.25x that; maximum 1.75 cents at
  P=0.50); Polymarket sports-category taker is 0.75% of notional. A quoted
  sportsbook price carries its vig in the price itself -- fee 0 by construction.
- **Both legs, idempotent, self-healing.** Each detected lock writes two rows
  (`market_type: "arb"`, `bet_id = "arb|<sport>|<matchup>|<venue>|<side>"`),
  deduped per leg so a crash between the two appends heals on the next tick.
  Kalshi legs resolve their market ticker via the depth sidecar's
  event-ticker/home-suffix rule and get the same fill-simulation stamp as any
  directional bet; non-Kalshi legs stamp `no_book` honestly.

## 8. Askable analytics -- `scripts/platformkit/intel_query/paper_analytics.py`

```
python -m scripts.platformkit.intel_query.paper_analytics "this week by channel"
python -m scripts.platformkit.intel_query.paper_analytics "arb lane"
python -m scripts.platformkit.intel_query.paper_analytics "settlement backlog"
```

Answers `summary` (windowed, groupable by channel/venue/sport/market_type),
`today`, `this week`, the arb lane, and the open-bet age backlog. Three
properties are binding:

- **Streams, never loads.** The ledger is read line-by-line; one malformed line
  is skipped, not fatal.
- **Every answer carries its sources** (`source_files`) **and
  `edge_claimed: false`.**
- **No units number without its gate.** Channel-grouped answers attach each
  channel's greenlight status; a channel the gate has no verdict for reports
  `"unknown"` -- the fail-closed default is never GREEN-by-silence.

---

*Related: [`docs/INGEST_PIPELINES.md`](INGEST_PIPELINES.md) -
[`docs/BETTING.md`](BETTING.md) - [`docs/EXECUTION_GUIDE.md`](EXECUTION_GUIDE.md) -
[`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md)*

*Last verified: 2026-07-15*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
