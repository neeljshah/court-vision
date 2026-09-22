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
(domains/<sport>/signal_catalog.py, e.g. basketball_nba lines 70-80); AsOfContext is src/loop/signal.py:54 (a READ-ONLY import;
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
