# NBA PROP PUSH-PLAYBOOK -- ASSISTS (AST)

_Deep/actionable layer of the edge-intelligence corpus. Sport = NBA. The ONE documented
near-durable NBA model edge (~+7%, both directions) -- fragile, kept RAW on purpose, never bet
in playoffs. Grounded in src/prediction/prop_pergame.py, scripts/ast_edge_*.py +
validate_ast_edge_*.py, props_pergame_metrics.json, deep-dive 07, and MEMORY
feedback_ast_edge_is_real_not_underbias. ASCII. No fabricated $-edge; tier-tagged throughout._

## One-line verdict
AST is the single NBA prop where the per-game model has shown a real, bidirectional divergence
from the closing prop line that survived bootstrap + an anti-model flip (a skilled model must
LOSE when flipped -- it does). It is FRAGILE: validated only on one ~9-week window, flagged
"period-unstable," and the related headline +18.38% was a separate market-follow artifact (do
NOT conflate). Tier: HYPOTHESIS -> (re-prove) CALIBRATION; $-edge unproven on closing lines.

## The model (and WHY it is deliberately RAW)
- AST is priced by the per-game stack `prop_pergame.predict_pergame("ast", row)`
  (prop_pergame.py:4859) on the BLEND path: XGBoost + LightGBM + seed-MLP -> NNLS blend ->
  isotonic calibrator -> garbage-time haircut -> residual correction.
- CRITICAL POLICY: AST is deliberately NOT on the q50/calibration-to-mean path that ships for
  {reb,blk,stl,tov,fg3m} (prop_pergame.py:115, _USE_Q50_STATS excludes ast). Calibrating AST
  toward the mean would pull the prediction toward the market and KILL the divergence that IS
  the edge (accuracy != edge -- the load-bearing project lesson). Keep AST RAW. Any future
  recalibration of AST must be gated against the AST closing-line backtest, not against MAE.
- Honest holdout (props_pergame_metrics.json, leak-free temporal split): AST R2 0.4988, MAE
  1.36, train R2 0.5582, gap 0.059 -- modest, well-controlled, no overfit blowup.

## Drivers (rate-only, ARCHETYPE not people)
1. PLAYMAKING ROLE (dominant): the "primary creator / high-usage lead guard" archetype carries
   a high, stable assist rate; the edge concentrates on high-assist roles where soft books lag
   teammate-redistribution. Describe by ROLE/ARCHETYPE, never by name (binding graph rule).
2. TEAMMATE FINISHING + AVAILABILITY (the leak risk AND the freshness lever): assists depend on
   teammates converting -> a counting-stat context leak. When a high-usage scorer is OUT, the
   creator's assist opportunity shifts -- this is exactly the SAME-DAY FRESHNESS lever (minutes/
   role/lineup) the historical box model cannot see (deep-dive 07 sec5/6). The biggest unmodeled
   driver and the most likely source of any durable AST edge.
3. PACE / GAME SCRIPT: faster pace + competitive script -> more possessions -> more assist
   chances; blowouts compress them.
4. SOFT-BOOK LAZINESS: DFS/soft books set assist lines off a stale base that lags role changes
   (deep-dive 07; markets-and-props "soft books lazy on playmakers").

## Data
- HAVE: `data/domains/basketball_nba/player_boxscores.parquet` (~27.8k player-games) + the
  per-game leak-free feature builder (prop_pergame.build_pergame_dataset); cached OOF
  predictions; the benashkar closing-line corpus + eval_2025_26_combined.csv (a SECOND,
  independent line source) for replication.
- MISSING: a live keyless prop feed wired in (the top NBA get-to-edge blocker -- props
  priced but not compared to book lines at scale); same-day minutes/lineup freshness in BOTH
  train and inference builders (parity); real SGP/closing-line capture for forward CLV.

## Calibration / CLV proof plan (this stat has REAL proof scripts -- reuse them)
- DECOMPOSITION (already built -- `scripts/ast_edge_decomposition.py`): on real closing lines at
  ACTUAL posted odds it runs (1) OVER/UNDER direction split, (2) always-over / always-under
  baselines on the same slate, (3) ANTI-MODEL flip (a skilled model must lose flipped),
  (4) mean(actual - line) line-bias check (is the line just set low?), (5) top-K-player removal
  (overfit/concentration check), (6) bootstrap 95% CI on ROI, (7) early/late temporal split.
  This is the gold-standard recipe -- AST passing the flip + bootstrap is what earns "real edge,
  not under-bias artifact."
- CROSS-CORPUS REPLICATION (already built -- `scripts/validate_ast_edge_independent.py`):
  rolling-origin backtest that retrains the EXACT production AST stack
  (cache_pergame_oof._train_and_predict_stat) on rows strictly before each monthly cutoff, then
  grades fresh leak-free preds vs eval_2025_26_combined.csv closing AST lines. RUN THIS: edge
  replicating out-of-corpus is the decisive de-risk; vanishing is a critical red flag.
  (validate_ast_edge_crosstime.py, validate_ast_edge_extoos.py extend the time/OOS surface.)
- THE BAR: leak-free OOS BSS>0 vs the DEVIGGED prop close (not vs MAE), bootstrap-significant,
  replicating on >=2 corpora (proof-standards.md rule 4). Then forward CLV on captured closing
  AST lines via clv_ledger for real money.

## Soft-line target (the $-hypothesis cell)
Assist O/U on high-playmaking ROLES on DFS/soft books, REGULAR SEASON ONLY, where the line lags
a recent role/teammate-availability change. Bet BOTH directions per the model's divergence (the
edge is bidirectional, not a blind under). NEVER in playoffs (see caveat).

## Honest tier + caveat
- TIER: HYPOTHESIS -> CALIBRATION (re-prove leak-free OOS vs devigged close before trusting).
  $-edge: unproven on closing lines (no captured AST closing-line CLV yet).
- CAVEATS (binding): (1) NEVER bet AST in PLAYOFFS -- the edge is regular-season and
  period-unstable (MEMORY feedback_ast_edge_is_real). (2) Keep AST RAW -- do NOT add the q50/
  mean-calibration path; it would erase the divergence. (3) Do NOT conflate the AST edge with the
  retracted +18.38% (a separate market-follow + flat-payout artifact -- no-edge-claims rule).
  (4) It is validated on ONE ~9-week window -> run validate_ast_edge_independent.py to confirm
  cross-corpus before sizing anything. This is the strongest NBA model signal we have, and it is
  exactly as fragile as that sentence implies.
