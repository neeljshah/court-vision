# S447 MLB in-game predict_live vs the served pregame carry -- STEP 1 of 2 (REPORT ONLY)

Machine: local Windows worktree C:/Users/neelj/nba-harness-h102, master-based, HEAD not moved.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B, Q. Spec:
docs/evidence/tracking/specs/S447_spec.md.
WHERE: local. No network, no GPU, no pod. Construct rows only in tests; no archive read.

## Before-condition quotes (verified in this worktree, file:line)

- `scripts/platformkit/ingame/repricer_router.py:34` `_SURFACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "surfaces")`
- `scripts/platformkit/ingame/repricer_router.py:52` `path = os.path.join(_SURFACE_DIR, "%s.json" % sport)`
  (`ls scripts/platformkit/ingame/surfaces/` = nba.json only -- no mlb surface exists)
- `scripts/platformkit/ingame/live_loop.py:237` `rp = rr.reprice(sport, gs, prior)`
- `scripts/platformkit/ingame/live_loop.py:243` `rp = _pregame_carry(sport, prior, reason=str(rp.get("reason", "")))`
  (every MLB live tick today is served the constant pregame prior, never predict_live)
- `domains/mlb/predictor.py:99` `self._elo = _mov_final_ratings(df)` (Elo comes from whatever `games_df` slice built the instance -- an as-of Elo for day D is `MLBPredictor(games_df=games[games.date < D])`)
- `domains/mlb/predictor.py:112-115` `self.ingame_recal = lambda p: float(min(max(p, 0.0), 1.0))` -- the W156 "recal" predict_live applies is a fixed identity, not a fitted step (false premise in the row's own hypothesis text, per the spec's before-condition (b))
- `domains/mlb/predictor.py:237` `def predict_live(self, home, away, inning, half, home_runs, away_runs)`
- `scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:22-24` `N_BOOT = 2000`, `SEED = 13`, `N_MIN_GAMES = 30`; `:70 def cluster_bootstrap(...)`; `:84 def verdict(lo, hi, n_games, n_min=N_MIN_GAMES)` -- all four imported and reused UNEDITED, never reinvented.
- `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md` card C2: `mlb_segmented_r3` (176 games, 29,887 eligible ticks) "is descriptive forever ... May NOT be used for: a second charged window -- SPENT-WINDOW RULE" (its one charge, S347, returned 96 of 96 UNDERPOWERED).

## Discrepancy noted (not a blocker)

The task/spec text names `scripts/platformkit/eval_gate/gate_a0_ingame_vs_market.py`; the real
file is `scripts/platformkit/ingame/gate_a0_ingame_vs_market.py` (confirmed by `find`); imports
point at the real path.

## Real state_summary format (ground truth, from the existing test file)

`tests/platformkit/test_gate_a0_ingame_vs_market.py` shows the real string format: `'home_score=0.0 away_score=0.0 inning=2 half=top ...'` / `half=bot` for the bottom half. The historical-corpus loader (`load_historical`) was written against this confirmed format; half spellings are mapped via a lookup (`_LOADER_HALVES`, AMENDMENT 5 item d), not the inline conditional an earlier memo draft wrongly attributed to a `_norm_half()` function (no such function exists; corrected by FIX 1e, superseded by item d's strict lookup). Team names are NOT in `state_summary`; the loader reads `home`/`away` off the row itself and refuses (counts) any row missing them -- NOT VERIFIED against real corpus files.

## The 13 CONSTRUCT cases (docs/evidence/tracking/specs/S447_spec.md line 14)

| # | Case | Test | Result |
|---|------|------|--------|
| 1 | model instant = its own state receipt, no later state admitted | `test_case1_model_instant_uses_only_its_own_row_state` | PASS |
| 2 | no pregame prior -> refused + counted, never imputed | `test_case2_no_prior_refused_never_imputed` | PASS |
| 3 | carry read once per game, identical across ticks | `test_case3_carry_read_once_per_game_later_value_ignored` | PASS |
| 4 | as-of Elo excludes any game on/after cutoff date | `test_case4_asof_elo_never_includes_game_on_or_after_cutoff` | PASS |
| 5 | Brier exact on a two-game synthetic corpus | `test_case5_brier_exact_two_game_synthetic_corpus` | PASS |
| 6 | paired-diff sign convention (live minus carry; negative=ahead) | `test_case6_paired_diff_sign_convention_negative_is_live_ahead` | PASS |
| 7 | INSUFFICIENT under n_games < N_MIN_GAMES even with mid present | `test_case7_insufficient_under_n_min_even_with_mid_present` | PASS |
| 8 | mid never read by the verdict function | `test_case8_mid_never_enters_the_verdict` | PASS |
| 9 | historical rows labelled historical_descriptive, never a verdict | `test_case9_historical_rows_labelled_descriptive_never_a_verdict` | PASS |
| 10 | forward-only game, zero historical rows, still scores | `test_case10_forward_only_game_with_zero_historical_rows_still_scores` | PASS |
| 11 | UTC-midnight game resolves cutoff from game_date, not receipt | `test_case11_utc_midnight_cutoff_uses_game_date_not_receipt` | PASS |
| 12 | duplicate / out-of-order receipts refused + counted (S431's rule) | `test_case12_duplicate_and_out_of_order_receipts_refused` | PASS |
| 13 | A9 identities recorded for a streamed input | `test_case13_a9_identity_recorded_for_a_streamed_input` | PASS |

`python -m pytest tests/platformkit/eval_gate/test_mlb_predict_live_vs_carry.py -q` -> 13 passed.

## FIX 1b (AMENDMENT 1)

Round 1 (Opus tier 2 ACCEPT WITH CORRECTIONS + codex sol REJECT, four blockers) required
items (a)-(j). All applied in this worktree; base `git rev-parse --short HEAD` = `61419f21c`
(unmoved). The loaders + as-of-corpus helpers moved to a NEW
`scripts/platformkit/eval_gate/mlb_predict_live_vs_carry_io.py` to keep both python files
under the 300-LOC cap (candidate-file note); new regressions for (c)/(d)/(e)/(f)/(g)/(i) went
to a NEW `tests/platformkit/eval_gate/test_mlb_predict_live_vs_carry_1b.py`; (a)/(b)/(h) are
in-place edits to the existing `test_mlb_predict_live_vs_carry.py` (cases 6, 9, 13 unchanged
in number, corrected in body).

| item | change | file:line |
|---|---|---|
| (a) | `forward_cell([])` -> `verdict: "INSUFFICIENT"` (never NULL), field renamed `charged` -> `chargeable` (both cells) | `mlb_predict_live_vs_carry.py:176-216` |
| (b) | case 6 rewritten through `forward_cell` (30 games, brier_live 0.0/brier_carry 1.0 -> point -1.0, AHEAD; mirror -> BEHIND) | `test_mlb_predict_live_vs_carry.py:72-82` |
| (c) | carry + last-receipt maps keyed by `(corpus, game_id)`, not `game_id` alone | `mlb_predict_live_vs_carry.py:108` |
| (d) | every receipt parsed via `parse_venue_time` to integer microseconds (`_receipt_micros`); a `mid_receipt` strictly after the state receipt strips the mid | `mlb_predict_live_vs_carry.py:60-65,110,155-160` |
| (e) | unsettled (`outcome is None`) -> `unsettled`; missing home/away score -> `unparseable_state`; non-ASCII byte in the historical loader -> counted `non_ascii_byte_refused`, run continues (per-line decode, not a whole-file `open(encoding=...)`) | `mlb_predict_live_vs_carry.py:131-138`; `mlb_predict_live_vs_carry_io.py:85-91` |
| (f) | `_valid_prob` (finite, in `[0,1]`) gates `p_live`, `carry`, and `mid`; `json.dumps(..., allow_nan=False)`; LF bytes via `sys.stdout.buffer.write` | `mlb_predict_live_vs_carry.py:67-72,220-223,275-279` |
| (g) | `canonicalize_calendar_day` floors both the corpus dates and the cutoff to midnight before the strict `<` filter | `mlb_predict_live_vs_carry_io.py:42-59` |
| (h) | `record_identity` now does `Path(path).resolve(strict=True)` before reading; identities below and the test are absolute paths | `mlb_predict_live_vs_carry_io.py:35-40` |
| (i) | `CorpusStartBeforeTick` raised by `get_asof_predictor` on an empty as-of slice (never constructs `MLBPredictor(games_df=empty)`, which raises `IndexError`); `process_rows` catches it and counts `corpus_start_before_tick` | `mlb_predict_live_vs_carry_io.py:29-33,62-70`; `mlb_predict_live_vs_carry.py:143-146` |
| (j) | `PROPOSED_S447_mlb_surface.md` reworded to describe `nba.json`'s no-claim boolean without quoting its key name | `docs/research/organization-sprint/PROPOSED_S447_mlb_surface.md` (gitignored, not in git status) |

New refusal reasons introduced by 1b: `invalid_carry`, `invalid_receipt_time`, `unsettled`,
`invalid_probability`, `invalid_outcome`, `invalid_mid`, `book_receipt_after_state`,
`corpus_start_before_tick`, `non_ascii_byte_refused`, `unparseable_historical_row`. DESIGN
NOTE: an invalid `mid`/late `mid_receipt` strips only the `mid` field and counts a refusal --
it never drops the tick's own `brier_live`/`brier_carry` scoring (mid is descriptive, case 8).

Test counts: `test_mlb_predict_live_vs_carry.py` 13 passed (cases 1-13, 6/9/13 amended in
place); `test_mlb_predict_live_vs_carry_1b.py` 10 passed (amendment items a, c, d x2, e x2,
f x2, g, i).

## A9 identities (path, bytes, sha256) -- recomputed from this tree, absolute paths (item h),
LF-normalised bytes (`read_bytes().replace(b"\r\n", b"\n")`), round 8 / FIX 1i, at fix time
(regenerated LAST, after every other edit in this memo)

candidate HEAD: `git rev-parse HEAD` (this worktree) = `39d79ff4c167c2817e9509db3de3348424a96d0a`.
verification base: `git -C C:/Users/neelj/nba-ai-system rev-parse master` = `39d79ff4c167c2817e9509db3de3348424a96d0a` (both read fresh from git; equal because the orchestrator fast-forwarded this worktree onto the current master immediately before resubmission).

| path | bytes (LF) | sha256 (LF-normalised) |
|---|---|---|
| C:\Users\neelj\nba-harness-h102\scripts\platformkit\eval_gate\mlb_predict_live_vs_carry.py (untracked) | 12255 | f6417408dab3a3ef436ae5070008acb110d930c0c22d6b5f884cc6f56469f588 |
| C:\Users\neelj\nba-harness-h102\scripts\platformkit\eval_gate\mlb_predict_live_vs_carry_io.py (untracked) | 13921 | 869f8b2774830cd5713fffc0427b634ca979c10f6f909ab46051a7809c993fe5 |
| C:\Users\neelj\nba-harness-h102\scripts\platformkit\eval_gate\mlb_predict_live_vs_carry_report.py (untracked) | 4646 | 57c51bf8ba24ca48181e29647fd925aaf28f4b5c8166b6ddff5fa41552eff8eb |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry.py (untracked) | 8286 | 64ee77670210194f1cac13f537a052237e16fcd109a1e372d973944e91e12ad7 |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry_1b.py (untracked) | 6550 | f872eea7ab482f6234325917ff68f3b3fa3d927274e3c389f5e1e99af1a16eea |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry_1c.py (untracked) | 4655 | 3808bf52aae2eb582e408565bd9d954c4f99b0630550377a7563c2443860ba61 |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry_1d.py (untracked) | 3195 | f5da9e980b18a214fc2db9813c4bc3f18bca95faa535626093164b061b425240 |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry_1e.py (untracked) | 4324 | 77041800fd0819351f3566d0b5b614060a465c50230561b37d2d81dcd7ef13c5 |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry_1f.py (untracked) | 4853 | 1953e03a1e4ab4aec9c9826eeac2b84d4f24c646a9c82a7421dbebfd042fb93e |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry_1g.py (untracked) | 3936 | 80661c9465a78e1090f9199e82c1acef141d6d93058476c31ef6f0e17ee05ca2 |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry_1h.py (untracked) | 4676 | 1304e9f8b46620edf9f7030c724d33c7a546ad8853f06c9e9b25334f5d46995f |
| C:\Users\neelj\nba-harness-h102\tests\platformkit\eval_gate\test_mlb_predict_live_vs_carry_1i.py (untracked, NEW round 8) | 4232 | 4c9c686aa649cfe99c356f51db8f909babdb96e419a6ff4920c9c3ddb108d537 |
| C:\Users\neelj\nba-harness-h102\docs\evidence\harness\S447_PROPOSAL_mlb_surface_2026-09-24.md (untracked, tracked twin of round-2 item d) | 3858 | 9b0c7d30396a8d914b88d9e399da224ec51625126b99e7774db64c612e0936f9 |
| C:\Users\neelj\nba-harness-h102\scripts\platformkit\ingame\repricer_router.py (must-not-move) | 8095 | e8c34b3d21d3c5e55bcb51e30bcb78c3c88ec80ab12fbfcbe3a0fafc5e2b2401 |
| C:\Users\neelj\nba-harness-h102\scripts\platformkit\ingame\live_loop.py (must-not-move) | 17486 | 5f985a9eed5835cc4ed620ac7819aeaedc00798a5745782685afd9b2a8f7ede6 |
| C:\Users\neelj\nba-harness-h102\domains\mlb\predictor.py (must-not-move) | 15631 | 9c32d2401644bc2b0d487defbbd76b00f317cbec086c02cfd0a7fd2b91cb5ad1 |
| C:\Users\neelj\nba-harness-h102\domains\mlb\refresh_ratings.py (must-not-move) | 4534 | 26f2494fb3273a5acff0dce73c5b19262620fcdaaa56f5f3827bd012757222ac |
| C:\Users\neelj\nba-harness-h102\scripts\platformkit\ingame\gate_a0_ingame_vs_market.py (must-not-move) | 11748 | 1f917e06e92b69bebabaf0ecb6d8bfd2ffe8f7a8cc71415fbdea79c0224cfb13 |

The five must-not-move files are byte-identical to master at the current base (B10, Q3): each
row's LF-normalised sha256 was cross-checked against `git show master:<path>` (LF-normalised)
and matched for all five (identical bytes/sha256 to every prior round -- these files were never
touched). `git status --short` shows fourteen untracked files (no memo self-count needed since
it is regenerated in place) -- the three `mlb_predict_live_vs_carry*.py` modules, all nine
`test_mlb_predict_live_vs_carry*.py` files (`.py` through `_1i.py`), this memo, and the
`S447_PROPOSAL_mlb_surface_2026-09-24.md` tracked twin -- none is a tracked file modified in
place. The gitignored PROPOSED file (round-2 items j/d) is under `docs/research/**` and so
never appears in `git status`.

## LOC / preflight

- `mlb_predict_live_vs_carry.py`: 272 LOC. `mlb_predict_live_vs_carry_io.py`: 279 LOC.
  `mlb_predict_live_vs_carry_report.py`: 89 LOC. All three <= 300.
- `test_mlb_predict_live_vs_carry.py`: 165. `_1b.py`: 137. `_1c.py`: 106. `_1d.py`: 73.
  `_1e.py`: 99. `_1f.py`: 95. `_1g.py`: 81. `_1h.py`: 90. NEW `_1i.py`: 95 LOC.
- `docs/evidence/harness/S447_PROPOSAL_mlb_surface_2026-09-24.md`: 64 lines (ASCII).
- `python -m scripts.platformkit.tracking.contract_preflight --base master --spec docs/evidence/tracking/specs/S447_spec.md --paths` (all candidate files above + this memo)
  -> 0 FAIL, all 9 checks PASS (vocab clean over 14 files; crlf clean, 14 untracked normalise on
  add; loc all .py <= 300; schema additive; head_slice none; spec_threshold 2 literal(s)
  matched; proposed n/a; removed_artifact none; row_duplication none) -- round 8, all fourteen
  candidate files including the tracked proposal twin, the NEW `_1i` test file, and this memo;
  the verdict file `_verdict_s447_1i.md` is excluded, per instruction.

## SPENT-WINDOW statement

`mlb_segmented_r3` (card C2) is SPENT: its one chargeable attempt (S347) has already been read and returned 96 of 96 UNDERPOWERED. This module MUST NOT and does NOT emit a chargeable AHEAD/BEHIND/UNDERPOWERED/INSUFFICIENT from that corpus alone -- `historical_cell()` always returns `label: "historical_descriptive"`, `chargeable: false`, and carries no `verdict` key at all (case 9, structurally enforced, not just by convention). Only the `forward` cell (2026-09-25+ capture) can carry a scored verdict, and one K-budget charge for it is recorded by the orchestrator at landing time, not by this module.

## STEP 2 (not applied here)

A PROPOSED diff for the `surfaces/mlb.json` producer + router wiring was written to `docs/research/organization-sprint/PROPOSED_S447_mlb_surface.md` (not applied; STEP 2 of 2).

## FIX 1c (AMENDMENT 2)

Round 2 (codex sol REJECT, four BLOCKING + one CORRECTION, `_verdict_s447_1c.md`). All five
items fixed; base `git rev-parse HEAD` unmoved at `d6577e1f5...`.

| item | BEFORE (repro) | AFTER (fix) | file:line |
|---|---|---|---|
| (a) exact outcome | `outcome=0.5` scored (`int(0.5)` silently -> `0`) | `_valid_outcome()` validates finite, exactly `0.0`/`1.0`, BEFORE any `int()` | `mlb_predict_live_vs_carry.py:78-86` |
| (b) validate before access | missing `game_id` -> `KeyError`; `home_score="bad"` -> `ValueError`; `1.5` -> silently truncated to `1` | `parse_int_exact()` + `validate_state()` run FIRST in `process_rows`, before any dict access; loader regex captures gated the same way | `mlb_predict_live_vs_carry_io.py:43-70`; `mlb_predict_live_vs_carry.py:123-126` |
| (c) tz-consistent days | zoned cutoff -> `TypeError: Invalid comparison ...` | `canonicalize_calendar_day` strips tz to UTC-naive on both sides before comparing | `mlb_predict_live_vs_carry_io.py:42-59` |
| (d) Q6 word in PROPOSED file | banned word present | reworded in place + Q6-clean tracked twin published | `docs/evidence/harness/S447_PROPOSAL_mlb_surface_2026-09-24.md` |
| (e) CORRECTION | `charged` field name + "edited-in-place" wording wrong | renamed `chargeable`; corrected to "all seven row files untracked"; identities regenerated | memo (this file) |

Regressions (13, `test_mlb_predict_live_vs_carry_1c.py`): `test_amendment2_a_fractional_and_nonfinite_outcome_refused` (x4 params), `test_amendment2_a_exact_zero_and_one_still_score`, `test_amendment2_b_missing_game_id_refused_not_a_keyerror`, `test_amendment2_b_non_numeric_score_refused_not_a_valueerror`, `test_amendment2_b_fractional_score_refused_not_silently_truncated`, `test_amendment2_b_validate_state_checked_before_any_predictor_call`, `test_amendment2_b_loader_fractional_score_refused_not_truncated`, `test_amendment2_b_parse_int_exact_and_validate_state_helpers`, `test_amendment2_c_zoned_cutoff_compares_without_error`, `test_amendment2_c_naive_cutoff_still_unaffected`.

## FIX 1d (AMENDMENT 3)

Round 3 (codex sol REJECT, three BLOCKING, `_verdict_s447_1d.md`). All three fixed; base
`git rev-parse HEAD` unmoved at `f9dfd66eb...`.

| item | BEFORE (repro) | AFTER (fix) | file:line |
|---|---|---|---|
| (a) numeric-string outcome | `outcome='1'` scored (`brier_live=0.25`, `{}` refusals) -- `float('1')` succeeds silently | `_valid_outcome` rejects `bool`/non-`(int,float)` before any `float()`; `'0'`,`'1'`,`False`,`True` refuse `invalid_outcome`; `0`,`1`,`1.0` still score | `mlb_predict_live_vs_carry.py:78-86` |
| (b) validated ints discarded | `validate_state` returned a `bool`; raw `inning='6.0'` reached `int()` in `build_predict_live_fn`, raising `ValueError` | `validate_state` returns a NORMALISED row (parsed `inning`/`home_score`/`away_score`); `process_rows` rebinds `row = validate_state(row)`; every downstream read, incl. `predict_live_fn(row)`, uses it | `mlb_predict_live_vs_carry_io.py:60-83`; `mlb_predict_live_vs_carry.py:119,155` |
| (c) non-mapping / missing game_date | `validate_state([])` -> `AttributeError`; missing `game_date` -> `KeyError` downstream | `validate_state` returns `None` for non-`dict` rows and requires+canonicalises `game_date`; NEW `decode_forward_row` type-checks decoded JSON before `r["corpus"]=...` | `mlb_predict_live_vs_carry_io.py:68-79,127-136` |

Regressions (10, `test_mlb_predict_live_vs_carry_1d.py`): `test_amendment3_a_string_and_bool_outcomes_refused` (x4 params), `test_amendment3_a_int_and_float_zero_one_still_score`, `test_amendment3_b_normalized_ints_reach_the_predictor_never_the_raw_strings`, `test_amendment3_b_validate_state_returns_the_normalized_ints`, `test_amendment3_c_non_mapping_row_refused_not_a_crash`, `test_amendment3_c_missing_game_date_refused_not_a_keyerror`, `test_amendment3_c_validate_state_rejects_list_and_none`. An EXISTING assertion in `test_mlb_predict_live_vs_carry_1c.py` was updated in place to match item (b)'s new normalised-row-or-`None` contract (was `is True`/`is False`).

Test counts: `13 + 10 + 13 + 10 = 46` passed across the four
`test_mlb_predict_live_vs_carry*.py` files, run on the host, per-file.

## FIX 1e (AMENDMENT 4)

Round 4 (codex sol REJECT, three BLOCKING + one CORRECTION, `_verdict_s447_1e.md`). All four
fixed; base `git rev-parse HEAD` unmoved at `66c348b2d...`.

| item | BEFORE (repro) | AFTER (fix) | file:line |
|---|---|---|---|
| (a) form checks | `game_id=[]` -> `TypeError: unhashable type: 'list'` in `process_rows` ((corpus, game_id) dict key); `half='sideways'` scored with `{}` refusals | `game_id` must be a non-empty `str`/`int` (`bool` rejected -- it is an `int` subclass); `home`/`away` non-empty `str`; `half` lower-cased and checked against `("top","bottom")`; `parse_int_exact` itself now rejects `bool` (one root-cause fix, not three call-site guards); scores `>=0`, inning `>=1` -- all refuse `unparseable_state` | `mlb_predict_live_vs_carry_io.py:44-56,61,64-88` |
| (b) receipt overflow | `receipt=1e308` (finite) -> `epoch*1e6` overflows to `inf` -> `round(inf)` raises `OverflowError: cannot convert float infinity to integer` | `_receipt_micros` computes `scaled = epoch*1_000_000` and checks `math.isfinite(scaled)` BEFORE `round`/`int`; non-finite refuses `invalid_receipt_time` | `mlb_predict_live_vs_carry.py:59-68` |
| (c) decoded-list untested | prior regression fed a materialised `[]` straight to `process_rows`; nothing called `decode_forward_row(b"[]")` via `_main`'s own ingestion loop | extracted `ingest_forward_bytes(raw: bytes) -> (rows, counts)` (the exact logic `_main` used inline); `_main` now calls it per file; `REASON_UNPARSEABLE` given one definition in `_io.py`, re-imported by the main module | `mlb_predict_live_vs_carry_io.py:24,159-174`; `mlb_predict_live_vs_carry.py:255-259` |
| (d) CORRECTION | memo said `load_historical` used a `_norm_half()` function | no such function exists; corrected to name the actual mechanism, the inline conditional `"bottom" if m.group(4).lower().startswith("bot") else "top"` | `mlb_predict_live_vs_carry_io.py:172`; memo "Real state_summary format" section above |

All three repros above were confirmed interactively pre-fix (raw row unchanged / `OverflowError`
/ no test through the real path) and post-fix, matching the AFTER column exactly.

Regressions (12, NEW `tests/platformkit/eval_gate/test_mlb_predict_live_vs_carry_1e.py`): `test_amendment4_a_list_game_id_refused_not_a_typeerror`, `test_amendment4_a_sideways_half_refused_not_scored`, `test_amendment4_a_half_case_insensitive_still_scores`, `test_amendment4_a_negative_score_refused`, `test_amendment4_a_inning_zero_refused`, `test_amendment4_a_boolean_score_refused` (x2 params: `True`, `False`), `test_amendment4_a_empty_string_game_id_refused` (updated in round 5 per verdict item 6, see FIX 1f), `test_amendment4_a_valid_row_still_scores_and_normalizes_half`, `test_amendment4_b_finite_huge_receipt_refused_not_an_overflowerror`, `test_amendment4_c_decoded_list_counted_through_the_extracted_ingestion_function`, `test_amendment4_c_ingest_forward_bytes_tags_and_counts_mixed_lines`.

Test counts: `13 + 10 + 13 + 10 + 12 = 58` passed across the five
`test_mlb_predict_live_vs_carry*.py` files, run on the host, per-file
(`python -m pytest <file> -q -p no:cacheprovider`).

## FIX 1f (AMENDMENT 5)

Round 5 (codex sol REJECT, FIVE BLOCKING + one CORRECTION -- corrected count, AMENDMENT 6 item
c; this memo previously and wrongly said four -- `_verdict_s447_1f.md`). All six fixed;
candidate HEAD unmoved (full sha in A9 below).

| item | BEFORE (repro) | AFTER (fix) | file:line |
|---|---|---|---|
| (a) Q9 no differential series | artifact carried only summary stats; CI could not be recomputed without reopening source inputs (`HAS_DIFFERENTIAL_SERIES False`) | `process_rows` archives `paired_diff`, `carry`, and a reconstructible `state` dict per unit; `historical_cell`/`forward_cell` carry a `rows` list beside the summary; `cluster_bootstrap` on `rows` alone matches `paired_diff` exactly | `mlb_predict_live_vs_carry.py` (process_rows); NEW `mlb_predict_live_vs_carry_report.py` |
| (b) Q5 one corpus said AHEAD | 30 games, one corpus, losses 0.0/1.0 -> `verdict='AHEAD'`, no `min_corpora_eff` (`HAS_MIN_CORPORA_EFF False`) | `forward_cell` counts distinct `corpus` tags (`min_corpora_eff`); `< 2` -> `SINGLE-WINDOW` (numbers still reported); `>= 2` -> gate_a0's verdict as before | `mlb_predict_live_vs_carry_report.py` |
| (c) Q4 hand-built date slice | `games_asof` used a bare `date < cutoff` slice, no purge/embargo | routes through the shared `EMBARGO_DAYS` constant (`cpcv_engine`, sourced from `walkforward.py`, reused unedited): a game within `EMBARGO_DAYS` calendar days of the cutoff is purged even though it is `< cutoff` | `mlb_predict_live_vs_carry_io.py` (games_asof) |
| (d) malformed half silently -> top | `half=sideways` -> `LOADER_HALF top` | loader accepts only `top`/`bot`/`bottom` (normalised via `_LOADER_HALVES`); any other spelling counts `unparseable_historical_row` | `mlb_predict_live_vs_carry_io.py` (load_historical) |
| (e) BLOCKING, A9 base false | memo's A9 base was a corrupted, non-existent sha (an orchestrator short-sha substitution) | full 40-hex shas read fresh via `git rev-parse` at fix time, labelled candidate HEAD / verification base | memo (this file), A9 section below |
| (f) CORRECTION | empty-game-id test asserted only `validate_state(...) is None` | passes the row through `process_rows`, asserts `refusals == {REASON_UNPARSEABLE: 1}` | `test_mlb_predict_live_vs_carry_1e.py` |

Ripple from (c): six PRE-EXISTING date-literal tests (case 4, case 11, `amendment_g`, both
`amendment2_c` tests) had dates widened past the embargo band to keep testing their ORIGINAL
point, not land inside the new purge band by accident. Ripple from (b): case 6's expected
verdict is now SINGLE-WINDOW, not AHEAD/BEHIND (its construct IS the Q5 regression); its
paired_diff SIGN assertion is unchanged. Item (f): the empty-game-id test in
`test_mlb_predict_live_vs_carry_1e.py` now asserts `refusals == {REASON_UNPARSEABLE: 1}`
through `process_rows`, not `validate_state(...) is None` alone.

Regressions (6, NEW `tests/platformkit/eval_gate/test_mlb_predict_live_vs_carry_1f.py`): `test_amendment5_a_rows_list_reconstructs_the_summary`, `test_amendment5_b_single_corpus_forward_cell_is_single_window`, `test_amendment5_b_two_independent_corpora_can_reach_ahead`, `test_amendment5_c_embargo_band_excludes_near_cutoff_rows_outside_included`, `test_amendment5_d_loader_rejects_non_standard_half_spelling`, `test_amendment5_d_loader_accepts_bot_and_bottom_spellings`.

Test counts: `13 + 10 + 13 + 10 + 12 + 6 = 64` passed across the six
`test_mlb_predict_live_vs_carry*.py` files, run on the host, per-file
(`python -m pytest <file> -q -p no:cacheprovider`).

## FIX 1g (AMENDMENT 6)

Round 6 (codex sol REJECT, two BLOCKING, `_verdict_s447_1g.md`). Both fixed; candidate HEAD
unmoved (full sha in A9 below).

| item | BEFORE (repro) | AFTER (fix) | file:line |
|---|---|---|---|
| (a) corpus_unit lost at ingestion | `ingest_forward_bytes` overwrote every row's identity with the constant `"forward"`; input corpora `['w1','w2']` -> ingested corpora `['forward']` -> `min_corpora_eff=1, verdict='SINGLE-WINDOW'` even with two real windows; `min_corpora_eff` also stored the OBSERVED count, not a floor | `ingest_forward_bytes` validates and preserves a `corpus_unit` (non-empty scalar, bool rejected) SEPARATELY from the `corpus` cell label; `process_rows` carries it into each scored row; `forward_cell` counts DISTINCT `corpus_unit` values as `n_corpora_observed` and reports the constant replication floor under `min_corpora_eff` (`MIN_CORPORA_EFF=2`) | `mlb_predict_live_vs_carry_io.py` (ingest_forward_bytes); `mlb_predict_live_vs_carry.py` (process_rows); `mlb_predict_live_vs_carry_report.py` (forward_cell) |
| (b) no charged-window floor | a forward row dated `2026-09-24` scored normally (`n_ticks=1`, no refusal, `verdict='SINGLE-WINDOW'`) | forward rows (`corpus=="forward"`) dated strictly before `FORWARD_WINDOW_START = "2026-09-25"` refuse before scoring, counted `forward_before_window`; historical rows are unaffected | `mlb_predict_live_vs_carry.py` (process_rows) |

Ripple: two PRE-EXISTING tests updated in place -- `test_amendment_i_corpus_start_before_tick_refused_not_crashed` (1b) moved its dates on/after 2026-09-25 so the new window floor does not intercept it first; the two `min_corpora_eff` FIX 1f tests (base 1f file) now assert the renamed `n_corpora_observed` for the observed count and `min_corpora_eff == 2` (the floor) in both the one- and two-window cases, and the two-window case varies `corpus_unit`, not `corpus`; `test_amendment4_c_ingest_forward_bytes_tags_and_counts_mixed_lines` (1e) now includes a `corpus_unit` on its one decodable line.

Regressions (6, NEW `tests/platformkit/eval_gate/test_mlb_predict_live_vs_carry_1g.py`): `test_amendment6_a_two_real_corpus_units_survive_ingestion_and_escape_single_window`, `test_amendment6_a_one_real_corpus_unit_stays_single_window`, `test_amendment6_a_missing_corpus_unit_refused_as_unparseable_state`, `test_amendment6_b_forward_row_before_window_start_refused`, `test_amendment6_b_forward_row_on_window_start_admitted`, `test_amendment6_b_historical_rows_unaffected_by_the_forward_window_floor`.

Test counts: `13 + 10 + 13 + 10 + 12 + 6 + 6 = 70` passed across the seven
`test_mlb_predict_live_vs_carry*.py` files, run on the host, per-file
(`python -m pytest <file> -q -p no:cacheprovider`).

## FIX 1h (AMENDMENT 7)

Round 7 (codex sol REJECT, three BLOCKING, `_verdict_s447_1h.md`). All three fixed; candidate
HEAD unmoved (full sha in A9 below).

| item | BEFORE (repro) | AFTER (fix) | file:line |
|---|---|---|---|
| (a) hand-built date mask, Q4 not implemented | `games_asof` imported `EMBARGO_DAYS` but only compared it to a computed date gap itself; dates `['2026-06-10','2026-06-17']` vs cutoff `2026-06-20` -> `['2026-06-10']` but `shared_split_called=False` | each strictly-past candidate is asked of `cpcv_engine._purged` (imported unedited as `_shared_purge_route`), via a sentinel team pair that isolates its calendar-day embargo term; same admitted dates, now with `shared_split_called=True` | `mlb_predict_live_vs_carry_io.py` (games_asof) |
| (b) corpus_unit not canonicalised | 30 forward rows split between `corpus_unit=1` (int) and `corpus_unit="1"` (str) -> `n_corpora_observed=2, verdict='AHEAD'` | `ingest_forward_bytes` canonicalises every admitted unit to `str(unit)`; both spellings collapse to one canonical `"1"` -> `n_corpora_observed=1, verdict='SINGLE-WINDOW'` | `mlb_predict_live_vs_carry_io.py` (ingest_forward_bytes) |
| (c) `_valid_prob` accepted bool/numeric strings | `carry=True`, predictor result `False`, `outcome=0` -> `n_scored=1, refusals={}, brier_live=0.0, brier_carry=1.0` | `_valid_prob` rejects `bool`/non-`(int,float)` before any `float()`, exactly like `_valid_outcome`; `True`/`False`/`"0.5"` all refuse for carry, mid, and the model's own output | `mlb_predict_live_vs_carry.py` (_valid_prob) |

No pre-existing test needed updating: (a) preserves the identical admitted-date output already
exercised (same symmetric embargo, now called rather than hand-computed); (b)/(c) only tighten
validation no prior construct exercised (a mismatched-representation unit, a bool/string prob).

Regressions (11, NEW `tests/platformkit/eval_gate/test_mlb_predict_live_vs_carry_1h.py`): `test_amendment7_a_games_asof_routes_through_the_shared_split_function`, `test_amendment7_b_mixed_int_and_string_corpus_unit_counts_as_one`, `test_amendment7_c_boolean_and_string_carry_refused` (x3 params), `test_amendment7_c_boolean_and_string_mid_refused` (x3 params), `test_amendment7_c_boolean_and_string_model_output_refused` (x3 params).

Test counts: `13 + 10 + 13 + 10 + 12 + 6 + 6 + 11 = 81` passed across the eight
`test_mlb_predict_live_vs_carry*.py` files, run on the host, per-file
(`python -m pytest <file> -q -p no:cacheprovider`).

## FIX 1i (AMENDMENT 8)

Round 8 (codex sol REJECT, three BLOCKING, `_verdict_s447_1i.md`). All three fixed; candidate
HEAD unmoved (full sha in A9 below).

| item | BEFORE (repro) | AFTER (fix) | file:line |
|---|---|---|---|
| (a) predictor could reach outcome | `predict_live_fn(row)` got the full row; `lambda r: float(r["outcome"])` scored `[0,1]` as `brier_live=[0.0,0.0]`, `refusals={}` | NEW `_model_view(row)` allowlists only `game_date`/`home`/`away`/`inning`/`half`/`home_score`/`away_score`/`corpus_unit`; `predict_live_fn(_model_view(row))`; a `KeyError` (outcome/carry/mid unreachable) is caught and counted `invalid_probability`, never scored | `mlb_predict_live_vs_carry.py` (_model_view, process_rows) |
| (b) integers routed through float | `parse_int_exact("9007199254740993")` -> `9007199254740992` (float64 precision loss) | `int` returned directly (never `float()`); `str` validated as a finite integral `Decimal` (exact at any magnitude); `float` accepted only when integral AND `abs(x) <= 2**53` | `mlb_predict_live_vs_carry_io.py` (parse_int_exact) |
| (c) whitespace-only unit admitted | 15 rows `'   '` + 15 `'w1'` -> `n_corpora_observed=2, verdict='AHEAD'`, no refusals | canonicalisation is `str(unit).strip()`; an empty result refuses `unparseable_state`; the stripped value is stored, so `' w1 '` and `'w1'` are one unit | `mlb_predict_live_vs_carry_io.py` (ingest_forward_bytes) |

Ripple: `test_case5_brier_exact_two_game_synthetic_corpus` (base file) branched its stub
predictor on `r["game_id"]`, which is not in the allowlist; rewritten to use an external
prediction sequence (row order) instead, preserving the exact same Brier assertions.

Regressions (7, NEW `tests/platformkit/eval_gate/test_mlb_predict_live_vs_carry_1i.py`): `test_amendment8_a_predictor_cannot_reach_the_settled_outcome`, `test_amendment8_a_predictor_cannot_reach_carry_or_mid_either`, `test_amendment8_a_model_view_keys_are_exactly_the_allowlist`, `test_amendment8_b_large_string_integer_round_trips_exactly`, `test_amendment8_b_unsafe_large_float_refused`, `test_amendment8_c_whitespace_only_unit_refused_padded_unit_collapses`, `test_amendment8_c_padded_spelling_of_one_unit_collapses_with_the_bare_spelling`.

Test counts: `13 + 10 + 13 + 10 + 12 + 6 + 6 + 11 + 7 = 88` passed across the nine
`test_mlb_predict_live_vs_carry*.py` files, run on the host, per-file
(`python -m pytest <file> -q -p no:cacheprovider`).

## NOT VERIFIED

- No real run: `load_historical()` was not invoked against `data/cache/ingame_grade_joined/mlb_segmented_r3` (barred from `data/cache` here); the forward capture does not exist yet (today is 2026-09-24; it starts 2026-09-25). Expected first real-run result is `INSUFFICIENT`, not a failure.
- The historical adapter's field-name assumptions (`home`/`away`/`pregame_prior`/`market_prob`) and `build_predict_live_fn`/`get_asof_predictor` against the real `domains/mlb/predictor.py` + `data/domains/mlb/games.parquet` are UNVERIFIED end-to-end; only pure sub-functions with an injected stub factory were exercised, per the CONSTRUCT-only acceptance rule.
- NEW GAPS (not yet resolved, none read in this worktree): gate_a0's real joined-row schema; `CorpusStartBeforeTick`/`mid_receipt` against the real corpus; `EMBARGO_DAYS=3`'s effect on real `mlb_segmented_r3` date density via the shared `_purged` route; whether real forward JSONL rows carry a `corpus_unit` field at all (or distinct nights get distinct values); `forward_before_window` against a real row; and AMENDMENT 8's model-view/exact-integer/stripped-unit fixes against a real forward capture.
- Per SPENT-WINDOW (CORPUS_DATA_CARDS_2026-09-22.md C2): this worktree spends no charge from `mlb_segmented_r3` (S347, already read) and emits no chargeable verdict from it -- `historical_cell()` stays structurally incapable of one (case 9). The only chargeable cell is `forward`, gated on >= 30 forward games AND >= 2 `corpus_unit` values from the 2026-09-25+ capture; zero exist today.
- Round 2-8 (FIX 1c through 1i): the independent verifier's own sandbox could not run this row's `tmp_path`-based tests at all -- every CONSTRUCT case failed during pytest setup (`_verdict_s447_1c.md` through `_verdict_s447_1i.md`, all "NOT VERIFIED"). All 88 tests in this memo were instead run on the host, per-file, and passed; not independently re-run inside the sandbox.
