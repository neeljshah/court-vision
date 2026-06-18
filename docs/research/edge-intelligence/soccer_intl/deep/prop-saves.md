# soccer_intl PROP PUSH-PLAYBOOK -- SAVES (goalkeeper)

_Deep/actionable layer of the edge-intelligence corpus. Sport = soccer_intl (World Cup).
The ONLY calibration-proven WC prop (bss +0.3365). Read it skeptically: the proof is partly
STRUCTURAL, so the genuine bar for this stat is FORWARD CLV, not the backtest. Grounded in
domains/soccer/{player_rates,prop_engine,team_defense,dispersion}.py, prop_calibration.json
(as_of 2026-06-18, n=662/stat), deep-dive 04 sec5/sec7, and the verified data on disk.
ASCII. No fabricated $-edge; every claim carries a tier + the artifact that earns it._

## One-line verdict
Saves is the one WC stat that beats the base-rate reference out-of-sample (bss +0.3365), but
that lift is mostly because save count is a near-deterministic function of shots-on-target
faced -- so calibration here is cheap and proves little about EDGE. The real, unproven prize is
on the SHOT-VOLUME projection for low-attention keepers (backups, minnow-nation GKs) priced
off lazy DFS lines. Tier: CALIBRATION-PROVEN (suggestive, correlated-n); $-edge HYPOTHESIS,
blocked on closing-line capture.

## The model (what produces the number)
- Pipeline: `player_rates.player_rate(stat="Saves")` -> per-90 save rate, EB-shrunk toward a
  keeper baseline (SHRINK_K=3, player_rates.py:255), blended with the ESPN club prior
  (club_w = min(starts, 20), player_rates.py:203-224). lam = per90 * E[min]/90 * opp_mult
  (prop_engine.py:161).
- Distribution: NB, two-pass -- Poisson learns lam, then re-distribute with r = lam/(phi-1)
  (prop_edge.py:154-165); phi from `dispersion.stat_dispersion("Saves")`. Saves is the stat
  that MOST needs the NB widen: keeper save counts swing 0..8, a Poisson tail at lam~2-3 is far
  too thin for the over-4.5 / over-5.5 ladder rungs.
- Opponent multiplier: Saves <- opponent shotsOnTarget (team_defense.py:72-85). This is the
  RIGHT driver -- a keeper's saves are mechanically driven by how many SOT the opponent
  generates -- but on ~24 WC matches the per-opponent SOT table is 1-3 matches deep and shrinks
  to ~1.0 (deep-dive 04 sec5). Wired, currently a near-no-op.

## Drivers (what actually moves saves; rate-only, never people)
1. OPPONENT SHOT-ON-TARGET VOLUME (dominant). Saves ~ SOT_faced x (1 - finishing_rate). The
   edge lever is projecting opponent SOT, NOT the keeper's stopping skill (which is high-variance
   and near-league-flat at this sample). This is why Saves "calibrates" trivially: condition on
   realized SOT and the count is almost deterministic.
2. GAME SCRIPT / team strength: a keeper on a weaker nation faces more shots -> higher save
   floor. The team scoreline model (scoreline_engine.py) ALREADY knows which side is the
   underdog but does NOT feed the prop stack (deep-dive 04 scope note) -- a free, unused signal.
3. KEEPER MINUTES: GKs almost always play 90 unless subbed/sent off, so minute risk is the
   SMALLEST of any prop here. This is a structural reason Saves is the cleanest WC prop.
4. ROLE/ARCHETYPE: a "sweeper-keeper" behind a high-line press faces fewer but higher-quality
   shots; a "shot-stopper" behind a deep block faces more volume. Describe via SCHEME (high-line
   vs low-block), never by name. Today unmodeled -- a candidate rate-conditioning feature.

## Data
- HAVE: `espn_player_stats.parquet` saves column -- VERIFIED 45 rows with saves>0, mean 2.82
  saves (only ~48 G-position players total in the 1,241-row corpus). `espn_club_priors.parquet`
  carries a Saves prior for 101 keepers. Opponent SOT is in the same per-match table.
- MISSING (the binding gaps): (a) closing prop lines -- `prop_line_history.jsonl` is ~1 row
  (deep-dive 06 sec5), so NO CLV exists; (b) projected (not realized) minutes feed -- the
  backtest is handed realized minutes (props_eval.py:127), so live calibration is optimistic;
  (c) a projected-opponent-SOT model independent of the keeper's own history.

## Calibration / CLV proof plan
- CALIBRATION (done, suggestive): `props_eval --cache` -> bss +0.3365, brier 0.01755, ece 0.004,
  n=662 (pooled player-match-stat, NOT 662 independent obs -- effective n is ~24 matches x ~2
  keepers, heavily correlated). Clears prop_tiering proven bar (bss>=0.05 AND n>=100,
  prop_tiering.py:113). HONEST CAVEAT: the .5-line backtest is near-trivial for keepers, so a
  high bss is expected and is NOT evidence of beatable mispricing.
- TIGHTEN THE CALIBRATION CLAIM (cheap, do first):
  1. Re-run with PROJECTED minutes instead of realized to expose the true live-board error
     (deep-dive 04 plan #5). Likely re-tiers Saves slightly down -- that is honest.
  2. Add a distinct-MATCH count alongside pooled-n in the cache (plan #3); require >= a minimum
     number of matches before "proven", so n=662 cannot be misread as independent.
  3. Score the FULL alt-line ladder (over 1.5 / 2.5 / 3.5 / 4.5), not just the .5 nearest lam --
     the longer rungs are where the NB widen matters and where lazy lines actually live.
- CLV (the real bar, NOT YET STARTED): capture the closing Saves line per keeper into
  `prop_line_history.jsonl` on a cadence up to kickoff (the code exists -- deep-dive 06 sec6
  quick-win 1; this is OPS, not modeling). Then `clv_ledger.compute_clv` (clv_ledger.py:100,
  correct sign: positive = better number than fair close) accrues forward CLV. Saves can only
  become CLV-PROVEN once a meaningful sample of closing lines exists.
- DFS pick'em variant: PrizePicks has no two-way close -> CLV-vs-close undefined; prove via
  P(over) calibration vs realized + realized hit-rate at fixed payout + DFS-line MOVEMENT
  (edge-theory.md note).

## Soft-line target (where the $-hypothesis lives)
The beatable CELL is NOT star keepers on major books (efficient). It is: SAVES on backup /
rotation keepers and minnow-nation keepers, on DFS pick'em, where the line is set off a generic
projection that ignores (a) the opponent's projected SOT volume and (b) that a weaker nation's
keeper faces a high shot floor. Our edge, if any, is on the SHOT-VOLUME projection feeding lam,
not on finishing. HYPOTHESIS until CLV/DFS-movement proves it.

## Honest tier + caveat
- TIER: CALIBRATION-PROVEN (suggestive). $-edge: HYPOTHESIS.
- CAVEAT (binding): the +0.3365 bss is partly a STRUCTURAL artifact of save-count
  determinism + correlated pooled-n on ~24 matches. Treat as "well-calibrated and not worse
  than the close," NEVER as a discovered edge. The single most actionable step is OPS, not
  modeling: capture closing Saves lines so the claim can advance past calibration. Until then,
  Saves is honest decision-support, not a profit engine.
