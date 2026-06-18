# EVERY-MARKET MAP -- the full bet taxonomy, the honest hunt, the forward roadmap

> **Thesis (the honest edge lane).** Liquid mainlines (sides / totals / moneyline on
> major games) are razor-efficient -- our joint Monte-Carlo sim *MATCHES* them and does
> not beat them (proven below). The only place where being the smartest *can* pay is the
> **EXTREME / OBSCURE / PROP / DEEP-COMBO (SGP) / IN-GAME-MICRO** tail that little or no
> sharp money polices. The system already PRICES every imaginable bet as a function of the
> SAME (n_sims, K) correlated samples (so every parlay preserves the joint structure that
> leg-by-leg pricing destroys); this map is the census + the honest hunt result + the
> roadmap to VALIDATE the suspected thin-market mispricing forward.
>
> **The binding catch.** Almost every obscure market has **no real historical close data
> locally**. It can be PRICED + CALIBRATED now, but VALIDATED only via forward capture.
> So the honest hunt can only run the gate on the few HAS_CLOSE mainlines -- and those
> MATCH / REJECT (efficient). **No obscure market can SHIP here, by construction. There is
> no fabricated survivor.** A soft-line in-sample beat would be SUGGESTIVE only, never a $
> claim, and real $ is additionally capped by book limits on thin lines.

Code: `scripts/platformkit/market_coverage/` (NEW; consumes `src/sim`,
`scripts/team_system/market_intelligence.py`, `predict_matchup`, and the REAL
`scripts/platformkit/eval_gate/` READ-ONLY -- none of those human-gated modules edited).

---

## 1. The full taxonomy -- every imaginable bet, by family

Two orthogonal honesty axes are attached to EVERY enumerated market (`tags.py`):

- **THINNESS** -- how much sharp money polices the line (where smart *can* pay):
  `LIQUID` (mainline, razor-efficient, we MATCH) -> `SEMI` (core star props) ->
  `THIN` (combos / alt-lines / quarter-half / role-player props) ->
  `EXTREME` (longshots / deep SGP / scenario / in-game micro).
- **VALIDATABLE** -- can the price be confirmed offline at all:
  `HAS_CLOSE` (real local close -> gate it NOW vs the SHIN-devigged close) ->
  `PRICE_ONLY` (marginal calibratable now, no captured close for THIS line) ->
  `FORWARD_ONLY` (no local close at all -> validated only by forward CLV).

| # | Family | Example markets (priced off ONE joint sim matrix) | Typical thinness | Validatable now? |
|---|--------|---------------------------------------------------|------------------|------------------|
| 1 | **player-props-core** | every-stat O/U at alt lines: pts (10..50), reb (6..15), ast (5..12), fg3m (2..6), stl, blk, tov; PRA tiers | SEMI (stars) / THIN (role) | PRICE_ONLY (marginal WF MAE), close FORWARD_ONLY |
| 2 | **player-props-combos** | same-player cross-stat: PR / PA / RA / PRA, stocks; milestone ladders (30+ pts, 10+ ast, 15+ reb); double-double / triple-double / 5x5 | THIN -> EXTREME | FORWARD_ONLY (joint, no local close) |
| 3 | **team-quarter-half** | team totals + sides for Q1-Q4 / H1 / H2; quarter winners | THIN (slow-moving, stale) | FORWARD_ONLY (quarter split is a sim-derived APPROX) |
| 4 | **game-scenario-longshot** | blowout 15+/20+, nailbiter <=3, OT band, shootout 230+, rockfight <205, race-to-20, winning-margin band, any-35/40/50+ scorer, player 50+ | EXTREME (+10000 tails) | FORWARD_ONLY |
| 5 | **sgp-correlation** | correlated multi-leg parlays: 2-leg same-player, 2-leg teammates, 3-leg mixed, star+game-total; priced JOINT (joint/independent **lift** surfaces where the book's leg-by-leg price is wrong) | EXTREME | FORWARD_ONLY (no SGP close stored locally) |
| 6 | **mlb-soccer-tennis** | generic over/under + moneyline / match-win on the other sports; the **HAS_CLOSE reference markets** live here | LIQUID (mainline) / SEMI | **HAS_CLOSE** (NBA ml, MLB ml, soccer O/U 2.5, tennis match-win) |
| 7 | **ingame-micro** | next basket, next team to score, live win-prob band, race-to-next-5, in-game player milestone (live re-priced) | EXTREME | FORWARD_ONLY (no historical micro close; live-repriceable only) |

Pricing substrate: `markets.SampleBook` wraps one coherent `(n_sims, K)` matrix; `build_menu`
/ `book_builder.build_full_book` enumerate all 7 families off it; `price_joint` REFUSES an
`independent` book (pricing correlated legs independently mis-prices them -- the kernel
boundary). The sim prices every number; the LLM authors none.

---

## 2. The honest hunt -- model vs the (often soft) close

`edge_finder.py` runs the **REAL** `eval_gate.walk_forward` (leak-free, purge/embargo) on every
HAS_CLOSE market, pools >=2 independent corpora where they exist, scores BSS vs the **SHIN-devigged
close**, and requires clustered Diebold-Mariano `p<0.05`, `N>=200`, `>=2 corpora` to SHIP. The
predict_fn is a deliberately-weak "shrink the train-slice base rate toward the close" forecaster:
the point is the GATE VERDICT (do we beat the soft close?), not a tuned engine.

**Result on the real local corpora (NBA / MLB / soccer; 2026-06-16):**

| market | family | verdict | BSS vs close | DM p | N |
|--------|--------|---------|--------------|------|---|
| soccer_ou25 (Over 2.5) | mlb-soccer-tennis | **MATCH** | +0.0007 | 0.547 | 2497 |
| nba_moneyline | mlb-soccer-tennis | **REJECT** | -0.0117 | 0.025 | 747 |
| mlb_moneyline | mlb-soccer-tennis | DATA_LIMITED | - | - | - (box/odds id-spaces do not join) |
| 44 obscure / prop / combo / SGP / quarter / scenario / in-game markets | families 1-5, 7 | **NEEDS_FORWARD_CLV** | - | - | - (no local close) |

- **soccer O/U 2.5 = MATCH.** `|BSS| <= 0.01` -> the totals market is efficient; we match the
  devigged close within noise. Honest null, recorded as a success.
- **NBA moneyline = REJECT.** The weak shrink-to-close forecaster *loses* to the close
  (BSS negative); the mainline is efficient -- there is no beat to be had on it. (It is also a
  single-corpus fold, N=747, so it could not satisfy the >=2-corpora rule even with a positive
  BSS -- a second binding reason it can never SHIP locally.)
- **MLB moneyline = DATA_LIMITED.** ESPN numeric `event_id` vs the date-team odds id-space do
  not join -> 0 states -> honest DATA_LIMITED, not a result.
- **0 SHIPs.** Every obscure / prop / SGP / quarter / scenario / in-game market is
  NEEDS_FORWARD_CLV: priceable + calibratable now, but with no local close it CANNOT ship here.
  **No fabricated survivor.**

**MATCHED (efficient, honest null):** soccer O/U 2.5 (and NBA / MLB mainlines, consistent with the
already-proven whole-platform result -- mainlines MATCH the devigged close, never beat it).
**BEAT a soft line >=2 corpora + DM p<0.05 + N>=200:** **none.** The hunt is honest: the lane where
a beat is *plausible* (the thin tail) is exactly the lane with no local close to gate against.

---

## 3. Verifier status (this sprint)

- **market_coverage per-file tests: 54/54 PASS** -- `tests/test_{book_builder,coverage,edge_finder,sample_book,tags}.py` + `test_markets.py` + `test_calibrate.py`, each run per-file with the basketball_ai interpreter.
- **eval-gate reference core: 34/34 GREEN** (`eval_gate/run_all.py`): test_eval_core 8/8, test_walkforward 6/6, test_shin 5/5, test_ingame_blend 4/4, test_freshness 6/6, test_ledger 5/5. The gate is unmodified and still fail-closed.
- No human-gated module (`src/sim`, `src/prediction`, `scripts/team_system/market_intelligence.py`, `eval_gate/*`) was edited.

---

## 4. The roadmap -- which thin markets to capture forward, and the honest catch

The ONLY way to turn a NEEDS_FORWARD_CLV market into a validated result is the
**forward-capture clock** (`scripts/platformkit/forward_capture/`): an append-only, atomic,
idempotent timestamped odds archive that logs OUR price BEFORE the line moves, then grades
forward CLV (open->close, and price-vs-outcome) over time. It stores RAW QUOTED PRICES only --
no probability/edge/$ column exists, so a dollar claim cannot be stored even by accident.

**Capture priority (highest suspected mispricing x lowest policing first):**

1. **Core single player props (family 1, SEMI/THIN).** Most capturable (props feeds are common),
   marginals already calibratable -> capture closing prop lines forward, grade our sim marginal
   vs the devigged prop close. The honest near-term win is per-prop CALIBRATION, not $.
2. **Quarter / half team totals + sides (family 3, THIN, slow/stale).** Soft, slow-moving, often
   stale -> the cleanest "thin and policed-late" lane. Capture period closes forward. NOTE our
   quarter split is a sim-derived APPROX (tagged TAIL_APPROX) until a real per-quarter sim exists.
3. **SGP / correlated combos (family 5, EXTREME).** Where the joint **lift** is real and books
   price legs near-independently -> structurally the best mispricing candidate, BUT no SGP close
   is stored anywhere locally and SGP limits are the lowest in the book. Forward-capture the
   book's actual SGP price vs our joint price; expect the tightest $ cap.
4. **Scenario / longshot tails + in-game micro (families 4, 7, EXTREME).** Capture live-repriced
   micro markets during games (the in-game repricer already exists). Validation is *only* forward;
   these have the widest vig and lowest limits.

**The honest catch (binding):**

- **Most obscure markets have NO local close** -> they are PRICED + CALIBRATED now but VALIDATED
  only via forward capture. The forward clock has not yet accrued a graded survivor.
- **A soft-line in-sample beat is SUGGESTIVE, never a $ claim.** Any future survivor is flagged
  `needs_forward_clv` and must clear the forward CLV clock first.
- **Real $ is capped by book limits.** The thinner / more exotic the market (exactly where
  mispricing is most plausible), the lower the limit -> the dollar ceiling shrinks as the
  suspected edge grows. Calibration + CLV is the deliverable; ROI is not claimed.
- **Mainlines MATCH and will keep matching.** Re-running the gate on more mainline data will
  reproduce MATCH/REJECT, not a beat. That is the proven, honest baseline.

**Next real step:** wire a real odds feed into `forward_capture` (currently MockFeed + RealFeed
stub), start the clock on family 1 (core props) + family 3 (quarter/half), and grade forward CLV.
Only a market that clears that forward clock vs its real close may ever be called a survivor --
and even then the claim is calibration + CLV, capped by limits, never a fabricated ROI.
