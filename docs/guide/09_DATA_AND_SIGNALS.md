# 09 - Data, Signals & Intelligence

> **Honesty rail (read first).** Everything below is a **calibration / sharpness /
> coverage** story, never a dollar edge. The market is efficient pregame: our
> calibrated forecasts *match* the devigged closing line within noise on
> team-strength markets, we never claim to *beat* it. The one measured win is
> **in-game conditioning** (calibration only). PAPER / UNITS only -- no real money.
> The single truth source for any number is
> [JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md). Retracted figures listed
> there are never reprinted here as current.

This is the bottom of the funnel's input stack: **DATA -> SIGNALS -> INTELLIGENCE**.
It covers what we ingest per sport, the signal factory that turns raw data into
candidate features, the person-free intelligence graph, the computer-vision
tracking moat, and -- most importantly -- the validation discipline that decides
which signals are real. The headline of this whole layer is counter-intuitive:
**an honest REJECT is a success.** Most candidate signals are correctly thrown
away, and that is exactly what proves the gate works.

---

## 1. The data we ingest (two tracks, four sports)

The data funnel has two independent tracks that merge at the feature layer.

```
Track 1: Broadcast video                  Track 2: Statistical / market data
  yt-dlp / archive.org / inbox              nba_api + BBRef + keyless odds feeds
        |                                          |
  fetcher.py (SHA256 store)                 src/data/ (TTL-cached JSON per source)
        |                                          |
  unified_pipeline.py                       feature_engineering.py
  (YOLO -> homography ->                            |
   Kalman+Hungarian -> OSNet                  +-----+ the two tracks JOIN here
   -> EasyOCR -> EventDetector)               |
        |                                     v
  data/tracking_data.csv  ----------->  Feature matrix -> prop models + win-prob
```

**Track 2 (statistical/market)** is the load-bearing one today. NBA: `nba_api`
gamelogs (622 players, 3 seasons), 221,866 shots, play-by-play for 3,627 games,
hustle / synergy / on-off / matchup tracking endpoints, plus Basketball-Reference
advanced stats -- all TTL-cached as JSON under `data/nba/`. The sport-blind
platform extends this **keyless-first** to four sports via per-sport adapters:

| Sport | Keyless source | What we get |
|---|---|---|
| `basketball_nba` | ESPN site API + `nba_api` | schedule+elo spine, moneyline, per-quarter linescores, box |
| `mlb` | MLB StatsAPI + ESPN + SBR | spine, moneyline, starting pitchers, park factor, gamelogs |
| `soccer` (EPL) | football-data.co.uk + ESPN | match spine, O/U 2.5, xG-proxy, club priors |
| `tennis` (ATP+WTA) | Sackmann archives + tennis-data + ESPN | match spine, moneylines, serve/return splits per surface |

No paid odds-API key is needed for the default slate. Prices come from ESPN
(republishing one book's line), Kalshi, and Polymarket. Every provider degrades
to an explicit `UNAVAILABLE` sentinel on failure -- **we never fabricate a price.**

**Track 1 (CV)** -- see section 4 -- adds spatial/behavioral features at ~$0.10/game
on a consumer RTX 4060. It is fully plumbed but currently carries SHAP ~= 0 in the
production models (a credible thesis, not yet a demonstrated advantage).

### Leak-free by construction

Every derived corpus (`asof_*` stems) is leak-free **by construction**, not by
after-the-fact filtering. The shared primitive `scripts/platformkit/asof_common.py`
uses a snapshot-before-update pattern: sort events chronologically, **snapshot**
each entity's prior-only state, then **update** state only *after* all snapshots in
that event. A debut row snapshots to `NaN` and a built-in assertion enforces
"debut => NaN", so no row can ever see its own current event. This is what makes a
full rebuild reproduce the exact pregame feature each entity would have seen --
walk-forward, truncation-invariant.

---

## 2. The signal factory

The features in `src/features/feature_engineering.py` (~69 across 7 classes: box-score,
derived, CV spatial/temporal/biomechanical, market microstructure, NLP) are the
*engineered* inputs. On top of that sits the **signal factory**: the self-improving
loop's ARM-A enumerates **candidate signals** -- pure transforms of proof-validated
leak-free features plus >=2-column algebraic interactions -- inexhaustibly and with
no LLM required (`src/loop/discovery.py`). The factory's job is to propose; the gate's
job (section 5) is to decide. The catalog of verdicts lives in
[signal-inventory.md](../signal-inventory.md).

---

## 3. The person-free intelligence vault

Between raw tracking and the models sits an **80-artifact intelligence layer**
(~10 MB of parquet+json) that answers questions the models would otherwise guess:
*who is this player right now, what scheme is the opponent imposing, how confident
should we be here?* It clusters into identity/archetype, form/trend, matchup/scheme,
lineup/chemistry, situational, schedule/rest/officials, retrieval, and
quality/calibration classes. The full manifest with per-artifact row counts is
[INTELLIGENCE.md](../INTELLIGENCE.md).

On top of those artifacts is the **Obsidian knowledge graph**, and its defining
discipline is that it is **PERSON-FREE**:

```
vault/Sports/          <- multi-sport platform graph, PERSON-FREE by default
   _Hub.md             <- registry of all 4 sports
   _Signals_Hub.md     <- cross-sport REJECT/DEFER/SHIP tally
   Tennis/ Soccer/ MLB/ Basketball_NBA/
       Archetypes/  Playstyles/  Schemes/  ...   (NO individual athletes)
```

The graph models **playstyles, archetypes, schemes, and team compositions -- never
people.** Enforcement is mechanical, not aspirational: `graph_health._is_person_bearing()`
flags any note carrying `[[Players/...]]` links, `player_name:`/`display_name:`
frontmatter, or `## Roster`/`## Squad` headers, and two test suites
(`test_graph_invariants`, `test_generators_person_free`) guard the invariant on
every build. Named generators are gated OFF unless an explicit `--with-named` flag
is passed. Each NBA atlas section subclasses one `AtlasSection` contract that bakes
in leak-safety: `build(entity_id, as_of)` may only read rows with
`game_date <= as_of`, a sample-size -> confidence ladder stamps each fact, and the
builder **DEFERs rather than invents** when a source count is missing. The graph is a
descriptive scouting + correlation asset -- its measured point-accuracy lift on the
served predictor is ~0 today, and CLV vs the close is ~0. (See
[MEMORY_GRAPH.md](../MEMORY_GRAPH.md).)

---

## 4. The CV tracking moat

The computer-vision pipeline converts NBA broadcast video into player court
coordinates and behavioral features end-to-end on a single consumer GPU. It is built
from primitives, not a black-box wrapper: a custom-trained YOLOv8n ball detector,
classical-CV court homography (HSV masking -> HoughLinesP -> `getPerspectiveTransform`)
hardened for broadcast footage (inlier gating, EMA smoothing, replay/scene-cut
suspension), a 6D constant-velocity **Kalman filter** for motion plus the **Hungarian
algorithm** for globally-optimal frame-to-frame ID assignment, and an OSNet omni-scale
re-ID network reimplemented in PyTorch.

**The honest CV status:** the detector finds all 10 players, but the tracker maintains
~5-6 stable slots per frame on the calibration clip -- reliable 10-player broadcast
tracking is *not yet demonstrated*. Re-ID resolves anonymous slots to **252 distinct
real NBA player IDs across 241 games** (`data/nba_ai.db` `cv_features`, 17,254 rows),
but per-player CV attribution is ~4% accurate and no ground-truth labels exist, so
MOTA/IDF1/positional-RMSE are **not benchmarked** -- only self-consistency gates. CV
features carry **SHAP ~= 0** in production (`cv_lift_report.json: has_cv_data = false`).
The moat thesis is the **cost barrier** (~$0.10/game vs six/seven-figure optical-tracking
contracts), not a demonstrated predictive edge. (See [DATA.md](../DATA.md),
[KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md).)

---

## 5. The validation discipline (why claims are trustworthy)

This is the senior-grade differentiator. A candidate signal must clear, **in order**:

```
candidate signal
   |
   1. Expanding walk-forward  (train on past, score on held-out future; per-fold
   |     leak guard asserts max_train_date < min_test_date)
   2. Null-shuffle permutation (real lift must beat the permuted-null, not just 0)
   3. Benjamini-Hochberg FDR  (controls false discovery across the whole sweep)
   4. >= 2 independent corpora (single-fold lifts are treated as artifacts)
   |
   v
  VERDICT:  REJECT | DEFER | VARIANCE_ONLY | SHIP(unverified candidate)
```

Backing primitives, all enforced in code:

- **Truncation-invariance leak test** (`tests/test_ingame_leak_free.py`): re-featurize
  a *truncated* event stream and assert past rows are byte-identical -- a feature at
  time T is the same with or without future events.
- **Per-fold leak guard** (`src/prediction/walk_forward_backtester.py`): asserts
  `max_train_date < min_test_date` every fold.
- **Multi-corpus calibration gate** (`scripts/validate_calibration_multicorpus.py`):
  a calibration ships only if it beats raw on **>= 2 independent OOS corpora**.
- **The ship gate built to refute** (`src/loop/gate.py`): expanding WF + permutation +
  ablation-vs-full + FDR. Most candidates correctly get rejected.

### What the gate actually found

- **4-sport / 6-corpus edge hunt:** the calibrated model **MATCHES the devigged close
  within noise** on team-strength markets (NBA/MLB moneyline, soccer O/U); totals/ATP
  trail only by the freshness gap. This is the honest best case for an efficient market.
  (`scripts/platformkit/edge_hunt_scoreboard.py`, `beat_the_close_scoreboard.py`.)
- **Every candidate signal REJECTED across >= 2 corpora.** Signals that looked positive
  full-sample then **sign-flipped** out-of-sample -- the overfit signature, caught.
- **The one measured win is in-game conditioning** (calibration, not $): fusing the
  pregame rating prior with realized mid-game state sharpens the win-prob forecaster
  (NBA Brier 0.209 -> 0.159, MLB 0.241 -> 0.126), scoped real-corpus-only with
  `edge_claimed=False`. A live book sees the score too -- this is sharpness, not edge.
- **Self-caught leaks ARE the strength:** a 0.79-CV-vs-0.06-holdout overfit, hard-corrected;
  a full-season walk-forward proving the model is well-calibrated (Brier 0.208 vs close
  0.198) but does **not** beat the close (CLV ~= 0).

The pitch this layer makes: *we build ambitious data + signal machinery, then build the
instruments that disprove our own hype.* That is what makes every surviving claim worth
trusting.

---

## Where to look in the repo

- `src/features/feature_engineering.py` -- the ~69-feature engineered surface
- `src/loop/discovery.py` -- LLM-free signal proposer (the signal factory)
- `src/loop/gate.py` -- the ship gate (WF + permutation + ablation + FDR)
- `scripts/platformkit/asof_common.py` -- leak-free as-of snapshot primitive
- `scripts/validate_calibration_multicorpus.py` -- multi-corpus calibration gate
- `src/prediction/walk_forward_backtester.py` -- per-fold leak guard
- `tests/test_ingame_leak_free.py` -- truncation-invariance leak test
- `scripts/platformkit/edge_hunt_scoreboard.py`, `beat_the_close_scoreboard.py`,
  `ingame_scoreboard.py` -- the market-efficiency / in-game scoreboards
- `intel/` (30 `player_*` + 18 `team_*`) and `src/loop/atlas.py` -- atlas-section builders
- `scripts/platformkit/atlas/build_all.py` -- person-free graph builder
- `src/tracking/{advanced_tracker,court_detector,osnet_reid,color_reid}.py`,
  `src/pipeline/unified_pipeline.py` -- the CV pipeline
- Docs: [DATA.md](../DATA.md) - [signal-inventory.md](../signal-inventory.md) -
  [INTELLIGENCE.md](../INTELLIGENCE.md) - [MEMORY_GRAPH.md](../MEMORY_GRAPH.md) -
  [KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md) -
  [JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) (truth source)
