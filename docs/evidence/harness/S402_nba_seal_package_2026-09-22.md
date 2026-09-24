# S402: NBA seal package -- reconcile the census, pin every denominator and identity

Row S402, worktree harness-h63 (master-based), 2026-09-22. Documentary tooling only.
No corpus was run, no metric was computed, no seal line was written by this row.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, sections B and Q (Q6 in particular).

## 1. BINDING BEFORE-CONDITION (quoted from master)

### (a) The S382 draft

docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md, 252 lines, CRLF on disk.
Section order (heading line numbers): 1 `# S382 NBA second-corpus preregistration -- DRAFT r1,
UNSEALED 2026-09-21`; 10 `## Hypotheses and signs`; 19 `## Arms and features`; 88 `## Frozen
inputs, folds and embargo`; 117 `## Populations, phases and reporting`; 165 `## Bars and stop
rule`; 193 `## Scope, corpus pins and provenance (filled by the orchestrator before sealing)`;
209 `## Pre-seal eligibility census (counts only; scorer --census-only, scored = false, run
2026-09-21)`; 230 `## Seal`.

Seven TO-FREEZE-FROM-CENSUS placeholders, verbatim with their line numbers:

- 91 `Canonical per-file manifest SHA-256: TO-FREEZE-FROM-CENSUS.`
- 98 `TO-FREEZE-FROM-CENSUS. No archive is read by this document-only lane.`
- 115 `TO-FREEZE-FROM-CENSUS. Do not apply the full-population counts to either subset.`
- 161 `including period support within exposure and D subsets: TO-FREEZE-FROM-CENSUS.`
- 185 `Launch values not yet available: TO-FREEZE-FROM-CENSUS (record at authorized launch).`
- 207 `Unknown complete source/model/version hashes: TO-FREEZE-FROM-CENSUS.`
- 225 `exposure-subset and D-paired denominators: TO-FREEZE-FROM-CENSUS.`

The do-not-seal list (lines 225-251 per the spec; the bullets themselves run 234-251 under
`Do not seal until ALL of the following are resolved:` at 233) holds EIGHT items, in order:
S383 period-stratified scorer extension; the eligibility amendment; the venue-time parser
amendment; the integral NBA state amendment; the S385 provenance memo and D's interpretation;
the census rerun plus pinned manifest and reconciled denominators; the MLB trial verdict and
its auditor S379; the orchestrator's review, charge and launch-K record. Line 252 closes:
`No lane adds a seal. This document remains DRAFT r1 and freezes nothing.`

### (b) The S387 census-only output and the corpus manifest

scripts/platformkit/ingame/baseline_four_arm.py line 289 writes `census.json` on
`--census-only`; the payload is built in baseline_four_arm_eligibility.py:223-224:

    census = dict(scored=False, fields_read=FIELDS_READ + sorted(fields_read - set(FIELDS_READ)),
                  manifest_fields_read=['files'], sports={counts['sport']: counts})

The per-sport counts block (baseline_four_arm_eligibility.py:162-182) carries `sport`, `files`,
`games`, `ticks`, `eligible_ticks`, `eligible_games`, `eligible_ticks_d`,
`model_prob_missing_for_d`, `non_integral_state`, `excluded_ticks`, `excluded_by_reason`,
`duplicate_identical`, `conflicting_duplicate_key`, `high_conflict_game`, `excluded_games`,
`per_file`, `per_game`, `state_transition_ticks`, `games_per_first_tick_utc_date`,
`games_without_parseable_tick`, `eligible_games_per_first_tick_utc_date`, `folds` (each
`dict(date, train_games, train_ticks, warmup)`, lines 153-159), `warmup_folds` and
`eligible_games_at_least_30`. Per-game entries carry `unique_keys` and `conflicting_keys`.

The real corpus manifest was READ ONCE for its shape only (not run, no row read):
`C:\Users\neelj\nba-ai-system\data\cache\ingame_grade_joined\nba_checkpoints_r1\manifest.json`
is 223,031 bytes, top-level keys exactly `['files']`, 1,593 entries, first key
`00529e50f4e00177b57bd4a224dcfb50a8e9aff254bd8dbbec61dc0f54395a78.jsonl` mapped to a 64-character
digest; the first bytes are `{"files":{"00529e50...jsonl":"e939cdfd...` -- canonical compact,
sorted keys. The converter's convention is stated in
docs/evidence/harness/S360_nba_joined_corpus_2026-09-21.md line 67: "manifest.json with
canonical compact `{"files": {name: sha256}}`, and census.json."

### (c) The S377 readiness census

scripts/platformkit/ingame/nba_corpus_readiness.py `main` takes `--corpus-dir` (required),
`--exposed-ids` (optional CSV with a game_id header) and `--out` (required), refuses an output
path inside the corpus directory, and writes atomically (tempfile, flush, `os.fsync`,
`os.replace`). Its census keys (lines 251-282) include `files`, `bytes`, `file_bytes`,
`manifest`, `manifest_sha256`, `converter_manifest`, `records`, `ticks`, `refused_ticks`,
`future_records`, `unique_keys`, `identical_duplicate_keys`, `conflicting_duplicate_keys`,
`refusals`, `games`, `post_final_ticks`, `close_not_max_games`, `model_coverage`, `per_game`,
`periods`, `exposure`, `eligible` (`all` and `live`, each `games`/`ticks`), plus
`first_tick_dates`, `date_folds` and `embargo`. `manifest_sha256` is the SHA-256 of
`json.dumps({"files": manifest}, sort_keys=True, separators=(",", ":"), allow_nan=False)`.

### (d) The sealed MLB prereg's seal line

docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md, `## Seal` section: "The final line of
this file is SHA256 followed by the lowercase hexadecimal digest of all bytes above that line
after CRLF-to-LF normalization; the separator newline belongs to the hashed prefix." Its last
line is `SHA256: 18b45d85...` (64 hex characters). The sealed text is a NEW file; the draft
stays unsealed. S402 writes NO such line; the orchestrator adds it.

### (e) The S392 disposition and the S385 finding

docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md line 4: "Arm D remains
DESCRIPTIVE ONLY." Its identity inventory states, verbatim: U "historically 1,593 games /
465,249 ticks"; S "historically 797 games / 232,951 ticks"; V "historically 796 games"; H "S58
trial B's 1,593 checkpoints". Its recommendation is option (iii), none of U as untouched
validation. S385 (docs/evidence/harness/S385_S86_MODEL_PROVENANCE_SCOUT_2026-09-21.md) states:
"Every constant is UNKNOWN; arm D is not untouched out-of-sample on the NBA corpus."

### (f) S395 AMENDMENT 1(c)

docs/evidence/tracking/specs/S395_spec.md lines 48-50: "The S382 seal package must pin, in
these exact line formats, ELIGIBLE_GAMES_SHA256: <hex>, ELIGIBLE_GAMES: <n>,
S86_EXPOSED_GAMES: <n>, S58_SCORED_GAMES: <n>, plus the S387 census denominators; until it
exists the NBA auditor's tests use a synthetic sealed prereg carrying those lines."

## 2. Two spec conflicts, stated rather than hidden

1. S402_spec.md line 25 lists the CLI without any path to the S392 document, while line 29
   requires `S86_EXPOSED_GAMES` / `S58_SCORED_GAMES` to be "quoted from the S392 document (not
   recomputed)": a required input had no flag. Resolved additively with a REQUIRED
   `--disposition <path>`; the counts are quoted from its identity bullets S and H by anchored
   patterns that must match exactly once, and zero or several matches is a counted refusal.
2. Line 33 requires the report to mark each do-not-seal item "CLOSED with the evidence path, or
   OPEN", but no flag supplies those paths. Resolved additively with a repeatable
   `--closed <index>=<evidence-path>`; CLOSED requires an existing FILE (contract A7, FIX 1b
   item 4), and an item with no entry is OPEN.

Placeholder 5 (draft line 185, launch values) is derivable from no census: it stays OPEN unless
`--pin launch_values=<text>` supplies it. That is the spec's own path, not a silent fill.

## 3. What was built

- `nba_seal_package.py` (300 lines) and `nba_seal_package_checks.py` (300 lines) under
  `scripts/platformkit/ingame/`: the CLI and the assembly; draft and disposition parsing,
  corpus identity scan, reconciliation.
- `tests/platformkit/ingame/test_nba_seal_package.py` (293 lines): 12 construct tests.
- `tests/platformkit/ingame/test_nba_seal_package_pins.py` (298 lines): 25 tests from FIX 1b,
  1c and round 3; this companion exists because the first file is at the <= 300 rail.

Behaviour, matching CHANGE items 1(a)-(d):

(a) Reconciliation compares `files`, `games`, `ticks`, `unique_keys`, `eligible_games`,
`eligible_ticks`, `excluded_post_final` (readiness `post_final_ticks` against census
`excluded_ticks` AND `excluded_by_reason.post_final`), `corpus_bytes` and `manifest_sha256`
across the S377 readiness JSON, the S387 census and the corpus itself. Any disagreement exits 3
with the differing keys listed and NO text. Counts are strict ints; a missing field is not a zero.

(b) `ELIGIBLE_GAMES_SHA256` is the SHA-256 over the sorted eligible identities joined by LF, read
from the corpus `game_id` field by an anchored pattern -- rows are never parsed as JSON, so no
probability and no outcome value is read. The manifest digest is ONE serialization of
`{"files": mapping}`; the byte total, fold counts, period support and S392 counts are pinned too.

(c) A COPY of the draft is filled, each placeholder mapped to exactly one entry of a DECLARED
anchor table; zero or several matches is UNMAPPED and stays visible. The appended block carries
the S395 line formats, the ten census denominators as `CENSUS.<key>` plus the one `NBA_CENSUS:`
line, each pin and `ARM_D_STATUS: DESCRIPTIVE_ONLY (S392 disposition)`. The report lists every
placeholder (line, anchor, key, status) and every do-not-seal item verbatim, CLOSED or OPEN.

(d) With any placeholder, do-not-seal item or required pin still open the tool exits 4 and writes
NO text; the report still lands. `--allow-open` writes a text marked `STATUS: DRAFT -- OPEN ITEMS
REMAIN; NOT SEALABLE.`. Both files are written atomically; input text is folded from CRLF/CR to
LF before anything is hashed; and the assembled text is refused if any line of it is a seal line.

## 4. Evidence

- `python -m pytest tests/platformkit/ingame/test_nba_seal_package.py -q -p no:cacheprovider`
  -> `12 passed in 3.81s`; the same command on `..._pins.py` -> `25 passed in 7.82s` (round 3).
- `python -m scripts.platformkit.ingame.nba_seal_package --help` -> exit 0 (module form; the
  direct path form has never imported `scripts.platformkit` and this round did not change it).
- Line counts 300 / 300 / 293 / 298 (memo below 300), all ASCII, all <= 300.
- `contract_preflight` over the five files (--base master, --spec S402_spec.md) -> 9 PASS, 0 FAIL.
- The first test consumes the REAL ROW fixture end to end and
  `test_landed_draft_placeholders_all_map` runs the LANDED S382 draft through the anchor table:
  placeholders at lines 91, 98, 115, 161, 185, 207 and 225 all map; do-not-seal parses to eight.

## 5. Defect classes pre-empted

Digest serialized once; a placeholder is never silently left or substituted (UNMAPPED and OPEN
are reported and block the write); counts strict int; no probability or outcome value read from
the corpus; LF folding before any hash; identities sorted so file and row order cannot move the
digest; an identity in two files is refused, never merged; every `except` raises a counted
refusal; CLOSED requires an existing evidence FILE; writes are atomic.

## 6. FIX 1b (2026-09-22; Opus ACCEPT WITH CORRECTIONS + codex sol REJECT closed)

Six findings closed and still in force, each held by the named test. (1) The four `REQUIRED_PINS`
are required: a missing one joins `missing_pins` and blocks, and `corpus_pins` carries the
identity pins only, never `launch_values` (`test_missing_required_pin_blocks_ready_to_seal`,
`test_launch_values_is_not_a_corpus_pin`). (2) A period key set other than `checks.PERIODS`
(quoted from `nba_corpus_readiness.py:21`) is a counted Stop `readiness_periods_keys` listing the
keys present (`test_period_support_must_carry_exactly_the_five_periods`). (3) AMENDMENT 2(a):
`PRIMARY_GAMES_SHA256`, `PRIMARY_GAMES` and `WARMUP_GAMES` join the frozen block; a game's fold is
its first-tick UTC date and the primary set is the eligible games whose fold is not `warmup: true`
(rule quoted from `baseline_four_arm.py:81` and `baseline_four_arm_eligibility.py:153-159`); the
draft's own `1,570`, stated twice and parsed with `checks.POST_WARMUP`, must agree or the tool
STOPs naming BOTH numbers (`test_primary_set_excludes_exactly_the_warm_up_fold_games`,
`test_post_warmup_game_count_must_match_the_draft`). (4) A pin value must be printable and
`--closed` evidence must be an existing FILE, never a directory
(`test_pin_value_with_a_line_break_is_refused`, `test_closed_evidence_must_be_an_existing_file`).
(5) AMENDMENT 2(d): the census echo is `CENSUS.<key>`, never `CENSUS_ELIGIBLE_GAMES:` which an
unanchored `ELIGIBLE_GAMES` pattern would match twice, and `_block` refuses `duplicate_pinned_line`
(`test_every_pinned_line_is_unique_by_name`). (6) AMENDMENT 2(e): a missing input is a counted Stop
and a Stop keeps the reconciliation table
(`test_missing_input_file_is_a_counted_stop_with_the_report`,
`test_a_stop_before_reconciliation_writes_a_report_without_a_table`).

## 7. FIX 1c (2026-09-22; Opus round-2 ACCEPT WITH CORRECTIONS, codex sol round-2 REJECT and the
S395 auditor's round-3 verdict)

Nine findings closed. Every BEFORE below was reproduced by loading a COPY of the candidate with
the fixed lines reverted (the copy lives in a scratchpad, never in the worktree) and running it
on the same synthetic inputs.

1. **The primary population is reconciled against the census (Opus 1, sol 3).** BEFORE the primary
   set was re-derived from the corpus alone, so a game whose first-tick date was absent from
   `census.folds` was silently PRIMARY: folds `[2026-03-14 warmup, 2026-03-15]` against a
   three-date corpus produced `READY_TO_SEAL` with `FOLDS: 2`. AFTER `checks.primary_games`
   returns the FULL `{fold date: warmup}` map and refuses `game_fold_date_not_in_census_folds`,
   `eligible_games_per_date_differs` (against the counts the cross-check master emits at
   `baseline_four_arm_eligibility.py:180-181`) and `census_warmup_folds_differs`; `FOLDS` and
   `WARMUP_FOLDS` are read off that one validated map
   (`test_a_corpus_date_absent_from_the_census_folds_is_refused`,
   `test_the_per_date_eligible_counts_must_equal_the_census`,
   `test_census_warmup_folds_must_equal_the_warmup_flags`).
2. **The duplicate-name refusal spans the filled draft (Opus 2).** BEFORE `_block` built its name
   set from the appended block only, so a draft body line `ELIGIBLE_GAMES: 99` survived beside the
   emitted `ELIGIBLE_GAMES: 3`; AFTER the FILLED draft joins the set, narrowed in round 3 item 2
   to the emitted names (`test_a_draft_body_line_cannot_shadow_a_pinned_name`).
3. **The seal-line guard is whitespace-tolerant (Opus NOTE 3)**: an indented seal line in the
   draft stops the run, and round 3 item 5 widened the guard to `checks.SEAL`
   (`test_a_seal_line_in_the_draft_is_refused`).
4. **Only declared pins exist (Opus NOTE 4)**: a name outside `checks.REQUIRED_PINS` plus
   `launch_values` is refused `unknown_pin` (`test_an_undeclared_pin_name_is_refused`).
5. **Pin halves are validated UNMODIFIED and the guard runs over the bytes to be written (sol 1).**
   BEFORE `_pairs` stripped both halves and never checked the NAME, so `launch_values=ok<LF>` was
   accepted and a name carrying a CR emitted `PIN auditor<CR>SHA256: abc: <hash>`: the old guard
   split the RAW text on LF and returned False while the same bytes normalized to a real
   `SHA256: abc: ...` line. AFTER no strip, the name must match `checks.PIN_NAME`
   (`[a-z][a-z0-9_]{0,31}`) and the value `checks.PRINTABLE` (`[ -~]+`, so every character below
   0x20 and 0x7f is refused), the fill path uses the same rail, and the final guard runs over the
   LF-normalized `splitlines()` (`test_a_pin_name_and_value_are_validated_unmodified`, 5 forms).
6. **A pin is resolved with git, not by shape (sol 2).** BEFORE `0000000` passed the hex-shape rail
   although `git cat-file -e 0000000^{commit}` exits 128. AFTER `_resolve` runs `git -C <this
   repository> cat-file -e <value>^{commit}` then `git rev-parse <value>^{commit}` -- round 3
   item 3 requires the value to BE a sha first -- refuses `pin_not_a_commit` (counted, exit 3,
   no text) and emits the canonical FULL hash (`test_a_fabricated_hex_pin_is_not_a_commit`,
   `test_a_real_commit_resolves_to_its_canonical_full_hash` against this worktree's own history).
7. **The corpus timestamp goes through the scorer's parser (sol 3).** BEFORE an anchored regex
   accepted only `...+00:00`, so `2026-03-14T23:30:00.12345-05:00` matched NOTHING while the
   scorer reads it as UTC date 2026-03-15. AFTER `checks.TS` captures the raw `ts` text and
   `checks.identities` parses it with `baseline_four_arm_features.timestamp` (the scorer's own
   `parse_venue_time` wrapper, called as `baseline_four_arm_eligibility.py:26-30` does), keeping
   the MINIMUM instant per game (`test_an_offset_timestamp_lands_on_the_scorer_utc_date`).
8. **No output may alias an input or the other output (sol 4).** `--out X --report X` and `--out
   <the draft>` are `path_collision`, counted, exit 3; round 3 item 1 moved that guard ahead of
   every write (`test_output_paths_may_not_alias_each_other_or_an_input`).
9. **The S395 auditor's one census line (S395 round 3).** The ten S387 census values are also
   emitted as a single `NBA_CENSUS: <compact JSON>` line (sorted keys, no spaces, serialized once)
   beside the `CENSUS.<key>` echoes and joins the uniqueness check
   (`test_the_nba_census_line_parses_back_to_the_ten_keys`).

To hold the <= 300 LOC rail, `manifest_files` moved to its only caller's module (as
`_manifest_files`), `_unique_keys` folded into `_sport_census`, `_refuse_constant` into `_load`
and `_source` into its three call sites: both modules are new in this row, nothing else imports
them, and no behaviour moved with them. Exit codes are unchanged (0, 3, 4) and no seal line is
written on any path.

## 8. Round 3 corrections (2026-09-22; Opus round-3 ACCEPT WITH CORRECTIONS)

Five corrections, each with a pinned test; every BEFORE is read off the pre-fix line, not re-run
here. (1) DATA LOSS: the `path_collision` guard sat in `package` (:207) and `main`'s handler then
wrote the report to the aliased path, so `--report <the draft>` returned 3 and destroyed the draft
(the round-3 verdict measured 1990 bytes replaced by 187). It is hoisted into `main` ahead of the
try, prints to stderr and writes NOTHING (`test_output_paths_may_not_alias_each_other_or_an_input`
asserts identical draft bytes for `--out` and for `--report`). (2) `:199` made every prose line a
pinned line, so `Note: alpha` / `Note: beta` refused `duplicate_pinned_line`; names are now
intersected against the EMITTED set (`FROZEN_ORDER`, `CENSUS.*`, `NBA_CENSUS`, `SOURCE_*`, `PIN *`,
`UNSEALED`), so prose passes and a shadowed emitted name still refuses (both asserts in
`test_a_draft_body_line_cannot_shadow_a_pinned_name`). (3) `<v>^{commit}` peels any revision, so
`--pin scorer=master` / `HEAD` / `HEAD~1` resolved to a MOVING sha; a value must match `checks.SHA`
= `[0-9a-f]{7,40}` before any git call, else `pin_not_a_sha`
(`test_a_pin_that_is_not_a_sha_is_refused`). (4) Declared per-date counts are `strict_int`-ed, so
`1.0` cannot reconcile with `1` (`test_float_count_is_refused`). (5) The seal guard is
`checks.SEAL` (`\s*sha256\s*:`, case-insensitive), at least as wide as the reader's `rb"^SHA256:
([0-9a-f]{64})"` (`test_a_seal_line_in_the_draft_is_refused`, 3 forms).

## 9. NOT VERIFIED

- The tool has NEVER been run on the real corpus, the real census or the real readiness JSON.
  Every number in every test is synthetic except the quoted S392 counts and the REAL ROW shape.
  The orchestrator runs it from the repo root after S387 lands and the census is re-run.
- S387 is NOT fully landed on master: baseline_four_arm_eligibility.py line 124 still refuses a
  non-int outcome, which S387 AMENDMENT 2 says is wrong for a corpus storing `outcome` as 1.0.
  Until that lands a real census reports `eligible_ticks` 0 and the reconciliation here would
  STOP. Not this row's file and not fixed here.
- No seal line was produced and no sealed text was run against the S347 seal procedure. The real
  corpus manifest was read for its shape only; the tool does not re-hash corpus files against it.
- The per-period support comes from the S377 readiness census (the S387 block carries none) and
  its key set is quoted from `nba_corpus_readiness.py:21`; neither was checked against a real
  readiness JSON or a real S387 census.
- No test covers a corpus larger than three files or a draft revision other than r1; the anchor
  table is exact and will refuse, not guess, on any other draft text.
- Nothing here measures, compares or ranks any arm. No calibration result is claimed.
- `PRIMARY_GAMES_SHA256` has NEVER been computed over the real corpus, and the draft's stated
  1,570 has NEVER been compared against a real census; the tool STOPs rather than guess.
- The fold rule is REPRODUCED from the scorer, not imported: no test binds the two, and the key
  `eligible_games_per_first_tick_utc_date` is read from a SYNTHETIC census only; no real S387
  census was opened to confirm the writer still emits it.
- The timestamp parser IS imported from the scorer now (`baseline_four_arm_features.timestamp`),
  but no real corpus row was parsed with it here, and no test binds this module's refusal
  counting to the scorer's own row selection.
- `_resolve` calls `git` in the repository that holds the tool. It was exercised against THIS
  worktree's HEAD only; behaviour in a detached or bare checkout, or with a pin naming a commit
  that exists only in another remote, is untested.
- `duplicate_pinned_line` and `NBA_CENSUS` are proved only against synthetic text; no S395
  consumer pattern was run against a produced text.

## Post-S417 re-audit of the landed MLB release (2026-09-23 16:5xZ, orchestrator; S417 AMENDMENT 6 requirement)

S417 landed at d2ae4b4f3 (widened four_arm_output_audit_checks.py additively for B_lag). The LANDED S379 auditor was re-run over
the ONLY real four-arm output (S347 attempt 1) from the repo root on master:
python -m scripts.platformkit.ingame.four_arm_output_audit --out-dir data/cache/ingame_grade_joined/_trials/S347_four_arm_attempt1
  --prereg docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md
  --manifest data/cache/ingame_grade_joined/_manifests/manifest_canonical_mlb_segmented_r3.json
  --corpus-dir data/cache/ingame_grade_joined/mlb_segmented_r3 --ledger data/cache/eval_gate/backtest_fwer.jsonl
  --audit-out data/cache/ingame_grade_joined/_trials/S347_four_arm_attempt1_AUDIT_postS417.json
RESULT: 22 PASS / 1 NOT_AUDITABLE (C.means: saved summary has no per-arm mean fields for some cells) / 0 FAIL, verdict_release
True -- check names and statuses IDENTICAL to the landed _AUDIT_final.json (23 checks). The ledger was read only: sha256 prefix
0b40b55d08eba4dc and 19 rows before and after. The MLB release is unchanged by S417.
RECORD OF A WRONG PATH: two earlier invocations with --manifest data/cache/ingame_grade_joined/_segmented_r3_manifest.json (the
path the seal runbook draft guessed; that file has keys generated_at / root / suffix / sports, not the per-file 'files' map)
returned 11 FAIL (A.manifest and everything downstream) on master AND on the pre-S417 checkouts 22f80c370, c2f478131 and
32c9915f9 -- the failure was the manifest argument, not any landed commit. The sealed prereg pins the canonical per-file
manifest at SHA-256 f3b5e3f9364f7627404cac7e8f51ffbf95fa56ffc72e20020629958aac3f72b1, which is the _manifests/ file above.
