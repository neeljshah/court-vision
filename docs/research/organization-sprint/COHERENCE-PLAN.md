# COHERENCE-PLAN -- Organization Sprint Fix Waves

ASCII only. LOCAL commits only. src/kernel/api/scripts(team_system,intel) are HUMAN-GATED
(must not be edited; build in scripts/platformkit or domains/<sport>). Every prediction-touching
change must pass the eval-gate. Per-file tests ONLY. <=300 LOC/file.

This plan converts the cross-surface audit into ordered FIX WAVES. Each wave is a set of fixes
over DISJOINT file surfaces so the items inside a wave can run as parallel Workflow fan-outs
(one agent per surface bullet). A wave's GATE must pass before the next wave starts. P0
correctness/honesty/leak fixes come first. The remaining-work streams (X2 MLB in-game, memory
reorg, vault reorg, code-org, CLAUDE.md-slim apply) are explicit planned waves at the end.

Owner-model legend: OPUS = author/decide/diff-review; SONNET = mechanical edit under a precise
spec; HUMAN = human-confirm/apply (gated path, push, key rotation, real-corpus run, or buyer copy).

Severity source: the per-surface auditor findings. P0 = active honesty/leak/correctness defect
reachable today. P1 = latent leak/correctness or false-claim that bites on the real path or a
common input. P2 = hygiene/doc/dead-code.

--------------------------------------------------------------------------------
## WAVE 0 -- P0 LEAK + HONESTY (blocking; serialize per-surface, run surfaces in parallel)
--------------------------------------------------------------------------------
These are the only true-P0 items: a reachable-today leak or a fabricated/unreproducible win.
Disjoint surfaces -> parallel-safe. NONE of these touch a human-gated tree.

W0.1  Vintage leak guard: string-compare timestamp vs date-only drops/leaks same-day predictions.
      - FIX: factor ONE shared vintage-compare util (parse both sides with
        datetime.fromisoformat, normalize tz to UTC, assert avail_dt < state/tip_dt). Replace the
        raw string compares in: ledger/grade_outcomes.py (`str(pred_ts) < str(game_date)` over-drops
        same-day pre-tip), eval_gate/schema.py:50 + walkforward.py:39 (date-only avail passes as
        prefix-less-than an in-game datetime state_ts -> same-day in-game leak), freshness already
        does it right (as_of_reader) -- make it the reference. Add the masking test: a
        pred_ts='<date>T09:00:00' / game_date='<date>' row MUST be kept; an in-game feature_avail
        at-or-after state_ts MUST raise LEAK.
      - OWNER: OPUS authors the util + spec; SONNET applies to the 3 call sites + tests.
      - FILES: scripts/platformkit/eval_gate/{schema.py,walkforward.py}; scripts/platformkit/
        ledger/grade_outcomes.py; (reference) scripts/platformkit/freshness/as_of_reader.py;
        tests test_eval_core.py, test_walkforward.py, ledger/test_ledger.py.

W0.2  Freshness vintage guard raises TypeError on tz-aware vs naive (read path crashes; AssertionError
      catch escapes) AND supersede tie-break is input-order-dependent.
      - FIX: coerce both sides to UTC before compare in as_of_reader (mirror the W0.1 util);
        make the supersede tie deterministic + conservative (OUT wins on equal extracted_at).
        Add tz-aware tests and both-orders supersede tests.
      - OWNER: SONNET under spec (same util as W0.1, so coordinate ordering: W0.1 lands the util
        first if shared, else this surface inlines it -- keep disjoint by having W0.2 own
        as_of_reader.py exclusively).
      - FILES: scripts/platformkit/freshness/as_of_reader.py + test_freshness_pipeline.py.

W0.3  Tennis predictions produce ZERO ledger rows (block key 'p_home_win' never matches
      _iter_binary_markets) AND build_result has no game_date/inputs -> ledger vintage guard
      bypassed for in-game tennis (and NBA same key).
      - FIX: add ('p_home_win','ml') to the market-key map (or emit canonical home_win_prob/
        p1_win_prob from the blocks); populate build_result with game_date + a state-bearing
        inputs dict so append_from_result enforces pred_ts<tip and yields distinct inputs_hash
        per live state. Add a test: real build_result('tennis') -> >=1 row, distinct hashes.
      - OWNER: OPUS (touches predict_matchup contract + ledger key map -- needs a decision on the
        canonical key); SONNET applies.
      - FILES: scripts/platformkit/predict_matchup.py (_pregame_block/_ingame_block/build_result);
        scripts/platformkit/ledger/ledger.py (_iter_binary_markets, append_from_result);
        ledger/test_ledger.py.

W0.4  RAG retrieval tools + raw-note resource emit UNSCRUBBED numbers; scrubber misses bare
      decimals / spreads / 'percent' / most BOUNDARY_FORBIDDEN_TOKENS / 5 of 6 retracted numbers.
      - FIX: run assemble._scrub over h.snippet+h.title in vault_search() and related_nodes(),
        and over the vault://note/{id} resource body (or drop the raw-body resource). Build
        _FORBIDDEN_RE FROM config.BOUNDARY_FORBIDDEN_TOKENS; add bare-decimal prob (0?\.\d{2,}),
        signed half-point lines ([+-]\d{1,2}\.5), 'percent|pct' words, n/m ratios; add an explicit
        retracted-number guard (18.38|0.119|78.11|8.94|54.57|54). Fix the \bprob/\bodds
        unbounded-prefix bug (problem->scrubbed). Import the production regex into the boundary
        tests (no copy) and add an adversarial MEMORY-query test asserting no forbidden token in
        any tool/resource output.
      - OWNER: OPUS (regex + boundary policy is honesty-critical); SONNET applies + tests.
      - FILES: scripts/mcp_server/vault_knowledge.py; scripts/platformkit/knowledge/{assemble.py,
        config.py}; scripts/platformkit/knowledge/tests/test_boundary.py.

W0.5  promptfoo.yaml is shipped broken (provider id `exec` invalid; output.exitCode assertion
      semantically invalid) while its comments claim identical CLI exit semantics.
      - FIX: drive the gate from a subprocess/python_assert that runs run_gate --golden and asserts
        on returncode (not provider exitCode); use the `exec:`-prefixed id form if keeping exec;
        keep the `contains: SYNTHETIC ANCHOR` honesty guard and strengthen `verdict` to a verdict
        VALUE. Correct the header comment. (Wired into nothing yet -> deferred, but fix before any
        CI wiring.)
      - OWNER: OPUS authors; SONNET applies.
      - FILES: scripts/platformkit/eval_gate/promptfoo.yaml.

W0.6  In-game WIN headline (NBA 0.209->0.159) is real-corpus-only, CONTRADICTED by the committed
      fixture (no-improvement 0.301 vs 0.244), printed without VALIDATION_PENDING, and propagated
      into 6+ docs + PROPOSED UI copy; ingame_scoreboard prose hard-codes numbers that contradict
      its own table; PROOFS.md falsely claims the whole scoreboard reproduces on committed fixtures.
      - FIX (CODE part, this wave): make ingame_scoreboard 'Reading it:' summary derive numbers
        from the rendered rows (no hard-coded literals); add a SYNTHETIC/FIXTURE source badge to
        beat_the_close_scoreboard + ingame_scoreboard when PROOF_CORPUS_ROOT points at
        tests/fixtures, and change the 'SAME real outcomes' header to name the fixture slice;
        replace unicode em-dash/arrows with ASCII in both render_markdown writers.
      - FIX (DOC/COPY part -> HUMAN, tracked in Wave 8): scope the 'reproduces on committed
        fixtures' and 'every headline number is OOS' claims; badge NBA in-game as real-corpus /
        VALIDATION_PENDING with the honest fixture verdict; reconcile the MLB 0.241/0.250/0.256
        variants to one generated number.
      - OWNER: OPUS authors the scoreboard fix; SONNET applies code; HUMAN applies the buyer-doc
        copy edits (Wave 8 has the doc set).
      - FILES (code): scripts/platformkit/ingame_scoreboard.py; scripts/platformkit/
        beat_the_close_scoreboard.py. (docs deferred to Wave 8.)

GATE-0 (must pass before Wave 1):
  - cd scripts/platformkit/eval_gate && python run_all.py  -> ALL GREEN.
  - python -m scripts.platformkit.eval_gate.run_gate --golden  -> exit 0, honest verdicts.
  - New W0 tests pass per-file (same-day keep, tz-aware, tennis ledger row, boundary scrub,
    fixture-badge present).
  - OPUS eyeballs each diff; confirm no human-gated path touched; ASCII-only; no retracted number
    as live copy.

--------------------------------------------------------------------------------
## WAVE 1 -- P1 CORRECTNESS + HONESTY (leak-adjacent / false-claim; disjoint surfaces)
--------------------------------------------------------------------------------
Run after GATE-0. Surfaces are disjoint -> parallel fan-out, one agent per bullet.

W1.1  eval-gate verdict statistics can manufacture a false BEATS_CLOSE.
      - FIX: DM p-value from Student-t on (G-1) cluster df (not normal); g==1 returns
        SE=inf/dm_stat=0/p=1.0 (never significant on one cluster); add n_clusters>=MIN_CLUSTERS
        (e.g. 20) to the BEATS_CLOSE condition alongside DM_MIN_N. Add a direct _verdict unit
        (bss>0,p<0.05,n>=200 -> BEATS_CLOSE; n<200 -> falls through).
      - OWNER: OPUS (stats); SONNET applies.
      - FILES: scripts/platformkit/eval_gate/{dm_test.py,run_gate.py}; test_eval_core.py / test_gate.py.

W1.2  Real --corpus predictor is a broken stub (ml_accuracy.run signature/return-type mismatch);
      run_gate has no --sport dispatch; SELL-READINESS documents a 4-sport real path the gate
      cannot run; gate/anchor/baselines/golden are NBA-only while docs claim 4-sport.
      - FIX: add --sport to run_gate.main(); _load_model_predictor(sport) dispatches to
        proof_<sport>.beat_the_close_*.run with a per-state adapter matching
        predict_fn(train,test,select_inside)->float; generalize season parsing (drop hardcoded
        'nba_'); add validate_golden (or corpus validator) on the real corpus path; either add
        registered-skip soccer/tennis slots for symmetry or scope SELL-READINESS to NBA(+MLB)
        until dispatch exists. Add a unit asserting the wrapper call-shape.
      - OWNER: OPUS (architecture decision); SONNET applies. SELL-READINESS copy edit -> HUMAN (Wave 8).
      - FILES: scripts/platformkit/eval_gate/run_gate.py (CORPORA, SKIPPED_SLOTS,
        _load_model_predictor, _load_states, main); cross-ref proof_nba/ml_accuracy.py.

W1.3  In-game blend headline functions are dead vs the eval path; production predict_live->
      live_repricer is NOT judged by the gate; ingame_blend_* orphaned; overfit_gap measured on
      RAW but metrics on SMOOTHED; signed-vs-abs margin bucketing fragments late-game data;
      garbage_clamp + real fit_plive never in the OOS proof; causal EMA unguarded against ordering;
      train/inference time_pressure divergence.
      - FIX (in-game architecture coherence): (a) wire the OOS harness to build p0 via derive_p0
        and p_live via build_state_features+fit_plive+predict_plive (exercise the shipping path),
        applying garbage_clamp inside the blended path; (b) compute overfit_gap and headline
        metrics on the SAME (smoothed-or-not) series; (c) make build_state_features the single
        source for every PLIVE_FEATS feature (kill the /600 ad-hoc); (d) sort/assert per-game time
        order in _apply_smoothing; (e) resolve signed-vs-abs margin (pick one, align garbage_clamp
        + grid_monotone_score + docstrings); (f) add a gate in-game dimension OR document the gate
        as pregame-only and the in-game proofs as the judge for in-game (reconcile run_gate
        docstring + SELL-READINESS). Remove dead TIME_EDGES/MARGIN_EDGES + Sequence import.
      - OWNER: OPUS (this is the decisive measured edge -- design + diff review); SONNET applies
        the mechanical parts (imports, EMA sort, feature source).
      - FILES: domains/basketball_nba/ingame_blend_{eval,plive,prior,surface}.py;
        scripts/platformkit/eval_gate/ingame_blend.py; domains/basketball_nba/tests/test_ingame_blend.py.
      - NOTE: disjoint from W1.1/W1.2 (different files) so parallel-safe, but it is the heaviest
        item; give it its own agent and the most review.

W1.4  Tennis in-game recalibrator fit ONLY on the 1-0 state is extrapolated to all multi-set leads.
      - FIX: restrict _recal_ingame to the 1-0 state (sets total==1), or fit/validate per-state;
        qualify the honest_note so 0.043->0.006 is not implied at 2-1/2-0/1-1. Add predict_live
        tests for trailing / multi-set / games-only states.
      - OWNER: OPUS (calibration claim); SONNET applies.
      - FILES: domains/tennis/{predictor.py,predictor_helpers.py}; tests/platform/test_tennis_predictor.py.

W1.5  Ledger beat-gate compares model-Brier-on-all-rows vs close-Brier-on-devig-subset
      (apples-to-oranges); reliability_diagram run_ledger emits MATCHES/BEATS on n=30 while
      calibration_record ABSTAINs (n<50) on the same fixture; concurrent ledger append loses rows
      despite ATOMIC/IDEMPOTENT claim.
      - FIX: compute model Brier on the same masked subset for the beat comparison (both metrics.py
        and reliability_diagram); apply the n<50 abstain gate in reliability_diagram run_ledger and
        guard/remove the BEATS_CLOSE branch; add a cross-process lock (O_EXCL lockfile or
        flock/msvcrt) around the read-modify-write OR document single-writer in the module header
        and SELL-READINESS.
      - OWNER: OPUS (verdict-consistency + concurrency decision); SONNET applies.
      - FILES: scripts/platformkit/ledger/{metrics.py,ledger.py,grade_outcomes.py};
        scripts/platformkit/reliability_diagram.py.

W1.6  Calibration banner hardcodes NBA anchor + literal 'nba ml' for EVERY sport; predict_matchup
      --json carries NO validation_pending/SYNTHETIC flag (suppressible banner is the only place
      it appears); 'last OOS Brier'/'last recalibration' mislabel a synthetic anchor.
      - FIX: thread sport into print_banner (per-sport anchor or honest fallback line); add
        'validation_pending':True + 'calibration_anchor':'SYNTHETIC...' to build_result so the
        flag rides with the number on stdout; rename banner lines to 'frozen synthetic-anchor
        Brier (regression guard, NOT an OOS result)' and 'anchor frozen_at:'. Add a test asserting
        '[SYNTHETIC ANCHOR]' renders for a _synthetic baseline. Update test_calibration_banner
        assertions.
      - OWNER: OPUS (honesty copy); SONNET applies + tests.
      - FILES: scripts/platformkit/{calibration_banner.py,predict_matchup.py,test_calibration_banner.py}.

W1.7  RAG ingest provenance: contextual Haiku path is orphaned (manifest mislabels backend);
      'sha-incremental refresh' is a no-op; dense lane is 1.37GB (34x doc) loaded whole; VAULT_INDEX
      sport-tag orphans cross-sport digests.
      - FIX: either call contextual.stamp_prefixes in index.build before fit_lanes OR make the
        manifest report the ACTUAL backend (template); downgrade/implement refresh and correct the
        docstrings; store the dense lane sparse (save_npz) or cap max_features + correct the
        ~40MB claim; fix the VAULT_INDEX vs 'NBA' sport-tag (tag or union into each sport mask) so
        digests are retrievable. Add a build-path test asserting manifest backend honesty.
      - OWNER: OPUS (provenance-honesty); SONNET applies.
      - FILES: scripts/platformkit/knowledge/{index.py,contextual.py,config.py,retrieve.py,ingest.py};
        knowledge/tests/test_index.py.

GATE-1 (must pass before Wave 2):
  - run_all.py GREEN; run_gate --golden exit 0 with honest verdicts (no BEATS on golden).
  - calibration_record regenerates byte-identically and verdicts match across record/banner/
    reliability_diagram (no n<50 MATCHES/BEATS anywhere).
  - in-game OOS proof exercises the shipping fit_plive/garbage_clamp path; overfit_gap on the
    reported series.
  - All new W1 tests pass per-file. OPUS reviews every diff.

--------------------------------------------------------------------------------
## WAVE 2 -- TEST-HARNESS INTEGRITY (bare-name collisions, per-file pytest, missing tests)
--------------------------------------------------------------------------------
This is a single coherent surface (the platformkit test import convention) plus the missing-test
gaps. Do the import-convention fix FIRST (one agent, whole sweep) because it touches many files;
then fan out the missing-test additions in parallel.

W2.1  Standardize platformkit test imports on the knowledge/ pattern (repo-root sys.path insert +
      fully-qualified `from scripts.platformkit.<pkg>.<mod> import ...`). This single change fixes:
      (a) all 7 eval_gate test files failing under `python -m pytest <file>` from repo root;
      (b) the schema/ledger/metrics bare-name cross-contamination (freshness<->ledger<->eval_gate);
      (c) the duplicate basename test_ledger.py / test_ingame_blend.py / test_freshness* collision.
      - ALSO: rename the duplicated test basenames to be unique (e.g. eval_gate/test_evalgate_ledger.py)
        and/or set importmode=importlib in pytest.ini; rename dm_test.py -> dm.py (helper, not a test).
      - OWNER: OPUS authors the convention + does the eval_gate sweep (subtle); SONNET mirrors to
        freshness/ledger if any remain.
      - FILES: scripts/platformkit/eval_gate/test_*.py + run_all.py; ledger/test_ledger.py;
        freshness/test_freshness_pipeline.py; pytest.ini; eval_gate/dm_test.py + its 3 importers.
      - GATE for this item: `python -m pytest scripts/platformkit/eval_gate/test_gate.py -q` AND
        `pytest scripts/platformkit/eval_gate/test_ledger.py scripts/platformkit/ledger/test_ledger.py`
        (co-run) both PASS from repo root.

W2.2  Add test_gate to run_all.py MODULES (the keystone exit-code contract is currently excluded
      from the one-command proof). Verify it loads under run_all's path post-W2.1.
      - OWNER: SONNET. FILES: scripts/platformkit/eval_gate/run_all.py.

W2.3  Add the MISSING tests (disjoint files -> parallel):
      - predict_matchup.py: --json parses, edge_claimed False, no edge/ROI tokens, --no-banner
        suppresses stderr, unknown-sport exits 0. (NEW: scripts/platformkit/test_predict_matchup.py)
      - sports_predictor_server.py: _norm_sport, _dispatch unknown-tool/sport/non-dict-state errors,
        _ingame_flags whitelist == predict_matchup arg dests, _parse_or_wrap verbatim, edge_claimed
        False, read_edge_map degrade. (NEW: mcp_server/test_sports_predictor_server.py)
      - ledger.append_from_result + _iter_binary_markets (pregame+ingame layers, out-of-range/
        missing skipped, layer_filter, verbatim prob). (extend ledger/test_ledger.py)
      - pretooluse_guard.py: block bare `git push`/`git push origin`/--force/`pytest tests/`;
        do NOT block `git push private`/single-file pytest/non-Bash. (NEW: hooks/test_pretooluse_guard.py)
      - langfuse_trace.py: _check_schema rejects bool-as-number + unknown type; validate_output
        raises path; retry_with_validation; no-op tracer. (NEW: tests/platform/test_langfuse_trace.py)
      - freshness->predict integration: a vintage>=tip row is quarantined in the real read path.
      - cost_ledger.py: parse_run_json defaults, JSONL fallback, empty-input exit 1.
      - OWNER: SONNET per file under OPUS-written specs; OPUS reviews the hook + boundary tests.

GATE-2: every per-file test passes BOTH standalone and co-run from repo root; run_all GREEN incl
        test_gate; new test files green. OPUS spot-checks the hook + MCP boundary assertions.

--------------------------------------------------------------------------------
## WAVE 3 -- HOOK / GUARD CORRECTNESS (pre-activation; security-relevant gating)
--------------------------------------------------------------------------------
Fix the block logic BEFORE PROPOSED-settings.json is ever applied (Wave 7). Single surface
(scripts/hooks/) -> one or two agents.

W3.1  pretooluse_guard.py parsing gaps (each diverges from the invariant it claims to enforce):
      - _is_full_pytest misses `pytest tests/sub/`, `pytest .`, and flag-value targets (-k/-m).
      - _is_push_to_origin defeated by `git -C <dir> push`; false-positives on echo/quoted;
        --force is a naive substring (over-blocks commit msgs, misses -f).
      - cwd-prefix guidance is a loose substring (trailing `cd` passes).
      Tighten all per the audit fix sketches; the W2.3 test must pass.
      - OWNER: OPUS (security logic); SONNET applies. FILES: scripts/hooks/pretooluse_guard.py.

W3.2  posttooluse_warn.py: LOC check no-ops on relative file_path when cwd!=repo root (resolve
      against JSON cwd); GATED_PREFIXES omits scripts/intel; remove unused `os` import.
      - OWNER: SONNET. FILES: scripts/hooks/posttooluse_warn.py.

GATE-3: hooks behave per the W2.3 table on the documented echo-pipe cases; no human-gated edit.

--------------------------------------------------------------------------------
## WAVE 4 -- DEAD CODE / DUP MODULES / NAMING / SMALL DOC FIXES (low-risk, high-parallel)
--------------------------------------------------------------------------------
All disjoint, mechanical, no behavior change to the gate. Fan out widely (SONNET).

W4.1  Reconcile the duplicate eval_gate prototype modules vs promoted production copies
      (eval_gate/ledger.py vs ledger/ledger.py have drifted; freshness_schema/ingame_blend dups).
      Decide one owner (delete prototypes + point eval_gate self-tests at promoted modules, OR
      freeze eval_gate as reference and mark research-only). OWNER: OPUS decides, SONNET executes.
W4.2  Divergent enums/strings to single source: InjuryDelta severity (freshness vs eval_gate
      schemas); config.NO_EDGE_DISCLAIMER vs assemble.NO_EDGE_DISCLAIMER (drop the dead config
      copy); config.BOUNDARY_FORBIDDEN_TOKENS dead (wired in W0.4).
W4.3  Unused imports / dead locals across ~18 files (flake8 F401/F841 list): drop them, incl
      predict_matchup.py:141 dead `s = _norm_sport(sport)`.
W4.4  Dead constants/params: TIME_EDGES/MARGIN_EDGES (handled in W1.3), MIN_BODY_CHARS unenforced,
      PARQUET_ENGINE not passed, drift_check recent/baseline_days unthreaded, _iter_binary_markets
      unused `sport`, degraded_predict_fn dead + false docstring, _BISECT_TOL comment.
W4.5  Shin early-return un-normalized pi (sum-to-1 contract); empty-input nan guards in
      scoring.brier/log_loss; bare `shin` import -> package import.
W4.6  Skill H1 heading mismatches (cross-sport-benchmark '# benchmark', pipeline-rebuild
      '# run-pipeline'); brain-rebuild duplicated --strict; calibration-report NBA module path;
      eval-gate SKILL false '--golden flag does not exist' claim (point at run_gate --golden).
W4.7  Doc-name fixes: vault_knowledge.py cites non-existent scripts/mcp_server/test_boundary.py;
      mcp design docs use sports_predictor vs sports_predictor_server + wrong dir;
      drift_check baseline-window overlap; replay_proof sub-threshold metrics next to
      insufficient_data; drift_log unbounded sentinel; append-only-vs-delete contradiction.
W4.8  Consolidate the three near-duplicate PROPOSED board-calibration docs (hyphen/underscore
      twins) to one authoritative file (DOC; HUMAN confirms deletion).
W4.9  SELL-READINESS typo 'the the-odds-api'; '~25 proof modules' imprecise count;
      reliability_diagram annotation hygiene; lockfile not removed.

GATE-4: run_all GREEN; flake8 F401/F841 clean on sprint files; ASCII-only; hygiene_lint scoped
        green on buyer docs (or allowlist added). OPUS reviews W4.1/W4.5 (behavior-touching).

--------------------------------------------------------------------------------
## REMAINING-WORK WAVES (planned streams; each its own fan-out)
--------------------------------------------------------------------------------

### WAVE 5 -- COMMIT THE RAG (close the "shipped" gap)  [HUMAN-confirm commit]
The offline RAG (scripts/platformkit/knowledge/) and scripts/mcp_server/vault_knowledge.py are
built but UNTRACKED and not gitignored -- one `git add -A` from publishing brain-over-private-vault
code; the "committed LOCAL" claim is false for them.
  - Decide intent: internal-only -> add explicit .gitignore entries; product code -> targeted
    `git add <paths>` + LOCAL commit (verify lancedb/index artifacts under data/ stay ignored).
  - Same call for scripts/run_courtvision.ps1 (untracked+unignored).
  - Register vault_knowledge in PROPOSED-mcp.json; add an index naming the two MCP servers.
  - Update CHANGELOG to mark RAG COMPLETE once W0.4/W1.7 land and recall@5/boundary are measured.
  - OWNER: OPUS prepares the targeted add list + .gitignore diff; HUMAN runs the commit/ignore.

### WAVE 6 -- X2: MLB IN-GAME (second corpus for the in-game architecture)
The in-game architecture is single-corpus (NBA) until MLB lands; mlb_2024 gate slot is an empty
REGISTERED_SKIP_UNTIL_X2.
  - Build domains/mlb in-game blend reusing the NBA blend_prob/smooth_series pure functions over
    the free statsapi.mlb.com pitch feed; MLB golden-state schema (inning/half/score, no seconds
    clock) + gen_golden MLB branch; wire freshness lever to domains/mlb/asof_sp_form (starting
    pitcher) as the MLB freshness signal; evaluate per-inning Brier vs MLB published win-prob on
    Retrosheet as the independent 2nd corpus; freeze a real mlb_2024 baseline and move it out of
    SKIPPED_SLOTS into CORPORA.
  - Fix the stale MLB repricer test (test_metadata_present 'no edge' substring drift) and the MLB
    repricer _honest_note em-dash.
  - DEPENDS ON: W1.2 (run_gate --sport dispatch) and W1.3 (in-game gate dimension / proof judge).
  - OWNER: OPUS architecture + diff review; SONNET implements; HUMAN runs the real-corpus eval
    (real-corpus OOS is HUMAN-RUN-pending -- never a fabricated win).

### WAVE 7 -- BUILD-LOOP ACTIVATION (wire the inert scaffolding)  [HUMAN-confirm apply]
Hooks/MCP/cost_ledger/obs ship inert (no .claude/settings.json; eval-gate is judge by convention
only). Apply ONLY after Wave 3 (hook logic correct) and Wave 2 (tests).
  - Apply PROPOSED-settings.json (use $CLAUDE_PROJECT_DIR / absolute script paths; reconcile
    deny-glob form; resolve the Agent(*) merge note); PROPOSED-mcp.json (pin the basketball_ai
    python; precreate data/results + data/mcp_memory; fix sqlite/memory paths; add vault-knowledge).
  - Fix the doc API errors first: Batch API beta->GA namespace, 100k limit, cache pricing
    referents, missing alert_on_drift.py / _Simulation_Signals.md references (HEADLESS-AND-CRON,
    PROMPT-CACHING-AND-BATCH).
  - Implement the N4 nightly headless gate-run + ledger-row appender (or mark deferred).
  - OWNER: OPUS prepares corrected snippets; HUMAN applies settings/mcp registration.

### WAVE 8 -- BUYER-DOC + CLAUDE.md COHERENCE  [HUMAN-confirm copy]
All buyer-facing prose; HUMAN owns the apply because it is claim-authority copy.
  - README/QUICKSTART/PROOFS/PLATFORM/ONE-PAGER: badge NBA in-game as real-corpus/VALIDATION_PENDING
    with the honest fixture verdict (no-improvement); scope 'every headline number is OOS' to real
    corpora; reconcile MLB in-game number to one generated value; re-point the absent
    vault/_Edge_Maps source citations to committed artifacts (CALIBRATION_RECORD/PROOFS);
    reconcile README headline numbers vs CALIBRATION_RECORD; add the eval-gate/ledger/freshness/RAG
    layer to the architecture + trust + buyer-docs sections.
  - CALIBRATION_RECORD section-2 SYNTHETIC fixture badge symmetry; PROPOSED board-calibration
    in-game row VALIDATION_PENDING flag; nba_2023_24 baseline verdict label (MATCHES vs BEHIND)
    reconcile to dm_p<0.05 -> BEHIND.
  - SELL-READINESS <-> JOB_EVIDENCE_PACKET: resolve the calibration-not-edge vs AST ROI-edge
    "single truth source" contradiction (re-point the authority line at the no-edge rule, or scope
    the AST ROI line as recruiter-context not a product claim); refresh JOB_EVIDENCE_PACKET to
    acknowledge the calibration product.
  - ARCHITECTURE.md/PLATFORM.md stale kernel/domains map (domains/nba->basketball_nba; kernel/sim
    ->sim_framework; drop kernel/api; add eval_gate as the cross-sport JUDGE node, freshness,
    ledger, RAG); fix the three colliding ledger.py doc references.
  - Apply PROPOSED-CLAUDE.md (slim): FIRST verify .claude/rules auto-load (only human-gated-paths
    has `paths:` frontmatter; no loader reads the rules dir; sessionstart_context is inert) -- either
    confirm the harness loads .claude/rules and honors `paths:`, or keep full invariant text inline.
    Fix PROPOSED-CLAUDE predictor-API mislabel (predictor has predict()/to_jd()/predict_live(), NOT
    cohesive_read/live_read), kernel subdir list, intel glob (scripts/intel/** not intel/**); add the
    eval-gate-is-the-judge + LLM-never-authors-a-number + leak-free-checklist + real-corpus-OOS-is-
    human-run invariants that the slim plan currently drops.
  - OWNER: OPUS drafts every edit as a diff against the committed docs; HUMAN reviews + applies.

### WAVE 9 -- MEMORY / VAULT / CODE-ORG REORG  [planned, HUMAN-gated outputs]
Produce the deferred PROPOSED snippets (human-confirm, same pattern as the other PROPOSED-*):
memory reorg, vault reorg, code-org. Plus the Phase-0 tracking artifacts (TASK-LEDGER /
RISK-REGISTER) the CHANGELOG promised, or strike the promise.
  - OWNER: OPUS authors PROPOSED docs; HUMAN applies.

--------------------------------------------------------------------------------
## EXECUTION NOTES (for the Workflow fan-out runner)
--------------------------------------------------------------------------------
- ONE FILE -> ONE AGENT. Pre-assign each bullet's FILES to a single agent; never let two agents
  edit the same file in a wave (avoids the Sonnet concurrent-write collision pattern).
- bash cwd is FLAKY: prefix every command with `cd /c/Users/neelj/nba-ai-system &&` and use the
  basketball_ai python (C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe).
- NEVER run full `pytest` (freezes the box); per-file only. NEVER two concurrent brain rebuilds.
- After each wave, OPUS reviews EVERY diff and runs the wave GATE before releasing the next wave.
- HUMAN-CONFIRM items (Waves 5, 7, 8, 9 applies; any push; key rotation per
  docs/SECURITY_REMEDIATION.md) are NEVER auto-applied by an agent.
- Binding honesty invariants hold throughout: calibration NOT edge; honest market-efficient /
  BSS<=0 / ABSTAIN is a SUCCESS; the LLM authors no probability/number that enters predictions;
  real-corpus OOS is HUMAN-RUN-pending and never a fabricated win; never print the retracted
  numbers (+18.38/0.119/+54/78.11/8.94/54.57) outside explicit retraction framing.
