# S450: MLB starting-pitcher strikeout distribution -- three arms, REPORT ONLY

Build result: 153 passed (13/18/7/8/14/7/2/7/23/15/10/20/9, thirteen files); `contract_preflight` 9/9 PASS over 24 owned files; HEAD EQUAL master (see "FIX 1q" below).

Spec: `docs/evidence/tracking/specs/S450_spec.md`. AMENDMENTS 1-16 are ALL
BINDING; AMENDMENT 16 (`_verdict_s450_1p.md`) is current -- see "FIX 1p" below.
Verifier contract: `VERIFIER_CONTRACT.md` sections A9, B1-B11, Q1-Q9, S1, S2, S4.

Worktree: `C:/Users/neelj/nba-harness-h104` (branch `harness-h104`). FIX 1p
started `git merge --ff-only master`, EQUAL at `fd5211c96`; a mid-lane
re-merge (two unrelated S466/S470 spec-only pushes, no owned/must-not-move
path touched) re-equalized to `40c63c2a3` -- both shas in "FIX 1p" below.
Must-not-move + `S450_spec.md` stay diff-empty. No network, no pod, no
`data/` read.

## Files built

| File | Lines | Role |
|---|---:|---|
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_arms.py` | 181 | PMF adapter, arms A/B/C, PMF scoring primitives |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_manifest.py` | 259 | starter manifest, K-rate pool, strict-int coercion; FIX 1m: `manifest_columns_refusal`; FIX 1n: `_resolve_starters`/`_row_signature`/`STARTER_CONFLICT` (14(b)); FIX 1o: `_row_signature` covers every source column, `MANIFEST_KEY_INVALID` for NaN game_pk/team (15(b)) |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_fit.py` | 290 | per-row scoring, FIT grid fits, real purge, `assert_vintage`, `compute_null_losses`; FIX 1p: the null path guards `pitcher_history_invalid` BEFORE `arm_c_forecast` (16(a)) |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_history.py` | 144 | `pitcher_history_invalid`, mirroring `player_rates_mlb`'s own row selection exactly; FIX 1p: required count columns checked before the empty/dateless early return (16(a)), memo stores+identity-checks the cached df itself (16(b)); FIX 1q: `clear_memo()` added (finding 1) |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_realrun.py` | 247 | `cpcv_derive_fit_rows`, `split_folds`, null-gated C-vs-B verdict, fold-aggregation helpers |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_seal.py` | 253 | sealed-prereg validation, `params_mismatch`, charge-row append, `next_k_family`; FIX 1n: `file_identity`/`raw_file_identity` moved here (14(d) LOC rail) |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_cpcv.py` | 116 | every scored HOLDOUT row via its own `cpcv_splits` path, trained on RAW rows, never manifest rows |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_launch.py` | 164 | CLI arg parsing, `launch_gate_validate`/`launch_gate_charge`; FIX 1m: `resolve_path_targets`; FIX 1n: `launch_gate_bound_check` (14(c)) |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution.py` | 300 | CLI, `build_report` orchestration, JSON output, `--fixtures`; FIX 1n: `main()` calls `launch_gate_bound_check` before `manifest_columns_refusal` (14(c)); FIX 1q: `build_report` calls `clear_memo()` before its `try` and again in a `finally` (finding 1) |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution.py` | 300 | the 13 construct cases; FIX 1o: case 3 rewritten (n=35, clears n>=30, non-hollow, 15(c)); `_history_df` uses `date_range` |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1b.py` | 300 | 18 regressions; FIX 1p: the beta=0 rate-abstain fixture now carries the required count columns (16(a) side-effect, not a finding) |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1e.py` | 133 | 7 regressions, one per AMENDMENT 5 finding |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1f.py` | 172 | 8 regressions |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1g.py` | 277 | 14 regressions |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1h.py` | 229 | 3 FIX 1h + 3 FIX 1i + 1 FIX 1j regression |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1j.py` | 115 | 2 regressions for AMENDMENT 10(a) |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1k.py` | 198 | 7 regressions |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1l.py` | 257 | 21 regressions for AMENDMENT 12 (a)-(f) |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1m.py` | 237 | 15 regressions for AMENDMENT 13; FIX 1n: `fix1m.py:123` gained pre-existing-ledger + gamelogs byte-equality asserts (232 -> 237, finding 2(ii)) |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1n.py` | 121 | 10 regressions for AMENDMENT 14 (a)-(c) -- pitcher-history bad-value constructs, duplicate collapse, `starter_conflict` + reversal-invariance, precedence with pre-existing-ledger byte equality |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1o.py` | 230 | 20 regressions for AMENDMENT 15 -- ambiguous own-row is_pitcher (None/"True"/2/"1"/pd.NA), np.bool_/integral-float64/bool-False controls, missing count columns, bad-row-after-as_of no-effect, `_fit_grid` zero forecast calls, memoisation call-count, corpus-wide exposure, `_row_signature` full-column diff, None-vs-NaN conflict, NaN game_pk/team CLI refusal |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1p.py` | 170 | 7 regressions for AMENDMENT 16 (FIX 1p) -- empty/dateless frame column-first ordering, None-df, null-path zero/one forecast calls, memo stale-key-not-trusted, memo single-recompute; FIX 1q: +2 (memo empty after `build_report` returns, and after it raises) |
| `docs/evidence/harness/S450_PREREG_DRAFT_2026-09-24.md` | 188 | draft, unsealed prereg; FIX 1p: :3 states AMENDMENTS 1-16 cumulative (was stale at 1-13, 16(d)) |

All twenty-two code/test files (9 modules + 13 tests) are under the 300-LOC
rail (three at exactly 300), ASCII-only (checked byte-by-byte).

## Inputs (A9 -- no real corpus opened; these ARE the inputs to this build)

Repo-relative path (never absolute, never an abbreviated basename), byte
size, SHA-256, REGENERATED from disk as the LAST edit via `file_identity()`
(never hand-computed). All 23 recomputed hashes equal the 23 below.
Resolution is LF-normalised for every row (all 23 are TEXT files).

| Path | Bytes | SHA-256 | Resolution |
|---|---:|---|---|
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution.py` | 15181 | `596b61be2b59113cb7181791557d063ab34d23e825419ddd65b21aa8d10b4588` | LF-normalised |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_arms.py` | 7580 | `221e3566b4637c446337698dd6ca5641b456a75faa8a60d69a9e336b7e0534dd` | LF-normalised |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_fit.py` | 14701 | `21536c53e2a45b4757d014e119866867dad9c9747a496360b71a2c381e1f1033` | LF-normalised |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_history.py` | 6675 | `9cde9db4e426a3ab38b52183b6d640f4749c7f14f2ef619f31d0afbf3126a1e8` | LF-normalised |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_manifest.py` | 12520 | `94bd5cdddf26ce3d9f3088dbc1c7b1faf6e871ca1f745ea37eb6321e0721aca7` | LF-normalised |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_realrun.py` | 12164 | `269a8b0f08e2e9e176bc8f6d025945b5d1fe6d78ba74ff798c3fa9a0b95cf076` | LF-normalised |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_seal.py` | 12424 | `486eb56bd571ac259b47dae56c6222d088755fca6ea3634ab1308ac466504ed7` | LF-normalised |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_cpcv.py` | 6341 | `c2ef8026ddf408e6e1b3fd96b62cc81fecc5a2d0475a1a0bf86ab2804ad9a117` | LF-normalised |
| `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_launch.py` | 8488 | `e86aa5a90743b73cf171581c3e4cfd76effb5464ca8325bca38c5470b634cfd2` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution.py` | 14026 | `e26185767f095cf0642669fbbc898ab5bbe76a548bc8bf67ad512385ca890054` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1b.py` | 14113 | `952d4c4fc92a54d604ce71d497ddc821937ad2971d713e993e849ffd40574cb7` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1e.py` | 5999 | `734977e7d4ed5e5e6f38e83d83551caf4546ccd3c3fa83779f6c4caf63c4e723` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1f.py` | 9268 | `667074a1cd6c15ce86922430e6d6d69528f407ae8fd2511ee8104902d1af9244` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1g.py` | 13961 | `b8375a8815d8caa9f909bc6b7999fcce9878fb0ab071e3f37eec5319fb140ad3` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1h.py` | 12513 | `b591556e3ed2c6fb55cbbcbc2c50c7bbe02ed15193f41c2a55c128368ba996fe` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1j.py` | 6034 | `6da18e548a94b9af754f59c4c9babdfecb98f841f690bb183bee30b3fdb115f1` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1k.py` | 10584 | `f192fd5ea1e43fd002beefa8e481d293a583efd109a97110abdb90823c43ee47` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1l.py` | 12415 | `93946c4478c13b10f4b740b6007025d9b49f352e81720471e4ee1745ce386d8e` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1m.py` | 12191 | `60e1a5dbf9aa3a7c5f26041367f18351e03297c8585ab3bdd97465d6309fdab6` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1n.py` | 6115 | `fca0843c4b1baede92a0a1bfaef78262a0fec4b0339e6490ee02f69476ec5e14` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1o.py` | 11246 | `fb56838e3e41d1376a1bfb645ca5c0c7a8f36e52802eb77e52fe3b92bbd5795d` | LF-normalised |
| `tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1p.py` | 7671 | `c0b80074c7db4efe889e64094b43cb0559873798e8f63b3f9bcfc52b427f4ff0` | LF-normalised |
| `docs/evidence/harness/S450_PREREG_DRAFT_2026-09-24.md` | 10232 | `bd40d1c2dd451fb2ce31e382073b10f29e4e77ceda1aebe6db14f6441f3d8abf` | LF-normalised |

(23 files: 9 `.../eval_gate/` modules + 13 `.../eval_gate/` tests + the
prereg draft; paths resolve under `C:\Users\neelj\nba-harness-h104\`.) No
parquet, no probables file, no other data path was opened by this lane.
`data/domains/mlb/player_gamelogs.parquet` is named only as text (fact (f))
-- the orchestrator's real run is the first time this code will touch it.

## Before-condition drift (verified worktree files) / AMENDMENT 1 mapping

Drift: `prop_engine_mlb.py`'s import block spans lines 37-45 (spec said
36-45); `prop_distribution` at line 111; no other cited fact-(a)-(f) line
drifted. `cpcv_tail_metrics.py:69` is `reliability_table` (unedited);
`entry_timing/study.py`'s `cluster_boot_ci` default `(n_boot=500, seed=7)`,
called here with `n_boot=2000, seed=13`. `negbinom_engine.py:78` is
`fit_dispersion_first_half` (team-RUN, not pitcher K) -- confirms
AMENDMENT 1(a)'s narrowed absence claim.

Changed from the original CHANGE/ACCEPTANCE text: **Eligibility** replaces
`_identify_start_opportunities` with `build_start_manifest` (gamelogs-only,
missing/nonpositive `battersFaced` KEPT). **Scoring** replaces
`crps_discrete`/`pinball_at_quantile`/`median_and_pm1` with PMF-native
scorers. **CPCV route**: `cpcv_evaluate_distributional` NOT called;
`assert_vintage` reused as a per-row leak-guard. **Case 10**: missing-BF
KEPT/SCORED with projected exposure. **Case 12**: an implementation
identity test, not a null. Cases 1-9/11/13 reworded for PMF-native scoring.

## Lane 3 / Lane 4 cross-reference (read, not reused for eligibility/scoring)

**Lane 3** (`c9f4bc37a`): hand-rolled EW rate tracker, does not reproduce
the served law -- WORSE on all 3 props, both holdouts
(`props_eval_verdict.json` key `legacy_v1_wave5_ew_vs_baselines`). **Lane 4**
(`df6225f8b`): `dispersion_for` still the fixed, never-fit `{8.0,10,12.0}`. Neither has a memo or an S-row.

## The 13 construct cases

All 13 pass: (1) Arm A reproduces `prop_distribution` byte-for-byte; (2) a
start strictly after T never changes Arm A/B/C's forecast; (3)/(5)
`fit_r_grid`/`fit_beta_grid` identical whether or not holdout rows exist; (4)
a same-date or later opposing row never enters `opp_k_rate_as_of`; (6)-(8)
CRPS/pinball/tail-Brier exact on hand PMFs; (9) `aggregate_arm`/`paired_ci`
report INSUFFICIENT under n>=30; (10) missing `battersFaced` kept/eligible,
abstain-all-three-together and PMF residual-mass abstention hold, a
HISTORY-BACKED missing-BF row IS scored; (11) both-favourable->ACCEPT,
one->SINGLE-WINDOW, neither->NULL; (12) Arm C at beta=0 reproduces Arm B's
`p_over`; (13) strict-int COUNT coercion + ASCII/sort_keys JSON +
`file_identity`'s SHA-256 by hand.

**Disclosure (AMENDMENT 12(g)):** cases (3)/(5) are identical only at the
`fit_r_grid`/`fit_beta_grid` call -- `build_report`'s FIT set itself depends
on holdout B's extent (`cpcv_derive_fit_rows` purges FIT rows in any date
group straddling a holdout, AMENDMENT 5(b)). `cpcv_splits` excludes each
holdout row's own test group + one embargo group from training (AMENDMENT
6(a)). `_fit.py:137`'s `assert_vintage(_vintage_state(row))` is a TAUTOLOGY
(avail = date-1s always < state_ts = date+12h), named as such -- FIX 1o
recomputed this citation (was `:131`) after `pitcher_history_invalid` moved
to the new history module; the verdict's own `:153` assumed no relocation.
Restored FIX 1n sentence: the seal binds 12 keys and does NOT bind K_LINES,
MIN_FOLD_N, SUPPORT_MAX, RESIDUAL_EPS, LOG_FLOOR, the CPCV n_groups/embargo
or the scorer set -- recoverable only through `prereg_commit_sha`; the
exact-equality corpus bound holds only at the sealed 2026-07-02 parquet;
every ingest refresh requires a reseal (S456). Beside 12(b), AMENDMENT
15(a)'s exposure: `pitcher_history_invalid`'s LEAGUE-pool check is
corpus-wide (one bad truthy-is_pitcher row poisons every later forecast,
any player); an own-row-only bad value stays scoped to that one player.

## CLI smoke check + reuse audit

`--help` prints the documented flags incl. `--prereg`/`--charge-ledger`/
`--holdout-b-end`; `--fixtures --out <tmp>.json` re-ran clean this round,
writes valid ASCII JSON, `launch.charged=false`, verdict `INSUFFICIENT`
`r_grid_insufficient` (n well under 30) -- the honest fixture outcome.
Signatures relied on, unedited: `prop_distribution(...)`; `_make_p_over`;
`cpcv_engine.assert_vintage`/`_blocked_indices`/`cpcv_splits`; `reliability_table(..., min_n=30)`; `cluster_boot_ci(..., n_boot=2000, seed=13)`.

## Must-not-move check

No file on the must-not-move list (`prop_engine_mlb.py`, `prop_edge_mlb.py`,
`prop_edge_config.py`, `props_eval_mlb.py`, `props_eval_gate_mlb*.py`,
`props_eval_shootout2_mlb*.py`, `cpcv_distribution.py`, `cpcv_engine.py`,
`cpcv_tail_metrics.py`, `entry_timing/study.py`) was edited -- `git diff
--stat master -- <the 14 files>` is empty, exit 0, against the `master` sha
in "FIX 1p" below; `S450_spec.md` and `player_rates_mlb.py` (read-only
reference for 15(a)'s mirrored mask, never edited) likewise diff-empty.
`git status --porcelain` lists exactly the 24 untracked owned files (9
modules + 13 tests + 2 docs) -- other lanes' landings are in this worktree's merged history, not among its own untracked files.

## Verdict vocabulary

This memo and all artifacts use only ACCEPT/REJECT/NULL/SINGLE-WINDOW/
INSUFFICIENT for verdicts, calibration language only (Q6), no retracted figure.

## Fix history, FIX 1b-1o condensed (full detail in each round's own
`_verdict_s450_1{b,c,d,e,f,g,h,i,j,k,l,m,o,p,q}.md`; FIX 1q above is the current, binding state)

- **FIX 1b** (AMENDMENT 2): ordinal starter never max-IP; common grid
  denominator; real purge; order-independent null.
- **FIX 1c** (AMENDMENT 3): finite ordinals; grid scores `None` never `inf`;
  all-or-nothing K-rate pool.
- **FIX 1d** (AMENDMENT 4): under-floor grid fits carry no scores; rate
  unavailable abstains before any arm.
- **FIX 1e** (AMENDMENT 5): sealed-prereg + ledger-charge gate; FIT rows via
  real `cpcv_splits`.
- **FIX 1f** (AMENDMENT 6, REJECTED): every holdout row via its OWN
  `cpcv_splits` path; complete null denominator.
- **FIX 1g** (AMENDMENT 7, REJECTED): holdout train sets from RAW gamelog
  rows; `next_k_family` fails closed.
- **FIX 1h** (AMENDMENT 8, REJECTED): opp/league K-rates recomputed
  per-path; ledger validates every row first.
- **FIX 1i** (AMENDMENT 9): `holdout_b_end` sealed/CLI-bound.
- **FIX 1j** (AMENDMENT 10, REJECTED): CPCV train path keeps every selected
  row; corpus bound checked before the charge.
- **FIX 1k** (AMENDMENT 11, REJECTED): holdout B's CPCV pool accumulates
  every preceding fold; corpus bound refuses on ANY difference.
- **FIX 1l** (AMENDMENT 12, two-tier): date-free corpus refuses, never
  raises; K/AB pool via `coerce_count`; five named refusals; pre-charge
  `ordinal_column_absent`. 97 passed.
- **FIX 1m** (AMENDMENT 13, two-tier): `resolve_path_targets` (`_launch.py`)
  refuses `path_alias`/`registry_write_refused`, called FIRST in `main()`
  (repro: `--gamelogs == --out == --charge-ledger` used to silently overwrite
  the input, rc 0). `manifest_columns_refusal` (`_manifest.py`) refuses
  `ordinal_column_absent` for any missing `MANIFEST_REQUIRED_COLS` column or
  an empty manifest (repro: `ORDINAL_COL` present, `pitch_strikeOuts` absent
  used to charge then raise `KeyError`). Named refusals asserted by reason in
  fix1h/fix1k/fix1l/fix1m. REAL-RUN EXPOSURE (finding 4, restated beside
  12(b)): `_pool_k_rate` is all-or-nothing -- one non-integral/NaN batter row
  ANYWHERE before a date makes `league_k_rate_as_of` `None` for every LATER
  start, corpus-wide, not per-date-quarantined. 114 passed.
- **FIX 1o** (AMENDMENT 15, two-tier): `pitcher_history_invalid` moved to
  the new `_history.py`, mirrors the consumer exactly (own rows by
  `player_id` alone, league rows via `is_pitcher.fillna(False).astype(bool)`),
  memoised per `(id(df), as_of)` -- guard ordering + memo identity superseded
  by FIX 1p(a)/(b) below. `_row_signature` covers every source column;
  `MANIFEST_KEY_INVALID` names NaN game_pk/team. Case 3 non-hollow. 144
  passed; preflight 9/9 (23 owned files); HEAD=master=`0daa0acd4` EQUAL.

- **FIX 1n** (AMENDMENT 14, two-tier verdict `_verdict_s450_1n.md`): (a)
  `pitcher_history_invalid(df, as_of)` (then in `_fit.py:35`) scanned every
  pitcher row before `as_of` for a non-finite/non-integral
  `pitch_strikeOuts`/`battersFaced` via `coerce_count`, called before every
  arm/grid-fit call -- superseded by FIX 1o(a) below (moved module, mirrored
  mask, `player_id`-aware). (b) `_resolve_starters`/`_row_signature`
  (order-independent starter selection, byte-equivalent collapse,
  `starter_conflict`) -- superseded by FIX 1o(b) below (full-column
  signature). (c) `launch_gate_bound_check` pinned the pre-charge precedence
  (bound check before `manifest_columns_refusal`) -- still current, extended
  by FIX 1o(b)'s `manifest_key_invalid`. Repros confirmed LIVE pre-edit: a
  `pitch_strikeOuts=NaN` row scored instead of abstaining; K `[3,9]` gave
  `y=[3]` forward / `y=[9]` reversed; a date+team-missing corpus gave
  `ordinal_column_absent` not `holdout_b_end_mismatch`. 124 passed
  (13/18/7/8/14/7/2/7/23/15/10, `..._fix1n.py`=10 new); preflight 9/9 (21
  owned files).

## FIX 1p (AMENDMENT 16, two-tier verdict on FIX 1o -- `_verdict_s450_1p.md`: codex sol round 15 REJECT three blockers/one correction; Opus FINAL round 5 ACCEPT WITH CORRECTIONS one correction/four notes, reconciled)

Premise check: all twelve pre-existing test files reproduced 144 passed (13/18/7/8/14/7/2/7/23/15/10/20). Verifier reproductions replayed in isolation before any edit (these row files are untracked with no prior git history to diff against, so the pre-fix logic was replayed verbatim in a scratch script, never the real worktree files): (1) an empty frame carrying date/player_id/is_pitcher/battersFaced but no pitch_strikeOuts gave guard `False` (expected `True`); (2) the null path's poisoned-history row (NaN own-row K) reached `arm_c_forecast` once, `arm_calls=1`, 1 assignment (expected 0/0); (3) a stale `False` cached under a colliding `(id(df), as_of)` key was trusted over the real df's own invalid NaN K.

(a) GUARD BEFORE EVERY EARLY RETURN AND ARM: `_history.py:129` (post-FIX-1q renumbering; was `:109`)'s `pitcher_history_invalid` now checks both required count columns BEFORE the empty-frame/dateless early return, not after -- an empty or dateless frame missing a count column is invalid, never silently `False`. `compute_null_losses` (`_fit.py:269`) now calls the guard before `arm_c_forecast` and `continue`s (omits the assignment) on invalid history. New: 3 regressions (empty frame, dateless-with-columns control, null-path zero-calls) + 1 clean-history control.
(b) IDENTITY-SAFE MEMO: `_history.py:40` (dict; post-FIX-1q renumbering, was `:35`) / `:134-143` (lookup+store; was `:114-128`) stores the cached `df` itself beside its verdict and compares `cached[0] is df` before trusting a hit -- a foreign entry parked under a colliding `id(df)` key is recomputed, never trusted; holding the reference also keeps that id from being freed for the entry's own lifetime. New: 2 regressions (stale-key-not-trusted via a deterministic manufactured collision, not flaky real gc timing; single-recompute control).
(c) A9 LAST: all 23 rows below regenerated via `file_identity()` from disk AFTER every other edit; this table is the final edit; re-read after writing to confirm every row matches disk.
(d) PREREG: `S450_PREREG_DRAFT_2026-09-24.md:3` corrected from the stale "AMENDMENTS 1-13" to "AMENDMENTS 1-16"; its A9 row regenerated after.
(e) DISCLOSED (carried, not fixed this row): a corpus without `battersFaced` passes `manifest_columns_refusal` and is charged, then every forecast abstains `pitcher_history_invalid` -- a certain INSUFFICIENT with a K spent (raised-priority register gap). The bool-False own-row exemption still sums those rows in the consumer; harmless only if two-way batting lines are always 0/0 (unverified on the real parquet). The `fillna` FutureWarning mirrors the consumer's identical line, left as-is by design.

Side effect of (a), fixed in place: `fix1b.py:275`'s beta=0 rate-abstain fixture used a columnless `pd.DataFrame()` as a "history doesn't matter here" stand-in; under the new column-first ordering that frame is itself `pitcher_history_invalid`, flipping the abstain reason. Fixed by giving the fixture's df the two required (0-row) count columns, isolating the rate-unavailability behaviour the test names -- verified failing pre-fix (`pitcher_history_invalid` reason, not `opp_rate_unavailable`), passing post-fix.

Per-file (AFTER FIX 1p): 13/18/7/8/14/7/2/7/23/15/10/20 unchanged from FIX 1o; NEW `..._fix1p.py` = 7. 151 passed total. `--help`/`--fixtures` self-checks clean (`launch.charged=false`, valid ASCII JSON). `contract_preflight` (24 owned files): 9/9 PASS.

`git rev-parse HEAD` at lane start = `fd5211c96b87989e9ad760f2337977ece486b64c` = `git rev-parse master` -- **EQUAL**. A mid-lane `git merge --ff-only master` (two unrelated S466/S470 spec-only pushes, neither touching an owned/must-not-move path) re-advanced both to `40c63c2a30637a665ff7dec7f67d42cea68b7816` -- **EQUAL**; must-not-move + `S450_spec.md` diff-empty, reconfirmed after.

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## FIX 1q (round 16 two-tier verdict `_verdict_s450_1q.md`: codex sol ACCEPT WITH CORRECTIONS two corrections/three notes; Opus tier 2 FINAL ROUND 6 ACCEPT WITH CORRECTIONS one correction/three notes, reconciled -- CORRECTIONS-ONLY, no amendment)

Premise check: the worktree fast-forwarded onto `master` at lane start (to `9991fa53c0dfa51dae0e874c6a78268eebe64188`); a second `git merge --ff-only master` immediately before landing re-advanced both to `8daf8d5afb764fe86cdaf3e41f9c13d7960532ce` (two unrelated S460/S462 spec-only AMENDMENT landings, neither touching an owned or must-not-move path -- `git diff --stat master` empty both before and after). Reproduced the verifier's minimal repro verbatim before editing (`_report_gamelogs(n_a=10, n_b=10)`, `build_report` called 3x via a monkeypatched no-op `clear_memo`, memo inspected after each call, `del df` between calls): call 1 `len(_memo)`=75, call 2=150, call 3=225 -- exact match to the verdict's 75/150/225 (41/82/123 distinct frames pinned).

(a) MEMO CLEARED PER REPORT (finding 1, CORRECTION): `mlb_pitcher_k_distribution.py`'s `build_report` now calls `clear_memo()` (new function, `_history.py:43-50`) before its `try` and again in a `finally`, so nothing survives one report regardless of return path or exception. Post-fix, the same 3-call repro gives `len(_memo)`=0/0/0 after every call. New: 2 regressions in `test_mlb_pitcher_k_distribution_fix1p.py` (memo empty after `build_report` returns; memo empty after it raises, via the existing `cpcv_engine._blocked_indices` monkeypatch sentinel used by fix1b's own raise-path test).
(b) CITATIONS REFRESHED (finding 3, NOTE): `_history.py:40` (the `_memo` dict, unchanged) / `:134-143` (the lookup+store, was `:114-128` before FIX 1q's `clear_memo` insertion shifted the file down 10 lines) / `:129` (the column guard, was `:109`) -- see "FIX 1p" (a)/(b) above, corrected in place.
(c) MEMO LIFETIME DISCLOSED (findings 1/2, NOTE): the memo is cleared per `build_report` call, keyed on `id(df)` -- identity is real only for one report's lifetime, never across reports. It does not detect an in-place mutation of a held frame between calls (verdict finding 2); the pipeline never performs one (the corpus and every `train_df` slice are read-only after scoring starts, no test mutates in place), so this stays a disclosed, unreached gap, not a fix. (d) REGISTER (new gap, carried, not fixed this row): `score_holdout_via_cpcv` (`_cpcv.py:110-115`) builds one boolean-mask copy of the corpus PER HOLDOUT ROW, and `build_report` keeps every scored copy (`train_dfs_by_fold`) for the null -- unrelated to the `_history.py` memo this row fixed. At real scale (thousands of starts x a six-figure-row train frame) this may not fit in laptop RAM. Measure before the real run; share frames per `(path, date)` or recompute inside the null instead of retaining every fold's copy.

Per-file (AFTER FIX 1q): 13/18/7/8/14/7/2/7/23/15/10/20 unchanged from FIX 1p; `..._fix1p.py` 7 -> 9 (+2). 153 passed total. `--help`/`--fixtures` self-checks clean (`launch.charged=false`, valid ASCII JSON, INSUFFICIENT `r_grid_insufficient` on the tiny fixture). `contract_preflight` (24 owned files, `_verdict_s450_1q.md` excluded per the dispatch): 9/9 PASS.

`git rev-parse HEAD` at lane start = `9991fa53c0dfa51dae0e874c6a78268eebe64188` = `git rev-parse master` -- **EQUAL**. Immediately before landing, both re-advanced via `git merge --ff-only master` to `8daf8d5afb764fe86cdaf3e41f9c13d7960532ce` -- **EQUAL**; must-not-move + `S450_spec.md` diff-empty, reconfirmed after.

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED

- No real corpus or real ledger was read/written. Every number here comes
  from hand-built or tiny embedded fixtures/tmp_path files, never a measured
  claim about `player_gamelogs.parquet` or the real launch ledger.
- The null execution is construct-fixtures-only; behaviour under a real
  fold's true opp-rate signal is untested here.
- The seal/ledger/params MECHANISM exists but no sealed prereg or real
  launch charge exists yet; `ledger_unwritable` etc. via injectable stubs.
- `cpcv_derive_fit_rows`/`cpcv_paths_for_holdout` derive train sets
  conservatively from `cpcv_splits`, never the full `cpcv_evaluate` routes.
- Decimal-typed arithmetic (RAILS b) was not used: lam/r/beta/probabilities
  are statistical, not money -- float + `math.isfinite` guards instead.
- The ordinal starter rule, `resolve_path_targets`/`manifest_columns_refusal`
  (FIX 1m), and `pitcher_history_invalid`/`_resolve_starters`/
  `launch_gate_bound_check` (FIX 1n) are construct-only-verified against
  tmp_path fixtures; whether the REAL corpus/prereg/ledger/`--out` paths
  ever alias, fall under `data/registry/`, or carry a real bad history row
  is unknown until the orchestrator's real run.
- The exact-match `corpus_bound_mismatch` needs `--holdout-b-end` EQUAL to
  the refreshed corpus's own max date -- untested against the real
  parquet's actual refresh cadence.
- `launch_gate_validate`/`launch_gate_charge` and the CPCV candidate-pool
  accumulation were exercised only via hand-built 2-3-row fixtures; no
  corpus with more than two holdout folds.
- `pitcher_history_invalid`'s own-row/league-pool split (FIX 1o) and its
  guard-ordering/identity-safe-memo/clear-per-report fixes (FIX 1p/1q) are
  construct-only-verified; whether the REAL `player_gamelogs.parquet`'s
  `is_pitcher` column ever holds a genuinely non-bool value, and whether the
  corpus ever hands the CLI a columnless/dateless train frame, remain unknown
  until the orchestrator's real run. (An "id-reuse rate" for the memo is no
  longer a meaningful unknown: FIX 1q clears it every `build_report` call, so
  no stale entry ever exists to be reused against -- the real-scale memory
  gap that DOES remain is the `train_dfs_by_fold` retention in the FIX 1q
  register, not this memo.)
- FIX 1p's `battersFaced`-missing pre-charge gap (16(e)) is disclosed, not
  fixed, in this row -- carried to the register at raised priority, not
  re-probed against the real corpus.
