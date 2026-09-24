GAP S396 | sport all (signals) | worktree harness-h57 (master-based) | log cx_s396_signal_audit
# Signal audit runner: every candidate signal through the leak-free walk-forward gate, one charge per family (workstream B; ASTRA_ROUND15 row 6)

SINGLE PROBLEM: 60 catalog signal classes (scripts/platformkit/eval_gate/spa_catalog_report.txt: catalog_signals_on_disk=60, every
row NOT_EVALUABLE) and 86 registry signals (data/registry/signal_registry.parquet, columns signal_id, entity, domain, granularity,
source, formula, leak_rule, consumer, ev_tier, coverage_pct, status; 72 folded / 14 deferred; consumers scouting 55, ingame 12,
corr-model 10, point-model-candidate 9) have never been pushed through the landed leak-free gate with a sealed hypothesis, a ledger
charge and a game-clustered interval. Nothing may be called a signal until it has, and an honest NOT_EVALUABLE or UNDERPOWERED per
signal is the expected result.

BINDING BEFORE-CONDITION: quote from master (a) scripts/platformkit/eval_gate/backtest_runner.py _charge_ledger(path, spec, sport,
start, end, *, family=None, hypothesis_hash=None, tier=None, prereg_sha256=None, trial_prereg_sha256=None) -> dict (k_cumulative =
cumulative_k(prior, 1) over the WHOLE file; k_family = next_k_family(rows, family); append under ledger_lock), load_states(sport,
start, end, repo=None, counts=None) -> list[dict], and the family allowance helper used at its line 243 (threshold = eps_eff(0.05,
charge["k_cumulative"])); the canonical call in s58_nba_halftime_asof_trial.py:125-133 (SEAL -> CHARGE -> score; the K used is the
charged row's own k_cumulative); (b) walkforward.py: PURGE_HOURS = 48, EMBARGO_DAYS = 3, walk_forward(states, predict_fn,
select_inside=True, *, strict_redaction=False, allow_keys=(), guard_state_keys=False) -> WalkForwardResult (predict_fn receives the
training slice, the redacted test state and select_inside; records carry game_id, ts, p_model, p_close, y), TEST_VIEW_KEYS and
LeakError; (c) scripts/platformkit/ingame/gate_a0_ingame_vs_market.py cluster_bootstrap(df, col_a, col_b, n_boot=N_BOOT, seed=SEED)
-> (point, lo, hi) and verdict(lo, hi, n_games, n_min=N_MIN_GAMES) (UNDERPOWERED when n_games < n_min or lo <= 0 <= hi; BEHIND when
lo > 0; AHEAD otherwise -- a difference is candidate loss minus reference loss); (d) romano_wolf.py (n_bootstrap 2000, seed 2718,
game_id-block null bootstrap: quote its public signature); (e) retro_correction.catalog_signals() and the interface of one catalog
class (how it exposes name, domain and any compute method); (f) scripts/platformkit/catalog_common.py verdict words (SHIP / REJECT /
DEFER) -- this row does NOT use them. Contract Q1, Q2, Q3, Q5, Q6.

CHANGE (owned files: NEW scripts/platformkit/eval_gate/signal_audit_family.py, NEW signal_audit_runner.py, NEW
signal_audit_verdicts.py, NEW tests/platformkit/eval_gate/test_signal_audit_family.py, NEW test_signal_audit_runner.py, memo;
data/registry/ is READ-ONLY and is never written, copied or re-saved; no landed module is edited):
1. signal_audit_family.py (<= 300 LOC): a FAMILY is defined BEFORE scoring by (sport, target = the settled home-win outcome,
   decision horizon = the pregame close, reference baseline = the devigged close p_close, fixed corpus window start..end); every
   signal variant is a MEMBER of one family; alias-equivalent members share computation but keep their inventory identity. The
   FAMILY MANIFEST (one JSON file per family) lists, per member: signal_id, source (catalog | registry), the ONE-LINE HYPOTHESIS
   ('adding <signal> to the devigged close lowers walk-forward Brier on <sport> <start>..<end>'), the feature builder name, and
   EVALUABILITY (EVALUABLE | NOT_EVALUABLE:<reason>) decided by whether a leak-free per-state feature exists on the gate corpus:
   registry rows whose entity is player, whose consumer is scouting, or whose formula is not computable from the state's allowed keys
   are NOT_EVALUABLE with that reason; catalog classes without a compute method likewise. Every member, contrast and window is a
   COUNTED hypothesis; n_declared_evaluable is written into the manifest. seal(manifest_path) -> sha256 writes the canonical compact
   JSON once and a sibling .sha256; check_seal refuses an edited manifest. The manifest is committed BEFORE any run (Q1) and its
   digest is the family's hypothesis_hash. Any revision or additional look is a NEW manifest and a NEW charge.
2. signal_audit_runner.py (<= 300 LOC): --family-manifest <sealed file> --ledger <path> --out <dir> [--dry-run]. Order: verify the
   seal and that the manifest is git-committed -> read the ledger's prior max K -> exactly ONE _charge_ledger(..., family=<manifest
   family>, hypothesis_hash=<manifest sha256>, tier=<from manifest>) for the whole family -> write charge.json (k_at_launch = the
   charged row's own k_cumulative; family_allowance = eps_eff(0.05, k_at_launch); member_allowance = family_allowance /
   n_declared_evaluable, a Bonferroni allocation, as Decimal strings) -> load_states(sport, start, end) -> reference arm: walk_forward
   with predict_fn returning p_close -> for EVERY evaluable member: walk_forward with predict_fn = the market prior with the signal
   added through one declared link (logit(p_close) + beta * z(signal); beta and the z-scaling fitted ONLY on the training slice
   walk_forward hands to predict_fn; strict_redaction=True) -> per member: paired per-game Brier and log-loss differences (candidate
   minus reference), archived as the per-game paired-loss series beside the summary (Q9) -> the game-clustered bootstrap draws (the
   landed n_boot and seed; the 0.05 interval proven draw-for-draw equal to cluster_bootstrap) -> the interval at the MEMBER allowance
   (percentiles member_allowance / 2 and 1 - member_allowance / 2 over the same draws) -> verdict: AHEAD(SINGLE-WINDOW) ONLY when the
   member-allowance interval lies wholly below zero with n_games >= the landed n_min; BEHIND when it lies wholly above zero;
   UNDERPOWERED otherwise; the landed Romano-Wolf stepdown over the family's evaluable members is reported as a SECONDARY column and
   never decides. NOT_EVALUABLE members are listed with their reason and consume nothing. The FULL MATRIX (every member, every
   column) is published; nothing is omitted. A crash after the charge leaves charge.json and failure.json (the charge stands).
   --dry-run does everything except the charge and the metric (it prints the evaluability census and the K it would read). Stdout:
   accounting lines only (ledger path, prior max K, k_at_launch, family, counts); every value goes to the artifact.
3. signal_audit_verdicts.py (<= 300 LOC): the artifact schema (per member: hypothesis, evaluability, n_games, n_states, point, ci95
   [lo, hi], ci_member_allowance [lo, hi], verdict, rw_adjusted_reject, largest_single_game_share, leave_one_game_out_range) and
   survivors(): an AHEAD(SINGLE-WINDOW) member is NEVER promoted by this tool; the survivors list names each such member with the
   sentence 'requires its own sealed prereg on a second corpus and min_corpora_eff at the launch K before any statement' (Q5).
4. Tests: seal / check_seal / edited manifest refused; a synthetic corpus of at least 60 games with one planted informative signal
   and one noise signal through the REAL walk_forward and the game-clustered draws (small n_boot through the landed parameter): the
   planted signal's interval is below zero, the noise signal is UNDERPOWERED, the ledger grows by exactly ONE row regardless of the
   number of members, K is read at launch, member_allowance equals family_allowance / n_declared_evaluable, no metric appears on
   stdout, a leaked key raises LeakError under strict_redaction, order independence over member order and state order, NOT_EVALUABLE
   reason for a player-entity registry row, the paired-loss series file reconstructs the point to 1e-9.
5. Memo docs/evidence/harness/S396_signal_audit_2026-09-22.md.

CONTROLS: PREPARE only; construct tests; no real corpus, no real ledger (tests use a temp ledger through the landed test seam), no
network; the registry parquet is opened READ-ONLY at most to read its schema in a test marked skipif when the file is absent. The
orchestrator runs the first family from the repo root (one charge) after its manifest is sealed and committed. ACCEPTANCE: per-file
tests pass one at a time; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary (the SHIP word of catalog_common is not used); memo
ends with NOT VERIFIED.

AMENDMENT 1 (2026-09-22 16:5xZ; binding; after the Opus build's five findings). (a) eps_eff lives in
scripts/platformkit/combo/fwer_budget.py:64 and is imported from there (backtest_runner.py:243 is the usage). (b) THE CATALOG
INTERFACE IS build, NOT compute: every catalog class exposes name, target, scope, hypothesis() and build(self, ctx: AsOfContext)
(domains/<sport>/signal_catalog.py, e.g. basketball_nba lines 70-80); AsOfContext is src/loop/signal.py:fifty-four (a READ-ONLY import;
src/ is never edited) with fields decision_time, player_id, team, opp, game_id, game_date, season, is_home, scope, snapshot, live,
extra. A catalog member is EVALUABLE when its target is the home-win outcome and its scope includes pregame; the runner builds one
AsOfContext per state from the allowed test-view keys only (decision_time = the state's timestamp through parse_venue_time; team =
the home code and opp = the away code with is_home True; game_id; game_date; season derived from game_date; scope 'pregame';
player_id None; live None), calls build(ctx) inside predict_fn for the training slice and the test state, and takes the scalar it
returns (a dict -> the member's declared key). A None, an exception or a non-finite value is a COUNTED NOT_EVALUABLE:build_failed for
that state (never zero); a member with fewer than the landed n_min games carrying a finite feature is UNDERPOWERED:feature_coverage.
Leak safety of what build reads is the store's as-of contract (AsOfContext's docstring: every read filtered to <= decision_time);
the runner additionally asserts that build never touches the test state's redacted keys (strict_redaction stays on) and records the
atlas / store paths the class declares. Members whose build requires an input absent on this machine are NOT_EVALUABLE:<input
missing> with the input named. (c) The per-member column helpers (bootstrap_draws, interval, paired_series, score_member) may live
in signal_audit_verdicts.py (the 300-line rail). (d) --dry-run stops before load_states (declared; the evaluability census and the K
are printed without opening the corpus). (e) The registry-schema test skips when data/registry/signal_registry.parquet is absent;
its fixture columns are the eleven real ones.

AMENDMENT 2 (2026-09-22 18:4xZ; binding; from the Opus round-3 verdict). (a) OWNED SET PINNED at eight files: scripts/platformkit/
eval_gate/signal_audit_catalog.py (the catalog AST census and evaluability, split out for the 300-LOC rail), signal_audit_family.py,
signal_audit_runner.py, signal_audit_verdicts.py, tests/platformkit/eval_gate/test_signal_audit_family.py,
test_signal_audit_runner.py, test_signal_audit_report.py, and the memo -- additive, nothing else touched; src/loop/signal.py is a
read-only import. (b) NE_INPUT REACHABLE: every one of the 60 on-disk catalog classes declares reads_atlas = [], so gating
NOT_EVALUABLE:<input missing> on reads_atlas alone never fires and all 60 seal as EVALUABLE, inflating n_declared_evaluable (the
allowance divisor; conservative direction, but wrong as a count). The evaluability rule ALSO returns NE_INPUT when the AST build
body references self.store, self.read or ctx.extra (the memo already measures 27 such classes); the census counts the two paths
separately (ne_input_declared, ne_input_body). (c) A LeakError (an AssertionError) raised inside the census or a member's scoring
is fail-closed by design: it ends the run rather than refusing one member, and the memo says so.

AMENDMENT 3 (2026-09-22 19:1xZ; binding; from the astra round-4 critique on fix 1f; the full critique is archived as
docs/evidence/harness/S396_astra_r4_critique_2026-09-22.md and is binding where it names a line). (a) TIME ORDER IS CHRONOLOGICAL:
the landed walk_forward consumes training rows in STRING timestamp order (walkforward.py:135), so mixed UTC offsets ('10:00+00:00'
vs '11:00+02:00') misorder -- the runner normalizes EVERY timestamp it hands to walk_forward to canonical UTC 'Z' text (through
parse_venue_time) and refuses a state whose timestamp cannot be normalized; a test with mixed offsets and a builder asserting
monotonic UTC time; the census stub's memory must live per instance (fresh instances isolate the census from the folds).
(b) AVAILABILITY AND SETTLEMENT ARE CHECKED, NOT ASSUMED: the reference close used for a decision must carry an availability
timestamp <= the decision time (a close with no availability timestamp refuses reference_availability_unknown); a training label
enters a fold only when its game's settlement timestamp <= that fold's decision boundary (imported EMBARGO honoured); a test with
overlapping unrelated games after twenty warm-up games requires exclusion. (c) THE CHARGE IS IDEMPOTENT PER MANIFEST DIGEST: a
run whose family manifest digest already has a ledger row REFUSES charge_exists (K unchanged) unless --resume-charge <row id>
names that row AND the prior run's failure.json exists, in which case the run REUSES the row (no new charge) and writes into a
new --out; _charge_ledger's append-then-raise is inside the receipt / failure protection; tests: crash then identical retry
-> refused, one ledger row; resume -> one row, run completes. (d) ONE READ: the manifest bytes are read ONCE; the digest, the seal
check, the validation and the charge all use those bytes (a swap between hash and validate cannot change the allowance); test by
swapping the file between calls. (e) BUILDER BINDING RE-DERIVED: a registry member's builder name is part of the sealed
hypothesis identity and is re-derived at validation (a changed builder name refuses); a noise hypothesis can never score a
planted feature. (f) LeakError NEVER DEGRADES: a LeakError raised inside signal.build is not converted to BuildFailed
(catalog.py:226) -- it terminates the family with failure.json; the sorting-failure suppression at catalog.py:208 is removed.
(g) UNEQUAL COVERAGE: members with different n_states enter the Romano-Wolf step-down only on the intersection of their state
keys (recorded as n_states_common), or the family refuses unequal_coverage when the intersection is below the minimum.

AMENDMENT 4 (2026-09-22 21:3xZ; binding; from the codex sol round-4 verdict on fix 1f, read together with the AMENDMENT 3 rulings fix 1g landed). (a) REAL LOADER ROWS OR NOT VALIDATED: MEASURED -- rows returned by the landed
load_states carry an unzoned state_ts and carry neither reference_available_at nor settled_at, so the default runner
refuses them twice over (signal_audit_catalog.py:282; decision_time_refused, then reference_availability_unknown
once a Z is added). RULING: availability and settlement timestamps are supplied through the real loader / corpus
contract and are NEVER synthesized, defaulted or back-filled by the runner; until that contract carries them the
affected rows are marked NOT VALIDATED in the artifact and the memo, and the refusal of AMENDMENT 3(b) stands as the
only other outcome. Test: a loader-shaped row without availability evidence yields NOT VALIDATED or
reference_availability_unknown, never a scored member.
(b) ALIAS-EQUIVALENT COMPUTATION SHARING EXISTS: MEASURED -- CHANGE 1's sharing is absent; MEMBER_FIELDS has no alias
or computation identity and a search for alias across every candidate module returns nothing (signal_audit_family.py:43).
RULING: a canonical computation key (or an explicit alias target) is part of the SEALED member identity and is
validated at load; each canonical computation is evaluated ONCE, separate inventory rows are still emitted per alias,
and every hypothesis is still counted in the allowance divisor. Test: two alias members of one canonical computation
produce one evaluation, two inventory rows, and a divisor of two.
(c) STRICT NUMERIC VALIDATION ON EVERY COUNT AND BOUND: MEASURED -- artifact validation accepted
n_states_at_min_train=1.5 and ci_member_allowance=[nan,nan] (signal_audit_verdicts.py:155). RULING: every count is a
strict non-boolean int (a float, bool or numeric string refuses) and every metric and interval bound is a
non-boolean FINITE real (nan, inf and bool refuse), checked before the artifact is written. Tests: each of 1.5, True,
"3", nan and inf refuses in the field where it is planted.
(d) THE CRITIQUE ARCHIVE IS NOT A CANDIDATE FILE: MEASURED -- git status during verification carried a ninth
untracked artifact, docs/evidence/harness/S396_astra_r4_critique_2026-09-22.md, outside AMENDMENT 2(a)'s pinned eight.
RULING: AMENDMENT 2(a)'s owned set stays EIGHT files; an archived critique named by an amendment is evidence of the
adjudication, archived and landed on its own pathspec, and is excluded from this row's candidate -- a verifier
counting the owned set excludes it by name rather than rejecting the candidate for it. Test: the candidate's file
census equals the pinned eight with the critique listed separately as archived evidence.
(e) THE PERCENTILE SENTENCE IS CORRECTED: MEASURED -- the memo at S396_signal_audit_2026-09-22.md:194 says unresolved
percentiles pin to extreme draws, but interval(arange(2000), 0.00015625) returned [0.156171875, 1998.843828125] --
interpolated, not pinned. RULING: the memo describes the interpolation actually used and states plainly that nominal
coverage in the tiny tail remains UNRESOLVED; no claim rests on that tail. Test: the memo's sentence quotes the
reproduced endpoints above.
(f) PYTHON 3.10 IS THE RUNTIME: MEASURED -- the fix lane ran the three test files on Python 3.12.3 because the default
3.10 interpreter rejects a trailing Z in datetime.fromisoformat; the local environment (conda basketball_ai) is Python 3.10.20
and the runner must run there. RULING: every timestamp parse goes through the landed parse_venue_time (never fromisoformat on
a Z-suffixed text), and the per-file tests are run and reported under the default python of the repo (3.10); a round or fix
report states the interpreter version it used. Test: the three test files pass under python 3.10 with a Z-suffixed fixture.

AMENDMENT 5 (2026-09-23 16:5xZ; binding; from round 5 on fix 1h -- sol REJECT (two blockers) and astra REJECT (two blockers,
one correction); both tiers confirmed AMENDMENT 4(b), 4(c), 4(f) and the unzoned fallback CLOSED under Python 3.10.0).
(a) EVERY ROW IS VALIDATED BEFORE THE CHARGE -- STILL OPEN (4(a)): signal_audit_runner.py:162 and :174-200 charge, then load
and validate; a loader that merely declares availability_fields passes the pre-charge guard while its rows lack both fields
(ledger 0 -> 1, then decision_time_refused), and the tracked test at test_signal_audit_runner.py:234-238 EXPECTS one ledger
row after malformed timing evidence. RULING: load once; validate every input row (zoned timestamps through parse_venue_time,
availability and settlement evidence present, unique ids, finite close, a STRICT BINARY outcome in {0, 1} -- a 2 or a bool
is refused by name, never dropped_unsettled, never scored; feature-vintage alignment; strict redaction) BEFORE charged_run;
any refusal means ZERO ledger rows and the row set marked NOT VALIDATED; the validated snapshot is what _score_family
receives; the malformed-row tests require zero ledger rows. (b) INVALID SETTLED LABELS CANNOT SCORE: an outcome of 2 injected
into one of 64 states produced a completed AHEAD (SINGLE-WINDOW) report over all 64 with ledger 0 -> 1
(signal_audit_runner.py:199; :97 checks integer type only). Covered by (a); a dedicated test injects 2, -1, True and "1".
(c) charge.json CARRIES BOTH ALLOWANCES: CHANGE 2 requires them; the receipt has charge, charge_row_id, hypothesis_hash,
k_at_launch, ledger_path, manifest_commit, manifest_committed, prior_max_k only. RULING: immediately after the allowances are
derived (runner :176-177) the receipt is enriched ATOMICALLY with family_allowance and member_allowance as Decimal strings,
before any metric, retaining the crash-safe initial receipt; an exact artifact-schema assertion pins the key set. (d) The
memo's line-count sentence is corrected to the measured lengths (modules 300 / 299 / 279 / 300; tests 299 / 300 / 300; memo
300). (e) The identical-launch behaviour (0 -> 1 -> 1 with charge_exists on the second) is CORRECT per AMENDMENT 3(c) and
stands. Everything else in fixes 1b-1h byte-identical in behaviour.

AMENDMENT 6 (2026-09-23 18:2xZ; binding; from round 6 on fix 1i -- Opus tier 1 ACCEPT WITH CORRECTIONS, Opus tier 2 ACCEPT with
no blocking or correction items). Both tiers reproduced AMENDMENT 5 (a)-(d) as closed: every row validated before charged_run
(a bad last row of 64 leaves ledger_rows 0, NOT VALIDATED, no charge.json); 2 / -1 / True / '1' / None / 1.0 / np.int64(1)
refused as outcome_not_strict_binary; the allowances written atomically into charge.json as Decimal strings with the exact
ten-key set; lengths 300/299/289/300 and 299/300/300 and the memo 300, ASCII, LF; the identical relaunch 0 -> 1 -> 1;
feature vintage strictly earlier than the decision time with zone conversion; crash between the receipt and the enrichment
leaves an untorn charge.json plus failure.json; order independence over shuffles. ONE CORRECTION, RULED: (a) AN EMPTY CORPUS
MUST NEVER BE CHARGED: a loader returning [] passed validation and wrote a ledger row (n_states 0) -- a spent FWER
hypothesis with no possible measurement, and AMENDMENT 3(c) then blocks the identical retry with charge_exists. RULING:
after the validation loop and inside the same try block, an empty corpus is refused by name (corpus_empty) and a corpus
below the family's n_min is refused by name (corpus_below_n_min, naming the count and the bar) BEFORE the charge, through the
same NOT VALIDATED path with charged 0 and no charge.json; a zero-row test and a below-n_min test assert no ledger row and no
charge.json. (b) The memo's stale sentence at the NOT VERIFIED section ('Six verdicts were applied here (rounds 1-3 ...)')
reads: the verdicts of rounds 1-6 were applied through fix 1j; both round-6 tiers accepted fix 1i (tier 1 with the
corpus_empty correction); the row's independent acceptance is recorded in the register at landing. (c) NOTES kept as
wording only: availability_declared is informational on the dry-run dict (renamed availability_declared_informational or
dropped -- builder's choice, stated); outcome_not_strict_binary and the other row refusals name the game_id and the
offending value; the memo's earlier-round test counts stay in their round sections and the FIX 1j section carries the
current figures. Tier 2's NOTE that a row with outcome None (an unsettled game) refuses the whole batch is the intended
AMENDMENT 5(a) behaviour: the real loader filters unsettled games before the runner -- the memo states this contract.
