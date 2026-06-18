# soccer_intl -- EDGE MAP (beatable vs efficient, with evidence + tier)

_Part of the edge-intelligence corpus. SPORT = soccer_intl (World Cup / international).
The honest north star is CALIBRATION vs the devigged close, never a $-edge. Every claim
carries a tier (HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN) + the artifact that earns it.
Grounded in docs/research/project-deep-dive/04-soccer-wc-prop-engine.md and 06-eval-proving-spine.md,
the live cache data/domains/soccer/prop_calibration.json (as_of 2026-06-18, n=6620), and the code in
domains/soccer/ + scripts/platformkit/prop_edge.py. ASCII only._

## The one-line verdict
This sport is DATA-STARVED (24 WC events, every player exactly 1 WC match -- verified in
data/domains/soccer/espn_player_stats.parquet, 1241 rows). Player props are the only candidate
pocket (P1 in edge-theory.md); team mainlines are CUT. Of 10 prop markets, exactly ONE clears the
proven bar (Saves, bss +0.3365) and that one is near-deterministic, so the calibration there is
partly structural rather than a discovered edge. Net: the path to a defensible *calibrated* board
exists; the path to a *$-edge* does not yet, and is gated on data depth + CLV capture that has not
started.

## Market-by-market map

### CUT / EFFICIENT (stop hunting $-edge here)

| Market | Verdict | Tier | Evidence |
|---|---|---|---|
| Match h2h / result (1X2) | CUT -- efficient | n/a (mainline) | cut-list-no-edge.md CUT 1: sharp pregame mainlines match the close, CLV~0. WC mainlines are heavily bet by sharps; soccer scoreline model (domains/soccer/scoreline_engine.py, predictor.py) does NOT feed the prop stack and is decision-support only. |
| Over/Under total goals (2.5) | CUT -- efficient | CALIBRATION-only | Soccer O/U-2.5 proven adapter-only on 25,834 *club* matches (Poisson-totals) per MEMORY soccer-third-domain; on WC specifically the sample is 24 matches -- no edge, only calibration. Keep as a yardstick. |
| Asian handicap / spread | CUT -- efficient | n/a | Same family as h2h; sharp-priced. |
| Cards (player) | CUT -- DEMOTE (CUT 4) | WEAK (measured negative) | bss -0.1076, ece 0.0553, n=662. A single match's yellow card is near-irreducible Bernoulli noise. cut-list CUT 4 names this explicitly. Model-view only; never paper-bet. |
| Assists (player) | CUT -- DEMOTE (CUT 4) | WEAK | bss -0.074. Teammate-dependent, rare-event. |
| Goals (player) | CUT -- DEMOTE (CUT 4) | WEAK | bss -0.0252. Rare-event; Poisson on ~0.1-0.4 lam is a poor discriminator at the .5 line. |
| Goal+Assist (player) | CUT -- DEMOTE | WEAK | bss -0.0067 (~null). Sum of two leaky rare events; correlation unmodeled (independent marginals). |
| Offsides (player) | CUT -- DEMOTE | WEAK | bss -0.0155. Low-volume, noisy. |

### MARGINAL (keep on board, demoted; do NOT treat as edge yet)

| Market | Verdict | Tier | Evidence |
|---|---|---|---|
| Fouls (committed) | KEEP, marginal | MARGINAL | bss +0.0339, n=662, but below PROVEN_BSS=0.05 (prop_tiering.classify, prop_tiering.py:113). Higher-volume than goals (lam ~1-2) so the .5-ladder is informative. Best non-Saves candidate to graduate as data grows. |
| Fouls Drawn | KEEP, marginal | MARGINAL | bss +0.026. Same family; opponent foulsCommitted is the allowed-attribution source (team_defense.py:72-85). |
| Shots (total) | KEEP, marginal | MARGINAL | bss +0.0076 (~null). High volume (lam ~1-3) but high variance (brier 0.224, ece 0.085 -- worst ECE on the board); needs dispersion + minutes work. |
| Shots On Target | KEEP, marginal | MARGINAL | bss +0.0049 (~null). Should be jointly modeled with Shots (currently independent marginals -- a known gap). |

### BEATABLE pocket (the only proven one -- and read it skeptically)

| Market | Verdict | Tier | Evidence |
|---|---|---|---|
| Saves (goalkeeper) | KEEP, proven-calibration | CALIBRATION-PROVEN (suggestive) | bss +0.3365, brier 0.01755, ece 0.004, n=662. Clears proven bar (bss>=0.05 AND n>=100). BUT: deep-dive 04 sec 5 + 06 sec 5 both flag this as partly STRUCTURAL -- a keeper's save count is nearly a deterministic function of shots faced given minutes, so the .5-line backtest is near-trivial. 45 keeper-rows with saves>0 in the corpus; only ~48 G-position players total. Treat as "well-calibrated and not worse than the close," NOT a discovered $-edge. |

## Where to PUSH (concentrate effort)
1. **Saves -> from calibration to CLV.** It is the only market with real OOS skill. The missing
   step is CLV capture (prop_line_history.jsonl has ~1 row -- 06 sec 5). Until closing lines accrue
   we cannot say Saves beats anything; we can only say it is honest.
2. **Fouls / Fouls Drawn -> graduate to proven.** Both are positive-bss, high-volume, and the
   cheapest to move: just keep ingesting matchdays and re-run `props_eval --cache`. These are the
   realistic second/third proven markets per deep-dive 04 sec 7.
3. **Minutes projection (cross-cutting).** The biggest unmeasured error on the LIVE board: the
   calibration cache feeds REALIZED minutes (props_eval.py:127 loop), so the live board's true
   calibration is optimistic (04 sec 5, lever in model-levers.md). This caps every prop above.

## Where to CUT (reallocate away)
- All WC mainlines (h2h / total / handicap) -- efficient, cut-list CUT 1.
- Cards / Assists / Goals / Goal+Assist / Offsides as bet drivers -- measured negative/null skill
  (cut-list CUT 4). Keep as model-view rows; the tier system already demotes them
  (calibration_rank_key, prop_tiering.py:167, makes them impossible to top the board).
- Isotonic recal on this thin data -- DEFERRED (cut-list CUT 5; recal_eval verdict "overfit tell
  +0.01003 gap"). Do not re-enable until N grows.
- Opponent-adjustment as a trusted signal -- MEASURED NULL (team_defense plumbed but per-opponent
  table is ~1-3 matches deep, shrinks to 1.0). Keep wired, re-test as data grows; do not credit it.

## Honest tier summary
- CALIBRATION-PROVEN: Saves (1 market, suggestive on correlated n).
- MARGINAL (positive but sub-threshold): Fouls, Fouls Drawn, Shots, SOT.
- WEAK / CUT: Cards, Assists, Goals, Goal+Assist, Offsides.
- CLV-PROVEN: NONE (no closing-line capture; the top tier does not exist in code -- 06 sec 5 #4).
The board is a trustworthy, honestly-tiered calibrated decision-support surface. It is not, and on
current data cannot be, a profit engine.
