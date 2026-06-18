# WIRING SPEC -- NBA KEYLESS PROP PROVIDER joined to the deep NBA model + MC-sim ladder

_Part of the edge-intelligence corpus (`_wiring/`). Executable spec for a future BUILD agent.
Grounded in deep-dive 07 (the deep NBA prop stack + MC-sim ladder) + 09 (intelligence) + 12
(corpora) + the EXISTING keyless prop plumbing. HONESTY: soft/DFS player props are the P1 beatable
pocket (`_framework/edge-theory.md`), and the NBA model is the DEEPEST in the system -- so this is
where the credible prop ceiling lives. But DFS pick'em has no two-way close: prove via P(over)
calibration vs realized + realized ROI at fixed payout + DFS-line MOVEMENT, NEVER a fabricated $-edge.
ASCII only. READ-ONLY on code; this file only proposes (the model + engines live under `src/**`)._

---

## 0. Why NBA props are the credible prop pocket

- The MASTER PLAN's P1 pocket is "SOFT / DFS PLAYER PROPS... lazily priced, high volume, per-player
  distributions we can model" (`00-INTELLIGENCE-MASTER-PLAN.md`). Cut-list KEEP-list agrees.
- The NBA prop model is the DEEPEST in the project: `src/prediction/prop_pergame.py` (5,403 LOC,
  7 stats, leak-free per-game XGB+LGB+MLP NNLS-blend + isotonic, q50 quantile heads for 5 stats),
  honest holdout R^2 0.31-0.51 with controlled gaps (<0.075) (deep-dive 07 sec 2). Plus an MC-sim
  ladder: `PropPricingEngine.get_distribution` (10K possession sims -> full empirical distribution
  -> P(over); Gaussian fallback) at `src/prediction/prop_pricing_engine.py:268` (deep-dive 07 sec 1).
- NBA prop DATA is DEEP and multi-season: `data/domains/basketball_nba/player_boxscores.parquet`
  = 27,816 player-games (2024-10 .. 2026-01), `prop_pergame` corpus n=101,765 rows (atlas_lift.json).
  Cross-validation of prop calibration on MANY seasons is only credible where data is deep
  (deep-dive 12 sec 1.1) -- NBA is exactly that, unlike the 24-match World Cup vertical (CUT 4/5).

So: the same keyless DFS plumbing that already serves World Cup soccer props can serve NBA, joined
to a far deeper model. This is the single highest-value PROP wiring in the system.

---

## 1. The plumbing ALREADY EXISTS -- this is mostly an extension, not a new build

The keyless prop stack is built and tested for soccer_intl; NBA reuses ~90% of it:

- `scripts/platformkit/odds_provider/prop_prizepicks.py` -- keyless PrizePicks provider. The
  endpoints are SPORT-GENERIC: `GET /leagues` -> resolve a league id BY NAME, then
  `GET /projections?league_id=<id>&per_page=250&single_stat=true`. Today `_LEAGUE_NAME` (line 49)
  maps only `{"soccer_intl": "WORLD CUP"}`. **NBA needs ONE LINE: add `"nba": "NBA"`** (resolve by
  name, durable across seasons -- the `find_league_id` exact-normalized match at :75 already guards
  against "NBA 1H" / "NBA SZN" collisions).
- `scripts/platformkit/odds_provider/prop_underdog.py` -- the Underdog twin (same pattern).
- `scripts/platformkit/odds_provider/prop_base.py` -- `PropLine` normalized record + `canon_stat`.
  Today `_STAT_CANON` (line 29) is SOCCER-only. **NBA needs new stat mappings** (sec 2).
- `scripts/platformkit/prop_edge.py` -- the CONVERGENCE seam: joins scraped lines x the per-sport
  per-player distribution -> a RANKED, tier-labelled board. Today `_SUPPORTED = {"soccer_intl"}`
  (line ~30) and it imports `domains.soccer.prop_engine`. **NBA needs a parallel branch** that
  joins to the NBA model (sec 3).
- `scripts/platformkit/props_eval.py` -- the CALIBRATION GATE (`backtest_calibration` :249,
  `score_prop_predictions` :57, reliability bins :39). This is the leak-free P(over)-calibration
  scorer; NBA props get judged by the SAME gate (sec 5).
- `scripts/platformkit/prop_line_history.py` -- logs prop-line TICKS (for DFS-line movement, the
  pick'em CLV proxy). Already exists; just point it at the NBA feed.

DFS PICK'EM PRICING HONESTY (already enforced in `prop_prizepicks.parse_props` :148-160): standard
PrizePicks lines are pick'em -> `over_price=None, under_price=None, payout_type="dfs_pickem"`. We
NEVER fabricate a two-sided price. For NBA this is unchanged. goblin/demon flex variants still
expose no numeric two-sided price -> keep None.

---

## 2. NBA stat canon vocabulary (extend `_STAT_CANON` in prop_base.py)

PrizePicks/Underdog NBA stat_type labels map onto the model's 7 stats (pts/reb/ast/fg3m/stl/blk/tov)
plus the combos the MC-sim ladder can price coherently:

```
"points" -> "PTS"          "rebounds" -> "REB"        "assists" -> "AST"
"3-pt made" -> "FG3M"      "3-pointers made" -> "FG3M"
"steals" -> "STL"          "blocked shots" -> "BLK"   "blks" -> "BLK"
"turnovers" -> "TOV"
"pts+rebs+asts" -> "PRA"   "points+rebounds+assists" -> "PRA"
"pts+rebs" -> "PR"         "pts+asts" -> "PA"         "rebs+asts" -> "RA"
"blks+stls" -> "BS"        "fantasy score" -> "FANTASY"
"double double" -> "DD"
```
Unknown labels pass through UNCHANGED (prop_base.canon_stat contract :74) so nothing is silently
dropped. The COMBO stats (PRA/PR/PA/RA/BS) are the highest-value NBA DFS surface and the MC-sim
ladder can price them COHERENTLY (sec 3) where a per-stat Gaussian cannot.

---

## 3. The join: scraped NBA lines x the deep model + MC-sim ladder

`prop_edge.py` for NBA needs a branch that mirrors the soccer convergence but routes to NBA:

### 3a. Single-stat lines (PTS/REB/AST/FG3M/STL/BLK/TOV)
Price each `PropLine` against the deep per-game distribution:
- POINT + interval: `predict_pergame(stat, feature_row, ...)` (`prop_pergame.py:4859`) for the mean,
  then the per-stat quantile/conformal interval. CRITICAL: inflate sigma per the documented
  multiplier (blk ~x1.86, per-stat -- deep-dive 07 sec 5 "Sigma too tight"; memory
  `feedback_prop_interval_sigma_too_tight`). A too-tight distribution FABRICATES tail P(over) edges
  (proof-standards "TOO-TIGHT DISTRIBUTION" trap, saw +131% absurd EV). FLAG implausible |EV|.
- P(over) at the DFS line: for the 5 q50 stats, interpolate the quantile curve
  (`QuantilePropsModel.predict_proba_over`, deep-dive 07 sec 1) -- NO Gaussian assumption. For
  pts/ast use the blend mean + inflated sigma -> Gaussian P(over) as fallback.
- STL is near-noise (R^2 0.11) and BLK weak (0.22) (deep-dive 07 sec 5): FLAG these as
  low-confidence / non-bettable in the board output -- do NOT imply a usable distribution
  (deep-dive 07 sec 6 item 5). Demote them below reliable rows (the soccer board already has this
  `ev_flag` demotion pattern, prop_edge.py honest-note).

### 3b. Combo lines (PRA/PR/PA/RA/BS) -- the MC-sim ladder's coherent advantage
A per-stat Gaussian cannot price PRA correctly because pts/reb/ast are CORRELATED. Route combos to
the MC-sim ladder: `PropPricingEngine.get_distribution` (`prop_pricing_engine.py`) runs 10K
possession sims over `PossessionSimulator` -> a JOINT empirical sample of (pts, reb, ast, ...) per
player-game -> sum the relevant stats per sample -> empirical P(combo > line). This is the
sport-blind `JointDistribution` / `market_surface` philosophy (deep-dive 01 sec 2b) applied to
props: ONE sample matrix -> all combo ladders read off it coherently. The book misprices combos by
treating legs independently (P5 correlated-SGP pocket, edge-theory) -- the MC ladder is the tool
that can detect it. Use `correlation_recal.py` archetype-conditioned residual correlations
(genuinely wired, deep-dive 09 sec 3) to keep the joint coherent.

### 3c. Same-day minutes conditioning (the freshness lever)
Combo + counting props scale with minutes. Condition the distribution on projected minutes
(`minutes_aware_props.py` elasticity, or ideally the freshness feed from `same-day-freshness.md`).
A scratch/OUT teammate -> vacated minutes -> a measurable distribution shift the LAZY DFS line may
not yet reflect (the soft-pricing crack, edge-theory sec "where they crack"). This is where NBA
props + freshness COMBINE into the most plausible real pocket.

### 3d. Name resolution (the top risk -- copy soccer's discipline)
prop_edge.py's honest-note: "name resolution is the top risk (a wrong match fabricates a fake
edge)". Reuse the resolver pattern: build a name index over `player_boxscores.parquet` players,
fuzzy-match the PrizePicks `new_player.attributes.name`, and on NO confident match emit NOTHING for
that row (never guess -- the soccer resolver returns unmapped rather than mismatch). A fabricated
join is the fastest way to invent a fake edge.

HUMAN-GATED: `prop_pergame.py` / `prop_pricing_engine.py` / `minutes_aware_props.py` /
`correlation_recal.py` are under `src/**` (propose-only). The new NBA provider line + canon stats +
`prop_edge.py` NBA branch are ADDITIVE in safe areas (`scripts/platformkit/odds_provider/`,
`scripts/platformkit/prop_edge.py`). Edits to the src model layer are PROPOSED diffs under
`docs/research/organization-sprint/`. Build the additive plumbing; propose the src touches.

---

## 4. Cross-season calibration (the credible-ceiling claim)

The reason NBA props are worth the build: calibration can be CROSS-VALIDATED on MANY seasons.
- The per-game corpus is n=101,765 rows (atlas_lift.json), 2022-2026 (`games.parquet` span,
  deep-dive 12 sec 1.1), 27,816 player-games of recent box data.
- Run `props_eval.backtest_calibration` (`props_eval.py:249`) walk-forward across SEASONS: fit /
  calibrate on prior seasons, score P(over) calibration on the held-out later season -- a temporal
  split (proof-standards item 2). This is the >=2-corpus bar with REAL depth, unlike the 24-match WC
  vertical where isotonic recal OVERFITS (CUT 5; deep-dive 12 sec 3).
- Report per-stat Brier / ECE / reliability bins (`_reliability_bins` :39) of P(over) vs realized,
  paired with SHARPNESS (so collapse-to-0.5 is not mistaken for calibrated, proof-standards item 3).

---

## 5. PROOF for a DFS pick'em market (no two-way close)

`_framework/edge-theory.md` is explicit: DFS pick'em has no two-sided close -> CLV-vs-close is
UNDEFINED. Prove the NBA prop edge via the THREE allowed yardsticks:
1. P(over) CALIBRATION vs realized (sec 4) -- the north-star metric. CALIBRATION-PROVEN = per-stat
   Brier/ECE that is well-calibrated AND sharper than the naive recency baseline
   (`domains/basketball_nba/player_props.py:76 price_prop`, the honest L15-Gaussian reference).
2. REALIZED ROI at the FIXED DFS payout, walk-forward, at the TAKEN line -- with the small-N caveat
   (proof-standards item 5: -47% on 7 bets means nothing; require n>=60 settled, the cold-start bar,
   deep-dive 01 sec 5).
3. DFS-LINE MOVEMENT (`prop_line_history.py`): did the line move TOWARD our projection after we
   priced it? Positive line-movement-in-our-direction is the pick'em analog of CLV.

Evidence tier: starts HYPOTHESIS; advances to CALIBRATION-PROVEN on P(over) calibration sharper than
the recency baseline replicated across >=2 seasons; the pick'em "CLV-PROVEN" analog requires forward
DFS-line-movement + realized ROI at n>=60. Paper-only until that bar is cleared (real money is
hard-gated, deep-dive 01 sec 5).

## 6. Build order (minimal -> full)
1. `_LEAGUE_NAME["nba"]="NBA"` in prop_prizepicks.py + prop_underdog.py (one line each) +
   extend `_STAT_CANON` (sec 2). Per-file test: `test_prop_prizepicks.py` with an NBA fixture.
2. NBA branch in `prop_edge.py` for SINGLE stats (sec 3a) joined to `prop_pergame` + recency
   baseline; name resolver (3d); sigma inflation + |EV| flag.
3. `props_eval` cross-season NBA calibration backtest (sec 4) -> the CALIBRATION-PROVEN verdict.
4. Combo ladder via MC-sim (sec 3b) -- the coherent-joint advantage, the highest prop ceiling.
5. Wire `prop_line_history` to the NBA feed -> DFS-line-movement proof (sec 5).

## 7. Honest ceiling
NBA props are the system's BEST shot at a real prop pocket because the model is deepest and the data
spans seasons. The honest ceiling is a WELL-CALIBRATED per-stat + coherent-combo P(over) that is
SHARPER than the recency baseline and -- on the soft DFS surface, conditioned on same-day minutes --
plausibly mispriced often enough to show positive realized ROI + favorable line movement. That is a
CALIBRATION + soft-pocket claim, PROVEN forward on paper, never asserted. The pregame TEAM market
stays CUT (efficient, deep-dive 01 sec 7); props are where the depth can pay.
