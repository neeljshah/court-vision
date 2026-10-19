# S448 -- MLB served ratings frozen at 2026-07-12: walk-forward vs frozen Elo (REPORT ONLY)

Worktree: harness-h103. Candidate HEAD (full sha, `git rev-parse HEAD`, this fix 1q
session, after `git merge --ff-only master`) and verification base (full sha,
`git rev-parse master`, same worktree, re-measured as the LAST step before
landing) print the SAME sha this round: `a57c1af7d342bd5edb53162f5759794c2c971e60`
(the fast-forward pulled in six unrelated `docs/evidence/tracking/specs/*.md`
files only) -- CORRECTION (fix 1p, AMENDMENT 15(b)):
prior rounds' prose here claimed the two printed shas differed while printing the
same string twice and citing a stale `60d6de4cd..f13ae4e1` two-commit gap; that
narrative is removed. The correct, current statement is the equality above: this
worktree is fast-forwarded to master and no commit has been made here (no commit;
no push; no network; no write under any data/ directory; no parquet file was
read this session -- the two parquet rows in the A9 table below are CARRIED
FORWARD from an earlier fix, not re-read this session, see NOT VERIFIED). All
six must-not-move files below were
independently re-hashed (LF-normalised) against `git show master:<path>` this
session -- every one MATCHES: `domains/mlb/refresh_ratings.py`,
`domains/mlb/predictor.py`, `domains/mlb/ingest_manifest.py`,
`scripts/platformkit/predictor_jd.py`, `scripts/platformkit/proof_mlb/beat_the_close_ml.py`
and `domains/mlb/ingest_current.py` were only read, never edited.

## Before-condition, measured directly in an earlier fix (carried forward)

Read via a scratch script (`pyarrow.ParquetFile` metadata + a single-column scan of
`date` only): `C:/Users/neelj/nba-ai-system/data/domains/mlb/games_current.parquet`
(the same file the spec names on master 03f9cf31e): size_bytes 164496, mtime
2026-07-16 13:59:04 UTC (08:59 local -0500), num_row_groups 1, num_rows 11179,
schema_names event_id/date/season/home_team/away_team/home_runs/away_runs/
target_home_win/game_seq/home_league, date column min 2022-04-07 max 2026-07-12.
This reproduces the spec's BINDING BEFORE-CONDITION (a) exactly.
`domains/mlb/ingest_manifest.py:43` sets `IngestSource("games_current", LEAK_PRE_GAME,
sla_minutes=1440, ...)`; as of 2026-09-24 the corpus is ~65 days past that 1-day SLA.

## How the frozen and walk-forward snapshots are built

Both snapshots replay the SAME leak-free update rule, imported unedited from
`beat_the_close_ml.py` (`_K=6.0`, `_HFA=24.0`, `_INIT=1500.0`). FROZEN:
`frozen_ratings()` calls `final_ratings()` ONCE on the as-of slice (date <= asof).
WALK-FORWARD: `_walkforward_ratings_before(games, date_d)` calls it on the as-of
slice strictly before `date_d`. Both come from `clean_games_asof()` (5(a)/8(b)):
*games* is converted to per-row RECORDS and date-sliced BEFORE any pandas
DataFrame is built. AMENDMENT 11(a) (this fix): row-level validation ITSELF
(event_id/date/team/game_seq/score) now runs entirely PER RECORD while scalar
types are still intact, and a DataFrame is built ONLY from the accepted records --
so a malformed sibling record WITHIN THE SAME slice (e.g. a float `game_seq`
alongside a valid int one, both dated before the same cutoff) can no longer
coerce or refuse the valid record via a shared pandas column. `_main()`'s
NO-OVERRIDE (default) branch calls `read_games_parquet(refresh_ratings._FROZEN,
refresh_ratings._CURRENT)` (10(a)) -- the SAME two source paths the served loader
uses, imported unedited, read via per-file records concatenated as Python lists.

## Row-level validation (AMENDMENT 1(a)/(b), extended by 5/6/8/9/11)

`mlb_frozen_vs_walkforward_elo_io.py` holds `validate_schema()`, `clean_games()`
(whole-corpus bookkeeping), `clean_games_asof()` (as-of training slice) and
`clean_games_window()` (9(c): the scoring window's own scope), all sharing NEW
`_clean_records()` (11(a): validates a LIST OF RECORD DICTS directly -- event_id,
date, team, game_seq, score checks all run on the raw dict, duplicate detection
via `collections.Counter` over valid string ids -- and constructs the returned
DataFrame only from the accepted records at the very end; replaces the prior
DataFrame-first `_clean_rows()`/`_normalize_dates()` pair). Reasons:
`invalid_event_id`, `duplicate_game_key`, `invalid_date`, `invalid_team`,
`invalid_game_seq`, `missing_final`, `tie_or_malformed`. `_int_like()` (game_seq)
accepts non-boolean `int`/`np.integer` ONLY (5(c)). `_finite_nonneg_int()` (scores)
refuses ANY non-scalar via `pd.api.types.is_scalar()` (9(b)), then `bool`/`np.bool_`
(6(d)), then catches `OverflowError` during `float()` conversion and refuses
(11(b): `10**1000` etc. fail closed, never crash). `_is_missing_scalar()` (8(a))
replaces raw `pd.isna()` in control flow. `_valid_date_value()` strips a
timezone-aware Timestamp's tz (8(c)). The optional Kalshi value is selected by
`..._kalshi.select_kalshi_mid()` (`price`/`yes_mid` alternative, 9(d); an
overflowing probability also caught and counted `kalshi_non_finite`, 11(c), and a
bool/string probability refused before conversion, 13(c)): `kalshi_yes_mid` always
reported; `kalshi_mid_home` only when `side` validates (6(a)). NEW
`..._validate.py` (13(a)): `pre_slice_refusal()`/`filter_records()` validate a
record's schema and date BEFORE `clean_games_asof()`/`clean_games_window()` ever
date-compare it, so a non-mapping or mis-dated record refuses instead of silently
failing the cutoff test; `_finite_nonneg_int()` (scores) now also requires
`_int_like()` (13(b)): a float or numeric string refuses, never coerced.

## Fix history (1b - 1q), grouped to stay under the memo's 300-line cap

**1b-1d** (AMDT 1-3): non-final/tied/negative/non-numeric refused before either replay; strict schema + order-independent duplicates; bootstrap fails closed every draw+bound; strict id/date typing; refused-row date tiebreaker; `window_end` from clean+refused rows. 21 tests.
**1e-1g** (AMDT 4-6): `home_team`/`away_team` non-blank and DISTINCT; duplicate validation as-of/per-snapshot (NEW `clean_games_asof()`); Kalshi selection real (NEW `..._kalshi.py`, yes/home mid split + 4 counters); non-dict capture rows and bool scores refused. 29 tests.
**1h-1j** (AMDT 7-9): Kalshi tie-break gained side+ordinal; event_id validated before any lookup/hash; container-valued scores refuse; `clean_games_asof()` record-first; tz-aware Timestamps normalise; NEW `read_games_parquet()`/`clean_games_window()`; Kalshi `price` alt. 15 tests.
**1k-1m** (AMDT 10-12): default ingress branch corrected to `read_games_parquet(_FROZEN, _CURRENT)`, not `load_combined_corpus()`; same-slice malformed-sibling coercion fixed (NEW `_clean_records()`, per-record); schema check per-record, never first-record-only. 6 tests.
**1n-1p** (AMDT 13-15): schema/date validation before slicing (NEW `..._validate.py`); run totals int-only (`_int_like`); Kalshi bool/str refused before `float()`; dual yes_mid/price fields validated independently (NEW `_validated_numeric()`); refusal event_id normalised JSON-safe (NEW `json_safe_event_id()`). 16 tests.
**1q** (Opus tier-2 final-pass correction, not a numbered spec amendment): NEW `validate_window()` in `..._validate.py` refuses `frozen_asof` not strictly before `window_start` (`frozen_asof_not_before_window`) and a timed `window_start` (`window_start_not_midnight`), called as `score_window()`'s own `start`; `verdict_of()` moved to `..._validate.py` (`min_dates` an injected parameter, default 5, not a module-coupled constant) to hold the main module under the 300 LOC cap. 2 tests.
Full reproductions for rounds 1b-1p are preserved in this worktree's prior
verdict files (`_verdict_s448_1c.md` .. `_verdict_s448_1p.md`); this round's
binding verdict is `_verdict_S448_opus_final.md`; see FIX 1q below.

## 95 cases across five test files, all CONSTRUCT

Per-file (repo rule: never the whole suite), all five commands recorded in full,
never shorthand:

`python -m pytest tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo.py -q -p no:cacheprovider`
= `17 passed`

`python -m pytest tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1b.py -q -p no:cacheprovider`
= `15 passed`

`python -m pytest tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1c.py -q -p no:cacheprovider`
= `22 passed`

`python -m pytest tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_kalshi.py -q -p no:cacheprovider`
= `23 passed`

`python -m pytest tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1n.py -q -p no:cacheprovider`
= `18 passed`

(95 total: base 17 + 1b 15 + 1c 22 + kalshi 23 + 1n 18 (16 pre-existing + 2 NEW
this fix), all 93 pre-existing unchanged in behaviour -- see FIX 1q below.)

n = 95 (CONSTRUCT) -- eye check = n/a (S-row); reproduction = rerun the same five
pytest commands above.

## A9 identities (regenerated LAST, fix 1q, candidate HEAD == verification base `master`, both `a57c1af7d342bd5edb53162f5759794c2c971e60`)

Text files hashed as LF-normalised bytes (`read_bytes().replace(b"\r\n", b"\n")`); the
two parquet files are hashed as raw bytes, resolved absolute paths. All six
must-not-move files were re-hashed (LF-normalised) against `git show master:<path>`
this fix -- every one MATCHES (candidate HEAD equals master this round, see header).
Every recorded hash below for the TEN .py candidate files plus the PROPOSED
runbook was asserted against a fresh on-disk read this session via a scratch
script: of the sixteen "unchanged" rows, the FOURTEEN text-file hashes matched
the prior fix's recorded values exactly by fresh read; the TWO parquet rows
(among those sixteen) are CARRIED FORWARD from an earlier fix, not re-read this
session (repo rule: never re-read data/ unless asked; see NOT VERIFIED); the
three edited files' hashes changed and are recorded below.

| path | role | size (bytes, LF-normalised) | sha256 (LF-normalised) |
|---|---|---|---|
| scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo.py | untracked, MODIFIED (fix 1q: `verdict_of()` moved out to `..._validate.py`, `validate_window()` call site added at score_window()'s top) | 14339 | df0bac971dc42a6931d2bf066fc512cde2d9991f4aba0be0e6e795ef50a069a6 |
| scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo_io.py | untracked, unchanged since fix 1p | 14262 | e42f99bc60b03bcc80e4487720f746444cdbe7f6d74fc677321eb7c630e6bac1 |
| scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo_kalshi.py | untracked, unchanged since fix 1o | 9535 | f90e4dc5abddffa20fe714abfc4783678ba49bc3158e72b1def2e0f98b3da7bb |
| scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo_ingress.py | untracked, unchanged since fix 1j | 1653 | b713298e4578508aa9c8de7eae8461f031a353a642b30b0937f106a3970b24f2 |
| scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo_validate.py | untracked, MODIFIED (fix 1q: NEW `validate_window()`; `verdict_of()` moved in from the main module, `min_dates` an injected parameter) | 5677 | 54047214758307789b0513d66a6500bac33620fbc91872f62c8469453809780c |
| tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo.py | untracked, unchanged since fix 1n | 15708 | 8f0d8ebe7d39a411d911c4e4b816f304867c7674454b01db8dc9f5d1124da9d4 |
| tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1b.py | untracked, unchanged since fix 1j | 15062 | 22dcbee8d966b6615c2297113434b17679bf47335f64690202adf40fb3973329 |
| tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1c.py | untracked, unchanged since fix 1m | 14735 | b3fc5aa6269b01eb7b6f5ac7ab78f903e900c373ef555152178989ad755e9cc7 |
| tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_kalshi.py | untracked, unchanged since fix 1l | 11176 | ca385e716e3ee9a27ed794cf2d09c08ed3f1f3ff5ef6d367b3d59a033438b892 |
| tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1n.py | untracked, MODIFIED (fix 1q: +2 validate_window regressions) | 11108 | db285989479a4c72352b33598435d892b49a62e5d04fe8a689844c48f44c3736 |
| docs/research/organization-sprint/PROPOSED_S448_refresh_runbook.md | untracked, gitignored (docs/research/* per .gitignore:489), runbook only, unchanged | 3741 | 69e66dd7d0a5964bed77e7fd5ec22f7e8e0e5a2c2e636bd774b5af783438e507 |
| domains/mlb/refresh_ratings.py | must-not-move | 4534 | 26f2494fb3273a5acff0dce73c5b19262620fcdaaa56f5f3827bd012757222ac |
| domains/mlb/ingest_manifest.py | must-not-move | 2513 | 26b40da151b867b6e3c68890730894b59a0d6fd1bef5e30fa4b34a9e549583bf |
| scripts/platformkit/predictor_jd.py | must-not-move | 12315 | d13fb4c7393eecb973251ae7b35612c8e2ff1f398c25505156e070947b571511 |
| scripts/platformkit/proof_mlb/beat_the_close_ml.py | must-not-move | 8039 | f2d014eeb62654d70122f89c5ff75817f4dbe5997da0f011e11230a93b71cd49 |
| domains/mlb/ingest_current.py | must-not-move | 7934 | 5114c125ea82ea8ff734a4ba070a7e17516238c55f4ba7b450afa9fdcaa3229d |
| domains/mlb/predictor.py | read for context (`_mov_final_ratings` import site, not edited) | 15631 | 9c32d2401644bc2b0d487defbbd76b00f317cbec086c02cfd0a7fd2b91cb5ad1 |
| C:/Users/neelj/nba-ai-system/data/domains/mlb/games.parquet | frozen input (2010-2021), resolved absolute path, read-only binary hash, raw bytes | 343723 | ddc69f4a3b0657a1d4011cb038443a5a3faa22552d7d81c4cb9b1af783700c31 |
| C:/Users/neelj/nba-ai-system/data/domains/mlb/games_current.parquet | current input (2022+), resolved absolute path, read-only binary hash, raw bytes | 164496 | 2d44bf48962ffdbfab5ffc150aef79c3bf2b26e870c132a4b6d333f4c0d33002 |

No A9 row says "not hashed". `git status --short` shows exactly eleven untracked
candidate paths -- TEN Python files plus this memo:

1. `scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo.py`
2. `scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo_io.py`
3. `scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo_kalshi.py`
4. `scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo_ingress.py`
5. `scripts/platformkit/eval_gate/mlb_frozen_vs_walkforward_elo_validate.py` (NEW)
6. `tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo.py`
7. `tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1b.py`
8. `tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1c.py`
9. `tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_kalshi.py`
10. `tests/platformkit/eval_gate/test_mlb_frozen_vs_walkforward_elo_1n.py` (NEW)

plus `docs/evidence/harness/S448_mlb_frozen_elo_2026-09-24.md` (this memo, not .py);
the gitignored PROPOSED runbook is hashed above but does not appear in
`git status --short`.

## LOC and test counts

- `mlb_frozen_vs_walkforward_elo.py`: 293 LOC (fix 1q: `verdict_of()` moved out,
  `validate_window()` call site added, net -7)
- `mlb_frozen_vs_walkforward_elo_io.py`: 300 LOC (at the cap, unchanged since fix 1p)
- `mlb_frozen_vs_walkforward_elo_kalshi.py`: 178 LOC (unchanged since fix 1o)
- `mlb_frozen_vs_walkforward_elo_ingress.py`: 33 LOC (unchanged)
- `mlb_frozen_vs_walkforward_elo_validate.py`: 117 LOC (fix 1q: +NEW
  `validate_window()`, +`verdict_of()` moved in from the main module)
- `test_mlb_frozen_vs_walkforward_elo.py`: 300 LOC (at the cap, unchanged), 17 tests, 17 passed
- `test_mlb_frozen_vs_walkforward_elo_1b.py`: 297 LOC (unchanged), 15 tests, 15 passed
- `test_mlb_frozen_vs_walkforward_elo_1c.py`: 300 LOC (at the cap, unchanged), 22 tests, 22 passed
- `test_mlb_frozen_vs_walkforward_elo_kalshi.py`: 248 LOC (unchanged), 23 tests, 23 passed
- `test_mlb_frozen_vs_walkforward_elo_1n.py`: 222 LOC (fix 1q: +2
  validate_window regressions), 18 tests, 18 passed
- All TEN .py candidate files: 0 non-ASCII bytes
- `python -m scripts.platformkit.tracking.contract_preflight --paths <all ten .py
  candidate files, verdict file excluded> --base master --spec
  docs/evidence/tracking/specs/S448_spec.md` = 9/9 PASS (see FIX 1q below)
- The written report's `"kalshi_refused"` object serialises SIX counters total: the
  four prescribed, plus `kalshi_malformed_row` and `kalshi_ambiguous_price`.
- CLI help for `--games-parquet` names the real default:
  `read_games_parquet(_FROZEN, _CURRENT)`, never `load_combined_corpus()`.

## Q6 / calibration language

Calibration vocabulary only (Q6) anywhere in any module, test file, memo or
runbook; verdict words used are exactly ACCEPT, REJECT, NULL, and UNDERPOWERED.

## STEP 2

`docs/research/organization-sprint/PROPOSED_S448_refresh_runbook.md` -- a PROPOSED
runbook only. Not applied, not scheduled, not run.

## FIX 1o (AMENDMENT 14, round 14: REJECT, 1 BLOCKING + 1 CORRECTION; trimmed --
## restates the compact Fix history above, full repro in `_verdict_s448_1o.md`)

Dual `yes_mid`/`price` Kalshi fields were compared before either was validated
(`..._kalshi.py:64`): `yes_mid=1,price=True` passed `1.0` with every counter
zero; `yes_mid=nan,price=nan` counted `kalshi_ambiguous_price` instead of
`kalshi_non_finite`. Fix: NEW `_validated_numeric()` validates/normalises each
field independently before any comparison. 3 regressions in `..._1n.py`. Memo
sha/inventory correction attempted, superseded by fix 1p (below). 90/90 tests;
9/9 preflight; edited `..._kalshi.py`, `..._1n.py`.

## FIX 1p (AMENDMENT 15, round 15: REJECT, 1 BLOCKING + 1 CORRECTION; trimmed --
## full repro in `_verdict_s448_1p.md`)

An invalid numeric `event_id` was refused but copied unchanged into the
refusal record (`..._io.py:188`, `..._validate.py:31`): a `nan` id broke
strict `json.dumps(..., allow_nan=False)`. Fix: NEW `json_safe_event_id()` in
`..._validate.py`, normalising any non-JSON-safe id to `None` at both
`..._io.py` refusal-append sites and both `pre_slice_refusal()` return sites.
3 regressions in `..._1n.py`. Memo sha-equality prose (fix 1o promised, never
executed) actually corrected this round. 93/93 tests; 9/9 preflight; edited
`..._io.py`, `..._validate.py`, `..._1n.py`.

## FIX 1q (Opus tier-2 final-pass verdict `_verdict_S448_opus_final.md`: ACCEPT WITH CORRECTIONS)

STEP 0 premise check: all five pre-existing test files passed as shipped (93)
before any edit; each correction below was reproduced against the verdict's
own repro steps first, then fixed and re-shown passing.

**1.** Nothing enforced `frozen_asof` strictly before `window_start`, or
day-grain window bounds (`mlb_frozen_vs_walkforward_elo.py:80`):
`frozen_asof=2026-07-17` with `window_start=2026-07-13` let the frozen arm
train on the scored games' own results; a timed `window_start` silently
dropped that day's games from both the scored and refused lists. Fix: NEW
`validate_window(window_start, frozen_asof)` in `..._validate.py`, raising
`ValueError` naming `frozen_asof_not_before_window` or
`window_start_not_midnight`, called as `score_window()`'s own `start` in
place of the bare `pd.Timestamp(window_start)`. `verdict_of()` moved into
`..._validate.py` (`min_dates` now an injected parameter, default 5, no
behaviour change) to hold the main module under the 300 LOC cap, net -7 LOC.
2 regressions in `..._1n.py`: `test_frozen_asof_not_before_window_start_refused`,
`test_window_start_with_time_of_day_refused`.

**2.** Memo self-contradicted on which rows were freshly hashed (parquet vs
text files, header/before-condition-heading/A9 paragraph vs NOT VERIFIED) --
fixed at all three sites; the "fix 12" typo corrected to "fix 1m".

**3.** NOT VERIFIED omitted served-parity risk (frozen arm's cleaned slice vs
the served RAW concat) -- new bullet added below.

**4.** `--window-end` has no regular-season bound by default -- new bullet
added below noting the real run must pass it explicitly.

95/95 tests; 9/9 preflight; edited `mlb_frozen_vs_walkforward_elo.py` (call
site + `verdict_of` removed), `..._validate.py` (NEW `validate_window()`,
`verdict_of` moved in), `..._1n.py` (+2), this memo.

## NOT VERIFIED

- No real run: `games_current.parquet` was never extended past 2026-07-12 by this
  row; `read_games_parquet(refresh_ratings._FROZEN, refresh_ratings._CURRENT)` was
  never called against the REAL two parquet files in this session (only fixture
  parquets); `_main()`'s real-corpus branch has never executed here.
- The Kalshi `first_pitch`/`side` references are supplied by the JSON file itself;
  a real capture file wiring a genuine source for either is a later, separate step.
- The regular-season end date is not hardcoded; `window_end` defaults to the max
  normalised date across clean AND refused rows -- it has no regular-season
  bound by default (`mlb_frozen_vs_walkforward_elo_io.py:248`), so the real run
  must pass `--window-end` explicitly (through the end of the regular season)
  or it will score postseason finals too.
- Performance of `_clean_records()` at full corpus scale (a per-record Python loop
  plus an O(n) Counter pass, once per as-of/window call) was not measured; nothing
  in the spec asks this row to optimize it.
- The two frozen/current parquet inputs' sha256 rows in the A9 table above were
  carried forward unchanged from the prior fix's hashing, not re-read this
  session (repo rule: never re-read data/ unless asked; nothing this fix touched
  could have changed those files).
- Frozen arm == served Elo is unproven on the real corpus: the served Elo is
  `final_ratings(load_combined_corpus())` on the RAW, un-deduplicated concat
  (`domains/mlb/refresh_ratings.py:51-59,:83`), while the harness frozen arm is
  `final_ratings()` on the CLEANED, deduplicated as-of slice, and
  `build_report()` discards that slice's own refusal list. The real run must
  compare the report's `frozen_ratings_digest` with
  `ratings_digest(final_ratings(load_combined_corpus()))` and treat a mismatch
  as the frozen arm NOT being the served Elo.
