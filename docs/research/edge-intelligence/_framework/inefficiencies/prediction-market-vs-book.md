# INEFFICIENCY: PREDICTION-MARKET vs SPORTSBOOK DIVERGENCE (P4) -- detection recipe + proof

_Part of the edge-intelligence corpus (_framework/inefficiencies/). The DEEP, actionable layer
for ONE pocket: Kalshi / Polymarket (a different crowd) diverging from the devigged sportsbook
consensus. Grounds: edge-theory.md (P4), proof-standards.md, cut-list-no-edge.md (CUT 1/6),
_scrapers/data-acquisition.md (B1/B3/B4), and the live code
`scripts/platformkit/odds_provider/{kalshi.py,polymarket.py,espn.py,aggregate.py}` +
`odds_shop.py`. Binding: no $-edge claimed; ASCII only; a null here is a SUCCESS._

---

## 1. THE EXACT MECHANISM (and why it is the WEAKEST P-tier here)

A sportsbook close and a prediction-market price are set by DIFFERENT crowds with different
incentives, liquidity, and fee structures. When they disagree on the same team-winner outcome,
ONE of them is closer to the true probability. The candidate edge: if the sportsbook consensus is
the sharper of the two (usually true for liquid major-sport mainlines), a divergent
prediction-market price is takeable on the exchange at a better number -- and vice versa for a
genuinely sharp exchange.

WHY IT IS WEAK / mostly a NON-edge (the honest core):
- A prediction market is NOT a sportsbook. The Kalshi YES ask carries its OWN vig/skew and
  liquidity is low, spreads wide (data-acquisition.md B3). A "divergence" may just be the exchange
  spread, not a real probability gap.
- A surfaced "best price" on Kalshi/Polymarket may not be BETTABLE AT SIZE -- mixing it into
  `best_line` can show a price you cannot actually take (data-acquisition.md B3, deep-dive 03).
- Orientation depends ENTIRELY on name-matching; a label the resolver doesn't know can FLIP a
  side and fabricate a phantom divergence (B3/B4).
- The sportsbook side itself is a SINGLE republished book (ESPN's `pickcenter`, B1) -- a mainline
  that is already efficient (CUT 1). So the "fair" sportsbook number is itself a one-venue proxy.
This is P4, ranked below P1/P2/P3 deliberately. Treat divergence as a LABELED SIGNAL to
investigate, never as a bettable book line.

---

## 2. IN-DATA DETECTION RECIPE (exactly what to compute)

Everything needed is already aggregated into a single multi-venue surface; the detection is a
per-event cross-venue comparison of DEVIGGED probabilities.

### 2.1 Build the multi-venue surface (built)
- `aggregate(sport, providers)` with the standard stack ESPN + Kalshi + Polymarket
  (`aggregate.py:147-152`) merges venues per event, flipping sides when orientation differs
  (`_merge`/`_fold`, `:112`), into `{venue: {"home": dec, "away": dec[, "draw": dec]}}`
  (`to_odds_lookup`, `:193`). Venues present: ESPN's republished book, `"kalshi"`, `"polymarket"`.
- Kalshi emit: YES ask -> implied prob -> decimal `1/prob` (`kalshi.py:15`, `_yes_ask_prob` reads
  `yes_ask_dollars`/`last_price_dollars`/`yes_bid_dollars` `:55-60`; only events with EXACTLY two
  team markets each with a usable YES ask are surfaced, `:102-113`, venue label `"kalshi"`).
- Polymarket emit: two-outcome market, `outcomePrices` JSON-string -> outcome[0]->home,
  [1]->away (`polymarket.py:65`), venue `"polymarket"`.

### 2.2 Devig each venue to a fair probability, then diff
- For EACH venue's two-way `{home_dec, away_dec}`, compute the fair two-way with the vetted Shin
  solver `odds_shop.devig_twoway(home_dec, away_dec)` -> `(fair_home, fair_away)`. This strips the
  book vig AND the exchange spread to a comparable probability.
  - NOTE on prediction markets: Kalshi's `home`/`away` decimals are BOTH `1/yes_ask` of two
    SEPARATE YES markets, so they generally do NOT sum to <1 the way a vigged book does -- their
    "overround" is the bid/ask + fee structure. Devig still normalizes them to a comparable fair
    pair; document that the exchange "fair" is noisier than a book devig.
- DETECTION STATISTIC per event:
  `divergence = fair_home(prediction_market) - fair_home(sportsbook_devigged)`.
  Rank events by `|divergence|`. A large, repeatable divergence on a LIQUID prediction-market
  contract is the candidate. Require BOTH venues present for the event (no divergence without two
  sides).
- GUARD (mandatory, the phantom-divergence filter): confirm the orientation matched correctly --
  `teams_match(ev.home, home, sport)` (`aggregate.py:210`, the deliberately STRICT, false-negative-
  biased matcher). A divergence riding on a name flip is fabricated; drop any event where the
  resolver is uncertain (better no-signal than a wrong-side signal).
- LIQUIDITY GUARD: tag the prediction-market side with its venue and a liquidity proxy (Kalshi
  bid/ask width; Polymarket volume). A divergence on a thin contract is the exchange spread, not a
  probability gap -- demote it. Keep prediction markets SEPARATELY LABELED (data-acquisition.md B3
  plan item 3: tag venue type), NEVER folded into a "best_line" treated as bettable.

### 2.3 Which side is sharp? (the direction question)
The divergence alone does not say who is right. Two honest reads:
- DEFAULT prior: the liquid sportsbook consensus is sharper than a thin exchange -> a divergent
  exchange price is the candidate to TAKE (if takeable at size). This is the usual case for major
  sports.
- INVERSE case: in a market with genuinely deep exchange liquidity and thin book attention (niche
  / political-style sports timing), the exchange may lead. Only assert this with measured evidence
  (section 3), never by assumption.
Our OWN model is a THIRD opinion: cross-check `divergence` against our pregame
`predict()` win-prob. The strongest candidate is one where OUR model AND the sportsbook both
disagree with the exchange in the SAME direction (two independent sharp views vs the exchange).

---

## 3. PROOF METHOD (leak-free, which metric, and CLV)

The proof is: does the DIVERGENCE SIGNAL predict which side is right, out-of-sample, and does
acting on it accrue positive CLV?

- LEAK-FREE construction: snapshot both venues with timestamps `< kickoff` (espn scoreboard event
  time / Kalshi market close / Polymarket commence); the divergence is computed only from
  pre-event prices. Discard any post-kickoff (live) price -- that is the P2 feed, not this signal.
- CALIBRATION metric: for the side the divergence FAVORS (the one the sharper venue prices higher),
  score Brier / log-loss vs realized outcomes, and compute Brier-Skill-Score vs the
  sportsbook-devigged close. BSS>0 = the divergence-adjusted view is sharper than the book close
  alone. Must hold on >=2 independent corpora/folds (proof-standards #4); a single slate is a
  selection artifact (we have only NBA 18 / MLB 180 republished mainlines today -- far below the
  gate, data-acquisition.md A4).
- CLV metric (this pocket HAS a defined CLV, unlike DFS): record the prediction-market price we
  would TAKE at decision time vs the eventual closing devigged consensus
  (`clv_ledger.compute_clv(side, taken_decimal, closing_decimal_home, closing_decimal_away)`,
  Shin-devig, positive = better number than close). Positive forward CLV at meaningful N on a
  specific venue/sport cell = CLV-PROVEN for that cell. Mind the SIGN gotcha (MEMORY: the OLD
  betting_portfolio `record_clv` was backwards; `clv_ledger.compute_clv` is the correct, consistent
  implementation -- do NOT re-introduce the backwards path).
- SIGNIFICANCE: cluster-robust Diebold-Mariano (games correlated); small-N divergence ROI is noise.

---

## 4. REALISTIC MAGNITUDE (honest)

There is NO measured magnitude here and we assert none. The realistic expectation: on liquid
major-sport mainlines the prediction-market price tracks the book devig closely -> divergence ~0
most of the time (efficient, the dominant case). The non-zero divergences cluster on THIN
contracts where the gap is mostly exchange spread (a non-edge). The genuinely actionable residue
-- a real, repeatable, takeable-at-size divergence where the exchange is stale relative to a
sharp consensus -- is expected to be RARE and small. The honest success criterion is finding the
few venue/sport cells (if any) with a measurable BSS>0 + positive CLV, and quarantining the rest.

---

## 5. THE HONEST CAVEATS (why this may NOT be real)

- **Exchange spread masquerading as divergence.** Low liquidity + wide bid/ask on Kalshi/Polymarket
  means the "price" is a fuzzy band; a devigged gap may be entirely spread, not a probability edge
  (data-acquisition.md B3). The liquidity guard (2.2) is load-bearing.
- **Not bettable at size.** Even a real gap may be untakeable beyond a few dollars on a thin
  contract -- so the "edge" does not scale (B3).
- **Name-resolution side flips.** Orientation is 100% name-driven; an unknown label flips a side
  and fabricates divergence (B3/B4). Drop uncertain matches (false-negative-biased matcher is the
  right posture, `aggregate.py:210`).
- **The sportsbook reference is one republished book** (ESPN pickcenter, B1) -- itself an efficient
  mainline (CUT 1) and a single-venue proxy, so "fair" has its own noise. A genuine multi-book
  consensus (keyed Odds API B2) would sharpen the reference but is out of the keyless default.
- **Arbitrage is not a profit center** (cut-list CUT 6): a book/exchange two-way arb is rare,
  fragile, limit-constrained. Keep divergence as a labeled FLAG, not the money engine; the durable
  execution edge is line-shopping for the best takeable price, not standing arb income.
- **Thin sample.** NBA 18 / MLB 180 republished mainlines is far below the proof gate; nothing here
  is provable until a real cross-venue closing-line series accrues (data-acquisition.md A4 +
  closing-line-and-clv.md).

---

## 6. TIER + WHAT WOULD PROMOTE IT

- TIER: HYPOTHESIS (divergence as a signal is unmeasured here -- B3/B4 both tier HYPOTHESIS). It
  is the WEAKEST of the P-tiers and should be the LOWEST priority of the three inefficiency files,
  consistent with cut-list discipline.
- TO CALIBRATION-PROVEN: leak-free WF BSS>0 for the divergence-favored side vs the
  sportsbook-devigged close, replicated on >=2 corpora, with liquidity-guarded contracts only.
- TO CLV-PROVEN: standing positive forward CLV (`clv_ledger.compute_clv`) on a specific venue/sport
  cell at meaningful N, taking the exchange price vs the eventual closing consensus, with the
  arb/limit caveats explicit.

ONE-LINE: Kalshi/Polymarket vs the devigged sportsbook is a different-crowd divergence we can
already compute on the merged multi-venue surface (`aggregate` -> per-venue `devig_twoway`), but it
is the weakest pocket -- most "divergences" are exchange spread or name-flip artifacts on thin,
not-bettable-at-size contracts -- so it stays a LABELED FLAG (never folded into a bettable
best_line), HYPOTHESIS, proven only by leak-free BSS>0 + forward CLV on a liquidity-guarded cell,
never by the raw gap.
