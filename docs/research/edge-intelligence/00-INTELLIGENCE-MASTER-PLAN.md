# EDGE-INTELLIGENCE MASTER PLAN -- the corpus that makes the system smarter + pushes edge
_Authored 2026-06-18. Blueprint for a large (dozens->hundreds of files) INTELLIGENCE corpus.
The goal is intelligence: deepen knowledge + localize edge in the BEATABLE pockets, and CUT
effort where markets are efficient. ASCII only._

## North star (binding)
INTELLIGENCE is the goal. "Intelligence" here = (a) DATA DEPTH (every usable data point per
sport), (b) CALIBRATED KNOWLEDGE (models + priors that match reality, measured), and
(c) EDGE LOCALIZATION (knowing exactly WHERE the market is beatable vs efficient, and why).
Edge is PROVEN by calibration vs the devigged close + CLV -- NEVER asserted, NEVER a
fabricated $ number. A null/"no-edge-here" finding is a SUCCESS: it tells us where to STOP
spending. "Push the edge" = concentrate effort + data + intelligence on the beatable pockets
and CUT the efficient ones.

## The beatable-pocket thesis (where edge actually is)
Ranked by realistic beatability (concentrate here):
1. SOFT / DFS PLAYER PROPS (PrizePicks/Underdog/soft books) -- lazily priced, high volume,
   per-player distributions we can model. THE primary pocket. (We have WC + MLB prop engines.)
2. LIVE / IN-GAME LAG -- books lag the realized game state; the decisive combinable edge.
3. STALE LINES on slow/soft books; line-shopping + arbitrage (execution edges, model-free).
4. PREDICTION-MARKET vs SPORTSBOOK divergence (Kalshi/Polymarket vs books) -- two crowds.
5. CORRELATED SGPs mispriced by books (joint distribution we can price).
6. NICHE leagues / markets with thin bookmaker attention.

EFFICIENT (CUT / deprioritize -- no durable edge):
- Sharp pregame MAINLINES (h2h/spread/total on major sports at Pinnacle/sharp books).
- NBA PREGAME team markets (at the data ceiling; recency>volume; only AST-prop edge is durable).
- Anything we can only "match the close" on -> keep as calibrated decision-support, stop
  hunting $ there.

## What "everything needed to get to edge in sports" decomposes into (the framework)
For EACH sport we model (NBA, MLB, soccer-club, soccer-intl/World-Cup, tennis), the path to
edge is the same pipeline; the corpus documents + deepens every stage:
  DATA (every source, have vs missing) -> SIGNALS/PRIORS (every lever, ship/reject log) ->
  MODELS (distribution per market, calibrated) -> MARKETS (every prop/line + which are soft) ->
  INEFFICIENCY (the specific beatable pockets + detection recipe) -> PROOF (calibration + CLV)
  -> EXECUTION (scrape + rank + paper -> real only on proven CLV).

## Corpus structure (scales to hundreds of files)
docs/research/edge-intelligence/
  00-INTELLIGENCE-MASTER-PLAN.md            (this)
  _framework/
    edge-theory.md                          (edge defined; CLV; beatable-pocket taxonomy)
    data-to-edge-pipeline.md                (how intelligence files feed models -> edge)
    cut-list-no-edge.md                     (efficient markets to STOP spending on + why)
    proof-standards.md                      (leak-free + calibration + CLV bar; overfit traps)
    intelligence-architecture.md            (how the smart files plug into the predictors/board)
  <sport>/   (one dir each: nba, mlb, soccer_club, soccer_intl, tennis)
    00-edge-map.md                          (beatable vs efficient per market, with evidence)
    data-sources.md                         (every source needed: have / missing / how to get)
    markets-and-props.md                    (every market + prop ladder + which are soft)
    inefficiency-catalog.md                 (specific pockets + how to DETECT each in-data)
    model-levers.md                         (every modeling lever + SHIP/REJECT/PENDING log)
    get-to-edge-plan.md                     (the concrete prioritized path to edge for this sport)
    deep/                                   (the volume: scales to hundreds)
      prop-<stat>.md                        (per prop stat: distribution, drivers, calibration)
      archetype-<name>.md                   (PLAYSTYLES/ARCHETYPES, NOT people -- per the graph rule)
      datasource-<name>.md                  (per source: schema, how to scrape, leak rules)
      inefficiency-<name>.md                (per pocket: detection recipe + proof method)
  _live/        (cross-sport in-game edge intelligence -- the decisive lever)
  _scrapers/    (data-acquisition intelligence: every source + how to acquire it keyless)
  _proof/       (living edge ledger: what's CLV-proven vs calibration-only vs rejected)

## Generation plan (waves of agents; honest, grounded)
WAVE 0 (running): the 12-agent project deep-dive (docs/research/project-deep-dive/) -> the MAP
  of what exists + per-area ceilings + where edge is. Grounds everything below.
WAVE 1: _framework/ (5 files) + per-sport 00-edge-map + get-to-edge-plan (5 sports x 2) -> ~15
  files. Each grounded in the deep-dive + real data + honest edge thesis.
WAVE 2: per-sport data-sources + markets-and-props + inefficiency-catalog + model-levers
  (5 x 4) -> ~20 files. Catalog every data source, market, pocket, lever per sport.
WAVE 3+: the deep/ files -- per-prop-stat, per-archetype (playstyle not people), per-datasource,
  per-inefficiency -- generated in batches until the corpus is comprehensive (-> hundreds).
  Each deep file must be GROUNDED (cite data/code/real numbers) and HONEST (flag thin/overfit;
  label edge as proven/calibration-only/hypothesis).
Concurrency: serialize the big fleets (deep-dive THEN corpus waves) to avoid API-529 overload;
the paper accrual loop keeps running in the background throughout.

## Honesty guardrails for the whole corpus (binding)
- No fabricated $-edge anywhere. Edge claims carry an evidence tier: HYPOTHESIS ->
  CALIBRATION-PROVEN (OOS Brier/BSS) -> CLV-PROVEN (forward, paper). Most start as HYPOTHESIS.
- Every "lever" gets a SHIP/REJECT/PENDING verdict from the real leak-free gate before it's
  trusted; single-fold/in-sample lifts are artifacts (record them as rejected).
- "Cut where no edge" is first-class: cut-list-no-edge.md and each edge-map must say plainly
  where we should STOP, so effort flows to the beatable pockets.
- Playstyles/archetypes/schemes, NOT people, in any graph/archetype intelligence.
- Local-only; never push; ASCII; leak-free; per-file tests for any code the corpus motivates.
