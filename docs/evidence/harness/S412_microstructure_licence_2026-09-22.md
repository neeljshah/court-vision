# S412 -- microstructure licence: a sealed MATCH class beside S400's AHEAD licence

Row: S412 (workstream E, decision 13). Status: PREPARE only, PENDING ADJUDICATION of the seal.
Nothing here is sealed, landed or wired into a runtime; no caller exists. Built in worktree
`nba-harness-h81` on master `4f66acfb5727f091f5d9e84e37b9e1aab2b369d9`. Machine: the local laptop
(pure functions and construct tests only; no pod, no network, no archive, no ledger, no result file).

## Files

| file | lines | role |
|---|---|---|
| `scripts/platformkit/execution/microstructure_licence_inputs.py` | 234 | the two declared constants, `MatchCell`, `SealedCorpus`, `LicenceSeal`, `LicenceInputError` |
| `scripts/platformkit/execution/microstructure_licence.py` | 277 | `decide_licence` (R1-R6), `skewed_pads` / `quote_licensed` (item 3), `weekly_stop` (item 4) |
| `tests/platformkit/execution/test_microstructure_licence_inputs.py` | 236 | 44 construct tests incl. the byte-identity test |
| `tests/platformkit/execution/test_microstructure_licence.py` | 297 | 28 construct tests, one per false-PASS risk of CHANGE item 6 |

## Binding before-condition (quoted from master at 4f66acfb5)

(a) `scripts/platformkit/execution/paper_sizing_inputs.py:28`
`VERDICTS = ("AHEAD", "BEHIND", "UNDERPOWERED", "SINGLE-WINDOW")`; `:57-58`
`if self.verdict not in VERDICTS:` / `raise PaperSizingInputError("unknown_verdict", "verdict")`.
Re-measured: `CalibrationEvidence("f", 2, "MATCH", ...)` raises `unknown_verdict`.

(b) `paper_sizing_inputs.py:82-84` `def width(self) -> Decimal:` /
`"""The licensing interval width; the point never enters the size."""` / `return self.ci_hi - self.ci_lo`;
`:86-89` `def licensed(self) -> bool:` / `"""AHEAD only, with a sealed preregistration for every corpus."""` /
`return (self.verdict == "AHEAD" and self.corpus_count >= 2` /
`and len(self.sealed_prereg_sha256) == self.corpus_count)`.

(c) `scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:24` `N_MIN_GAMES = 30`; `:84-87`
`def verdict(lo, hi, n_games, n_min=N_MIN_GAMES):` / `if n_games < n_min or (lo <= 0 <= hi):` /
`return 'UNDERPOWERED'` / `return 'BEHIND' if lo > 0 else 'AHEAD'`. One name over two facts: too few
games, and a well-powered interval covering zero.

(d) `scripts/platformkit/execution/paper_sizing_policy.py:29-31` `# DECLARED policy constant, never a
measured number: ...` / `WIDTH_REFERENCE_DEFAULT = Decimal("0.02")`; `:125-140` `_permitted` calls
`check_caps(..., qty=str(candidate))` and returns `number(report["max_permitted_qty"], ...)`.

(e) `paper_sizing_inputs.py:117-120` `def certified(self) -> bool:` /
`"""True only for an ISSUED refuse-mode label; BOUNDED is not certified."""`;
`scripts/platformkit/execution/fee_certification_gate.py:204-217` `def require_certified(mode: str = "refuse")`
returns `replace(status, label=f"CERTIFIED fee_module_sha256={status.fee_module_sha256}")` when certified and
`raise FeeCertificationError("fee certification refused")` in refuse mode otherwise.

(f) `scripts/platformkit/execution/family_week_ledger.py:18` `TARGET_WEEKS = 8`; `:164-173` `def streak(self,
family: str) -> int:` / `"""Count qualifying weeks ending at the latest completed UTC ISO week."""`, walking back
while `counts[week] >= floor`; `:175-188` `independence()` returns `{"families": [first, second], "status": status,
"shared_game_ids": shared}` with status `"NOT INDEPENDENT" if shared`.

(g) `scripts/platformkit/execution/quote_engine.py:3-5` `The documented anchor default is the contemporaneous
observed mid: pass None ... A caller must not substitute a standalone model value as the default anchor.`; `:35`
`_ADVERSE_CENTS = INGAME_MAX_DRIFT_PCT`; `:150-152` `adverse = caps.get('adverse_selection_cents', {'bid':
_ADVERSE_CENTS, 'ask': _ADVERSE_CENTS})` / `pads = {s: _number(adverse[s]) for s in ('bid', 'ask')}`; `:172`
`center = mid - k_inv * inv`; reduce-only flatten path `:147` `reducing = remaining < deadline` and `:163-166`
`reduction_room = ...`; reached through `quote_reservation.py:196` `def make_quotes_reserved(...)`.
LINE DRIFT: the spec cites quote_engine `:141-144`, `:164` and `:134-160`; on master the same text sits at
`:150-152`, `:172` and `:147-166`. The content is as the spec states; only the line numbers moved.

(h) `scripts/platformkit/execution/position_caps.py:1-9` `Units are contracts. ... Every logged open unfilled
quantity counts. ... max_permitted_qty is bounded by the submitted qty and tells the caller how much of it can proceed.`

(i) `scripts/platformkit/execution/markout_causal.py:182` `def summary_strict(...)`; `:246-247`
`verdict = "INSUFFICIENT" if lo is None or hi is None else (` /
`"POSITIVE" if lo > 0.0 else "NEGATIVE" if hi < 0.0 else "INDISTINGUISHABLE")`;
`scripts/platformkit/execution/entry_timing/study.py:30-32` `def cluster_boot_ci(...)` /
`"""95% CI for the mean, bootstrap resampling whole game clusters."""`; `:37-38` `if len(keys) < 5:` /
`return (None, None)`.

(j) `scripts/platformkit/execution/forward_replay_qualification.py:21` `WEEK_GAMES, SPORT_GAMES, FILL_GAMES = 4, 30, 30`.

## Premise re-measured (Q8)

The premise holds on master today: `licensed()` is False for every verdict but AHEAD, the string "MATCH" cannot
enter `CalibrationEvidence` (unknown_verdict), and the S347 cell is landed-UNDERPOWERED
(`verdict(-0.010776, 0.004000, 135, 30) == "UNDERPOWERED"`), so S400 sizes it zero. Without a second class a
maker book sizes zero forever. Premise: NOT FALSIFIED.

## The two declared constants

- `MATCH_N_MIN = N_MIN_GAMES` (imported from the landed gate; 30). The `n_games < n_min` branch of UNDERPOWERED
  is never MATCH.
- `MATCH_HALF_WIDTH_MAX = Decimal("0.01")` in Brier units: half the landed `WIDTH_REFERENCE_DEFAULT` scale.
  DECLARED, not measured. Both live only in `microstructure_licence_inputs.py`; a test asserts the licence
  module re-declares neither.

MATCH(cell) is true when ALL hold: the landed `verdict(ci_lo, ci_hi, n_games, 30)` is UNDERPOWERED;
`n_games >= 30`; `ci_lo <= 0 <= ci_hi`; `(ci_hi - ci_lo) / 2 <= 0.01`; `concentration_pass is True`. A cell carries
no declared verdict: MATCH is computed, so a hand-written label cannot license a size.

## Worked S347 cell (quoted literals, no file opened)

S347 all_tick overall B_brier: point -0.003363, ci95 [-0.010776, +0.004000], n_games 135. Landed verdict
UNDERPOWERED; n 135 >= 30; the interval covers zero; half-width (0.004000 + 0.010776) / 2 = 0.007388 <= 0.01.
With concentration_pass True it is MATCH. It is ONE corpus on a spent window, so R2 refuses it
(`too_few_corpora`, size 0) -- the first licence test consumes exactly this cell end to end.

## Rules as built (decide_licence)

- R1 CLASS: exactly one of AHEAD / MATCH, named in `LicenceDecision.licence_class`. AHEAD returns
  `routed_to_size_paper` with size 0 from this module; size_paper is never called here. Any other class is a
  counted refusal.
- R2 CALIBRATION: at least two `SealedCorpus`, each a distinct 64-hex digest (the licence's own digest may not
  equal one); corpus game-id sets pairwise disjoint, reported in the landed `independence()` record shape
  (`NOT INDEPENDENT` with the shared ids); every sealed cell MATCH; any cell with ci_lo > 0, primary or
  secondary, refuses (`corpus_behind`). Every cell's family must equal the decision family.
- R3 FEES: a `FeeEvidence` whose `certified` is True (only `FeeEvidence.from_status` over a refuse-mode
  `require_certified` status issues it); BOUNDED or a hand-built label is `fee_uncertified`. Venue must be
  kalshi; Polymarket is `venue_excluded` until the 37 S399 mismatches close.
- R4 STREAK: `ledger.streak(family) >= TARGET_WEEKS`, read at every call from the `FamilyWeekLedger` object
  (an int is refused).
- R5 SEAL FIRST: `LicenceSeal(prereg_sha256, commit_utc)`; the zoned commit time (parsed with
  `parse_venue_time`) must be STRICTLY before Monday 00:00 UTC of the earliest ISO week the streak reads; both
  times are printed in the decision.
- R6 SIZE: exactly one contract, then `min(1, rooms.room_for(side), check_caps(...)["max_permitted_qty"])`
  asked prospectively through the landed `_permitted`; floored; zero is `room_exhausted` and never rounded up.
  No Kelly step and no expectation arithmetic.
- R7: no S362 constant is imported or read.

Every intermediate is an exact string in the fixed-order audit tuple; reasons come from a closed vocabulary in a
fixed order, independent of input order (tested over both corpus permutations).

## Sign-only skew (item 3)

`quote_licensed` always passes `anchor=None` (make_quotes, or make_quotes_reserved when a reservation is
given), so the anchor stays the observed mid. With r = p_model - book mid probability: r > 0 adds exactly one
cent to the ASK adverse-selection pad, r < 0 to the BID pad; r == 0 or an absent p_model leaves the caps
untouched, so the output equals the unskewed landed output. |r| never enters anything. Inventory remains the
landed `center = mid - k_inv * inv` and reduce-only path; k_inv, k_sd, flatten_deadline_s are caller constants.

## Primary grade, sealed cell and multiplicity rule (item 4)

The grade is the fee-netted causal markout in probability points at 30 / 120 / 300 s from the landed
`summary_strict`, clustered on game_id, with the LANDED MEAN estimator (`cluster_boot_ci`); a median would be new
code and a different sealed quantity. `largest_single_game_share` and `leave_one_game_out_range_units` are
required fields of the stopping input and are carried into its record.
PROPOSED sealed primary cell: family x `PRIMARY_HORIZON_S = 120`. Multiplicity rule: exactly one primary cell,
so no correction is applied; the 30 s and 300 s horizons and every other family are descriptive only and are
never promoted.

`weekly_stop` order: (1) after four completed weeks, a projected week-8 qualified or fill-bearing count below 30
is STOP `underpowered_projection` (never extended); (2) below 30 cumulative qualified or 30 fill-bearing games
there is no interim look (`no_interim_look`); (3) INSUFFICIENT is counted (`insufficient_weeks = 1`) as no
signal and no evidence, never a stop; (4) a week below the family floor is not graded (the ledger streak stops
quoting); (5) NEGATIVE on a floor-meeting week is STOP `negative_markout`. The verdict label is recomputed from
the interval; a disagreement is a counted refusal. Note: the landed streak already breaks at the FIRST
below-floor week, which is stricter than "three consecutive weeks below the floor", so that rule is subsumed.

## What each outcome honestly licenses (item 5)

POSITIVE (the sealed cell's interval excludes zero from above, fee-netted, surviving the WORST queue multiplier
of the S411 grid, concentration diagnostics published, on >= 2 independent families): on this venue, in this
family, over N qualified games, the fee-netted maker markout distribution had a positive clustered mean of X
probability points with interval [a, b] under the declared fill model -- and, MATCH being true by construction,
that the result did not come from calibration. It licenses no currency figure, no rate, no projection and no
real-money path, only a larger paper series and an owner decision.

NEGATIVE (the interval contains or sits below zero): an honest REJECT and a success, licensing closure of the
maker channel for that family and a statement of the measured upper bound; the channel stays RED and is never
massaged.

## The licence is a DECLARATION

Digests are checked for 64-hex format and distinctness only; resolving a seal to its artifact is the S395
auditor's job. The seal commit time is supplied by the caller; this code never runs git.

## Deviations from the spec text, stated

- Item 6 "a ledger append that drops the streak": with a fixed `as_of` the landed ledger can only add weeks, so
  an append cannot lower the streak of the same object. The test shows both directions instead: the same ledger
  object gives `family_streak_short` then `sized` across an append (no cache), and a ledger whose week rolled
  over onto a below-floor week gives streak 0 and size 0.
- The byte-identity test pins the SHA-256 of each of the six master blobs (CRLF folded to LF) instead of calling
  git; `git diff master` over the six paths was also empty at build time.

## Tests run (per file, one at a time, in the worktree)

- `python -m pytest tests/platformkit/execution/test_microstructure_licence.py -q -p no:cacheprovider`: 27 passed.
- `python -m pytest tests/platformkit/execution/test_microstructure_licence_inputs.py -q -p no:cacheprovider`: 26 passed.
- `python -m scripts.platformkit.tracking.contract_preflight --paths <the five files> --base master --spec
  docs/evidence/tracking/specs/S412_spec.md`: 0 FAIL.

## FIX 1b (AMENDMENT 1)

Changes (the module stays PREPARE only, with no caller):

- (a) and (b) `scripts/platformkit/execution/microstructure_licence_inputs.py:162-224`: new `MARKOUT_VERDICTS`,
  `MIN_CLUSTERS = 5` (the landed `cluster_boot_ci` literal, `entry_timing/study.py:37`), `SUMMARY_KEYS`, `_finite`
  (moved here from the licence module) and `markout_verdict(horizon)`. `n_clusters` must be a strict int (bool,
  float and str are refused), and so must `n` and `n_scored` when present. `mean_units`, both interval bounds, the
  share and the leave-one-game-out range must be None or a finite int, float or Decimal (`Decimal.is_finite` /
  `math.isfinite`). The share must lie in [0, 1] and the range must be >= 0. A verdict outside the landed set is
  refused. If `n_clusters` < 5 the function returns INSUFFICIENT whatever the label or interval says. Otherwise
  an inverted interval, or a label that differs from the one recomputed from the interval (for example NEGATIVE
  over an interval that covers zero), is refused. Every refusal uses the reason `bad_markout_summary` (the old
  `verdict_inconsistent` refusal is gone).
- `scripts/platformkit/execution/microstructure_licence.py:249`: `weekly_stop` calls `markout_verdict`. This means
  an INSUFFICIENT week can never reach STOP `negative_markout`. At `:251` every record `json.dumps` passes
  `allow_nan=False`. The old `_finite` and `_SUMMARY_KEYS` were removed from this module.
- The spec text disagrees with itself. Its example "NEGATIVE with n_clusters < 5 is refused" conflicts with the
  regression case "n_clusters=4, NEGATIVE, [-0.02, -0.001] -> CONTINUE". The build follows the regression case
  and the clause "derive INSUFFICIENT whenever n_clusters < 5, regardless of the verdict string or interval". So
  a label with fewer than 5 clusters is overridden to INSUFFICIENT and the call is not refused. Labels are
  checked for consistency only when there are at least 5 clusters.
- New tests: `test_four_cluster_negative_label_is_insufficient_never_a_stop` (test_microstructure_licence.py:250),
  `test_non_finite_or_out_of_range_summary_field_refuses` (9 cases, test_microstructure_licence_inputs.py:170),
  and `test_stop_record_never_carries_nan_or_infinity` (test_microstructure_licence_inputs.py:176).
- Re-run per file: test_microstructure_licence.py gave 28 passed and test_microstructure_licence_inputs.py gave
  36 passed. The byte-identity test was re-run on its own and passed.

NEW GAP statements from AMENDMENT 1(c). These are recorded and do not block this row:

- The three-consecutive-weeks-below-floor rule is enforced only through the landed streak break. That break
  happens at the first week below the floor, so it is stricter than the spec.
- `skewed_pads` refuses a best bid of 0 cents (`0 < bid` is required), while the landed quote engine allows it.
- A seal written in the middle of a series refuses the whole licence until the streak breaks and restarts after
  the seal. This is conservative.
- The landed `FamilyWeekLedger` built with `as_of=None` fixes `_current` when it is constructed. This is a gap in
  landed code, and a row should be registered for it later.

## FIX 1c (AMENDMENT 2)

- `scripts/platformkit/execution/microstructure_licence_inputs.py:216-217`: the inverted-interval check (lo > hi,
  refused as `bad_markout_summary`) now runs BEFORE the `n_clusters < MIN_CLUSTERS` early return at `:218-219`.
  The other structural checks (strict-int counts, non-finite fields, share outside [0, 1], negative range,
  unknown label) already ran before that return and are unchanged. Only the label-vs-interval consistency
  check still depends on n_clusters >= 5.
- New test: `test_inverted_interval_refuses_even_below_the_cluster_floor`
  (test_microstructure_licence_inputs.py:176): n_clusters=4 with [-0.001, -0.02] is refused; n_clusters=4
  NEGATIVE with [-0.02, -0.001] still derives INSUFFICIENT. The existing
  `test_four_cluster_negative_label_is_insufficient_never_a_stop` (CONTINUE) is kept.

## FIX 1d (AMENDMENT 3)

- `scripts/platformkit/execution/microstructure_licence_inputs.py:220-225`: after the
  `n_clusters < MIN_CLUSTERS` early return (INSUFFICIENT, None diagnostics accepted), each of the two interval
  bounds, `mean_units`, `largest_single_game_share` and `leave_one_game_out_range_units` must be present; a
  None is refused as `bad_markout_summary`. The label is then derived from the interval only
  (`:226`); the old None-interval INSUFFICIENT branch at >= 5 clusters is gone.
- New tests (test_microstructure_licence_inputs.py): `test_null_diagnostic_at_the_cluster_floor_refuses`
  (`:195`, five parametrized cases, n_clusters=5, interval [-0.02, -0.001], one None field each) and
  `test_all_null_diagnostics_below_the_cluster_floor_are_insufficient` (`:201`, n_clusters=4, every
  diagnostic None, INSUFFICIENT).
- Re-run per file: test_microstructure_licence_inputs.py 43 passed; test_microstructure_licence.py 28 passed.
  The owned-files table above now carries the line counts after this fix (234 / 276 / 204 / 297).

## FIX 1e (AMENDMENT 4)

- `scripts/platformkit/execution/microstructure_licence.py:96-99`: the `independence` audit-trail serialization
  inside `_calibration` (`json.dumps(records, sort_keys=True, separators=(",", ":"))`) now passes
  `allow_nan=False`. This was the one `json.dumps` call in the two owned modules that lacked the guard --
  grepped both files: `microstructure_licence.py` has exactly two `json.dumps` calls (this one and the
  `weekly_stop` record serialization at `:251-252`, which already carried `allow_nan=False` since FIX 1b);
  `microstructure_licence_inputs.py` has none.
- New test: `test_independence_serialization_refuses_a_non_finite_shared_game_id`
  (`tests/platformkit/execution/test_microstructure_licence_inputs.py:215`). `SealedCorpus.game_ids` is always
  text-validated (`_text`), so a non-finite value can never reach `_independence` through the real construction
  path; the test probes the private `_independence()` builder directly with a duck-typed `_FakeCorpus` carrying
  a shared `float("nan")` game id, confirms the resulting record's `shared_game_ids` list is non-empty, shows
  the default `json.dumps` (no guard) emits the literal string `"NaN"`, and asserts the guarded call
  (`allow_nan=False`) raises `ValueError` instead. SUPERSEDED by FIX 1f: this regression called only
  `_independence` and a test-local `json.dumps`, never the production `_calibration` call that owns `:96-99`,
  so removing the guard there would not have failed it.
- Re-run per file: `test_microstructure_licence_inputs.py` gave 44 passed (43 + 1 new);
  `test_microstructure_licence.py` gave 28 passed, unchanged. The owned-files table above now carries the line
  counts after this fix (234 / 277 / 229 / 297). `contract_preflight` over the five owned paths: 0 FAIL.

## FIX 1f (AMENDMENT 5)

- Root cause: AMENDMENT 4's regression asserted `pytest.raises(ValueError)` around its OWN standalone
  `json.dumps(records, ..., allow_nan=False)` call, built from a `records` list it computed itself by calling
  `microstructure_licence._independence(...)` directly. It never called `_calibration` (or `decide_licence`),
  so removing `allow_nan=False` from the production serialization at `microstructure_licence.py:96-99` would
  not have failed it -- the regression exercised a copy of the guard, not the guard.
- Fix: rewrote the same test in place (kept the name-appropriate location, `def` now at
  `tests/platformkit/execution/test_microstructure_licence_inputs.py:216`, renamed
  `test_calibration_serialization_refuses_a_non_finite_shared_game_id`). `_FakeCorpus` (`:208`) gained two
  attributes `_calibration` reads before it reaches `_independence` (`sealed_prereg_sha256`, `cells=()`), so a
  duck-typed pair can be passed straight to the private `_calibration` function -- `_calibration` never checks
  `isinstance(corpora[i], SealedCorpus)` (only `decide_licence` does, at `:140-141`), so this is a legitimate
  way to drive the exact production code path with corpora whose game-id sets share `float("nan")` while every
  other rule (2 distinct-looking corpora, a real `LicenceSeal`, no cells to fail MATCH/BEHIND/family checks
  before the serialization line runs) is satisfied. The test now asserts
  `pytest.raises(ValueError): microstructure_licence._calibration("family", (corpus_a, corpus_b), seal, {})`.
- Mutation proof (temporarily removed `allow_nan=False` from `:96-99`, restored after):
  - Guard removed: `python -m pytest tests/platformkit/execution/test_microstructure_licence_inputs.py -q -p
    no:cacheprovider -k test_calibration_serialization_refuses_a_non_finite_shared_game_id` -> **1 failed**,
    `Failed: DID NOT RAISE <class 'ValueError'>` at the `with pytest.raises(ValueError):` line. (A first attempt
    with `seal=None` also failed the test, but on an unrelated `AttributeError: 'NoneType' object has no
    attribute 'prereg_sha256'` raised two lines later in `_calibration` -- a real `LicenceSeal` was substituted
    so the mutation is caught by the intended "no ValueError" signal, not an incidental stub crash.)
  - Guard restored (`git diff --stat` over the module: clean, byte-identical to the fast-forwarded master
    baseline): same command -> **44 passed**.
- Re-run per file: `test_microstructure_licence_inputs.py` gave 44 passed (same count; one test rewritten, none
  added); `test_microstructure_licence.py` gave 28 passed, unchanged. `contract_preflight` over the five owned
  paths: 0 FAIL.

## NOT VERIFIED

- The across-game dispersion of the maker markout is unmeasured; no interval here is a measured number.
- Zero qualified games and zero paper fills exist to date for any family; nothing here was graded.
- `MATCH_HALF_WIDTH_MAX = 0.01` is a declared constant, never validated against any corpus.
- Every markout number this licence would grade depends on the S411 fill model (queue multiplier grid), which
  is not built or validated here.
- `PRIMARY_HORIZON_S = 120` and the multiplicity rule are PROPOSED; decision 13's seal is pending the owner's
  adjudication, and no preregistration file exists yet, so R5 has never been satisfied by a real commit.
- The reservation path of `quote_licensed` is exercised only with a stub recorder (anchor is None); no issued
  `Reservation` was driven through it.
- The tests were run in the worktree, not in master (verifier step A1 is the verifier's).
- No two-corpus MATCH evidence exists; the only quoted cell (S347) is one spent corpus.
