# soccer_intl -- INEFFICIENCY CATALOG (beatable pockets + detection recipe + proof method)

_Part of the edge-intelligence corpus. The specific beatable pockets for WC / international soccer,
each with a DETECTION recipe (how to find it in-data) and the PROOF method (calibration / CLV).
All pockets are HYPOTHESIS-tier unless tagged otherwise. Markets are mostly efficient; these are
the cracks worth probing, with the honest bar from proof-standards.md. ASCII only._

## Pocket S1 -- Saves x low-attention keeper (the only proven-anchored pocket)
- **Thesis:** Saves is the one CALIBRATION-PROVEN stat (bss +0.3365, brier 0.018, ece 0.004,
  prop_calibration.json). Crossed with backup/rotation or minnow-nation keepers (low bookmaker /
  DFS attention), a well-projected save distribution can diverge from a lazily-set line.
- **Detection recipe:** for each offered Saves line, build the distribution
  (`prop_engine.prop_distribution`), compute |model_p_over - implied_p|; flag rows where the keeper's
  team is a heavy underdog (high opponent shot volume -> high lam) OR the keeper is a non-first-choice
  (rotation) where the DFS projection likely used a generic prior. Cross with
  `team_defense.opponent_multiplier` Saves<-opponent shotsOnTarget map (team_defense.py:72-85).
- **Proof method:** P(over) calibration vs realized (already +0.3365) -> then CLV/DFS-movement.
  CAVEAT (proof-standards thin-data trap): the high bss is partly STRUCTURAL (saves ~ shots faced
  given minutes), so the proof MUST be CLV-vs-close / DFS-movement, not just re-confirming the
  near-trivial .5-line calibration. Tier stays CALIBRATION-PROVEN until CLV exists.

## Pocket S2 -- Fouls / Fouls-Drawn role-player rate (graduate-candidate)
- **Thesis:** Fouls (+0.0339) and Fouls Drawn (+0.026) are positive-bss, high-volume, role-stable
  (a CDM's foul rate or a dribbling winger's drawn-foul rate is one of the more predictable soccer
  quantities). Marginal today only because of thin N.
- **Detection recipe:** rank players by stability of leak-free foul per-90 across their prior rows
  (low CV) AND high `n_eff` (club-prior-backed, n_eff >= CONFIDENCE_N_EFF=5, player_rates.py:32);
  flag offered lines where model_p_over diverges from implied for these stable role players.
- **Proof method:** the cheapest pocket to PROVE -- it just needs N. Re-run `props_eval --cache`
  after each matchday; promote to proven when bss>=0.05 AND distinct-match N is adequate (NOT just
  662 correlated player-rows -- proof-standards #4 / 06 sec 6 #4). >=2 matchdays must agree.

## Pocket S3 -- Lineup-freshness mispricing (the live/freshness crack -- P2)
- **Thesis:** the dominant unmodeled fact is WHO STARTS and FOR HOW LONG. A confirmed lineup posted
  ~60 min before kickoff is information the model's 1-prior-match minutes estimate cannot see, and
  that slow books / fixed DFS lines may also lag. A star rested or a surprise starter mis-prices
  every prop for that player.
- **Detection recipe:** compare `player_minutes.expected_minutes` (player_minutes.py:29, projected
  from priors) against the confirmed XI once ingested; flag players where projected start_prob
  disagrees with the actual lineup (surprise start = lam too low; surprise bench = lam should be ~0).
  Requires the MISSING predicted-lineups source (data-sources.md). Until then this pocket is
  undetectable.
- **Proof method:** CLV vs the line just before lineup release vs just after; and P(over) calibration
  conditioned on "lineup-confirmed" rows. This is the highest-ceiling pocket but BLOCKED on data.

## Pocket S4 -- DFS pick'em structural rigidity (P1 / structural)
- **Thesis:** PrizePicks/Underdog cannot move a fixed-payout pick'em line to kill a genuine
  mispricing (edge-theory.md STRUCTURAL crack). On a proven-calibration stat (Saves, eventually
  Fouls), a persistently divergent projection is a candidate edge.
- **Detection recipe:** scrape PrizePicks + Underdog (prop_prizepicks.py / prop_underdog.py), join
  to our distribution, restrict to proven/marginal stats only (calibration_rank_key already enforces
  this ordering, prop_tiering.py:167), and log each scrape to a movement series. A line that stays
  put while realized rates drift is the structural signal.
- **Proof method:** DFS has NO two-way close -> prove via P(over) calibration vs realized + realized
  ROI at the fixed payout + DFS-LINE MOVEMENT (edge-theory.md note). Requires the MISSING movement
  log. Quarantine these in the paper ledger (prop_paper only_reliable=True default) until proven.

## Pocket S5 -- Correlated SGP / joint props (P5 -- unbuilt)
- **Thesis:** books price Shots, SOT, and Goal+Assist legs independently; the true joint
  distribution (a shared latent shot-volume term drives all three) is correlated. A correctly priced
  joint can beat the product-of-marginals the book implies.
- **Detection recipe:** estimate the empirical correlation of (Shots, SOT) and (Goals, Assists)
  per-position on espn_player_stats.parquet; where the book's implied SGP price = product-of-legs but
  our copula/shared-latent price differs, flag.
- **Proof method:** NONE today -- the engine emits independent marginals only (markets-and-props.md
  gap; 04 sec 6 #10). This is a BIGGER BET; validate on the FULL stat-pair surface, not just the
  dominant pair (retro full-surface lesson, MEMORY). HYPOTHESIS, unbuilt.

## Pocket S6 -- per_start->per90 lam bias (a correctable model error, NOT a market crack)
- **Thesis (anti-pocket / risk):** `ingest_espn_athlete` uses starts (not total appearances) as the
  per-90 denominator -> club per90 is a mild OVER-estimate, nudging lam up for rotation players
  (04 sec 5). This manufactures fake OVER edges, the classic too-tight/biased-prior trap
  (proof-standards overfit traps).
- **Detection recipe:** flag rows where the club-prior weight dominates n_eff AND the player is a
  rotation (low start_prob) -- those OVER edges are suspect.
- **Proof method:** fix the denominator (use appearances) and re-measure; this is a model-correctness
  fix, expected to REMOVE spurious edges, not add real ones. A null/negative result here is the win.

## Cross-cutting detection: name-resolution false edges (the top live-board risk)
Every pocket above is contaminated if `player_resolver.resolve_player` mis-matches a scraped name
to the wrong player_id -> book A's line priced against player B's history = a fabricated edge
(04 sec 5). The resolver biases to false-negative (never guesses among 2+ candidates), which is
correct, but coverage is unmeasured. DETECTION: add a resolver-coverage report (resolved /
unresolved / opp-mapped counts) to the board payload (04 sec 6 #4) and treat any edge on an
unresolved-adjacent name as untrusted.
