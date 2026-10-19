# S457 -- event-response quantisation, pass-2 pre-filter, telemetry (BUILD LANE)

Worktree: C:/Users/neelj/nba-harness-h110 (branch harness-h110, master-based; candidate HEAD and
verification-base master are EQUAL at 121d08a1f233bea88e8d603559374666c3b63904, the base this
FIX 1d lane was pinned to -- see A9 identities). Spec: docs/evidence/tracking/specs/S457_spec.md,
AMENDMENTS 1-4 (2026-09-25) are BINDING and followed throughout; the CHANGE/ACCEPTANCE RULE
numbering below is AMENDMENT 1's.

## Pre-edit premise check (BINDING BEFORE-CONDITION, S2)

Ran both existing test files on master BEFORE any edit:
- `tests/platformkit/ingame/test_event_response.py` -- **13 passed** (2.48s)
- `tests/platformkit/ingame/test_event_response_1c.py` -- **11 passed** (0.62s)

This matches AMENDMENT 1(a)'s corrected premise (13 + 11 on master), not the original spec
text's "test_event_response_events.py 11" (no such test file exists; the second file is
`test_event_response_1c.py`). Also verified from
`docs/evidence/forward/event_response/2026-09-22_mlb_event_response.json` (85,186 bytes):
events 159 (89 period / 49 pitcher / 16 score / 5 status, matches REAL RUN 1 exactly), and
summed `mean` string length across all `summary[].horizons[].mean` = 16,864 chars of the
85,186-byte artifact -- matches AMENDMENT 1(a)'s "16,864 of 85,186" precisely. Confirmed
`event_response_events.py:267`-equivalent (now event_response.py) `allow_nan=False` already
present pre-edit, and residuals hardcoded null (no per-quote Decimal residual arithmetic exists).

## A9 identities (regenerated last, FIX 1e)

Candidate HEAD == pinned verification-base, both full shas, EQUAL: `121d08a1f233bea88e8d603559374666c3b63904`
(`git rev-parse HEAD` in this worktree; the local `master` ref has since advanced further, to
`d0f41925cb45d9814b9404a0bf44ac3a0e76212a`, via unrelated concurrent commits -- this worktree
stays fast-forwarded to the pinned base per the FIX 1d/1e task instruction, same situation FIX 1d
already recorded with an earlier master tip). Working-tree sha256, `\r\n` normalised to `\n`
(no commit exists yet in this sandbox):

| path | bytes | sha256 |
|---|---|---|
| scripts/platformkit/ingame/event_response.py | 15407 | 830dfab48ba279cd65dfb2e4e390bdaaeb87ec596caf423cdcbd5a4f5d0ffc68 |
| scripts/platformkit/ingame/event_response_events.py | 10834 | 312d7942c0fb788843182079d40ca25b226d24432b08be0552a595908d839203 |
| scripts/platformkit/ingame/event_response_quant.py | 4919 | 8daf733d94fffa943654d3c44746722825c9f94dabd882b7c35c31c164457eb9 |
| tests/platformkit/ingame/test_event_response.py | 19148 | 0a5c30aac2d516d591d6517c16601112109f43883326d18f0507b4283471df11 |
| tests/platformkit/ingame/test_event_response_ops.py | 14929 | 66cc7e495df37f56216dd76a85b01f79eab1ae4609d7cd4ab3731821fcb0ef2e |

## Files (owned)

| file | LOC (`wc -l`) | note |
|---|---|---|
| scripts/platformkit/ingame/event_response.py | 300 | edited: quantise mean/median/CI/lag_median_s, pass-2 prefilter wiring, telemetry; FIX 1b/1c: finite-gated summary stats, final event values quantised; FIX 1d: `_measure()` keeps exact Decimal `moves` (no early quantise) so `_summary()` aggregates before rounding (finding 1); `report()` builds output-only quantised event copies via `quantise_event()`; `_summary()` counts `lag_non_finite` for a dropped non-finite lag (finding 2) |
| scripts/platformkit/ingame/event_response_events.py | 234 | edited: `rows()` gained optional `prefilter`/`telemetry` params (whole-input hashing/sizing untouched); untouched by FIX 1d |
| scripts/platformkit/ingame/event_response_quant.py | 123 | `quantise`, `finite_str`, `bounded_floats`, `line_matches`, `pass2_prefilter`, `build_telemetry`, `quantise_optional`, `QUANTISATION`; FIX 1d: new `quantise_event()` (output-copy quantisation, finding 1); `bounded_floats()` now catches `ValueError` alongside `OverflowError` so a signalling NaN returns None instead of raising (finding 2); FIX 1e: `pass2_prefilter` needles encode `utf-8` not `ascii` (opus finding 1) |
| tests/platformkit/ingame/test_event_response_ops.py | 278 | 13 constructs through FIX 1c; FIX 1d added `test_case1c_exact_moves_survive_aggregation_no_double_rounding` and `test_case4c_signalling_nan_bounded_floats_returns_none`, and extended `test_case4b` with a `lag_non_finite` assertion; FIX 1e added `test_case1d_exact_move_survives_parse_float_decimal` (moved from test_event_response.py, opus finding 2), `test_case3g_non_ascii_served_ticker_matches_oracle` (opus finding 1), and case2's comparison is now a `json.dumps` byte-identity `dump()` (opus finding 3) |
| tests/platformkit/ingame/test_event_response.py | 300 | edited for the telemetry exception (item 6): `test_01`/`test_07`'s whole-artifact comparisons now exclude the `telemetry` key (runtime_s legitimately varies between runs; AMENDMENT 1d); FIX 1b: the two-line `test_07` comparison collapsed to one line, LOC 301 -> 300 (finding 4); FIX 1c: `test_atomic_write_and_partial_recovery` updated for quantised `moves["5"]` (finding 1), LOC held at exactly 300; FIX 1e: `test_01`'s comparison is a `json.dumps` byte-identity check (opus finding 3), and the weak standalone `exact_move` computation was replaced by the `"0.000000"` output assertion alone (the exact-1e-18 check moved to test_event_response_ops.py, opus finding 2), LOC held at exactly 300 |

Every file is ASCII, `<= 300` LOC (test_event_response.py collapsed to exactly 300 in FIX 1b;
`contract_preflight`'s `loc` check over all 6 candidate files reports PASS -- see below).

## Hunks (summary)

- `event_response_quant.py` (new): `quantise()` quantizes a finite Decimal to 6 places
  (ROUND_HALF_EVEN) under a 4200-digit local context so a value carried from the 2100-prec
  outer context never raises `InvalidOperation`; `finite_str()` passes a Decimal through as a
  string, refusing non-finite (the actual "string NaN" guard -- `allow_nan=False` alone never
  catches an already-stringified value); `bounded_floats()` converts Decimals to floats for the
  CI bootstrap, returning None (never raising) on `OverflowError` or a non-finite result;
  `line_matches()` is the pass-2 cheap filter (always decode on a backslash, else require a
  served-ticker substring); `pass2_prefilter()` builds the per-sport filter closure or None;
  `build_telemetry()` builds `{runtime_s, lines_seen, lines_decoded}`.
- `event_response_events.py: rows()`: added `prefilter=None, telemetry=None` trailing params.
  Every line is still hashed/sized before any filtering (whole-input accounting untouched);
  `telemetry["lines_seen"]` counts every line, a `prefilter`-rejected line is skipped before
  `json.loads` and before `telemetry["lines_decoded"]` increments. No existing positional caller
  breaks (both new params are optional, appended after `last_seen`).
- `event_response.py`: `report()` gained `prefilter_pass2: bool = True` (keyword-only, after the
  existing `now`) and records `start = time.monotonic()`. The pass-2 book loop builds a
  per-sport `line_filter` via `pass2_prefilter(tickers, sport, prefilter_pass2)` and threads it
  plus a `pass2_telemetry` Counter into `rows()`; nothing else in that loop changed (the pass-2
  integrity check against pass-1 hashes is untouched). `_measure()`'s per-event `mid_before` and
  `venue_lag_s` now route through `finite_str()` (formalizes the explicit finite check;
  per-event values were already guaranteed finite by `_mid()`'s upstream `is_finite()` check, so
  this never fires on real data -- AMENDMENT 1c: quantisation/finite-checks apply to *final
  reported* values, never to a mid before change detection). `_summary()` now takes `counts` and:
  (a) uses `bounded_floats()` instead of a bare `float(v)` list comprehension that could raise an
  uncaught `OverflowError` for an unreachable extreme-magnitude Decimal, counting
  `non_finite_summary_input` instead of crashing; (b) checks `math.isfinite(lo) and
  math.isfinite(hi)` on the CI bootstrap's own return before using it, counting `non_finite_ci`
  and falling back to `INSUFFICIENT` instead of ever stringifying a NaN/Infinity float; (c) wraps
  `mean`/`median`/`mean_ci95`/`lag_median_s` in `quantise()`. The return dict gained
  `quantisation=QUANTISATION` and `telemetry=telemetry`. Net effect: event definitions, reasons,
  the horizon set, and the pass-1 whole-day accounting are byte-for-byte unchanged.
- `test_event_response.py`: `test_01_last_quote_at_horizon_end_to_end` compared
  `first.read_bytes() == second.read_bytes()` across two CLI runs with a fixed `--as-of`; now
  compares the two parsed dicts with `telemetry` excluded (runtime_s differs by wall clock,
  confirmed by the failure diff before the fix: `runtime_s: 0.016` vs `0.0`).
  `test_07_game_order_independent` had two whole-dict comparisons across separate `run()` calls
  on the same root; both now also exclude `telemetry`. No other assertion in either file touches
  telemetry, and none of `test_event_response_1c.py`'s 11 tests compare whole artifacts.

## Before / after artifact size on the fixture (case 1, ACCEPTANCE RULE construct 1)

Three synthetic games, moves 0.10 / 0.10 / 0.11 at horizon 5s -> mean = 0.31/3, a genuinely
non-terminating quotient at any fixed precision.

- Simulated BEFORE (old unbounded-Decimal `mean` string spliced back in, `quantisation` key
  removed): **5334 bytes**; the `mean` field alone is 2102 characters
  (`0.10333333333333...` at prec=2100).
- AFTER (this landing, quantised): **3302 bytes**; `mean` field is `"0.103333"` (8 characters,
  exactly 6 places past the decimal point).
- `result["quantisation"] == {"places": 6, "rounding": "ROUND_HALF_EVEN"}` on every artifact.

## The 7 ACCEPTANCE RULE cases (AMENDMENT 1 numbering) -> tests

| # | construct | test(s) |
|---|---|---|
| 1 | non-terminating mean quantised to exactly 6 places, quantisation declared | `test_case1_nonterminating_mean_quantised_to_six_places` |
| 2 | quantised artifact byte-identical across two runs of the same fixture (telemetry varies) | `test_case2_byte_identical_across_runs_telemetry_varies` |
| 3 | pass-2 filtered path == unfiltered oracle (AMENDMENT 1b's 6 adversarial fixtures), `lines_decoded < lines_seen` | `test_case3a` unicode-escaped identity, `3b` embedded escaped quote, `3c` ticker-is-a-prefix, `3d` numeric game_key (rejected as today), `3e` duplicate rows, `3f` competing same-day unserved market (linkage stable) |
| 4 | real non-finite intermediate refused, counted, never serialised (string NaN explicitly refused) | `test_case4_non_finite_intermediate_refused_and_never_serialised` |
| 5 | `runtime_s` + both counters present, finite | `test_case5_telemetry_present_and_finite` |
| 6 | the two existing test files pass with unchanged counts (13 + 11) | verified directly (see below), no new-file test needed |
| 7 | real 2026-09-22 shards match REAL RUN 1 exactly (89/49/16/5), `runtime_s` <= 1200s | **NOT VERIFIED here -- orchestrator work (rails: "never a construct")** |

Case 4 detail (AMENDMENT 1c: real non-finite input, not a synthetic literal): direct unit calls
prove `quant.quantise(Decimal("NaN"))` and `quant.finite_str(Decimal("Infinity"))` both raise
`ValueError("non_finite_statistic")`; `cluster_boot_ci` monkeypatched to `(nan, inf)` (unreachable
from real [0,1]-bounded price data, stated honestly) and `report()` is asserted to mark that
horizon `INSUFFICIENT` with `mean_ci95: null`, count `non_finite_ci == 1`, and never emit the
literal substring `"NaN"`/`"Infinity"` anywhere in the serialised artifact.

Case 3's six sub-fixtures each assert `events`/`summary`/`counts` are IDENTICAL between
`prefilter_pass2=True` and `=False` (the oracle switch), plus `lines_decoded < lines_seen` in the
filtered run. 3a: a `\uXXXX`-escaped ticker character (decodes to the same ticker; a plain
substring check would miss it). 3b: an embedded escaped quote in `home_abbr`. 3c: an unserved
ticker with the served ticker as a strict prefix (over-inclusive match, harmless,
`lines_decoded >= 2`). 3d: numeric `game_key` (rejected as today, `invalid_game_key == 1` both
paths). 3e: the identical served-ticker line sent twice (`duplicate_instant == 1` both paths).
3f: a second, unserved, same-day market (linkage does not flip, served `game_id` unchanged).

## Post-edit pass counts (per-file, one at a time, `-p no:cacheprovider`)

- `tests/platformkit/ingame/test_event_response.py` -- **13 passed** (unchanged count; two
  assertions updated for the telemetry exception per item 6, as noted above; re-verified after
  FIX 1b's LOC collapse)
- `tests/platformkit/ingame/test_event_response_1c.py` -- **11 passed** (unchanged, no edits)
- `tests/platformkit/ingame/test_event_response_ops.py` -- **12 passed** (10 original + FIX 1b's
  `test_case4b_non_finite_summary_moves_never_abort_report` and
  `test_case5b_telemetry_non_finite_runtime_reported_as_null`)

CLI checks: `python -m scripts.platformkit.ingame.event_response --help` runs clean (no new
required argument; `prefilter_pass2` is a `report()`-only keyword, not exposed on the CLI --
production always runs with the AMENDMENT 1b optimisation on). `event_response_events.py` and
`event_response_quant.py` have no `main()` (unchanged / new helper module respectively) --
imported and exercised directly instead.

## contract_preflight

`python -m scripts.platformkit.tracking.contract_preflight --paths
scripts/platformkit/ingame/event_response.py scripts/platformkit/ingame/event_response_events.py
scripts/platformkit/ingame/event_response_quant.py tests/platformkit/ingame/test_event_response_ops.py
--base master --spec docs/evidence/tracking/specs/S457_spec.md`:

History, collapsed to one dated line per round (all runs used the 6-file `--paths` set from FIX 1b
onward: both `.py` modules, both test files, and this memo; `--base master --spec
...S457_spec.md`):

- 2026-09-25 first run (4 files): FAIL `vocab` (a Q6-word inside a docstring describing an
  unreachable corner, regardless of context) + FAIL `spec_threshold` (13/16/89 not yet echoed
  anywhere); fixed by rewording the docstring and adding the numbers to the new test module's
  docstring.
- 2026-09-25 second run (4 files): all 9 PASS.
- 2026-09-25 FIX 1b run (6 files, widened per AMENDMENT 2a): all 9 PASS (vocab now clean over 6).
- 2026-09-25 FIX 1c run (6 files): all 9 PASS (`event_response_quant.py` 110 LOC, `ops` 229 LOC).
- 2026-09-25 FIX 1d run (6 files, this round): all 9 PASS -- `vocab` clean, `crlf` clean (3
  untracked), `loc` all .py <= 300 (`event_response.py` 300, `event_response_quant.py` 123,
  `test_event_response_ops.py` 247), `schema` additive, `head_slice` none, `spec_threshold` 16
  matched, `proposed` none given, `removed_artifact` none, `row_duplication` none.

## must-not-move check

`git diff --stat master -- scripts/platformkit/ingame/event_latency_census.py
scripts/platformkit/ingame/microstructure_features.py scripts/platformkit/execution/venue_time.py`
-> empty output for all three (byte-identical to master). No capture module appears in `git
status --short` either.

## git status --short

```
 M scripts/platformkit/ingame/event_response.py
 M scripts/platformkit/ingame/event_response_events.py
 M tests/platformkit/ingame/test_event_response.py
?? scripts/platformkit/ingame/event_response_quant.py
?? tests/platformkit/ingame/test_event_response_ops.py
```

The `test_event_response.py` modification is the item-6-sanctioned telemetry exception only (no
other line touched); everything else matches "the two modified modules plus your untracked
candidates."

## Fix history, rounds 1b-1c (collapsed to one dated line per fix; full prose superseded)

- 2026-09-25 FIX 1b (verdict `_verdict_s457_1.md` REJECT, 3 BLOCKING + 2 CORRECTION): memo's
  retrospective Q6-word hit reworded; `_summary()` gated mean/median/`lag_median_s` on a finite
  `bounded_floats()`/`.is_finite()` result instead of unconditionally quantising a non-finite
  input (added `test_case4b_non_finite_summary_moves_never_abort_report`); `build_telemetry()`
  guarded `runtime_s` with `math.isfinite`/non-negative, else null + `telemetry_runtime_non_finite`
  (added `test_case5b_...`); `test_07`'s telemetry-exclusion diff collapsed to one line (LOC
  301->300); memo SHA sentence moved before NOT VERIFIED. 12 passed (was 10).
- 2026-09-25 FIX 1c (verdict `_verdict_s457_1c.md` REJECT, 1 BLOCKING + 1 CORRECTION):
  `mid_before`/`venue_lag_s`/`moves[h]` were serialised via `finite_str()`/bare `str()` at full
  unquantised precision instead of `quantise()` (repro: `str(Decimal("0.76543215") -
  Decimal("0.12345675"))` -> `"0.64197540"`, 8 places); added `quantise_optional()`, wired all
  three through it (`quantise(...)` -> `"0.641975"`, 6 places); added
  `test_case1b_final_event_values_quantised_to_six_places`; identities regenerated, headings
  corrected FIX 1 -> FIX 1b. 13 passed (12 + case1b).

## FIX 1d (verifier verdict `_verdict_s457_1d.md`, REJECT -> addressed)

1. **BLOCKING, event_response.py:128,151-164 event moves quantised before aggregation
   (double-rounding)** -- reproduced first: individually-quantised moves `4.9E-7, 4.9E-7, 5.3E-7`
   -> `"0.000000", "0.000000", "0.000001"`; `_summary()`'s mean from those pre-rounded values ->
   `"0.000000"`, while exact Decimal aggregation (`4.9E-7+4.9E-7+5.3E-7)/3`) then a single
   quantise gives `"0.000001"`. Root cause: `_measure()` (line 128) called `quantise()` on each
   move the instant it was computed, so `_summary()` (lines 151-164) aggregated already-rounded
   inputs. Fixed: `_measure()` now stores the exact Decimal difference (no early `quantise()`
   call); `_summary()`'s `Decimal(r["moves"][str(h)])` already round-trips a Decimal unchanged, so
   aggregation and the CI bootstrap now see exact values; a new `quantise_event()` in
   `event_response_quant.py` builds a serialisation-only copy (`moves` quantised to 6 places) that
   `report()` uses for the JSON `events` field, so the exact `events` list keeps feeding
   `_summary()` while the artifact's own events stay six-place strings (unchanged behaviour,
   verified by the existing `test_case1b`/`test_01`/`test_04` assertions on `result["events"]`).
   Added `test_case1c_exact_moves_survive_aggregation_no_double_rounding` with the verifier's
   exact three-value reproduction, asserting the fixed mean `"0.000001"`.
2. **BLOCKING, event_response_quant.py:69; event_response.py:166-170 non-finite handling
   incomplete** -- reproduced first: `bounded_floats([Decimal("sNaN")])` raised
   `ValueError: cannot convert signaling NaN to float` (a signalling NaN raises `ValueError` on
   `float()`, not `OverflowError`, so the existing `except OverflowError` never caught it); and
   `_summary()` with `venue_lag_s="Infinity"` gave `lag_median_s=None, lag_n=0, counters={}` --
   correct nulls but the non-finite input was dropped with no named counter, contrary to
   AMENDMENT 2. Fixed: `bounded_floats()` now catches `(OverflowError, ValueError)`, returning
   `None` instead of raising (added `test_case4c_signalling_nan_bounded_floats_returns_none`);
   `_summary()` compares `len(raw_lags)` to `len(lags)` and increments `counts["lag_non_finite"]`
   for the difference when positive (extended `test_case4b` with
   `assert counts["lag_non_finite"] == 1`).

Post-FIX-1d pass counts: `test_event_response.py` 13, `test_event_response_1c.py` 11,
`test_event_response_ops.py` 15 (13 + `test_case1c` + `test_case4c`).

## FIX 1e (verdict `_verdict_S457_opus_final.md`, ACCEPT WITH CORRECTIONS -> addressed)

(1) `pass2_prefilter` needles encoded `t.encode("ascii")`, crashing on a non-ASCII served ticker (`test_case3g` added, oracle-equivalence proven); (2) `test_atomic_write_and_partial_recovery`'s standalone `exact_move` recomputation was a weaker, out-of-pipeline proxy for the real parse -- replaced by `test_case1d_exact_move_survives_parse_float_decimal` in `test_event_response_ops.py`, which monkeypatches `quantise_event` to capture the real pre-quantise event and asserts its move is exactly `Decimal("1e-18")`, while `test_event_response.py` keeps only the `"0.000000"` output assertion (that file is at the 300-line cap); (3) case 2 and `test_01`'s whole-artifact comparisons were dict equality (weaker than the byte-identity the case names promise) -- both now compare `json.dumps(..., sort_keys=True, ensure_ascii=True, allow_nan=False)` of the two reports with `telemetry` excluded. Post-FIX-1e pass counts: `test_event_response.py` 13, `test_event_response_1c.py` 11, `test_event_response_ops.py` 17 (15 + `test_case1d` + `test_case3g`).

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED

- **Case 7 / the real-run gate (AMENDMENT 1e)**: the 2026-09-22 shards were NOT re-run here.
  This is explicit orchestrator work per the spec CONTROLS ("the real re-run is orchestrator work,
  never inside the lane") and the rails ("never a construct"). `runtime_s` on the real corpus,
  and the full event/reason comparison against REAL RUN 1's 89/49/16/5, remain to be recorded by
  the orchestrator after landing; the 1200s wall bar is unmeasured here.
- No network, no pod, no `data/` access was used anywhere in this build (construct/fixture tests
  only, as required).
- The hand recompute of two REAL RUN 1 events against the raw shards (already NOT VERIFIED on
  the parent S435 memo) remains owed and is not addressed by this row.
- Case 1 artifact sizes (5334 / 3302 bytes) and Case 7's real-shard equality / 1200s runtime bar
  were flagged NOT VERIFIED by the verifier and remain orchestrator/real-run work, unchanged by
  FIX 1b (no code path affecting the case-1 fixture or the real corpus was touched).
