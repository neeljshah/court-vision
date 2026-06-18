# INTELLIGENCE ARCHITECTURE -- how the smart files plug back in to make the system smarter
_Part of the edge-intelligence corpus. The governing question: an "intelligent file" (atlas,
archetype, signal, inefficiency recipe, edge-map) is only worth its tokens if it makes a
NUMBER better or correctly tells us where to STOP. This file defines the two roles every piece
of intelligence can have, the hard rule that decides which, and how the corpus feeds the build
queue. Grounded in deep-dives 01/06/09. Honesty rails: calibration not $; a NULL is a success;
playstyles/archetypes NOT people. ASCII only._

## The core distinction (every intelligence artifact is exactly one of these)
1. GATED PREDICT-TIME INPUT -- a feature/prior/recal/correction that changes a SERVED number.
   It must EARN this role at the leak-free gate. If it cannot, it is not this.
2. DESCRIPTIVE SCOUTING -- knowledge that informs humans/agents/explainability but does NOT
   touch the served number. The default and honorable resting place. Most intelligence lives
   here, correctly.

The failure mode the project already hit (the DEAD FUNNEL, deep-dive 09 sec5) is artifacts
that PRETEND to be role 1 but are actually role 2: atlas columns injected at
player_props.py:2156-2170, silently dropped because the model was never trained on them
(`prop_stack_meta.json` has no `atlas_`). Built, persisted, read, thrown away. The whole
architecture below exists to prevent that pretense.

## THE RULE (binding, the keystone of this file)
> Any intelligence promoted to a GATED PREDICT-TIME INPUT must BEAT RAW on >= 2 INDEPENDENT
> corpora at the real leak-free eval-gate. Otherwise it stays DESCRIPTIVE SCOUTING.

Why >=2 corpora: a single good fold/corpus is usually a SELECTION ARTIFACT (proof-standards
bar 4; the project reverted 17 NBA feature-adds and many single-fold "lifts"). Why "beat RAW"
and not "beat the close": beating the close is the wrong target on efficient mainlines
(accuracy != edge); the gate measures BSS-vs-close as the honest yardstick but a feature
SHIPS on a leak-free Brier gain vs the frozen baseline without regression (run_gate.py:107;
self_improve SHIP needs `d_brier>0.005` + no significant regression, deep-dive 06 sec2d).

Corollary (the demote test): if the measured ablation is a NULL or negative, DEMOTE to
scouting -- do not graft. Concretely, `.planning/loop/atlas_lift.json` says pts/reb/ast get
WORSE with the bulk atlas and only fg3m is trivially better; so the honest action for ~43 of
44 atlases is "stay descriptive," and that is a SUCCESS, not a failure.

## The evidence ladder a piece of intelligence climbs (and where it can stop)
HYPOTHESIS (proposed, unmeasured)
  -> CALIBRATION-PROVEN (leak-free OOS, BSS>0 / Brier gain on >=2 corpora at the gate)
  -> CLV-PROVEN (forward paper CLV>0, cluster-robust CI>0).
Most artifacts stop at HYPOTHESIS or never enter the ladder at all -- they are pure scouting.
`prop_tiering.classify` (deep-dive 06 sec2f) already encodes the first two rungs
(proven iff bss>=0.05 AND n>=100; MODEL_VIEW vs CALIBRATION_PROVEN); the CLV-PROVEN rung is
designed but UNBUILT (no code promotes on accumulated CLV; deep-dive 06 sec5 gap 4). Building
that rung is downstream of capturing closing lines (see data-to-edge-pipeline.md severed link 1).

## How intelligence plugs in PER ROLE (the real seams)
GATED PREDICT-TIME INPUTS (the narrow, earned channel):
- Point-mean features: must be in the TRAINED feature schema, not just injected. The graft is
  an explicit reviewed step: add `atlas_feature_names()` columns to the per-stat training
  matrix, retrain, re-run `eval_atlas_by_section.py` PER SECTION (not bulk -- bulk +49 buried
  signal in noise), wire ONLY the all-folds winners. The 5 already-VALIDATED NBA signals
  (`pbp_origin_transition`, `rest_x_age`, `shot_clock_leverage`, `opp_position_defense_reb`,
  `oreb_matchup`, deep-dive 09 sec1c) are the highest-probability candidates for this channel.
- Joint/correlation coherence: ALREADY LIVE and correct -- `correlation_recal.py` reads
  archetype-conditioned residual correlations (`prop_corr_archetype_*.json`) to fix
  multi-leg/parlay calibration WITHOUT touching point means (deep-dive 09 sec3). This is the
  model for "intelligence that pays its way": it improves a distribution's coherence, gated,
  no edge claim.
- In-game conditioning: `ingame_atlas_corrector.py` is built but SHADOW-only (CV_INGAME_ATLAS=0);
  it earns the gated role only if it clears replay validation on CRPS/Brier. In-game is the
  one pocket where freshness is structurally available (deep-dive 09 sec7), so this is the
  most defensible future graft.

DESCRIPTIVE SCOUTING (the default, large channel):
- The `brain_*.py` read layer + `sport_read.build_sport_read(sport, jd)` consumes the JD +
  brain query and writes PROSE ONLY; `brain_critic` scans for edge-claim leakage and falls
  back to a safe template (deep-dive 01 sec3). The gate+engine compute EVERY number; the LLM
  never computes one. This is the correct firewall: intelligence-as-explanation cannot
  silently become intelligence-as-input.
- 44 atlases + 86 catalogued signals + 151 intelligence artifacts are a deep, provenance-
  stamped SCOUTING asset and a strong demo, at (measured) ~zero point-prediction lift.
  That is a legitimate product role -- the corpus must label it as such and stop implying the
  funnel is alive (deep-dive 09 sec6 quick-win 3).

## Flag discipline (the architecture's own honesty wiring)
The flag state must MATCH the measured role, or the system lies to itself:
- `CV_PROP_EXTRA_FEATURES` (default ON) is currently a NO-OP for accuracy (injected then
  dropped) -- either close the parity gap (retrain) or flip OFF and relabel scouting-only.
- `CV_LOOP_DISCOVERY` (OFF), `CV_INGAME_ATLAS` (OFF) -- the useful work is behind OFF flags;
  a SHIP from discovery is NOT auto-grafted (deep-dive 09 sec2c). NEVER flip a flag ON
  autonomously (human-gated invariant). The corpus PROPOSES grafts; a human gates them.

## How the corpus feeds the BUILD QUEUE
The corpus is not decoration; it is the prioritized backlog generator. The feed loop:
1. Each per-sport `inefficiency-catalog.md` + `model-levers.md` enumerates HYPOTHESES, each
   tagged with a detection/measurement recipe and the corpus its proof would use.
2. A hypothesis becomes a QUEUED build item only if (a) it is NOT in a CUT category
   (cut-list-no-edge.md) without extraordinary evidence, and (b) it has a concrete leak-free
   gate plan (which corpora, which baseline, which metric).
3. The build runs the REAL gate (`signal-audit` / `eval-gate` skills wrap it). Verdict
   SHIP / HOLD / REJECT / INSUFFICIENT_DATA is written back to the corpus `_proof/` ledger.
   A REJECT is recorded as knowledge (it removes that hypothesis from the queue permanently).
4. A SHIP that clears >=2 corpora is proposed as a gated graft (human-confirmed); everything
   else stays descriptive. CLV-PROVEN promotion waits on forward paper accrual.

Net effect: the corpus continuously narrows effort toward the beatable pockets (props, live,
correlation, CV-slot data) and CUTS the efficient ones (mainlines, NBA pregame team markets,
momentum, rare-event props), so the finite build budget flows only where the chain in
data-to-edge-pipeline.md can actually complete.

## The single sharpest architectural rule, restated
Intelligence makes the system smarter in exactly two ways: a NUMBER it provably improves at
the gate (rare, earned, >=2 corpora), or a STOP it correctly tells us to make (common, also a
win). Anything that is neither -- injected-but-untrained features, scouting that masquerades
as input, single-fold lifts -- is debt that makes the system DUMBER by implying an edge it
does not have. The architecture's job is to keep every artifact honestly in one of the two
real roles.
