# EDGE-INTELLIGENCE CORPUS -- index + the honest path to edge
_98 files here + 12 project deep-dive reports (docs/research/project-deep-dive/). Built
2026-06-17/18 by an Opus fleet, grounded in the real code/data, honestly tiered. ASCII._

## The one-paragraph truth (read this first)
The system can already PRICE the full market surface across 5 sports and is honestly AT
its CALIBRATION ceiling on efficient markets (matches the devigged close; CLV ~ 0 -- a
success, not a target to beat). It has NOT proven a dollar edge anywhere, because the two
things edge requires are missing: (1) keyless PROP-LINE FEEDS wired across sports so a
per-player distribution can be priced against a SOFT line, and (2) captured CLOSING LINES
so any candidate can be proven by CLV. Both are largely a wiring/ops problem, not a
modeling one -- the engines, scrapers, and gate already exist. The durable, honest goal is
deeper data + localized edge in the BEATABLE pockets (soft/DFS props, live lag, correlated
SGPs), proven by calibration then CLV, while CUTTING the efficient markets.

## Start here (the spine)
- 00-INTELLIGENCE-MASTER-PLAN.md -- the corpus blueprint + beatable-pocket thesis.
- 01-everything-needed-to-edge.md -- the single prioritized "everything needed to reach edge" list.
- _framework/edge-theory.md -- what edge is; the two yardsticks (calibration + CLV); where markets crack.
- _framework/cut-list-no-edge.md -- the 6 things to STOP spending on (reallocate to pockets).
- _framework/proof-standards.md -- the leak-free/OOS/CLV bar + the overfit traps that fake edges.
- _proof/edge-ledger.md -- the living tier table (HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN / REJECTED) for every candidate.
- _proof/cut-vs-push-scorecard.md -- per-(sport,market) CUT-or-PUSH call.

## Map
- _framework/ -- theory + pipeline + architecture + methods/ (8 reusable method docs:
  poisson-vs-negbin, eb-shrinkage, shin-devig, conformal-intervals, isotonic-when,
  kelly-correlation, clv-computation, walk-forward-leak-guards) + inefficiencies/ (7
  detection recipes: dfs-pickem-rigidity, live-ingame-lag, prediction-market-vs-book,
  stale-soft-line, correlated-sgp, same-day-freshness-gap, low-attention-niche).
- _scrapers/ -- data-acquisition.md + closing-line-and-clv.md + deep/ (11 per-source
  scrape specs: prizepicks, underdog, fanduel, draftkings-playwright, espn-summary,
  espn-athlete-overview, mlb-statsapi, sofascore-fotmob, kalshi, polymarket, the-odds-api,
  sackmann-and-footballdata).
- _live/in-game-edge.md -- the cross-sport in-game conditioning lever (proven calibration, hard to trade).
- _wiring/ -- actionable specs to make the system smarter NOW: wire-the-dead-funnel.md,
  same-day-freshness.md, nba-props-keyless.md.
- <sport>/ for nba, mlb, soccer_club, soccer_intl, tennis -- each has 00-edge-map,
  data-sources, markets-and-props, inefficiency-catalog, model-levers, get-to-edge-plan,
  and deep/ (per-stat push-playbooks + playstyle/role archetypes -- styles, never people).

## The consolidated PATH TO EDGE (recurring #1 findings across all sports)
1. WIRE THE PROP FEEDS (one-line-adjacent): the keyless Underdog single-GET + PrizePicks
   already carry NBA/MLB/tennis rows -- add the league ids (prop_underdog _SPORT_ID,
   prop_prizepicks _LEAGUE_NAME) + route prop_edge by sport to the right engine. Unblocks
   prop edges over DEEP multi-season corpora (esp. MLB, in-season + ~1031-game corpus now).
2. CAPTURE CLV: run the loop up to kickoff so closing lines accrue (prop_line_history is
   built; it is an ops cadence). Until then no candidate can graduate past calibration.
3. DEEPEN DATA in the pockets: MLB gamelog backfill (done ->30k games); Sofascore/FotMob
   for the stats ESPN lacks; same-day lineups/pitcher (statsapi &hydrate=probablePitcher).
4. HONESTY FIXES: tag venue_type so prediction-market prices are not shown as bettable
   best_line/arb; fit per-stat NegBinom width; use PROJECTED not realized minutes in the
   WC backtest (current calibration is optimistic).
5. THE ONE STRUCTURAL EDGE: correlated SGPs from the NBA possession sim's EMERGENT joint
   correlation -- the one thing a marginal model or the book cannot replicate; blocked only
   on league-wide sim depth + real SGP price capture, not machinery.
6. CUT: sharp mainlines, NBA pregame team markets, momentum signals, rare-event props with
   measured negative skill (WC Cards/Assists/Goals), thin-data overfit tricks, arb-as-income.

## Honest edge-state (as of 2026-06-18)
- CALIBRATION-PROVEN (sharper than base/close, leak-free): in-game conditional win-prob
  (NBA 0.209->0.159, MLB 0.241->0.126) -- not tradeable; WC Saves (bss +0.337) -- partly
  structural, needs forward CLV.
- HYPOTHESIS (plausible pockets, unproven): soft/DFS props in sound stats (MLB Pitcher-Ks /
  Hits / Walks / Outs; soccer Fouls; tennis Aces; NBA AST), correlated SGPs, live-lag.
- REJECTED / NULL (honest): opponent-adjust (measured null on thin WC), isotonic recal
  (OOS overfit), atlas features (~0 point-accuracy lift), momentum (worse than null),
  the retracted ROI artifacts.
- BLOCKED ON FEEDS, not modeling: nearly every prop edge (no wired prop feed) + all CLV.

## How to use this corpus
For a sport: read <sport>/00-edge-map.md -> get-to-edge-plan.md -> the relevant deep/ +
_framework/inefficiencies/ recipe. For a build: _wiring/ + _scrapers/deep/ are the specs.
For the proof bar: _framework/proof-standards.md + _proof/edge-ledger.md. Every claim is
tiered; nothing is a $-edge until CLV proves it on paper. Cut where the ledger says no edge.


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../../INDEX.md) - [Home](../../../README.md) - [Glossary](../../GLOSSARY.md)
