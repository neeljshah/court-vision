# S439 candidate: FIX 1e (AMENDMENT 4) -- construct-only; independent verification pending

Local construct work only, in nba-harness-h94. No captured archive was scored.
Vocabulary follows contract Q6; automated scan required.

## Binding before-condition (before coding)

Exact probe output:
```text
BEFORE new_module_exists= False
ingame/baseline_four_arm.py lines=296 bytes=17746 sha256=ee821a457d5a3eb63583f36fec01872301ba0f7eb55c57279266831ab84465db
ingame/baseline_four_arm_features.py lines=300 bytes=15557 sha256=4cd95bb70b0578318ad04f7144455e083a754924c8b0ee2c6c596e38e9880647
ingame/gate_a0_ingame_vs_market.py lines=299 bytes=12047 sha256=e61c16a46c57b339e702f8ab27e95b897b24dbdd1f4f4f562fd7433f959ed659
execution/paper_night.py lines=299 bytes=15357 sha256=4e912e5155343534b340b757b402a9114b4d9119326d926f982b912f044d3df2
execution/entry_timing/study.py lines=194 bytes=8325 sha256=95e97820786a878581b3c420d7202ab940a22078c43c53111715dfba09ce12d4
execution/forward_replay_qualification.py lines=262 bytes=14837 sha256=0170676d9d4e17e1792deb8fb556a490afaeea2ae033369a4148392fcbf1c84e
ingame/local_state_capture_sources.py lines=300 bytes=20512 sha256=70aac0623c242073fed60c48b9894e234c691bde3e20cfda3bd82e36c690062e
execution/cross_venue_pairs.py lines=300 bytes=17501 sha256=7f240260727ecaeba1d7e49a715a2ef2ba97cc6d0e291fe5c580cc22da7351c1
S431_exists= False
S435_exists= False
```
Resolution: source text. The independently checked ingame/event_latency_census.py,
ingame/event_response.py and ingame/event_response_events.py are also absent.
baseline_four_arm.py has predict_rows, with a per-game earlier-date and
three-day settlement embargo inside walk_forward. gate_a0 has N_BOOT=2000,
SEED=13, N_MIN_GAMES=30 and reads prejoined rows. The final status normalizer
is final; settlement requires two finite scores.

## Imported contracts read before coding

Exact signatures relied on (stdlib omitted):
```python
def predict_rows(rows: list[dict], corpus: str) -> list[dict]:
def cluster_boot_ci(values: list[float], clusters: list, n_boot: int = 500,
                    seed: int = 7) -> tuple[float | None, float | None]:
def timestamp(value: Any) -> Decimal:
def alias(sport: str, abbr: Optional[str]) -> Optional[str]:
def team_code_from_ticker(ticker: str) -> Optional[str]:
def label_code(sport: str, label: object, codes: frozenset):
```
Respectively: ingame/baseline_four_arm.py, execution/entry_timing/study.py,
execution/coherence_scanner_inputs.py, ingame/game_market_link.py (two),
execution/cross_venue_link.py. `timestamp` calls execution/venue_time.py's
`parse_venue_time(value) -> float | None`. The other imported symbol is
`FEATURES` from ingame/baseline_four_arm_features.py. `nearest` (imported from
execution/forward_replay_qualification.py, line 17) supplies the mid_age p50 / p90
nearest-rank quantiles (line 181); cluster_boot_ci supplies the confidence intervals
(sol round 5 CORRECTION, applied by the orchestrator before landing).

## Result and scope (current, post FIX 1e)

The scoreboard is a standalone night-wake command (paper_night.py's three
steps are untouched and byte-identical to master); it is not armed by any
supervisor. No real-night counts were measured. Receipts are S431 file-order
dependent (first copy of an instant kept, a later duplicate or an
earlier-than-preceding instant refused and counted); every cutoff, ordering,
duplicate, filtering, lookup, prediction-key and sort decision anywhere in
this module is a whole microsecond from `_instant()`, never an exact Decimal
`timestamp()` comparison. CORRECTION: FIX 1c's identical claim at this spot
was only ever true of `_receipts()` -- six further decision-path
`timestamp()` uses survived in `_models()`/`run()` (training cutoff,
duplicate keys, prediction-dict keys, the selected-ticks sort) until FIX 1d
below removed them. Each ticker scores its own yes event (a tie is 0, itself
settled). Held-out reconstruction passes every tick -- settled or not -- the
SAME placeholder outcome/close_ts into the landed `predict_rows`, so
settlement controls only the outcome-loss emission, never the model inputs.
`mid_age_us` quantiles are computed per arm cell from that cell's own
eligible rows. A single corpus/window never emits AHEAD/BEHIND (SINGLE-WINDOW
instead); an away-oriented tick's own_yes_mid is never mixed with a
home-minus-away state summary; predictor `ts`/`close_ts` are always six-digit
UTC (FIX 1e, AMENDMENT 4, below). 63 tests pass across the three test files
(43 + 16 + 4), including adversarial and mutant-killing cases.

## Enumeration (15/15 CONSTRUCT, ORCHESTRATOR ADJUSTMENTS bar)

| # | Construct | Result |
| - | --- | --- |
| 1 | Equal receipt alignment | PASS |
| 2 | Whole-microsecond cutoff: +1ns = same instant (kept), +1us = later (excluded) | PASS |
| 3 | Settled game scored against outcome and aligned mid | PASS |
| 4 | Unsettled game omitted only from outcome comparison, counted | PASS |
| 5 | Two-game Brier/logloss match independent arithmetic | PASS |
| 6 | Fewer than 5 clusters -> INSUFFICIENT, null CI | PASS |
| 7 | 5+ clusters below 30 games -> INSUFFICIENT | PASS |
| 8 | Four segments, sport boundaries, tennis refused | PASS |
| 9 | Sport with no served game -> zero cells + reason | PASS |
| 10 | A,B,C,D,B_lag ordering preserved | PASS |
| 11 | Duplicate/out-of-order receipts refused and counted (file order) | PASS |
| 12 | Opened input byte counts and sha256 recomputed | PASS |
| 13 | Missing/uncommitted prereg refuses before output creation | PASS |
| 14 | C-minus-B per-tick and aggregate contrast agree exactly | PASS |
| 15 | B_lag uses the previous receipt, never the current | PASS |

Additional tests: strict count types, nonfinite/absurd inputs, naive-time
refusal, future/malformed rows, latest-final recovery, the actual landed
B/C/D predictor and embargo, missing optional D feature, future/duplicate
schedules, overnight settlement, compact streaming, refused-HTTP ordering,
invalid-lag isolation, malformed history, nonfinite prediction, CRLF seal
(both directions, genuinely multiline), settlement-independent prediction
inputs (spy), and per-arm mid_age filtering.

## FIX 1b (AMENDMENT 1) -- landed, summary retained for the record

(a) CRLF-safe seal (`_seal()`, LF-normalised compare). (b) Own-yes-event
scoring via `ticker_outcome()`/`_mid()` in ingame_scoreboard_rules.py; ties
settle at 0. (c) `_models()` builds a test row for every tick regardless of
settlement (superseded by FIX 1c(b) below -- the placeholder was not yet
unconditional; codex round 2 caught this). (d) `_receipts()` rewritten to
FILE-order S431 semantics with `_instant()` (superseded in part by FIX
1c(a) -- the cutoff/start-end/age comparisons still used exact `timestamp()`
until this round). (e) Mutant-killing tests added (MLB Bottom-half, edited-
but-committed prereg, embargo). (f) `select_rows` census reasons folded into
counts. (g) `mid_age_us` recorded, MLB inningState Middle/End mapped, `--arms`
honoured. Split rules module created to hold the LOC cap.

## FIX 1c (AMENDMENT 2) -- summary retained for the record

Base sha ef7248901. Codex round 2: five blockers, one correction (FIX 1b's
own claim in (c) did not match the code). (a) Integer microseconds
everywhere in `_receipts()`, `now`, the shard-day cutoff and `_capture()` --
no exact `timestamp()` comparison remained. (b) Settlement never reaches the
prediction path: `_models()` test rows always carry a fixed placeholder
outcome/close_ts; a spy test proved identical held-out rows settled vs
unsettled. (c) Settlement derived solely from `_receipts()`'s kept-first-copy
output, the separate raw-timestamp final veto removed. (d) `mid_age_us`
quantiled per arm cell from that cell's own eligible rows. (e) A real
multiline CRLF seal construct exercised both directions. Tests:
test_ingame_scoreboard.py 43 passed, test_ingame_scoreboard_1b.py 14 passed.
No prereg change (POLICY unchanged; sha256 unchanged from FIX 1b).

## FIX 1d (AMENDMENT 3) -- summary retained for the record

Base sha 61419f21c. Codex round 3: two blockers (FIX 1c's own claim did not
match the code -- six `timestamp()` uses on a decision path remained outside
`_receipts()`; the settlement-independence spy checked inputs only, never
outputs). (a) The six remaining decision-path `timestamp()` calls in
`_models()`/`run()` (training-embargo boundary, training duplicate key,
prediction-dict key and cutoff, selected-ticks sort, prediction lookup)
replaced by `_instant()`; the training-duplicate filter rewritten as
`dedupe_first()` (new, ingame_scoreboard_rules.py). `timestamp()` remains
exactly once, validating `scheduled_start` in `run()`, discarded, on no
decision path. (b) The settlement-independence spy also asserts identical
keyed B/C/D inventories, not just identical inputs. Tests:
test_ingame_scoreboard.py 43 passed, test_ingame_scoreboard_1b.py 16 passed.
No prereg change (POLICY unchanged; sha256 unchanged from FIX 1b/1c).

## FIX 1e (AMENDMENT 4)

Base sha (this tree, current): b2edd3a55. Codex round 4: four blockers, one
correction (`_verdict_s439_1e.md`; AMENDMENT 3 otherwise confirmed). The
sandbox verifier could not run tmp_path tests; these ran on the host.

(a) Q5 -- a single window never says AHEAD/BEHIND [ingame_scoreboard.py:178].
Before: `verdict = 'INSUFFICIENT' if n<30 else ('BEHIND' if contrast and lo>0
else 'AHEAD' if contrast and hi<0 else 'UNDERPOWERED')`; reproduction (30
games, constant contrast -0.1, n=30, lo=hi=-0.1): `verdict='AHEAD'`. After:
`_summary()` calls the new `contrast_verdict()` (ingame_scoreboard_rules.py);
AHEAD/BEHIND now require BOTH `min_corpora_eff` and `n_corpora >= 2` and
`n_corpora >= min_corpora_eff` in the input -- this row supplies neither, so
its own report always says SINGLE-WINDOW when directional. Same reproduction
now gives `verdict='SINGLE-WINDOW'`, `ci95=[-0.1,-0.1]` (numbers unchanged).
RESEAL: `vocabulary` gained `'SINGLE-WINDOW'`; old seal (superseded)
`988ebe19cacc3b6b3a133c7fa90949f3994429fd7b08b0dab318325501952f50`; new seal
`35c73a795465b789542c707e679e3278e39c4465ae71fb41341d05235713cae8`;
PREREG_2026-09-24.json rewritten to match, `_seal()` round-trip verified.
Regression: test_ingame_scoreboard_1e.py::test_single_window_never_ahead_or_behind.

(b) Ticker orientation carried into every tick [ingame_scoreboard.py:137,
244; new `is_home_ticker()` in ingame_scoreboard_rules.py]. Before: an
away-ticker's own_yes_mid=0.25 with home 12 away 2 reached `_models()` as
`market_prob=0.25` beside `state_summary='score_diff=10 ...'` (h-a=10,
home-oriented; mismatched). After: each tick records `home_oriented` at
construction; `_models()` skips any tick where `home_oriented` is falsy,
counting `not_reconstructible_orientation`, before building its state fields
-- it is never mixed with a home-referenced score_diff. Regression (two
games, one home- one away-oriented ticker; spies on `predict_rows`):
test_ingame_scoreboard_1e.py::test_away_ticker_not_reconstructible_and_never_mixed
-- asserts `away0` never reaches the predictor while `home0` does, and
`away0`'s B/C arms are None.

(c) Instants canonicalised before the predictor [ingame_scoreboard.py:134,
157-158; new `canon_instant()` in ingame_scoreboard_rules.py]. Before: a
retained nine-digit first receipt's raw `ts` string passed straight into
`_models()`'s train/test rows; reproduction --
`baseline_four_arm_features.timestamp('2026-09-22T12:00:00.000000001Z')`
raises `ValueError: submicrosecond timestamp unsupported`, which
`select_rows` catches and reports as `unparseable_time`, and `predict_rows`
silently drops the row. After: training and test `ts`/`close_ts` are
rebuilt as six-digit UTC strings from `_instant()` before being handed to
`predict_rows`; the same nine-digit value now canonicalises to
`2026-09-22T12:00:00.000000Z`, which parses cleanly. Regression:
test_ingame_scoreboard_1e.py::test_ninedigit_receipt_reaches_predictor_canonicalized
-- asserts the spied row's `ts`, zero `unparseable_time` refusals, and the
tick's `mid`-target B arm actually reconstructs.

(d) The eligibility census never swallows [ingame_scoreboard.py:172]. Before:
`except ERRORS: pass` -- forcing `select_rows` to raise `ValueError`
leaves `counts` holding only unrelated defaults (e.g. `{'training_duplicate':
0}`), no trace of the failure. After: `except ERRORS as exc:
counts['census_refused'] += 1; counts['census_refused:'+str(exc)] += 1` --
the reason text is retained and the function continues (the real
`predict_rows` call is a separate try block, unaffected). Regression:
test_ingame_scoreboard_1e.py::test_census_refusal_is_counted_not_swallowed.

(e) Full-package test imports [test_ingame_scoreboard_1b.py:11]. Before:
`from test_ingame_scoreboard import ...` (bare module name). After: `from
tests.platformkit.execution.test_ingame_scoreboard import ...`, matching the
pattern already used by test_cross_venue_s398_1h.py/1i.py in this same
directory. The new test_ingame_scoreboard_1e.py uses the full-package form
from the start.

Tests, run one file at a time:
```text
python -m pytest tests/platformkit/execution/test_ingame_scoreboard.py -q -p no:cacheprovider
43 passed
python -m pytest tests/platformkit/execution/test_ingame_scoreboard_1b.py -q -p no:cacheprovider
16 passed
python -m pytest tests/platformkit/execution/test_ingame_scoreboard_1e.py -q -p no:cacheprovider
4 passed
```
63 passed total (4 new regressions in the new file; no existing test's
assertions were weakened).

Preflight (this tree, base master), 9/9 PASS over the six owned files:
```text
python -m scripts.platformkit.tracking.contract_preflight --base master --spec docs/evidence/tracking/specs/S439_spec.md --paths scripts/platformkit/execution/ingame_scoreboard.py scripts/platformkit/execution/ingame_scoreboard_rules.py tests/platformkit/execution/test_ingame_scoreboard.py tests/platformkit/execution/test_ingame_scoreboard_1b.py tests/platformkit/execution/test_ingame_scoreboard_1e.py docs/evidence/forward/scoreboard/PREREG_2026-09-24.json
PASS vocab / crlf / loc / schema / head_slice / spec_threshold (2 literals) / proposed / removed_artifact / row_duplication
```

LOC (`wc -l`), all ASCII and <= 300: ingame_scoreboard.py 298 (net +1 vs FIX
1d's 299 -- helpers moved to the rules module to stay under the cap);
ingame_scoreboard_rules.py 135 (+36: `is_home_ticker`, `canon_instant`,
`contrast_verdict`); test_ingame_scoreboard.py 297 (unchanged);
test_ingame_scoreboard_1b.py 249 (import line + one fixture's `home_oriented`
key, line count unchanged); test_ingame_scoreboard_1e.py 88 (new);
PREREG_2026-09-24.json 1 (resealed, vocabulary +1 entry).

A9 recompute, this tree, base sha b2edd3a55:
```text
scripts/platformkit/execution/ingame_scoreboard.py lines=298 bytes=22010 sha256=ba37c375ca62aee6b0eeb9b5cc502ec94c7cb6ad08f234e64990758ac2e85544
scripts/platformkit/execution/ingame_scoreboard_rules.py lines=135 bytes=6769 sha256=5a58a2217f19124a68d46e1c67f201d6ce051618f413ca9668cff7367bb36fc7
tests/platformkit/execution/test_ingame_scoreboard.py lines=297 bytes=18140 sha256=201ce74642cc080276787c0dfd5b4a556bfdfb5865a1b592bca0735d34743f94
tests/platformkit/execution/test_ingame_scoreboard_1b.py lines=249 bytes=13174 sha256=1ec6abe6e513394fc66494b29885d3e8f27beee7c372a5ba009e59921a33c091
tests/platformkit/execution/test_ingame_scoreboard_1e.py lines=88 bytes=5473 sha256=50f083f78457118e0cfe10e74f5d8775c0e9cf96997698ffdb8da1aa1c167b5b
docs/evidence/forward/scoreboard/PREREG_2026-09-24.json lines=1 bytes=4611 sha256=421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d
docs/evidence/tracking/specs/S439_spec.md lines=31 bytes=17310 sha256=480757575f0c9de6a851d74ce1cf61d381401cdbaecc72acc42566f9aa7b399e
```
Must-not-move files re-hashed from this tree and confirmed byte-identical to
their master blobs (`git diff --stat master -- <14 files>` empty, including
the read-only forward_schedule_writer.py cited in AMENDMENT 4(b)): the same
set as FIX 1c/1d plus forward_schedule_writer.py. HEAD unchanged at
b2edd3a55.

No commit was created in this lane. `git status --short` shows only the
seven untracked candidates (the five owned code/test files, this memo, and
the docs/evidence/forward/scoreboard/ directory holding the resealed prereg).
SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED
- FIX 1e is construct-only, same as every round before it: no real night has
  been scored under the SINGLE-WINDOW vocabulary, orientation-aware
  reconstruction, canonicalised-instant or census-refusal-counted rules.
  Nothing here is a real-night claim.
- No real-night archive, network, pod, real model artifact or measured corpus was used.
- The prereg has not been committed; no successful production seal check was exercised.
- Cross-corpus directional evidence, large-shard memory ceilings, interruption during
  fsync, and actual filesystem power-loss behavior were not tested.
- NFL/ncaaf four-arm fitting and tennis live regulation segmentation are unavailable
  in the landed dependencies; native captures lack the optional D model feature.
- No calibrated result from the default live MLB/soccer capture-only path is claimed.
- An independent verifier has not accepted this candidate; no supervisor was armed.
