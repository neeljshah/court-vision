# 04 -- Soccer / World Cup Player-Prop Engine

Deep-dive on the World Cup soccer player-prop vertical: per-90-rate x expected-minutes
-> Poisson/NB count distribution -> p(over line), with ESPN club-season priors, a
leak-free dispersion calibration, an opponent-adjustment lever, MEASURED out-of-sample
calibration tiering, and a paper-only proving loop.

HONESTY RAILS (binding, restated here so the doc cannot drift): markets are efficient;
the only honest win is CALIBRATION, never a dollar edge. Everything below is
paper-only / decision-support. Where a component is thin, in-sample, stranded, or
unvalidated it is flagged as such. No profit/CLV/ROI edge is claimed anywhere.

Scope note: this area is the soccer PLAYER-PROP stack only. The soccer TEAM/scoreline
model (`adapter.py`, `scoreline_engine.py`, `ratings.py`, `predictor.py`, `markets.py`,
the `atlas_*` family, `finishing_*`, `hfa_lambda`, `rho_fit`, `signal_catalog*`) is a
separate vertical and is referenced only where the prop stack consumes it (it does not).

---

## 1. INVENTORY -- components that EXIST and are USED

### Core prop model (domains/soccer/)
- `player_rates.py` -- leak-free, empirical-Bayes-shrunk per-90 rate priors per
  (player, canonical stat). Holds `CANON_TO_COLS` (the 10-stat -> raw-ESPN-column map)
  and the club-prior blend. The spine of the whole stack.
- `player_minutes.py` -- leak-free expected-minutes model (start_prob x ~85' + sub minutes).
- `prop_engine.py` -- assembles lam = per90 x E[min]/90 x opp_mult, builds the
  Poisson/Negative-Binomial count distribution, exposes `p_over(line)` and an alt-line ladder.
- `dispersion.py` -- per-stat Negative-Binomial dispersion index phi = var/mean (leak-free),
  with sensible per-stat priors when the fit is too thin to trust.
- `team_defense.py` -- leak-free per-opponent, per-stat ALLOWED/FOR multipliers (the
  opponent-adjustment lever). Built and wired, but MEASURED null (see section 5).
- `player_resolver.py` -- scraped-name -> roster player_id resolver; biases to
  false-negative (never guesses among 2+ candidates).
- `prop_settle.py` -- settle one prop vs realized post-match ESPN stats (win/loss/push/pending).
- `prop_recal.py` -- per-stat ISOTONIC recalibration (pure-Python PAVA + optional sklearn).
  Built; currently DEFERRED (overfit tell on OOS, see section 5).

### Ingest (knowledge substrate, gitignored output)
- `ingest_espn_players.py` -- keyless ESPN per-player post-match stats -> `espn_player_stats.parquet`
  (the settlement source + WC-history rate substrate).
- `ingest_espn_athlete.py` -- keyless ESPN athlete-OVERVIEW club-season aggregates ->
  `espn_club_priors.parquet` (the "0 -> reliable edges" unlock).

### Convergence + tiering + proving (scripts/platformkit/)
- `prop_edge.py` -- CONVERGENCE: scraped prop lines x our distributions -> ranked,
  tier-labelled board (`build_prop_board`). The public entry point.
- `prop_tiering.py` -- MEASURED-calibration -> evidence tiers (proven/marginal/weak/unmeasured)
  + the honesty-first rank key.
- `props_eval.py` -- leak-free walk-forward calibration backtest + the (p, outcome) pair
  generator + calibration-cache writer.
- `recal_eval.py` -- honest TEMPORAL-split OOS test of the isotonic recalibrator (the DEFER gate).
- `soccer_team_map.py` -- light, safe-no-op opponent-name -> team_abbr resolver for the board.
- `prop_loop.py` -- unattended paper-accrual loop (ingest -> board -> record -> grade -> summarize).
- `prop_paper.py` / `prop_paper_store.py` / `prop_line_history.py` -- append-only paper ledger,
  store, and line-history capture.
- odds providers: `odds_provider/prop_prizepicks.py`, `odds_provider/prop_underdog.py`,
  `odds_provider/prop_base.py` (PropLine + `canon_stat`).

### Data on disk (data/domains/soccer/)
- `espn_player_stats.parquet` -- 1,241 rows, 23 cols, 24 events, **1,241 distinct player_id,
  every player exactly 1 WC match** (the central data limit). Date range 2026-06-11..06-17.
- `espn_club_priors.parquet` -- 8,741 rows, 6 cols, 960 players; 960 of the 1,241 WC players
  have a club prior; 9 outfield stats x 960 players + Saves x 101 keepers.
- `prop_calibration.json` -- MEASURED per-stat bss cache (the tier source); n=662/stat,
  overall n=6,620 (player-match-stat predictions, not matches).
- `prop_recal.json` -- fitted isotonic knots (present but DEFERRED at the board).

### Consumers (frontend + serve)
- `scripts/platformkit/frontend/serve.py` -- `/api/props?sport=soccer_intl` endpoint;
  prefers the snapshot, falls back to `build_prop_board`.
- `scripts/platformkit/frontend/snapshot_writer.py` -- precomputes the board into the snapshot.

---

## 2. HOW IT WORKS -- data flow + key algorithms

### Pipeline
```
ESPN keyless API
   |-- ingest_espn_players.ingest_range()   -> espn_player_stats.parquet  (post-match, 1 row/player/match)
   |-- ingest_espn_athlete.build_club_priors()-> espn_club_priors.parquet (club-season aggregates)
                                  |
player_rates.player_rate()  --(per90, n_eff)-->  prop_engine.prop_distribution()
player_minutes.expected_minutes() --(E[min])-->        |   lam = per90 * E[min]/90 * opp_mult
dispersion.stat_dispersion() ----(phi)-------->        |   model = poisson | negbin(r=lam/(phi-1))
team_defense.opponent_multiplier() -(opp_mult)->       v
                                            p_over(line) callable + alt-line ladder
                                                       |
prop_edge.build_prop_board()  <- scraped PropLines (PrizePicks/Underdog) + player_resolver + soccer_team_map
        |  EV vs soft price (devig) OR gap-from-0.5; prop_tiering tags MEASURED OOS calibration
        v
   ranked board -> snapshot_writer / serve /api/props -> prop_loop (paper accrual) -> prop_paper ledger -> prop_settle (grade)
```

### Key algorithms + signatures (file:line)

**Per-90 rate, leak-free + shrunk** -- `player_rates.player_rate(df, player_id,
stat_canonical, as_of_date, *, position=None, club_prior=None)` (player_rates.py:143).
- Leak guard: `_prior_rows` keeps only `date < as_of_date` (player_rates.py:62-71).
- Raw rate = 90 * sum(stat) / sum(minutes) over the player's prior rows.
- Empirical-Bayes shrink toward a position baseline:
  `shrunk = (n_eff*raw + SHRINK_K*baseline)/(n_eff+SHRINK_K)`, `SHRINK_K=3.0` (player_rates.py:255).
- Club-prior blend path (player_rates.py:203-224): `num = n_wc*wc_per90 + club_w*club_per90`,
  `den = n_wc + club_w`, `club_w = min(starts, CLUB_WEIGHT_CAP=20)`. n_eff = n_wc + club_w;
  a rate is "no-longer-thin" once `n_eff >= CONFIDENCE_N_EFF=5.0`. This is the unlock that
  turns ~1-WC-match players into reliable rates.

**Expected minutes** -- `player_minutes.expected_minutes(df, player_id, as_of_date)`
(player_minutes.py:29). `e_minutes = start_prob*85 + (1-start_prob)*avg_sub_min`; always-started
-> 88; pure sub -> avg sub minutes. No prior history -> status "unknown" (never fabricates a lineup).

**Count distribution** -- `prop_engine.prop_distribution(...)` (prop_engine.py:99).
- `lam = per90 * max(mins,0)/90 * opp` (prop_engine.py:161).
- Poisson pmf via `math.exp(k*log(lam) - lam - lgamma(k+1))` (prop_engine.py:42).
- NB pmf parameterised by (mean, size r), p = r/(r+mean), variance = mean + mean^2/r (prop_engine.py:51).
- `p_over(line) = 1 - sum_{k<=floor(line)} pmf(k)`; half-integer lines never push (prop_engine.py:78).
- Degrades to `{"status":"unknown"}` and never raises.

**Dispersion** -- `dispersion.stat_dispersion(df, stat, as_of_date)` (dispersion.py:129).
- phi = population var/mean of pooled leak-free player-match counts; `_MIN_N=40` rows before a
  fit is trusted, else a per-stat prior phi (`_PRIOR_PHI`, dispersion.py:54). Row-specific size
  `r_for_lam(phi, lam) = lam/(phi-1)` clamped to [1, 50] so NB variance = lam*phi at each row's
  own scale (dispersion.py:180). The board does a two-pass: Poisson to learn lam, then
  re-distribute with r=lam/(phi-1) (prop_edge.py:154-165).

**Opponent multiplier** -- `team_defense.opponent_multiplier(...)` (team_defense.py:193).
- Allowed-attribution: in each 2-team event, team A's total is ALLOWED by team B (team_defense.py:115).
- `ratio = team_allowed / league_baseline`, EB-shrunk toward 1.0 by opponent match count
  (`shrink_k=3`), clamped to [0.5, 2.0]. Special maps: Fouls Drawn <- opponent foulsCommitted;
  Saves <- opponent shotsOnTarget (team_defense.py:72-85).

**Board convergence** -- `prop_edge.build_prop_board(sport, *, as_of, providers, df, lines_source,
priors_path, calibration_path)` (prop_edge.py:229). Per line: `resolve_player` -> `canon_stat`
-> club prior -> opp_mult -> two-pass distribution -> `model_p_over` -> EV-vs-soft-price (devig)
if sportsbook-priced else gap-from-0.5; `apply_tier` attaches MEASURED calibration; `_rank`
sorts via `prop_tiering.calibration_rank_key`.

**Calibration backtest** -- `props_eval.backtest_calibration(...)` (props_eval.py:249) over the
shared leak-free loop `_collect_per_stat_preds` (props_eval.py:127): for each match in date order,
build each player/stat dist from `date < as_of` only, feed REALIZED minutes as `e_minutes` (so
this isolates RATE calibration, not minute-projection error), predict p_over on the .5 line
nearest lam, settle vs realized. `score_prop_predictions` (props_eval.py:57) returns Brier, ECE,
log-loss, sharpness, base-rate, and brier_skill_score (bss vs the empirical base-rate reference).

**Tiering** -- `prop_tiering.classify(stat, calibration)` (prop_tiering.py:113):
"proven" requires `bss >= 0.05 AND n >= 100`; `bss >= 0` -> "marginal"; `bss < 0` -> "weak";
absent -> "unmeasured". `apply_tier` promotes tier to `CALIBRATION_PROVEN` only when
proven AND reliable AND ev_flag ok (prop_tiering.py:137). `calibration_rank_key` buckets proven
above marginal above weak/unmeasured, so a weak-stat row can NEVER outrank a proven-stat row on
raw EV (prop_tiering.py:167).

---

## 3. HOW IT IS USED -- callers / endpoints / loops

- `build_prop_board` is imported by:
  - `frontend/serve.py:58` -> `/api/props?sport=soccer_intl` (serve.py:191-206); prefers the
    precomputed snapshot, falls back to a live build, guarded to never 500.
  - `frontend/snapshot_writer.py:50` -> `_build_props` (snapshot_writer.py:129) computes the board
    once per snapshot so the endpoint is a cheap read.
- `prop_loop.run_tick` (prop_loop.py) is the unattended proving loop: optional realized-stats
  ingest -> `snapshot_writer.write_all` (one board compute) -> record reliable+ev_ok edges to the
  paper ledger -> grade now-final matches via `prop_settle` -> summarize per-stat n/hit/paper_roi.
- `prop_paper` (prop_paper.py) owns the append-only, idempotent paper ledger; default bar is
  `only_reliable=True` (records ZERO when nothing is reliable -- the honest behaviour).
- `props_eval.write_calibration_cache` produces `prop_calibration.json` that `prop_tiering`/
  `prop_edge` read to tier the board. CLI: `python -m scripts.platformkit.props_eval --cache`.
- `prop_recal.fit_recalibrators` writes `prop_recal.json`; `recal_eval.run_eval` is the honesty
  gate that currently keeps it OUT of the live board.
- The stack is also exercised by `scripts/e2e_smoke_test.py` and `scripts/gamenight_e2e_harness.py`.
- Note: the soccer team/scoreline model does NOT feed this stack -- props are wholly per-player.

---

## 4. STRENGTHS -- what is genuinely solid

- **Leak-freeness is enforced at one chokepoint.** Every rate/dispersion/opponent quantity flows
  through `player_rates._prior_rows` (`date < as_of` strict). The backtest reuses the SAME
  pred-gen loop the recalibrator and tier-cache consume, so "what we score" == "what we ship".
- **Degrade-not-fabricate discipline is everywhere.** Every public function returns a status and
  never raises; unknown rate/minutes -> `{"status":"unknown"}` (no fabricated probability); a
  too-tight Poisson is explicitly called out as fabricating tail edges and is widened by leak-free
  NB dispersion. The resolver and team-map both bias to false-negative / no-op rather than guess.
- **The club-priors unlock is real data, not a hack.** Without it, 1-WC-match players shrink almost
  fully to a position baseline and the board produces 0 reliable edges. Blending a capped club
  season (min(starts,20) "matches-worth") is the player's genuine recent form and lifts 960/1,241
  WC players to a non-thin rate. The per_start->per90 approximation is documented as a mild
  over-estimate prior, not a trusted probability.
- **Calibration is MEASURED, not assumed, and the result is honestly negative where it should be.**
  Saves bss=+0.3365 (n=662, brier 0.018, ece 0.004) is genuinely strong; the tier system DEMOTES
  the stats that measured no skill (Shots On Target +0.005, Cards -0.108, Assists -0.074, Goals
  -0.025) instead of hiding them. Overall bss=+0.11 is modest and stated as such.
- **The recal DEFER is the system working.** `recal_eval.run_eval` produced verdict
  "MIXED: recal improves OOS ECE (-0.00115) but NOT Brier (+0.00393) -- defer; In-sample Brier
  delta=-0.00610 vs OOS +0.00393 (gap=+0.01003 is the overfit tell)." It correctly refuses to ship
  a recalibrator that only looks good in-sample on a 4-train/2-test date split.
- **Honesty-first ranking is structural.** `calibration_rank_key` makes it impossible for a
  weak-stat raw-EV blowup to top the board over a proven-stat row.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS (brutally honest)

- **The data is a single round of group games.** 24 events, 1,241 player rows, **every player has
  exactly 1 WC match** (verified). Strict leak-free per-player WC rates therefore barely exist yet:
  early matches are skipped (no prior), and most rates ride the club prior + position baseline.
  Everything downstream inherits this thinness.
- **"n=662 per stat" is NOT 662 independent observations.** It is player-match-stat predictions
  pooled across all players for one stat; the effective independent sample is far smaller
  (matches x players, heavily correlated within a match). The PROVEN_N=100 bar is a guard, but a
  single +0.3 bss stat on ~24 matches should be read as "promising, thin," not "established."
- **Only Saves is genuinely proven; the rest are weak/marginal.** Per the cache: Saves bss +0.337
  (proven). Fouls +0.034, Fouls Drawn +0.026, Shots +0.008, SOT +0.005 are all "marginal" and below
  PROVEN_BSS=0.05. Cards -0.108, Assists -0.074, Goals -0.025, Offsides -0.016, Goal+Assist -0.007
  measured NEGATIVE skill ("weak"). So 9 of 10 markets are NOT shippable as calibrated today.
  Saves itself is the easiest market (a keeper's save count is nearly a deterministic function of
  shots faced) -- the high bss partly reflects that the .5-line backtest is near-trivial for keepers.
- **Opponent-adjustment is a MEASURED null.** `team_defense` is fully built and wired, but the
  cache `mode` is "strict leak-free +opp-adj" with overall bss only +0.11; the lever has not
  demonstrated a calibration improvement and on ~24 matches the per-opponent allowed table is
  itself ~1-3 matches deep, so the multiplier is mostly shrunk back toward 1.0. It is a plumbed
  lever awaiting data, not a validated signal.
- **Isotonic recal is DEFERRED (overfit).** `prop_recal.json` exists but the board does NOT apply
  it -- the OOS Brier worsens (+0.00393) while in-sample improves (-0.00610). MIN_N=150 pairs/stat
  on this data means only a couple of stats even fit. Correctly stranded for now.
- **Backtest feeds REALIZED minutes as e_minutes.** This is deliberate (isolates rate calibration)
  but means the live board carries an UNMEASURED additional error source: `player_minutes` minute
  projection. The reported calibration is optimistic relative to what the live board actually
  prices, because the live path must project minutes (lineup risk, rotation, subs) that the
  backtest is handed for free.
- **`club_priors=True` is "approx as-of" (mild lookahead).** The club-prior parquet is a
  current-season snapshot with a single `as_of`, not a true point-in-time series, so the
  club-augmented calibration mode carries a documented mild lookahead. The cache currently shipped
  is the strict leak-free mode, which is the right call.
- **per_start -> per90 is a biased approximation.** `ingest_espn_athlete` uses `starts` as the
  per-90 denominator (ignores sub appearances), so the club per90 is a mild over-estimate. Fine as
  a prior, but it systematically nudges lam upward for rotation players.
- **Name resolution is the top live-board risk.** A wrong scraped-name match prices book A's line
  against player B's history -> a fabricated edge. The resolver biases to false-negative, which is
  correct, but it is unmeasured how many real edges are silently dropped vs how many slip through.
- **Opponent team-name mapping is a small hard-coded table** (`_NAME_TO_ABBR`, soccer_team_map.py)
  plus a 3-letter-prefix rule; unmapped -> no-op. Safe, but brittle and incomplete across all WC
  nations; many opponent adjustments will silently be 1.0.
- **Dispersion fits ride priors.** With `_MIN_N=40` and only ~1k player-match rows, several stats
  fall back to the per-stat prior phi rather than a real fit; the over-dispersion widths are
  therefore largely assumed, not measured (which is the safe direction, but unvalidated).
- **No CLV capture.** `prop_paper`/`prop_loop` explicitly do NOT compute closing-line value (no
  closing-line snapshot is built). paper_roi is small-N P&L at the taken price -- explicitly NOT a
  $-edge. This is the single biggest gap for ever validating any edge claim honestly.

---

## 6. PLAN TO GET BETTER -- prioritized

### Quick wins (days; mostly data + plumbing, no model risk)
1. **Keep ingesting WC matches and re-running the cache.** The dominant lever is simply more rounds.
   Re-run `props_eval --cache` after each matchday; the strict-leak-free per-player rates only start
   to exist once players have 2+ matches. This is the cheapest improvement and unblocks everything.
2. **Capture closing lines.** Add a closing-line snapshot to `prop_line_history` so `prop_paper` can
   compute CLV-vs-close. Without this, no calibration result can ever graduate to an honest edge
   discussion. Highest-value plumbing add.
3. **Surface effective-N, not pooled-N, in the tier cache.** Add a matches-based / clustered-N
   alongside the pooled n=662 so "proven" cannot be read as 662 independent samples. Tighten the
   PROVEN bar to also require a minimum number of distinct matches.
4. **Expand `_NAME_TO_ABBR`** to the full WC nation set and add a tiny resolver-coverage report
   (how many lines resolved / unresolved / opp-mapped) to the board payload for monitoring.

### Medium (weeks; modeling, all gate-validated)
5. **Validate minute-projection error end-to-end.** Run the backtest with PROJECTED minutes (not
   realized) to measure the true live-board calibration; report the gap. This converts an unmeasured
   risk into a measured one and likely re-tiers some stats downward honestly.
6. **Position-conditioned dispersion + rate baselines.** Split phi and the position baseline by
   finer role (DF/MF/FW/GK already partly available via `position`); keepers vs outfielders clearly
   need separate dispersion. Low risk, gate via `recal_eval`-style OOS.
7. **Re-test the opponent lever as data grows.** Re-run the +opp-adj calibration each matchday; ship
   it only if it improves OOS Brier on >=2 matchdays (currently a null).
8. **Hierarchical / partial-pooling rate model.** Replace the single EB shrink with a proper
   per-stat hierarchical prior (player within position within league) so thin players borrow
   strength more principledly than the current capped linear blend.

### Bigger bets (only worth it if the vertical is a priority)
9. **Minutes model with lineup signal.** The biggest unmeasured error is minutes. Ingest predicted
   lineups / injury news (even coarsely) to sharpen `expected_minutes`; this is where most of the
   live-board error actually lives.
10. **Joint/correlated props (e.g. Shots + SOT, Goal+Assist).** Move from independent marginals to a
    coherent joint (copula or a shared latent shot-volume term) so SOT and Shots and G+A are
    internally consistent; validate on the full stat-pair surface, not just the dominant pair.
11. **Cross-tournament corpus for priors.** Use prior WC / continental / club-league per-90 surfaces
    as a second independent corpus to confirm any per-stat skill out-of-sample before promoting it.

---

## 7. HOW GOOD CAN IT GET -- honest ceiling

**Realistic best:** a WELL-CALIBRATED player-prop board for a handful of high-volume,
near-deterministic markets -- Saves first (already proven), then Shots and Fouls/Fouls-Drawn as
those players accumulate 3-5+ WC matches and the club priors anchor the rest. "Well-calibrated"
means low ECE and a small positive bss vs base-rate on truly out-of-sample matchdays, paired with
honest sharpness. That is a credible, defensible outcome.

**What it is NOT, and the limits:**
- It will NOT beat the closing line. DFS pick'em and soft books are increasingly efficient on
  star-player props; the proven-calibration claim is "our probabilities are honest," never "the line
  is beatable." Any positive paper_roi on ~tens of bets is small-N variance until CLV is captured.
- The hard ceiling on the rare/Bernoulli-ish markets (Cards, Assists, Goals, Offsides, Goal+Assist)
  is information, not modeling: a single match's yellow card or assist is near-irreducible noise, so
  those will likely stay "weak/marginal" no matter how clean the pipeline. The tier system already
  tells the truth about them.
- The binding constraints are, in order: (a) DATA DEPTH (1 WC match/player today; the whole vertical
  is data-starved and gets better mostly by waiting for matchdays); (b) MINUTE-PROJECTION error,
  currently unmeasured because the backtest is handed realized minutes; (c) MARKET EFFICIENCY, which
  caps any dollar claim regardless of calibration quality.

**Bottom line:** with continued ingest + CLV capture + minute-projection validation, this becomes a
genuinely well-calibrated, honestly-tiered prop board where 2-4 markets (led by Saves) carry real
OOS skill and the rest are correctly demoted. That is the ceiling -- a trustworthy calibrated
decision-support product, not a profit engine.
