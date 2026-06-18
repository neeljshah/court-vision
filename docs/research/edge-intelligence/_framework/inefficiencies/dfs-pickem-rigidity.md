# INEFFICIENCY: DFS PICK'EM PAYOUT RIGIDITY (P1, structural) -- detection recipe + proof

_Part of the edge-intelligence corpus (_framework/inefficiencies/). The DEEP, actionable layer
for ONE pocket: the structural crack in fixed-payout DFS pick'em (PrizePicks standard, Underdog
pick'em fallback). Grounds: edge-theory.md (P1 + the structural-DFS note), proof-standards.md,
cut-list-no-edge.md (CUT 4 demoted stats), _scrapers/data-acquisition.md (A1/A2/D2),
_scrapers/closing-line-and-clv.md (DFS proof path), and the live code
`scripts/platformkit/prop_edge.py` + `odds_provider/prop_prizepicks.py` + `prop_underdog.py`.
Binding: no $-edge claimed; ASCII only; a null here is a SUCCESS._

---

## 1. THE EXACT MECHANISM (why the crack exists)

A two-way sportsbook defends a mispriced number by MOVING it: sharp money on the cheap side
shifts the line and re-vigs until EV->0. A DFS pick'em book CANNOT do this. PrizePicks (and any
Underdog row that falls back to `payout_type="dfs_pickem"`) posts a single PROJECTION (the line)
and a FIXED multiplier payout (2-pick / 3-pick power/flex). The payout is structurally frozen;
the only lever the operator has is moving the projection itself. So:

- When a projection is genuinely off the true median (stale base rate, ignored role change,
  ignored opponent), the mispricing PERSISTS until the operator manually re-projects -- there is
  no continuous market-clearing pressure pulling it to fair. This is the cleanest STRUCTURAL
  inefficiency in the taxonomy (edge-theory.md "STRUCTURAL: fixed-payout DFS pick'em can't move
  to kill a genuinely mispriced projection").
- The operator's incentive is also not "be unbiased" -- it is balanced action and a target hold
  via the multiplier. So projections can be systematically shaded toward the popular side
  (overs on stars, name-recognition unders) rather than toward the true median.

The edge is therefore: a per-player distribution that is BETTER-CALIBRATED than the operator's
lazy projection, on a stat where we have genuine predictive skill, priced against a line that
will not move to defend itself.

CRITICAL HONESTY (binding): there is NO two-way price on a pick'em row -> CLV-vs-close is
UNDEFINED (edge-theory.md DFS note). Every pick'em edge in our board is tagged
`edge_basis="model_view"` (gap from 0.5), NEVER a priced EV (`prop_edge.py:216-217`). We never
invent a synthetic two-way price to manufacture a CLV number -- that is a fabricated-edge
violation (closing-line-and-clv.md "do NOT fake it").

---

## 2. IN-DATA DETECTION RECIPE (exactly what to compute)

The board already computes the raw materials. The detection is: rank pick'em projections by the
gap between OUR calibrated P(over) and the implied 0.5, FILTERED to stats with proven skill and
players with a real prior, then watch whether the LINE itself moves toward our number.

### 2.1 Compute the model-vs-line gap across the slate
- Source the projections: `PrizePicksProvider.fetch_props(sport)` (`prop_prizepicks.py:42-43`,
  endpoints `/leagues` then `/projections?league_id=<id>&per_page=250&single_stat=true`) and the
  Underdog pick'em fallback rows. League resolved BY NAME (`_LEAGUE_NAME`, `:49`).
- Build the board: `prop_edge.build_prop_board(sport, as_of=...)` -> per row
  `model_p_over` = `float(p_over_fn(line.line))` (`prop_edge.py:171`), `model_lam`, `side`,
  `confidence`, `payout_type`, `ev_flag`. For pick'em rows `edge_basis="model_view"` and
  `model_gap = abs(model_p_over - 0.5)` (`:216`).
- The DETECTION STATISTIC for a pick'em row = `model_gap`, but ONLY trusted when:
  - `confidence == "ok"` (club-backed OR >=2 matches and not shrunk-to-baseline,
    `prop_edge._confidence` `:110`) -- a thin-data gap is a model artifact, not an edge.
  - `ev_flag == "ok"` (NOT `"uncalibrated_thin"`, NOT `"implausible"` |EV|>0.5 from a too-tight
    distribution, `:124`).
  - the stat is on the PROVEN list (section 4), not a CUT-4 demoted stat.
- The distribution must already be NB-WIDENED by the leak-free per-stat dispersion index
  (`soccer_dispersion.all_dispersions`, `prop_edge.py:269`); a raw Poisson is too tight and
  FABRICATES tail edges (proof-standards too-tight trap). This guard is load-bearing here because
  pick'em "edge" is entirely a distribution-shape claim.

### 2.2 The structural tell: LINE MOVEMENT (the thing CLV-vs-close cannot give us)
Because the payout is frozen, the operator's ONLY correction is moving the projection. So the
honest substitute for CLV is: did the line move TOWARD our flagged side, and did the result land
on it? Concretely, run the closing-line capture loop on pick'em rows too:
- Poll the board every tick up to kickoff; `prop_line_history.log_board_lines(board)` appends a
  time-series row per prop (`prop_line_history.py:57`). NOTE: `_priced` (`:45`) SKIPS pick'em
  rows for the CLV path (correct), so for the line-MOVEMENT detection we log the `line`
  (`stat_value`) trajectory separately, keyed `{match, player, stat}` + ts.
- DETECTION: for each pick'em prop, compute `line_open -> line_close` delta and compare its SIGN
  to our flagged `side`. A projection that drifts toward our side BEFORE settling is the
  operator correcting toward our number -- the structural-inefficiency fingerprint.
- Then settle: realized outcome vs `line_close`. Three-column scoreboard per stat:
  P(over) calibration (Brier/ECE), realized hit-rate at the FIXED payout, and line-movement
  agreement %.

### 2.3 Cross-book consistency check (a free fraud filter on the gap)
When the SAME player+stat also appears on a two-way book (Underdog `payout_type="sportsbook"`,
or FanDuel B5 if un-stranded), devig that two-way price (`odds_shop.devig_twoway`) to a fair
P(over) and compare it to the PrizePicks projection's implied median. If the sportsbook's
devigged median materially disagrees with the pick'em projection, the pick'em line is the stale
one -- and our model should agree with the sportsbook, not the pick'em. A model-gap that the
two-way book ALSO sees is the strongest candidate; a model-gap NO other venue sees is most likely
our own model error (or a name mis-resolution -- section 5).

---

## 3. PROOF METHOD (leak-free, which metric, and why NOT CLV)

DFS pick'em is the one pocket where the standard CLV bar does not apply. The proof spine
(closing-line-and-clv.md "honest DFS-pickem caveat") is a THREE-legged substitute, each leak-free:

1. **P(over) CALIBRATION vs realized (the north-star metric here).** Leak-free walk-forward: for
   each settled prop, `model_p_over` was computed `as_of < kickoff` (the board stamps `as_of`,
   `prop_edge.py:191`; distribution uses only pre-as_of data via `player_rate` /
   `prop_distribution`). Score Brier + ECE on the over-probability vs the realized over/under at
   the pick'em line. The bar (proof-standards #3): Brier + ECE paired with sharpness (so
   collapse-to-0.5 isn't "calibrated"), Brier-Skill-Score vs the base-rate-at-the-line. BSS>0 vs
   that base rate = CALIBRATION-PROVEN for this stat. Must hold on >=2 independent corpora/folds
   (proof-standards #4) -- a single tournament is a selection artifact.
2. **Realized ROI at the FIXED payout.** Simulate the actual 2-pick/3-pick power/flex multiplier
   on the flagged picks; report realized ROI with the real multiplier, NOT a devigged EV. This is
   weaker than CLV (no market verdict) but it is the operator's actual payout structure.
3. **LINE MOVEMENT (the structural tell).** Per 2.2: % of flagged props where the projection
   moved toward our side before close, and conditional hit-rate when it did. A standing positive
   on all three legs, cross-corpus, at meaningful N, is the pick'em analog of CLV-PROVEN -- label
   it "CLV-PROVEN (DFS substitute)" and state plainly that no two-way close exists.

Leak-free discipline baked in: separate train/inference builders (train/inference parity -- a new
prop feature that reads 0.0 at inference is the most expensive bug class, proof-standards #1);
walk-forward only; recalibrators fit on EARLIER matches tested on LATER (in-sample isotonic on
thin data ALWAYS looks good -- that is exactly why WC P(over) recal was DEFERRED, cut-list CUT 5).

Cold start: <~60 settled props for a stat -> INSUFFICIENT_DATA (proof-standards gate); accrue
before judging. The current WC corpus is 24 matches -> calibration claims are "suggestive," NOT
established (`prop_edge.py` honest_note; data-acquisition.md C3).

---

## 4. REALISTIC MAGNITUDE (honest, tiered per stat)

There is NO measured $ here and we do not assert one. The realistic CALIBRATION magnitude is
"sharper than a lazy projection on a few stats where we have skill; flat-to-negative on the
rest." Concentrate on the PROVEN stats and DEMOTE the rest:

- KEEP / concentrate (where calibration is plausibly positive): WC Saves (the one WC stat with
  positive measured skill), expected MLB Hits / Pitcher-Ks / Walks (own-rate, low teammate leak),
  NBA AST and REB props (AST is the one near-durable NBA model edge, ~+7% historically, RAW,
  never playoffs -- cut-list KEEP / NBA inefficiency-catalog N1).
- CUT / demote (CUT 4, measured negative or null skill, leak-free WC backtest): Cards
  (BSS -0.11), Assists (-0.07), Goals (-0.03), Shots-on-Target (~0). Likely MLB analog:
  Total Bases / RBIs / Runs (multi-outcome, teammate-dependent, Poisson is a poor shape -- the
  teammate/context-leak trap, proof-standards). These rank BELOW proven stats in the board and
  must NOT be paper-bet as edges (`prop_tiering` already demotes them; honest_note labels them
  "weak").

So the realistic picture: a handful of player x stat cells where our distribution is genuinely
sharper than the frozen projection, surrounded by a majority of cells where we are not -- and the
whole pocket gated on a DFS proof substitute, never a claimed profit.

---

## 5. THE HONEST CAVEATS (why this may NOT be real)

- **Name resolution is the #1 fabrication risk.** A wrong player match invents a fake edge
  (`prop_edge.py` docstring: "a wrong match fabricates a fake edge"). Resolution is via
  `resolve_player` (`:146`); a mis-resolve silently prices the wrong player's distribution against
  this player's line. PrizePicks league is matched BY NAME (`find_league_id`), and team aliases /
  accents / neutral-site WC naming MISS silently (data-acquisition.md cross-source matching). Any
  flagged edge MUST be checked for `matched_name == player` before trust.
- **Our distribution may be the wrong one, not the projection.** A model_gap that no two-way book
  agrees with (2.3) is more likely OUR error than an operator stale line. Too-tight distributions
  fabricate tail edges (proof-standards); the NB-widening guard mitigates but does not eliminate
  this.
- **Thin data.** 24 WC matches is below the proof gate; "calibration-proven" cannot be claimed at
  that N (proof-standards thin-data trap). The pocket only becomes provable in sports with deep
  corpora -- which is exactly why D2 (Underdog/PrizePicks NBA+MLB league ids on the SAME keyless
  endpoints, joining the deep boxscore corpora) is the single highest-value scraper change.
- **goblin/demon flex odds unparsed.** PrizePicks' highest-payout alt-projection lines are
  acknowledged but NOT parsed (data-acquisition.md A2) -- a real coverage gap; the multiplier
  structure on those is different and our fixed-payout ROI sim would be wrong for them.
- **Operator counter-measures.** Pick'em operators limit/curate winning accounts; even a real
  structural edge can be execution-throttled (cut-list discipline on fragile execution edges).

---

## 6. TIER + WHAT WOULD PROMOTE IT

- TIER: HYPOTHESIS (structural mechanism is sound; no leak-free OOS calibration artifact yet at a
  trustworthy N; current WC N=24 is below the gate).
- TO CALIBRATION-PROVEN: leak-free WF P(over) BSS>0 vs the base-rate-at-line on a PROVEN stat,
  replicated on >=2 corpora (needs D2: NBA/MLB DFS league ids + the deep boxscore corpora).
- TO CLV-PROVEN (DFS substitute): standing positive on all three legs of section 3 (P(over)
  calibration + fixed-payout ROI + line-movement agreement) forward, at meaningful N, per
  PROVEN stat -- never a two-way CLV, always labeled as the DFS substitute.

ONE-LINE: fixed-payout DFS pick'em can't move to defend a stale projection, so a better-calibrated
per-player distribution on a PROVEN stat is a real structural candidate -- but it is proven by
P(over) calibration + fixed-payout ROI + LINE MOVEMENT (never CLV), gated on deep corpora we don't
yet have for the high-volume sports, and the dominant risk is name mis-resolution + our own
too-tight distributions, not the operator.
