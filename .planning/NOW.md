---
updated: 2026-07-03
north_star: BEST predictions per sport (beat/match the devigged close on OOS calibration); honest, no fabricated edge.
active_project: sports-betting decision-support product (4 sports) + own keyless odds API
loop_queue_source: this file's NEXT list
---

# NOW -- the single source of truth for "what's done / what's next"

## >>> CEILING MODE (user directive 2026-06-26b): RAISE THE CEILING -- BEST PREDICTIONS
Shift from floor-raising (hardening/tests, wakes 1-15) to CEILING-raising: the highest-level
CALIBRATED predictions per sport (beat/MATCH devigged close on OOS calibration). Three levers in
priority: L1 MORE DATA independently (FIRST reclaim already-on-disk data discarded at ingest via NEW
leak-free extractors in domains/<sport>/**, zero-network; daemons keep capturing), L2 MORE SIGNALS
(many new leak-free candidates/cycle), L3 BETTER MODELS where room exists = IN-GAME conditioning +
same-day FRESHNESS (pregame is efficient -> MATCH not beat). GATE every candidate through the REAL
tools: use the `signal-audit` skill (REAL leak-free SHIP/REJECT gate per sport), `eval-gate`,
`cross-sport-benchmark` + `calibration-report` (OOS Brier/ECE vs baseline AND vs close). SHIP gated
survivors; REJECT-log the rest WITH the number (REJECT = success, never fabricate a win). Full spec:
BUILD_BACKLOG.md SECTION 0 CEILING PRIORITY block. Heavier than the hardening loop (1-2 Sonnets/wake
ok). Daemon flywheel + builder loop run independently; enders `bot stop` / program_complete only.
- DEEP RESEARCH DONE (2026-06-26b): docs/research/ceiling/ADVANCED_TECHNIQUES.md (top technique =
  Conformalized Quantile Regression for prop intervals) + ONDISK_RECLAIM_TARGETS.md (BIG finding:
  leak-free asof_*.parquet already BUILT for every sport but NO gate adapter merges them -> each
  reclaim = cheap wire+gate experiment). EXECUTION QUEUE in BUILD_BACKLOG S0.
- COMBO-MOAT WAVE-1 OPEN (ARCHITECT SESSION per SESSION_PROMPTS prompt 1,
  2026-07-05 17:05Z true-UTC): NEXT 0e execution started. YIELD NOTE: this entry
  supersedes the sprint loop's next wake -- the 17-23Z US verifier sweep items
  are COVERED by this wave's health scout lane, do not duplicate. Stage A in
  flight (wf_8d24dc3e-05f): health + live-activation verifier tick, per-sport
  ingredient inventory (reject-ledger + reclaim gates), combo-machinery contract
  scout, stack-family PREREG draft + Opus adversarial review. Fits run ONLY
  after Fable adjudicates + sha-pins the prereg (stage B: mlb_pregame_stack_v1,
  nba_pregame_stack_v1, soccer_home_sot_replication_v1). Stacks/gates need no
  sentinel; combo-daemon manifest wiring stays BLOCKED pending user confirmation
  of who armed data/cache/improve/PIPELINE_ENABLED. No edge claims.
  STAGE-A CLOSED ~17:35Z (wf_8d24dc3e, 5 agents/0.48M tok): PREREG AUTHORED +
  Opus adversarial review SOUND-WITH-FIXES, all 5 findings applied BEFORE pin
  (BLOCKING: gate_combo/gate_detail_layer base is hard-wired in-game
  sigmoid((a+b*frac_elapsed)*state_diff) -> pregame families use the fusion_mlb/
  asof_sp_form_eval N-feature WF-logistic harness reproducing L0-L6 explicitly;
  MAJORs: L1/L3 now mandatory, soccer prior SHIP was 1-of-11 year-bucket pairs
  = UNREPLICATED prior evidence, new bar >=4-of-6 leagues BOTH dirs at per-pair
  DM p<0.003846). PREREG SHA-PINNED (doc is gitignored-local by design;
  precedent = pin the hash): docs/research/combination-moat/
  PREREG_STACK_FAMILIES_2026-07-05.md sha256=
  1ea9108613af841175c663a75ec5a293d91003c27370dcd31dd096d336453baa (282 lines).
  Families: mlb K_cum=2 eps_eff=.025 (adds park+sp_ra to tuned 2-sig base, 2
  disjoint eras); nba K_cum=2 (7 solo-REJECT box dims vs Elo; expected
  NOT_TESTABLE at replication -- no 2nd disjoint box corpus; MUST NOT SHIP);
  soccer K_cum=13 eps_eff=.003846 min_corpora=4 (6-league div split). Fable
  Q1-Q6 rulings in-doc (NBA 2nd-corpus probe queued wave-2 as domains/-only
  build; WC-drop keeps pinned bars; freeze harness-internal, combo_bandit
  state untouched). HEALTH from stage-A scout: governor WORKING (17 429s today
  vs 1678 baseline, PASS); m13 props_snapshot RED 1509s vs 660 SLA (triage
  in stage B); MLB grade-rows probe looked at legacy path, re-probe at
  data/cache/ingame_grade/ queued; late-inning clamp PENDING (no rows yet).
  STAGE-B CLOSED ~18:40Z (wf_95fdc577, 12 agents/1.31M tok, commits de868023
  harness+mlb / 76b54835 nba / 511d1ea9 soccer; every lane Opus-reviewed,
  prereg sha re-verified at start+end of each lane, no tamper). THE MOAT
  MACHINERY NOW EXISTS: combo/stack_fit.py (250L) + stack_gate_pregame.py
  (300L, L0-L6+FDR pregame judge importing guards/nested_cv/fwer/dm) + 31
  tests green; harness review fix-round KILLED a decorative-L1 bug (stub
  select/score fns -- sealed-holdout now hard-gates, 2 regression tests).
  VERDICTS (0e wave-1 done-when MET: >=2 sports gated stack verdicts on disk
  w/ planted-null + replication attached): (1) mlb_pregame_stack_v1 HONEST
  REJECT both candidates at L3 seed-stability (p10 -0.000028/-0.000215<0; L1
  real+passed .000031/.000137; STRUCTURAL: corpus-B 2022-2026 added-feature
  coverage=0% -- 5413/5413 rows fell back, park/sp_ra asof features do not
  exist on the current era -> any MLB stack retry FIRST needs current-era
  asof rebuild); (2) nba_pregame_stack_v1 NOT_TESTABLE both candidates
  exactly as pre-registered (never-SHIP guard verified live; top3 by |solo
  delta| = pace/dreb/blk; close-corpus overlap verified n=89/1251, labeled;
  informational close briers 0.2468/0.2395); (3) soccer_home_sot_replication
  _v1 HONEST REJECT -- FAMILY CLOSED: 0/6 leagues at DM p<0.003846 (p range
  .0417-.33 = 10-85x over bar), L3 p10 -0.000242, planted-null fired
  correctly, L1 passed honestly (.000687) -> the 1-of-11 year-bucket
  SHIP-at-gate is CONCLUSIVELY a multiple-comparison artifact; vs-close
  BEHIND (.2455 vs .2399). Lane SELF-CAUGHT a real bug pre-report: soccer
  odds.parquet p_over/p_under are RAW DECIMAL ODDS (mean~1.94) not probs --
  first run showed false BEAT w/ nonsense close_brier .4865; fixed via
  adapter._devig_over -> honest BEHIND (landmine memory written). Most
  stacks rejecting = the system working, as pre-registered. OPS: m10
  self-recovered GREEN; grade rows PRESENT at the CORRECT paths (6918 grade
  + 2.43M inplay rows today; stage-A FAIL was a wrong-path probe); sampled
  grade rows show enrichment=false -> follow-up at settle-time; late-inning
  PENDING (early innings). m13 ROOT-CAUSED (not a wedge): EVERY tick times
  out at 240s since 16:40Z (live-slate load) AND the timeout path never
  writes the promised fallback snapshot (mtime frozen; LANE-6 design gap);
  kill+relaunch proven ineffective (PIDs 9264->24252 identical behavior) ->
  fix chain IN FLIGHT (wf_d89026f0: bounded pass + honest fallback write +
  live reload verify + Opus review). ALSO IN FLIGHT: intel synergy wave
  (wf_cf55b7dc: LeBron 30-team fit sweep SCOUTING-framed + quality-claims
  criteria.formula fix). No edge claims -- all numbers above are
  calibration-layer verdicts.
- SESSION CLOSE-OUT ~02:20Z TRUE-UTC 07-06: (1) A3 FITTED + HONEST REJECT
  (a93eaf86, Opus PASS): TA1 off/def-rtg L1 sealed-holdout -0.001393, TA2
  four-factors -0.000905 (261 frozen holdout games) -- trailing team-adv
  ratings do NOT beat WF Elo OOS, exactly as pre-registered; corpora exact
  2460/1225, fallbacks 16/0 verified, FWER imported (K_cum=6 SPENT,
  eps=.008333), 4 reject_ledger rows, shas verified start+end, lane honestly
  reported the 331-game corpus-A close overlap that contradicted A3's ~zero
  prediction (all train-half, correctly unscored). (2) SAME-VENUE CLOSE WAVE
  landed (b9ccbe4f close_capture + 0cb06b8a reconciler single_side + 15af1c3c
  extraction-target followup): forward-only kalshi own-venue closes w/
  close_venue labels; single_side transparency NOTE -- first-side collapse
  (n=65 z=-0.97) is WEAKER than the audit's exclude-paired subset (n=38
  z=-2.46), two defensible corrections disagree in strength, headline
  DIVERGENT (z=-2.04) stands and paper_pm remains RED at E-check-3.
  (3) CRITERION F EARNED NOT_REFUTED live: after the real producers re-ran
  (clv_scoreboard CLI refresh; m20 --once re-emit w/ new edge_claimed:false
  contract 8a9216d8 + tennis regression tests 8bf05fdd), cv_honesty=
  NOT_REFUTED failures=[] on FRESH inputs -- the gate peeled 3 real failures
  honestly (stale scoreboard -> missing edge_claimed -> clean) and channels
  STILL don't GREEN (evidence floors unmet -- correct suppression).
  (4) SCOPE-REVIEW CATCH: V1's extraction target kx_close_fallback.py was
  outside its ownership list -> b9ccbe4f shipped guard-imported-but-
  uncommitted helpers (feature silently inert); caught by an Opus scope FAIL
  on the m20 micro-review, repaired w/ attributed commits; ownership-list
  rail memorized (lane-ownership-extraction-trap). (5) DEPTH_PROGRAM final
  consolidated verdicts appended (rows 1-partial/2/5/9/10/12/14/17 + Family
  3), re-pinned sha256=
  341ad5074312ef8fdc5af7419aac67f01bf4329719226b725f14c2bfbbd19fab.
  SESSION TOTALS (2026-07-05 22:20Z - 07-06 02:20Z): 7 workflows + 9
  standalone agents (~54 agents / ~4.4M subagent tokens), ~21 commits, 5
  premise catches, 2 reproduced fail-open holes killed pre-land, 3 honest
  REJECTs recorded (TA1/TA2 + the standing conformal closure), 0 false
  ships, 0 fake GREENs. All handoff duties done exc. duty-3 watch (ripens
  ~07-07: tennis dispatch adjudication on shadow evidence + wnba). No edge
  claims.
- PREREG AMENDMENT A3 AUTHORED + SHA-PINNED ~01:10Z TRUE-UTC 07-06 (Fable-
  authored per 0f(b); prior shas V1 1ea91086 + A2 ccf703e1 verified intact
  before writing): docs/research/combination-moat/PREREG_AMENDMENT_A3_2026-
  07-06.md sha256=
  709505d795efd36e9df7e33d4b5ed7b5875e4e09d9dd2e4e35a1a823985ae737. Opens NBA
  Family 3 ONLY: team-adv ratings stacks on the GAP#6 reclaim (asof_team_adv
  .parquet, coverage RECOUNTED 1230+1230+1225=3685 -- an earlier scout claim
  of 2024-25-only was a join-dtype artifact, 5th premise catch today).
  Era-disjoint pair A=2022-24 (2460 games) / B=2024-25 (1225); base identical
  V1/A2 elo-logit; K_new=2 (TA1 off/def rtg diffs; TA2 four-factors efg/tov/
  oreb diffs); NBA K_cum=6, eps_eff=0.008333, min_corpora_eff=2; REPLICATED_
  WEAK cap carried verbatim (same-source pipeline); planted-null >=20 draws +
  null-floor prescreen; L1/L3 mandatory; vs-close judge non-blocking (2022-24
  close overlap ~zero, reported honestly); expected outcome REJECT (Elo
  collinearity = designed honest risk). Fit lane launches AFTER this commit
  (protocol: pin-before-fit). ALSO IN FLIGHT: paperpm same-venue close wave
  (wf_1d5c4130) from the Opus audit -- root cause of the paper_pm DIVERGENT
  flip = CROSS-VENUE basis (Kalshi taken price scored vs BOOK lock-window
  close; dogs +49.76% claimed CLV went 4-21, z=-2.84, CLV fattest on losers;
  survives independence correction z=-2.46 on the 38-row single-side subset)
  -> forward-only Kalshi own-venue close capture + reconciler single_side
  transparency block; paper_pm mean CLV treated as an UPPER BOUND inflated by
  venue basis until same-venue closes accrue. ROW-WORK wave wf_ffafa21a: BOTH
  lanes honest premise catches (tennis outcome resolver ALREADY built+wired
  2026-07-03 -- row 12's residue is exactly the dispatch-promotion watch;
  after_cost/beat_the_line/edge_greenlight freshness rows ALREADY registered
  same-day) -- row 2 CLOSED, row 12 corrected. No edge claims.
- GREENLIGHT UNCAP BUILT + LIVE ~00:25Z TRUE-UTC 07-06 (duty 1 build complete;
  wf_6dd79761 10 agents/1.00M + completion wf_dc1b83e3 6 agents/0.51M; commits
  fa468979 L2-reconciler / 5433aa84 L3-stamp+TABLE / 67e1fd7d L1-module /
  f5d399f0 L4-wiring -- every lane Opus cv-code-reviewer PASS vs pinned spec
  87bfdf1f, lanes sha-verified at start+end, no tamper). REVIEW SYSTEM EARNED
  ITS KEEP: L1 was refused TWICE with REPRODUCED fail-open holes (planted
  78.11/18.38/54.57 in cited ops artifacts passed the F-scan; planted
  edge_claimed:True in ingame_clv_verdict passed check-2) -- both fixed +
  regression-locked before landing. INTEGRATION (orchestrator-run, this
  entry = the ledgered actions): (1) prereg_sha_stamp run once on real
  l4_gate_prereg.json -> additive sha256=1a85eca7... + snapshot sidecar
  (fields byte-intact, F-check-5 sha_pending resolved); (2) reconciler
  always-emit live: moneyline GENUINE_VARIANCE n=72 max|z|=0.92 (n up from
  28 on 07-02); paper_ingame + paper_ingame_prop honest INSUFFICIENT_DATA
  n=0 (R-NA feed); paper_pm FLIPPED to DIVERGENT max|z_units|=2.04 at n=92
  (was GENUINE_VARIANCE z=1.24 at n=36) -> close-capture audit QUEUED (the
  machinery flagging its own channel = the anti-fabrication direction);
  (3) live refresh: NOT_BUILT count 0, criterion (e) emits measured reasons
  (settled_n_or_coverage_below_60 / same_venue_clv_ci_straddles_zero /
  reconcile_not_applicable:<ch>), criterion (f) RED on genuinely stale
  clv_scoreboard (fail-closed freshness; daemon flywheel owns refresh), ALL
  channels RED/AMBER -- no fake GREEN, matching the pre-ledgered expected
  outcome. Tests grounded by orchestrator's own runs: 18 (edge_greenlight)
  + 32 (trust_honesty) green per-file. Nits: pre-existing 07-02 junk
  clv_reconcile_--help.json deleted (argv-as-channel CLI quirk, cosmetic,
  fix skipped YAGNI). DEPTH_PROGRAM verdicts += GAP#3 BUILT line, re-pinned
  sha256=acbd0743b271f994ab24a7958e506603c3ac4303c1c0db4a2e594b11bba6168d.
  Suppression-only invariant intact: GREEN only stops withholding, nothing
  places; uncap EARNED per charter. No edge claims.
- GAP-ROCKS WAVE CLOSED ~23:58Z TRUE-UTC (wf_15876188, 12 agents/0.85M; duty 4
  head): 2 LANDED + 2 HONEST PREMISE CATCHES (the queue's own integrity rail
  firing). LANDED: (1) GAP#6 asof_team_adv.py 8989fe92 (Opus PASS; leak-free
  prior-only trailing from team_advanced_stats.parquet 7370 rows 2022-25;
  asof_team_adv.parquet 975KB live; snapshot-before-update WF, games.parquet
  authoritative dates; truncation-invariance + shift tests) -- 2nd-corpus
  ingredient EXISTS, fits still need sha-pinned prereg amendment (K
  cumulative); (2) composer-arc fixes d849d940 (claims_validator numpy-int64
  encoder fix, verdict logic untouched; context_shooting entity-id divergence
  fixed in PRODUCER -> nba_context_shooting 3/3 VERIFIED by independent
  recompute, was 1/3; validator never weakened). PREMISE CATCHES: (3) GAP#8
  baseout "DORMANT 0/0" is STALE -- gate live at data/frontend/ops/
  ingame_baseout_gate.json (23:18Z, n_ticks=33706/n_games=92, floors cleared)
  w/ two-corpus HONEST REJECT (a: -0.0053 dm_p~6e-17 BUT b flips +0.0012
  p=.034 AND planted null does not collapse -> overfit floor caught); closed
  as already-wired, re-adjudicate only on materially larger forward corpus;
  (4) schedule-tail premise FALSE -- games.parquet already holds 1156 full
  2025-26 rows; the "0 rows" scout read used season-key 202526 vs 2025-26
  (scout-artifact rail: verify key formats before queueing reclaims); real
  residual = 2025-26 BOX coverage 74/1156 (network-ingest class, queued
  separately only if binding). DEPTH_PROGRAM doc gained an append-only CYCLE
  VERDICTS block (rows never rewritten); re-pinned sha256=
  ef5f7d1d2adf8f5f62357912a680ae4f5fc5726fe02ef6c4da87c6ad4175e0a8.
  CONFORMAL not pulled (class closed: 3 CQR REJECTs + aci pinball-null). No
  edge claims.
- ONE-CONCLUSION COMPOSER LANDED ~23:30Z TRUE-UTC (duty 2; wf_004db836 2 lanes
  + Fable-directed fix round; commits 51ce7129 claim / ca57abe5 composer /
  6acd8b97 domain-filter fix; every lane Opus cv-code-reviewer PASS): (1) the
  canonical-shooter leaderboard is now MATERIALIZED as a VERIFIED claim
  (data/cache/intel_claims/nba_canonical_shooter_claims.jsonl: naive composite
  w/ weights IMPORTED from quality_validity_gate.py, gate-matched floors
  20g/200FGA, independent-recompute VERIFIED, rows carry fg3m/fg3a). (2)
  compose_best('shooter') answers the user capstone with ONE auditable
  conclusion + a DECLARED rule: clause-0 ASPECT DOMAIN = NBA official 82-3PM
  statistical minimum as config DATA (FABLE RULING after the live run exposed
  the wave-26 failure mode resurfacing: unfiltered naive #1 = Jarrett Allen
  fg3m=0, Gafford #2 -- domain restriction from the league's own standard,
  never a tuned threshold; unfiltered_rank1 always reported alongside);
  primary axis read LIVE from the gate verdict file (REJECT_NAIVE_STAYS_
  CANONICAL, never hardcoded -- flips if the gate ever flips); attribution
  axes with claim-id provenance; honest disagreements surfaced (shooter_
  quality_v1's own #1 = Kevin Durant; conclusion Keon Ellis not_qualifying on
  that axis's stiffer floors; rest-split axis #1 = Chris Boucher);
  face_validity_diagnostic passthrough; fail-closed UNANSWERABLE on missing
  claims/fields; VERIFIED-only loader (ask.py routes best-shooter asks).
  Tests 8+22 green per-file, Opus re-ran them + the live call itself.
  Composer generalizes via aspect-config map; only shooter wired (ponytail).
  (3) HONEST CATCHES for next wave: independent recompute DOWNGRADED 2/3
  context-shooting claims to MISMATCH (real entity-id divergences in the
  domains/basketball_nba/context_shooting_claims.py producer -- previously
  ledgered VERIFIED; the recompute rail caught it) + claims_validator.py
  write_summary crashes on numpy int64 (pre-existing; worked around without
  altering any verdict). Both queued. No edge claims -- SCOUTING framing,
  edge_claimed false everywhere.
- GREENLIGHT SPEC AMENDED + SHA-PINNED ~22:31Z TRUE-UTC (new architect session,
  duty 1, pre-build): all wf_582fb362 reviewer catches + Fable rulings R-a..R-e
  integrated INTO docs/research/depth-program/GREENLIGHT_UNCAP_SPEC_2026-07-05.md
  (r2, 299 lines, gitignored-local; pin-the-hash precedent). sha256=
  87bfdf1f107664aa0af3e1deb9ff6c929285c3e55a97f33f8bd43971b7966c56. Binding
  deltas vs the 22:15Z draft: GREEN floors IMPORTED from governance.policy
  (MIN_SETTLED_N=500 / MIN_TRUE_CLOSE_FRAC=0.90; literals = review-FAIL), 60/60
  demoted to AMBER-only tier; R-NA rule (NOT_APPLICABLE caps AMBER, never
  passes, reasons listed); E-check-3 reconciler ALWAYS-emits per known channel
  (in-game channels start honest INSUFFICIENT_DATA/N-A) -- extension in-wave;
  F-check-5 split into snapshot-immutability (runs today) + sha-integrity
  (N/A `sha_pending` until new prereg_sha_stamp.py emits the field, additive-
  only) -- emission in-wave; SLAs read FROM freshness_sla.TABLE (10 new keys,
  seconds-literals in the module = review-FAIL); reject-ledger watermark =
  dedicated append-only sidecar (data/cache/greenlight/) w/ prefix-sha rewrite
  detection, never inside the regenerable report; anti-fake tamper test
  mandatory; build lanes must sha-verify the spec at lane start+end. Build
  wave next: 4 file-disjoint lanes (module+tests / reconciler / stamp+TABLE /
  wiring), Opus cv-code-reviewer PASS|FAIL each, commit-on-PASS. Expected
  honest outcome: NO channel turns GREEN today (n/coverage floors + sha just
  stamped) -- the machinery becomes real, statuses stay earned. No edge claims.
- GREENLIGHT DESIGN LANDED AT HANDOFF ~22:15Z (wf_582fb362, 2 agents/0.20M):
  SOUND-WITH-FIXES. Spec = real fail-closed computations for (e) channel_trust
  (5 measured artifacts w/ freshness) + (f) cv_honesty (5 machine checks:
  retracted-number scan, edge_claimed integrity, proposal_only, ledger
  monotonicity, prereg integrity). Reviewer catches (all accepted): F-check-5
  sha field does not exist yet in l4_gate_prereg.json (vaporware pillar --
  fail-closed but unreachable); in-game channels lack per-channel reconcile
  artifacts -> permanently RED at E-check-3 as written; 60/60 trust floors
  contradict governance.policy vetted 500/0.90 (strongest gaming gap);
  freshness check_one returns NA for 6 unregistered artifacts. FABLE RULINGS
  recorded in NEXT_SESSION_PROMPT duty 1 (floors from governance.policy for
  GREEN; NOT-APPLICABLE never silently passes; reconciler extension + sha
  emission in the build wave; SLAs read from TABLE; watermark sidecar).
  Build = new session's first wave, spec amended+pinned first. No edge claims.
- ARCHITECT SESSION CLOSED ~22:10Z TRUE-UTC (user starting a new session).
  SESSION TOTALS (2026-07-05 17:02-22:10Z): 9 workflows + 1 standalone review
  (~60 agents / ~7M subagent tokens), ~24 commits, 11 combination candidates
  gated w/ ZERO false ships, factory built+proven, corpus B built+consumed,
  shadow layer live end-to-end w/ durable evidence store, m13 root-caused+
  fixed, 4 real infra bugs caught by honesty machinery (decorative-L1,
  decimal-odds false-BEAT, test-prod-overwrite x2, unreachable shadows),
  prereg discipline held (4 pinned docs, K cumulative). IN FLIGHT AT
  HANDOFF: greenlight-uncap design wf_582fb362 (next session adjudicates
  from disk). NEXT_SESSION_PROMPT.md REWRITTEN (duties: 1 greenlight
  adjudicate+build, 2 ONE-CONCLUSION answer composer -- canonical shooter
  leaderboard not yet materialized as a claim, composer mirrors fit_sweep,
  3 tennis/wnba promotion on shadow evidence, 4 gap-matrix rocks). YIELD:
  this session ends on the user's new-session start; no wakeups scheduled.
  No edge claims.
- CYCLE-3 FOLLOW-UPS CLOSED ~21:55Z TRUE-UTC (wf_ed653abd, 9 agents/0.91M,
  commits 3ec9e409 tennis-diagnosis + e25585bc shadow-history+factory, all
  Opus PASS): (1) TENNIS ROOT CAUSE SETTLED: state resolution is NOT broken
  (live-verified on 3 real ESPN matches incl. Bencic/Gauff; bridge + dual-
  tour merge work) -- the ONE root for both symptoms is the DELIBERATE
  missing tennis branch in live_board.live_model_home_prob (model_p None ->
  early return -> on_tick never fires -> zero grade pairs -> zero labels);
  fix = a model-dispatch choice between two proven candidates = PROPOSED
  doc (docs/research/PROPOSED_tennis_ingame_model_dispatch.md) for
  adjudication AFTER shadow evidence accrues (shadow-first ruling stands).
  (2) DURABLE SHADOW STORE LIVE: shadow_history.py + fail-open hook (proven
  reachable for no_model_prob rows; 50MB/day bound; 50/50 tests) ->
  data/cache/ingame_shadow_history/<sport>/<date>.jsonl -- promotion
  decisions now have an append evidence store. (3) FACTORY HARDENED:
  SHIP->REPLICATED_WEAK remap structural on same_source_pair (clause 3 by
  code), plant-null recomputes products from permuted components (clause 4
  literal), docstrings fixed, dup ledger rows trimmed (421->417, richer
  originals kept). NOTE: inplay_capture_loop.py concurrently expanded by
  another lane/user (DEFAULT_SPORTS += npb/kbo CAPTURE-ONLY, tennis/wnba
  already in; LIVE_INTERVAL 20s) -- intentional, preserved. NEXT BIG ROCK:
  GAP#3 greenlight uncap -- (e) channel_trust + (f) cv_honesty REAL
  implementations (design lane launching; charter: faking them green is a
  blockable regression, so spec first, build second). No edge claims.
- NBA A2 RE-GATE CLOSED 21:25Z TRUE-UTC (wf_7d1ba1de, 3 agents/0.36M,
  commit d26bcf52, Opus PASS w/ byte-identical independent reproduction):
  ALL 4 CANDIDATES HONEST REJECT at layer=FDR_PRESCREEN -- deltas
  -0.001292/-0.000801/+0.000085/+0.000587 ALL inside the matched null
  floor (p99 0.0025-0.0031 on the 1225-row primary unit) = killed in
  seconds, full ceremony correctly never spent. FIRST REAL FACTORY RUN
  PROVEN: prescreen speed + discipline both demonstrated; base identity
  verified max|diff|=0.0 across all 1814 rows; L1 selector now genuinely
  argmaxes (diagnostic bypass chose nba_pace_x_dreb -> honest L1 REJECT
  outer_score=-0.000484). TWO REAL FACTORY BUGS found+fixed+regression-
  tested in-lane: L0 base-slice shape mismatch (would have force-REJECTed
  every above-floor candidate for the WRONG reason) + the constant-L1-
  selector nit. COMBINATION-MOAT PROGRAM STATE after A2: every enumerated
  family adjudicated w/ ZERO false ships -- MLB REJECT(L3+structural),
  soccer solo+interactions REJECT (families closed), tennis interactions
  FROZEN (overfit floor), NBA 4x REJECT-at-prescreen (no longer
  NOT_TESTABLE -- genuinely tested on the powered pair). FOLLOW-UPS
  QUEUED (3 nits): (a) STRUCTURAL REPLICATED-WEAK remap in batch_gate
  (latent: a future same-source-pair SHIP would bypass clause 3 -- enforce
  by code not by luck); (b) _plant_null product-recompute-from-permuted-
  inputs (letter of clause 4; unreached this run); (c) null_floor
  docstrings 1..3 -> 1..4. Reviewer side-effect: 4 dup ledger rows
  21:18:41 (local-only, harmless). No edge claims.
- SHADOW VERIFICATION ADDENDUM 21:15Z: post-reload heartbeat rows CONFIRM
  the shadow code live (11/36 games rows carry ALL FOUR shadow keys).
  NEW LOAD-BEARING FINDING: today's tennis rows die at no_live_state
  (line ~586, UPSTREAM of the model gate) -- tennis's real blocker is
  STATE RESOLUTION, not model serving; this likely ALSO explains the
  corpus_labeled=0 settle gap -> the two queued tennis mysteries collapse
  into ONE diagnosis item (state resolution -> labeling -> shadow values).
  wnba: watch next slate. ALSO QUEUED: durable shadow-evidence store
  (heartbeat is overwrite-per-cycle; promotion decisions need an APPEND
  history -- small measurement-only lane). Daemon 24320 healthy-starting
  (first cycle slow behind governor-paced 429 retries, expected).
- SHADOW ARC CLOSED ~21:10Z TRUE-UTC: orphaned shadow-lane work Opus-reviewed
  PASS (model_prob never mutated, decision path byte-unchanged, 39 tests) ->
  COMMITTED 3978eeb6 -- THEN Fable caught what the reviewer missed: the
  wnba/nba/tennis shadow writes sat AFTER the no_model_prob early return
  that fires for EXACTLY those sports = unreachable dead code for their own
  targets (the KBO wave-61 trap, 2nd occurrence), AND the pre-existing
  wnba shadow was therefore DEAD-ON-ARRIVAL since it shipped (never wrote a
  field; the audit's 'shadow-only by design' was actually 'shadow never
  fired'). FIX COMMITTED d38efe55: three model-less shadows moved BEFORE
  the early return (sp_shadow stays post-dec, needs real model_p); 30+9
  tests green; reviewer-lens lesson = verify REACHABILITY for the target
  inputs, not just harmlessness. Daemon cycled onto the fixed code
  (17444->23064->recycling); live tennis/wnba shadow-field verification in
  flight (tennis 13 + wnba 5 live events today). Tennis-settle sub-task was
  NOT done by the dead lane BUT tennis_outcome_resolver.py already exists
  committed -> the corpus_labeled=0 gap is a WIRING/dispatch question,
  re-queued as a diagnosis item. IN FLIGHT: nba-a2 re-gate (wf_7d1ba1de).
  No edge claims.
- CYCLE-2B CLOSED + A2 PINNED 20:57Z TRUE-UTC (wf_9f68bc45, 9 agents/0.98M;
  CLOCK RE-ANCHOR: this session's prior stamps from ~"18:40Z" onward ran up
  to ~1h AHEAD of date -u -- the known estimate-drift trap; entries below
  this line re-anchored, prior entries directionally right, order correct).
  (1) CLOSE-CAPTURE + FRESHNESS COMMITTED e355dd75: prediction-ledger
  true-close attach (lock-window [tip-30,tip] parity w/ line_store,
  true_close > proxy > no_close precedence, 8868f609 proxy logic
  unregressed) -- HONEST RESULT: 0/1981 historical rows lift (line_history
  retention starts 07-02, ledger rows predate; mechanism PROVEN live on
  event 401816034 clv_pct=1.70 true_close) -> coverage lifts FORWARD-ONLY;
  6 stale ops reports (edge_greenlight/clv_scoreboard/2x clv_reconcile/
  after_cost/beat_the_line, all 73-75h old) now RED in freshness_sla
  (sound documented deviation: rows added to the CONSUMED autonomy/
  freshness_sla TABLE, not the zero-consumer ops_sentinel MANUAL_TABLE);
  35+11+35+11 tests green. (2) EXEC FIXES COMMITTED 8f599910: same-venue
  CLV restriction (close_book fields carried through from line_store,
  previously discarded by every caller), soccer 1X2 3-way proxy devig,
  prediction-logger state-filter + event-day dedup (kills the 56%
  stale-re-log class, preserves designed whole-slate logging).
  (3) A2 AMENDMENT PINNED: docs/research/combination-moat/
  PREREG_AMENDMENT_A2_2026-07-05.md sha256=
  ccf703e176d9352a6baac06503a2a0afdb4695f98508b7981e65e783046640c7 (120
  lines; nba Family 2 re-opened on the ext corpus pair A1225/B589,
  K_cum=4 [2 prior stacks + N1 pace-x-dreb + N2 stl-x-fg3m], eps_eff=
  .0125, REPLICATED-WEAK clause mandatory, prescreen may only REJECT,
  L1/L3 mandatory; both prior shas verified pre-write). NBA RE-GATE = next
  wave via batch_gate. (4) SHADOW LANE DIED on StructuredOutput cap (5th
  occurrence of this dud class) AFTER writing code: 4 shadow modules +
  an inplay_capture_loop.py edit sit UNREVIEWED on disk -- Opus review
  agent dispatched (a2c2477d); NOTHING reloads the capture daemon until
  its verdict; tennis-settle sub-task status unknown, will re-queue if
  absent. No edge claims.
- DEPTH PROGRAM PINNED ~21:45Z (wf_de19e6ab 2 agents/0.28M): docs/research/
  depth-program/DEPTH_PROGRAM_2026-07-05.md sha256=
  7136825e9aae2a92287641156dfc7dca246bbc1f7d6b6150ada5b7a7348cb7f4 (260
  lines; 7-sport depth ledgers + verbatim completeness table + 20-row gap
  matrix + standing-queue contract; every row cites evidence). AUDIT
  HEADLINES: MLB + soccer_intl loops fully LIVE end-to-end (m20 verdicts
  computed TODAY: mlb MATCH mean_clv +0.86% / 59084 ticks / 142 mkts;
  soccer_intl MATCH +2.11% / 8043 ticks, ADVERSE segments suppressed);
  NBA + TENNIS in-game models REPLICATED but UNSERVED in live_board.py
  dispatch (only mlb/soccer branches exist); WNBA shadow-only by design;
  tennis ticks flow but corpus_labeled=0 (settle gap); edge_greenlight
  (e)/(f) NOT_BUILT caps every channel (honest hold; real implementations
  = the uncap); 5 manual reports stale since 07-02 read as live. FABLE
  QUEUE CORRECTIONS to the conductor head (it ran concurrent w/ cycle-2):
  GAP#5 season-split SUPERSEDED by the built corpus B (4cee589d, n=589);
  GAP#4 serving wire goes SHADOW-FIRST (wnba_ingame_shadow pattern,
  measurement-only; promotion = later reviewed decision on shadow
  evidence); GAP#9/#10 conformal items must check the ledger first
  (aci-online-conformal already ended SHIP_REJECT_pinball_null per
  live_status last_outcome -- no re-gating closed attempts). CYCLE-2b
  LAUNCHING: (L1) close-capture daemon for the prediction ledger +
  freshness-stamp the 5 stale reports; (L2) A2 AMENDMENT draft+review
  (NBA Family 2 re-gate on the 1225/589 pair + N1/N2 enumeration,
  K_cum=4, REPLICATED-WEAK label mandatory; Fable pins next turn);
  (L3) tennis+NBA in-game SHADOW wires + tennis settle-gap diagnosis;
  (L4) the 3 approved exec fixes (same-venue CLV, 1X2 proxy devig,
  logger state-filter + event-day dedup). No edge claims -- CLV numbers
  are execution measurements, MATCH verdicts are calibration-only.
- M13 CLOSED + CYCLE-2 HEAD CLOSED ~21:20Z (wf_d89026f0 4 agents/0.75M +
  wf_16c6fa77 6 agents/0.59M): (1) M13 FIX COMMITTED c53a69f6 (Fable-
  authorized as orchestrator after APPROVE-vs-PASS string mismatch left the
  approved work uncommitted): root cause = the anti-flicker fallback re-ran
  an UNBOUNDED feed path; now primary 240s + no-network synth fallback 45s
  + per-sport fanout deadlines + timeout writes an honest fallback ENVELOPE
  (never freeze, never fabricate); Opus reviewer independently confirmed
  LIVE (primary pass 825 cards; fallback envelopes under peak load; 49/49
  targeted tests). INCIDENT: a concurrent lane's git reset WIPED this
  lane's uncommitted work once (reflog 4x 'reset: moving to HEAD'); lane
  detected + re-applied + re-verified. NEW STANDING RULE (Fable): parallel
  EDITING lanes must use worktree isolation; lanes NEVER run git reset/
  checkout on the shared tree; approved work commits IMMEDIATELY.
  (2) NBA CORPUS B BUILT + COMMITTED 4cee589d: n=74 -> n=589 (100% WF
  coverage; ext parquets 1814 rows; frozen originals byte-identical, sha-
  verified by reviewer; exact-match reconciliation 515/675, 0 ambiguous,
  160 honest drops diagnosed 82 post-schedule-edge + 74 absent-from-stale-
  games.parquet + 4 All-Star). NBA REPLICATION ARM UNBLOCKED -> A2
  amendment next cycle. 2ND TEST-OVERWRITE INCIDENT (draft test hit a
  builder's DEFAULT out_path = the frozen prod parquet): caught via the
  sha256-before/after habit, recovered, shipped test uses tmp_path
  (landmine #10 extended). Follow-up queued: refresh games.parquet 2025-26
  schedule tail (~74 more games recoverable). (3) EXEC DIAGNOSIS COMMITTED
  8868f609: the 64% at-or-after-commence SOLVED = 56% REAL DEFECT (todays_
  live_games returns the FULL day slate w/ no state filter + dedup keys on
  LOG-day not event-day -> finished games re-log next day as fresh
  predictions) + 44% designed whole-slate CLV logging (not a bug);
  close-coverage gap FIXED at settle time (_clv_from_proxy reuses canonical
  compute_clv, stamps clv_status='proxy', excluded from true-close
  aggregates -- honest); 30 current proxy rows are soccer 1X2 w/ draw-leg-
  stripped booksum<1 (structural). FABLE ADJUDICATIONS on the 3 follow-ups:
  (a) same-venue-close CLV restriction APPROVED for a lane (measurement-
  integrity; the fanduel +22.7% class is a cross-venue artifact until
  proven otherwise); (b) soccer 1X2 3-way close-proxy devig APPROVED for a
  lane (Opus-reviewed); (c) prediction-logger state-filter + event-day
  dedup fix APPROVED for a lane (pm_trading is platformkit -- editable;
  directly serves execution discipline). All 3 queued cycle-2b. IN FLIGHT:
  depth-program wave (wf_de19e6ab). No edge claims.
- THROUGHPUT WAVE CLOSED ~20:35Z (wf_00a24f85, 10 agents/0.96M tok, commits
  cfafe175 factory + a877271e mlb-rebuild + 699ad581 exec-quality, all
  Opus-PASS): (1) TEST FACTORY LIVE: per-sport gate-ready corpus caches w/
  staleness-refusing sidecars + null-floor tables (M=40 matched-flexibility
  noise fits per corpus x param-count) + batch_gate one-process runner;
  reviewer verified THE RAIL STRUCTURALLY (prescreen has exactly 2 outcomes
  REJECT|PROCEED-to-full-ceremony; fail-open on missing floor = full
  ceremony; no ship shortcut exists); 8/8 tests. (2) MLB ERA REBUILD:
  honest source truth FIRST -- pitchers.parquet+games.parquet FROZEN at
  2010-2021 (zero 2022+ rows); the only clean current-era SP identity =
  probables.parquet (11128 rows 2022-2026, REAL announced starters;
  caveat: median ~773d backfill lag via historical schedule API, identity
  not outcome-derived); espn_boxscores 2025-03+ only; statcast 2022-23
  only; rebuilt what is real, CORPUS_ABSENT where not; 8 tests. MLB family
  stays REJECT until a sha-pinned amendment authorizes re-gate on the
  widened corpus. (3) NBA PROBE -- PREMISE CORRECTION: the "single 1299-row
  corpus" = complete 2024-25 (n=1225, 98.7% cov) + partial 2025-26 (n=74)
  NEVER SPLIT, and 678 ESPN-native 2025-26 FINALS (2026-01-20..05-24) sit
  on disk UN-AGGREGATED (espn_boxscores.parquet 401-format event_ids, box
  cols 100% populated, fg3 under compound suffix). FABLE RULING: Option-1
  74-game B-side REJECTED as a replication arm (no statistical power --
  a verdict either way is uninformative); AUTHORIZE Option-2 build (bridge
  678 finals -> game_id via espn_nba_bridge, re-aggregate, extend asof
  parquets -> corpus B n~600-700, domains/-only); season-split pairs COUNT
  as 2 corpora per the MLB-era precedent BUT adjacent-season same-source
  SHIPs get a REPLICATED-WEAK label + independent-source confirmation
  required before any promotion; NBA re-gate ONLY via sha-pinned A2 after
  the corpus lands. (4) EXECUTION SCOREBOARD LIVE (execution_quality.json/
  .md): REAL FINDINGS -- 64% of pregame prediction-ledger entries (1271/
  1981) stamped AT-OR-AFTER commence (mislabel vs true-late = diagnosis
  queued); that ledger has 0% close coverage (capture gap); venue CLV
  spreads (fanduel +22.7%*/kalshi +17.0%* vs pinnacle -1.9%*) FLAGGED
  possible cross-venue close-reference artifact -- NO interpretation until
  verified same-venue closes; in-game prop -31% adverse finding REPRODUCES,
  guard ON = working. CYCLE-2 HEAD LAUNCHING: NBA Option-2 corpus build +
  execution diagnosis lanes. m13 wf still running (fix already live+GREEN,
  fallback snapshot writing; deep pass still deadline-limited under live
  load). No edge claims -- CLV numbers above are execution measurements.
- THROUGHPUT WAVE OPEN ~20:15Z (USER DIRECTIVE 2026-07-05d: "make this
  testing as efficient and fast as possible... historical data and odds...
  paper betting to get execution perfect... rejecting and accepting as many
  different ways properly... constantly pushing" -- Fable frame: maximize
  HONEST throughput; rejects get cheaper, ships stay exactly as hard; edge
  LANGUAGE stays banned in artifacts, the search itself pushes at full
  speed). wf_00a24f85, 4 lanes: (1) TEST FACTORY -- per-sport gate-ready
  corpus caches + null-floor tables (the tennis overfit-floor lesson as
  CODE: candidate delta <= p99(matched null floor) = instant REJECT
  FDR_PRESCREEN; survivors STILL face the full >=20-draw ceremony, prescreen
  can never ship) + batch_gate one-process multi-candidate runner; (2) MLB
  CURRENT-ERA ASOF REBUILD (kills the corpus-B zero-coverage wall; data
  only, frozen family stays REJECT until an amendment authorizes re-gate);
  (3) NBA 2ND-CORPUS feasibility probe (read-only, ranked build plan);
  (4) EXECUTION-QUALITY scoreboard (per channel/sport/venue: CLV-vs-close
  distribution + entry-timing + true-close coverage; measurement-only,
  units/CLV language, in-game prop guard finding must reproduce). Paid
  OddsAPI re-purchase remains HUMAN (declined 2026-07-04; flagged to user
  as reopenable). m13 fix (wf_d89026f0) still in flight. No edge claims.
- A1 GATE WAVE CLOSED ~19:55Z (wf_18023b36, 6 agents/0.61M tok, commits
  75543f39 tennis + 548399e0 soccer, both Opus-PASS): ALL FOUR A1
  interaction candidates HONEST REJECT -- and the tennis result is the
  marquee null-machinery catch of the program: T1/T2 BEAT base on BOTH
  independent tours (DM p=0.00000/0.00005, held-out deltas +0.0006 ATP /
  +0.0021 WTA, cleared L0/L1/L2/L3/L4/L5) yet 20/20 planted-null draws
  shipped (permuted surface columns bought the SAME +0.0003-0.0006 from
  pure noise) => fdr_hat=1.0, family FROZEN at K_cum=2. WITHOUT the
  matched-flexibility planted null this was a certain false SHIP --
  cross-corpus DM alone cannot catch the small-param overfit floor
  (memory rail written: gate-baseline-comparability item 4). Reviewer
  independently RE-RAN the gate to verify the freeze is design-correct.
  SOCCER: L1 sealed-holdout selected S2 over S1 then REJECTed it
  (outer_score -0.00075 on 615 frozen games; 0/6 leagues at eps_eff
  .003333; L3 p10 -0.00073; vs-close BEHIND .2462 vs .2399 in the sanity
  zone). Soccer family K_cum=15; tennis K_cum=2 FROZEN. FWER ledger
  fully consistent -- bars never hardcoded (fwer_budget imported).
  FOLLOW-UPS QUEUED: (a) harness nit -- judge passes pre-tightened
  eps_eff into fdr_budget => double-tightening 0.0125 vs stated 0.025
  (conservative-only bias, cannot false-SHIP; fix ONLY under explicit
  authorization on the shared harness); (b) S2 np.sign zero-tie counts
  as agree (immaterial to REJECT); (c) ORCHESTRATION: Workflow args
  interpolation silently returned undefined in script template literals
  -> embed constants directly in scripts; parallel same-worktree lanes
  cross-contaminated REPORTS once -> use worktree isolation or per-lane
  file-list diffs. COMBINATION-MOAT CYCLE-1 NOW FULLY CLOSED: 7 verdicts
  across 4 sports (MLB REJECT, NBA NOT_TESTABLE x2, soccer REJECT x3,
  tennis REJECT x2 FROZEN), every one planted-null-attached, zero false
  ships, machinery + FWER ledgers reusable for cycle-2. STILL IN FLIGHT:
  m13 fix (wf_d89026f0). No edge claims.
- 0f WAVE-2 CLOSED + AMENDMENT A1 PINNED ~19:35Z (wf_129021ce, 4 agents/
  0.36M tok): (1) CONTEXT-ADJUSTED SHOOTING CLAIMS LIVE (commit ff179a3d):
  domains/basketball_nba/context_shooting_claims.py off player_boxscores
  .parquet (26,186 player-game rows 2024-25) -- fg3_pct_vs_team_context
  (the literal good-shooter-on-bad-team number, player excluded from team
  mean), fg3a_share_of_team, rest_context_fg3 (B2B vs 2+ days; game logs
  existed, no CORPUS_ABSENT needed); 3/3 claims validator-VERIFIED, 7
  tests green; STINT-level design (traded players get per-team context --
  LaVine SAC vs CHI distinct rows). (2) LLM-PROPOSER emitted 6
  mechanism-motivated interaction candidates w/ REAL on-disk coverage
  checks + mechanism numbers (soccer regime split: corr(sot,over25)=.042
  low-xG vs .095 high-xG regime); honest drops: MLB zero (coverage wall),
  soccer finishing/hfa/dispersion/clean_sheet DROPPED -- grep proved they
  do NOT exist on disk (stage-A inventory rows were wrong). (3) FABLE
  ADJUDICATION -> PREREG AMENDMENT A1 sha-pinned: docs/research/
  combination-moat/PREREG_AMENDMENT_A1_2026-07-05.md sha256=
  3904b1671faaea2e8edf43dc8944fb2248748a5551179a3a6b9f96816ee56466 (100
  lines; V1 stays frozen). ACCEPTED: tennis_interactions_v1 (T1 surface-
  hold-regime + T2 low-hold-regime; K_new=2 eps_eff=.025; ATP+WTA both
  dirs) + soccer family CONTINUATION (S1 xg-pace-regime x sot + S2
  supremacy-agreement x sot; K_cum 13->15, eps_eff TIGHTENS .003846->
  .003333, >=4/6 leagues both dirs; sot enters ONLY inside interaction
  terms -- closed solo family not re-gated). DEFERRED not-enumerated:
  NBA N1/N2 (NOT_TESTABLE until 2nd corpus; K unconsumed). Gate wave
  next. No edge claims.
- INTEL SYNERGY WAVE CLOSED ~19:20Z (wf_cf55b7dc, 9 agents/0.87M tok,
  commits 97d189c0 fit-sweep + 46b901f0 quality-fix): (1) LeBron 30-TEAM
  BEST-FIT SWEEP live + VALIDATED (nba_fit_sweep_claims.py producer +
  intel_query/fit_sweep.py query surface; claims_validator VERIFIED 0
  mismatch; frozen weights .40 complement/.35 scheme/.25 vacancy declared
  pre-compute; player excluded from own-team roster means): top-10 BOS
  .5703 / PHI .5631 / NYK .5566 / NOP .5542 / POR .5480 / OKC .5381 / LAL
  .5228 / PHX .5160 / HOU .5090 / BKN .5081; CHI honest UNANSWERABLE (no
  VERIFIED BIG-vacancy row); report data/cache/intel_claims/
  lebron_best_fit_sweep_2026-07-05.md w/ the fit-gate REJECT cited verbatim
  up top -- SCOUTING-only framing enforced end-to-end. (2) Quality claims
  now 2/3 VERIFIED + 1 unverifiable-BY-DESIGN (paired-bootstrap CI has no
  recompute formula, documented contract); REJECT_NAIVE_STAYS_CANONICAL
  re-confirmed on re-run (naive rho .4044 > shooter_quality_v1 .2680).
  (3) REVIEW CATCH: two tests were WRITING 3 synthetic rows OVER the prod
  329-row pillar snapshots (test-pollution made the shooter claim
  UNVERIFIABLE) -> monkeypatched + snapshots regenerated + regression
  tests (landmine memory #10). NOTE cross-lane report contamination
  occurred (two lanes, one worktree: lane A's report described lane B's
  diff; verdict-string mismatch APPROVE!=PASS left a false FAILED status)
  -- reconciled from disk: BOTH lanes committed, tree clean of intel files;
  workflow-design lesson = single-worktree parallel lanes must diff their
  OWN file list, and review schemas must pin the verdict enum. IN FLIGHT:
  m13 fix (wf_d89026f0) + 0f context-depth wave (wf_129021ce). No edge
  claims -- fit output is SCOUTING-only per the standing REJECT.
- MAINTENANCE (SYSTEM HEALTH SWEEP + WORKSPACE ORG, 2026-07-03 pm, review session):
  FOUND+FIXED two LIVE serving-spine outages: (1) m1_api_paper (:8099) WEDGED since
  13:00:30 (last request served = /api/paper/trail?limit=2000; event loop blocked,
  CPU spinning ~2.8h; supervisor HTTP probe TimeoutError but NO wedge-kill exists for
  HTTP-readiness procs -- heartbeat_reaper only covers heartbeat procs = REAL GAP,
  flagged not fixed) -> killed PID, supervisor relaunched, /health 200 + props route
  200 (2823 rows). (2) m1_api_boards (:8098) serving 500s: conda env anyio install
  was MIXED-VERSION (4.14 _backends importing TaskHandle missing from a stale
  _core/_tasks.py -- fallout of the WAKE-33 scrapling anyio bump while daemons ran)
  -> clean pip uninstall+reinstall anyio==4.14.1, relaunched, /health+/api/slate 200.
  Feed health 25/25 GREEN (5 providers x 5 sports). Props-route fix (460fd0cb) +
  PropsPanel (9bc820d4) verified intact + live; 7 per-file route tests green.
  ORG: NOW.md trimmed 291KB->100KB (WAKE-1..15 + June sessions + verbose DONE logs ->
  .planning/archive/NOW_ARCHIVE_2026-06.md; NEXT queue + P1->P7 in-play ledger + RECENT
  DONE kept in head -- code-review caught the first trim archiving the NEXT queue,
  restored same session); webapp/README.md created (prod-build/.next gotcha);
  root scratch (trail_temp.json, oa809*.json, STATUS.md lane notes) cleared/archived.
  No accuracy/edge claim; serving-spine repair only.
- INTERACTIVE FABLE WAVE (wf_ff769e21, USER-DIRECTED QUEUE ADJUDICATION +
  INDEPENDENCE BUILD, 2026-07-05 15:20-16:15Z, 24 agents/~2.36M tok, 10/10
  lanes PASS w/ Opus review, commits 9f6bc39b + afec9f52..b024a104): ALL 10
  human-queue items Fable-adjudicated as user-proxy (full record:
  docs/research/organization-sprint/HUMAN_QUEUE_2026-07-05.md top section).
  LANDED: (1) m1_ui reaper fix ('next-server'->'next'; arms at next
  supervisor restart -- running supervisor holds old code, flap frozen
  meanwhile); (2) Kalshi rate governor 297 LOC wired BOTH daemons at the
  inplay_kalshi choke point (capture .35 / snapshot .65 shares, cross-process
  429 pressure file, KALSHI_GOVERNOR_OFF kill-switch; evidence: m2_inplay
  1678 429s today unpaced); (3) depth-capture ARMED (Fable-sanctioned flag,
  fail-open) + m2_inplay_capture registered in daemon_registry (26 entries)
  + WNBA injuries daily daemon; (4) feed_health schema_drift overlay;
  (5) improve/ FWER min_corpora_eff floor + planted-null ledger bridge;
  (6) soccer ADVERSE-segment suppression (conservative withhold). RECLAIM
  GATES (honest verdicts, nothing wired): NBA 7/7 REJECT (pace/oreb/tov/dreb/
  fg3m/stl/blk asof dims vs Elo, planted nulls died correctly, ast_rate
  excluded as prior REJECT); tennis 10/10 REJECT (hold%/return dims, ATP-only);
  MLB found ALREADY DONE prior wakes (sp_ra REJECT; weather-vs-close REJECT
  n=2113); soccer 1 SHIP-AT-GATE candidate home_sot_for_l10 (beats OWN
  goals-only Poisson base w/ planted-null dying; vs-close UNTESTED, nothing
  wired, cross-corpus replication REQUIRED before any promotion) + 10 PARTIAL
  + 1 REJECT. RUNTIME: both inplay daemons reloaded onto new code via
  supervisor (capture 29752->17444 ~40s detect + 32s backoff; snapshot 15804
  reloading), governor active both callers. ALSO: ponytail plugin INSTALLED
  via CLI (new sessions); autostart -Register attempted = needs elevated
  shell (human); private remote VERIFIED reachable -> branch pushed; P0-A-002
  edge-named scripts untracked (9f6bc39b). HONESTY NOTES: 2 PROPOSED docs
  found stale-already-applied (m8_ci_cadence, CLV bridge -- live via
  aggregate_clv_to_corpus); PIPELINE_ENABLED sentinel found ALREADY ARMED on
  box (NOT this session -- flagged to user); selfimprove_daemon 307 LOC (was
  301 pre-existing over-cap, +6 flagged); pre-existing RH1 heartbeat test
  failure verified pre-existing via stash. NEXT: soccer home_sot_for_l10
  cross-corpus replication gate; nodriver install at next restart window
  (AGPL accepted for local-only); supervisor restart window to arm reaper
  fix. No edge claims -- every verdict above is calibration-only.
- SPRINT WAKE 70 (HEALTH TICK, 15:29Z): all green -- heartbeat 0.3 min,
  MLB/soccer feeds 1.0 min, KBO 138 rows. Hop; US verifier sweep wave
  launches next wake (~16:30Z) so results land as the 17Z window opens.
- SPRINT WAKE 69 (HEALTH TICK, 14:30Z): daemon SINGLETON confirmed (29752;
  the second PID was my own probe matching its own command line -- observer
  effect, resolved), heartbeat 1.6 min, MLB/tennis feeds 0-1 min fresh, KBO
  corpus 133 rows. All green; hop to US verifier sweep window ~17Z.
- SPRINT WAKE 68 (WAVE-65: KBO DAY-1 CORPUS CLOSED OUT, 2026-07-05 ~13:35Z
  true-UTC, wf_7b02838c-d51 2 agents/~0.16M tok): 113 rows/5 games. SSSK
  100% innings coverage / LTKT 77.8% / OBWO thin (mid-matinee wire start,
  expected). ANOMALY RESOLVED w/ evidence: HHLG+NCHT = REAL-SUSPENDED rain
  cancellations (cancel=true + textRelay rain; parser fabrication path
  ruled out by code audit) -> 37 pre-start shell rows flagged, QUARANTINE
  RULE recorded (exclude cancel=true games from future fit prep; capture
  keeps raw). 1 OBWO single-poll progression blip. Daemon healthy. Memory
  05i written: density adequate (~25 rows/game); binding constraint =
  GAMES; honest reopen-consideration bar ~150-200 covered games ~= mid-Aug
  2026 at current cadence; synthetic n is NOT the yardstick. NEXT: US
  verifier sweep 17-23Z (hops w/ honest ticks; wall-clock cadence
  sanctioned, no make-work). Slate report: data/domains/kbo/. No edge claims.
- SPRINT WAKE 67 (SLATE TICK, 12:14Z): corpus 110 rows/5 games. SSSK inn8
  (39 rows) + LTKT inn9 near close; HHLG/NCHT later starts in early innings
  (live ~2h more; HHLG 26-rows-at-inn1 pattern flagged for the close-out
  lane); OBWO final-static. Hop to ~13:15Z, close-out lane ~14:15Z.
- SPRINT WAKE 66 (MID-SLATE TICK, 2026-07-05 11:12Z TRUE-UTC via date -u;
  correction: wake-65's "~11:45Z" stamp was ~10:45Z actual -- estimate
  drift again, re-anchored): stop flag false. KBO real-state corpus
  accruing healthily MID-SLATE: 60 rows / 5 games (SSSK 24 climbing, OBWO
  19 final-static, HHLG 10, LTKT 6, NCHT 1 NEW file) -- daemon working by
  direct evidence (new game file appeared, counts climbing since the
  wave-61 reorder). All non-time-gated work remains COMPLETE; slate close
  ~12:30-13Z -> close-out verification lane next wake; US verifier sweep
  17-23Z after. No workflow in flight BY DESIGN (wake-50 precedent -- no
  make-work waves while everything is time-gated). No edge claims.
- SPRINT WAKE 65 (WAVE-64: BATTERY GAP CLOSED, 2026-07-05 ~11:45Z true-UTC,
  wf_0711da68-066 3 agents/~0.28M tok, commit 500c7e24): the tennis name
  gap was v4-ONLY (v3 already emitted player_name -- fix lane VERIFIED
  rather than assumed); v4 gained the same matches.parquet lookup (423 ids,
  0 unresolved), 17/17 re-VERIFIED w/ unchanged rows + stable claim_ids;
  Djokovic/Isner name lookups resolve w/ provenance (addendum artifact);
  15 tests green. QUEUE STATE: all non-time-gated PROGRAM v3 work COMPLETE
  (claims full-pop + fit SCOUTING/REJECT + battery proof + gaps closed);
  remaining items are time-gated (KBO slate-close accrual tick ~12:30Z,
  US verifier sweep 17-23Z) or human-gated (PROPOSED docs, depth arming).
  Per the wake-50 precedent: wall-clock cadence to the next window -- no
  make-work waves. Wakeup set for the slate-close window. No edge claims.
- SPRINT WAKE 64 (WAVE-63: V3 CLOSURE PROOF ON DISK, 2026-07-05 ~11:20Z
  true-UTC, wf_82443ee0-97c 5 agents/~0.37M tok, ledger-only commit): ask
  demo battery 29 questions via the REAL entrypoints -- 19 VERIFIED, 1
  SCOUTING (LeBron/LAL fit w/ inline REJECT cite, 4-way provenance), 5
  honest UNANSWERABLE (each names its missing piece), 3 VERDICT + 1 honest
  AMBIGUOUS tie, provenance_missing=0 (transcript:
  data/cache/intel_claims/ask_demo_battery_2026-07-05.json). One REAL gap:
  tennis v3/v4 stores key by numeric player_id only -> name lookups cannot
  resolve (fix = wave-64). m2 question CLOSED: INTENTIONAL siblings
  (disjoint outputs inplay_history vs ingame_grade, ~10 vs ~27 consumers,
  ZERO overlap, separate SLAs; shared-fetch idea PROPOSED only). WAVE-64
  launching: tennis id->name resolution (reuse the hold-claims name source,
  regenerate v3/v4, battery re-check). KBO slate-close tick ~12:30Z, US
  verifier sweep 17-23Z next. No edge claims.
- SPRINT WAKE 63 (WAVE-62: RETRO DIGEST + HANDOFF REFRESHED, 2026-07-05
  ~11:00Z true-UTC, wf_da0e1705-577 5 agents/~0.35M tok): digest verified
  (waves 47-61: 42 commits, 11 honesty catches, coverage 62 claims/13210
  rows/16305 entities); human queue extended in its REAL location (docs/
  research/organization-sprint/HUMAN_QUEUE_2026-07-05.md, items 9-10).
  CONFIRMED: m2_inplay (PID 15804, inplay_runner snapshots) and
  m2_inplay_capture (PID 29752) are TWO distinct daemons, both 429ing ->
  double-polling consolidation = open question (read-only intent check
  queued). KBO 27 rows/4 games accruing. FABLE wrote: sprint retro memory
  (waves47_61) + MEMORY.md index + NEXT_SESSION_PROMPT.md REWRITTEN for
  post-sprint (standard rails from 07-07, runtime-evidence bar, clock rail,
  open watches). WAVE-63 launching: ask-layer end-to-end demo battery (the
  v3 closure proof: 25 questions across all sports, provenance asserted) +
  m2 double-polling read-only intent check. Slate-close KBO tick ~13Z next.
- SPRINT WAKE 62 (WAVE-61: KBO CAPTURE LIVE FROM THE DAEMON -- ARC CLOSED,
  2026-07-05 ~10:35Z true-UTC, wf_7e0a2bd9-94a 6 agents/~0.51M tok, 1
  commit): the sanctioned reorder shipped (kbo-only deep capture before the
  no_live_state return; decision path byte-unchanged; 41 tests); daemon
  reloaded (7880->29752); RUNTIME PROOF: 26 relay rows / 4 games accruing
  autonomously (SSSK inning 1->2 progression, OBWO 19 rows). Three stacked
  bugs total on this arc (runner default / uncalled persistence / early
  return), every one caught by runtime-evidence review. Real-state corpus
  STARTED; model fit stays FORBIDDEN until a fresh pre-registered real-state
  gate. 429 micro: 192 total (soccer_intl 74/mlb 62/kbo 19), backoff exists
  (kalshi_pacing), feeds 1.4-9x hotter than yesterday NOT degraded, governor
  stays PROPOSED; NEW question: second daemon m2_inplay may be a legacy
  duplicate (1583 429s) -> read-only identity check queued. WAVE-62:
  sprint-retro digest + human-queue consolidation (07-06 EOD approaching),
  KBO accrual tick + m2_inplay duplicate check (read-only). No edge claims.
- SPRINT WAKE 61 (WAVE-60: TWO MORE REAL KBO BUGS PEELED, 2026-07-05 ~09:55Z
  true-UTC, wf_ed425118-c63 6 agents/~0.64M tok, 1 commit): (1) FIXED --
  kbo_capture_wire built state rows but NEVER persisted (append_state_row
  uncalled sibling; docstring lied); chain dry-run proves all 4 live tickers
  resolve end-to-end; daemon reloaded (PID 7880). (2) UNFIXED STRUCTURAL:
  _process_game returns no_live_state at line ~563 BEFORE the deep dispatch
  (~569) -- ESPN can't resolve KBO live states (why the relay exists), so
  the wire is unreachable; fix agent deferred, re-reviewer ruled FAIL
  (deferral != resolution; correct). FABLE SANCTION: minimal reorder -- for
  sport==kbo fire the fail-open deep capture BEFORE the early return,
  decision-path return UNCHANGED (capture-only). 429 lane died on
  StructuredOutput cap AGAIN (2nd) -> micro-schema retry. Partial 429 data:
  ~10% kbo-tagged of 192 total; feeds healthy. WAVE-61: reorder+test+reload
  +in-window verify (slate live to ~13Z), micro 429 diagnosis. No edge claims.
- SPRINT WAKE 60 (WAVE-59 ADJUDICATED FROM DISK, 2026-07-05 09:15Z TRUE-UTC
  [clock note: box=CDT/UTC-5; my wave 'now' args + recent ledger stamps ran
  ~45min ahead; re-anchored to date -u]): KBO lane died on StructuredOutput
  retries AFTER finishing -- disk shows the kbo_deep setdefault landed
  (08:47Z), default-assert test 5 green, daemon reloaded on NEW code (PID
  28232 @ 08:49Z). Runtime accrual PENDING honestly: slate live ~09:00Z,
  ticks flowing (last 09:00:28Z), zero kbo log lines in 20min = inconclusive
  (fail-open degrades SILENTLY -- verify lane must dry-run the chain if rows
  stay absent). m1_ui flap RESOLVED: orphan chain killed (3 PIDs, cascade),
  port 3000 -> new parented PID 22684, restart counter FROZEN at #264 since
  08:50Z (was ~90s cadence, 264 restarts/20h); reaper fix stays PROPOSED.
  1 commit (runner+test). WAVE-60 launching: KBO daemon-evidence accrual
  verify (+chain dry-run if silent), Kalshi 429 read-only diagnosis
  (global-rate-governor is a known frontier gap -- propose only).
- SPRINT WAKE 59 (WAVE-58: VERIFY LANE CAUGHT MY OWN OVERCLAIM, 2026-07-05
  ~09:50Z, wf_52c934de-cb2 9 agents/~0.79M tok, 1 lane commit): HONEST
  CORRECTION -- the kbo_deep wire is NOT live in production: the runner only
  setdefaults mlb_deep, never kbo_deep (serve_forever default False; enricher
  = dead code; zero kbo log lines; the disk state row was wave-56's MANUAL
  soak). Wave-57's "wire now LIVE" ledger line was an overclaim; alias/
  matcher chain dry-runs CORRECTLY -- gap is purely the runner default.
  m1_ui flap ROOT-CAUSED w/ evidence: 17h orphaned next-start holds :3000
  (259 relaunches; reconcile_survivors pattern-match bug never fires; C7
  breaker never tripped) -> code fix PROPOSED (supervisor tree untouched);
  orphan kill is the sanctioned minimal ops fix. NBA schedule claims: 5 dims
  x 30 teams VERIFIED from games.parquet (thin scoreboard cache honestly
  rejected). Kalshi 429 throttling noted all-sports (orthogonal, feeds still
  growing). WAVE-59: kbo_deep setdefault fix + reload + DAEMON-log accrual
  verify (slate live now), m1_ui orphan-chain kill + hold-clean watch.
- SPRINT WAKE 58 (WAVE-57 SHIPPED: DAEMON RELOADED + SOCCER WIDENED,
  2026-07-05 ~09:25Z, wf_0e1ab333-af3 6 agents/~0.48M tok, 1 lane commit +
  1 ops action): m2_inplay_capture reloaded SINGLETON-clean (PID 20452->
  23332, supervisor reap_and_restart in 2s, clean startup, two-layer HB
  verified 11.5 min, other daemons untouched) -- the wave-56 kbo_deep wire
  is now LIVE in production; KBO accrual honestly PENDING (matinee ended
  pre-reload, main slate ~09:30Z). Soccer: 2911 H2H pairs + 179 form teams
  VERIFIED (canonicalization + date-resort both PROVEN load-bearing by
  dedicated tests). NEW SMELL surfaced: m1_ui restart-cycling ~90s
  (pre-existing, untouched) -> diagnosis lane queued. WAVE-58 launching:
  in-window KBO accrual verify (4-game slate), m1_ui flap read-only
  diagnosis (fix only if platformkit-editable), NBA schedule/travel
  DESCRIPTIVE claims (predictive travel class stays CLOSED). No edge claims.
- SPRINT WAKE 57 (WAVE-56 SHIPPED: KBO CAPTURE WIRE CLOSED, 2026-07-05
  ~08:50Z, wf_79579c90-da0 6 agents/~0.61M tok, 2 lane commits): alias bridge
  evidence-derived across 3 alphabets (Kalshi KBO tickers do NOT fix team
  order -- unique-split matching; Naver codes via existing team_map glyphs,
  zero invented literals); fail-open chain wired via kbo_deep_state_fn
  (mirrors mlb_deep); LIVE SOAK stored a real progressing state row (counts
  0-1 -> 0-2, top 9th) with decision behavior UNCHANGED (no_model_prob,
  capture-only). 90 tests green. NPB+KBO join claims: 8 strength dims
  VERIFIED (NPB 3964-rowcount guard refuses on mismatch). Model wire stays
  FORBIDDEN (both ingame fits HONEST_NEGATIVE) until real states accrue for
  a fresh pre-registered fit. WAVE-57 launching: capture-daemon single-
  process reload (supervisor relaunch precedent, two-layer HB check) +
  in-window accrual verify (main slate ~09:30Z, 4 games), soccer widening
  (H2H pairs + form descriptive from owned results). No edge claims.
- SPRINT WAKE 56 (WAVE-55 SHIPPED: KBO LIVE CONFIRMED -- WALL BROKEN,
  2026-07-05 ~08:15Z, wf_c05edee0-9e0 9 agents/~0.75M tok, 3 lane commits):
  Naver relay served REAL MID-GAME states (2 polls 66s apart, game
  20260705OBWO02026: score 5->6, bases rotated, seq 79->80; full base-out/
  count fields) -- first success after every prior probe hit finals. State
  provider built (13 tests, live fixture); WIRE honestly deferred: needs a
  3-way team-code alias bridge (Kalshi ticker vs parquet vs Naver 2-letter)
  + date matcher; NO model wire (kbo_live_model stays HONEST_NEGATIVE
  fail-closed). Tennis H2H: 2787 full pairs VERIFIED (first production
  pair-keyed validator claim; no WTA rows -> no fabricated split). Fit
  REJECT registered into ask (17 verdict claims; validity questions answer
  REJECT w/ provenance; compose_fit cites it inline). Merged test state
  27+5+13+12 green. WAVE-56 launching: KBO alias bridge + capture wire +
  bounded live soak (4 games start ~09:30Z; alias rail: EXACT-match codes,
  never substring city match per prop-settler lesson), NPB/KBO descriptive
  team-strength claims (7th+ sport coverage). No edge claims.
- SPRINT WAKE 55 (WAVE-54 SHIPPED: FIT-VALIDITY GATE HONEST REJECT, 2026-07-05
  ~07:55Z, wf_bd872e77-95e 7 agents/~0.60M tok, 1 code commit): the marquee
  verdict -- fit score (archetype x scheme x vacancy, season<=s ingredients)
  does NOT predict post-move performance: pooled_delta=-0.0618 (H1 WORSE),
  sign 1/5 folds, off-init PROVEN, both nulls die, reproduced twice, 17 tests
  green. V2 amendment written BEFORE run (V1 frozen sha re-verified; V2 sha
  2df32a291c3190db); lane self-caught a coarse-grid optimizer defect + a null-
  comparison bug pre-verdict. REJECT = SUCCESS per priors; fit stays SCOUTING
  (memory written). Validation-contention: 18 producers audited, 3 missing
  per-store validation files materialized (wnba 5/8 claims were invisible to
  ask) -> coverage 62 VERIFIED claims/16 stores; 3 stale wnba dupe jsonls
  deleted (subset-verified). KBO probe: 5-game slate saved, 1 game ALREADY
  STARTED -> live window OPEN EARLY. WAVE-55 launching: KBO Naver LIVE
  mid-game confirm + capture-only wire (m31 as-of, fail-open, NO model/flag),
  tennis H2H full-pair claims (30616 pairs), fit REJECT verdict into ask.
- SPRINT WAKE 54 (WAVE-53 SHIPPED: NBA TRULY FULL-POP + MOVES 417, 2026-07-05
  ~07:25Z, wf_d8c6358b-cc0 10 agents/~0.80M tok, 3 lane commits): NBA uncap
  FIXED (1000->5424 rows, ts_pct=329 recount-verified, LeBron 9->17 rankable,
  20/20 re-VERIFIED, ids stable); soccer stale claim_id cleared; dossiers
  1992 / 8442 lines; coverage 5 sports/47 claims/10327 rows/13422 entities/
  21551 honest below-floor. bbref ingest 4/4 seasons (4 req, 0 blocks); moves
  96->417 (5 cohorts 82/80/85/74/96; prereg 96 reproduced byte-identical, sha
  intact). Recompute: strict threshold reading false BUT second-cohort event
  substantively satisfied -> FABLE DECISION (charter S6 user-proxy):
  AUTHORIZE gate run via V2 AMENDMENT (new sha-pinned file, V1 stays frozen;
  strict season<=s ingredients; planted-null + comparability + off-init;
  honest REJECT/NOT_TESTABLE expected = success; measurement-only, wires
  nothing). MLB whiff/chase honest CORPUS_ABSENT (no description col);
  zone_rate 665/1130 VERIFIED. WAVE-54 launching: fit-gate V2 amend+run,
  shared validation-json contention fix, KBO slate probe (window ~09:30Z).
- SPRINT WAKE 53 (WAVE-52 SHIPPED: COVERAGE+DEPTH WIDENED, 2026-07-05 ~07:00Z,
  wf_6ca41510-e18 21 agents/~2.02M tok, 5 lane commits): ask auto-discovers
  ALL claim stores + coverage_report.json (55 validated); dossiers 1253->1823
  / claim lines 1308->3865 (registry zero-match prefix fix + pipe-filename
  crash fix); WNBA +5 atlas parquets +5 claims 8/8 VERIFIED (IEEE754 tie bug
  caught); tennis atlases PERSISTED (playstyles 408 / h2h 30616 / surface 903;
  scouting honest-empty) + 9 surface claims v4; MLB TTO descriptive 4 dims/785
  SP (fatigue class stays CLOSED); bbref probe GREEN (robots allows, est +400
  moves, corpus-size threshold MET; artifacts docs/research local-only).
  HONEST CORRECTION: wave-51 NBA "full population" was WRONG -- TOP_N=50
  survived in basketball_claims.py (1000 rows = 20x50; caught by the dossier
  lane cross-check, missed by wave-51 dual review). WAVE-53 launching: NBA
  uncap+regen+settle (claim_ids stable), bbref 4-season ingest + moves rebuild
  + power recompute (gate run stays LOCKED pending Fable review; prereg sha
  pinned), MLB plate-discipline descriptive dims. KBO window ~09:30Z next.
- SPRINT WAKE 52 (WAVE-51 SHIPPED: FULL-POPULATION CLAIMS LIVE, 2026-07-05
  ~06:25Z, wf_b3927d59-905 28 agents/~2.37M tok, 7 lane commits): backlog
  dual review CAUGHT the KBO wire on a noise-disqualified fit + FABRICATED
  wire-proof params -> KBO dispatch branch REMOVED (NPB/KBO symmetric),
  docstrings HONEST_NEGATIVE, fail-closed loader, 14+4 tests green (another
  honesty-machinery catch). Full-population claims via UNMODIFIED validator:
  NBA NEW 20 dims/329 players (LeBron 9 rankable + 11 honest below-floor);
  tennis 245 + 8 v3 claims; MLB 4 modules uncapped (963 ranked); soccer 153;
  WNBA NEW 3 descriptive-only dims; fit ingredients 531 rows -> ask.py
  compose_fit SCOUTING-labeled (Luka/LAL composes; was 2x UNANSWERABLE).
  Fit-validity gate PRE-REGISTERED: n_moves=96 -> expected NOT_TESTABLE,
  double run-guard, spec sha pinned in commit (docs/research local-only).
  LAUNCHING wave-52: ask auto-discovery+coverage, dossier full-pop (staging
  only), WNBA atlas extract, tennis atlas persist, MLB TTO descriptive,
  bbref moves-backfill PROBE. KBO Naver confirm next window ~09:30Z.
- SPRINT WAKE 51 (PROGRAM v3 WAVE-1 LAUNCH, 2026-07-05 05:12Z TRUE-UTC; box
  local=UTC-5, prior entries' Z labels ran ~2h ahead -- wake-50 actually
  closed ~04:35-05:06Z): stop flag false. Found UNCOMMITTED wave-50 backlog
  (kbo_live_model.py + npb_kbo_wire_proof.py + 2 tests + live_board.py diff
  + tennis playstyle_ingame_gate_io.py) -> dual-Opus backlog review lane
  FIRST; commit on PASS at notification. LAUNCHED wave-51 workflow: 4 haiku
  scouts -> 6 file-disjoint sonnet lanes (NBA full-population claims NEW
  basketball_claims, tennis/MLB/soccer+WNBA cap-drop full-pop, fit-ingredient
  claims + SCOUTING fit family in ask.py, fit-validity gate PRE-REGISTRATION
  power-audit-first w/ honest NOT_TESTABLE allowed) -> dual Opus per lane ->
  fix round. claims_validator stays UNMODIFIED (rail). KBO Naver live confirm
  queued ~09:30-13Z; US verifier sweep ~17-23Z. No edge claims.
- SPRINT WAKE 50 (WAVE-49: H3 REPLAYABLE + REPLAY LEDGER 4/7, 2026-07-05
  ~07:10Z, wf_359c261e-484 3 agents/~0.30M tok, commit 6bf71d17): real export
  bug fixed (H1's base zipped into p_base instead of H0's own prediction);
  gate re-run BYTE-IDENTICAL to committed verdict (no-drift guard held);
  tennis_h3 client RAN at 4e-7. Replay coverage 4 RAN / 3 honest UNAVAILABLE
  (need gate re-fits, out of scope by policy). ALL runnable non-time-gated
  work now complete -> wall-clock cadence per charter until: KBO Naver LIVE
  confirm ~09:30Z (reopens KBO in-game), US verifier sweep ~17-23Z, sprint
  close 07-06 EOD. Overnight-session yield protocol active. No edge claimed.
- SPRINT WAKE 49 (WAVE-48: RMSE MODE + UMPIRE REPLAY 0.0, 2026-07-05 ~06:40Z,
  wf_2bcc5cb4-b36 3 agents/~0.40M tok, commit 328d8348): harness gains
  metric=rmse; umpire-totals client RAN at max_abs_diff=0.0 all 3 folds (pure
  relabel + gate's own fold constants, read-only); tally 3 RAN / 4 honest
  UNAVAILABLE w/ exact root causes (train-only refit needed / H0 rows never
  exported; prior wrong not-exists claim corrected). WAVE-49 (light): h3 H0-row
  export -> 4th RAN client. OVERNIGHT SESSION HANDOFF READY (prompt delivered
  to user; NEXT_SESSION_PROMPT current; yield protocol: old session exits if a
  newer wake entry exists). Milestones: KBO live confirm ~09:30Z, US verifier
  sweep ~17-23Z, sprint ends 07-06 EOD. No edge claimed.
- SPRINT WAKE 48 (WAVE-47: REPLAY CLIENTS LIVE + HUMAN QUEUE CONSOLIDATED,
  2026-07-05 ~05:55Z, wf_9dd1add2-dcd 6 agents/~0.45M tok, commit 3fbad559):
  (1) reprocess clients v2: 7 registered incl. REJECTs (Fable policy: honest
  negatives stay replay-reproducible); positional MATCHED 0.0 + wnba elo
  2.7e-7; 5 honest UNAVAILABLE (aggregate-only history, RMSE gap, shape v2);
  lane report empty (4th reporting dud) but disk work verified directly.
  (2) HUMAN_QUEUE_2026-07-05.md: all 19 PROPOSED docs + scattered items in ONE
  digest, 6 marked superseded. WAVE-48 (light): harness metric=rmse mode ->
  umpire client RAN. NEXT MILESTONES: KBO Naver LIVE confirm ~09:30Z (reopens
  KBO in-game); US verifier sweep ~17-23Z; sprint ends 07-06 EOD. No edge
  claimed.
- SPRINT WAKE 47 (WAVE-46 + RETRO WRITTEN + HANDOFF REFRESHED, 2026-07-05
  ~05:30Z, wf_628ebbcf-70e 4 agents/~0.38M tok, commit 265f1283): (1) depth
  hook COMMITTED: optional fail-open depth_capture_fn in inplay_capture_loop,
  live-proved 45 rows through the integrated path, OFF by default -- ARMING is
  a one-line HUMAN decision (no-flag-flip rail). (2) RETRO stats verified +
  memory written (waves 30-46: 141 commits/97 lane-code, 31 verdicts, 5 null
  catches, 12 honest non-ships, 0 code failures, 34 VERIFIED claims/4 sports).
  (3) NEXT_SESSION_PROMPT rewritten to current architecture (v2 executed,
  4 method rails, live assets, open leads, human queue). NEXT WAKES: KBO Naver
  live mid-game confirm at ~09:30Z+ (reopens KBO in-game if confirmed); US
  verifier sweep ~17-23Z; wave-47 light lanes (reprocess client registration
  for new gate-row exports, human-queue digest consolidation). Sprint ends
  07-06 EOD; standard rails 07-07. No edge claimed.
- SPRINT WAKE 46 (WAVE-45 4/4 IN 11 MIN: 5TH NULL CATCH + DEPTH CAPTURE LIVE +
  KBO WALL SOFTENS, 2026-07-05 ~05:00Z, wf_3a7dcdb7-21c 12 agents/~1.01M tok,
  commits 68a01a81/c700a35a/85ecdab1): (1) umpire totals gate HONEST REJECT
  exactly as pre-registered -- real beats baseline 3/3 folds (-.00074) but
  shuffled-umpire null beats it MORE (-.00091) = flexibility artifact, 5TH
  planted-null catch; gate proven not-over-conservative via synthetic plant.
  (2) KBO synthetic params QUARANTINED w/ noise-control proof (.4515 on zero
  signal), mirrors NPB. (3) depth capture LIVE: 90 order-book rows/6 sports/0
  429s; accrual started; wiring PROPOSED. (4) Naver relay RE-VERIFIED working
  keyless w/ base-out/score (module exists from wave-22); only LIVE mid-game
  confirmation missing -> ~09:30Z KBO slate wake confirms + wires; /record
  route unexplored; memory updated (wall softened). WAVE-46: retro-stats
  collector + depth daemon-wiring evaluation; SPRINT RETRO + NEXT_SESSION
  refresh due before 07-06 EOD; KBO live confirm at the 09:30Z+ wake.
  No edge claimed.
- SPRINT WAKE 45 (WAVE-44: NPB/KBO IN-GAME = SOURCE WALL, TERMINAL + HONEST,
  2026-07-05 ~04:40Z, wf_0b0498fc-df0 6 agents/~0.42M tok, no code commits --
  evidence lanes): (1) ALL 121,537 stored ticks scanned (not sampled): pure
  Kalshi quote schema, zero game-state fields; 'phase' is a constant literal.
  NPB/KBO in-game grading CLOSED at source level until a stateful keyless
  source lands (best lead: KBO Naver api-gw per-game relay route,
  undiscovered); memory updated TERMINAL. Wave-43's KBO params (synthetic
  states) violate the synthesis-leak rail -> wave-45 quarantine lane.
  (2) vault final refresh: MLB claims re-validated on the complete corpus
  (394/821, 113/136, 102/103 rendered in dynamic caveats verbatim), 441
  dossiers, idempotent, 0 MISMATCH. WAVE-45 pivot to where power now exists:
  umpire-tendency PREDICTIVE gate (pre-registered, MATCH-not-beat, expect
  REJECT -- first NEW pregame test with genuinely new data since v2), KBO
  synthetic-params quarantine, Kalshi order-book depth capture start (charter
  4b asset accrual), Naver relay bounded keyless probe. No edge claimed.
- SPRINT WAKE 44 (WAVE-43: STATCAST 100% COMPLETE + SYNTHESIS-LEAK RAIL BORN,
  2026-07-05 ~04:00Z, wf_81f3a635-4f4 18 agents/~1.44M tok, commits c143427a/
  4414086d): (1) statcast BOTH seasons complete (2022 180/180 710,509 + 2023
  183/183 720,984 = 1.43M rows); final qualifiers platoon 394/catcher 113/
  umpire 102, claims re-validated. (2) NPB base fit = HONEST_NEGATIVE with a
  NEW METHODOLOGY RAIL: final-score-only synthesis leaks outcome (noise control
  shows +.4057 BSS on ZERO signal) -> pure-noise control now MANDATORY for any
  synthesized-state fit (memory rail #3); fabricated params deleted; REAL data
  wall = live feed frac_elapsed=None, zero real in-game states. (3) finals
  auto-refresh wiring committed (invocation gap closed permanently). (4) kbo-
  fit + wire-dispatch agents returned EMPTY (dud class, 3rd) -- subsumed by
  wave-44: raw-tick PAYLOAD inspection (46.8K/57.1K stored ticks: is inning/
  score in there?) -> states extractor -> REAL-state fits + wire if derivable,
  else honest source-wall closure. WAVE-44: tick-payload+extractor -> cond.
  fits+wire, vault refresh on final qualifiers. No edge claimed.
- SPRINT WAKE 43 (WAVE-42: NPB DATE-CORRUPTION FIXED + STATCAST 2023 COMPLETE +
  LIVE-MODEL DUD REDISPATCHED, 2026-07-05 ~03:10Z, wf_1150f4e2-9d5 10 agents/
  ~0.74M tok, commit 66284ac8): (1) CRITICAL: ingest_npb sliced MONTH not DAY
  (1505/1505 rows day==month) -- fixed + regression test + parquet REBUILT to
  3,964 correct rows; pre-fix NPB date-dependent analyses SUSPECT (memory
  updated). Results lag was pure invocation-gap (NPB/KBO scoped out of auto-
  refresh); catchup modules committed, KBO 3255 rows current. (2) statcast 2023
  COMPLETE 183/183d 720,984 rows; 2022 at 166/180; indices re-ran clean.
  (3) verifier 17 PASS/16 PENDING (await live)/1 expected FAIL; feeds GREEN;
  m1_ui flap cosmetic (133 restarts, port responsive). (4) npbkbo-live-model
  lane returned EMPTY (agent dud, 2nd occurrence) -> wave-43 redispatch SPLIT
  per doctrine: parallel npb/kbo base fits (on the REBUILT corpus) -> wire
  dispatch + replay proof; still ahead of the ~09Z slate. WAVE-43: fits+wire,
  label_finals_refresh wiring, statcast 2022 finish (14d). No edge claimed.
- SPRINT WAKE 42 (WAVE-41 4/4 PASS: NPB/KBO PREMISE CORRECTED + STATCAST SET
  COMMITTED, 2026-07-05 ~02:25Z, wf_565742a6-a32 15 agents/~1.01M tok, commits
  8fe73061/1735fb57): (1) NPB/KBO ROOT CAUSE: grades were NEVER trigger-blocked
  -- NO live model wired for npb/kbo (every tick skips no_model_prob; daemons
  healthy; 46.8K/57.1K ticks fine) + results lag 1-2d; premise memory written;
  wave-42 fits+wires per-sport in-game base models BEFORE the ~09Z slate.
  (2) statcast full set COMMITTED after the dynamic-caveat fix (corpus
  1,072,139 rows; platoon 231 qualifiers/catcher 97/umpire 97 all VERIFIED;
  2023 needs 28d, 2022 62d to complete). (3) vault: 446 entity dossiers, all
  MLB families render caveats verbatim. WAVE-42: npb-kbo live-model fit+wire
  (time-sensitive), results-lag fix, statcast continuation, verifier PENDING
  sweep. No edge claimed.
- SPRINT WAKE 41 (WAVE-40: STATCAST CORPUS REAL + M13 CLEARED + NPB/KBO GRADE
  WORRY, 2026-07-05 ~01:55Z real-clock [prior 2 wake stamps drifted +3h],
  wf_3c1379a0-2dc 13 agents/~1.18M tok, 2 commits 7461674c/0307be4c): (1)
  statcast FIXED for real (fetch/materialize split, regression test fails on
  pre-fix): 2022 2,034->412,260 rows (105/180d), 2023 306,139 (79/183d);
  platoon 0->~230 qualifiers, catcher 54->97, umpire 97; all 3 validation
  artifacts VERIFIED -- HELD on ONE surgical finding: stale hardcoded '0
  batters/ranking empty' caveat contradicts the shipped 50-row ranking ->
  wave-41 3-line fix then commit the set. (2) m13 zero-cards NOT a regression
  (manual cycle 1475 real cards via parallel path; self-healing transient
  documented). (3) vault registration + verbatim-caveat renderer committed;
  pipeline race means next regen absorbs the new artifacts. (4) NPB/KBO probe:
  capture healthy (46.8K/57.1K ticks) BUT yesterday's slate ended 12+h ago and
  grade dirs STILL absent -> trigger/finality diagnosis lane NOW, not at 09Z.
  WAVE-41: platoon-caveat fix, npb-kbo grade-check, vault regen, statcast
  fetch continuation. No edge claimed.
- SPRINT WAKE 40 (WAVE-39: UMPIRE ARM SHIPPED + 2 HELD ON REVIEW CATCHES,
  2026-07-05 ~05:15Z, wf_bed94924-86d 19 agents/~1.47M tok, 2 commits 1a2a1eaa/
  b7cde847): (1) umpire index SHIPPED: probables.parquet joins statcast 460/460
  on game_pk (no bridge), 68 umpires clear floor, leak caveat stated. (2) ask()
  tie-break fixed (deterministic + honest ambiguity list). (3) statcast lane
  HELD: found+fixed DESTRUCTIVE test-pollution bug (test clobbered prod 2023
  corpus to 4 rows!) but its cache rebuild STRANDS days after gaps (parquet 1
  day vs cache 19 for 2022) -> wave-40 finish (no live pull needed, cache
  intact: 96 days/~372K rows). (4) vault lane HELD: catcher registration
  claimed-but-undelivered -- NO catcher validation artifact was ever persisted
  (wave-38 ran validator ad hoc) -> wave-40 persists validation + registers.
  (5) m13 probe: proc fresh, bypass works, but latest snapshot 0 CARDS + SLA
  RED 705s -> wave-40 diagnosis lane (overnight empty slate vs parallel
  regression). WAVE-40: statcast-finish, vault-finish, m13-zero-cards, NPB/KBO
  pre-position probe (games ~09-10Z). No edge claimed.
- SPRINT WAKE 39 (WAVE-38 LANDED IN 22 MIN: 8/8 PASS, PROGRAM V2 EXECUTING,
  2026-07-05 ~04:20Z, wf_c88ae23d-1be 27 agents/~2.37M tok, 8 commits a71d070e..
  3f5d876b): (1) HONESTY CATCH: Statcast type=S/B/X only -> catcher metric
  relabeled out-of-zone strike-rate w/ chase confound stated (54/107 qualify,
  VERIFIED). (2) platoon HONEST_NEGATIVE: fuller seasons are 18-DAY WINDOWS not
  full seasons (0/633 clear floor) -> window extension = top unblock (wave-39).
  (3) pair-keyed contract path LIVE: tennis H2H + playstyle VERIFIED, ask()
  answers matchups. (4) verdict claims 6->16 (13 VERIFIED/3 honest MISMATCH/30
  files); found ask() tie-break bug -> wave-39 fix. (5) WNBA context: 3 parquets
  (35 officials/7276 fouls exact parity). (6) geo descriptors 3 sports; soccer
  altitude gate REJECT exactly as pre-registered. (7) reprocess clients: exactly
  1 adopted layer exists, honest UNAVAILABLE (aggregate-only history). (8)
  breaker lock: pre-fix repro lost 9/10 pings, fixed. WAVE-39: statcast full-
  season extension + index re-runs, umpire-join probe/arm, ask tie-break fix,
  vault refresh 3, m13 SLA probe. NPB/KBO verify at the first wake past 09Z.
  No edge claimed.
- SPRINT WAKE 38 (WAVE-37 LANDED + PROGRAM V2 FABLE-RATIFIED, 2026-07-05 ~03:15Z,
  wf_436f7bdf-17e 9 agents/~0.85M tok, 1 commit + 2 local-only docs): (1) m13
  sport-parallel scoring COMMITTED (cycle ~= slowest sport, 328s saved vs
  sequential-sum; runner killed for relaunch w/ new code; low-sev breaker-state
  RMW race flagged -> wave-38 lock lane). (2) injuries ingest already append-
  safe; daily wiring = PROPOSED doc + cron-ready CLI (roster not found in glob
  cap). (3) INTELLIGENCE PROGRAM V2 synthesized (Opus conductor) + RATIFIED by
  Fable w/ ONE AMENDMENT: conductor rank-7 verdict validator ALREADY EXISTS
  (5f68e9d6, 6 claims live) -> re-scoped to coverage completion (6 -> all 28
  verdicts). V2 headline ACCEPTED: predictive frontier EXHAUSTED at current
  corpora (every hypothesis CLOSED or UNDECIDABLE) -> descriptive/contract/
  infra program; power audit refused all underpowered gates; NBA in-game
  rolling-prior + all WNBA gates to watchlist. WAVE-38 (8 lanes): catcher
  framing, platoon (schema-check-first), tennis H2H/playstyle claims (pair-key
  first use), WNBA context extract, verdict coverage, geo consumers (gate arm
  expects REJECT), reprocess clients, breaker lock. NPB/KBO ~09-10Z wake.
  No edge claimed.
- SPRINT WAKE 37 (WAVE-36: BYPASS FIX VERIFIED LIVE + CONDUCTOR QUEUE EXHAUSTED,
  2026-07-05 ~02:15Z, wf_053ca842-a85 13 agents/~0.95M tok, 3 commits e6f39cb6..
  8c471112): (1) m13: supervisor reaper had ALREADY relaunched w/ fix 60s after
  commit; bypass VERIFIED LIVE (open providers skipped, all rows stamped); SLA
  honestly still RED -- scoring pass 356-800s vs 660s threshold = pure perf,
  next lever = per-sport parallel scoring (wave-37). (2) bare callers closed
  (serve.py + prop_paper.py through shared helper) -- ALL known breaker
  bypasses done. (3) vault dossiers 146->246 entities (MLB pitchers + soccer
  teams in). (4) Statcast fuller: 12 new cols/134K rows landed in-budget ->
  catcher/umpire/positioning/platoon surfaces unlocked. (5) WNBA probe: PARK
  refolds until 172+ games (~4 more); injuries ingest is single-shot -> daily
  scheduling lane. CONDUCTOR BUILD QUEUE (wave-28 program) NOW FULLY EXHAUSTED
  (all 7 build + 4 scrape items done or honestly closed) -> wave-37 runs an
  Opus conductor synthesis for program v2; Fable ratifies next wake. WAVE-37:
  m13-sport-parallel, wnba-injuries-daily, program-v2 conductor. NPB/KBO
  ~09-10Z wake. No edge claimed.
- SPRINT WAKE 36 (WAVE-35: H3 FIXED FOR REAL + 4TH NULL CATCH AT 17x + 4 SPORTS
  QUERYABLE, 2026-07-05 ~01:30Z, wf_296dde48-070 12 agents/~1.23M tok, 4 commits
  3a80e5d1..dd7f5987): (1) tennis H3 NaN-upcast null bug fixed FOR REAL
  (orchestrator re-verified artifact: n_train identical 8748/17496/26244 both
  sides; test de-vacuoused, fails pre-fix) -> NOT_TESTABLE (WTA no corpus).
  (2) NBA H_A/H_B rerun @1299 games: REJECT CONFIRMED; 2024-25 hot_night looked
  SHIP but null also beat base = 4th planted-null catch -> player-profile
  in-game class CLOSED (memory written). (3) m13 breaker BYPASS fixed (bare
  build_prop_board fallback; proof vs real circuit state); runner restart
  attempted -- 4 pool workers (23:14Z parent unfound) persist -> wave-36 ops
  lane does the proper supervisor-managed restart. serve.py/prop_paper.py bare
  callers flagged. (4) claims breadth: MLB K-rate + soccer strength top-50 both
  100% VERIFIED -> ask() now answers NBA/tennis/MLB/soccer with provenance.
  WAVE-36: m13 proper restart + SLA verify, bare-callers fix, vault-feed
  refresh 2, Statcast fuller pull, WNBA accrual probe. NPB/KBO ~09-10Z wake.
  No edge claimed.
- SPRINT WAKE 35 (WAVE-34: REVIEWERS CAUGHT A FALSE FIX CLAIM + REPROCESS LOOP
  PROVEN + BRIDGE 17x, 2026-07-05 ~00:20Z, wf_b7c4725e-0de 18 agents/~1.86M tok,
  3 commits): (1) reprocess loop COMPLETE -- rho mode + true exporters, both
  self-checks match verdicts within 1e-6 -> any intelligence change now replays
  against old games in one command. (2) tennis H3 HELD, review FAIL: fix agent
  CLAIMED null-population fix (8748==8748) but artifact shows 8748 vs 8951 --
  NaN-shuffle bug still live + keystone test vacuous; 4 findings -> wave-35
  finish lane. (3) NBA bridge: 74-game ceiling was a CODE BUG (2024-25
  linescores unread); now 1299 exact matches -> H_A/H_B pre-registered re-test
  at 17x power queued. (4) m13: stale proc restarted (62s), SLA GREEN, but NEW
  bug found: a breaker-BYPASS path still calls circuit-open providers ->
  wave-35 fix lane. (5) vault-feed 46->146 sections (tennis players in).
  WAVE-35: h3-null-fix, breaker-bypass fix, H_A/H_B rerun @1299, claims
  breadth (MLB/soccer rankings). NPB/KBO grades ~09-10Z wake. No edge claimed.
- SPRINT WAKE 34 (WAVE-33 LANDED IN 17 MIN -- FASTEST YET, 2026-07-04 ~23:15Z,
  wf_01874c65-606 15 agents/~1.35M tok, 4 commits): (1) NBA in-game H_A hot-night
  + H_B scheme-fit (pre-registered wave-26) BOTH HONEST REJECT outright -- base
  Brier .1677 vs .2357/.2404 conditioned, DM p<.001 wrong direction; real
  direction-blind bug in _planted_null_dies FOUND+FIXED during verify; thin-
  corpus caveat (74 bridged games) stated. (2) claims breadth: ATP+WTA hold
  rankings VERIFIED into ask layer; verdict claims 3->6 (2 honest skips);
  /ask-intel command LIVE. (3) tennis atlases persisted first time (408 players
  + 30616 pair-keyed H2H rows w/ provenance) -> H3 UNBLOCKED. (4) reprocess
  self-check HONEST BLOCKED: elo rows not harness-schema (gate exporter mislabeled),
  positional rows continuous (needs rho mode) -> wave-34 completion lane.
  WAVE-34: tennis H3 playstyle in-game gate, reprocess rho-mode + true exporters,
  m13 SLA verify + stale-code runner restart, vault-feed refresh (new claims),
  NBA bridge expansion (74-game ceiling raise). NPB/KBO grades = morning wake.
  No edge claimed.
- SPRINT WAKE 33 (WAVE-32 LANDED: DUAL REVIEWERS CAUGHT A REAL CONFOUND + 65%
  PROP-CYCLE CUT, 2026-07-04 ~22:30Z, wf_52a5cc51-006 18 agents/~1.63M tok,
  commits bd0fbf2c..07a64213): (1) positional-weight gate NOT_TESTABLE honest
  (overall CI naive-favoring [-.128,-.019]; BIG-group cell +.058 with 3/3 fold
  signs but CI incl 0 + replication below floor -> pre-registered re-test as
  corpus grows; naive canonical). (2) WNBA Elo refresh: ALL 3 candidates REJECT;
  dual review caught a REAL cold/warm-start confound (fake sign-flipping delta
  -> +.0002 after fix) -> gate-comparability memory written. (3) prop scoring
  2601-line cycle 1080.8s -> 371.5s (-65.6%), zero rows dropped, byte-identical
  default; with the circuit breaker, m13 SLA should go GREEN -- verify next
  probe. (4) reprocess harness v1 committed (self-check honestly BLOCKED on
  rho-shape; binary self-check queued on elo_refresh_rows). (5) heartbeat =
  stale assertion, not flake (deterministic 5 beats). WAVE-33 LAUNCHED: binary
  self-check, claims breadth (tennis hold rankings + all gate-verdict claims ->
  ask layer), NBA in-game H_A/H_B (edge-slot, spec wave-26), tennis playstyle
  persistence (unblocks H3), ask-intel command. No edge claimed.
- SPRINT WAKE 32 (WAVE-31 LANDED IN 34 MIN + SCOUT FLEET + WAVE-32 LAUNCHED,
  2026-07-04 ~21:35Z, wf_01221c03-405 16 agents/~1.53M tok + 5 Haiku scouts/
  3.5min, commits 00be9aab..5f68e9d6): (1) m13 breaker COMPLETE, live proof
  68/68 served rows carry SKIPPED_CIRCUIT (was 0/68) -> committed. (2) MLB
  velo-fatigue HONEST REJECT (real proxy LOSES to base .2137->.2177, DM p=.0023
  wrong dir) -> SP-fatigue class CLOSED, memory written. (3) soccer tier
  REJECT_ARTIFACT (3rd planted-null catch). (4) SHIPs: vault-feed staging (46
  dossier sections + 53 atlas hubs), consolidate-not-delete retention (0
  eligible until ~07-18), verdict-claims validator (3/3 real verdicts VERIFIED)
  + gate_verdict ask family. (5) ops lane: all 4 probe anomalies were STALE --
  daemon already polling wnba/npb/kbo since 07-03, resolver/bet_board fixes
  already live, beat_thread PASS; zero changes. (6) reprocess lane = agent dud
  (empty return) -> redispatched. WAVE-32 (FAST-LANE: scouted paths, dual
  reviewers): reprocess-v2, positional-weight gate (Fable design: per-posgroup
  weights vs naive, null=shuffled positions), WNBA Elo MOV refresh, prop-edge
  line budget, heartbeat flake. No edge claimed.
- SPRINT WAKE 31 (WAVE-30 LANDED + CONTINUOUS NO-DOWNTIME MODE, 2026-07-04
  ~20:20Z, run wf_56124b67-c33, 21 agents/~1.10M tok, 7 lanes COMMITTED
  cb9bd7fa..fa3f3a4c): (1) tennis surface-hold HONEST REJECT (ATP +.00012 /
  WTA +.0025 worse, 0/3 folds both tours, null died clean) -> surface-blind
  canonical, do-not-relitigate. (2) composition v1 NOT_TESTABLE (CI incl 0 both
  pops, 2025-26 replication below floor) -> naive canonical; sample-size axis
  parked. (3) WNBA rest INVALID_BASE: frozen Elo DEGENERATE on 2026 fold (BSS
  -.012) -> base refresh queued. (4) SHIPs: schema snapshots (6 pairs, 0 drift/
  16d), city-geo 631 rows (WNBA 100%, soccer 90.14%), ESPN WNBA injuries
  confirmed+ingested (41 rows), ask-anything v1 (VERIFIED-claims only).
  (5) m13 breaker HELD uncommitted -- re-review FAIL: bounded/synth served path
  drops SKIPPED_CIRCUIT + live proof missing -> wave-31 finish lane. (6) probe:
  NPB/KBO capture LIVE (18372 ticks); m1_line_daemon needs restart TONIGHT for
  wnba/npb/kbo closes -> wave-31 ops lane. USER: continuous mode + GPU/speed
  rules ratified (.planning/platform/WAVE_31_PLAN.md). Wave-31 fleet launched.
- SESSION HANDOFF (2026-07-04 ~19:50Z): session b90493cf ENDED at user request
  ("find a stopping point, pasting new session prompt"). WAVE-30 fleet STOPPED
  mid-build; partial UNREVIEWED work stashed as stash@{0} "wave-30-partial-
  UNREVIEWED" (m13 circuit breaker, tennis surface-hold gate, schema snapshot --
  7 files; nothing committed per every-ship-reviewed rule). Tree CLEAN at
  144b502d. NEW SESSION OWNS THE LOOP (boot from .planning/NEXT_SESSION_PROMPT.md):
  first actions = re-run wave-30 lanes fresh per the WAKE-30 ledger specs below
  (stash is reference only -- pop OR re-build, builder's choice after reading it;
  m13 SLA RED circuit-breaker fix is the priority), then night-slate live-
  activation verify + NPB/KBO first grades ~09-10Z 07-05. GUARD: if a scheduled
  wake fires in the OLD session (one armed for ~20:30Z), it must EXIT immediately
  without acting -- the new session owns the loop and the wake lock.
- SPRINT WAKE 30 (SCHEDULED WAKE: M13 ROOT CAUSE EXPOSED BY ITS OWN FIX + WAVE-30
  FLEET LAUNCHED, 2026-07-04 ~19:35Z, in flight wf_9ca5d74f): stop flag clear;
  verifier 16 PASS / 16 PENDING (between July-4 day and night slates -- honest) /
  2 FAIL (beat_thread cosmetic + m13 SLA RED again). m13 TRIAGE: timeout wrapper
  WORKS ("score timed out after 240s" -- the infinite hang is gone) and thereby
  EXPOSED the true root cause: dead providers called inline in the score path
  (prizepicks 403 walled, betmgm 400 broken -- BetMGM should not be hot-path at
  all per memory) burn the whole 240s budget most cycles -> snapshot rarely
  refreshes. = the exact prop_cards.py follow-up wave-22 flagged. WAVE-30 lanes:
  (1) per-provider timeouts + file-backed circuit breaker (skip dead providers,
  SKIPPED_CIRCUIT recorded honestly, manual-cycle proof required); (2) tennis
  surface-hold in-game gate (conductor rank 5, planted-null); (3) provider
  schema-drift shape snapshots (scrape-target rank 1, resilience). NPB/KBO first
  grades: next games ~09-10Z 07-05, verify next-morning wake. No edge claimed.
- SPRINT WAKE 29 (INTEL BUILD FLEET: CURRY ADJUDICATED + 2 PLANTED-NULL CATCHES,
  2026-07-04 ~19:00Z, commits 176c908e/cd9a1c61/48ecbfbc/b464018f, 10 agents /
  ~1.13M tokens, 1 fix round): (1) THE HEADLINE: predictive-validity gate = HONEST
  REJECT of shooter_quality_v1 (naive rho .4044 vs .2680 forecasting future-30d
  TS%, CI excludes 0, 0/3 folds) -> naive STAYS CANONICAL for prediction; BUT the
  face diagnostic: intelligence index ranks Curry 5/329 (Durant/LaVine top-3,
  basketball-plausible), Ellis falls 1->99 -- the index DESCRIBES shooting value,
  the naive index FORECASTS efficiency; both published, correctly labeled
  (descriptive = scouting layer, never prediction-wired). (2) WNBA extraction:
  6 atlas_wnba_* parquets from the 168-game CDN corpus, ~20 dims unblocked; Opus
  caught 2 real data bugs (turnovers sliver, cumulative pointsTotal) -> fixed vs
  real corpus. (3) contract entity_key: generalized to any entity, 12/12 VERIFIED,
  byte-identical. (4) MLB SP-fatigue: NOT_TESTABLE -- real model dm_p=.020 BUT
  planted null shows SAME improvement = flexibility artifact; false positive
  refused (2nd planted-null catch this wave). No edge claimed.
- SPRINT WAKE 28 (MULTI-SPORT INTELLIGENCE PROGRAM COMPLETE, 2026-07-04 ~18:20Z,
  6 agents / ~0.88M tokens, docs local-only): 4 sport-truth specs DONE with live-read
  numbers (MLB 35 dims/27 covered; soccer_intl 38/25; tennis 48/34 -- structural
  finding: tennis atlas is in-memory->vault-prose, never persisted to parquet; WNBA
  54/13 with 39 gaps MOSTLY zero-new-fetch from the owned CDN corpus) + STORAGE AUDIT
  (75GB/87K files; honest deviation: only 2 retention policies exist, not the 5 the
  brief claimed; uncapped line_history growth flagged; irreplaceable venue-history
  backup -> HUMAN) + OPUS CONDUCTOR program: build queue ratified (1 WNBA zero-fetch
  extraction, 2 contract entity_key, 3 NBA shooter_quality + predictive-validity
  gate, 4 MLB SP-fatigue in-game gate, 5 tennis surface-hold in-game, 6 WNBA rest
  covariate), scrape targets (1 schema-drift snapshots=resilience, 2 ESPN injuries,
  3 altitude table, 4 fuller Statcast, 5 tennis/wnba venue backfill->HUMAN), 5 spec
  fixes all none-blocking/watch, vault+memory feed design written. Verify: 17 PASS/
  1 cosmetic FAIL/16 await live games; pacing absorbed 2x 429 correctly. No edge
  claimed.
- SPRINT WAKES 26-27 (VALIDATED-INTELLIGENCE STACK SHIPPED + BASKETBALL-TRUTH SPEC +
  MULTI-SPORT PROGRAM LAUNCHED, 2026-07-04 ~17:40Z, commits 5ae26b67/9c48aa13/612fcee4,
  ~16 agents / ~1.3M tokens): (1) wave-26 stack COMMITTED after double Opus review
  (final reviewer independently hand-recomputed rank-1 from raw parquet; 9 grammar-
  injection attempts all blocked; 45 tests): player-intel producer (12 claims,
  machine-recomputable contract) + INDEPENDENT validator (12/12 VERIFIED live;
  planted errors caught; found+fixed int64-id dtype bug) + L4 LLM gate pre-registered
  (deterministic planted-null, SCOUTING_ONLY fail-action). Integration fix round:
  contract gained aggregate/window_spec/value_precision (12 UNVERIFIABLE -> 12
  VERIFIED, rankings byte-identical). (2) BASKETBALL-TRUTH SPEC (Opus researcher):
  naive composite CONFIRMED inverts (Ellis .6882 [460 FGA] > Curry .6517 [1255 FGA]);
  shooter/scorer_quality_v1 with FROZEN weights (eff .30/difficulty .30/gravity .25/
  volume .15), predictive-validity gate design (Spearman vs future-30d TS%, naive
  stays canonical if it wins), in-game hypotheses H-A/H-B specced w/ planted-null;
  gaps: no defender-distance/contest tracking, no player-level in-game feed ->
  scrape targets. (3) wave-28 LAUNCHED: 4 Sonnet sport-truth researchers (mlb/
  soccer_intl/tennis/wnba) + storage auditor -> Opus conductor (cross-sport contract,
  build queue, gap-driven scrape targets, vault/obsidian + auto-memory feed design).
  (4) PONYTAIL (user link) verified real (73.7k stars, MIT, efficiency ladder) --
  discipline injected into all fleet briefs; harness install = 2 interactive /plugin
  commands -> HUMAN QUEUE. No edge claimed.
- SPRINT WAKE 25 (SCHEDULED LIGHT CHECK-IN + LEAK-DISCIPLINE OBSERVABILITY FIX,
  2026-07-04 ~16:15Z, commit 00ec12a5, 2 agents / ~0.09M tokens): wall-clock
  accrual wake, NO fleet (correct per cadence rule -- no gate decided). Spine GREEN
  (all_ready, feeds, freshness), pacing counters LIVE (17req/0-429). Verifier now
  17 PASS / 16 PENDING (no live games at 16:00Z) / 1 FAIL (supervisor_beat_thread
  = boot_initiator provenance stamp, RESTART-PENDING: current supervisor launched
  14:16Z, its boot.ps1 fix committed 14:54Z -- all FUNCTIONAL fixes live). FOUND+
  FIXED+SHIPPED (Opus PASS): forward_evidence_scoreboard read n_forward_games_graded
  (=discovery corpus 31 for soccer_intl) not n_forward_games (=1 leak-free forward)
  -> false DECIDABLE_NOW misleading the escalation trigger; conservative fix (subset,
  cannot inflate readiness), decidable_now 2->0, MLB unchanged, +regression test,
  13 green. No edge claimed.
- SPRINT WAKE 24 (SCRAPING FRONTIER: USER Q "is scraping at the highest level, best
  webscraping systems, using githubs", 2026-07-04 ~16:35Z, commit ad8e59dd + local
  scout doc, 6 agents / ~0.53M tokens): (1) TIER-3 browser-render transport BUILT
  (browser_fetch.py on scrapling DynamicFetcher/Playwright; StealthyFetcher/camoufox
  not installed) DEFAULT-OFF (CV_BROWSER_FALLBACK), byte-identical when off; live
  probes Sofascore + WNBA-CDN + stats.wnba ALL STILL_BLOCKED with real evidence
  (403 / CloudFront AccessDenied XML / Playwright timeout = egress walls, NOT code).
  (2) OSS scout ranked the stealth frontier (nodriver 28/31 AGPL, curl_cffi 26,
  patchright 25; camoufox in maintenance gap) + per-blocked-source unlock map +
  install plan (all HUMAN/restart-window per no-install-while-running rail). HONESTY
  SELF-CATCH: scout FABRICATED a 'curl-cffi update' CLI verb (does not exist on
  0.15.0) -- Opus round-2 refused PASS, orchestrator corrected to 'pip install -U'
  + retraction framing before commit. (3) 3 real gaps recorded: browser-render tier
  (built, needs better browser pkg), single egress IP (proxy=PAID=human-only),
  global per-host rate governor (small build queued). Memory
  [[scraping-frontier-2026-07-04]]. ALSO fixed live: m1_ui orphan-node #3 on
  port 3000 killed -> all_ready; verified pacing counters LIVE (17req/0-429),
  freshness_sla GREEN. No edge claimed.
- SPRINT WAKE 23 (LEAN 3-LANE: OWN-CLOSES BACK TO 2023 + LIVENESS ISOLATION + SOCCER
  SPLIT, 2026-07-04 ~15:50Z, commits ecb11d4a/c871d175/2d63fb62, 6 agents / ~0.54M
  tokens, 1 report-crash recovered via direct Opus review -- session crash #2, both
  on StructuredOutput cap, pattern already in CHARTER_DRIFT_NOTES): (1) own NBA
  close corpus 332->663 games via NEW espn_tipoff_backfill (on-disk sources checked
  first, honestly date-only); TWO-SPLIT benchmark: 2023-24 MATCHES_CLOSE_WITHIN_
  NOISE (.23248 vs .23001), 2024-26 TRAILS_CLOSE (.20083 vs .18596) -- per-split
  honest verdicts. (2) ops/liveness heartbeat test-isolation CLOSED (bare pytest
  calls -> scratch dir; ~35 daemon callers audited byte-identical incl supervisor
  beat_self, proven empirically; 30 tests; advisory: is_live bare round-trip
  asymmetry, inert today). (3) enrichment_rows_soccer split 345->212+186 LOC,
  byte-identical proven. All 3 lanes Opus-PASS. No edge claimed.
- SPRINT WAKE 22 (NEW SESSION b90493cf: USER PRESENT -- 3 RATIFICATIONS + ATTENDED
  RESTART + 6-LANE DIRECTIVE FLEET, 2026-07-04 ~15:10Z, commits d5d78251/a5467143/
  59422469/7f3ac340/fe193537/72fcaa91, 13 agents / ~1.4M tokens, 1 report-crash
  recovered via direct Opus review): (1) boot.ps1 cycle EXECUTED attended (gov
  preflight PASS, 41 procs); verifier 15 PASS / 16 PENDING (no live games) / 3 FAIL
  all root-caused: boot_initiator = env-producer gap in boot.ps1 (FIXED), pacing-
  counter FAIL = verifier restart_ts race (self-corrected), m13 stale = unbounded
  score call (timeout wrapper shipped; stuck PID killed -> supervisor relaunched
  PID 14028 with fix). (2) xG wiring APPLIED (user-ratified): scale 0.15->1.0885;
  forward gate INSUFFICIENT_FORWARD n=1 -- pends live corpus growth. (3) OWN NBA
  close corpus (user chose build-own over $59 OddsAPI): 332 games PM 2024-11..
  2026-04, 0 leak rows, 1863 exclusions counted; benchmark TRAILS_CLOSE (.20146 vs
  .18705, honest). (4) hist-refit: WNBA anchored blend ADOPT on a 2nd independent
  corpus (all checkpoints, both directions); MLB PM recal MATCH delta=0.0 + forward
  Kalshi MATCH. (5) CQR: found already-built with honest 7-stat REJECT (a642eac5),
  REJECT reproduced live on current corpus. (6) breadth: espn_wp += wnba, NBA states
  corpus + gate run, WNBA CDN still WAF-blocked (honest), KBO Naver relay probe.
  All 6 lanes Opus-PASS. No edge claimed.
- SPRINT WAKE 21 (CONSOLIDATION: SUITE GREEN + CALIBRATION SCOREBOARD + TAIL FINAL
  MEMO, 2026-07-04/05 ~13:00Z, commits 85245194/f23495b6, 15 agents / ~1.02M
  tokens, 1 self-caught fabrication): (1) TEST INTEGRITY: 632 tests / 51 files
  GREEN, 0 regressions from the night's ~80 commits, 19/19 modules import clean.
  (2) CALIBRATION SCOREBOARD (real tooling): eval-gate 38/38 GREEN; per-sport ECE
  all IMPROVED (tennis -0.0297 largest, nba -0.0086, mlb -0.0035, soccer -0.0017);
  cross-sport OOS NBA/TENNIS/SOCCER VALIDATED, MLB honest non-beat (pitcher-blind
  gap, not fabricated). (3) restart verifier covers the full wave-15..20
  activation set (2 honest 'restart-pending' FAILs). (4) TAIL FINAL MEMO: H2 dead
  in all 6 corpora, H1 thin-pocket artifact only -> forward gates the sole
  arbiter. (5) loose-ends lane FALSELY claimed npb/kbo still blocked (read a
  pre-fix artifact) -> Opus caught it, fix confirmed the wave-20 _SPORTS entries
  ARE live (verified: ingame_live_state.py:59-60) -- the honesty gate catching
  its own stale-read. Serving spine GREEN; m1_ui churn continues (fix inert till
  restart, as predicted). No edge claimed.
- SPRINT WAKE 20 (NBA-READINESS BUILD-OUT + NPB/KBO GRADING UNBLOCKED + MLB TAIL
  CLOSED, 2026-07-04/05 ~12:00Z, commits b457e758/7f400e2e/b0ab0377/27f509d6,
  13 agents / ~1.12M tokens, 1 lane-overlap FAIL adjudicated): (1) NBA outcome
  resolver (182 real tickers) + tail gate NBA entry stamped 2026-10-01 -- opening
  night's ticks count as forward evidence from tick one. (2) NBA states gate
  PORTED (2880s regulation, cross-fit+CI, ready-for-corpus; input =
  linescores.parquet, NOT a CDN backfill -- lane 4 found cdn.nba.com hard-BLOCKED
  at all tiers). (3) NPB/KBO grading BLOCKER CLEARED: _SPORTS now has npb/kbo via
  a new live-state source (coarse score+status = enough for outcome grading);
  activates at daemon restart. (4) MLB PM BACKFILL CLOSED (exhausted at natural
  edge, 2731 games / 7.33M ticks to 2026-06-29): H1 n=1630 + H2 n=1900 BOTH
  CALIBRATED -> FINAL historical-tail word: every corpus CALIBRATED except the
  thin PM-2023 H1 pocket (n=14) -- the prior is firmly 'no persistent venue tail
  bias; forward gates decide'. Ledger + scoreboard rebuilt. No edge claimed.
- SPRINT WAKE 19 (STRUCTURAL GAPS SURFACED: NPB/KBO LIVE-STATE + NBA READINESS +
  FORWARD-EVIDENCE VIEW, 2026-07-04 ~11:00Z, commits ac013fd9/a90c35d8, 15 agents /
  ~1.12M tokens): (1) NPB/KBO grading BLOCKED at root -- ingame_live_state._SPORTS
  has NO npb/kbo entry -> every tick hits no_live_state, never grades (capture
  healthy: 18K+ npb ticks; resolvers 23/23 tests green but never exercised). No
  ESPN equivalent -> needs a live-in-progress scraper (npb.jp/koreabaseball or
  Naver); honest DEFER -> wave-20 build. (2) Forward-evidence scoreboard SHIPPED:
  mlb tail forward_n=5 (5d to floor), soccer_intl 31 DECIDABLE, rest off-season
  zeros. (3) NBA READINESS audit: gaps = DEFAULT_SPORTS lacks 'nba', no
  nba_outcome_resolver, tail-scan-multi lacks 'nba', states_gate ports cleanly
  -- all buildable in safe areas before Oct. (4) enrichment first-fruits:
  book_depth stale-flag 1.6% on a fuller slate (vs 91% thin), soccer GATE-A
  n_joined=19, gumbo stale (blocks GATE-B) -- grade-row persistence not yet
  exercised (live-game gap, not code). (5) MLB PM backfill still running (~11mo
  short); partial stays CALIBRATED. No edge claimed.
- SPRINT WAKE 18 (SUPERVISOR STORM FIXED AT ROOT + ENRICHMENT PERSISTED + WNBA SHADOW
  LIVE-VERIFIED, 2026-07-04 ~10:15Z, commits a8de869a/dad0bc29/290588a4, 10 agents /
  ~0.92M tokens, ui lane report-crash #4 but its artifact survived intact):
  (1) supervisor: 41 serial probes x 2s vs 90s threshold = the whole 65-event
  wedge storm -> beat thread (m13 precedent) + 300s threshold + initiator stamp;
  inert until next boot. (2) m1_ui = GENUINE_APP_CRASH_LOOP: stale node orphans
  (watchdog-kill survivors) hold port 3000 (2,288 EADDRINUSE) -> orchestrator
  killed the current orphan (2nd occurrence; the supervisor fix stops the
  orphan factory); PROPOSED env-gated UI-off diff in the triage json (user
  request). (3) enrichment persists into grade rows + sidecar retention
  (archive-never-delete) shipped. (4) KBO parser 0-0-placeholder bug fixed
  before first finals; WNBA SHADOW FIELD VERIFIED on 3 real live games; NPB/KBO
  finals still pending (games in progress at check). (5) MLB PM backfill still
  running in background; validation deferred to completion. No edge claimed.
- SPRINT WAKE 17 (429 PACING FIXED + SUPERVISOR SELF-WEDGE ROOT-CAUSED + RESOLVER
  FABRICATION BUG CAUGHT, 2026-07-04 ~09:00Z, commits b396f67c/8f2149c1/39e2866c,
  13 agents / ~1.14M tokens, 1 LOC-trim fix round): (1) Kalshi 429: 17-req/cycle
  bursts + silent swallow -> stagger + Retry-After cooldown + counters; activates
  at the m2 bounce (with the grade-writer fix). (2) API dual-crash = chronic
  SUPERVISOR SELF-WEDGE cascade (watchdog killed/relaunched m9 five times
  07:08-07:18Z; 36 wedge events since 06-23; boot sweep reaps children) --
  threshold/robustness fix queued; explains the m1_ui flap history. (3) NPB/KBO
  day one: 51K ticks combined, settle+grading wired; resolver neighbor-day
  FABRICATION bug reproduced live + fixed BEFORE any grade consumed it.
  (4) MLB PM gap backfill running in background (~349-day gap; validation
  deferred to completion). (5) Enrichment persistence: option (b) additive,
  GATED on a sidecar retention policy (Fable accepted; queued together).
  No edge claimed.
- SPRINT WAKE 16 (CLOSING ARC: RETRO + DRIFT NOTES + HONEST NULLS + APIS AUTO-
  RECOVERED, 2026-07-04 ~07:30Z, commits a65cd636/9a2986e3, 11 agents / ~0.89M
  tokens, 5/5 PASS): forward check -- ALL 6 sports ticking live (tennis/wnba/npb/
  kbo first ticks confirmed), MLB forward_games=5 rising, book_depth flowing;
  :8099+:8098 died ~07:05Z and the SUPERVISOR AUTO-RECOVERED both (fresh PIDs,
  200s -- resilience working; root-cause queued); Kalshi 429 rate-limit cycles
  observed on the widened 6-sport capture -> pacing lane queued. PM completed to
  budget: NBA n=1056+/band, MLB n=685+/band -- ALL CALIBRATED, tail-bias prior
  firm. States gate CI hardening: honest NULL (0/6 cells survive). Retro
  written (15 wakes/181 agents/17.46M tokens/64 commits/0 code FAILs at
  snapshot) + CHARTER_DRIFT_NOTES_2026-07-04.md (7 items for the 07-10 review).
  Sprint retrospective memory saved. No edge claimed.
- SPRINT WAKE 15 (RESTART CONFIRMED DONE + GRADE-WRITER FIXED + xG STORY COMPLETE +
  TAIL PRIOR SETTLING, 2026-07-04 ~03:30, commits 25e2ff11/87042bf7/602d394b/fcd9d37c,
  10 agents / ~1.09M tokens): (1) RESTART AUDIT: boot.ps1 cycle CONFIRMED 2026-07-03
  23:11 (13/13 PIDs in 51s window) -- m33-m37 + capture widening + kalshi fix ALL
  LIVE; digest corrected (the ONE human action is DONE). Residuals found+handled:
  orphaned pre-restart node held port 3000 (m1_ui 34-restart flap) -> orchestrator
  killed the orphan (evidence-verified, charter-allowed) -> m1_ui READY clean;
  m13 self-recovered. (2) GRADE-WRITER ROOT CAUSE: frac_elapsed saturates 1.0 in
  bottom-9th/extras -> model rejected every late tick (the 21.8% truncation
  class); clamp fix + heartbeat observability shipped -- m2 runs old code until
  its next restart (queued as optional bounce). (3) xG COMPLETE: cross-fit
  BETTER both directions BUT NO_ADD_BEYOND_MARKET -- xG catches our model up to
  venue, does not beat it (honest WORSE->MATCH win; PROPOSED wiring -> human
  queue). (4) PM resumed: NBA 908 games thru Nov-2025 + MLB 397, H1/H2
  CALIBRATED everywhere; ledger 6 corpora, H1 synthesis: only the thin PM-2023
  pocket significant -- prior shifts toward no persistent venue tail bias;
  forward gates arbiter. (5) wnba-states-gate crashed on report (3rd time) --
  direct Opus review running. No edge claimed.
- SPRINT WAKE 14 (FIRST xG WIN + NEW PROCSPECS FOUND LIVE + PM 2024+ CORPUS + WNBA CDN
  UNLOCKED, 2026-07-04 ~02:00, commits b9c32708/4ad1dccc/a65dfd93/cfbc0492, 11 agents
  / ~1.07M tokens, 0 fix rounds, 5/5 PASS): (1) GATE A VALIDATION = BETTER_THAN_
  BASELINE both md5 halves (xG conditioning, unfitted, reconstructed corpus n=29;
  half0 delta -0.0173 CI excl 0) -- the first real soccer WORSE->MATCH datapoint;
  strengthen honestly next. (2) LIVE FINDING: m33-m37 heartbeats FRESH, 41 procs,
  kalshi pregame flowing for wnba/npb/kbo -- new ProcSpecs are RUNNING (restart
  done or hot-loaded; wave-15 audits, human queue may already be satisfied).
  (3) m2 triage: narrow per-game grade-writer SUSPECTED_WEDGE (raw ticks flow,
  grade file frozen); systemic proxy 21.8% (29/133) truncated before I9 ->
  grade-writer fix queued (affects verdict corpora). (4) PM 2024+ slug family
  found: +583 games/1.58M ticks backfilled (cursors resumable), all bands
  CALIBRATED; WC-2022 confirmed nonexistent. (5) WNBA CDN yields to STEALTH:
  168 games, 504 checkpoint states (bonus/timeouts/run). No edge claimed.
- SPRINT WAKE 13 (BACKFILLS EXHAUSTED + EVIDENCE LEDGER + GATE PRODUCERS, 2026-07-04
  ~01:00, commits da092442/60b7976b/707639c6/19e2ef57/c8cbb591, 11 agents / ~1.06M
  tokens, 0 fix rounds, 5/5 PASS): PM NBA-2023 backfilled (435 games/1.10M ticks)
  -- BOTH bands CALIBRATED (H1 +0.086 CI incl 0); Kalshi backfill EXHAUSTED both
  sports (MLB 1600 mkts to 04-27, NBA 106 playoffs) -- ALL bands CALIBRATED.
  TAIL LEDGER live (28 rows, 4 corpus classes): H2 likely dead; H1 = thin
  PM-MLB-2023 pocket only; forward gates decide. DIGEST_2026-07-05.md written.
  Gate producers wired: soccer xG (first real n=19 joined, 1 game, honest
  INSUFFICIENT) + MLB base-out via pk bridge (n=0 tonight -- m2 capture ticks
  stalled 04:31Z while a game ran; heartbeat fresh; wave-14 ops triage,
  no-kill per charter). No edge claimed.
- SPRINT WAKE 12 (HISTORICAL BACKFILLS + TAIL EVIDENCE SYNTHESIS, 2026-07-05 ~00:30,
  commits fe982589/6843db17(incl kalshi lane via add-chain quirk)/789b87a1/a8b67fb3,
  11 agents / ~1.1M tokens, 0 fix rounds, 5/5 PASS): TAIL HYPOTHESIS STATE AFTER
  4 CORPORA -- H2 (mid-fav overpriced) LIKELY DEAD: CALIBRATED on PM-2023 (n=138)
  AND on Kalshi discovery-excluded (n=799, all 8 bands calibrated); H1 (longshot
  underpriced) THIN CROSS-VENUE SUPPORT: PM-2023 VENUE_UNDERPRICES (realized .523
  vs price .155, CI excludes 0, n=14, one half INSUFFICIENT) -- rides on the
  forward gates now. Corpora: PM 2023 pilot 744 games/1.83M ticks (dailies are a
  2023-only pilot, NOT multi-season -- premise corrected); Kalshi 1194 markets/
  2.16M candles to 05-20 (tranche 2 resumable). WTA odds 8,054 rows ingested +
  WTA close gate honest BEHIND (+0.0173, efficient-market expectation). Prop
  channel = CORRECTLY-SILENT (clv_guard by design on the -31% prior; KEEP ->
  human queue). espn_wp arm un-inerted (event id in state) + 18/36 fuzzy-resolved
  (18 rest = future games). No edge claimed.
- SPRINT WAKE 11 (ENRICHMENT LIVE-WIRED + GATES PRE-REGISTERED + 126 ROWS CLV-GRADED,
  2026-07-05 early, commits 9dc59af2/c1b65e1a/c044490e/92a08226/03daf447, 11 agents /
  ~1.03M tokens, 0 fix rounds, 5/5 PASS): enrichment facade wired into capture ticks
  (decision-identity proven on/off/poisoned; espn_wp arm inert pending event-id
  resolution -- wave 12); game-pk bridge live 13/13 ESPN + m37 ProcSpec; 3 feature
  gates pre-registered with fixture-proven judges (soccer xG / MLB base-out /
  stale-quote); WNBA line-shopping LIVE (4 shoppable, 3 books, real gap rows);
  scan_ledger dup fix DIRECT (296 false positives -> genuine count); KX proxy
  closes graded 126 previously-ungradeable in-game rows (close_kind=last_tick
  labeled; mean +6.08%/median -21.65%, calibration measurement). ALSO:
  historical-odds scout adjudicated -- POLYMARKET = multi-season intra-game
  goldmine (1-min paths to 2023), Kalshi candles rich but ~2-3mo deep, WTA odds
  gap fillable, OddsAPI human brief queued. No edge claimed.
- SPRINT WAKE 10 (DATA-BREADTH BUILD: 5 SCOUT-DERIVED INGEST LANES ALL SHIPPED + FIRST
  EXTERNAL BENCHMARK, 2026-07-04 late night, commits 61c62782/d36b07c5/ebad9e01/
  35eb8a57/4261507c, 11 agents / ~1.04M tokens, 0 fix rounds, 5/5 PASS; scout fleet
  = 7 more agents earlier): (1) FotMob live xG ingest -- 3 REAL live matches
  captured (WC + NWSL) with as-of no-leak discipline; shape bug found live
  (general block, not content). (2) MLB GUMBO -- 7 live games 0 errors; reality
  check: diffPatch returns FULL snapshots in this deployment (fullUpdate = the
  norm); fielding-position trap confirmed with named players and test-locked.
  (3) Venue depth-of-book (Kalshi orderbook+trades + PM CLOB) -- live run 110
  snapshots, honest 91%-stale-on-thin-slate context; gamma cache never read.
  (4) WNBA CDN ingest -- code fixture-proven; egress WAF-blocked this session
  (recorded, zero fabricated rows). (5) ESPN WP reference + FIRST THREE-WAY
  BENCHMARK on 98 games / 27,772 ticks: our model Brier .18602 vs ESPN WP
  .18771 vs venue .18133 -- we narrowly beat ESPN's own reference model, venue
  lowest (consistent with MATCH; NO edge claim). All sidecar/measurement-only;
  ZERO capture-loop edits (wire specs documented per module). Source recipes +
  reality-checks saved to memory reference_ingame_data_sources_2026_07_04.
- SPRINT WAKE 9 (FULL FLEET: PROP-CLOSE MYSTERY SOLVED + WNBA 3 BOOKS + DRAW PRICES
  LIVE + LEDGER EXONERATED + FRESHNESS AUTO-WIRED, 2026-07-04 night, commits
  bc40e46e/caa6b867/61263ade/7c44c190/fce73b78, 11 agents / ~0.88M tokens, 0 fix
  rounds, 5/5 PASS): (1) draw-key carried through to the board -- live soccer Draw
  prices attach 8/10 events. (2) WNBA books 1 -> up to 3/game (ESPN-DK pickcenter,
  Pinnacle league 578, FanDuel customPageId=wnba -- all live-probed before wiring);
  best_price_scan wnba widen queued. (3) PROP CLOSES: 0/180 was STRUCTURAL --
  capture was FanDuel-only and FanDuel posts ZERO MLB player props (proven live);
  +DraftKingsV2 -> 48 real prop closes captured tonight; NEW finding: paper_
  ingame_prop channel has 0 rows EVER (trader wired, never places) -> queued.
  (4) ledger DIRTY exonerated: 0 genuine dups (coarse-key false positives; index
  sidecar ready), 0/326 CLV-backfillable (200 props categorical + 126 Kalshi-
  ticker id-space structural -> ticker-keyed close capture queued). (5) freshness
  adjudications auto-refresh on the m36 tick (every 32nd, 9.68s, verified
  matching waves 7-8). ALSO: user directive un-parked IN-GAME DATA BREADTH
  (charter iv, commit 5c576023) -- 6-scout read-only probe fleet running against
  official live feeds + sports-app APIs + orderbook depth; wave 10 builds the
  Opus-ranked winners. No edge claimed.
- SPRINT WAKE 8 (FULL FLEET: BOTH FLAGSHIP FINDINGS ADJUDICATED + WNBA/SOCCER PRICING
  FIXED LIVE, 2026-07-04 night, commits ca89e485/fdbcb38a/9ebd0da2/5221cde4 + tail-
  prereg pending direct Opus review after 2nd builder report-crash, 10 agents /
  ~0.94M tokens): (1) WNBA resolver map grounded on 330 real tickers -- 5/5 of
  tonight's games price live (was 0/2); 15 franchises, 210/210 collision-free.
  (2) soccer board 1X2 attach 0/8 -> 8/8 live; NEW upstream gap found: aggregate
  to_odds_lookup drops the 'draw' key (wave 9). (3) SOCCER TRUST RE-RUN:
  BACKFILLED variant H1+H2 ADVERSE-REPLICATED (all schemes, CIs exclude 0); RAW
  floor-limited INSUFFICIENT; PROPOSED suppression doc upgraded to 'evidence bar
  met, human decision requested' (diff UNAPPLIED; exposure still zero units).
  (4) MLB FRESH-TRUST: wave-7's I4-I6 fresh-only WORSE does NOT replicate
  (NOT-REPLICATED/INSUFFICIENT everywhere) -- same single-fold failure mode as
  WAKE-27's BETTER; drift memo written; honest bottom line: NO evidence the MLB
  in-play model beats or trails the venue in any segment under replication.
  (5) tail-prereg lane crashed on report (code landed: per-sport stamps
  wnba/npb/kbo @ 07-04T12:00Z, existing sports byte-identical) -- direct Opus
  review running. No edge claimed.
- SPRINT WAKE 7 (FULL FLEET: MLB IN-PLAY 'BEATS VENUE' STORY FULLY DEAD + SOCCER UNK
  KILLED BOTH DIRECTIONS + NPB/KBO PRICE LIVE + RESTART VERIFIER, 2026-07-04 early,
  commits 37c91463/59bbb4a6/dd0620fb/8e2e6ba1 + 10e33afa (npb-kanji, direct-Opus-
  reviewed after builder crash), 11 agents / ~1.04M tokens, 0 fix rounds, 5/5 PASS):
  (1) soccer minute/half state fixed (stoppage '+N' ValueError + halftime HT
  unparseable were the root causes) -- live-verified on a live WC match; future
  ticks segment-labeled. (2) QUOTE-FRESHNESS CONTROL: MLB fresh_share only .218
  (stale runs to 337 ticks); I4-I6 FLIP raw=MATCH -> fresh_only=WORSE_THAN_VENUE
  (CIs>0); PREMISE CORRECTION: current raw MLB verdict is ALL-MATCH -- the WAKE-27
  I5-I9 BETTER did not survive corpus growth. Soccer WORSE robust to control.
  (3) pricing verify: NPB 6/6 + KBO 5/5 priced LIVE end-to-end; WNBA pricing
  BLOCKED by missing team_resolver map (Kalshi city-only labels) -- wave-8;
  soccer bet_board '1X2'-vs-'Moneyline' group mismatch found (wave-8); close
  capture for new sports = pure pending-restart cost (quantified: 0 possible);
  MLB tail gate 5 forward games accruing. (4) post_restart_verify one-command
  pack (found+fixed :8099 /health readiness bug). (5) UNK backfill: 22/22 games
  salvaged deterministically (sidecar, +/-10min buffer, 20.7% excluded);
  WORSE_THAN_VENUE robust in raw AND backfilled variants. No edge claimed.
- SPRINT WAKE 6 (FULL FLEET: SOCCER SUPPRESSION HONESTLY NOT ACTIONABLE + NEW PROPS
  STANDING BASELINE + LABEL-STALENESS GUARD + DAY-2 DIGEST, 2026-07-03 late night,
  commits 9a024be9/6994ed71/79d824e1 + npb-kanji pending review, 12 agents / ~1.08M
  tokens, 1 stub-report fix round + 1 lane crash): (1) SOCCER TRUST ADJUDICATION =
  INSUFFICIENT, not adverse-replicated: md5 halves are 6+6 games (floor 8); the only
  replicating WORSE bucket is UNK -- a CAPTURE ARTIFACT (22/40 games have no
  minute-level state, bare 'live' placeholder); exposure quantified = ZERO units
  (all 32 soccer paper_ingame rows carry stake_units=0.0); venue-quote STALENESS
  is a live alternative explanation (only 10-40% of ticks carry a fresh
  market_prob, stale runs up to 62 ticks); PROPOSED reversible suppression diff
  written to docs/research/organization-sprint/ but explicitly recommends NOT
  applying yet. Segment-trust does NOT gate soccer execution today (MLB-only
  hook) -- known, quantified, zero-stake. (2) props shootout #2: league_shrunk
  (k fit on fit-window only) = STANDING BASELINE, wins all 3 props both
  holdouts; EW re-rejected independently; prev-season new REJECT. (3) label
  staleness guard: bounded finals refresh on the m36 tick + freshness_sla rows
  for ALL label artifacts. (4) DIGEST_2026-07-04.md written (120 lines, verified
  no retracted numbers). (5) npb-kanji lane CRASHED on structured-output cap --
  orphaned diff under direct Opus review before any commit (charter: every ship
  reviewed). No edge claimed.
- SPRINT WAKE 5 (FULL FLEET: WNBA SHADOW LIVE ON A REAL Q4 GAME + SOCCER 3-WAY + TWO
  BIG HONEST VERDICTS + KBO PAPER LIVE-READY, 2026-07-03 night, commits 25216d37/
  9afb9f31/635a4abc/25638f2f/30e0cbf9, 13 agents / ~1.28M tokens, 1 fix round
  (LOC-split only), 5/5 PASS): (1) wnba live-state route + pre-existing basketball
  clock gap fixed; LIVE-verified on NYL-MIN Q4 (shadow p=0.9815 through the exact
  capture path). (2) kalshi 3-way KXWCGAME -> soccer_intl pregame 0->8 events
  live; consumers proven draw-safe. (3) MLB props eval on the 5-season corpus:
  EW projections WORSE than season-to-date mean at CRPS for Ks/hits/walks in
  BOTH holdouts -- honest REJECT of the EW design; no historical prop lines on
  disk so no market comparison (recorded). (4) npb/kbo board + paper channel via
  kalshi_listing; KBO odds-match fixed live (4 real paper bets recorded in the
  live test cycle under existing gates); NPB = honest kanji-map limitation
  (queued). (5) soccer resolver: 2 compounding root causes fixed, n_labeled
  8->30, and the FIRST real soccer in-play verdicts landed: H1+H2 both
  WORSE_THAN_VENUE (model brier .31/.42 vs venue .15/.26, CIs exclude 0) ->
  suppression recommendation queued for cross-corpus trust + human. No edge
  claimed anywhere.
- SPRINT WAKE 4 (FULL FLEET: KALSHI PREGAME BUG FOUND+FIXED + WNBA PAPER CHANNEL LIVE-
  READY + NPB/KBO IN-PLAY + TENNIS ZERO GAPS, 2026-07-03 night, commits d68d0df7/
  1721c148/19aa2348/44a37adc, 11 agents / ~1.26M tokens, 0 fix rounds, 5/5 Opus PASS):
  (1) settle_stamp had a SECOND bug (production ev = flat settled_finals dict ->
  None for EVERY sport on that path) -- fixed 3-shape; WTA dual-board merge
  (found _scoreboard_url never honored league=); WNBA ticker map rebuilt from
  330 REAL tickers (no HHMM; Kalshi city shorthand GS/WSH/NY/LA/PDX/CONN):
  326/330 resolve, 314/318 match parquet labels. (2) WNBA pregame paper channel
  wired end-to-end (predictor_jd->predict_matchup->bet_board->live_board->
  paper_today; honest no-odds degrade verified; live p=0.6914 on real corpus);
  npb/kbo board = honest gap (needs kalshi-derived listing machinery). (3)
  npb+kbo in-play capture-only (model_prob honestly None -- zero placement) +
  resolvers grounded on 44 real tickers (NO home/away signal from Kalshi --
  first-code=away convention) + WNBA shadow (sp_shadow contract; logs None
  until live_state gets a wnba route -- wave 5). (4) BIGGEST FIND: Kalshi
  pregame fetch() returned 0 events for EVERY sport (no series_ticker filter,
  exact-match required, masked by aggregate) -- fixed + live-verified mlb
  0->47, wnba 0->6, npb 0->6; snapshot daemons +wnba/npb/kbo; CLV path proven
  sport-blind. (5) ops-verify: every sprint module ran live, 129/129 targeted
  regressions, sprint_status.json + 9-step restart checklist composed. ONE
  supervisor restart activates everything. No edge claimed.
- SPRINT WAKE 3 (FULL FLEET: KBO SHIPPED + TENNIS TRULY FIXED + MULTI-SPORT GRADING +
  WNBA BLEND WINNER + PAPER ENABLEMENT, 2026-07-03 night, commits 933d9302/bb8bb567/
  e44255a6/e1c8258a/5de5e850, 11 agents / ~1.26M tokens, 0 fix rounds, 5/5 Opus PASS):
  (1) KBO end-to-end: 3,250 games 2022-2026 (recipe correction: teamId= empty
  REQUIRED; gameMonth='' = whole season in 1 request); gate honest PARTIAL (2024
  trips BSS_MIN degenerate guard, 2025+2026 beats both baselines); KXKBOGAME/
  SPREAD/TOTAL wired, RFI honestly unwired (no market_type fits). (2) TENNIS real
  root cause: ESPN tennis nests matches in groupings[] -- flat iteration returned
  ZERO matches; live_state + settled_finals fixed (team sports byte-identical);
  settle_stamp.py same-class gap + WTA path -> wave-4. (3) m36 grading-multi:
  outcome verdict + segment trust for soccer_intl/tennis/wnba (soccer 7 games =
  INSUFFICIENT_DATA floor-honest; wnba ticker regex ASSUMED -- validate vs real
  ticker queued). (4) WNBA blend: pre-declared 4-family shootout fit on 2024 only
  -> ANCHORED (k=.63, 1/sqrt(min) scaling) wins 6/6 checkpoints on BOTH 2025 +
  2026 OOS (pooled Brier .1589/.1685 vs fixed .2223/.2303) -- adopted; internal
  baselines only, NO market claim. (5) Enablement: npb pregame kalshi hint;
  feed_health 5->7 sports; WNBA in-play settle arm wired (bets could never
  settle); honest gaps recorded (to_jd pregame seam missing for wnba/npb;
  best-price needs >=2 books). No edge claimed anywhere.
- SPRINT WAKE 2 (FULL FLEET: 3 HONEST REJECTS + 2 NEW SPORTS CLOSER + TENNIS CAPTURE
  UNBLOCKED, 2026-07-03 eve, commits 902afdf5/07c78018/37bc2a40/3aede182, 13 agents /
  ~1.23M subagent tokens, 1 fix round): (1) REPLICATION GATE: all 3 wave-1 m19
  survivors REJECT cross-corpus (wta_hold 1/4 significant sub-corpora, soccer
  diff_sot_for 2/4, diff_shots_for 2/4 vs >=3/4 bar; all improve same-sign but
  significance does not replicate) -- single-fold fragility caught by the
  discipline, nothing wired, human queue stays clean. (2) NPB END-TO-END: 1,505
  real games 2022-2026 scraped politely from npb.jp; gate CALIBRATION_BASELINE_OK
  but WEAK-honest (bss_vs_coin .006/.008); draws excluded ~3%; KXNPBGAME+SPREAD
  wired; Opus initial FAIL was a stub REPORT (code verified clean), fix+re-review
  PASS. (3) TENNIS: resolver verified vs Kalshi settlements (>=92/100, 0
  mismatches); DEFAULT_SPORTS now +tennis+wnba (activates at pending restart);
  paper-settle routes tennis; FOUND 2 shared-file bugs (ingame_live_state +
  settled_finals read 'team' but tennis carries 'athlete') -> wave-3. (4) WNBA
  IN-GAME: blend + predict_live shipped, calibration check on 150 real games =
  naive score-diff sigmoid BEATS fixed blend at half/Q3 (.1915/.1606 vs .2316/
  .2318) -- recorded honestly, refit on >=2 corpora queued. (5) KBO LABELS
  SOLVED: exact asmx recipe (form-urlencoded + load-bearing Referer; 200-with-
  error-page trap documented), 147 games parsed 2025-05, depth to 2001, 10-team
  EN<->KR table -> build lane queued. Scoreboard probe: 32/32 READY, 0 reds,
  MLB 975K ticks / tennis 112K / soccer 275K captured today. No edge claimed.
- SPRINT WAKE 1 (FULL FLEET: 4 SHIPS + 1 PROBE, ALL OPUS-PASS, 2026-07-03 pm, commits
  71073874/bacfd223/3546dcb6/b4c1d7ec, 11 agents / ~1.2M subagent tokens, sprint rail
  LIFTED per user directive): (1) RELIABILITY: m33 http_wedge_reaper (kill ONLY on
  >=3 consecutive >10s HTTP timeouts on LISTENING port AND cpu>50%>2min; the :8099
  wedge class) + m34 freshness_sla (per-daemon SLA table, missing entry=NA never
  GREEN) -- RESTART PENDING to activate. (2) WNBA END-TO-END: 768 labels (2024-2026),
  Elo fit on 2024 only, gate on 2025+2026 independently = CALIBRATION_BASELINE_OK
  (brier .2195/.2341 vs coin .25), close-comparison honestly PENDING (capture starts
  at daemon re-import); Kalshi KXWNBAGAME/SPREAD/TOTAL live-verified wired,
  KXWNBATEAMTOTAL probed 404 excluded; in-game deferred (NBA blend hardcodes 2880s).
  (3) IN-PLAY MULTI: cross-sport tail scan (tennis n=0 -- capture NOT started,
  DEFAULT_SPORTS lacks tennis = REAL GAP queued; soccer_intl 7/39 graded) + H1/H2
  forward gates PRE-REGISTERED 2026-07-04T00:00Z (orchestrator tightened builder's
  07-06 stamp, +2 forward days, zero discovery contamination) + tick-latency
  scoreboard (mlb GREEN p50=29s n=47K ticks; venue ts absent -> lag honestly
  NOT_AVAILABLE) as m35. (4) m19 WIDENED 6->11 candidates: WTA hold SHIP_REVIEW
  (truncation control FLIPS -- downgraded correctly), soccer diff_sot_for +
  diff_shots_for single-corpus SHIP (dm_p .030/.049, NOT wired, replication queued),
  2 honest REJECTs, 6 prior candidates byte-identical. (5) KBO/NPB PROBE: both
  FEASIBLE-WITH-GAPS; Kalshi KXKBO*/KXNPB* + Pinnacle ids (KBO 6227, NPB 187703)
  LIVE; ESPN + statsapi both DEAD ENDS for labels (statsapi sportId=32/31 = stub
  rosters, zero schedules); NPB-first (npb.jp HTML 2018+ scrapeable, no auth);
  biggest gap = historical price corpus (present-only venues). No edge claimed;
  paper/measurement only; local commits only.
- WAKE-34 (IN-PLAY EVERY-LINE WIDENING + IN-PLAY QUALITY SCOREBOARD, 2026-07-03, commit
  021e3712, Fable-planned / 2 Sonnet executors): user directive "ingame knows every little
  line and data it can get, AI independent". AUDIT FOUND: in-play capture was Kalshi
  MONEYLINE ONLY (195K rows/1 venue/1 market type) and had NO TENNIS AT ALL during
  Wimbledon while Kalshi listed open KXATPMATCH/KXWTAMATCH; Kalshi also quotes in-play
  MLB total/spread/team_total + WC spread/team_total we never asked for. SHIPPED:
  (1) kalshi_series_spec.py per-sport (series, market_type) map -- mlb 4 series, tennis
  ATP+WTA, WC 3, NBA spread pre-wired for Oct; line from real floor_strike/cap_strike;
  per-series failure isolation; in-play default transport = resilient_get_json (stealth
  tier). (2) CONSUMER SAFETY SWEEP (the critical half): moneyline filters added to
  inplay_capture_loop._yes_pair + pm_game_placer.group_by_game so a total/spread prob is
  NEVER ingested as a win prob (protects m32 tail gate + all grading); 8 consumers
  audited. (3) inplay_capture_quality.py scoreboard (ticks/games/market-type breadth/
  tail share/live-window gaps, verdict vs yesterday) every m30 tick ->
  data/frontend/ops/inplay_capture_quality.json. Live smoke: mlb 250 ticks across 4
  market types, tennis 41 ATP/WTA ticks. 116 tests green / 9 per-file runs. Known
  pre-existing failure test_inplay_aggregate_grade.py (grade-dir grew past MIN_GAMES,
  reproduces on stash -- unrelated). Coverage only, no accuracy/edge claim.
- WAKE-33 (SCRAPING NEVER-DIES: STEALTH TRANSPORT + LEAGUE RESOLVER + CAPTURE SCOREBOARD,
  2026-07-03, commits d96bbebe + 88ed9943, Fable-planned / 3 Sonnet executors): user directive
  "odds webscraping must run independently+perfectly, multi-book, constantly refreshing" citing
  github.com/d4vinci/Scrapling. (1) stealth_fetch.py + transport.py: scrapling 0.4.9
  browser-TLS-impersonated fallback -- plain urllib first, escalate ONLY on blocked-shaped
  failure (401/403/406/409/429/451/503/HTML-wall), per-host 6h-TTL stealth-first memory,
  kill switch CV_STEALTH_FALLBACK=0; wired into http_cache default path (injected test
  fetchers untouched). (2) FOUND+FIXED live outage: tennis captured ZERO all July (during
  Wimbledon!) -- Pinnacle league id 12 delisted (401) and live Wimbledon ids rotate per
  round; NEW pinnacle_league_resolver.py resolves ids dynamically (ATP+WTA filter, 1h
  cache, 401 auto-invalidate) -> tennis restored, 22 games/132 quotes first tick, daemon
  autonomously writing. (3) feed_health widened 2->5 sports + heal() auto-marks
  auth-blocked provider hosts stealth-first each m30 tick; capture_quality.py scoreboard
  (rows/games/venues/tail-share/max-gap + GREEN/REGRESSION vs yesterday, elapsed-
  normalized) wired into m30 -> data/frontend/ops/capture_quality.json; flagged a REAL
  soccer rate drop day one. GOTCHAS: daemons run conda basketball_ai which is Py3.10.20
  (CLAUDE.md "Py3.9" is STALE) -- scrapling[fetchers] installed BOTH envs; daemon restarts
  required for new code (supervisor auto-relaunches on terminate); scrapling bumped anyio
  4.12->4.14 in conda env, API :8099 verified healthy after. 164 tests green across 12
  per-file runs; live 5-sport feed health ALL GREEN incl pinnacle/tennis. Coverage
  measurement only, no accuracy/edge claim.
- WAKE-32 (IN-PLAY TAIL-BAND VENUE-BIAS GATE, 2026-07-03, commit d61251b1): user
  redirect "my intelligence IS the edge; longshot in-game prices are flawed" -> NEW
  hypothesis CLASS (venue price bias, NOT public-state modeling -- cannot be "already
  priced" since it IS the price). ingame_tail_scan.py: price-band scan of 95 outcome-
  graded captured MLB in-play games (45K ticks), game-clustered bootstrap. DISCOVERY:
  home-side prices ran ABOVE realized in every band >0.20 ([0.65,0.80) significant,
  gap -0.178); longshot bands [0.10,0.20) realized ABOVE price both md5-halves
  (+0.080/+0.177) with model dBrier<0 both halves; [0.65,0.80) dBrier -0.0175/-0.0172
  both halves. Because bands were chosen from this sample, ingame_tail_gate.py PRE-
  REGISTERS H1 (longshot underpriced [0.10,0.20)) + H2 (mid-fav overpriced [0.65,0.80))
  at 2026-07-03T00:00Z and scores FORWARD-captured games only; wired as m32's 4th
  nightly candidate (CONFIRMED_FORWARD -> ship_review roster; acting stays human).
  Caveats recorded: fees/fills NOT modeled; deep tail [0,0.10) our model is WORSE
  (MARKET_BETTER in one half) -- do not chase deep tails; discovery window 2 weeks,
  possible drift. 19 tests green (7 scan + 5 gate + 7 m32 resynced). NO edge claimed;
  verdict file data/domains/mlb/ingame_tail_verdict.json starts PENDING_FORWARD n=0.
- WAKE-31 (MLB DEEP INTELLIGENCE PUSH -- context layer + SP lever DELIVERED, 2026-07-02):
  user directive: push MLB data/intelligence depth toward NBA's, verify-live-first, Sonnet
  executors. VERIFIED-LIVE FIRST (3 doc claims corrected): edge-map's "6,558-row/17-day
  gamelog corpus" is STALE (now 36,018 rows, 2026-04-01..07-02); sp_elo_offset confirmed
  genuinely NOT wired into MLBPredictor (pure MOV-Elo, checked predictor.py live);
  edge_engine extract_rule already MLB-aware (bullpen/probable-pitcher/weather keywords).
  SHIPPED (2 Sonnet executors + orchestrator, commits 3b360a6c + 0e01e83d, local only):
  (1) domains/mlb/ingest_probables.py -- ONE keyless statsapi schedule call
  (hydrate=probablePitcher,weather,officials) covers probables+weather+HP-umpire;
  2026 backfill 1,314 games, 99.9% SP / ~99% weather+ump coverage; gotchas: pitchHand
  never populated; postponed games surface under 2 dates (dedup handles). UN-DEFERS
  asof_bullpen_DEFER.md (its blocker WAS game_pk-keyed SP identity). (2) domains/mlb/
  ingest_injuries.py -- ESPN injuries snapshot (282 rows/30 teams) + longComment beat
  text through the EXISTING edge_engine.extract_rule (deterministic arm, extract_llm
  stub untouched) -> 167 edge facts (120 lineup_status, 40 pitcher_usage); athlete_id
  parsed from playercard href (not exposed directly). (3) m31_mlb_context ProcSpec
  (scripts/platformkit/mlb_context_runner.py, 6h cadence, heartbeat-gated, live tick
  verified: probables=1327 injuries=282 facts=167; test_manifest resynced 21 green).
  (4) Pitch-state corpora BACKFILLED via existing ingest_pitch_states: +2024/2025/2026
  (574 games, 165K rows) -> FIVE independent season corpora (2022-2026) for future
  per-pitch gates. (5) THE SP LEVER GATED + DELIVERED FLAG-OFF: sp_adjust_current.py --
  historical replication PASSED (Brier delta<0 + same-sign w in BOTH eras 2010-2015 /
  2016-2021), 2026 forward OOS with historical w (fully OOS, n=1002 bridged, 541
  non-NaN SP form): Brier 0.24761->0.24629, ECE 0.0205->0.0142, half-refit agrees ->
  verdict SHIP-READY in data/domains/mlb/sp_adjust_verdict.json; maybe_adjust() no-op
  unless CV_MLB_SP_ADJUST=1 (NOT set anywhere -- wiring into predict_service's MLB
  slate producer is the human decision). Current-era SP form = probables SP identity x
  player_gamelogs starts, EW a=0.35 min-3-starts snapshot-before-update; gamelogs
  inningsPitched is ALREADY decimal thirds (5.667), unlike classic box notation.
  37 new tests green (8 probables + 9 injuries + 4 runner + 16 sp_adjust).
  CONTINUATION (same wake, commit 93b139ae): user asked "how does the AI use all
  this independently to keep getting better + paper-bet in-game" -> shipped the
  missing flywheel hook: m32_mlb_context_autogate ProcSpec (nightly): re-runs the
  SP-offset 2026 forward eval + a NEW leak-free weather-totals gate (domains/mlb/
  weather_totals_gate.py) against the growing m31 corpus, composes data/frontend/
  ops/mlb_context_autogate.json (candidates + ship_review roster; live tick:
  sp=SHIP-READY, weather=REJECT). Weather verdict = honest REJECT: overall RMSE
  -0.0155 and half2 -0.0518 but half1 +0.0215 -> fails two-half replication (the
  discipline working; expected direction coefs temp+/wind_out+ recorded for the
  future retry as corpus grows -- m32 retries it automatically nightly). +18 tests
  (12 weather + 6 runner). Verdicts only: wiring a winner (CV_MLB_SP_ADJUST=1)
  stays the human decision. In-game SP shadow-logging in the inplay capture loop
  queued (NEXT 5) rather than hot-editing a running daemon.
  CORRECTION (same wake, post-backfill): the SP-offset SHIP-READY did NOT SURVIVE
  corpus expansion. After the 2024+2025 gamelog/probables backfill landed (gamelogs
  36K->178,836 rows; probables 6,185 games), re-ran the forward eval on the
  5.7x universe (n=5731, 4573 non-NaN SP form): baseline Brier 0.24438 vs
  SP-adjusted 0.24446 (WORSE), ECE 0.00437 vs 0.00768 (WORSE), half-refit flat ->
  verdict now REJECT (sp_adjust_verdict.json rewritten; m32 re-checks nightly).
  The n=1002 2026-only lift was small-sample variance. DO NOT flip
  CV_MLB_SP_ADJUST -- the earlier "ready when you are" note is WITHDRAWN. The
  in-game SHADOW logging stays (it measures a DIFFERENT question -- phase-
  dependent in-game lift vs live prices -- and is logging-only), but its pregame
  premise is now null; treat shadow results with that prior. Honest REJECT =
  the ratchet working: SHIP-READY at 10am, corpus 5x'd by 4pm, self-corrected.
  MIRROR FLIP same run: weather_totals REJECT -> SHIP_REVIEW on the expanded
  corpus (n=5731, 98.3% cov): beats baseline RMSE in BOTH halves (-0.0045 /
  -0.0285), coefs sane (temp+ / wind_out+ / wind_in ~0). FRAMING: sharpness vs
  our OWN no-weather baseline ONLY -- books price weather, NOT an edge; next bar
  = gate vs the totals CLOSE (oddsapi captures). Both same-day flips = the
  m31-grows/m32-re-gates loop proven end-to-end.
  CONTINUATION 3 (same wake, commits 64bd75cc + 3a930046 -- the "go" push, two
  decisive honest REJECTs): (a) weather_vs_close_gate: does weather explain the
  CLOSE's residual on 2,013 scorable games w/ real 2025-2026 totals closes?
  REJECT -- half1 delta +0.00013 fails replication, residual coefs tiny; books
  price weather ~completely. BONUS measurement: our own baseline+weather trails
  the close by 0.113 RMSE (the honest gap-to-market number). Now m32's 3rd
  nightly candidate. (b) ingame_sp_layer_gate_mlb: SP prior (flat AND decay-
  weighted) as an in-game layer over (p0, state) BASE, walk-forward, 2024/2025/
  2026 pitch corpora (~138K states): REJECT in ALL 3 corpora, both variants
  (noise control clean); the "decay" is decay-of-harm, not masked early benefit.
  Realized state + Elo already contain SP form -- consistent w/ the pregame
  n=5,731 REJECT. 2022/2023 skipped honestly (no gamelog coverage pre-2024-03;
  backfill running in background will extend). SP shadow logging stays live
  (grades vs PRICES, a different question) but with a firmly null prior now.
  NET LEDGER TODAY: context data layer SHIPPED + self-gating; SP lever fully
  adjudicated (pregame REJECT + in-game REJECT); weather = model-view only.
  CORPUS COMPLETE: 2022+2023 backfill landed -> player_gamelogs now 321,012 rows
  / probables 11,047 games, BOTH spanning all 5 seasons 2022-2026, aligned with
  the 5 pitch-state corpora. The edge-map's #1 unlock (multi-season prop
  calibration corpus) is DONE at the data layer; m32's SP eval universe expands
  automatically tonight (bridge now covers 2022-2026). Next prop step = run the
  real props_eval on this corpus (per-opportunity props first: Ks/hits/walks).
  CONTINUATION 2 (same wake, commits 91b0ed81 + 3380f0a6): user pushed "bankroll ->
  profitable, in-game must be much better + execution, tradable" -> shipped the
  quant ladder's shadow arm: (a) ingame_sp_shadow.py + 15-line additive wire into
  inplay_capture_loop -- every live MLB tick now logs model_prob_sp_shadow (SP-
  adjusted, historical-fit params) NEXT TO baseline model_prob, decision path
  untouched (field appended AFTER on_tick returns; poisoned-build -> permanent
  None); live spot-check 6/9 slate games float (PHI/PIT 0.55->0.5700), 3/9 honest
  None (thin form); m2_inplay_capture bounced (pid 9160, READY) so it's capturing
  shadows live. NEXT STEP when data accumulates: score shadow vs baseline Brier/
  CLV per game-phase (early innings should help, late should fade -- prior-decay
  hypothesis). (b) fixed m31/m32 runner tests stamping epoch-1970 beats into LIVE
  heartbeat files (observed live on m32: healthy daemon read stale) -- autouse
  _beat monkeypatch. (c) BACKGROUND 2024+2025 gamelogs+probables backfill running
  (ingest_player_stats + ingest_probables, ~370 dates) -> multi-season SP/context
  gate power + the edge-map's #1 prop-calibration unlock. (d) stack restarted:
  36/36 procs READY incl m31+m32. Paper-only; no $ claim; local commits only.
- WAKE-30 (FULL OPS CYCLE -- stale-premise check + a real feed break FOUND+FIXED, 2026-07-02):
  Ran the standing autonomous ops cycle end-to-end. STATE CHECK: the P1.1-P1.4/P3.1
  items WAKE-29-era NOW.md marked "NOT committed yet" had ALREADY landed in
  07a3f4c4/e9f84e6c (verified via git log, not the stale doc text) -- corrected those
  notes in place; nothing new to commit from tracked work (untracked sell/deploy/doc
  material correctly left alone, human-gated). STACK: all 34 supervisor procs READY,
  :3000/:8098/:8099 all HTTP 200. SENTINELS: output_freshness (m29) all 9 daemons
  GREEN; feed_health (m30) caught a REAL break -- Pinnacle soccer_intl 401 (kalshi's
  matching RED had already self-healed as transient by the time it was checked).
  DIAGNOSED LIVE (not assumed transient): direct-probed leagues/2764/matchups (401)
  vs leagues/246/matchups (mlb, 200) with identical headers -- not rate-limiting.
  GET /sports/29/leagues showed 2764 no longer listed at all; "FIFA - World Cup" now
  lives at id 2686 (588 live matchups) -- Pinnacle rotated the league id once the
  2026 World Cup proper started (was a pre-kickoff qualifying/futures container).
  FIX: scripts/platformkit/odds_provider/pinnacle.py _LEAGUE_ID['soccer_intl'] 2764
  -> 2686, +3 regression tests (test_pinnacle_league_ids.py) locking the id and
  guarding a revert; live-reran feed_health after the fix -> 5/5 providers GREEN.
  Restores the Pinnacle sharp anchor for WC pregame pricing + CLV grading (WC was
  silently missing its anchor book since kickoff -- degraded quietly, no exception,
  exactly the blind spot m30 exists to catch). Committed (59b4758d) + full
  boot.ps1 -Stop/boot.ps1 restart so the running m17/m18/m22/m23 daemons pick it up;
  verified LISTENING+200 on all 3 ports post-restart (a stale supervisor_status.json
  read during the restart window falsely looked all_ready=True before the new
  processes had actually bound their ports -- ground-truthed via netstat instead of
  trusting the JSON blindly). MEASUREMENT: CLV scoreboard -- Kalshi/PM game
  significant +13.51% CLV vs -11.1u record, game moneyline +0.96% vs -7.1u; reran
  clv_result_reconciler on both (n=36, n=28) -> both GENUINE_VARIANCE (max |z|=1.24),
  unchanged from the P1.4 verdict, confirms it isn't drifting. IN-GAME FUNNEL: 1 live
  MLB game today, markets(22)->live_state(1)->...->bet(1) = 100% conversion once a
  game is live (the funnel itself is healthy; the 21-market dropoff is honest
  no-live-state, not a leak). m27 settle: 0/14 settled yet (mid-slate, none final --
  expected, not a bug). prop_close_capture (m16): still captured=0/180 (props not yet
  posted by FanDuel this many hours out) -- unchanged from the WAKE-29-era note, not
  yet a full game day, left as the existing FOLLOW-UP. IMPROVE: refreshed
  domains/soccer/pregame_winprob_gate poisson_xg on the current corpus -- verdict
  unchanged (PARTIAL vs FAIR Elo, 1/6 leagues; shots-over-goals Elo-independent claim
  still REPLICATED 6/6, DM p=0.0 every league) -- confirms the corpus growth hasn't
  flipped an existing verdict; did NOT attempt the tennis asof_hold reclaim (ATP-only
  coverage, no WTA companion file exists yet, so it cannot clear the cross-corpus
  SHIP bar without a real new WTA extractor -- queued honestly in NEXT rather than
  rushed). All governance preflight gates PASSED on the fresh boot; ledger_health
  DIRTY (dup=210, settled_without_clv=235) and improve_ledger_reconcile ORPHAN_SHIPS
  (49/49) are REPORTED-not-gating and unchanged from baseline -- noted, not chased
  this cycle. Paper-only; no $ claim; no flag flipped; local commit only, not pushed.
- WAKE-30 CONTINUED (FRONT-END PLAYER PROPS -- route collision + missing bridge FOUND+
  FIXED, PropsPanel SHIPPED, 2026-07-02): user asked to get front-end props/scraping/
  paper-trading/AI all genuinely working for mlb+soccer_intl. Found GET /api/predict/
  props/{sport} (the exact route the webapp calls) was PERMANENTLY dead: Starlette
  matches routes by REGISTRATION ORDER, and app.py's generic /api/predict/{sport}/
  {game_id} (registered at module scope) beat extra_mounts' later-mounted /api/
  predict/props/{sport} for any 2-segment request -- every call landed on the generic
  handler with sport='props', game_id=<real sport>, returning a bogus "no snapshot for
  sport 'props'". FIX: extra_mounts._prioritize_props_routes moves the props routes to
  the front of app.router.routes post-mount; +4 tests proving the bug existed pre-fix
  (460fd0cb). SEPARATELY found the route, even fixed, had NO data bridge: it only ever
  read player_prop MarketRows from predict_service's OWN snapshot, which nothing writes
  for mlb/soccer_intl (NBA-domain-pricer-only) -- the REAL scraped-book props (Draft
  Kings/Underdog/PrizePicks/FanDuel, Poisson/NB priced, 1639 mlb / 506 soccer_intl
  edges) already existed on a separate :8098 endpoint. NEW predict_service/
  prop_surface_scraped.py bridges the SAME on-disk snapshot read-only (no network, no
  re-pricing) as a fallback when the domain snapshot has zero prop rows; NBA untouched.
  Also fixed PrizePicks masking a real 403 WAF block (external, not evadable -- same
  class as the documented BetMGM block) as a misleading "league not found" (b9e9ee76).
  DELEGATED the actual UI panel to a Sonnet executor agent (self-contained brief: live
  API shape, LiveLinesPanel.tsx pattern to mirror) -> built PropsPanel.tsx, fixed a
  stale TS type (types_w12.ts expected 'props' key + non-nullable numbers; real API is
  'rows' + nullable), wired into /p6, npm build clean, committed (9bc820d4). Then hit a
  NEW deploy gotcha: webapp runs `next start` (prod, not dev) and its persistent .next/
  cache/ survives rebuilds+restarts -- had to shutil.rmtree the cache dir (rm -rf got
  permission-hook-blocked) THEN restart m1_ui before the live page reflected the new
  panel; memory: gotcha-nextjs-static-cache-serves-stale-after-rebuild. LIVE-VERIFIED
  end-to-end: /api/predict/props/{mlb,soccer_intl} both source=scraped_book_snapshot
  with real counts; /p6 raw HTML now contains the panel's P(over)/Poisson markers (was
  byte-identical to pre-session baseline before the cache clear). All 3 ports 200,
  34/34 procs READY, bankroll live (79.25u). Paper-only; no $ claim; no flag flipped;
  local commits only, not pushed.
- WAKE-29 (PAPER TRADING AUDIT -> FOUND+FIXED the in-game channel never SETTLED, 2026-07-01):
  user "make sure paper trading is working." Audited live: stack 29/29 up, bankroll live-updating
  (68.4u of 100 = the measured bleed), PREGAME channels healthy (today props=105, paper_pm=42,
  moneyline=27 all placing+settling+CLV). BIG WIN confirmed: in-game channel now PLACES (paper_ingame
  =55 today vs ~1 historically -- the WAKE-25 two-sided fix is live incl edge-flip re-entry on both
  legs). BUT found the break: **82 paper_ingame rows EVER, 0 EVER settled** -> the in-game channel
  placed but NOTHING graded (no outcome, no CLV, no bankroll impact, no learning). ROOT: inplay_daytrader
  places via paper_ingame.record_ingame_bet and paper_ingame.grade_live can settle one, but NOTHING
  called grade_live -- there was no in-game SETTLE arm (pregame has one, in-game never got one), and the
  same KALSHI-TICKER-not-ESPN-id gap meant an ESPN-id settler could never match anyway. FIX: added
  MlbOutcomeResolver.final_score (ticker->boxscore final score, not just win/loss) + NEW
  scripts/platformkit/ingame/ingame_paper_settle.py: loads OPEN paper_ingame rows, resolves each MLB
  bet's final score from the ticker, calls grade_live -> settles with real outcome+unit_result;
  idempotent (already-settled edge_keys skipped), a not-yet-final game stays OPEN, soccer stays open
  pending a soccer resolver; +5 tests. RAN LIVE: settled 68 stuck MLB bets (33W-35L, net +0.353u, all
  unique settle_keys = dedup-safe), 5 MLB still-open (not final) + 9 soccer open. Registered ProcSpec
  m27_ingame_paper_settle (--interval 900) so it settles continuously; test_manifest resynced. Also
  fixed a latent flake: ingame_segment_trust corpus split used builtin hash() (per-process randomized
  -> non-reproducible verdict) -> switched to md5 (deterministic). ANSWER TO USER: paper trading IS
  working -- pregame end-to-end, and in-game now settles too (was the one broken leg). 50+ touched tests
  green; <=300 LOC each, ASCII, units-only no $, executed=False, edge_claimed=False, no flag armed.
  m27 goes live on next boot.ps1 restart (I already ran the backfill by hand). NEXT: a soccer in-game
  outcome resolver (domains/soccer results) so the 9 open WC in-game bets settle too.
- WAKE-28 (SELF-IMPROVING EXECUTION via CROSS-CORPUS trust gate + CORRECTS WAKE-27, 2026-07-01):
  user "keep building ai so it independently gets better execution." Built the mechanism that lets
  in-game EXECUTION improve on its own -- and immediately caught that WAKE-27's headline was a
  single-fold ARTIFACT. Split the labeled MLB corpus into TWO INDEPENDENT corpora (even-dated vs
  odd-dated games) and re-ran the outcome verdict on each: corpus A (50 games) = ALL innings MATCH;
  corpus B (44 games) = I5-I8 BETTER_THAN_VENUE (big deltas). So the "I5-I9 beats venue" from WAKE-27
  was driven ENTIRELY by one half and does NOT replicate -> under the discipline (">=2 independent
  corpora; single-fold lifts are artifacts") it is NOT robust. Correct honest state: NO segment is
  proven better-than-venue across independent corpora. BUILT the gate that enforces this automatically:
  scripts/platformkit/ingame/ingame_segment_trust.py (splits corpus into >=2 disjoint date-parity
  corpora, runs ingame_outcome_verdict on each, marks a segment TRUSTED only if BETTER_THAN_VENUE in
  EVERY non-insufficient corpus / ADVERSE only if WORSE in every / else NEUTRAL; writes
  data/frontend/ops/ingame_segment_trust.json; +7 tests). WIRED into inplay_capture_loop._build_tick:
  floor_for_segment routes the in-game EV floor -> an ADVERSE segment reverts to the STRICT
  pre-registered floor (suppress its marginal relaxed bets), TRUSTED/NEUTRAL/unknown keep today's
  relaxed floor. So execution self-improves as games accrue but changes ONLY on cross-corpus PROOF;
  thin/unreplicated data changes nothing (do-no-harm), reversible via CV_INGAME_SEGMENT_TRUST=0.
  LIVE build: EVERY segment NEUTRAL (correct -- nothing replicates yet) -> ZERO execution change today,
  gate armed to act autonomously when a lift replicates (->TRUSTED) or a segment proves consistently
  worse (->ADVERSE->auto-suppress). Registered ProcSpec m26_ingame_segment_trust (--interval 1800),
  test_manifest resynced. 46 touched tests green; <=300 LOC, ASCII, no $ field, edge_claimed=False,
  flips no flag, places no bet. Live on next boot.ps1 restart. NEXT lever unchanged but now
  AUTOMATED: the gate itself promotes/demotes segments; watch ingame_segment_trust.json cross slates.
- WAKE-27 (IN-GAME MODEL better-than-venue vs OUTCOME in innings 5-9 -- FULL-CORPUS ONLY, NOT
  cross-corpus-replicated: see WAKE-28 correction, 2026-07-01):
  user "keep making paper trade better ... beat pinnacle, make money on kalshi/sportsbooks." Attacked
  the recurring in-game-CALIBRATION lever (WAKE-24/25/26 all ended pointing here). The in-game CLV
  verdict could only compare model vs the CONTEMPORANEOUS venue price (MATCH, hit_rate 0.42) and the
  per-segment CLV showed the model leaning BELOW the Kalshi price in late innings -- ambiguous: model
  lag, or the thin venue quote lagging? SETTLED IT by unlocking OUTCOME labels. ROOT of the blind spot:
  capture writes each game's grade series keyed by the KALSHI TICKER (KXMLBGAME-26JUN241845PHIWSH), not
  the ESPN id, so settle_stamp (keys by ESPN id) never landed a home_win label -> the whole in-game
  layer had ZERO outcome labels. FIX: the ticker ENCODES date+away+home abbrs -> NEW
  scripts/platformkit/ingame/ingame_outcome_label.py (parse ticker + Kalshi->ESPN abbr alias map
  AZ->ARI/CWS->CHW/... + unambiguous away|home split, join to data/domains/mlb/espn_boxscores.parquet
  -> home_win; offline, leak-free, None on unresolved/tie/non-final; +7 tests). Refreshed the stale box
  parquet (ended 06-25) through 07-01 via domains.mlb.ingest_espn_box (keyless ESPN, +73 finals) ->
  labeled 94/97 captured games. NEW scripts/platformkit/ingame/ingame_outcome_verdict.py: per inning
  segment, Brier(model vs OUTCOME) vs Brier(venue in-play price vs OUTCOME), per-GAME clustered
  bootstrap CI (game = cluster unit), verdict BETTER_THAN_VENUE only when CI upper < 0; +6 tests.
  LIVE VERDICT (data/frontend/ops/ingame_outcome_verdict.json): I1-I4 MATCH, I5-I9 BETTER_THAN_VENUE
  (delta -0.032/-0.035/-0.043/-0.052/-0.060, all CI upper<0), UNK MATCH. So from the 5th inning on our
  live model is BETTER CALIBRATED TO TRUTH than the Kalshi in-play price -> the two-sided daytrader's
  late-inning disagreements with Kalshi are usually RIGHT (validates placing there; be cautious I1-I4=
  MATCH). HONEST CAVEATS (binding): Kalshi in-play is THIN/LAGGY, so this beats a STALE VENUE QUOTE, NOT
  an efficient close, NOT Pinnacle, NOT a $ edge; better-Brier != profitable (round-trip cost ~3-5c);
  n=29-45 games/1 slate window = single-fold, artifact risk. So made it CONTINUOUS: ProcSpec
  m25_ingame_outcome_verdict (--interval 900), test_manifest resynced (32 green) -> accrues games across
  slates so the lift replicates or washes out honestly. NO placement behavior change this wake (honest:
  don't act on one window); NEXT lever = once BETTER_THAN_VENUE holds across >=2 slate windows, gate the
  in-game EV floor to relax ONLY in proven segments (I5+) and stay strict/suppress where MATCH. All
  under scripts/platformkit/ingame (safe area), <=300 LOC, ASCII, no $ field, edge_claimed=False, no
  flag armed, paper-only. Live on next boot.ps1 restart (running supervisor has pre-edit manifest).
- WAKE-26 (NEUTRAL-SITE: user "this game has no home or away" -- VERIFIED model already correct + made
  it VISIBLE, 2026-06-29): user flagged that a World Cup game has no home/away so the model shouldn't use
  it. INVESTIGATED + corrected my own prior over-claim (I'd blamed hfa_lambda): soccer_intl does NOT use
  the domestic hfa_lambda -- it uses domains/soccer_intl/predictor.IntlSoccerPredictor which DEFAULTS
  neutral=True (no home tilt) for both predict + predict_live, and the in-game path doesn't override it.
  PROVEN by pricing GER-PAR both ways: NEUTRAL (what we use) Germany pregame 0.689 / live33 0.589 vs
  HOME-TILT 0.888 / 0.793; snapshot home_ml=0.689 confirms neutral is applied. So NO home/away bug --
  the model already drops the tilt exactly as the user wants; the home/away labels are just pairing tags.
  The 0.589-vs-market-0.67 gap is small IN-GAME calibration (our favorite-decay slightly faster than the
  market), NOT home/away, and likely our model trailing an efficient market. REAL residual = the
  snapshot/state stamped neutral=None (why it LOOKED like home/away context). FIX: ingame_live_state now
  stamps a `neutral` flag (_neutral_site: honors ESPN competition.neutralSite when present, else True for
  soccer_intl) so the in-game state explicitly carries neutral=True; +helper, 10 tests green; LIVE-
  VERIFIED GER-PAR -> neutral=True. Additive, no model/number change (model was already neutral), no flag,
  no bet. NEXT real lever stays in-game CALIBRATION (favorite time-decay), not home/away.
- WAKE-25 (IN-GAME ROOT CAUSE FIXED: signal was HOME-ONLY -- now two-sided + places live, 2026-06-29):
  user "world cup going on, should be working." There WAS a live WC game (GER-PAR 33' 0-0). Ran the
  m24 funnel against it: 47 markets -> 1 live_state (the live game resolved fine; 46 upcoming = correct
  no_live_state) -> cleared model_prob/home_leg/priced -> died at below_floor. Dug in: GER-PAR our model
  Germany 58.5% vs market 69% = +EV on PARAGUAY (away). ROOT CAUSE: scripts/platformkit/ingame/
  inplay_edge_signal.evaluate was HOME-ONLY (SIDE='home'; ev = ev_vs_price(mp, home_dec) only) -> every
  AWAY-side edge (~half the opportunity space) silently discarded -> the dominant reason the in-game
  channel placed ~nothing (1 ever vs 136 pregame). FIX: made evaluate TWO-SIDED -- price both legs at
  no-vig fair, take the +EV side, return side/bet_model_prob/bet_devigged_price; the GRADE pair stays
  HOME-aligned (leak-free) -- only the placed bet's side/odds/prob reflect the chosen leg. Wired
  inplay_daytrader.on_tick to place ev['side'] (was _sig.SIDE) with that side's prob+decimal. Also
  added mlb to _INGAME_RELAXED_EV_FLOOR (was soccer-only -> MLB in-game now places too). Tests: updated
  1 relaxed test (model==fair is the true no-edge point under two-sided) + added 2 two-sided tests; 14
  edge-signal + 7 capture-loop green; the only 2 reds (test_inplay_daytrader G1/G2) are PRE-EXISTING
  (verified via git stash: fail on original code too -- short game_id write-guard, not mine). LIVE-
  VERIFIED: re-ran poll_once -> GER-PAR action=bet tier=A on the away (Paraguay) edge, n_bets=1 (was 0).
  HONEST CAVEAT: an 11-pt in-game disagreement is MORE LIKELY in-game MODEL MISCALIBRATION than a real
  edge; this is PAPER, CLV-graded -- the mechanism is now correct + places, the NEXT lever is in-game
  model CALIBRATION so the disagreements are trustworthy. No $ claim, no flag armed, paper units only.
  Goes fully live on next boot.ps1 restart (running supervisor has pre-edit code).
- WAKE-24 (IN-GAME is the move, pregame ML isn't -- DIAGNOSE the in-game starvation, 2026-06-29):
  user "pregame ML isn't the move, should make a lot of bets in-game, efficient paper trading, make
  in-game edges better." QUANTIFIED the inversion from the live ledger (data/frontend/clv_ledger.jsonl,
  137 rows): paper(pregame props)=80, paper_pm=30, moneyline(pregame ML)=26, paper_ingame=ONLY 1 (and
  malformed: market_prob/edge/units=None). So 136 pregame vs ~0 in-game -- exact inverse of the thesis.
  ROOT CAUSE (ran inplay_capture_loop.poll_once live): 48 Kalshi game markets, ALL 48 -> no_live_state,
  model_prob=None; n_live=0 + statsapi live_games=0 -> there are simply NO in-progress games right now
  (19:36Z = ~3:36pm ET; tickers are 26JUL01 = 2 days out; MLB slate starts ~23:00Z). So 0 in-game NOW
  is CORRECT. BUT historically 1-ever vs 136 => during live windows the funnel (markets->live_state->
  model_prob->home_leg->priced->tier_floor->bet) drops almost everything and we had ZERO visibility
  into which stage. The engine is SOUND + wired (inplay_daytrader uses the LIVE leak-free model via
  live_board.live_model_home_prob, edge gate inplay_edge_signal = calibration_justified+liquid+fresh+
  tier, quarter-Kelly, places to paper_ingame; capture loop m2 calls on_tick every tick). NOTE: the
  SEPARATE pm_game_placer(m12) prices LIVE exchange markets with the PREGAME model -> stale-edge bets;
  the real in-game channel is the daytrader, not m12. BUILT instrumentation:
  scripts/platformkit/ingame/ingame_placement_funnel.py (folds poll_once's per-game decisions into the
  stage funnel + reason histogram + biggest_dropoff; writes data/frontend/ops/ingame_placement_funnel
  .json; +8 tests) -> ProcSpec m24_ingame_placement_funnel (--interval 300), manifest resynced (21
  green). Live on next boot.ps1 restart. NEXT (do it DURING tonight's live slate ~23:00Z+): read the
  funnel -> if drop is at live_state, fix the Kalshi-ticker->live_state resolution for the daytrader
  (the chronic id gap, see WAKE-20d/21); if at tier_floor, the gate is too tight for in-game. Diagnose
  on REAL live data, then tune so in-game places a lot. Candidate/diagnostic only; no bet, no flag,
  no $ edge.
- WAKE-23 (FIND GAPS IN OUR OWN SCRAPED LINES, all sports, 2026-06-29): user corrected -- they have
  their OWN scraper, NEVER meant to use OddsAPI; want the NBA "every little detail" edge-hunt applied
  across sports on the lines WE are getting. FOUND the real feed: data/cache/line_history/<sport>/
  <date>.jsonl = our DK(via espn)/FanDuel/Pinnacle scrape, ML+spread+total, devigged+timestamped,
  fresh today (7610 MLB rows). OddsAPI was a red herring. BUILT sport-blind gap-finder
  scripts/platformkit/clv/scraped_line_gaps.py (reads OUR feed, groups by game/market/line, best book
  price vs Pinnacle-sharp-fair via vetted best_price; +8 tests). 1st live run found 2 MLB "gaps"
  (Yankees@RedSox FanDuel 3.50 away +31.6% CLV) -- I CHECKED them: STALE-DATA MIRAGE (DK 02:53 said
  50/50; FanDuel quote was 30min OLD at 02:23 saying 74/26; +CLV on BOTH sides = the tell). THE LESSON
  = finding apparent gaps is trivial; the real work is rejecting the ~99% stale/mismatched. ADDED a
  FRESHNESS GATE (max_stale_sec default 600: within each game/market/line, drop any quote staler than
  the freshest) -> mirages correctly vanish -> honest EMPTY (slate efficient across our 3 books when
  comparing only contemporaneous quotes). Then made it AUTONOMOUS: scraped_line_gaps_daemon.py (~4min,
  writes data/frontend/ops/scraped_line_gaps.json + scraped_line_catches.jsonl only on a real fresh
  gap; +6 tests) -> ProcSpec m23_scraped_line_gaps, manifest resynced (21 green). Goes live next
  boot.ps1 restart. CANDIDATE-ONLY: our files only, no OddsAPI, no bet, no flag, +CLV is prob space.
  REAL LEVER now: more CONTEMPORANEOUS books (only 31-34/143 MLB groups shoppable >=2 books; NBA/
  soccer_intl ~1 book) + tighter capture cadence to catch transient gaps in their live window.
- WAKE-22 (USE-MORE-BOOKS / FIND-GAPS made CONTINUOUS, 2026-06-29): user frustrated "ai should
  make money on kalshi/DK, use more books, find gaps". Ran the honest model-free lever LIVE:
  best_price_audit (best price across all wired books vs sharp fair) over the real slate = ZERO +CLV
  gaps at min-clv 0.0 (26 MLB games, 13 shoppable, MAX 3 books each; soccer pinnacle 401). Market is
  efficient at line-shop level RIGHT NOW. KEY: cross-book gaps are TRANSIENT (book lags ~60-120s) so a
  manual one-shot run misses them -> the lever only pays off polling continuously. BUILT
  scripts/platformkit/clv/best_price_scan_daemon.py (every ~4min runs the scan, writes
  data/frontend/ops/best_price_scan.json, appends data/frontend/ops/best_price_catches.jsonl ONLY when
  a real +CLV gap appears; injectable/offline tests; +6 green) -> registered as supervisor ProcSpec
  m22_best_price_scan (argv --interval 240), test_manifest resynced (21 green). CANDIDATE-ONLY: reads
  public odds, places NO bet, flips NO flag, +CLV is probability space NOT a $ edge. Goes live on next
  boot.ps1 restart. HONEST FRAMING for the user: the two real "more books" levers are (1) this
  continuous scan + (2) WIRING MORE bettable feeds (only 3 shoppable; Pinnacle soccer auth 401, add
  MGM/Caesars) to widen best-of-N -- NOT a smarter model. The bleed is still PROPS (139-217); pregame
  prop calib suppress-gate is the next unit-saver (lane 2, not yet built this wake).
- WAKE-16 (CEILING, 2026-06-26 ~10:00): SHIP b3b108da -- first ceiling experiment: reclaim MLB
  sp_ra_diff_asof through the REAL WF DM gate -> HONEST REJECT (Brier 0.240312->0.240226, DM p=0.54;
  planted-null collapses; truncation-invariant). SP form priced into the close. Reusable as-of
  reclaim gate template kept. NEXT: CQR prop intervals (domains/basketball_nba/prop_cqr.py) -- the
  prop-coverage gap has REAL room (efficient pregame reclaims will mostly reject; props + in-game won't).
- WAKE-20 (UNITS: reset + stopped the measured bleed + FE open, 2026-06-27): user asked to fix
  everything, reset units, make as many units as possible. (1) RESET paper bankroll 100u via NEW
  reversible scripts/platformkit/paper/bankroll_reset.py (archives the 5 canonical settled/display
  files to _ledger_archive/<ts>_reset, reinits, daemon reconciles -> live 100.0u, net 0; +3 tests,
  --restore reverses). Was -2.06u (net -102u, -24u that day). (2) DIAGNOSED the -31% in-game-prop
  CLV bleed on the archived ledger (n=402 true-close): mean CLV -31.0% (CI excl 0) AND CLV is
  ANTI-correlated with model edge (corr -0.083; high-edge half -34.7%) -> tightening the vig/edge
  gate selects the WORST bets. Channel is structurally adversely-selected; only CLV-positive action
  is STOP placing it. (3) NEW scripts/platformkit/improve/ingame_prop_clv_guard.py SUPPRESS-ONLY,
  DEFAULT ON (CV_INGAME_PROP_CLV_GUARD=0 restores broad-capture), composed into auto_loop
  _place_ingame_props gate (over the optional calib gate). +4 tests; 16 trader+guard green. Honest
  anti-edge move, NOT an edge claim, paper units only, no flag armed ON. (4) FE verified live +
  opened: :3000 UI + :8098 boards + :8099 API all 200; /api/paper/today reflects 100u; supervisor
  23/23 READY. CAVEAT: guard takes effect on NEXT stack restart (running auto_loop process has the
  old code cached) -> restart boot.ps1 to apply live. WAKE-19 below stands.
- WAKE-20b (RESTARTED LIVE, running without user, 2026-06-27 ~15:45): boot.ps1 -Stop (clean drain,
  21 PIDs) then boot.ps1 -> governance preflight PASSED, ONE supervisor (PID 17612, singleton OK),
  24/24 procs READY incl m19_asof_reclaim (ran its first autonomous sweep: tick=0 candidates=6
  reject=6, scoreboard row written, now daily). In-game prop CLV guard is_enabled()=True in the live
  auto_loop. The pre-restart guard-less code had queued 34 open paper_ingame_prop positions ->
  re-baselined bankroll to a clean guard-on 100u (2nd reversible reset; archived). FE live: :3000 UI
  + :8098 + :8099 all up; /api/paper/today + supervisor doc show 100u + 24/24. Stack is detached
  (Start-Process) so it persists unattended. m19 + bleed-fix are now LIVE.
- WAKE-20c (IN-GAME edge-hunt made CONTINUOUS, 2026-06-27): user thesis = in-game has the small
  gaps, hunt them continuously w/ live data+lines. FOUND: m11 already logs model+market tick series
  per live game (data/cache/ingame_grade/<sport>/) and ingame_clv_grade.grade_sport produces the
  honest in-play-close anticipation verdict -- but it was MANUAL-ONLY (segment_emit not on flywheel).
  Ran it live (8 live MLB games): MLB MATCH mean_clv=+0.043 over 24.7k ticks/70 mkts (BEAT 24 vs
  BEHIND 16); soccer MATCH +0.035. The in-game GAME engine is the one channel that leans POSITIVE
  (vs -31% props). BUILT m20_ingame_clv_verdict daemon (scripts/platformkit/ingame/
  ingame_clv_verdict_daemon.py, ~10min loop, writes data/frontend/ops/ingame_clv_verdict.json; +5
  tests) -> registered as ProcSpec m20 (25 procs), test_manifest resynced. RESTARTED: 25/25 READY,
  m20 wrote first verdict, guard still ON. Verdict is CLV/probability MATCH not BEAT -- NOT a $ edge;
  the honest path is to keep measuring so a real persistent gap crosses MATCH->BEAT on its own.
- WAKE-21 (MATCH->BEAT TRIGGER wired, 2026-06-27): user asked "when does in-play start beating".
  Refused a profit DATE (would fabricate a $ edge); instead made the crossing self-firing. Why MATCH
  not BEAT today: mean_clv +0.0255 = 2.5 prob pts < the ~3-5c in-play round-trip cost, hit_rate 0.43,
  BEAT 23 ~= BEHIND 20. BUILT scripts/platformkit/improve/ingame_baseout_gate.py (leak-free: target =
  in-play close = last market tick; residual = close - model_prob_t; does deep base-out/RE24/count/
  pitch state predict the residual OOS? two chronological corpora must BOTH improve RMSE w/ DM p<0.05
  AND planted null must collapse -> SHIP_REVIEW else REJECT; INSUFFICIENT below 4000 ticks/16 games) +
  ingame_baseout_gate_daemon.py (hourly) registered as ProcSpec m21 (26 procs); +12 tests, manifest
  resynced; 33 green. LIVE corpus today = 1792 ticks / 14 games -> honest INSUFFICIENT (still filling;
  deep state only flows post-id-fix). Candidate-only: flips NO flag, places NO bet, probability space.
  CAVEAT: m21 goes live on NEXT boot.ps1 restart (running supervisor has pre-edit code). The verdict
  now crosses MATCH->BEAT (or REJECTs the lever) on its OWN -- no date-guessing.
- WAKE-20d (DEEP in-game variables, 2026-06-27): user wants deep live data (base-out, every variable)
  collected constantly + validated. SHIPPED the deep MLB base-out extractor:
  scripts/platformkit/ingame/ingame_baseout_mlb.py (parse_baseout + baseout_summary_fields; outs,
  baserunners 3-bit base_state, base_out_state 0-23, standard RE24 run-expectancy table, count; leak-
  free, never raises; +7 tests). VALIDATED ON 8 REAL LIVE GAMES (e.g. ARI@TB 1out/runner-on-3rd
  RE24=0.950; SEA@CLE 0out/1st 0-2). Wired ADDITIVELY into ingame_live_state._extract + the
  live_grade._state_summary key tuple (outs/base/bos/re/count) -> when capture resolves an ESPN
  event, the series now carries the deep state (verified end-to-end: "...inning=7 half=bottom outs=1
  base=4 bos=13 re=0.95 count=1-1"). 22 tests green; restarted 25/25 READY.
  HONEST BOTTLENECK (not fixed): the ACTIVE capture keys games by KALSHI TICKER (KXMLBGAME-...), and
  ingame_live_state.live_state("mlb", <kalshi_ticker>) returns None -> empty state ("live") -> deep
  vars (and even score/inning) DON'T flow into the active Kalshi-keyed series. Pre-existing ID gap,
  not caused by this change. NEXT: build an ESPN<->Kalshi live-game id resolver (parse ticker ->
  date+away+home -> match ingame_box_mlb.live_games -> statsapi situation has outs+offense) so deep
  capture flows into the active series; THEN once accumulated, gate base-out -> win-prob (no base-out
  corpus exists yet, so collection must precede validation). Extractor is built+validated; the
  resolver is the remaining wire. No edge claim; calibration/descriptive state only.
- WAKE-21 (BLOCKER UNBLOCKED: deep state flows into the ACTIVE series, 2026-06-27): built the
  ESPN/Kalshi<->statsapi MLB id resolver WAKE-20d called for -> deep base-out now flows into the
  active Kalshi-keyed in-play series continuously, LIVE-VERIFIED. NEW
  scripts/platformkit/ingame/ingame_id_resolver_mlb.py: parse_kalshi_mlb_ticker (KXMLBGAME-26JUN271810
  AZTB -> date/time/away+home blob) + resolve_ticker (matches the blob's away+home Kalshi abbrevs vs
  ingame_box_mlb.live_games full team names by EXACT mapped-abbrev equality; KALSHI_ABBR = all 30
  clubs incl the divergent AZ/CWS/WSH/SD/SF/ATH; UNIQUE match only -> 0 or >1 (live doubleheader) =
  None, NEVER mis-binds) + linescore_deep_fields (adapts the statsapi linescore offense/outs/count ->
  the EXISTING ingame_baseout_mlb.parse_baseout, reuse not duplicate) + deep_state_for_ticker +
  make_tick_deep_fn (LAZY per-tick enricher: no candidate fetch until a real game needs it -> dead-feed
  test path stays offline); +13 tests. ROOT CAUSE found beyond the id gap: inplay_capture_loop._build_
  tick PROJECTED the state to 7 keys, DROPPING score/inning/outs/base/bos/re/count before they reached
  live_grade._state_summary -> every tick logged a bare "live" even when ESPN HAD the situation. FIX:
  widened _build_tick passthrough (label-only; model/price/sizing read top-level tick fields, cannot
  change a decision) + merged the statsapi deep state in _process_game (mlb-only, additive, guarded) +
  threaded deep_state_fn through poll_once/serve_forever (default OFF -> existing tests offline) +
  enabled mlb_deep=True in inplay_capture_runner.run (production). LIVE-VERIFIED on the real slate:
  all 7 in-progress games resolved to correct gamePks with accurate base-out; the abbrev map has ZERO
  gaps (every live ticker blob decomposes uniquely into known abbrevs); after restart the SAME active
  file KXMLBGAME-26JUN271915MIASTL flipped from "live" -> "home_score=0 away_score=4 inning=5 half=top
  outs=0 base=0 bos=0 re=0.481 count=0-0"; 10 live series now carry deep base-out. Restarted 25/25
  READY, guard is_enabled()=True. No edge claim; descriptive state + the gamePk join-key for items 2-4.
  PRE-EXISTING (not mine, noted): tests/platformkit/ingame/test_inplay_daytrader.py 2 fails -- the
  paper_ingame _is_malformed_input write-guard now rejects the tests' short "G1"/"G2" game_ids
  (added in a prior WAKE; my changes don't import that path).
  ALSO SHIPPED item 2 (deeper vars) same wake: NEW scripts/platformkit/ingame/ingame_pitcher_mlb.py
  (pure adapters tto_for + pitcher_batter_fields; current pitcher/batter from linescore
  defense.pitcher/offense.batter, pitch_count from boxscore numberOfPitches, TTO =
  battersFaced//9+1 = the order-turn the batter NOW up is in -> the 3rd-time-through zone; +7 tests).
  Wired ADDITIVELY into deep_state_for_ticker (one extra boxscore fetch/game/tick, guarded -> base-out
  still flows if it misses); pitch_count + tto added to _build_tick passthrough + live_grade._state_
  summary (numeric tokens only -- pitcher/batter NAMES flow in the structured state but stay OUT of the
  space-joined label to avoid breaking k=v parsing). LIVE-VERIFIED: e.g. COLMIN Paredes pc=73 tto=3,
  SEACLE Cecconi pc=81 tto=3; after 2nd restart the active MIASTL series carries
  "...outs=2 base=0 bos=2 re=0.098 count=0-0 pitch_count=13 tto=1". 25/25 READY, guard ON. COST NOTE:
  the capture tick now does ~1 schedule + 2N linescore + N boxscore fetches/tick (N live games);
  boxscore ~100KB each -- monitor tick cadence (heartbeat as_of should advance ~every 20s); throttle the
  boxscore if cadence slips. NEXT (queue): item 3 in-game true-close capture (m21, exact-gamePk/game_id
  join, mirror m16/m18) -> item 4 gate base-out+tto -> win-prob once the corpus accumulates.
- WAKE-19 (AUTONOMY: ceiling loop runs WITHOUT Claude, 2026-06-27): wired the asof-reclaim gate
  as a self-running daemon. NEW scripts/platformkit/ceiling/asof_reclaim_sweep.py (gates ALL on-disk
  *_diff_asof candidates: NBA ast/dreb/fg3m/stl/blk + MLB sp_ra_diff = 6, normalizes to one verdict
  row, logs each to reject_ledger + ceiling_reclaim_scoreboard.jsonl, control-failing SHIP ->
  SHIP_REVIEW, never auto-ships) + asof_reclaim_daemon.py (daily loop, survives any tick failure,
  injectable for tests) + test (7 green). Registered as supervisor ProcSpec m19_asof_reclaim in
  supervisor/stack_specs.py (readiness NONE, _FOREVER, no depends_on) -> launches on next supervisor
  boot, 24 procs now. ALSO resynced the STALE tests/supervisor/test_manifest.py frozen proc set (it
  stopped at m13; m14-m18 were added in prior sessions but never added to the test -> it had been RED
  for sessions; now includes m1_bankroll + m14-m19, 36 green). First sweep: ALL 6 REJECT (efficient
  pregame). predictor.py untouched, NO flag flipped, candidate-only. WAKE-18 below stands.
- WAKE-18 (CEILING / Rung-2 player intel, 2026-06-27): reclaimed leak-free `ast_rate_diff_asof`
  (asof_features.parquet) through the REAL single-corpus WF DM gate vs leak-free Elo ->
  HONEST REJECT. NEW domains/basketball_nba/asof_ast_rate_eval.py (+test, 3 green), reuses the
  MLB asof_ra_diff_eval template (inlined helpers, F5-isolated). Brier base 0.205026 -> cand
  0.205040 (delta -1.4e-5, WORSE); DM p=0.78; fitted feat_w shrinks to -0.006; planted-null
  collapses (p=0.997); truncation-invariant. base Elo BSS 0.174 (non-degenerate). VERDICT: assist
  rate carries NO incremental win-prob signal over Elo -- the memo "AST ~+4-5%" was a box/prop
  artifact, not a team edge. player_plusminus.json is scouting_only (season aggregate = leaky) so
  it is NOT gate-able; this is its leak-free cousin. Logged to reject_ledger. CANDIDATE-ONLY, no
  flag flipped, predictor.py untouched. Remaining pregame box reclaims (dreb/fg3m/stl/blk diffs)
  expected REJECT too (efficient); the real lever stays IN-GAME conditioning.
- WAKE-17 (READINESS, 2026-06-26 ~16:46): flywheel healthy (23/23 procs all READY incl m15-m18).
  V1 PROP SETTLEMENT = VERIFIED WORKING, NOT a bug: the 47 props tagged game_date=2026-06-25 are
  actually 06-26 games (statsapi: Nationals@Orioles, Cubs@Brewers etc. are 'Scheduled' today, NOT
  final) -- an ET-day mis-tag the settler's date+1 fallback already handles -> honest-pending, will
  settle tonight when the 06-26 slate goes final. prop_settler_mlb._team_hit/city-abbrev fix is
  sound (ran live: full-name matchups resolve correctly; the mismatch was date, not name).
  SHIP 7a3fc3ba (V3): clv_ledger.record_bet now labels market_type on market-omitted ML rows.
  ROOT: record_bet only persisted 'market' when a caller passed it, but the game-ML placers
  (run_paper_today/m1_paper + /api/clv/record) omit market= -> rows got a moneyline bet_id but NO
  market/market_type field -> rendered '?' (9 live mlb rows). Now persists bet_id()'s resolved
  value (default 'moneyline') as BOTH market+market_type at the writer (honest label, identity key
  already classified them ML). +2 fail-before/pass-after tests; 12/12 file + 100/100 dependent
  (sanity/dedup/betid/guard) green; ASCII; LOC 327. Note: the 9 EXISTING rows aren't retro-fixed
  (don't race the live ledger) -- forward-looking; a betid_backfill relabel could clean them later.
  Scoreboard: props settled 7 (all PM ML, all clv no_close); boards games-shown mlb 0 / soccer_intl
  0 (V2/V4 OPEN: API serves 200 but games:[] -- next wake: honest-empty vs fill-bug); CLV 7 settled
  / 0 clv; bankroll 97.0u (net -3.0, day 06-26); reject delta 0 (plumbing SHIP, no signal).
  NEXT: V2/V4 -- determine if mlb/soccer_intl empty boards are honest-empty (no card clears the
  tier gate / no game in-window) or a real snapshot-fill bug; fix if bug, document if honest.
- WAKE-18 (READINESS, 2026-06-26 ~17:15): flywheel healthy (23/23 all READY; m13 was mid-RESTART,
  transient). OPS MISHAP + RECOVERED: ran `stop_bot.py --status` to probe -- it IGNORES args and
  ACTUALLY STOPPED the bot (disabled CourtVisionBot task + set stop_requested=True). Reversed BOTH
  (schtasks ENABLE + cleared flag); flywheel never halted (separate from go.ps1). Memory written:
  PROBE the stop flag by READING .bot_state/live_status.json, NEVER run stop_bot.py.
  V2/V4 = FALSE ALARM (my WAKE-17 probe bug): /api/v1/bestbets/<sport> serves status=ok, mlb 16
  games/94 candidates/10 best_bets + soccer_intl 6 games/24 candidates/0 best_bets (honest no-bet,
  games shown); daemon board /api/bestbets/board serves 2461 mlb / 85 soccer cards (stale=by-design
  serve-stale-never-green). The WAKE-17 'games:[]' was reading d['cards'] when the envelope uses
  d['games']. NO board bug. Corrected here.
  SHIP 94cc287c (grade_summary under-count): scoreboard.py n_settled required clv_pct, so all 7
  settled paper_pm bets (clv_status='no_close') were dropped -> grade_summary.json showed n_settled=0
  + flat_unit 0/0 despite a real 1W/5L paper record. Split populations: n_settled + flat-unit count
  ALL settled; CLV stats stay over the clv-bearing subset; added n_no_close. Live now n_settled 0->7,
  flat-unit 1W/5L (mlb 6 / soccer 1), CLV INSUFFICIENT_DATA. SAFE: real-money gate recomputes from
  ledger rows (summary advisory-only, never trusted) -> cannot spoof. NEW test_scoreboard.py +5; 59
  dependent green; artifact regenerated. Scoreboard: props settled 0 (pend to tonight's finals);
  boards games-shown mlb 16 / soccer_intl 6 (WORKING); CLV 7 settled / 0 clv; bankroll 97.0u (net
  -3.0); reject delta 0 (SHIP). NEXT: K1 Kalshi team_total pricer (add SP-ERA + park, calibrate vs
  settled totals through the REAL gate, place ONLY if it beats/matches the Kalshi line OOS else
  REJECT-log) -- the next genuine ceiling/exec item now that V1-V4 are closed.
- WAKE-22 (READINESS, 2026-06-26 ~17:30): m13 props pred tick RESTART FLAP ELIMINATED (was restart
  every ~22 min, now zero restarts). TWO-LAYER FIX in scripts/platformkit/props/props_pred_tick_runner.py:
  (1) START beat at tick() entry (was end-only -> sleep+score=700s > 660s fresh threshold);
  (2) NEW _beat_during_scoring background thread every 300s during _score_props_bounded (scoring
  700+ props takes 700-985s > threshold, so start-beat alone still fails after ~660s). FIX VERIFIED:
  background beater fired exactly at t+300s (mtime 17:35:00 updated mid-scoring), no supervisor restart
  since PID 31112 launch at 17:29:59. 9/9 tests pass, 297 LOC.
  ALSO: soccer_intl old DraftKingsProvider (sportsbook-us-il 404 endpoint) REMOVED from prop_edge_config.py
  + test updated (34/34 pass). MLB calibration cache stamped settle_logic_version=v2-void-nan (was null;
  stale warning fired every tick). Full stack: 14/14 supervisor daemons GREEN; paper_today fresh (388
  placed/444 pending/3 settled/-4.0u, executed=False, edge_claimed=False); predict :8099 200. STALE
  by-design (untracked/long-cadence): m14/m17/m15/m18/m8. Props snapshot stale (m13 scoring in progress);
  will refresh on next tick completion. NEXT (CEILING): T2 Mondrian group-conditional conformal OR E1
  LLM in-game context (detail_layer_gate template backend).
- WAKE-21 (CEILING/T4 ACI, 2026-06-26 ~15:57): SHIP fb468a9c -- 3rd CEILING experiment answered
  through the REAL gate -> HONEST REJECT (pinball + planted_null). Q: does Adaptive Conformal
  Inference (Gibbs+Candes 2021) hold in-game interval coverage under distribution drift better
  than static split-conformal? A: PARTIAL -- coverage YES, sharpness NO -> do NOT default-on.
  New leak-free streaming wrapper (scripts/platformkit/ingame/aci_online.py, 249 LOC, +13
  tests, +36 regression green): pure numpy+stdlib, online a_{t+1}=a_t+gamma*(a-err_t), width-
  only multiplicative adjustment per tick around base band midpoint. At tick t, ACI sees ONLY
  series[:t] -- never the future. Synthetic non-stationary stream (2000 ticks, sigma DOUBLES
  at t=500, gamma=0.05, target 90%): ACI coverage 89.9% (gap -0.001 vs nominal) vs static
  77.7% (gap -0.123) -- ACI RECOVERS coverage cleanly under drift. BUT pays pinball cost (wider
  bands) -> fails pinball <= static+0.01 check; planted-null (iid resample) shows residual-var
  drift even after shuffling -> null_collapses=False -> REJECT:pinball+planted_null. Default-OFF
  wrapper; not wired into ingame_serve_recal_seam. Reusable for in-game wp interval coverage
  replay, prop-band streaming, future Mondrian+ACI composition. Scoreboard: REJECT delta +1
  (ACI online).
  NEXT (CEILING queue, ranked): T2 Mondrian / group-conditional conformal on prop coverage
  (scripts/platformkit/mondrian_conformal.py) -- attacks per-regime miscoverage (stat x minutes
  -tier), wraps the EXISTING conformal/coverage code, the lightest-touch experiment that may
  unstick CQR's over-cover gap on subsets; OR T3 Venn-Abers in calibrator_zoo (probability
  validity guarantee + [p0,p1] band on the probability). T5 NGBoost stays last (highest reject
  prior given the pregame data ceiling).
- WAKE-20 (CEILING/T1 CQR, 2026-06-26 ~15:50): SHIP a642eac5 -- 2nd CEILING experiment answered
  through the REAL gate -> HONEST REJECT 7/7. Q: does CQR (Romano+ 2019, adaptive-width
  conformalized quantile regression) beat the incumbent constant-width split-conformal for NBA
  prop intervals? A: NO on the strict gate -- the existing split-conformal ships unchanged.
  New leak-free WF gate (domains/basketball_nba/prop_cqr.py, 288 LOC, +10 tests, +38 regression
  green) reuses pregame_oof.parquet (356k rows, 7 stats): chrono 50/25/25 train/calib/test split;
  lightgbm quantile (alpha/2, 1-alpha/2) over leak-free per-row features (rolling_mean_15,
  rolling_std_15, rolling_median_15, oof_pred, n_prior, season_avg_to_date -- all built from
  STRICT prior rows via shift(1)); conformity E_i = max(q_lo-y, y-q_hi) on CALIB; finite-sample
  conformal correction; planted-null = joint-shuffle features. Real-OOF verdict (n_test=11896
  per stat, alpha=0.10): CQR beats split-conformal on PINBALL on ALL 7 stats (pts ast reb fg3m
  stl blk tov; cqr_pb < sc_pb every row) AND on WIDTH (sharper bands every row) BUT
  OVER-covers nominal 90% (cov 91-96% vs sc 88-91%) -> fails |cqr_gap| <= |sc_gap| proximity;
  planted-null inflation (>1.5x) sub-bar on real data too -> REJECT all 7. Default-OFF
  measurement script; NOT wired into pricing. Honest finding: adaptive Q-quantile is sharper
  AND more conservative -- the conformal correction over-corrects on this OOF; the room CQR was
  supposed to fill (under-coverage) doesn't exist in the way the doc predicted on these splits.
  Reusable CQR template kept; next ceiling levers: (a) per-stat or per-(stat x minutes-tier)
  conformalization (Mondrian T2 hybrid), (b) T5 NGBoost / quantile-GBDT distributional head,
  (c) ACI online conformal for in-game (T4). Scoreboard: REJECT delta +1 (CQR adaptive-width).
  NEXT: T4 ACI online conformal in-game (scripts/platformkit/ingame/aci_online.py) -- attacks
  the freshness-drift gap, thin one-param wrapper, respects minimal-feature constraint, low
  rejection prior.
- WAKE-19 (CEILING/K1, 2026-06-26 ~17:45): flywheel healthy (23/23 all READY); stop flag clear
  (read .bot_state, did NOT run stop_bot.py). SHIP 1447a72b = K1 answered through the REAL gate ->
  HONEST REJECT. Q: does starting-pitcher RA-as-of + park factor make the Kalshi team_total pricer
  bet-ready? A: NO -- do NOT enable the placer. New leak-free WF eval (domains/mlb/totals_sp_park_eval.py,
  300 LOC, +5 tests) reuses totals_sigma_wf._build_wf_lambdas (run-rate lambda baseline) + OLS-blends
  asof_park.park_factor + (home+away)_sp_ra_asof; chronological 50/50 split, TRAIN-only centering,
  12037 held-out games: rmse_base 4.5621 -> rmse_combo 4.5313 (delta -0.0308 runs, BELOW the -0.05
  SHIP bar); planted-null collapses to -0.0003 -> the -0.031 is a small real-but-sub-threshold effect.
  Park+SP on totals is subsumed by the market, consistent w/ the prior moneyline SP-form REJECT.
  Verdict -> data/frontend/funnel/mlb_totals_sp_park_gate.json (scouting_only, vs_close UNPROVEN, no $).
  Kalshi team_total placer STAYS default-OFF -- never bet a biased pricer (exactly K1's bar).
  Scoreboard: props settled 0 (pend to tonight's finals); boards mlb 16 / soccer_intl 6 (working);
  CLV 7 settled / 0 clv (no_close); bankroll 97.0u (net -3.0); REJECT delta +1 (totals park+SP).
  NEXT (CEILING queue): CQR prop intervals (domains/basketball_nba/prop_cqr.py, GPU quantile fit) --
  the documented prop-interval under-coverage is REAL room (unlike efficient pregame reclaims);
  then E1 LLM in-game context (detail_layer_gate offline-template), asof reclaims NBA/tennis/soccer.
- INTELLIGENCE/LLM design DONE (2026-06-26c): docs/research/ceiling/LLM_CONTEXT_PRIORS.md -- use LLM +
  person-free brain to contextualize games into LEAK-FREE as-of priors, run independently (default-off
  daemon), gated like any signal. HONEST: LLM context is a HIGH-reject lane (CV_LLM_SCHEME already
  rejected +0.005 p=0.87; pregame efficient) -> ships SCOUTING-ONLY unless IN-GAME context moves OOS
  calibration. Reuses knowledge/contextual.py + detail_layer_gate.py (planted-null built in) +
  scheme_prior.py. CHEAPEST DECISIVE FIRST (E1, ~zero API cost): gate ONE regime_structural channel
  (offline template backend) through detail_layer_gate.py on 2 NBA seasons + shuffled-context null ->
  real SHIP/REJECT number; only pay for Haiku/PBP-text backend if the free channel survives.
  NEAR-TERM QUEUE: (next) CQR prop intervals, then E1 LLM in-game context, then asof reclaims (NBA/
  tennis/soccer), then ACI in-game.
- GAP AUDIT + FIX (2026-06-26 ~15:14, user "no gaps"): paper trading IS live (305 bets: 298 open/7
  settled, mlb+soccer_intl, newest 15:08). OLD-lines backtest fuel EXISTS (historical_event_odds 9.8M
  + line_history 193M). PRIMARY GAP FOUND + FIXED: live supervisor (20h uptime) predated m15_prop_settle
  / m16_prop_close_capture / m17_kalshi_scan / m18_pm_close_capture -> all 7 settled were clv_status
  'no_close' (CLV unmeasurable). RESTARTED stack (stop.ps1+go.ps1): now 23 procs all READY, the 4
  daemons LIVE -> close-capture + prop-settle restored; CLV will populate as bets settle. REMAINING
  SMALL GAP (queued for builder loop): grade_summary reports n_settled=0 despite 7 settled in ledger
  (PM settled rows not counted by the summary reader) -- fix the reader to count all settled + verify
  CLV starts populating post-restart.
- EXEC/EDGE AUDIT (2026-06-26 ~15:20, user 'kalshi high level + best bets + edges'): FRONTEND WORKING
  (webapp:3000=200, /api/paper/trail=200 real rows incl settled paper_pm w/ unit_result); KALSHI EXEC
  WORKING for game-winner ML (30 pm bets, m12 live; m18 now CLV-grades them post-restart); BEST-BETS
  board generating (best_bets.json cards, m10 fresh); m17_kalshi_scan scanning liquid surface. HONEST
  GAP (calibration not plumbing): Kalshi props/totals are LIQUID (~1c spread) but we do NOT bet them --
  totals pricer biased +5.2% (ignores starting pitcher+park), prop pricer matched 0 live. Betting them
  now = fabricated edge. PATH TO HIGH-LEVEL KALSHI (queued AHEAD of CQR/LLM): (K1) make kalshi_pricers
  team_total pricer bet-ready -- add starting-pitcher-ERA + park, CALIBRATE vs settled totals through
  the REAL gate, enable placement ONLY once it beats/matches the Kalshi line OOS; (K2) populate the
  prop board with Kalshi-offered stats so the prop pricer matches live; (K3) more soft books for +CLV
  line-shop. Build in scripts/platformkit/pm_trading/**; gated; never bet a biased pricer.
- EFFICIENCY AUDIT (2026-06-26 ~15:30, user 'efficient + GPU'): HONEST = system is ALREADY efficient,
  NO bloat to fix. GPU RTX 4060 healthy 42% util / 7GB free (torch cu121, CUDA avail). Daemon stack
  lean: ~3GB total / 24 procs (~120MB avg, max 394MB) + webapp 164MB. The 91% system RAM is mostly
  NON-system dev-box procs (editor/browser/Claude), not the AI. Do NOT make-work on lean daemons.
  STANDING EFFICIENCY DISCIPLINE (L5, folded into the loop prompt): (a) any NEW model fit the loop
  builds (CQR/NGBoost/Kalshi-totals calib) defaults to GPU (device='cuda'/gpu_hist/lgbm device='gpu')
  with CPU fallback; (b) offload heavy compute (CV, full-season WF) to RunPod 3090, keep local box
  light; (c) LLM = Haiku Batches + content-hash cache, call only on live state; (d) profile-before-
  optimize -- only touch a hot path with a measured before/after, never fabricate an efficiency win;
  (e) per-file tests only (full suite freezes the 16GB box).
- MLB + WC (soccer_intl) VERTICAL AUDIT (2026-06-26 ~16:10): BOTH live + betting on today's slate
  (mlb 285 bets=240 props+37 Kalshi ML, newest 16:08; soccer_intl 57=52 props+5 Kalshi ML, newest
  15:40). Models hardened tonight (mlb MOV-Elo bug fix + tests; soccer rho_fit fix). GAPS before
  'highest level' (queued, verify ahead of K2/CQR): (V1) PROP SETTLEMENT -- 0/292 props settled;
  m15_prop_settle just came online (2min) -> VERIFY props actually settle once games finalize; if not,
  it's the MLB city-abbrev name-match settler bug resurfacing (prop_settler_mlb._team_hit). (V2)
  FRONTEND BOARDS show 0 games for mlb + soccer_intl despite 240+52 props placed today -> snapshot
  fill/staleness gap (known FRONT-END FILL issue), NOT honest-empty -> regen + verify cards fill.
  (V3) 8 mlb bets have market_type='?' -> trace + label. (V4) bestbets API /api/v1/bestbets/<sport>
  returned a parse error -> verify it serves mlb + soccer_intl. CLV still pending (no_close on the few
  settled; populates as new bets settle with captured closes via m16/m18).

## >>> ACTIVE MISSION (user directive 2026-06-26): FULL-FUNNEL, ALL SPORTS, SMARTER EVERY NIGHT
Run the full funnel end-to-end (DATA->SIGNALS->MODELS->ENGINES->PREDICTIONS->INTEL->LINES->
EXECUTION->IMPROVE) for every in-season sport (NBA, MLB, soccer, soccer_intl, tennis; NFL in
season), unattended, getting better every cycle. Win = calibration + measured CLV; NEVER a
fabricated $/edge; REJECT logged = success. Full directive + funnel + per-cycle output spec:
.planning/platform/BUILD_BACKLOG.md SECTION 0 (ACTIVE MISSION). The runtime FLYWHEEL (go.ps1
supervisor m1..m18 -- capture lines / paper-trade / settle / CLV / m4 recalibrate) runs detached
at ~zero token cost and keeps improving predictions overnight with or without this chat; the
builder loop self-schedules wakes to add gated code/signals/models on top. Enders: `bot stop`
or `program_complete` only.
- WAKE-1..15 (2026-06-26 hardening burst: twin-aware open counts, NaN/inf line guards,
  domain-engine test coverage, 3 real bug fixes) -> ARCHIVED verbatim in
  .planning/archive/NOW_ARCHIVE_2026-06.md

## NEXT (max 5 -- action | where | done-when) [MASTER PLAN v2 2026-07-02: .planning/PLAN_SELF_IMPROVING_AI.md -- 8 phases ending in PRE-REGISTERED proof-of-edge criteria (8.1a-g) + human-gated real-money pilot runbook (8.2); economics phase 6 (cost model/maker sim/beat-the-line scoreboard) decides if money ever happens; NBA-season readiness phase 7 before Oct. This queue = the Phase-1 head]
[RATIFIED QUEUE 2026-07-03 -- .planning/AUTONOMY_CHARTER.md governs unattended wakes: routing, spend rails, decision rights, wake protocol. Read it before pulling work. SPRINT MODE amended: usage rail LIFTED thru 07-06 per user directive; full fleet per wake; Fable decides even if loop model switches to Opus (see memory feedback_sprint_fleet_orchestration_2026_07_03).]
[SPRINT WAKES 1-21 DONE 2026-07-03..05 (~84 lane commits, every ship Opus-reviewed; ledger above). USER DIRECTIVE 2026-07-04 ~14:00Z (user present in-session): make the AI MOST ROBUST; webscrape every live source; use OWN historical odds + data as training fuel (self-improvement); use advanced techniques (conformal family per docs/research/ceiling/ADVANCED_TECHNIQUES.md); keep pushing the in-game program. Honesty rails unchanged (calibration yardstick, no $-edge claims). USER RATIFIED LIVE: (a) boot.ps1 restart EXECUTED ~14:15Z by orchestrator ATTENDED (20 PIDs drained incl. port-3000 orphan; governance preflight PASS; supervisor PID 30864) -- wave-22 lane 0 verifies activation; (b) PROPOSED_soccer_xg_wiring.md APPLY approved (model-affecting ship ratified; fresh Opus review + gate re-run before commit); (c) OddsAPI $59 purchase DECLINED -- user chose BUILD OUR OWN NBA close corpus from owned PM/Kalshi venue history instead.]
[USER DIRECTIVE 2026-07-04c (VALIDATED INTELLIGENCE): player-level in-depth ACCURATE intelligence -- "top 10 best shooters" answerable from rigorously accurate own data; LLM plays a big role but everything validated at the highest level by predictions. Fable interpretation: queryable player-intel layer w/ provenance + sample floors + independent recompute validation; LLM context via charter lane (v) planted-null gate (fail -> SCOUTING-ONLY). Wave-26 fleet launched on this.]
0. [WAVE-26 INTEL FLEET, in flight] (a) player-intel foundation: NBA shooting intelligence from owned parquets (metrics + pre-declared ranking criteria + provenance + floors, claims JSONL contract); (b) claims-validator: independent recompute harness over the claims contract; (c) L4 LLM-context gate PRE-REGISTRATION per charter lane v (shuffled-context planted-null harness, no LLM wired yet) | domains/basketball_nba/ + scripts/platformkit/ | Opus-PASS lanes committed, demo answer to "top 10 shooters" with honest caveats.
0b. [WAVE-27 BASKETBALL-TRUTH INTELLIGENCE -- USER REFINEMENT 2026-07-04e: "shooting stats lie or don't tell the whole story... Steph is the best shooter, his numbers might not be the best... most pressure, most gravity... use every point of data and how games play out and predictions and outcomes to determine these players... using LLM to make predictions and analytics is way more complicated and is my edge". The wave-26 naive composite putting Keon Ellis #1 = the exact demonstrated failure mode.]
   (R, LAUNCHED) Opus sport-research lane: basketball-truth metric spec grounded in the ACTUAL 28 player-atlas + 13 team-atlas + tracking schemas -- multi-factor shooter/scorer quality (volume, efficiency-vs-league, difficulty [pull-up share/shot-clock/time-to-shot], gravity/spacing, usage/creation burden, scheme splits), weights DECLARED from basketball reasoning BEFORE fitting (no narrative-tuning); face-validity checklist (Curry-class top-decile = diagnostic, NEVER a fitting target) + pre-registered PREDICTIVE-VALIDITY test design (intelligence-adjusted ranking must forecast future out-of-sample shooting outcomes better than the naive ranking, walk-forward) + in-game conditioning hypotheses as gate specs (usage x hot-night scoring, scheme-fit effects).
   (B/G, after 26-fix lands) build the multi-factor index on the claims contract (multi-source joins) + run the predictive-validity gate; both rankings published side by side with honest verdicts; ask-anything skill rides on top | docs/research/intel-layer/ then domains/basketball_nba/ + scripts/platformkit/ | Curry-check reported as diagnostic; gate verdict decides which ranking is CANONICAL.
0c. [WAVE-28 MULTI-SPORT INTELLIGENCE PROGRAM, LAUNCHED -- USER DIRECTIVE 2026-07-04f: "many sonnet and haiku researchers, opus conductors, for each sport... every little aspect of each sport, on court off court, how they work together... make it into data using predictions and historical odds... make obsidian better and memory as good as possible... use github.com/DietrichGebert/ponytail for low usage"] (a) 4 Sonnet sport-truth researchers (MLB, soccer_intl, tennis, WNBA -- NBA already in flight): per-sport inventory of ALL owned data + full intelligence-dimension enumeration + dimension->data map (gaps = scraping targets) + pre-registerable validation hypotheses vs predictions/historical odds; (b) storage-audit lane (data/ layout health, retention coverage, proposal-only); (c) Opus CONDUCTOR synthesis after all lanes: cross-sport intelligence program, generalized claims/validator contract, prioritized build queue, vault/obsidian + auto-memory feed design (brain_pipeline proposal, no hand-edits, no rebuild launch); (d) PONYTAIL: verified real (73.7k stars, MIT, efficiency skill) -- decision-ladder discipline injected into all fleet briefs NOW; harness plugin install = 2 interactive /plugin commands -> HUMAN QUEUE | docs/research/intel-layer/ | 4 sport specs + program doc + storage spec on disk.
HUMAN QUEUE ADDITION (ponytail): run in an interactive session, two separate prompts: (1) /plugin marketplace add DietrichGebert/ponytail (2) /plugin install ponytail@ponytail -- then all future sessions run it automatically (default mode full; /ponytail lite|ultra|off to adjust).
0d. [WAVE-29 BUILD FLEET, LAUNCHED ~18:25Z -- conductor-ratified queue top 4] (1) WNBA zero-fetch extraction: 168-game CDN corpus -> season-aggregate player/team parquets (unblocks ~20 dims); (2) claims contract += criteria.entity_key (producer+validator, 12/12 stays VERIFIED, rankings byte-identical); (3) NBA shooter_quality_v1/scorer_quality_v1 scored on 329 qualifiers per FROZEN spec weights + predictive-validity gate run (naive stays canonical if it wins; Curry/Ellis positions reported as diagnostic); (4) MLB SP within-start fatigue in-game conditioning gate (ingame_layer_gate_nba clone, planted-null, walk-forward) | per intelligence_program.json | Opus-PASS lanes committed with honest verdicts. Deferred to wave-30: tennis surface-hold, WNBA rest covariate, schema-drift snapshots, ESPN injuries, altitude table.
0e. [COMBINATION-MOAT PROGRAM -- USER DIRECTIVE 2026-07-05 ~17:40Z (in-session):
   "stop rejecting as many by combining many signals using intelligence -- that's
   the moat." FABLE INTERPRETATION (binding): NO gate is lowered, ever; the reject
   RATE stays high by design -- what changes is candidate QUALITY and testing
   COMBINATIONS as first-class citizens. Proof-of-concept already on the board:
   MLB tuned method = elo_logit + sp_first6_diff_ew (SP-form solo-REJECTED as an
   edge, yet -20% ECE as a feature in the 2-signal calibration stack). Lanes:
   (a) per-sport JOINT CALIBRATION STACKS: walk-forward regularized stacks over
   the leak-free reject-ledger signals; gate the STACK vs base AND vs devigged
   close; planted-null = shuffled-feature stack must die; FWER min_corpora_eff
   floor (wired wf_ff769e21) MANDATORY; families pre-registered before any fit.
   (b) intelligence-guided INTERACTIONS only (mechanism-motivated from the
   claims/atlas layer: umpire-zone x SP-whiff-style, rest x pace, surface x
   hold-form), proposed via discovery.py / Fable-authored lists under a bounded
   comparison budget -- NO brute-force feature crosses. First family member =
   soccer home_sot_for_l10 cross-corpus replication (wave wf_ff769e21 survivor).
   (c) prior-x-state IN-GAME fusion (trust-gated segment models) as real-state
   corpora accrue (KBO bar ~mid-Aug; depth corpus day-1 today).
   GATING NOTE: PROPOSED-combo-daemon-wiring.md is "inert until sentinel exists"
   and data/cache/improve/PIPELINE_ENABLED was FOUND ARMED 2026-07-05 (arming
   party unconfirmed) -- get user confirmation of the sentinel BEFORE applying
   the combo-daemon manifest wiring; stacks/gates above need no sentinel.
   | domains/<sport>/ + scripts/platformkit/ (combo_bandit, meta_flex_fwer, FWER
   rails exist) | done-when: >=2 sports have a gated STACK verdict on disk
   (SHIP or honest REJECT, planted-null + replication attached); most stacks
   REJECTING is the expected, successful outcome.
0h. [DEPTH PROGRAM / COMPLETE KALSHI PAPER PRODUCT -- USER DIRECTIVE 2026-07-05e
   (in-session): "keep building everything so the AI is most in-depth it can
   be... complete product that works on Kalshi API automatically... no holes...
   all data, all signals, all models, as many engines per prediction, really
   testing, a very advanced LLM conducting... ask any sports question accurately
   with substantial data support... think of everything." FABLE FRAME (binding):
   (a) REAL-MONEY BOUNDARY UNCHANGED -- Kalshi real execution stays HUMAN-ONLY
   default-DENY forever (charter S6); the buildable target is the COMPLETE
   AUTOMATIC PAPER PRODUCT (capture->predict->decide->paper-execute->settle->
   learn per sport on Kalshi) + the pre-registered proof criteria (master plan
   8.1a-g) + human pilot runbook (8.2) that gate any go/no-go, which is the
   user's call alone. (b) "NO HOLES" MADE MEASURABLE: the DEPTH PROGRAM doc =
   complete enumeration (per sport: data assets -> derivable signal families ->
   model/engine classes -> intelligence dims -> ask-layer gaps -> Kalshi
   product-completeness table) + a ranked GAP MATRIX that becomes the STANDING
   QUEUE the test factory consumes each cycle. (c) LLM conductor = Opus
   program-synthesis lanes + Fable adjudication, exactly the loop already
   running. (d) All gates/rails unchanged -- depth grows through the factory,
   never around it. | docs/research/depth-program/ + the standing NOW queue |
   done-when: DEPTH_PROGRAM doc on disk w/ gap matrix + completeness table,
   and the queue head pulls from it every cycle.]
0f. [CONTEXT-CONDITIONING DEPTH -- USER DIRECTIVE 2026-07-05c (in-session, verbatim
   intent): "teams schedules everything impacts players; a player can be a good
   shooter on a bad shooting team; everything affects everything -- depth to every
   thing and how every little part reacts to another; AI should be getting every
   signal, testing them, using smart LLMs on how signals combine into models,
   building new models testing against each other, knowing how every little aspect
   reacts to another, INDEPENDENTLY." FABLE INTERPRETATION (binding, extends 0e):
   (a) CONTEXT-ADJUSTED player intelligence dims as validated claims FIRST
   (descriptive): player metric vs team-context (e.g. 3P% vs team-minus-player
   environment), opponent-context, schedule-context (rest/B2B splits) -- claims-
   validator recompute mandatory; these then become LEGAL stack/interaction
   ingredients via prereg. (b) LLM-AS-PROPOSER: smart-LLM (Opus) lanes read the
   claims/atlas/reject-ledger intelligence and PROPOSE mechanism-motivated
   interaction candidates (bounded lists, each w/ mechanism rationale + exact
   leak-free sources + coverage check); proposals cost K (FWER budget counts every
   enumerated candidate) but need NO L4 gate (search guidance, not features).
   LLM-derived FEATURES (text->model inputs) still require the L4 shuffled-context
   planted-null gate, fail=SCOUTING-only forever. (c) MODEL TOURNAMENT: every
   gated SHIP becomes the next base (ratchet semantics on the stack harness);
   REJECTs accumulate in the ledger = the map of what does NOT interact (that is
   knowledge too). (d) INDEPENDENCE: proposer->prereg-amendment(sha-pinned,
   Fable-adjudicated)->gate->ledger runs as the standing loop cadence. CLOSED
   CLASSES STAY CLOSED (travel-predictive, ast_rate, SP-fatigue, player-profile
   in-game, home_sot family, tennis solo dims) -- context-ADJUSTED descriptives +
   NEW interaction families are the legal surface. | domains/<sport>/ +
   scripts/platformkit/ | done-when: context-adjusted claims dims VERIFIED on
   disk + first LLM-proposed interaction family sha-pinned + gated w/ honest
   verdicts.]
[WAVES 22+23 CONSUMED 2026-07-04 ~15:50Z -- ledgers above. Queue below = wave 24; the bottleneck is now largely WALL-CLOCK forward-evidence accrual -> cadence rule: light check-ins unless a gate decides or the user messages.]
1. [LIVE-ACTIVATION-VERIFY] once MLB slate is live (~17:00Z+): enrichment fields present in fresh grade rows, kalshi pacing counters nonzero in capture heartbeat, m13 fresh props_snapshot + freshness_sla green (relaunched PID 14028 w/ timeout fix), grade-writer clamp writing late-inning rows; npb/kbo FIRST GRADES land overnight (their game windows) | orchestrator light check-in | verifier PENDINGs -> PASS or triaged.
2. [FORWARD-GATES-WATCH] wall-clock accrual, no fleet: MLB tail fwd (floor ~20), soccer_intl xG forward (floor 8/half), wnba/npb/kbo tail stamps live -- escalate to a decision wave ONLY on a real headline_verdict or an allowlist-external regression | forward_evidence_scoreboard | gate decides -> decision wave.
3. [OWN-CLOSES-FOLLOW-ONS] (a) is_live() bare round-trip asymmetry in ops/liveness (inert, one-line guard); (b) nba_close_corpus.py doc-latitude overage note; (c) consider WNBA/MLB own-close corpora on the same last-tick-before-commence pattern (PM/Kalshi history already on disk) | scripts/platformkit/venue_history/ | corpora + honest benchmarks per sport.
HUMAN QUEUE (updated 2026-07-04 wave 22): restart DONE (user-attended); xG wiring APPLIED; OddsAPI DECLINED (build-own shipped, 332 games). Still open: soccer-suppression memo; m32 weather_totals SHIP_REVIEW; states-gate CI adoption at bigger n; prop-guard KEEP ack; UI-off option; reconcile_survivors adopt design; register_autostart.ps1 -Register in an ELEVATED shell (standing).

DONE (2026-07-02): [P2.2] Feed-health scoreboard SHIPPED -- NEW scripts/platformkit/odds_provider/feed_health.py + feed_health_runner.py (registered as supervisor ProcSpec m30_feed_health, HEARTBEAT readiness, 600s cadence): live-probes every (provider, sport) pair the REAL slate uses (reuses aggregate.default_providers(), not a synthetic ping) and classifies GREEN (real data OR an honest empty/unsupported-sport degrade -- not an outage) vs RED (auth/forbidden/timeout/parse/unexpected-shape/exception -- the scraper is actually broken). LIVE-VERIFIED it catches a REAL fault: a live run hit an actual Pinnacle 401 Unauthorized on soccer_intl (transient rate-limit from repeated calls this session) that `aggregate()` had been silently swallowing (that venue just vanishes from the merged slate with no visible signal) -- feed_health correctly surfaced it as one RED row while mlb/espn/fanduel/kalshi/polymarket stayed GREEN. 16 new tests green (10 feed_health + 6 runner), both files well under 300 LOC (185, 115). Also updated tests/supervisor/test_manifest.py's service-set assertion for m30 (21 green).
DONE (2026-07-02): [P2.1] First new keyless book feed -- FOUND ALREADY SATISFIED, no code needed: live-verified `best_price_audit.audit(('mlb',))` -> max_books=3 (pinnacle+fanduel+espn:DraftKings), 9/10 games shoppable, matching the live best_price_scan.json on disk. The plan's premise ("live max_books=2") was itself stale -- the 2026-06-29 memory this session started from already recorded "only 3 shoppable" that day, so FanDuel's team-moneyline provider (odds_provider/fanduel.py, already in aggregate.default_providers()) had already closed this gap before today. Investigated a genuine 4th book: DraftKings-direct (via the curl_cffi-TLS-impersonation pattern prop_draftkings_v2.py already uses) is technically reachable -- probed live, confirmed working, found the real Game-Lines category/subcategory ids (league 84240, category 493, subcategory 4519 for MLB) -- but DK is ALREADY represented via ESPN's republished "espn:DraftKings" line, so a direct DK feed would duplicate a book already counted, not add independent line-shopping diversity. BetMGM (the one book with existing scaffolding, odds_provider/prop_betmgm.py) 403s live from this environment (WAF/datacenter-IP block -- confirmed by direct probe, an external constraint documented in the module's own docstring, not a bug). No further action; queued as a FOLLOW-UP (NEXT item 4) rather than forced.
DONE (2026-07-02): [P1.4] CLV-result reconciler SHIPPED + RESOLVES the paper_pm contradiction honestly -- NEW scripts/platformkit/clv/clv_result_reconciler.py: for a channel's measurable (true_close, non-suspect) settled rows, computes the CLOSE-IMPLIED expectation (Poisson-binomial normal approx for win count + EV for units, both driven by each bet's OWN fair_close_prob at the close) and z-scores the realized record against it. Live result on paper_pm (n=36, current numbers had moved since the plan was written: realized 16-20-0 net -4.01u, mean CLV +13.51%* significant): close-implied expected wins=18.06 (z=-0.69), expected units=+4.87 (z=-1.24) -- both |z|<1.96 -> VERDICT=GENUINE_VARIANCE, not a stale/fabricated close. Also mechanism-audited the close-capture path by hand before trusting the number: line_store.get_close's lock window is a real [tip-30min, tip] check (odds_provider/line_store.py:245-254); close_capture.py's LIVE Kalshi path can in fact never confirm is_proxy=False (a real-fetch always returns OddsEvent objects with no settlement-status field, so `is_settled` is hardcoded False at kalshi.py's normalization boundary) -- so every paper_pm true_close row in production is actually sourced from the line_store lock-window snapshot, a genuine pregame quote, not a Kalshi-settlement-price artifact. Ran the same reconciler on `moneyline` (n=28): also GENUINE_VARIANCE (max |z|=0.20). 12 new tests green, 241 LOC (<=300). Committed 2026-07-02 (07a3f4c4/e9f84e6c).
DONE (2026-07-02): [P1.2] Pregame prop close capture UNBLOCKED for MLB -- the capture pipeline (prop_close_capture_pregame.py -> prop_close_store -> prop_settler's true_close path) was ALREADY fully built and wired (from an earlier session) and IS running live (m16 daemon, fresh heartbeat, polling every 60s), but was capturing 0/168 open MLB pregame props because its only pregame two-way source, FanDuel (odds_provider/prop_fanduel.py), had NO customPageId entry for "mlb" at all -- 100% blocked at the sport-key level regardless of timing. FIXED: added "mlb":"mlb" to _PAGE_ID (live-probed: real page, 9 real MLB events surfaced) + added MLB player-prop market-name fragments to _PLAYER_STATS (total bases/rbis/home runs/stolen bases/earned runs allowed/hits allowed/walks allowed/batter+pitcher strikeouts/hits+runs+rbis -- deliberately NOT bare "hits"/"runs"/"strikeouts"/"outs", which collide with the real team/inning market titles observed live e.g. "1st Inning Hits", "Total Runs", "Runs Odd/Even", and would otherwise fabricate fake player props off a team market). Live-probed today's FanDuel MLB page: 9 real events, but games are ~8h+ out and only team/inning markets are posted so far, same "posts closer to game time" pattern already documented for soccer_intl -- so captured stays 0 TODAY, but the sport-key block that made it structurally impossible is gone; it activates automatically once FanDuel posts player props (no further code needed). 4 new regression tests (page-id resolves past "unsupported sport"; a real team/inning-market event correctly parses to 0 props; a real player-prop event parses correctly; provider end-to-end). 12/12 test_prop_fanduel.py green, canon_stat already had full MLB stat vocabulary (no change needed there). File stays 236 LOC (<=300). Committed 2026-07-02 (07a3f4c4/e9f84e6c).

DONE (2026-07-02): [P3.1] MLB moneyline DATA_LIMITED seam FIXED end-to-end -- edge_finder's mlb_moneyline market went from a permanent DATA_LIMITED (empty corpus) to a real MATCH verdict (n=2326 states, BSS=+0.0025, DM p=0.08 -- efficient mainline, honest null, exactly the expected result). TWO things done: (1) wired market_coverage/corpora.py's mlb_ml_states(root) to DELEGATE to odds_provider.oddsapi_close_corpus.build_states('mlb') instead of the old event_id-join that always returned [] (root is now unused/ignored -- kept only for signature compatibility with the other corpora builders); (2) FOUND+FIXED a real regression bug the wiring surfaced: oddsapi_close_corpus._mlb_result_fn built its date join key via `box["date"].astype(str).str[:8]`, which on today's datetime64-typed date column (domains.mlb.ingest_espn_box normalises dates that way, likely since WAKE-27's 07-01 box refresh) produced "2026-06-" (month-only, dashes) instead of "YYYYMMDD" -- silently zeroing the WHOLE join (build_states('mlb') was returning 0 states, not the 211 the 2026-06-26 memory recorded). Fixed to pd.to_datetime(...).dt.strftime("%Y%m%d") (mirrors the already-correct _soccer_result_fn pattern next to it) -> now yields 2326 real states, close Brier 0.2423. Added regression tests locking in both the date-format fix (test_oddsapi_close_corpus.py, 2 new tests) and the delegation (NEW test_corpora.py, 2 tests) since neither seam had direct per-file coverage before (only synthetic-injected builder tests existed). 64/64 tests green across the whole market_coverage + oddsapi_close_corpus suites; both edited files stay well under 300 LOC (corpora.py actually SHRANK, 167->145). No $ claim; the MATCH verdict is the expected honest result per the no-edge-claims discipline. Committed 2026-07-02 (07a3f4c4/e9f84e6c).

DONE (2026-07-02): [P1.1] Soccer in-game outcome resolver SHIPPED -- NEW scripts/platformkit/ingame/soccer_outcome.py (SoccerOutcomeResolver, ESPN-sourced, order-independent ticker->team-pair resolution, never guesses) + NEW domains/soccer_intl/ingest_espn_finals.py (ESPN scoreboard finals ingest, completed-only, mirrors domains.mlb.ingest_espn_box) + wired into ingame_paper_settle.py's score-fn dispatch (routes on KXMLBGAME/KXWCGAME ticker prefix; soccer finals auto-refresh each tick, 3-day UTC window, network-isolated from tests). LIVE RUN: settled all 9 stuck WC bets correctly (1 push/GERPAR draw, 4 losses, 4 wins matching real ESPN final scores incl. the CIV/COD FIFA-code overrides + ESPN's "Congo DR" spelling); idempotent on re-run (0 re-settled, MLB's 13 not-yet-final stayed open). 29 new/updated tests green, all <=300 LOC (soccer_outcome 200, ingame_paper_settle 251, ingest_espn_finals 177), ASCII, no $ field, executed=False, edge_claimed unset (matches existing MLB row convention), no flag flipped.
DONE (2026-07-02): [P1.3] Output-freshness sentinel SHIPPED for the 9 readiness=NONE daemons (m19-m27) -- NEW scripts/platformkit/ops_sentinel/ (output_freshness.py: declarative TABLE daemon->output-artifact->max_age_sec, GREEN/RED check + atomic write/load + a degrade-only merge_freshness_into_services bridge mirroring the existing-but-unwired autonomy.reaper_status_bridge pattern; output_freshness_runner.py: m29 loop wrapper, 300s cadence). Registered ProcSpec m29_output_freshness in supervisor/stack_specs.py (HEARTBEAT readiness, own heartbeat -- it is NOT itself readiness=NONE). DRIFT GUARD test asserts TABLE's keys == the real readiness=NONE ProcSpec name set from supervisor.stack_specs, so a future readiness=NONE daemon added without a sentinel row FAILS CI instead of going silently unmonitored. LIVE-VERIFIED against the real running stack: all 9 daemons GREEN (ages 194s-2399s, all well under threshold); simulated a wedge (future timestamp) -> correctly RED/stale. 49 tests green (13 ops_sentinel + 36 supervisor, incl. the pre-existing test_manifest.py service-set assertion updated for m29), all <=300 LOC (output_freshness 182, runner 114). NOT wired into the m5 autonomy monitor's live compose path yet (both status_composer.py and autonomy_monitor_runner.py are already AT the 300-LOC cap) -- flagged as a follow-up, not blocking; the sentinel's own output_freshness.json is independently useful today. Both committed 2026-07-02 (07a3f4c4/e9f84e6c).


## P1->P7 LEDGER -- in-play edge vertical (in-game super-engine, proven vs REAL prices)
Frontier: the decisive combinable edge is IN-GAME conditioning. Build it end-to-end and prove it vs REAL captured in-play prices. Paper-only; CLV/calibration is the yardstick; no $-claims.
- [x] P1 HISTORICAL IN-PLAY ODDS -> CLV REPLAY HARNESS. DONE 2026-06-18: connectors got fetch_price_history (Kalshi candlesticks via api.elections.kalshi.com /series/{S}/markets/{T}/candlesticks; Polymarket clob /prices-history) -> scripts/platformkit/odds_provider/inplay_history.py (+test 5 green). Offline harness scripts/platformkit/forward_capture/inplay_clv_replay.py (leak-free: model sees series[:i+1] only; CLV sign matches src/betting/clv.py; gate BEAT/MATCH/BEHIND/INSUFFICIENT_DATA; +test 9 green). Ran e2e on 2 REAL series (Polymarket 200-tick + Kalshi 72-tick WC) -> naive + trend models both honestly MATCH/no-beat (mean_clv~0). HONEST LIMIT: fixtures are coarse hourly/daily candlesticks (multi-day span), NOT intra-game ticks -> fine in-play resolution comes from P2 live daemon. Real in-game BEAT attempt deferred to P3 super-engine.
- [~] P2 IN-PLAY CAPTURE. BUILT 2026-06-18: scripts/platformkit/odds_provider/inplay_snapshot_daemon.py (poll_inplay_once/serve_inplay_forever; fast 5s while live / idle 120s; per-sport isolated; atomic tmp+os.replace; freshness sidecar _freshness.json advances only on success) + inplay_feed.py (VENUE-NATIVE liveness: in-play iff open+not-settled+commence_time recently passed; futures/pregame/settled correctly excluded -- dodges the ESPN-id<->venue-id crosswalk landmine). 17 tests green; store=data/cache/inplay_history/<sport>/<date>.jsonl. Smoke: no game live this minute -> 0 captured (honest, not fabricated); injected live tick -> 1 captured (gate not trivially-zero). FOLLOW-UPS: (a) capture a REAL live-game intra-game series when a game is actually live (or via replay feed); (b) wire into supervisor for unattended run.
- [~] P3 IN-GAME SUPER-ENGINE. CLAUSE-1 DONE 2026-06-18 (SHIP): NBA pregame-prior detail layer beats (margin,time) BASE on held-out Brier, leak-free expanding-window WF -> scripts/platformkit/ingame/ingame_layer_gate_nba.py (+io, +test 4 green). Pooled OOS Brier 0.1676->0.1584; DM clustered p=4e-05; 3/3 folds; per-quarter pattern = helps most end-Q1 (+0.0187) least end-Q3 (+0.0012) = REAL early-game team-strength signal not shrink-artifact; noise-p0 control REJECTS (guards the added-flexibility artifact). CALIBRATION only, no $. CLAUSE-2 (graded vs REAL in-play prices): BRIDGE BUILT 2026-06-18 -> scripts/platformkit/ingame/live_grade.py (capture_pair_once pairs predict_live model_prob w/ venue in-play market_prob, HOME-side aligned, skips misaligned/None rather than fake; grade_game feeds pairs to inplay_clv_replay; single partial game = INSUFFICIENT_DATA by design; +test 10 green). predict_live is NON-gated in domains/<sport>/predictor.py. LIVE SMOKE honest result: model side WORKS (real NYY 0.5688, CAN 1.000) but MARKET side BLOCKED -- keyless venues exposed NO tradeable in-play moneyline for tonight's live MLB games via the live fetch path, and available soccer markets are stale futures -> 0 real pairs, correctly skipped. ==> THE binding constraint on proving an in-game beat is VENUE IN-PLAY COVERAGE, not the model. PROBED + CONFIRMED 2026-06-18: Kalshi KXMLBGAME markets are LISTED but UNTRADED/ILLIQUID (live CWS@NYY: yes_bid/ask/last/vol all None; 360 1-min candles all price=None; all 20 open KXMLBGAME same) -> NO real tradeable in-play price exists to grade against on our keyless venues for the live slate. External liquidity reality, not a wiring gap. NEXT to close clause-2: (a) NBA in-season live capture (Oct+), OR (b) monitor any venue for a LIQUID in-play market + capture+grade when one appears, OR (c) add a liquid in-play exchange source (e.g. Betfair historical/live -- NOT keyless). Then aggregate MANY games (one game = variance not signal). Detail-layer ladder (pace/rest/quarter-shape) can also keep growing, each gated.
- [~] P4 SELF-IMPROVEMENT ALWAYS-ON. SUBSTANTIALLY DONE 2026-06-18: reused improve/ 5-gate ratchet + registry; added continuous glue scripts/platformkit/improve/{selfimprove_daemon,artifact_store,checkpoint}.py -> run_cycle/run_forever, versioned artifacts data/cache/improve/artifacts/<name>/v%04d.json + atomic current pointer (keep-prev-10), auto-rollback on regression, checkpoint.json resume (lossless), replication-gated (>=2 corpora else REPLICATION_PENDING), proposals.jsonl emission (never MEMORY.md/data/registry/, never flips flags). 7 tests green; smoke consumed real in-game verdict -> 3 versioned artifacts + proposals + clean restart. FOLLOW-UP: run unattended under supervisor (P7) + widen enumerator.
- [x] P5 PREDICTION + EXECUTION API DONE 2026-06-18: completed existing Auto-API :8099 (predict_service/app.py reads ONE store data/frontend/predict_service/<sport>/latest.json). Added frontend/exec_decision.py (Shin EV via odds_shop, tier floors A>=.08/B>=.04/C>=.02 +.01 proxy, below-floor=no_bet, flat-unit + capped quarter-Kelly UNITS only) + frontend/bestbets_routes.py (GET /api/v1/bestbets/{sport}[/{game_id}] = line-shop+devig + decision + in-game number via report._live + CLV scoreboard). Pregame GET /api/predict/{sport}; in-game GET /api/report/{sport}/{game_id}. CONFIRMED no $/roi/pnl field anywhere, below-floor=no_bet, CLV present, edge_claimed=False. Contract test 7/7 + existing 7/7 green (non-breaking).
- [~] P6 FRONT END (CourtVision) DONE 2026-06-18 (build+served-markup verified; no pixel render in-env): webapp/ (Next.js 14.2 courtvision-live) gained /p6 dashboard + /p6/<sport>/<game_id> reading P5 APIs (never recomputes); panels Slate/GameReport/BestBets(units,tier,decision)/ClvScoreboard/ParityGrid/RatchetPanel/PaperTrail; SSE (game report + paper) w/ poll fallback; NO $ column (stakes in units); degrades to "Unavailable" w/ honest reason. Added frontend/status_routes.py -> /api/improve/status + /api/parity. npm build PASS, tsc clean, served HTML on /p6 + game page HTTP 200 w/ real panels; +3 backend tests. Files in webapp/ (lib/p5api.ts,useStream.ts; app/p6/*; components/p6/*). FOLLOW-UP: headless browser screenshot when a driver is available.
- [~] P7 AUTONOMY DONE 2026-06-18 (in-env proven; real reboot pending): supervisor/ already mature (manifest->boot->supervise->drain, readiness, capped-backoff, isolation, atomic status.json) -> added P2 daemon (inplay_runner.py) + P4 daemon (selfimprove_runner.py, MEASUREMENT-ONLY defaults so nothing ships/no flag flip) w/ heartbeat probes, wired into manifest/ops/status.json (9 services). Governance preflight exits 0, real-money default-DENY. VERIFIED offline: kill one service -> auto-restart + others stay up (isolation); P4 resumes from checkpoint (no reprocess); P2 capture resumes; ops doctor PASS; 47 tests green. Autostart register_autostart.ps1 + watchdog_autostart.ps1 BUILT + -DryRun tested, NOT registered (human go-live = `.\register_autostart.ps1 -Register`). Needs real reboot to confirm OS AtLogOn trigger.

## RECENT DONE (max ~7; older -> DONE.md)
- FRONT-END BEST-BETS ROUTE UN-HUNG -- MLB paper trail live (2026-06-27): `GET /api/v1/bestbets/{sport}` (:8099, the UI's best-bets+execution panel) hung >30s for MLB (16 games) and timed out the dashboard, though /api/predict/mlb was fast. ROOT = TWO O(games) costs in the cold path: (1) `_collect_markets` called `line_store.get_latest(game_id)` with a BARE id (no sport hint) -> globbed EVERY sport's line_history (222M) + re-parsed per game (~4s x16 = ~64s); (2) per-game live ESPN read `_live_for` ran SEQUENTIALLY (~1.3s x16 = ~22s). FIX: added `line_store.get_latest_batch(sport, game_ids)` (one pass over just that sport's files, indexed by game_id; edge_api threads per-game quotes through, `{}` on no-history so it never re-scans) = 64s->1.8s; and `_decide_and_decorate` runs live reads CONCURRENTLY (ThreadPoolExecutor 12w + 8s deadline; slow games -> clean `unavailable` sentinel) = ~22s->capped. CRITICAL 3rd fix: the `with ThreadPoolExecutor()` __exit__ does shutdown(wait=True) which BLOCKED until every live read finished even after the deadline fired (a LIVE box-score read takes 20s+ -> cold MLB still 30s once games went live); switched to explicit pool + `shutdown(wait=False, cancel_futures=True)` so the response returns AT the deadline -- this made the deadline REAL and also fixed soccer_intl (32s->10.6s). All sports now ~10s cold / 0.05s cached. (Tried a startup warm = DROPPED: thundering-herds ESPN, and the m10 daemon board /api/bestbets/board already serves an always-warm best-bets view.) VERIFIED LIVE: bestbets/mlb 16 games / 11 best_bets (units only -- flat_unit+kelly_units+stake_units, edge+EV+tier, edge_claimed=False, NO $); /api/paper/trail 200 settled MLB rows + CLV scoreboard; front-end :3000 /p6 200; flywheel running (selfimprove_runner+inplay_runner+auto_loop+scheduler). Files frontend/{edge_api,bestbets_routes}.py + scripts/platformkit/odds_provider/line_store.py + test_line_store.py (+2 tests, 11 green); all <=300 LOC, ASCII, local-only, no push. NOTE: soccer_intl still ~32s cold (latent, secondary to MLB). Py3.10 gotcha: concurrent.futures.TimeoutError != builtin. Memory: gotcha-bestbets-route-hang-linehistory-livereads.
- ODDS-API HISTORICAL = ONE-SESSION ACQUISITION, REFOCUSED TO MLB+WC, WIRED INTO AI (2026-06-26): strategy = use the PAID odds API for ONE session to grab historical, then run INDEPENDENTLY on our own keyless live scrapers + this corpus. Made scripts/platformkit/odds_provider/oddsapi_team_backfill.py MULTI-SPORT (SPORT_KEYS nba/mlb/soccer_intl; the gated client is NBA-locked so I fetch via its sport-agnostic _gate_or_fetch internal) with a PREGAME GUARD (keep event iff commence_time>snapshot_ts -> in-play MLB lines, still 2-way, no longer masquerade as closes) and n-way Shin devig (soccer 3-way 1X2 -> probs sum to 1). Active sports first: KILLED the mis-prioritized NBA full-run (offseason; ~80 units lost), ran WC (complete: 16 dates, 2107 rows, 920u) + MLB (recency-first 2026->2025, cap 17.6k, running in bg). us,eu=Pinnacle anchor; holds ~2-3%, 17-30 books; 0 in-play rows kept. THEN built the AI BRIDGE scripts/platformkit/odds_provider/oddsapi_close_corpus.py (+6 tests): select_closes picks THE CLOSE per (event,market)=latest pregame snapshot w/ anchor devig; joins realized outcomes (mlb espn_boxscores via team_resolver.canonical abbr<->name; soccer_intl results.parquet full-name) -> corpora.py-compatible states (game_id,home,away,state_ts,outcome,devig_close_prob). THIS FILLS THE MLB SEAM that was DATA_LIMITED (market_coverage/corpora.mlb_ml_states returned [] -- no joinable local close). JOIN BUG fixed: key outcomes on commence date + ET-prior-day (late UTC games are prior ET day) -> MLB labeled 35->211 states, close Brier 0.250 @ 50.7% home base = the market benchmark the AI must beat OOS; WC 11 decisive (76 h2h closes, 19 played, ~8 draws excluded from 2-way frame -- honest). 17 new tests. CALIBRATION only, NO $/ROI. NEXT: (a) let bg MLB run finish -> rebuild corpus; (b) one-line wire build_states('mlb') into edge_finder.py:129 (replaces the [] DATA_LIMITED mlb path) so recalibrator/eval-gate score vs the close; (c) point select_closes at live-capture JSONL too = old+live blend for continuous self-improve; (d) NBA/MLB spreads+totals already captured for later. The 5 NBA seed dates from the prior turn remain valid in nba_team_strength.jsonl.
- 4-SPORT IN-GAME CALIBRATION = NBA-LEVEL + LIVE-SERVED (2026-06-18): 3/4 sports REPLICATED in-game prior-conditioning calibration beat (NBA fine-res DM p=1.2e-12; TENNIS after p1/winner sign-bug fix, corr 0.01->0.72; SOCCER after team-name->Elo fix, fallback 42.9%->0%, both dirs p<0.002); MLB honest characterized NULL (prior+late-inning+leverage+half+base-out[100% cov] all reject; run_diff+innings near-sufficient). Generic sport-blind gate w/ degenerate-base honesty guard (caught + killed a FALSE tennis 'replicated'). LIVE-SERVED for in-season sports: ingame_serve.py persists per-sport models (data/cache/ingame/models/<sport>_ingame.json, proven/base provenance) + ingame_live_state.py keyless ESPN extraction + GET /api/ingame/{sport}/{game_id}; vs_close UNPROVEN, no $. ~150 new tests across ingest+gate+serve. CALIBRATION not market. (2026-06-18)
- 4-SPORT IN-GAME GATE built + honestly graded (2026-06-18): generalized the proven NBA in-game gate into a sport-blind module (scripts/platformkit/ingame/ingame_gate_generic.py+_models, DEGENERATE-BASE honesty guard) + ingested in-game state trajectories for MLB/soccer/tennis (domains/<sport>/ingest_*states*; data/cache/ingame/<sport>_states__*.parquet). VERDICTS: NBA REPLICATED (real); MLB REJECT (strong base, prior adds nothing); SOCCER PARTIAL (real beat 1 dir p=0.045, underpowered 180g/corpus); TENNIS INVALID_BASE (set-level only, corr 0.009 -- suspected reconstruction bug, killed a FALSE 'replicated'). ~90 new tests across 4 ingest+gate modules. Follow-ups in flight: soccer power-up, tennis bug hunt, MLB detail ladder. CALIBRATION not market. (2026-06-18)
- P3 c1 CALIBRATION BEAT REPLICATED CROSS-CORPUS + CONFIRMED AT FINE RESOLUTION (2026-06-18): ingested NBA 2024-25 linescores (1321 games) + FULL 2-season PBP scoring trajectories (23 as-of states/game, zero drops) -> ingame_crossval_nba.py (Q-boundary) + ingame_finegrain_nba.py (~2-min). BOTH gates, BOTH directions: +PRIOR beats BASE on held-out Brier (Q-bnd A->B 0.1706->0.1613; fine A->B 0.1684->0.1583 clustered DM p=1.2e-12, B->A 0.1716->0.1647 p=1.2e-4), early-helps-most pattern holds, per-GAME clustering applied (shrinks DM 3.3x vs iid, still significant). VERDICT=REPLICATED at serving resolution. Now a CONFIDENT, proof-rail-complete in-game CALIBRATION beat over a margin/time base (leak-free+WF+OOS+2 seasons+DM+mechanism) -- NOT a market beat (that's liquidity-blocked clause-2). Also: P5 execution math independently reviewed CLEAN (Shin-devig edge, tier floors, capped quarter-Kelly, units-only no-$, edge_claimed=False). 4-sport parity GREEN. (2026-06-18)
- P3 LADDER EXHAUSTED + P4 DAEMON BUILT (2026-06-18): 3 new in-game detail layers (pace/total-variance, momentum/run, home-bias) all HONEST REJECT vs BASE+PRIOR (no DM-significant OOS Brier gain) -> ingame_ladder_nba.py(+layers,+7 tests); linescore-derived in-game signal is exhausted, more lift needs PBP-rich state not Q-snapshots. P4 self-improve daemon built on existing improve/ ratchet (selfimprove_daemon+artifact_store+checkpoint, 7 tests, real smoke staged 3 artifacts+proposals+resumed). Honest, no $. (2026-06-18)
- IN-GAME SUPER-ENGINE P3 (2026-06-18): CLAUSE-1 SHIP -- NBA pregame-prior detail layer beats (margin,time) base on held-out Brier (0.1676->0.1584, DM p=4e-05, 3/3 folds, per-quarter pattern = real early-game team-strength signal, noise-p0 control rejects) -> ingame_layer_gate_nba.py. CLAUSE-2 bridge built (live_grade.py, 10 tests): model side works live, but proving an in-game BEAT is blocked by VENUE in-play coverage (no tradeable in-play moneyline exposed for tonight's MLB; NBA offseason; soccer markets are futures). Honest: stack fully wired+ready, awaiting a live in-play price to grade against. CALIBRATION only, no $. (2026-06-18)
- IN-PLAY EDGE VERTICAL P1 done + P2 substantially done (2026-06-18): own connectors now fetch real in-play price history (Kalshi candlesticks + Polymarket prices-history -> inplay_history.py); offline leak-free in-play CLV replay harness (inplay_clv_replay.py) gives honest BEAT/MATCH/BEHIND/INSUFFICIENT_DATA -- ran e2e on 2 REAL series, baseline correctly MATCH/no-beat; venue-native in-play capture daemon (inplay_snapshot_daemon.py + inplay_feed.py). Adversarial review CLEAN (leak-free, CLV sign correct). ~5 new modules under scripts/platformkit, 31 new tests green. Paper-only, no $-claims. Parity GREEN (4/4). REAL in-game BEAT attempt deferred to P3 super-engine. (2026-06-18)
- OVERNIGHT IMPROVEMENT CYCLE (autonomous, 2026-06-17->18): added TRUE-CLV capture (prop_line_history.py logs lines each tick -> CLV-vs-close in prop_summary; loop restarted w/ it). Built + HONESTLY MEASURED 2 model levers, both correctly held back: opponent-adjustment (team_defense.py, leak-free, wired live) = measured NULL on the thin 1-round WC slice (opp has no strictly-earlier history yet; activates as rounds accrue); isotonic P(over) recal (prop_recal.py) = DEFER, proper temporal train/test shows it OVERFITS 24 matches (OOS Brier slightly worse) -- module ready, NOT applied live. Meta: WC is data-limited (24 matches); MLB (full season) is the higher-value next vertical. All per-file tests green; paper-only; no $-claims (2026-06-18)
- WORLD CUP PLAYER-PROP VERTICAL built end-to-end (Milestone 1, plan REVAMP_DECISIONS_AND_PHASES.md): snapshot backbone (compute-once -> snapshots/<sport>.json, serve reads it, refresh_daemon); deep prop scrapers (Underdog two-way priced + PrizePicks pick'em live; FanDuel parser ready/props-not-posted; DK=Playwright-deferred); ESPN per-player WC ingest (1241 rows/24 matches); Poisson/NB prop engine w/ dispersion calibration + EV honesty guard; resolver (98% name hit) + prop_edge board (/api/props, in snapshot); prop settlement + paper-CLV loop (records ONLY reliable+ok edges -> 0 today, honest); CLUB-SEASON PRIORS via ESPN athlete overview = the unlock (0 -> 321 reliable edges on a 36-player sample). ~15 new modules, all per-file tests green, all in scripts/platformkit + domains/soccer. PAPER ONLY, tier-labeled, no $-edge claims (2026-06-17)
- Clickable per-game BET BOARD: GET /api/game returns every market ranked (best_bets + groups) across all sports; React detail Dialog built (builds clean). Honest: EV only where priced, else MODEL_VIEW (2026-06-17)
- LIVE in-game tracking working end-to-end: ESPN keyless feed -> predict_live -> /api/live; verified on live MLB (4 games) + World Cup (England 1-1 Croatia 40' -> 45.1% as Croatia equalized) (2026-06-17)
- In-game bugs fixed: soccer_intl gained a predict_live (was pregame-only); MLB live anchored to Elo; NBA buzzer = exact 1.0 (2026-06-17)
- Paper/auto-bet loop verified SAFE: no real-money path (place_order stubs raise, ENABLED=False, gate needs BEATS_CLOSE); paper_autobet.py built; CLV loop end-to-end (2026-06-17)
- Claude-org reorg: memory 33.5KB->20.4KB; .planning/NOW.md SSOT; rules now load (@-imports); guard hooks wired+verified; skills consolidated (2026-06-17)
- Full per-sport market coverage built (NBA/MLB/soccer/tennis), 45 tests; soccer gained a real 1X2 moneyline (2026-06-17)
- Own keyless odds API (odds_provider/) + line-shop/arb/EV + CLV ledger; MLB odds attach via team_resolver (2026-06-17)
- Adversarial-review loop fixed 2 confirmed bugs (wrong-game odds match; MLB integer-line push) (2026-06-17)
- React+shadcn UI scaffolded + builds; World Cup wired into the board (2026-06-17)
- CRPS+pinball distributional metrics shipped to eval_gate/scoring.py (C7) (2026-06-17)


## Archived history
FRONT-END FILL directive (2026-06-22, delivered) + SESSION logs 2026-06-21..25 +
stale Active-blockers list -> .planning/archive/NOW_ARCHIVE_2026-06.md

## Pointers (links, never inline)
- Betting product research: docs/research/betting-product/
- Claude-org reorg research: docs/research/claude-org/
- Memory frontier entries: memory `project-betting-product-research-2026-06-17`, `project-betting-frontend-intl-mlb-2026-06-17`
