# CLOSING-LINE CAPTURE + TRUE CLV -- the #1 quick win

_Part of the edge-intelligence corpus (_scrapers/). The concrete plan to actually CAPTURE
closing lines and compute true CLV -- the bridge metric from "calibrated" to "would make
money," and the single biggest measurement gap in the system. Grounded in
`scripts/platformkit/prop_line_history.py`, `clv_ledger.py`, the `odds_snapshots/` logs,
and project-deep-dive 03 + 12. ASCII only._

## Why this is the top quick win

Per proof-standards.md, FORWARD CLV (positive closing-line value accrued on paper at a
meaningful sample) is the FINAL bar before any real money -- calibration proves sharpness,
CLV proves it pays. We have the calibration machinery (the eval-gate) but almost NO CLV
data, because closing lines are barely captured:

- `prop_line_history.py` (the prop closing-line module) EXISTS and is correct, but the
  history file `data/frontend/prop_line_history.jsonl` currently holds essentially ONE
  PLACEHOLDER row (verified live: `{"match":"A vs B","player":"P","stat":"Shots",...}`).
  Real prop closing lines have NOT accrued.
- Team-side `odds_snapshots/snapshots.jsonl` exists per domain but is THIN and SINGLE-VENUE
  (NBA 18 lines, MLB 180 lines; only ESPN's one republished book). `NOW.md` blocker:
  "Live odds limited to ESPN's single republished line until a 2nd venue matches -> no real
  arb yet"; deep-dive 12 limitation 5: "TRUE prop CLV is not yet computable."

So the honest yardstick has almost no data behind it (deep-dive 03 plan item 8). The fix is
NOT new modeling -- it is RUNNING THE CAPTURE we already built, on a cadence, up to kickoff,
over a full slate. That is cheap and it is the gate to every "would this pay?" claim.

## What already exists (use it, don't rebuild)

### Prop CLV (`prop_line_history.py`)
- `log_board_lines(board)` (`:57`): appends one JSONL row per PRICED edge
  `{match, player, stat, line, over_price, under_price, source, ts}` to
  `DEFAULT_HISTORY = data/frontend/prop_line_history.jsonl` (`:38`). It is a TIME SERIES
  (no dedup) -- call it EVERY tick so the last row for a prop becomes the closing proxy.
  Pick'em rows (no real two-way price, `_priced` at `:45` requires both decimals > 1.0) are
  SKIPPED -- they cannot have CLV.
- `closing_snapshot(history_rows, match, player, stat, line, source=None)` (`:136`): the
  LAST logged price for an exact prop = the closing-line proxy (max ts).
- `clv_vs_close(taken_side, taken_price, close_over, close_under)` (`:164`): devigs the
  closing two-way via the vetted Shin solver (`odds_shop.devig_twoway`) -> fair close prob
  for the taken side; `clv_pct = (fair_close - taken_p) / taken_p * 100`, taken_p =
  1/taken_price. POSITIVE = took a BETTER number than the close. Same sign convention as
  `clv_ledger.compute_clv`.

### Team CLV (`clv_ledger.py`)
- `record_bet` (`:58`), `compute_clv(side, taken_decimal, closing_decimal_home,
  closing_decimal_away)` (`:100`) -> `{taken_p, fair_close, clv_pct, fair_close_decimal,
  beat_close}`, `settle_closing_line` (`:134`), `append_settlement` (`:161`),
  `clv_summary(ledger)` (`:190`). Same Shin-devig, same sign. (NOTE: MEMORY flags a
  historical "record_clv backwards" gotcha in the OLD betting_portfolio path -- do NOT
  re-introduce it; `clv_ledger.compute_clv`/`prop_line_history.clv_vs_close` are the
  correct, consistent implementations.)

### The loop that should drive it
`auto_loop.py` (`run_once`, deep-dive 12 sec 2.3): step 1 paper-trades today's real games
into a CLV ledger (`executed=False`); step 2 grades finished games win/loss + CLV vs close;
step 3 self-improves gated by the eval-gate. `refresh_daemon.run_forever(interval_s=60)`
keeps board snapshots fresh. The plumbing to call `log_board_lines` every tick already
runs -- it just needs to be invoked over a real slate up to kickoff.

## The plan -- what to log, at what cadence

### 1. Log every priced board line on every refresh tick, up to kickoff
Wire `refresh_daemon` (or `auto_loop` step 1) to call `prop_line_history.log_board_lines`
on the SAME `board` it already computes, every tick (the daemon default is 60s; deep-dive
12 sec 2.2). No new fetch -- reuse the board already built for the snapshot. This turns the
time series into a real per-prop trajectory whose last pre-kickoff point is the close.

### 2. Stamp and respect kickoff (leak rule)
Each source carries an event time (Underdog `games[].scheduled_at`, ESPN scoreboard event
time). Log rows are valid only while `ts < kickoff`. The CLOSE = the last row with
`ts < kickoff`. Discard / quarantine any row logged at-or-after first ball (it is a live
line, P2, not the close). Add a `kickoff` field to the logged row so closing selection is
unambiguous rather than "the last row we happened to log."

### 3. Capture the TAKEN line at bet time
When a paper bet is recorded (auto_loop step 1), persist `taken_side`, `taken_price`, and
the prop identity (match/player/stat/line/source) into the paper book. CLV is meaningless
without the price you actually took; the taken price must be frozen at decision time, never
back-filled from a later snapshot.

### 4. At settlement, compute and accrue CLV
On grade (auto_loop step 2): `closing_snapshot(...)` -> `clv_vs_close(taken_side,
taken_price, close_over, close_under)` for props (or `clv_ledger.compute_clv` for team
markets). Append the `clv_pct` + `beat_close` to the settlement row. Report rolling
`clv_summary` (mean CLV, % beat-close, N) per sport/stat -- this is the honest scoreboard.

### 5. Cadence specifics
- Pregame markets: poll every 60s from board-open to kickoff; the densest sampling near
  kickoff gives the truest close. (Lines move most in the final hour.)
- A heartbeat / freshness stamp (deep-dive 12 plan item 2) so a stale closing proxy is
  visible and not silently trusted.
- Single-venue today is acceptable for CLV-vs-OWN-close (did we beat the number we could
  take?); multi-venue (B2 keyed Odds API) sharpens the "fair close" but is not required to
  START accruing.

## How `prop_line_history` feeds the proof spine

```
board (refresh tick) --log_board_lines--> prop_line_history.jsonl  (time series, per tick)
                                                  |
paper bet (taken_side, taken_price) ----+         | closing_snapshot (last ts < kickoff)
                                        |         v
settlement --clv_vs_close(taken, close_over, close_under)--> clv_pct, beat_close
                                        |
                                        +--> paper_book settlement row --> clv_summary
                                                  |
                                                  v
                              eval-gate / _proof ledger: CALIBRATION-PROVEN -> CLV-PROVEN
```

The output advances an edge from CALIBRATION-PROVEN (OOS Brier/BSS, which the eval-gate
already does) to CLV-PROVEN (forward paper CLV>0 at meaningful N) -- the only tier that
gates real money (proof-standards.md, edge-theory.md).

## The honest DFS-pick'em caveat (binding -- do NOT fake it)

CLV-vs-close is UNDEFINED for DFS pick'em (PrizePicks standard, and any Underdog row that
falls back to `payout_type="dfs_pickem"`): there is no two-way close to devig (edge-theory.md
DFS note). `log_board_lines` CORRECTLY skips these (`_priced` returns None when a side has no
decimal > 1.0). Do not invent a synthetic two-way price to force a CLV number -- that is a
fabricated-edge violation.

For pick'em props the proof path is DIFFERENT and must be labeled as such:
- P(over) CALIBRATION vs realized outcomes (Brier/ECE on the over-probability).
- Realized ROI at the FIXED payout (e.g. 2-pick / 3-pick power/flex multipliers).
- DFS LINE MOVEMENT (did the projection itself move toward the realized result after we
  flagged it?) -- the structural-inefficiency tell, since a fixed-payout book cannot move
  the payout, only the line.
These are weaker than CLV but they are the honest substitute; the prop board already labels
every pick'em edge `edge_basis="model_view"`, never a priced EV (deep-dive 03 sec 5).

Underdog's `payout_type="sportsbook"` rows (real `decimal_price`, line_type "balanced") DO
have a two-way close -> full `clv_vs_close` applies. So the priority is to accrue CLV on the
Underdog-priced rows first; treat PrizePicks pick'em via the calibration-only path.

## Bottom line

Nothing new needs to be modeled. The capture module, the Shin devig, the CLV math, and the
loop all EXIST and are unit-tested. The one missing thing is RUNNING `log_board_lines` every
tick up to kickoff over a real slate, persisting the taken price, and computing
`clv_vs_close` at settlement -- so the honest yardstick finally has data. Until then, every
"this would have paid" statement is unsupported. This is the cheapest, highest-leverage step
toward the CLV-PROVEN tier, and it is honest about its limits: single-venue close proxy, and
pick'em props proven by calibration + fixed-payout ROI + line movement, never by CLV.
