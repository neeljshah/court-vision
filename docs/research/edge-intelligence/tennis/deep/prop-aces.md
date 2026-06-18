# tennis PROP PUSH-PLAYBOOK -- ACES O/U (player)

_Deep/actionable layer of the edge-intelligence corpus. Sport = tennis. The single most
promising soft prop in tennis -- BUILDABLE from match_stats but BLOCKED by no tennis prop feed.
Grounded in data/domains/tennis/match_stats.parquet (VERIFIED 59,312 rows), domains/tennis/
markets.py + repricer.py, the tennis edge-map + markets-and-props, deep-dive 11. ASCII.
No fabricated $-edge; tier-tagged throughout._

## One-line verdict
The ingredients for a genuine ace-rate model are ON DISK (p1_ace, svpt, 1stIn, SvGms, ace_rate,
surface), and ace lines on DFS/soft books are notoriously lazy (flat across opponents +
surfaces). This is the highest-upside tennis prop. BUT: no ace LINE is scraped and no ace MODEL
is wired. Tier: HYPOTHESIS, double-BLOCKED (need a scraper AND a model). Pregame match-win is
CUT as efficient (Elo trails Pinnacle by Brier +0.0149) -- aces is where a real PRICING edge
could live precisely because it is a soft, structural, low-attention market.

## The model to BUILD (not yet wired)
aces ~ NegBinom( mean = serve_points_faced * ace_rate, dispersion phi ). VERIFIED on disk:
- ace_rate (aces per serve point): `p1_ace_rate` mean 0.0603, std 0.0578 (highly player-variable
  -> a real per-player signal, not league-flat).
- serve volume: `p1_svpt` mean 75.7, `p1_SvGms` mean 11.6 per match -> the count scaffold.
- DISPERSION IS THE TRAP: `p1_ace` var/mean = 5.21 (heavily OVERDISPERSED). A Poisson on
  lam~4.6 would invent absurdly thin tails and fabricate over-9.5/over-11.5 edge (the
  too-tight-distribution trap, proof-standards.md). NB is MANDATORY: r = mean/(phi-1), the same
  two-pass widen the soccer/MLB engines already use (prop_edge.py:154-165). Median aces 3,
  p90 11 -> the upper ladder rungs are exactly where lazy flat lines and our NB width interact.
- Reuse, don't rebuild: the soccer/MLB prop stack (per-rate x expected-volume -> NB count ->
  p_over + alt ladder) is sport-blind in shape; an ace model is the SAME pattern with
  ace_rate x projected_serve_points as lam.

## Drivers (rate-only, ARCHETYPE not people)
1. SERVER ACE RATE (dominant, player-specific): the "big-serve" archetype (tall, flat-first-serve
   bomber) vs the "counterpuncher / grinder" archetype have structurally different ace_rate.
   Describe by SERVE ARCHETYPE, never by name. ace_rate std 0.058 on a 0.060 mean confirms this
   is a strong, persistent signal -- the core of any edge.
2. SURFACE (large, and what lazy lines IGNORE): fast/low-bounce (grass, indoor hard) inflates
   aces; slow/high-bounce (clay) suppresses them. `surface` is available to condition on. A flat
   DFS ace line that ignores surface is the textbook soft-line crack.
3. OPPONENT RETURN DEPTH (return archetype): a strong-return opponent suppresses aces; books
   often ignore this entirely. The return side is derivable from the opponent's served-against
   stats. The biggest model-vs-lazy-line gap.
4. SERVE VOLUME / MATCH LENGTH: more serve points (bo5, long matches, server who gets broken less)
   -> more aces. Projected serve points = SvGms * points-per-serve-game, conditioned on the
   match-win/sets distribution the existing engine already produces.
5. MINUTES analog = expected number of serve games, which depends on the match going 2 vs 3 sets
   (bo3) -- couple lam to the existing set distribution (markets.py straight_sets 0.594).

## Data
- HAVE (VERIFIED): match_stats.parquet -- p1_ace/p2_ace (mean 4.61), p1_svpt, p1_1stIn,
  p1_SvGms, p1_ace_rate, p1_df_rate, surface, both players' serve+return columns; 59,312 rows.
  Enough to fit a leak-free per-player surface-adjusted ace-rate model with real history.
- MISSING (the two blockers): (1) NO ace LINE -- odds.parquet is match-winner two-way only
  (psw/psl/maxw/l), so there is nothing to price against or to compute CLV from; (2) NO ace
  MODEL is wired into the predictor/board. Also missing: a live serve feed for in-game ace props.

## Calibration / CLV proof plan
- STEP 0 (model, leak-free, BEFORE any line): build the NB ace model; backtest it walk-forward
  on match_stats (train on matches strictly before each test match, surface-conditioned),
  scoring p_over at the typical posted line nearest lam. Metric: Brier + ECE + Brier-Skill-Score
  vs a base-rate-of-over reference, plus realized COVERAGE of the NB intervals (catch the
  too-tight trap). Require >=2 independent splits / surfaces agree (proof-standards.md rule 4).
  This earns CALIBRATION-PROVEN status for the MODEL even with zero lines.
- STEP 1 (line capture -- the unblock): add an ace-prop scraper to odds_provider/ (PrizePicks
  pick'em or Underdog two-way), mirroring the existing prop_prizepicks/prop_underdog providers.
  PrizePicks pick'em -> edge_basis model_view, prove via P(over) calibration + fixed-payout
  hit-rate + DFS-line MOVEMENT (CLV-vs-close undefined). Underdog two-way -> devig (shin.py) +
  EV both sides + true forward CLV via clv_ledger.
- STEP 2 (CLV): once lines accrue, forward CLV is the bar for real money. None exists today
  (tennis paper_book is empty -- deep-dive 06: 0 settled rows carry a real CLV system-wide).

## Soft-line target (the $-hypothesis cell)
Ace O/U on ATP-250 / Challenger / WTA-lower-tier matches (low bookmaker attention, P6 + P1) and
on DFS pick'em where the ace line is set FLAT across opponent and surface. Our edge, if any, is
the surface + opponent-return + serve-volume conditioning the lazy line omits. HYPOTHESIS until
both blockers clear and a leak-free backtest + forward line-movement prove it.

## Honest tier + caveat
- TIER: HYPOTHESIS, double-BLOCKED (scraper + model both unbuilt).
- CAVEAT: this is the most promising tennis prop ON PAPER, but "promising" is not "proven."
  Order of work is fixed: build + leak-free-backtest the NB ace MODEL first (it can reach
  CALIBRATION-PROVEN with on-disk data alone), THEN add a line scraper, THEN accrue CLV. Do NOT
  price aces live or claim any edge until the model clears the gate; and never use Poisson (the
  5.2 var/mean overdispersion will fabricate tail edges). Pregame match-win stays CUT regardless.
