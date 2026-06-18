# INEFFICIENCY -- Stale / soft-book line (P3, execution edge, model-light)
_Per-pocket detection-recipe deep file. Cross-sport. The crack is SLOW UPDATE + line-shopping,
not model superiority. Grounded in the keyless odds-aggregation service (deep-dive 03) +
odds_shop value engine + prop_line_history capture. ASCII only. No $-edge claims._

## MECHANISM (why the crack exists)
A line is "stale" when a soft / slow book has NOT yet moved its number after the information
that already moved a sharp book or the consensus elsewhere. The cause is the framework
SLOW-UPDATE + LOW-ATTENTION cracks: a soft book reprices on a timer or on its own thin flow,
so for seconds-to-minutes (props: sometimes the whole pre-game window) its number lags the
true consensus. Two distinct, model-LIGHT exploits:
- LINE-SHOPPING (durable): take the BEST available number across books for the side you want.
  This is an execution edge -- you do not need to beat the close, you need a better price than
  the field offers at that instant. cut-list-no-edge CUT-6 keeps this; it is the durable
  execution edge, NOT arbitrage.
- STALE-VS-CONSENSUS (transient): when one book's two-way devigs to a fair prob materially off
  the multi-book devigged consensus, the off book is stale; the side it is generous on is the
  take. This decays in minutes; it is a SPEED game, not an intelligence game.

Note this pocket is mostly MODEL-FREE: the edge is in PRICE DISCOVERY across venues, not in
our distribution. That is why it is robust where our model edges are not -- it does not depend
on the (efficient) team/prop level being beatable.

## CONCRETE DETECTION RECIPE (exact data + query + threshold)
Data: the merged multi-venue slate already built by the aggregation service.
- Team markets: `scripts/platformkit/odds_provider/aggregate.py::aggregate(...)` ->
  `OddsEvent.prices = {venue: {home, away, draw}}` (decimal). Providers: `espn.py`
  (republished book moneylines), `kalshi.py`, `polymarket.py` (treat PM venues as a separate
  crowd -- see low-attention-niche.md, not as "stale book").
- Props: `PropLine` rows from `prop_underdog.py` / `prop_fanduel.py` (true two-way decimal) and
  `prop_prizepicks.py` (pick'em, prices None -> excluded from this two-way recipe).

Recipe A -- BEST-LINE (line-shopping), per game-side / per prop-side:
1. `best = odds_shop.best_line(book_prices)` -> for each side, the max decimal + which venue.
2. Flag a shop-gain when `best_side_decimal / median_other_venues_decimal - 1 >= TAU_SHOP`
   (start TAU_SHOP = 0.02, i.e. 2% better price than the field median). Below that the gain is
   inside vig noise.
3. Rank candidates by the price gain; the take is simply "this side at this venue."

Recipe B -- STALE-VS-CONSENSUS:
1. For each venue with a two-way, `fair_v = odds_shop.devig_twoway(price_a, price_b)` -> that
   venue's vig-free implied prob for side A.
2. Consensus = median of `fair_v` across venues EXCLUDING the venue under test (leave-one-out,
   so a stale book cannot drag its own consensus).
3. Stale flag when `|fair_v - consensus| >= TAU_STALE` AND that venue's `as_of` timestamp is
   older than the freshest venue by `>= DT_STALE`. Start TAU_STALE = 0.03 (3 prob pts),
   DT_STALE = 60s (the http_cache default TTL; tighten as capture cadence improves).
4. The take is the side the stale venue is generous on (its `fair_v` favors a side the
   consensus prices lower -> its posted price for that side is too long).

Arb (a special, rarer case): `odds_shop.detect_arb(best_a_decimal, best_b_decimal)` flags
1/a + 1/b < 1. KEEP as a free model-less flag; do NOT architect around it (CUT-6: rare,
fragile, limit-constrained -- not standing income).

## PROOF METHOD (which leak-free check + which metric)
This pocket's proof is NOT calibration-vs-close (the take IS the better-than-close number by
construction); the honest yardstick is CLV and realized capture:
- CLV (the bridge): log every flagged take at the price/time taken via
  `prop_line_history.log_board_lines(...)` (props) / a team analogue. After the line closes,
  `prop_line_history.clv_vs_close(...)` devigs the closing two-way and returns clv_pct with the
  SAME sign convention as clv_ledger (POSITIVE = we took a better number than the close).
  Stale-line and shop takes should accrue POSITIVE CLV by construction IF the stale move was
  real (the off book converges to consensus by close). Negative CLV at sample => we were
  chasing noise / the consensus itself was stale.
- Realized: settle the takes and report hit-rate + ROI at the REAL taken prices (devig, never
  flat-payout -- that is the +18.38% market-follow trap, proof-standards). Small-N ROI is noise
  (proof-standards rule 5); require a meaningful sample before trusting.
- Replication: stale flags must clear in >=2 independent capture windows; a single session of
  "off" prices is usually one slow book on one slate, not a durable venue property.

## MAGNITUDE (honest)
Order-of-magnitude, not a claim: line-shop gains live in the low single-prob-pts range
(TAU_SHOP 2% is the floor we even bother flagging); stale-vs-consensus gaps that survive
leave-one-out are typically 3-6 prob pts and decay in under a minute on liquid sides, longer on
thin props. Net realized capture is throttled hard by EXECUTION: soft-book limits, line moving
between flag and click, and account restriction on winners. The edge is real but small and
capacity-constrained -- it is an execution/ops edge, not a modeling breakthrough.

## HONEST CAVEAT / FAILURE MODES
- CAPTURE CADENCE is the binding constraint. http_cache TTL defaults to 60s; if our snapshots
  are 60s apart we cannot see a 10s stale window. Stale-vs-consensus is only as good as our
  polling rate, and faster polling risks rate-limit / IP blocks on keyless providers.
- DRACONIAN EXECUTION TAX. Soft books that price lazily ALSO limit/ban winners fastest. Capacity
  is tiny; this does not scale.
- FALSE STALENESS. A genuinely different number can reflect a real book-specific position
  (sharp money already there), not staleness. Leave-one-out consensus + the `as_of` age gate
  reduce but do not eliminate this; require the off book to CONVERGE by close (the CLV check) to
  confirm it was stale, not informed.
- NOT a model edge. This pocket does not validate our distribution; do not let a positive
  stale-line ledger be read as "our prop model has edge." Keep the ledgers separate.
- PM venues are NOT stale books. Kalshi/Polymarket divergence is a DIFFERENT-CROWD pocket
  (low-attention-niche.md), priced and proven differently; do not fold them into consensus here.

## TIER
HYPOTHESIS (execution-pocket). The aggregation + best_line + devig + arb + line-history
machinery all EXIST and are tested; what is missing is a forward CLV ledger of flagged stale/
shop takes at a meaningful sample. First milestone: stand up the capture cadence + log flags ->
measure forward CLV -> CLV-PROVEN only if positive at N. No calibration tier applies (model-light).
