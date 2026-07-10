# CourtVision -- a multi-sport prediction + decision-support AI with deep per-player intelligence

**One calibrated AI brain that, across five sports, prices every market from a single coherent
engine, drills all the way down to per-player prop distributions, reprices live as the game
unfolds, and hunts for edge in the soft pockets where it can actually exist -- proving every
claim leak-free and refusing to fabricate a dollar edge it has not earned.**

It is *wide*: NBA, MLB, club soccer, the World Cup, and tennis, every one of them speaking the
same `predict / to_jd / predict_live` interface, every market (moneyline, totals, spreads, 1X2,
BTTS, correct-score, player props, alt-line ladders, same-game-parlays) priced off one
calibrated anchor. It is *deep*: under each team number sits a per-player projected
distribution, a ~190-feature prop stack, 44 player/team "atlases", playstyle archetypes, a
coherent possession-level Monte-Carlo simulator, and a ~100-file edge-intelligence corpus that
catalogs -- per sport -- every data source, every market, every beatable pocket, and every
modeling lever with an honest ship/reject verdict. And it is *honest*: the pregame number
MATCHES the devigged closing line within noise on efficient markets (a success, not a target to
beat), in-game conditioning is a measured calibration win 4/4 sports, and **no dollar edge, ROI,
or "beat the close" is ever claimed** -- candidate edges are surfaced, tiered by evidence, and
only ever proven by forward closing-line value (CLV), never asserted.

Built by **[Neel Shah](https://neelshahportfolio.netlify.app)** -- solo human architect and
director of an agentic build pipeline. Engineering judgment, ship/reject decisions, and the
validation methodology are mine. Open to **ML / data / quant / founding-engineer** roles ->
[neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

---

## Explore the whole system, link by link

This README is the front door. **[docs/INDEX.md](docs/INDEX.md) is the full map** -- every tracked
document, organized by role and by funnel stage, so you can follow links from the raw data feeds
all the way through the models, the simulator, the calibration gates, line-shopping and execution,
the live in-game repricer, and the autonomous self-improvement loop. It is deep on purpose: a
thorough read is a multi-day tour.

- **New here?** -> [docs/INDEX.md](docs/INDEX.md) (the map) and the [GLOSSARY](docs/GLOSSARY.md)
  (CLV, leak-free, walk-forward, Shin devig, Brier, Kelly, ...)
- **Want the honest numbers first?** -> [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)
- **Want the guided tour?** -> [docs/research/project-deep-dive/00-MASTER.md](docs/research/project-deep-dive/00-MASTER.md)
  (13-chapter end-to-end walkthrough)
- **How AI built it?** -> [docs/BUILT_WITH_CLAUDE.md](docs/BUILT_WITH_CLAUDE.md)

**Deep-dive layer (new)** -> [DAEMONS](docs/DAEMONS.md) - [PLATFORM_HARNESS](docs/PLATFORM_HARNESS.md) -
[PAPER_TRADING_STACK](docs/PAPER_TRADING_STACK.md) - [INGEST_PIPELINES](docs/INGEST_PIPELINES.md) -
[DATA_DEPTH](docs/DATA_DEPTH.md) - [ASK_SURFACES](docs/ASK_SURFACES.md) -
[SPORTS_COVERAGE](docs/SPORTS_COVERAGE.md). The system's depth is now documented subsystem by
subsystem, not just at the funnel-stage level above.

---

## How the whole brain works together

Everything is one funnel, and every stage feeds the next. A model change in one place
propagates coherently to every market through a single seam.

```
  DATA            keyless, leak-free ingest across 5 sports (ESPN, MLB StatsAPI, Sackmann,
   |              football-data, prediction markets, DFS prop feeds) -> as-of-stamped parquet
   v
  SIGNALS         leak-safe per-entity features + priors: team ratings (MOV-Elo / EW-Poisson /
   |              surface-Elo / serve-hold), per-player per-exposure rates, 44 atlases, archetypes
   v
  MODELS          one CALIBRATED win-probability per sport (the anchor) + per-player count
   |              distributions (Poisson / Negative-Binomial, dispersion-calibrated)
   v
  ENGINES         JointDistribution (coherent score matrix) + the possession Monte-Carlo sim
   |              (emergent teammate correlation) + the live repricer (conditions on realized state)
   v
  PREDICTIONS     ONE seam -> the full market surface: ML / totals / spreads / 1X2 / BTTS /
   |              correct-score / player-prop ladders / SGP -- pregame and in-game, coherent
   v
  INTELLIGENCE    the edge-intelligence corpus + the proving spine: every candidate edge tiered
                  hypothesis -> calibration-proven -> CLV-proven; cut where markets are efficient
```

The cohesion is the point: **one win-probability anchors the moneyline, the spread, the total,
and the in-game reprice** -- they are coherent reads off the same engine, not four independent
models that can disagree. Pregame and in-game agree at tip-off by construction. Adding a sport
is an adapter, not a kernel rewrite; adding a market is a read off the same anchor.

---

## What it predicts

| Sport      | Pregame market surface                               | Per-player props                          | In-game reprice            |
|------------|------------------------------------------------------|-------------------------------------------|----------------------------|
| NBA        | moneyline, total, spread/margin                      | pts/reb/ast/3pm/stl/blk + PRA + DD + SGP  | end of Q1 / Q2 / Q3        |
| MLB        | moneyline, run-line, total                           | K / hits / TB / walks / outs / ER ...     | after inning 3 / 5 / 7     |
| Club soccer| 1X2, O/U-2.5, BTTS, correct-score, Asian handicap    | shots / SOT / fouls / cards / saves ...   | half-time                  |
| World Cup  | 1X2 (neutral-site), O/U-2.5, BTTS, correct-score     | shots / SOT / fouls / fouls-drawn / saves | live minute-by-minute      |
| Tennis     | match-win, games O/U, sets, holds                    | (aces buildable; feed-gated)              | after set 1                |

Every output is a calibrated probability or a point forecast with dispersion -- never a
recommended wager. The buyer-facing CLI stamps `"edge_claimed": false` on every response.

**NBA 2025-26 season coverage.** `games.parquet` carries all 1,156 scheduled games of the
2025-26 season; per-player boxscores now cover the FULL season -- 74 games from the original
quarter-level cache plus 1,082 games backfilled from ESPN full-game summaries into the same
`quarter_box` cache the pipeline already reads (q0 = full-game totals, q1-q4 = real quarters,
zero downstream transform changes). The season's canonical shooter leaderboard claim is
produced and independently VERIFIED on this corpus.

**Ask it what kind of shooter someone is.** Not a ranking -- a ten-axis trait vector
(volume/efficiency/difficulty/gravity/context), each axis citing its own VERIFIED claim, never
combined into one score:

```bash
python -m scripts.platformkit.intel_query.ask "what kind of shooter is Stephen Curry"
# or directly:
python -m scripts.platformkit.intel_query.compose_profile "Luka Doncic"
```

**Ask how the paper book is doing.** Streamed off the live paper ledger (never whole-file
loaded), every answer paired with its channel's fail-closed greenlight verdict so a units figure
never appears without its gate status:

```bash
python -m scripts.platformkit.intel_query.paper_analytics "this week by channel"
python -m scripts.platformkit.intel_query.paper_analytics "settlement backlog"
```

---

## Wide in knowledge -- and it knows every little detail

**Breadth (wide).** Five domains share one interface and one validation gate, so the brain
reasons about a Premier-League match, a World-Cup neutral-site game, an MLB pitching matchup, an
ATP set, and an NBA quarter with the same machinery. A keyless, free, idempotent, leak-free data
backbone refreshes all five (~93 MB of as-of parquet) -- MLB StatsAPI boxscores, ESPN
per-player rosters + athlete season splits, Sackmann tennis, football-data, plus prediction
markets (Kalshi / Polymarket) and DFS prop feeds (Underdog / PrizePicks). The opportunity surface
is bounded by data breadth, not by model breadth: the same pure best-line / Shin-devig / EV /
arbitrage core covers *every* event the feeds return.

**The claims scale.** Every derived stat the brain will answer a question from first has to pass
an independent validator that marks it `VERIFIED`, `MISMATCH`, or `UNVERIFIABLE` -- **52,379
VERIFIED claim rows** stand behind the ask surfaces today, tallied live from every
`*_validation.json` summary under `data/cache/intel_claims/` (33 claim stores, 7 sports). A
machine-readable **data census** (`data/frontend/ops/data_census.json`) inventories what's
derivable from the corpus on disk per sport -- 61 derivable families across NBA, MLB, soccer,
soccer_intl, tennis, WNBA, NPB, KBO, and cross-sport markets -- and ranks every still-`UNBUILT`
one by `leverage_rank` into a single cross-sport priority queue the autoloop reads to decide what
to build next. The full per-sport breakdown (data on disk, claim counts, biggest gap, model vs
close verdict) lives in [docs/SPORTS_COVERAGE.md](docs/SPORTS_COVERAGE.md).

**Depth (every little detail).** Under each team number the brain goes all the way down:

- **Per-player projected distributions.** Not a point estimate -- a full count distribution per
  player per stat (per-exposure rate x expected exposure -> Poisson/Negative-Binomial), so it
  prices the *entire* alt-line ladder ("over 0.5 / 1.5 / 2.5 ... shots", "10 vs 30 points") and
  the joint structure behind a same-game parlay, not just one line.
- **A ~190-feature NBA prop stack** (rolling form, opponent defense, pace, rest/B2B, shot-zone
  tendencies, on/off, synergy play-type PPP, referee tendencies, schedule hardship, ...), with
  23 feature blocks each annotated with the leak-free walk-forward result that killed or kept it.
- **44 "atlases"** (28 player + 16 team: usage role, pace fit, matchup splits, vs-scheme splits,
  rest/B2B splits, spacing gravity, clutch shape, foul-drawing, ...) -- a deep descriptive +
  correlation asset.
- **Playstyle archetypes, never people** -- striker / winger / holding-mid / keeper; power-hitter
  / contact-hitter / strikeout-pitcher; high-usage creator / 3-and-D wing / rim-runner;
  big-server / grinder / returner -- so the shrinkage prior knows what a *role* typically does.
- **A coherent possession Monte-Carlo simulator** whose teammate correlation EMERGES correct from
  a shared scoring pie (measured rho ~ -0.10 vs realized) instead of a hand-tuned matrix -- one
  ~3-4s GPU run prices the whole prop / combo / SGP surface coherently. This is the one thing a
  marginal prop model structurally cannot do.

---

## Player props + the edge hunt (honest)

The deepest, most actionable part of the brain is the **player-prop engine**, and it is where the
search for *genuine* edge concentrates -- precisely because that is where edge can plausibly
exist.

**The thesis (load-bearing).** Sharp mainline markets (moneyline / spread / total on liquid
sports) are efficient -- the brain MATCHES the devigged close and claims nothing more. The
*beatable* pockets are different in kind: **lazily-priced soft / DFS player props**, **live /
in-game lag**, **stale lines on slow books**, **prediction-market vs sportsbook divergence**, and
**correlated SGPs a coherent sim can price but a book misprices**. The brain is built to surface
and paper-trade exactly those -- and to *cut* effort where it has proven there is no edge.

**How a prop edge is found, end to end:** scrape the soft DFS / book line -> build the player's
full distribution from leak-free history (empirical-Bayes shrunk to the role archetype, blended
with a club-season prior) -> price every rung of the ladder -> compare to the offered line ->
rank by EV -- and then **label it by evidence tier and prove it before trusting it**:

- **HYPOTHESIS** -- a plausible mispricing, not yet measured (most candidates start here).
- **CALIBRATION-PROVEN** -- the model's P(over) is sharper than the line out-of-sample, leak-free
  (Brier-skill-score > 0). *Genuine, claimable.*
- **CLV-PROVEN** -- forward closing-line value accrues on paper at meaningful sample size. *The bar
  for real money -- and the only thing that ever justifies a dollar claim.*

A too-tight distribution would fabricate fake edges, so the brain calibrates dispersion (NB where
counts are over-dispersed), demotes any stat it has *measured* to be weak, and ranks proven-stat
edges above raw-EV blowups in unproven stats. The honest current state: in-game conditioning is
calibration-proven 4/4 sports; goalkeeper Saves is calibration-proven; most prop candidates are
HYPOTHESES awaiting CLV. **Paper-only; no dollar edge is claimed anywhere.** That discipline is
the product -- an instrument that hunts edge *and* tells you, truthfully, which of its findings
are real.

---

## The deep-intelligence layer

Beyond the models sits a living **edge-intelligence corpus** (~100 markdown + structured files)
that makes the breadth and depth navigable and actionable -- the brain's own map of where to
push and where to stop:

- **Per sport:** an edge-map (every market tagged beatable vs efficient, with evidence), a
  data-source ledger (have / missing / how-to-acquire), the full market + prop surface, an
  inefficiency catalog (each pocket with an in-data detection recipe + a proof method), a
  model-lever ledger (every lever with a SHIP / REJECT / PENDING verdict), and a prioritized
  path-to-edge.
- **Cross-cutting:** edge theory + the cut-list of efficient markets to stop spending on, proof
  standards (the leak-free / OOS / CLV bar and the overfit traps that fake edges), per-source
  scrape specs, per-inefficiency detection recipes, a reusable method library
  (Poisson-vs-NegBinom, empirical-Bayes shrinkage, Shin devig, isotonic-when, Kelly + correlation
  sizing, CLV computation, walk-forward leak guards), and a single living edge-ledger of every
  candidate's evidence tier.

Honest scope: the descriptive/atlas intelligence is a deep *scouting + correlation* asset and a
predict-time-input the funnel is still wiring in (measured point-accuracy lift on the served
model is ~0 today and is reported as such, not oversold). The corpus's value is making the entire
search for edge systematic, grounded, and honest. See
[docs/research/edge-intelligence/README.md](docs/research/edge-intelligence/README.md).

---

## The loop runs itself -- autonomy layer + the answer-engine oracle

Beyond the discovery loop (mine residuals -> validate behind the ship gate -> ship or
reject) sit the two autonomy stages that used to need a human: **self-shadowing**
forward-settles the loop's own not-yet-confirmed verdicts against real outcomes as they
land, and **self-proposal** generates and gates new hypotheses on a schedule with zero
LLM calls and zero human trigger. A **sentinel layer** watches the watchers -- disk
pressure, exception bursts, stalled heartbeats, tamper-evidence hashes on the
invariant-enforcing code itself -- and a **one-command system-liveness harness**
composes every gate/sentinel/ledger into a single readout that refuses to paper over a
down section: a live run this week correctly reported `OVERALL: RED` with the specific
failing subsystem named (a stale scraper heartbeat, 8 census-drift entries), not a
decorative green.

On top of the funnel sits an **answer-engine oracle**: a "what affects what" **effect
graph** (555 nodes / 296 edges across NBA, MLB, soccer, and tennis) built entirely from
rows the knowledge engine already adjudicated -- zero new statistics computed, only
labeled and linked -- plus a **resolver registry** that maps every supported question
type to exactly one deterministic source and REFUSES anything unregistered rather than
improvising a plausible-sounding answer. The knowledge engine itself is now fully
drained across all 4 sports: 151 mechanism hypotheses closed out (71 CONFIRMED_LOCAL, 51
honest NULLs, the rest not locally testable) -- every "does X actually happen" question
the oracle fields carries a verdict, sample size, p-value, and source file, not folklore.
Full account: [docs/PRODUCT_DEMO.md](docs/PRODUCT_DEMO.md).

---

## The thesis in numbers (calibration / sharpness -- NEVER a dollar edge)

### Pregame -- vs the devigged closing line, leak-free OOS

Lower Brier / RMSE is sharper. MATCH = within sampling noise of the sharp close. BEHIND = the
market's injury / lineup / weather / park / starting-pitcher freshness a public + box-score model
cannot see. Source: `vault/_Edge_Maps/_Beat_The_Close.md`, reproduced below verbatim from a live
`scripts.platformkit.beat_the_close_scoreboard` run against the real corpora; full framing +
the candidate-REJECT table in [docs/MARKET_EFFICIENCY_PROOF.md](docs/MARKET_EFFICIENCY_PROOF.md).

| Sport / market    | Our model     | Close   | Verdict                          |
|-------------------|---------------|---------|----------------------------------|
| NBA moneyline     | Brier 0.1735  | 0.1672  | MATCH (within noise)             |
| NBA total O/U     | RMSE  19.17   | 18.11   | BEHIND (injury/lineup freshness) |
| MLB moneyline     | Brier 0.2429  | 0.2390  | MATCH (tiny pitcher-blindness)   |
| MLB total O/U     | RMSE  4.72    | 4.44    | BEHIND (park/weather/SP)         |
| Soccer O/U-2.5    | Brier 0.2465  | 0.2390  | MATCH (pooled Platt)             |
| Tennis ATP ml     | Brier 0.2177  | 0.2028  | BEHIND (ATP closes very tight)   |

### In-game -- conditioning on the realized state beats the static pregame line. All 4 WIN.

A live book also sees the state, so this is forecaster QUALITY, not a dollar edge.
Source: `vault/_Edge_Maps/_Ingame_Scoreboard.md`.

| Sport  | Static -> Conditional Brier             | When                                |
|--------|-----------------------------------------|-------------------------------------|
| NBA    | 0.209 -> 0.159                          | end Q1/Q2/Q3 (rating prior + score) |
| MLB    | 0.241 -> 0.126                          | after inning 3/5/7                  |
| Soccer | 1X2 0.626 -> 0.502; O/U 0.264 -> 0.176  | half-time                           |
| Tennis | 0.219 -> 0.151                          | after set 1 (leak-free leader)      |

**Reading it.** Pregame MATCHES the devigged close on team-strength win markets and is BEHIND on
totals / ATP only by freshness data the market sees and we cannot -- a data-bound gap, not a model
defect. The sharpest forecaster FUSES the pregame intelligence prior with the realized state. We
never claim a dollar edge, an ROI, or beating the close.

---

## Run it in minutes

Slim install -- the predictor needs only a small scientific-Python surface (numpy, pandas,
pyarrow, scipy, scikit-learn). The heavy CV / web / daemon dependencies are NOT required.

```bash
pip install -r requirements-predictor.txt      # or:  pip install -e .  -> cv-matchup / cv-predict / cv-live
```

### One matchup -- pregame + in-game in a single JSON read

```bash
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
    --elapsed 0 --home-score 0 --away-score 0
```

```json
{
  "sport": "nba", "home": "BOS", "away": "LAL",
  "edge_claimed": false,
  "framing": "Pregame MATCHES the devigged close (calibration/sharpness, not an edge); in-game ADDS the realized state. No $ edge.",
  "pregame": { "p_home_win": 0.605, "total_mean": 211.3, "margin_home": 3.0 },
  "ingame":  { "p_home_win": 0.5732, "pregame_p_home": 0.605, "proj_total": 211.3, "proj_margin_home": 4.4 }
}
```

Swap `--sport` for `mlb`, `soccer`, `soccer_intl`, or `tennis`. Reproduce the leak-free scoreboards
on committed fixtures in under 60s on a fresh clone:

```bash
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
python -m scripts.platformkit.ingame_scoreboard        --corpus tests/fixtures/proof
```

---

## Why trust it -- the rigor IS the product

- **Leak-free by construction.** Expanding-window walk-forward with assertion-level per-fold leak
  guards, purge + embargo, and truncation-invariance tests (a feature at time T is byte-identical
  with or without future events). Cluster-robust Diebold-Mariano significance. The close is a
  comparison forecaster, never a model input.
- **Honest nulls are successes.** "BEHIND by freshness", "MATCH within noise", "this lever is a
  measured NULL", "this recalibration OVERFITS out-of-sample -> deferred" -- all stated plainly.
  An efficient market proven efficient is a headline result, not buried.
- **It disproves its own hype.** The same harnesses that grade the market were pointed inward and
  retired a market-follow ROI artifact, a Q4 look-ahead leak, and an L5-proxy ceiling mislabeled
  as edge. Building the instrument that refutes your own claims is the strongest signal here.
- **A units number is never shown without its gate.** The paper-execution stack's **greenlight
  gate** evaluates every channel against seven pre-registered criteria (sample size in both
  independent halves, both-halves profitability, CLV significance, after-cost units, trust +
  eval-gate honesty, excess win rate) and writes a fail-closed RED/AMBER/GREEN verdict nightly --
  criteria on trust and eval-gate honesty report RED, never a bare pass, on any missing or stale
  input. Fills are priced against real captured order-book depth (a VWAP walk of the opposite
  side's bid ladder, honest partial fills, `fill_quality: no_book` rather than a fabricated fill
  when the book is stale), and **STUCK detectors** turn a silent settlement stall into a visible
  alert instead of an unread log line (the incident that motivated it: 63+ silent zero-settle
  ticks). As of this writing every channel is RED or AMBER -- the gate reporting honestly that no
  edge has been proven yet is the feature, not a gap to paper over. Full account:
  [docs/PAPER_TRADING_STACK.md](docs/PAPER_TRADING_STACK.md).

**Honesty truth-source:** every number's provenance + every retracted over-claim live in
**[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)**. Open gaps:
**[docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md)**. We never claim a dollar edge / ROI /
beating the close / a CV predictive moat (CV SHAP ~ 0 in production today).

---

## Origin / NBA computer-vision lineage (engineering history, not the headline)

The platform grew out of **CourtVision**, an NBA broadcast-video CV pipeline (YOLOv8n detection ->
SIFT homography -> Kalman + Hungarian tracking -> OSNet re-ID -> EasyOCR -> EventDetector) that
turns a raw broadcast into court-coordinate data at ~$0.10-0.13 / full game on one consumer GPU.
It is where the validation machinery came from -- but it is lineage, not the product: the
CV-derived features carry ~0 measured predictive value today (SHAP ~ 0), and are not sold as an
edge. Full audited account: [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) section 2;
CV internals: [docs/CV_TRACKING.md](docs/CV_TRACKING.md).

---

## Buyer / reviewer docs

| Document | What it covers |
|----------|----------------|
| [docs/INDEX.md](docs/INDEX.md) | **The full map** -- every document, by role and by funnel stage (start here to go deep) |
| [docs/BUILT_WITH_CLAUDE.md](docs/BUILT_WITH_CLAUDE.md) | The agentic build pipeline -- Opus orchestrator + Sonnet executors under hard ship-gates |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Every term defined once (CLV, leak-free, walk-forward, Shin devig, Brier, Kelly, ...) |
| [docs/research/edge-intelligence/README.md](docs/research/edge-intelligence/README.md) | The deep-intelligence corpus index -- the brain's map of every edge, source, and lever |
| [docs/PREDICTOR_PLATFORM.md](docs/PREDICTOR_PLATFORM.md) | Full platform: thesis, scorecards, architecture, why it sells |
| [docs/PROOFS.md](docs/PROOFS.md) | The provability index -- every claim -> the runnable leak-free proof |
| [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) | The single honesty truth-source -- every number + the do-not-claim list |
| [docs/PRODUCT_DEMO.md](docs/PRODUCT_DEMO.md) | The 15-minute demo path -- system health, a live prediction, an oracle query with a receipt, the composed board, the honesty ledgers |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Open gaps and what is not yet demonstrated |
| [docs/PLATFORM.md](docs/PLATFORM.md) | Kernel + adapter multi-sport architecture direction |

---

## Tech stack

**ML / data:** Python, NumPy, pandas, pyarrow, scipy, scikit-learn (Isotonic + Platt + NNLS),
XGBoost, LightGBM. **Quant / validation:** walk-forward CV (season / era purged), Shin (1992)
devig, per-stat isotonic / temperature recalibration, NegBinom dispersion calibration,
multi-corpus calibration acceptance gate, cluster-robust Diebold-Mariano, truncation-invariance
leak tests, CLV ledger. **CV lineage:** YOLOv8n, OpenCV, SIFT homography, OSNet re-ID, EasyOCR.
**Live capture:** MLB GUMBO `feed/live` diffPatch poller at 10s cadence while any game is live
(5s politeness floor); an order-book **fill simulator** VWAP-walks captured Kalshi depth ladders
so a paper fill is priced against real liquidity, not a snapshot mid. **Serving:** FastAPI,
uvicorn, SSE, parquet feature store, compute-once snapshot service. **AI agents:** Claude Code --
Opus orchestrator + parallel Sonnet/Opus executors under hard ship gates (this codebase, including
the ~100-file intelligence corpus, was built by that pipeline under human direction). The runtime
is **Claude-free** -- classical models + a deterministic self-improve loop, no LLM on the
prediction path. **The build harness itself is live**: an autonomous probe-plan-spawn-gate-merge
loop (`scripts/platform_harness/`) is 63.9% through its current backlog (53/83 tasks) with zero
human required to click "continue." Full account:
[docs/BUILT_WITH_CLAUDE.md](docs/BUILT_WITH_CLAUDE.md) -
[docs/PLATFORM_HARNESS.md](docs/PLATFORM_HARNESS.md).

---

## Contact

Solo-built (human-directed agentic pipeline). Available for senior ML / data / quant /
founding-engineer roles.

- **Start here:** [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) -- the honest, audited account
- **Portfolio:** [neelshahportfolio.netlify.app](https://neelshahportfolio.netlify.app)
- **Email:** [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

---

*All prediction numbers in this README are calibration / sharpness (Brier / RMSE / ECE), never a
dollar edge. Candidate prop edges are tiered by evidence (hypothesis -> calibration-proven ->
CLV-proven) and proven only by forward CLV, never asserted. The single honesty truth-source is
[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md); retracted / inflated numbers appear
only there and in [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md), in explicit retraction
context, and never here.*
