# S396 build memo -- signal audit runner: one sealed family, one ledger charge
PREPARE only. Four new modules plus three per-file test files that push a SEALED signal family through the landed leak-free gate on exactly ONE ledger charge. No real corpus, no real ledger, no network; the first family manifest is sealed, committed and run by the orchestrator, not by this row. No landed module was edited and nothing under `src/`, `kernel/`, `api/`, `scripts/team_system/`, `intel/`, `data/` or `vault/` was written. Worktree: C:/Users/neelj/nba-harness-h57 only (branch harness-h57, master-based, master 009880081). Calibration language only: an honest NOT_EVALUABLE or UNDERPOWERED per signal is the expected result and this row's fixture produces exactly that, beside one planted arm.
## Files (lengths by `len(text.splitlines())`, all ASCII, LF-only)
- `scripts/platformkit/eval_gate/signal_audit_catalog.py` (NEW in FIX 1b, <=300)
- `scripts/platformkit/eval_gate/signal_audit_family.py` (NEW, <=300)
- `scripts/platformkit/eval_gate/signal_audit_runner.py` (NEW, <=300)
- `scripts/platformkit/eval_gate/signal_audit_verdicts.py` (NEW, <=300)
- `tests/platformkit/eval_gate/test_signal_audit_family.py` (NEW, <=300)
- `tests/platformkit/eval_gate/test_signal_audit_runner.py` (NEW, <=300)
- `tests/platformkit/eval_gate/test_signal_audit_report.py` (NEW in FIX 1c, <=300)
- `docs/evidence/harness/S396_signal_audit_2026-09-22.md` (this memo)
`signal_audit_catalog.py` is the seventh file (FIX 1b, the spec-writer's allowance for a NEW helper module carrying the AsOfContext adapter) and `test_signal_audit_report.py` the eighth (FIX 1c, the fix rail's ONE new companion test file); all four modules and all three test files remain at or below 300 lines.
## Binding before-condition
Quoted from `master` with `git show master:<path>` / `git grep ... master` before any code was written. (a) `scripts/platformkit/eval_gate/backtest_runner.py`:
```text
176:def _charge_ledger(path, spec, sport, start, end, *, family=None, hypothesis_hash=None,
                   tier=None, prereg_sha256=None, trial_prereg_sha256=None) -> dict
    with ledger_lock(path): rows = load_fwer(path)
        prior = max((int(r.get("k_cumulative", 0)) for r in rows), default=0)
        ... "k_cumulative": cumulative_k(prior, 1) ... "k_family": next_k_family(rows, family)
 94:def load_states(sport, start, end, repo=None, counts=None) -> list[dict]
243:    threshold = eps_eff(0.05, charge["k_cumulative"])   # eps_eff: combo/fwer_budget.py:64
 57:def assert_canonical_ledger(ledger_path, allow_noncanonical) -> bool
```
The canonical call, `s58_nba_halftime_asof_trial.py:125-133` (SEAL -> CHARGE -> score): `seal = sha256(<prereg bytes>)`, then `row = _charge_ledger(..., family=FAMILY, tier=TIER, hypothesis_hash=..., prereg_sha256=seal)`, then `k = int(row["k_cumulative"])` -- the ONLY K used. (b) `walkforward.py`: `PURGE_HOURS = 48` (31), `EMBARGO_DAYS = 3` (32), `TEST_VIEW_KEYS` (41), `class LeakError(AssertionError)`; (c) `ingame/gate_a0_ingame_vs_market.py`: `N_BOOT = 2000` (22), `SEED = 13` (23), `N_MIN_GAMES = 30` (24); (d) `romano_wolf.py`:
```text
124:def walk_forward(states, predict_fn, select_inside=True, *, strict_redaction=False,
                  allow_keys=(), guard_state_keys=False) -> WalkForwardResult
    records: List[dict]  # {game_id, ts, p_model, p_close, y}   n_train_sizes: List[int]
 70:def cluster_bootstrap(df, col_a, col_b, n_boot=N_BOOT, seed=SEED):
        rng = np.random.default_rng(seed); ng = len(g)
        g = df.groupby('game_id').agg(sa=(col_a,'sum'), sb=(col_b,'sum'), n=(col_a,'size'))
        for i in range(n_boot): pick = rng.integers(0, ng, ng)
        lo, hi = np.percentile(diffs, [2.5, 97.5])
 84:def verdict(lo, hi, n_games, n_min=N_MIN_GAMES):
        if n_games < n_min or (lo <= 0 <= hi): return 'UNDERPOWERED'
        return 'BEHIND' if lo > 0 else 'AHEAD'
 27:def romano_wolf_stepdown(loss_diffs, game_ids, *, alpha=0.05, n_bootstrap=2000,
                         seed=2718, mean_block_length=5.0) -> RomanoWolfResult
```
(e) `retro_correction.catalog_signals()` returns `(domain, class)` pairs by AST, never importing human-gated signal code; `domain` is the parent DIRECTORY name. One catalog class, `domains/basketball_nba/signal_catalog.py` (EloIdentitySignal): `name: str = "nba_elo_diff_hfa_identity"`, `target: str = "winprob"`, `scope: str = "pregame"`, `reads_atlas = []`, `emits = []`, `def build(self, ctx: AsOfContext) -> SignalValue`, `def hypothesis(self) -> Hypothesis`. (f) `catalog_common.py` carries the three verdict words at lines 177-178 (`... in {"REJECT", "DEFER"}` / `if actual == "<the third word>"`); this row uses NONE of them -- its vocabulary is AHEAD(SINGLE-WINDOW) / BEHIND / UNDERPOWERED / NOT_EVALUABLE / REFUSED. Measured here, 2026-09-22: `len(catalog_signals()) == 60`, first pair `('basketball_nba', 'EloIdentitySignal')`; the registry parquet is gitignored and absent from this worktree, its schema read READ-ONLY from the main tree with pyarrow metadata -- the 11 declared columns over 86 rows.
## Spec findings the orchestrator should see
1. **No catalog class has a `compute` method.** SUPERSEDED in its CONCLUSION by AMENDMENT 1(b) and FIX 1b:    the census still reproduces (`git grep -c "def compute" master -- "domains/*/signal_catalog*.py"` has no    hits over all 8 catalog files), but the interface is `build(ctx: AsOfContext)`, so it decides nothing.
2. **`eps_eff` is not in `eval_gate`.** It lives at `combo/fwer_budget.py:64`, imported by `backtest_runner.py`;    line 243 there is the usage the spec names.
3. **Column math lives in `signal_audit_verdicts.py`, not the runner** (AMENDMENT 1(c)): keeping the draws,    the intervals and the paired series in the runner put it at 324 lines, over the rail, so only the file    boundary moved.
   would read and never calls `load_states`, so a charge-free census cannot fail on a missing frozen corpus.
## What was built (CHANGE items 1-5)
1. `signal_audit_family.py`. The family is fixed BEFORE scoring by (sport, target = settled home-win outcome,    horizon = pregame close, reference = devigged close p_close, window start..end), echoed into the manifest and
   re-checked by `validate_manifest`. Members carry `member_key` = `source:signal_id`, the one-line hypothesis,    the builder name, evaluability and what the source DECLARES; counts are strict ints re-derived from the    members. `seal()` writes the canonical JSON once plus a `.sha256` and refuses a second seal.
2. `signal_audit_runner.py`. Order: `check_seal` -> `assert_committed` (tracked, clean; it returns the commit    SHA) -> `assert_canonical_ledger` -> prior max K from `load_fwer` -> exactly ONE `_charge_ledger(..., family,
   hypothesis_hash=<manifest digest>, tier)` -> `charge.json` -> `load_states` -> reference arm -> per member. K    is the charged row's own `k_cumulative`; `family_allowance = Decimal(repr(eps_eff(0.05, K)))`, asserted to
   equal the landed bar as a float, and `member_allowance = family_allowance / Decimal(n_declared_evaluable)`.    Both arms run through `walk_forward(..., strict_redaction=True, guard_state_keys=True)`; the reference arm
   returns the declared close from the runner side table (REFERENCE_CHANNEL) and the candidate arm the same    states through `logit(p_close) + beta * z(signal)`, mu / sd / beta from the training slice ONLY (below
   `MIN_TRAIN` it returns the close and builds nothing). Per member the paired Brier and log-loss series are    archived (Q9) and both intervals come from ONE set of game-clustered draws, the 0.05 pair asserted equal to
   `cluster_bootstrap` before any verdict forms: the landed `gate_a0.verdict` at the MEMBER allowance, AHEAD    relabelled AHEAD(SINGLE-WINDOW). A failure after the charge writes `failure.json` beside `charge.json`.
3. `signal_audit_verdicts.py`. The full-matrix row schema (the FIX 1c columns plus hypothesis, evaluability,    n_games, n_states, point, ci95, ci_member_allowance, verdict, the Romano-Wolf pair, the log-loss pair,
   coverage and the series paths), `validate_member`, the census, the draws / interval / series helpers, and    `survivors()`, which NEVER promotes: an AHEAD(SINGLE-WINDOW) row gets the Q5 sentence and nothing else.
4. Tests (see Validation). 5. This memo.
## Historical validation before Round 4
Per-file only, one file at a time, with bytecode writes disabled.
```text
python -B -m pytest tests/platformkit/eval_gate/test_signal_audit_family.py -q -p no:cacheprovider
22 passed, 1 skipped in 0.74s
python -B -m pytest tests/platformkit/eval_gate/test_signal_audit_runner.py -q -p no:cacheprovider
21 passed in 2.70s
python -B -m pytest tests/platformkit/eval_gate/test_signal_audit_report.py -q -p no:cacheprovider
20 passed in 3.75s
```
The A12 shared rail `tests/platformkit/test_loc_rail_scope.py` was run per-file as well: 1 passed, no allowlist entry needed. The one SKIP is the registry-parquet schema test: `data/registry/signal_registry.parquet` is gitignored and absent here, so the test is marked skipif and the tracked suite never depends on a gitignored file; its fixture columns came from a READ-ONLY pyarrow schema read of the real file in the main tree. What the runner tests cover: the full matrix publishes all five members; the planted signal's member-allowance
interval lies wholly below zero at n_games 80 >= the landed n_min while the noise signal is UNDERPOWERED; the ledger grows by exactly ONE row; K is read at launch (prior max 3 charges 4, the bar tightens); the interval is
draw-for-draw equal to `cluster_bootstrap` and both archived series rebuild their point to 1e-9; a leak, a dead corpus, an unsealed manifest, a duplicate game_id, an unusable close and a missing feature are refused or
counted; and a catalog stub that never yields is UNDERPOWERED:feature_coverage. CLI: `--help` exit 0 for both.
## FIX 1b -- AMENDMENT 1(b): the catalog interface is build(ctx: AsOfContext)
The build treated all 60 catalog classes as NOT_EVALUABLE because none exposes `compute`. AMENDMENT 1(b) binds the real interface. A NEW module `signal_audit_catalog.py` carries the whole catalog arm: the declaration
reader, the evaluability rule, the AsOfContext adapter and the coverage census. `signal_audit_family.py` no longer decides anything about the catalog; the runner scores a catalog member only if its feature covers at least the landed `n_min` games.
**Evaluability.** EVALUABLE when the DECLARED `target` is the home-win outcome (`winprob`) and the DECLARED `scope` includes pregame, read by AST so the census never imports the human-gated catalog code. Reasons that
fail closed, each naming itself: no `build` method; a foreign domain; a declared `reads_atlas` section or (see Round 3) a `build` body naming a point-in-time read; and, per state, `NOT_EVALUABLE:build_failed`. **The context.** One `AsOfContext` per state, from the strict test view and nothing else; the field map the
amendment enumerates is echoed into the artifact as `catalog_context.fields`. `AsOfContext` is imported
READ-ONLY from `src/loop/signal.py`; `src/` was not touched. The leak assertion is structural:
`context_from_state` re-runs `redact_test_view(..., strict=True)` on every row it is given -- training rows
included -- so the settled keys are dropped before the context exists and a stray key raises.
**Measured, 2026-09-22, this worktree.** `parse_venue_time` REFUSES the gate corpus's own timestamps:
`load_states` emits `state_ts` as `"<date>T12:00:00"` (unzoned) and the parser returns None with reason
`timezone_missing`. The adapter applies ONE declared normalization -- an unzoned stamp re-parsed as `+00:00`
through the same function, recorded under `catalog_context.unzoned_state_ts`; any other refusal is a counted
`build_failed:decision_time_refused`. The context carries NO `extra`, and 27 of the 60 classes read it.
```text
catalog classes on disk: 60
A. declared target + scope only (SUPERSEDED by Round 3's body scan): EVALUABLE 60
B. per family sport (what one family actually counts as hypotheses)
   sport=nba     EVALUABLE 16  NOT_EVALUABLE 44  (mlb 14, soccer 15, tennis 15)
   sport=mlb     EVALUABLE 14  NOT_EVALUABLE 46  (basketball_nba 16, soccer 15, tennis 15)
   sport=soccer  EVALUABLE 15  NOT_EVALUABLE 45  (basketball_nba 16, mlb 14, tennis 15)
   sport=tennis  EVALUABLE 15  NOT_EVALUABLE 45  (basketball_nba 16, mlb 14, soccer 15)
   (the sole NOT_EVALUABLE reason at B is "catalog domain <d> is not the family sport <s>";
    none is refused on target, scope, a missing build method or a missing atlas input)
C. measured per-state build over a 40-state corpus-shaped fixture (no store, no real corpus)
   n_games_finite=0 for 60 of 60 classes; every state counted as
   NOT_EVALUABLE:build_failed:no_value_for_declared_key
   -> every catalog member lands UNDERPOWERED:feature_coverage (0 < landed n_min 30)
```
The honest verdict moved from "NOT_EVALUABLE, wrong interface" to "EVALUABLE by declaration, UNDERPOWERED by
coverage" -- still zero scored catalog signals, but for a measured reason instead of a mistaken one, counted per
state.
**Registry rows, READ-ONLY.** The parquet is absent here; the main tree's copy was opened READ-ONLY (never
written, never copied): 86 rows, the 11 declared columns present. Census with the only per-state feature key
this machine's gate corpus carries (`schedule`, from `load_states`): entity is player 59, consumer is scouting
23, formula not computable from the state allowed keys 4, EVALUABLE 0. (`entity` player 59 / team 19 / lineup 8;
`consumer` scouting 55 / ingame 12 / corr-model 10 / point-model-candidate 9; `status` folded 72 / deferred 14.)
## FIX 1c -- the two round-1 verdicts applied
Opus r1 (ACCEPT WITH CORRECTIONS) and codex sol r1 (REJECT), both in this round; nothing else was touched.
1. **The committed bypass leaves a trace.** `assert_committed` returns the manifest's commit SHA, and
   `charge.json` AND `family_audit.json` carry `manifest_committed` (bool) plus `manifest_commit` (the SHA, or
   null when the test seam was used).
2. **`n_hypotheses_counted` counts every member, contrast and window** (= n_members + n_contrasts +
   n_windows; five members gives 7, not 2). The Bonferroni DIVISOR stays separate as `n_allowance_divisor`.
3. **The member tail is declared when the bootstrap cannot resolve it.** Each scored row carries `tail_rank` =
   floor(Decimal allowance * n_boot / 2), complete draws per tail, and `tail_unresolved` = tail_rank < 1. At the family's numbers then (K 20, 16 evaluable
   members, 2000 draws) the member allowance is 1.5625e-04 and the tail is 0.15625 of ONE draw: the percentile
   interpolates between draws; the earlier extrema/conservative-coverage claim is withdrawn (Round 4).
4. **No build runs on a head state.** The candidate arm returns the close before building anything when the
   training slice is under `MIN_TRAIN`, so a head-state build failure can no longer refuse a whole member; the
   test row is now built LAST, after beta.
5. **The reference channel is declared** in the report (`reference_channel`): p_close is served from a runner
   side table keyed by game_id, NOT through `redact_test_view`, which drops `devig_close_prob`. Each member also
   reports `n_states_at_min_train`.
6. **An occupied `--out` is refused** -- Round 4 requires explicit failure resume for the same digest; it cannot
   overwrite the first `charge.json`.
7. **Stale memo sentences corrected**: superseded finding 1 no longer names a test that no longer exists, and
   the "all NOT_EVALUABLE" scale sentence is replaced by the FIX 1b census.
8. **A stateful builder cannot carry a later state backward** (sol 1). `catalog.arm` returns a FACTORY: the
   coverage census gets its own builder instance and the scored arm takes a FRESH one per fold. Regression: a
   stub that remembers every state it is shown scores column-for-column identically to the stateless clock stub.
9. **`validate_manifest` is complete** (sol 2). Every fixed family field (target, horizon, reference, link,
   state_allowed_keys) is REQUIRED and equality-checked, and each member's sealed identity (member_key, the
   hypothesis for THIS window, a known source, a non-empty builder) is re-derived before the seal AND again
   before the charge.
10. **The CLI exposes no bypass** (sol 3). `--allow-noncanonical-ledger` and `--allow-uncommitted-manifest` are
    gone from argparse and survive only as keyword arguments of `run_family_audit`, which is what the tests use:
    Q1 and Q2 hold for every CLI run.
11. **The Q9 archive carries the model side** (sol 4). Each per-state row now holds p_candidate, p_reference,
    the label, the feature value, the fitted beta, the z-scaling (mu, sd), the training-slice size and a SHA-256
    of that slice's game ids, beside the losses; the report carries the immutable identities (the manifest digest,
    a SHA-256 per code file and per corpus counts). A test rebuilds p_candidate from the archive alone.
12. **This memo is at or under 300 lines** (sol 6), FIX sections before NOT VERIFIED and NOT VERIFIED last,
    with no evidence dropped -- the before-condition quotes, both censuses and every measured number remain.
## Round 2 -- both round-2 verdicts applied (FIX 1d)
Opus r2 ACCEPT WITH CORRECTIONS (one CORRECTION, three NOTEs) and codex sol r2 REJECT (three BLOCKERS; every
other round-1 item reproduced closed). Nothing else was touched.
1. **CORRECTION -- the Q9 CSV header self-identifies.** `render_series` takes an `identity` pair sequence, so a
   header carries manifest_sha256 and corpus_counts_sha256 beside the point; a test reads the header back.
2. **NOTE -- clustering is inert at this grain.** A duplicate `game_id` is refused, so `n_states == n_games` and
   every cluster holds ONE state: measured into the artifact as `clustering_inert_at_grain`.
3. **NOTE -- the point is averaged over the unfitted head.** The `n_states_at_min_train` states carry `d == 0`
   and still enter the bootstrap. REASONED, NOT MEASURED: no sensitivity run dropped the head and compared.
4. **NOTE -- `devig_close_prob` is the MANDATED reference channel, not a leak.** `walkforward._SETTLED_DENY`
   (line 44) classes it settled and `REFERENCE_CHANNEL` declares the side-table route; it is not a leak.
5. **BLOCKER -- a member could contradict its own declarations.** BEFORE: a catalog member declaring `target
   total`, `scope live`, `interface compute(state)` was ACCEPTED as EVALUABLE, as was a registry member marked
   EVALUABLE whose sealed `entity` is `player`. `validate_manifest` now RE-DERIVES each member from its OWN
   sealed declarations (`rederive`; never disk, so Q1 holds) and refuses any inequality. AFTER: both refused.
6. **BLOCKER -- the family CLI wrote before it detected the seal.** BEFORE: a second `--seal` run instrumented
   `events=['write'] then FileExistsError`, the manifest already rewritten under its own seal (and a run without
   `--seal` rewrote it silently). AFTER: `main` refuses BEFORE any write; the regression asserts `events == []`.
7. **BLOCKER -- census eligibility followed arrival order.** BEFORE: `forward [1, 2]: n_states_finite=2
   n_build_failed=0` against `reversed [2, 1]: n_states_finite=1 n_build_failed=1`. `coverage` now walks states
   sorted by parsed decision time then game_id (`_order_key`). AFTER: both orders give n_states_finite=2.
## Round 3 -- Opus round-3 corrections (FIX 1e)
Opus r3 ACCEPT WITH CORRECTIONS: all four round-2 fixes reproduced, ONE charge before any metric, the archive reconstructs to 1e-16. AMENDMENT 2(a) pins the eight-file owned set.
1. **CORRECTION -- NE_INPUT was unreachable (2(b)).** Every on-disk class declares `reads_atlas = []`, so
   gating on it alone never fired and the divisor was inflated. `evaluability` now ALSO returns NE_INPUT when
   the AST `build` body NAMES a point-in-time read (`self.store`, `self.read`, `ctx.extra`; `_body_reads`),
   sealed as `declares.body_reads` so `rederive` re-derives it; ne_input_declared and ne_input_body are
   DISTINCT reasons, counted apart. **Re-measured READ-ONLY on disk, SUPERSEDING the A/B counts above:**
   sport-blind EVALUABLE 60 -> EVALUABLE 33 + ne_input_body 27 (the same 27 classes measured above as reading
   `ctx.extra`); sport=nba EVALUABLE 16 -> EVALUABLE 10 + ne_input_body 6, the 44 foreign-domain rows
   unchanged -- an nba family's allowance divisor is 10, not 16. Pinned by a test parsing a stub catalog FILE.
2. **NOTE -- the guard is symmetric.** `guard_state_keys=True` was on the reference arm only; every
   `walk_forward` call passes it now: no measured reason for the asymmetry, and all three test files pass.
3. **NOTE -- a LeakError ENDS the run (2(c)).** An `AssertionError`, it escapes `except BuildFailed` in
   `coverage` and `except (KeyError, TypeError, ValueError)` in `_score_family`: fail-closed BY DESIGN -- the
   audit stops rather than refusing one member and scoring the rest.
Round 3 codex sol BLOCKING finding applied (FIX 1f): protect immediately after the charge; fsync a minimal
charge.json BEFORE allowances/report construction (the full allowances remain in family_audit.json).
K=7 -> 8, one temporary ledger row: BEFORE ['LEDGER_APPEND']; AFTER ['LEDGER_APPEND', 'WRITE:charge.json', 'WRITE:failure.json']; exception propagated.
Normal BEFORE/AFTER: ['LEDGER_APPEND', 'WRITE:charge.json', 'METRIC', 'WRITE:family_audit.json']. Pinned allowance/report failures: 2 failed before, 3 cases pass after; runner 21 passed, family 22 passed/1 skipped (absent registry), report 20 passed; both help commands exit 0.
## Round 4 -- FIX 1g, AMENDMENT 3(a)-(g)
Binding: docs/evidence/tracking/specs/S396_spec.md AMENDMENT 3 and docs/evidence/harness/S396_astra_r4_critique_2026-09-22.md.
Local PREPARE only, n = 7 timing/accounting/identity cases (CONSTRUCT); no commits or network.
(a,b) catalog.py:277/282 normalizes fixed-width UTC Z, validates reference_available_at <= state_ts, and removes settled_at into a side table. runner.py:86 filters training labels at the decision boundary; landed purge/EMBARGO stays intact. Unknown timing refuses. Instance-local MemoryStub asserts monotonic UTC.
(c) family.py:214 serializes digest accounting, refuses charge_exists, and protects append-then-raise. Row id is k_cumulative. --resume-charge requires matching failure.json plus charge.json and a new --out. --resume-from locates a prior directory outside --out's siblings.
(d,e) runner.py:160 reads the manifest bytes once; check_seal, validation and charge share that snapshot, with a stat-change refusal. family.py:129 re-derives the registry builder binding. The swap fixture raises before any charge.
(f,g) catalog.py:203/211 no longer suppresses sorting failures or LeakError from build. verdicts.py:288 aligns state-key intersections for shared Romano-Wolf resampling; records bootstrap.n_states_common and refuses unequal coverage below the landed game minimum.
Pinned tests: runner.py timing, unsettled-game exclusion, leaked build and event order; family.py builder identity and both crash/resume paths; report.py mixed-offset memory, one-read swap and correlated unequal coverage. Existing assertions remain. Equal-coverage UNDERPOWERED arms remain supported.
Tiny-tail documentation now states interpolation and unproved nominal coverage; pinned arange(2000) output is [0.156171875, 1998.843828125]. Comma-ID CSV round-trip is pinned.
Python one-liner stub reproductions, input/output verbatim (before measured before edits, except a uses the unchanged raw walk_forward route):
```text
a input=20_warmups,10+00,11+02,next_day before=AssertionError after=accepted
b input=20_warmups,unsettled_unrelated,unknown_close_time before=n_train:21,reference:0.5
b input=20_warmups,unsettled_unrelated,unknown_close_time after=n_train:20,reference_availability_unknown
c input=crash,identical_retry,new_out before=rows:2,K:2
c input=crash,identical_retry,new_out,resume:1 after=charge_exists,rows:1,K:1,resume:complete
d input=sealed_divisor:2,swapped_divisor:3 before=charged_divisor:3
d input=sealed_divisor:2,swapped_divisor:3 after=manifest_changed_during_validation,reads:1,rows:0
e input=noise_builder:features:planted before=accepted
e input=noise_builder:features:planted after=registry builder contradicts sealed identity
f input=signal.build_raises_LeakError before=BuildFailed
f input=signal.build_raises_LeakError after=LeakError
g input=correlated_arms:40,39 before=independent_coverage:40,39 after=n_states_common:39,below30:unequal_coverage: common games below minimum
normal input=stub_family rows=1 output=['LEDGER_APPEND', 'WRITE:charge.json', 'METRIC', 'WRITE:family_audit.json']
append_then_raise input=stub_family rows=1 output=['LEDGER_APPEND', 'WRITE:charge.json', 'WRITE:failure.json']
```
Runtime: installed C:/Users/neelj/anaconda3/python.exe 3.12.3. Default python is 3.10.0, whose datetime.fromisoformat rejects Z; the landed walkforward.py is unchanged. Commands use process-local PATH=C:/Users/neelj/anaconda3;%PATH% and PYTHONDONTWRITEBYTECODE=1.
Reproduce from tests with one explicit file per invocation: python -m pytest tests/platformkit/eval_gate/test_signal_audit_runner.py -q -p no:cacheprovider; then test_signal_audit_family.py; then test_signal_audit_report.py. Final output (runner, family, report): 27 passed in 2.21s; 26 passed, 1 skipped in 1.55s; 24 passed in 4.61s.
Both family and runner --help exit 0; the CLI exposes resume but no ledger/manifest bypass flags. Contract preflight: 9 PASS, 0 FAIL, --base master and the S396 spec.
FIX 1h input census (catalog/family/runner/verdicts; family/runner/report tests; memo): 300/299/279/300; 299/300/300; 300 lines, all ASCII and LF. The spec and archived critique were already changed/untracked at lane start and were not written by this lane.
## FIX 1h -- all five independent-verifier findings
Binding input: root _verdict_s396_1h.md and S396_spec.md including AMENDMENTS 1-4. Local construct fixtures only.
Runtime: default python 3.10.0. Each BEFORE below was reproduced before its module edit; AFTER uses the same construct.
1. BLOCKING, Python 3.10 timestamps: BEFORE `canonical_time = 2024-01-01T12:00:00.000000Z`;
   `ValueError Invalid isoformat string: '2024-01-01T12:00:00.000000Z'`. AFTER canonical UTC text ends +00:00,
   and the landed walker consumes the Z-input fixture. state_ts, feature_avail and settlement use the same normalizer.
   Nonzero sub-microsecond digits refuse explicitly before normalization can erase a strict availability boundary.
2. BLOCKING, loader evidence: BEFORE the exact loader-shaped construct raised `ValueError('decision_time_refused') ledger_rows= 1 failure= True`.
   AFTER an undeclared loader raises `ValueError('reference_availability_unknown') ledger_rows= 0 validation= NOT VALIDATED`.
   The default loader and any loader without the availability_fields contract refuse before charge; validation.json records
   NOT VALIDATED and charged=0. Dry-run prints NOT VALIDATED and never loads states. No evidence is defaulted or synthesized.
3. BLOCKING, alias sharing: BEFORE `candidate_calls= 2 inventory_rows= 2`, with no sealed alias identity.
   AFTER `candidate_calls= 1 inventory_rows= 2 divisor= 2`. MEMBER_FIELDS seals alias_of; validation re-derives its canonical
   target and refuses missing targets, alias chains and differing builder/declarations. Shared results retain both inventory
   identities and both hypotheses, including in the secondary Romano-Wolf matrix. Reversed member order seals identically.
4. BLOCKING, numeric fields: BEFORE accepted `ci95=[nan,nan], ci_member_allowance=[nan,nan], point=inf, n_states_at_min_train=1.5`
   and `ci_member_allowance=[True,True]`. AFTER `TypeError n_states_at_min_train must be a strict int, got 1.5 (float)`
   and `ValueError ci_member_allowance must be a finite non-bool real, got True`. Every count including nested coverage is strict;
   every metric/bound is finite and non-bool. tail_rank now counts complete draws per tail; interpolation is unchanged.
   Added 93 parameter cases; final JSON uses allow_nan=False. Existing interpolation and archived-evidence closures are unchanged.
5. CORRECTION, unzoned context: BEFORE `unzoned context accepted: 2024-01-02T12:00:00+00:00`;
   AFTER `BuildFailed NOT_EVALUABLE:build_failed:decision_time_refused (timezone_missing)`. The fallback is deleted.
   Zoned fixture contexts still pass; the direct unzoned regression refuses.
Verification: python -m pytest <one file> -q -p no:cacheprovider, sequentially, under default Python 3.10.0.
- tests/platformkit/eval_gate/test_signal_audit_runner.py: 31 passed (includes Z input and precise boundary refusal).
- tests/platformkit/eval_gate/test_signal_audit_family.py: 28 passed, 1 skipped (registry schema absent).
- tests/platformkit/eval_gate/test_signal_audit_report.py: 117 passed (includes all strict numeric regressions).
Both signal_audit_family --help and signal_audit_runner --help exit 0; these modules expose no self-check command.
Two intermediate test-edit errors (a comment swallowing a closing parenthesis and a misplaced assertion) were corrected before these passes.
Contract preflight over the pinned eight paths with --base master and the S396 spec: 9 PASS, 0 FAIL.
## FIX 1i -- both round-5 tiers, AMENDMENT 5
Local construct fixtures only, default Python 3.10.0; no authority or pre-existing module was edited.
1. BLOCKING (both tiers): every row is now loaded once and validated before charged_run; _score_family receives the detached validated snapshot. Timing, unique IDs, finite close, strict binary labels, vintage alignment and strict redaction all precede the charge. Any refusal writes validation.json with NOT VALIDATED and charged=0. BEFORE missing-evidence declared loader: `ValueError: reference_availability_unknown`, `ledger_rows=1`. BEFORE unzoned declared loader: `ValueError: decision_time_refused`, `ledger_rows=1`. AFTER the same constructs retain those named refusals with `ledger_rows=0`, `validation=NOT VALIDATED`. Regression tests assert zero charge for both metadata declarations, timing defects, duplicate IDs, nonfinite closes, leaked keys and vintage mismatches; a mutating charger proves the single loaded snapshot is detached.
2. BLOCKING (tier 2): BEFORE `outcome_2 completed n_states=64`, `ledger_rows=1`. AFTER `ValueError: outcome_not_strict_binary`, `ledger_rows=0`, `validation=NOT VALIDATED`. Dedicated 64-state tests inject each of 2, -1, True and "1" in the final row and require the same refusal.
3. BLOCKING (tier 1): BEFORE `family_allowance=None member_allowance=None` in charge.json. AFTER `family_allowance=0.05 member_allowance=0.025` as Decimal strings for the two-member construct. The initial crash-safe receipt remains; immediately after deriving allowances an atomic replacement adds both. The metric callback pins the exact ten-key schema and Decimal values; post-charge failure receipts still pass.
4. CORRECTION (tier 2): BEFORE memo claimed `All eight owned files remain exactly 300 lines`. Actual input lengths were 300/299/279/300; 299/300/300; 300. That historical sentence is corrected above. Final lengths (same order): 300/299/289/300; 299/300/300; 300. All eight remain ASCII, LF, <=300 lines.
Verification, one file at a time: runner 44 passed; family 28 passed, 1 skipped; report 117 passed.
Commands: python -m pytest tests/platformkit/eval_gate/test_signal_audit_<name>.py -q -p no:cacheprovider.
Both family and runner --help exited 0; neither exposes a self-check command. Preflight: 9 PASS, 0 FAIL.
Only runner.py, test_signal_audit_runner.py and this memo changed in FIX 1i; confirmed behavior stays unchanged.
## FIX 1j -- round-6 verdict, AMENDMENT 6
Local construct fixtures only, default Python 3.10.0. Edited only catalog.py, runner.py, runner tests and this memo in the pinned S396 set.
1. CORRECTION (tier 1), AMENDMENT 6(a): refuse empty and below-n_min corpora after full row validation, inside the same pre-charge try block.
   BEFORE: `count=0: completed n_states=0 | ledger_rows=1 | charge.json=True`.
   BEFORE: `count=29: completed n_states=29 | ledger_rows=1 | charge.json=True` (landed n_min=30).
   AFTER: `ValueError: corpus_empty` and `ValueError: corpus_below_n_min: count=29 n_min=30`.
   Both now give `ledger_rows=0 | charge.json=False | validation=NOT VALIDATED | charged=0`.
   Regression cases enumerate 0, 1 and n_min-1 rows with assert_no_charge; the direct 30-row boundary probe completes with one charge.
2. Tier-1 NOTE 2 / AMENDMENT 6(b): replaced the stale acceptance-history sentence in NOT VERIFIED with the ruled rounds 1-6 wording.
3. Tier-1 NOTE 3 / AMENDMENT 6(c): renamed the dry-run field availability_declared_informational; its value still gates nothing.
4. Tier-2 NOTE 1 / AMENDMENT 6(c): row refusals now include game_id and value (the offending row, canonicalized after timing validation).
   Timing and validation wrappers preserve exception types, including LeakError, and re-raise; diagnostics assertions cover both paths.
5. Tier-2 NOTE 2: the real loader must filter unsettled games before the runner. An outcome None still refuses the entire batch before charging.
6. Tier-2 NOTES 3-4: sport-specific census behavior and earlier-round figures remain unchanged; current figures follow here.
Verification: runner 47 passed; family 28 passed, 1 skipped (registry parquet absent); report 117 passed, one file at a time with -q -p no:cacheprovider.
Both family and runner --help exit 0; neither exposes a self-check command. No real archive, ledger, network or pod was used.
Two new diagnostic assertions initially failed on raw versus canonical feature times; corrected expectations now pass without changing timestamp behavior.
Contract preflight over the pinned eight with --base master and the S396 spec: 9 PASS, 0 FAIL.
Final lengths: modules 300/299/296/300; tests 299/300/300; memo 288. All eight ASCII, LF, <=300 lines.
## NOT VERIFIED
- No real signal was audited. Nothing here measures any catalog or registry signal; the only numbers produced come from a synthetic fixture corpus built by the test itself.
- No real corpus was loaded: `load_states` was never called against a real window, the committed-manifest path has not been run end to end on a real family, and the registry reader is untested against the real parquet (`read_registry_rows` was never executed here because the file is absent; only the column list was checked).
- The declared link is one additive logit link with a fixed ridge. No other functional form, interaction, per-signal tuning or alternative reference baseline was evaluated. `MIN_TRAIN`, the ridge and the Newton step count are new constants of this module, not landed bars, unswept, and not justified against any held-out criterion.
- The Romano-Wolf column is reported, not validated: its agreement with the member-allowance verdict is asserted nowhere, by design -- it never decides. Single window, single corpus: every interval this tool can produce is SINGLE-WINDOW, and an AHEAD(SINGLE-WINDOW) row is not a result and is never promoted by `survivors()`.
- Scale is untested. The largest family exercised here has 60 members (10 evaluable by declaration for nba after Round 3, all UNDERPOWERED by coverage), the largest SCORED family two; runtime through 2000 draws is unmeasured.
- No catalog class from `domains/` has ever produced a finite feature here; the scored catalog path is exercised only by stubs, and the fresh-builder guarantee is proven against a stub that keeps state, for the one failure mode that stub exhibits.
- `extra` is empty by construction: AMENDMENT 1(b) enumerates the context fields and names no `extra`. Whether the 27 classes reading `ctx.extra` should get the state's `features` channel is an OWNER decision, not this row's.
- The domain-to-sport map and season rule remain module declarations (four pairs; no current catalog class reads `ctx.season`).
- The default landed loader remains NOT VALIDATED. Every loader now supplies actual availability and settlement evidence in every row before charge; metadata declarations alone grant no validity and no evidence is synthesized.
- The sealed declaration, not disk, drives both a catalog build and FIX 1d's re-derivation: a member is checked against its OWN declarations (a manifest sealed from an ALREADY-edited class is not caught), and a class RENAMED or MOVED after sealing fails at import time -- a path exercised only through a stub.
- The archived model side is reconstructible for the REGISTRY arm in the fixture. No reconstruction was attempted from a real run, and the code digests prove identity only, never that the code is correct.
- The verdicts of rounds 1-6 were applied through fix 1j; both round-6 tiers accepted fix 1i (tier 1 with the corpus_empty correction); the row's independent acceptance is recorded in the register at landing.
