GAP S342 | sport all (maker channel) | worktree a1 | log cx_s342_quote_engine
# Maker quote engine: replace the fair-value echo in paper_maker.quote()

SINGLE PROBLEM: scripts/platformkit/execution/paper_maker.py posts AT fair value, qty 1, no spread, no
inventory term, no state-change pull (audit 04 capability #3 MISSING). A maker quoting at fair is zero gross by
construction and negative after the venue fee.

BINDING BEFORE-CONDITION (re-run, quote the output): `grep -n "_QTY = 1\|_ASSUMED_HALF_SPREAD_CENTS = 1" scripts/platformkit/execution/paper_maker.py`
returns both lines, and `ls scripts/platformkit/execution/quote_engine.py` fails.

CHANGE (NEW files only; paper_maker.py is NOT edited in this row):
1. scripts/platformkit/execution/quote_engine.py (<= 300 LOC, stdlib, ASCII, no network, no writes):
   `make_quotes(anchor, anchor_sd, book, inventory, state, caps, venue="kalshi") -> {"bid_cents","ask_cents","qty","reason"} | {"pulled": reason}`
   - ANCHOR (astra round 10): the caller passes the anchor; the documented default is the CONTEMPORANEOUS OBSERVED MID
     (the market is the model on every measured corpus), never a standalone model fair value.
   - half-spread (cents) = ceil(maker fee per contract at the quote price, from venue_fees.fee_kalshi_maker)
     + adverse-selection term (input parameter, cents; default from thresholds.py, NEVER fitted in this row)
     + uncertainty term k_sd * anchor_sd; floor 1 tick.
   - inventory skew: both quotes shift by -k_inv * inventory cents (long -> lower bid and ask); hard stop quoting
     the side that would breach caps["max_position"].
   - MAKER-ONLY: bid <= best_ask - 1 tick and ask >= best_bid + 1 tick; a quote that would cross is repriced
     to the passive side or dropped, never sent through.
   - PULL (return {"pulled": ...}) on: state change within state["pull_window_s"], stale book (reuse
     ingame.quote_freshness), suspended/terminal market (reuse paper_maker._market_suspended semantics),
     seconds_to_close below caps["flatten_deadline_s"] (then only inventory-REDUCING quotes allowed).
   - qty from caps["max_order_qty"] and remaining position room; fee computed per whole order.
2. tests/platformkit/execution/test_quote_engine.py: one test per rule above + property checks
   (bid < ask always; never crosses the observed touch; skew sign; pulled on each trigger; qty never exceeds room).
3. An `_demo()` assert self-check in the module.

CONTROLS: no parameter is fitted to any outcome or tape in this row (PREPARE only -- no scoring, no markout numbers;
a scored replay is the successor row and needs a sealed prereg first, contract Q1). Every default constant cites its
source line. No change to thresholds.py values (Q3).

ACCEPTANCE: the two test files pass per-file (`python -m pytest tests/platformkit/execution/test_quote_engine.py -q`);
`python -m scripts.platformkit.execution.quote_engine` prints the self-check line; diff touches NEW files only.

OUT OF SCOPE: wiring into paper_maker, live order path, any flag, any data/ write, any measured number.
Vocabulary follows contract Q6; automated scan required. Memo ends with a NOT VERIFIED list.
NOTE FOR THE BUILDER: the pod is OFF -- ignore every pod_run instruction in the standard prompt; nothing here needs
more than ~200 MB. HONEST LIMIT to record in the memo: no per-trade price tape exists in any archive
(book_replay.py docstring), so queue position and true fill rates stay unmodeled until capture records trades.
ASTRA ROUND 10 BINDINGS: round prices OUTWARD to the tick grid; adverse-selection input is per side; do not raise qty to dilute fee
rounding; caps are per-order, per-game, correlated-contract (same game_id) and global, enforced OUTSIDE model output; after the
flatten deadline the engine is reduce-only and unresolved inventory stays visible in the return value (maker-only cannot
guarantee a flatten); every abstention carries an explicit reason code.
