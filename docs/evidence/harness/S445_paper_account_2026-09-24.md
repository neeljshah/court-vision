# S445 paper account: PREPARE candidate; NOT VALIDATED

Build lane: Windows worktree C:/Users/neelj/nba-harness-h101, branch `harness-h101`. This memo states full
40-hex shas read fresh from git at fix time (AMENDMENT 8(c) -- an earlier round's memo carried a
NON-EXISTENT sha produced by a short-sha substitution that overwrote every prior sha token in this file
with one truncated candidate sha; that substitution error, not a hand edit, is disclaimed here and not
repeated; a later round's memo also drifted its OWN file count and equal/not-equal claim out of sync
between its top and bottom statements -- both are now derived from ONE fresh read, stated once, referenced
not repeated): **candidate HEAD** (this worktree, `git rev-parse HEAD`) =
`422f32335c244b1b29da37e8feef8708883371f4`. **Verification base**
(`git -C C:/Users/neelj/nba-ai-system rev-parse master`) = `422f32335c244b1b29da37e8feef8708883371f4`.
These are EQUAL: the orchestrator fast-forwarded this worktree onto the current master immediately
before resubmission (AMENDMENT 7(b): master moves between fix and verify; frozen/imported bytes
cross-checked identical against that sha in A9 below). AMENDMENT 9(b)/(c): `git diff --stat` cannot itself list
untracked files, so it is empty for tracked paths; `git status --porcelain` separately lists the thirteen
owned code/test files plus this memo (fourteen total), all still untracked (see the line below the A9
table).
Construct tests only; no network, no pod, no real capture read, no path under `data/`, no runtime caller added.
Binding source: `docs/evidence/tracking/specs/S445_spec.md` (base spec + AMENDMENT 1(a)-(l) +
AMENDMENT 2(a)-(f) + AMENDMENT 3(a)-(d) + AMENDMENT 4(a)-(c) + AMENDMENT 5(a)-(c) + AMENDMENT 6(a)-(c) +
AMENDMENT 7(a)-(c) + AMENDMENT 8(a)-(c) + AMENDMENT 9(a)-(c) + AMENDMENT 10(a)-(b) + AMENDMENT 11(a)-(d)).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, A9, B1-B11, Q1-Q9.

## Single problem (quoted, re-verified on this tree)

`scripts/platformkit/execution/fill_realism.py:91` inside `_prepare()`'s per-book-row loop:
`ledger = ReservationLedger([], clock=lambda: clock, ttl_s=counts['_ttl'])` -- one ledger built empty and
discarded per row; nothing carries reservation state to the next row, contract or game.
`scripts/platformkit/execution/position_caps.py:27` `check_caps` is a pure function over one snapshot; no
caller anywhere accumulates a snapshot across more than one decision. `quote_reservation.py:83-118`
`ReservationLedger` already IS a continuous-history primitive -- exactly the mechanism `fill_realism.py`
throws away every row instead of reusing across a night.

## FIX 1b (AMENDMENTS 1-2), condensed -- 2026-09-24

Round 1 review (Opus tier 2, 12 items + 2 NEW GAPs; codex sol, 5 blockers + 1 correction) rejected the
original 13/13 build; applied in full: `order_mismatch_refused`/`fill_on_released_order` guards before any
event is built; `order_id_reuse_refused`; `receipt_id` is the de-dup key WITHIN a family (families otherwise
independent; `by_family`/`by_game_id` reporting-only); canonical sort key `(instant, receipt_id, ticker,
game_id, order_id, sorted-JSON)` with duplicate-vs-conflict refusals and order-independent replay;
validate-then-coerce with a fixed refusal vocabulary, never raise; `qty` is str/int only; real ASCII JSONL
persistence (`paper_account_log.py`, NEW) with temp-then-`os.replace` and sorted replay; partial-fill pairs
plus CLI byte-for-byte reproduction; fills run `check_caps` prospectively against the real post-fill
snapshot (`quote_reservation.submit()`'s `max(cap, pre-event usage)` pattern), never the additive
reserve-style check that double-counts a fill's own open reservation.

NEW GAPS recorded per AMENDMENT 1(l) for a later row, not fixed here: `position_reducers.py:69` silently
no-ops a repeated submit/fill identity for any OTHER caller (this row's own per-family de-dup never depends
on it); the landed reducer places no guard against a fill on an already-terminal order (`fill_on_released_order`
here is a caller-side guard, not a reducer fix).

## Before-condition (S2, re-measured on this worktree)

`fill_realism.py:91` matches the spec's quoted line exactly, inside `_prepare()`. `position_exposure.py:
16-24` `exposure_book`: an open, unfilled reservation already counts toward per_game/correlated/global
exposure, not only a fill. `position_ledger.py:32-43` `EVENT_TYPES`: `cancel`/`reserve` are this row's own
vocabulary, mapped onto the landed `cancel_confirmed`/`submit`. `position_reducers.py:140-177`
`positions(events)`: "same events in, same snapshot out, every time" -- this row's restart-identity case
rests on exactly that docstring guarantee. S411 memo NOT VERIFIED carried forward unchanged: no
observation of queue position/counterfactual ownership; this row still only touches reservation-history
continuity, not fill probability.

## Input schema (one JSON object per decision receipt, ASCII, ingested via `PaperAccount.ingest`)

`kind` (`reserve|fill|partial_fill|cancel|expire`), `family`, `ticker`, `game_id` (non-empty strings), `side`
(`yes|no`), `qty` (positive whole contracts, str/int only), `receipt_id` (non-empty, unique per decision
WITHIN ITS FAMILY; byte-identical replay is `duplicate_fill_refused`, same-id/different-content is
`receipt_id_conflict_refused`), `instant` (`parse_venue_time`-parseable ISO8601 -- receipts consumed in
`(instant, receipt_id, ticker, game_id, order_id, canonical JSON)` order, never file order), `order_id`
(optional; required, and must already exist on the same ticker/game_id/side, for fill/partial_fill/
cancel/expire; defaults to `receipt_id` for `reserve`), `price_cents` (required for reserve/fill/
partial_fill, 1-99; absent for cancel/expire).

Internally each `kind` maps onto one landed `position_ledger.new_event` type: `reserve -> submit`,
`fill -> fill`, `partial_fill -> partial_fill`, `cancel -> cancel_confirmed`, `expire -> expire`. `caps` is
supplied whole by the caller at construction and passed through to `check_caps` untouched -- no cap value is
declared, read as a default, or altered inside `paper_account.py`.

## Case table (spec's 13 cases + `test_artifact_is_ascii_json_with_strict_int_counts`, 13 tests total, 13
passed; `tests/platformkit/execution/test_paper_account.py`)

| # | Spec case | Test |
|---|---|---|
| 1 | two simultaneous same-game contracts share one correlated cap | `test_two_simultaneous_same_game_contracts_share_correlated_cap` |
| 2 | partial fill then completion accumulates | `test_partial_fill_then_completing_fill_accumulates` |
| 3 | TTL expiry counts `expired`, releases room | `test_ttl_expiry_releases_room` |
| 4 | restart mid-night reproduces the identical sequence, byte for byte | `test_restart_mid_night_replay_is_byte_identical` |
| 5 | duplicated fill receipt refused, exactly one fill applied | `test_duplicated_fill_receipt_refused` |
| 6 | cap breach on the second contract refused, first unaffected | `test_cap_breach_second_refused_first_reservation_unaffected` |
| 7 | shuffled input order gives identical output | `test_shuffled_input_order_gives_identical_output` |
| 8 | cancellation releases room, never occupies it forever | `test_cancellation_releases_room` |
| 9 | two different games, one global cap enforces across both | `test_simultaneous_contracts_across_two_games_global_cap` |
| 10 | empty night: all-zero counts, valid artifact, never a crash | `test_empty_night_all_zero_valid_artifact` |
| 11 | unknown/malformed kind refused by name, never dropped/crashed | `test_unknown_and_malformed_kind_refused_and_counted` |
| 12 | isolated-per-snapshot allowance defect does not reappear | asserted inside case 1's test |
| 13 | fill_realism/position_caps/quote_reservation byte-identical; imports used by identity | `test_frozen_imports_byte_identical_and_used_by_identity` + `git status --short` below |

## A9 -- exact source of every candidate and must-not-move file (absolute path, bytes, sha256 of
LF-normalised bytes -- `read_bytes().replace(b"\r\n", b"\n")` -- recomputed on this tree as the FINAL edit,
against candidate HEAD `422f32335c244b1b29da37e8feef8708883371f4` (equal to the live master tip after the
orchestrator fast-forward -- see the revision statement); every frozen/imported row
cross-checked against `git show 422f32335c244b1b29da37e8feef8708883371f4:<path>` and
`git show 422f32335c244b1b29da37e8feef8708883371f4:<path>` (LF-normalised) -- all eight matched both)

| path | bytes (LF) | sha256 (LF-normalised) |
|---|---:|---|
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\paper_account.py (owned; fix 1k: AMENDMENT 11(a)/(c)) | 15951 | cd38d1c77ff4b9cb25a7c77ee196e0cb466df360863f036aec9a21eadadd6ce4 |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\paper_account_log.py (owned; fix 1k: AMENDMENT 11(b)) | 12309 | 860df6e0616f791b5054385f307aa961fea34f05edf65d375ce9d67f832ab491 |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account.py (owned; fix 1k: 3 instants corrected) | 10641 | 2829f6789b80ac8eb6a18f6128fedb99af5dfda5a114e7d564796caf1dbfcd77 |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1b.py (owned; fix 1k: 1 instant corrected) | 11132 | aecc47cfb8db5f0c0d93d42e910723bab94b6f292c162aa10823ffb26f8e8281 |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1c.py (owned, unchanged) | 4542 | be372b2563d2081c289e51515ff47496c8f3c5aa3d5dac342dd0b0621b290b0c |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1d.py (owned, unchanged) | 4562 | ffb843ace50133fd4215d40f7e01464276efa949a35d2aa240c53d853c29bd44 |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1e.py (owned, unchanged) | 3301 | 03afe67c778c6500e8c7d57a56ff05045fac41cfac442088db3672e3d4b74e2d |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1f.py (owned; fix 1k: helper updated for dict-pairs shape) | 3726 | f47cf30b6099a381884c585306ce734dc79139d22493d24e251d72d82d4a8700 |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1g.py (owned; fix 1k: helper + one test updated for dict-pairs shape) | 6011 | 3035621a8335103925949923f457a249bf5d0abb954329160f6e5a6d2e54c77d |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1h.py (owned; fix 1k: helper updated for dict-pairs shape) | 5214 | 87426074ebd02506c415c32aa11a0cdb5fc30a4d13736e83cc779448daee42de |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1i.py (owned, unchanged) | 3138 | f91c7db6bb861c98b21c38a8c42cdbf2e2f4f3fd6f13ff3e9934f1acebd1a27a |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1j.py (owned, unchanged) | 3743 | 47a1cd52a4a2ee4ceb6a3ef9753e5a70b9459eecbf6147a50d717c66288a55e1 |
| C:\Users\neelj\nba-harness-h101\tests\platformkit\execution\test_paper_account_1k.py (NEW, owned, AMENDMENT 11 regressions) | 4303 | ff1a4854c053f1d0761fbe4c4ee28f85ad08254ba3002e3f70f14251207ca89b |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\fill_realism.py (must not move) | 18642 | bf3c56b76d2289517a5001e956e4dda534ec32094db7775525f57e28da2d5b42 |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\position_caps.py (must not move) | 6806 | 0b6ce2732f89d20900f5332c51df448c5270839e133e97d19b589cbb12a83f56 |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\quote_reservation.py (must not move) | 12374 | 11f315fd937469631291e2bf4c94840c9991828362fcddeb8eb595b20a3ed24e |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\position_ledger.py (imported read-only) | 13311 | daf67b40d5ac225a35b31618bf78490477eb0227f23bfd1675052b9438925885 |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\position_reducers.py (imported read-only) | 11691 | c8298b2f1daa4628ff5b9b6bcd2b85600951e5a86258d0594a7359f9b442ac8d |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\position_decimal.py (imported read-only) | 2315 | 28896f74b10fcf6cd44be7fd78800f4b2cdacd41631659b4e4582625e90f83d1 |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\venue_time.py (imported read-only) | 1972 | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 |
| C:\Users\neelj\nba-harness-h101\scripts\platformkit\execution\position_exposure.py (imported read-only) | 1368 | 6f9379827eafa4972efbe6501d08bf1f6c311c00bd9cdef6b5139dfa3e465910 |

Note: sha256 above is over LF-normalised bytes, so it differs from raw-byte digests recorded in earlier
fix rounds of this memo for the SAME files (this Windows checkout carries CRLF on disk); `git diff --stat
master -- <every frozen path above>` is empty, confirming byte-for-byte identity to the live master tip.

`git status --porcelain` after this fix round (recomputed): **fourteen** untracked paths -- the thirteen
candidate code/test files above (fix 1j had twelve; fix 1k adds `test_paper_account_1k.py`) plus this
memo. No landed file modified; `git rev-parse HEAD` is `422f32335c244b1b29da37e8feef8708883371f4`, equal
to `master` this round (sol round 11 CORRECTION applied by the orchestrator before landing; the
orchestrator fast-forwarded this worktree onto the current master immediately before landing).

## LOC and tests

`scripts/platformkit/execution/paper_account.py`: 300 lines (cap 300), fix 1k: AMENDMENT 11(a)/(c).
`scripts/platformkit/execution/paper_account_log.py`: 272 lines (cap 300), fix 1k: AMENDMENT 11(b).
`tests/platformkit/execution/test_paper_account.py`/`_1b.py`: 3 same-instant sequencing fixtures each
corrected to distinct increasing instants (AMENDMENT 11(a) exposed arrival-order reliance); counts/line
totals otherwise unchanged. `_1c.py`..`_1j.py`: UNCHANGED (97/108/76/74/118/108/63/75 lines;
3/7/3/3/6/5/2/3 tests); `_1g.py`/`_1h.py`/`_1f.py` each updated ONE helper for the new dict-pairs envelope
shape (AMENDMENT 11(b)), test bodies/counts unchanged.
`tests/platformkit/execution/test_paper_account_1k.py`: 95 lines, 4 tests (NEW, AMENDMENT 11 regressions).
Per-file `python -m pytest <file> -q -p no:cacheprovider` (never `pytest tests/`), one file at a time:
test_paper_account.py 13 passed; _1b 16; _1c 3; _1d 7; _1e 3; _1f 3; _1g 6; _1h 5; _1i 2; _1j 3; _1k 4.
Combined: **65/65 passed** (13+16+3+7+3+3+6+5+2+3+4), replacing the fix-1j memo's "61/61" claim.

Landed test files re-run unchanged, per file: `test_position_caps.py` 42 passed, `test_quote_reservation.py`
45 passed, `test_fill_realism.py` 34 passed, `tests/platformkit/test_loc_rail_scope.py` 1 passed.

`python -m scripts.platformkit.tracking.contract_preflight --base master --spec docs/evidence/tracking/specs/S445_spec.md --paths scripts/platformkit/execution/paper_account.py scripts/platformkit/execution/paper_account_log.py tests/platformkit/execution/test_paper_account.py tests/platformkit/execution/test_paper_account_1b.py tests/platformkit/execution/test_paper_account_1c.py tests/platformkit/execution/test_paper_account_1d.py tests/platformkit/execution/test_paper_account_1e.py tests/platformkit/execution/test_paper_account_1f.py tests/platformkit/execution/test_paper_account_1g.py tests/platformkit/execution/test_paper_account_1h.py tests/platformkit/execution/test_paper_account_1i.py tests/platformkit/execution/test_paper_account_1j.py tests/platformkit/execution/test_paper_account_1k.py docs/evidence/harness/S445_paper_account_2026-09-24.md` -> 9 PASS, 0 FAIL over 14 files (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication all PASS; re-run after fix 1k).

## PROPOSED follow-up (not applied)

`docs/research/organization-sprint/PROPOSED_S445_fill_realism_integration.md` (gitignored locally; not
re-created by this fix round) states, as a diff not applied, how a future owner would replace
`fill_realism.py:91`'s per-row `ReservationLedger([], ...)` with a shared `PaperAccount`, including the
prospective fill cap-check. `fill_realism.py` stays untouched by this row.

## REAL RUN

None. No runtime caller feeds real night events yet; the first real run is that same PROPOSED follow-up,
producing a real night's receipts from capture -- a separate row.

## FIX HISTORY 1c-1i (AMENDMENTS 3-9), one line per round (further condensed
this round to hold the 300-line cap; full reproductions for each are in this
memo's own edit history and the corresponding `_verdict_s445_1<x>.md`)

- **1c** (AMENDMENT 3): malformed lines persist too; `receipt_id` identity claimed BEFORE cap/reducer eval
  (a later same-id receipt is duplicate/conflict-refused even if the first was itself refused); canonical
  replay IS the state once `log_path` is set. `test_paper_account_1c.py` 3 passed; combined 32/32.
- **1d** (AMENDMENT 4): an explicit top-level `kind` field distinguishes a malformed line from a receipt
  (no key-sniffing collision); `order_id` validate-then-coerce (`0`/`False`/`""` refused, never silently
  defaulted). `test_paper_account_1d.py` 7 passed; combined 39/39.
- **1e** (AMENDMENT 5): construction is ONE read/replay/write, never one write per loaded receipt (no
  lost-prefix-on-crash risk); `Decimal`/non-finite `qty` tagged so it is persistable, never raising.
  `test_paper_account_1e.py` 3 passed; combined 42/42.
- **1f** (AMENDMENT 6): a collision-proof `{"t":tag,"v":value}` envelope replaces the fix-1e bare-tag
  encoding (an ordinary payload dict shaped like the old tag no longer misdecodes); a corrupted envelope
  line counts `malformed_line`, never raises. `test_paper_account_1f.py` 3 passed; combined 45/45.
- **1g** (AMENDMENT 7): every invalid envelope node (unhashable tag/value, invalid null shape) raises
  `_EnvelopeError`, never a bare `TypeError`, so `read_log` refuses instead of crashing.
  `test_paper_account_1g.py` 6 passed; combined 51/51.
- **1h** (AMENDMENT 8): the envelope is strict in both directions (float requires an actual finite float,
  int excludes bool, every node's key set is exactly `{t,v}` or `{t}` alone for null); the CLI resolves a
  relative input path to absolute before reading/hashing/recording; this memo's revision shas, once
  corrupted by a short-sha substitution, are read fresh from git every round from here on.
  `test_paper_account_1h.py` 5 passed; combined 56/56.
- **1i** (AMENDMENT 9): canonical receipt identity (`_canon`) derives from the SAME typed envelope
  persistence writes, never `repr()`/insertion order, so two equal payloads built with reversed key
  insertion canonicalise identically before and after a reload. `test_paper_account_1i.py` 2 passed;
  combined 58/58.

## FIX 1j (AMENDMENT 10), condensed

Round 9 review (codex sol REJECT, one blocking). `_encode`'s catch-all coerced any unsupported type to a
bare string (`qty=Fraction(3,1)` refused live -- neither `str` nor `int` -- but persisted as
`{"t":"str","v":"3"}`; on reload `_decode` returned the real STRING `"3"`, which PASSED the same qty check
and flipped the outcome from refused to a live `reserved` -- a restart silently accepting a
previously-refused input). Fix: the catch-all now emits `{"t":"unsupported","v":repr(value)}`, decoded as
a new private `Unsupported` sentinel (never a `str`/`int`/`bool`), so the reloaded value fails the SAME
validator check the original type did, with no validator change needed; `_encode` re-emits the identical
envelope for an `Unsupported` input (idempotent). AFTER: `{'invalid_qty':1,'reserved':0}` identically
before and after a real reload. `test_paper_account_1j.py` (3 tests, real `tmp_path` I/O) -- 3 passed;
combined 61/61.

## FIX 1k (AMENDMENT 11)

Round 10 review (codex sol REJECT, three blocking; the AMENDMENT 10 sentinel, preflight, frozen modules
and equal role shas confirmed at fix-1j time).

**(a) the non-persistent path must canonically replay too** (`PaperAccount.ingest`, was line 157). BEFORE:
`log_path=None` processed each new receipt ONCE, incrementally, against whatever state prior calls left --
so arrival order decided the outcome (`['ob','oa']` kept order `ob`; `['oa','ob']` kept order `oa`, two
different risk decisions for the identical two receipts under one cap). Fix: EVERY `ingest()` -- log_path
or not -- clears family state and calls `replay_and_persist` over the complete receipt set in canonical
`(instant, receipt_id, ...)` order; only the disk write inside it stays conditioned on `log_path`. AFTER:
both arrival orders accept the SAME order id (`oa`), identical counts
(`test_reversed_arrival_without_log_path_accepts_same_order_id`). This exposed three EXISTING tests
(`test_partial_fill_then_completing_fill_accumulates`, `test_ttl_expiry_releases_room`,
`test_cancellation_releases_room` in `test_paper_account.py`; `test_fill_on_released_order_regression` in
`_1b.py`) that relied on same-instant arrival order for their own sequencing -- each now given distinct,
increasing `instant`s; assertions and counts unchanged.

**(b) dictionary keys are encoded too** (`paper_account_log.py` `_encode`/`_decode`). BEFORE: a dict's "v"
mapped raw Python keys straight through, so `qty={Fraction(3,1): 'x'}` crashed `json.dumps` with
`TypeError: keys must be str, int, float, bool or None, not Fraction`, even though the live validator had
already refused it as `invalid_qty` -- a refusal that could never reach disk. Fix: a dict's "v" is now a
canonically sorted list of `[encoded_key, encoded_value]` pairs; an unsupported key type becomes the
`Unsupported` sentinel same as any value. AFTER: `invalid_qty=1, reserved=0` before AND after a real
reload, never raising (`test_fraction_dict_key_qty_refused_identically_before_and_after_reload`; direct
check `test_encode_decode_dict_with_unsupported_key_direct`). `test_paper_account_1g.py`'s
`test_dict_non_str_key_refused` and the `_write_corrupt_qty_envelope` helpers in `_1f.py`/`_1g.py`/`_1h.py`
were updated for the new pairs shape; no test intent changed.

**(c) cap-validation failures speak the fixed vocabulary** (`PaperAccount._process`, was lines 234-250).
BEFORE: `caps={'global': 1.5}` made the frozen `check_caps` itself raise `ValueError("invalid global:
expected Decimal, int or string")`, which the generic `except ... outcome = str(exc)` counted VERBATIM --
a free-text sentence as a refusal-counter key. Fix: `check_caps`/`_growth_within_cap` are called inside
their own `try`, converting ANY exception to `ValueError('invalid_caps')`; the deliberate `cap_refused`
decision is raised OUTSIDE that `try`, so it is never caught by the same handler. AFTER:
`counts == {'invalid_caps': 1}`, no free-text key (`test_malformed_caps_refused_under_fixed_key_no_free_text`).

`test_paper_account_1k.py` (NEW, 4 tests) added to A9/LOC below; combined 65/65
(13+16+3+7+3+3+6+5+2+3+4). Memo kept under the 300-line cap (FIX 1j condensed above).

## NOT VERIFIED

- No observation of our own queue position or counterfactual ownership of a print (carried forward from S411;
  this row does not touch fill probability, only reservation-history continuity).
- **Zero real night's receipts exist; every test fixture in all eleven test files is constructed.**
- The fill_realism integration is PROPOSED only, never wired; `fill_realism.py` never calls `paper_account.py`.
- No TTL-timer or clock logic exists in this module; an `expire` receipt's timing is decided entirely by
  whatever future caller produces the receipt feed.
- Already fixed, in order, one line each in FIX HISTORY 1c-1i above plus FIX 1j/1k below (nothing left
  open): 1c-1i (malformed-line persistence and encoding collisions, lost-prefix-on-crash write, the
  collision-proof envelope, invalid-shape crashes, strict envelope typing, `_canon` identity), 1j
  (`_encode`'s fallback-to-string on an unsupported qty type), 1k (the non-persistent path's arrival-order
  dependence, unencoded dict keys, free-text cap-validation counters).
- Superseded by fix 1k(a): the canonical-replay fix (3c) used to be scoped to when `log_path` was set, with
  an ephemeral (no-`log_path`) account applying each receipt once in call order; EVERY `ingest()` now
  canonically replays regardless of `log_path`.
- The sandbox verifier that produced the round-4 through round-10 REJECTs could not run any `tmp_path`-based
  pytest body (read-only sandbox, no writable temporary directory); all eleven test files (65 tests),
  including the new `test_paper_account_1k.py`, are run and verified on the HOST by this fix lane, not by
  that sandbox verifier.
- Cross-week deployment, network, capture, pod or runtime activation: none exercised here (PREPARE only).
