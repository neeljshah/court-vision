# S369: causal mark identity, tie ordering, clustering, and probability units

Implementation and construct regressions PASS in nba-harness-h27.
Vocabulary follows contract Q6; automated scan required.

## Authority and scope

Authority: docs/evidence/tracking/specs/S369_spec.md and
docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md, findings 6 and 7a.
Contract sections B and Q were read, together with the complete S343, S344,
S345, S354, S356, and S357 specs and their amendment blocks.
All work ran locally in C:/Users/neelj/nba-harness-h27.
No archive, network, service, or pod was used. No measured result is reported.

Finding 6, quoted from the audit:

> **BLOCKING ? mark identity, clustering, and tie-breaking are wrong.**
> Repro: fill `game_id=G1` accepted a same-ticker `G2` tick; reversing two equal-time ticks changed mid `0.6?0.8`; two tickers from one game reported two default clusters.
> **Fix:** require matching `game_id`, reject conflicting equal-time marks unless a capture sequence breaks ties, and default clustering to `game_id`.

Finding 7, the markout portion quoted from the audit:

> **BLOCKING ? money-unit guards still fail open.**
> Repro: markout accepted cents `price=55` and returned `-54.4`;

The remaining fee-function portion of finding 7 is outside this row.
The new test file is authorized by the cap escape in S369: the existing causal
test file has 271 lines, so the added cases would exceed 300 lines there.
FIX 1b also updates the valid direct-mark fixture in test_fractional_chain.py
to supply its explicit ticker, as required by the verifier's second finding.

## Reproduction before module edits

Added four audit assertions before editing either module, then ran:

```text
python -m pytest tests/platformkit/execution/test_markout_identity_units.py -q -p no:cacheprovider
```

Exact failure excerpts, in test order:

```text
test_audit_cross_game_mark
E       AssertionError: {'mark': {'mid': 0.6, 'ticker': 'T1', 'ts': 30.0}, 'reason': None}

test_audit_equal_time_conflict
E       AssertionError: [{'mark': {'mid': 0.6, 'ticker': 'T1', 'ts': 30.0}, 'reason': None}, {'mark': {'mid': 0.8, 'ticker': 'T1', 'ts': 30.0}, 'reason': None}]

test_audit_one_game_two_tickers
E       assert 2 == 1

test_audit_cents_price
E       AssertionError: MarkoutResult(value=-54.4, reason=None, exit_fee_units=None, remaining_inventory_qty=0.53)

4 failed in 0.97s
```

After editing the modules, the same four assertions passed:

```text
....                                                                     [100%]
4 passed in 0.62s
```

These assert cross_game_mark, conflicting_equal_time_marks in both input
orders, one default cluster, and price_not_probability with value=None.

## Implementation

- markout_causal.py now matches both ticker and any mutually present game_id.
  Direct markout_strict calls also reject contradictory identity evidence.
  Missing game_id preserves compatibility; it is not treated as a mismatch.
- markout_causal_windows.py groups usable in-window ticks by source timestamp.
  Only the earliest usable timestamp group decides the mark or refusal.
  Different mids in that group require ordering evidence. Later groups cannot
  change the decision. Invalid ticks cannot compete; unchanged mids are eligible.
- Equal-time groups first try ascending response_end_ts, parsed only by
  parse_venue_time; if that cannot resolve every distinct mid, ascending seq
  is tried. seq is parsed exactly as Decimal from strings or integers, so
  large adjacent sequences remain distinct. Both rows must carry usable
  values in the same field. Equal keys may duplicate an identical mid, but
  cannot hide differing mids. Equal-time invalid reasons sort deterministically.
- Default summary clusters use game_id, with ticker fallback only when it is
  absent. Source namespaces prevent fallback ticker IDs colliding with game
  IDs. Added cluster_key reports the requested key; per-horizon cluster_sources
  counts scored fill-horizon observations using each source. Explicit caller
  cluster_key still works. Canonical cluster/value ordering stabilizes the
  reused cluster_boot_ci, means, and leave-one-game-out calculations.
- Original decimal price and mid values are checked against inclusive [0, 1]
  before rounding can conceal a breach. markout_strict adds the two specified
  range reasons; absent/nonfinite values retain price_or_mid_unusable.
  Resolver mid rejections retain mid_unusable_mark. NaN and infinity remain
  rejected with the shared math.isfinite gate. Parser exceptions are counted.

Additional boundary constructs initially exposed four rounded-range failures:

```text
4 failed, 57 passed in 1.06s
```

Both price and mid had accepted "1.000000000000000001" and "-1e-999".
Exact checks now cover direct scoring and resolver selection; distinct decimal
mids also cannot round into an apparently identical equal-time group.

## Compatibility and contract checks

Public parameter lists and result fields remain intact. The S369-mandated
cluster_key default changes from ticker to game_id; explicit ticker callers
retain that behavior. Existing reason strings remain; the specified new
reasons extend the vocabulary. Default wait remains 30 seconds, window
partitioning and endpoint rules are unchanged, and stale_mark still means
only an observed excessive book_age_sec. Delay statistics still include every
qualifying mark even when fee evidence prevents scoring. No price-change
freshness path is consulted. No fees, flags, thresholds, or ledger code changed.

Reader search under scripts/ and tests/ found the causal module as the windows
reader and the causal, mark-selection, and fractional-chain test readers.
All are covered below. The legacy markout test is also required by S343/S356.
The existing MarkoutResult.remaining_inventory_qty float presentation is
preserved for B2 and the explicit S357 JSON/float reader contract. New tests
provide quantities as strings; this row adds no size arithmetic or conversion.
Changing that legacy presentation requires an additive consumer migration.

## FIX 1b

Binding verdict: _verdict_s369_1b.md, three BLOCKING findings, no CORRECTION
entries. Read the local spec and `git show master:docs/evidence/tracking/specs/S369_spec.md`;
both contain the same requirements and neither has an AMENDMENT block.
All reproductions below ran before module edits and again after the fixes.

1. Later conflicts changed an earlier mark. Construct: fill T1/G1 at time 0,
   tick at 30 with mid 0.6; append ticks at 31 with mids 0.7 and 0.8.
   select_candidate now returns from the first usable timestamp group,
   resolving or refusing that group's ties without inspecting later groups.
   Corrected the named later-conflict regression to assert unchanged selection
   and summary under every permutation; added first-usable-group conflict
   coverage with earlier invalid ticks and an independently scored horizon.

```text
Before, one tick: {'mark': {'ts': 30.0, 'ticker': 'T1', 'mid': 0.6}, 'reason': None}
Before, appended: {'mark': None, 'reason': 'conflicting_equal_time_marks'}
After, one tick: {'mark': {'ts': 30.0, 'ticker': 'T1', 'mid': 0.6}, 'reason': None}
After, appended: {'mark': {'ts': 30.0, 'ticker': 'T1', 'mid': 0.6}, 'reason': None}
```

2. Missing ticker evidence was fabricated. Construct: fill T1/G1, price 0.55,
   fee 0, quantity 0.53; direct mark ts=30, mid=0.6, game_id=G1 without ticker.
   Also remove the fill ticker. markout_strict now requires both tickers and
   compares the original records. Missing, None, and empty tickers on either
   or both records have nine regressions. Valid direct-mark fixtures now carry
   tickers; mismatches retain cross_game_mark.

```text
Before, mark ticker absent and both absent (each):
MarkoutResult(value=0.04999999999999993, reason=None, exit_fee_units=None, remaining_inventory_qty=0.53)
After, mark ticker absent and both absent (each):
MarkoutResult(value=None, reason='ticker_missing', exit_fee_units=None, remaining_inventory_qty=None)
```

3. Finite Decimal overflow bypassed the specific range reason. Construct:
   set price="1e10000", then mid="1e10000", with matching ticker evidence.
   One exact probability_decimal parser now classifies original values before
   conversion. Malformed/nonfinite inputs retain price_or_mid_unusable;
   finite out-of-range values receive the price/mid-specific reason. Bounded
   values then pass through the existing math.isfinite float gate. Regressions
   cover positive huge strings and negative huge Decimals for both fields.

```text
Before, huge price and huge mid (each):
MarkoutResult(value=None, reason='price_or_mid_unusable', exit_fee_units=None, remaining_inventory_qty=None)
After, huge price:
MarkoutResult(value=None, reason='price_not_probability', exit_fee_units=None, remaining_inventory_qty=None)
After, huge mid:
MarkoutResult(value=None, reason='mid_not_probability', exit_fee_units=None, remaining_inventory_qty=None)
```

The regression file first reported `14 failed, 64 passed in 1.21s` against
the candidate modules, then `78 passed in 0.69s` after these module fixes.
The fractional-chain fixture initially reported `1 failed, 25 passed in 1.11s`
with `reason='ticker_missing'`; supplying ticker T yielded `26 passed in 0.70s`.

B1/B7/B8/B9: enumerated constructs only, with explicit observation counts.
B2/B6: no fields, public call names, files, imports, or reasons removed.
B3/B4: no new claim loop or evidence quarantine; missing fields are not zero.
B5/B10 and Q3: no deployment and no acceptance threshold changes.
Q1/Q2/Q4/Q5: no scored comparison, trial charge, or corpus result in this row.
Q6: automated contract vocabulary scan required below.

## FIX 1c

Binding verdict: _verdict_s369_1c.md. Finding 1 is BLOCKING; there are no
CORRECTION entries. Local and master S369 specs match, with no AMENDMENT block.

1. Large digit-only capture sequences were refused by math.isfinite's float
   conversion. Applied the exact fix in markout_causal_windows._sequence:
   return result when result.is_finite(), removing math.isfinite(result).
   Added ("1" + "0" * 400, "2" + "0" * 400) to the existing sequence-order
   regression, which checks both input permutations. Nonfinite sequence
   regressions still pass. No other module behavior changed in FIX 1c.

The verifier's minimal construct uses fill T1/G1 at time 0 and two same-time
ticks at 30, with the above sequences and respective mids (0.6, 0.7).
Exact output before the module edit, identical in both input orders:

```text
{'mark': None, 'reason': 'conflicting_equal_time_marks'}
```

After the module edit, identical in both input orders:

```text
{'mark': {'ts': 30.0, 'ticker': 'T1', 'mid': 0.6}, 'reason': None}
```

The added regression first failed against the candidate:
`E AssertionError: assert ('conflicting_equal_time_marks' is None)`;
`1 failed, 78 passed in 1.16s`. After the exact fix: `79 passed in 0.71s`.

2. Finding 2 is NOTE / NEW GAP, explicitly outside S369 acceptance. The legacy
   quantity presentation is unchanged; an exact decimal-string result path
   and consumer migration remain assigned to a separate additive row.
   The verifier's confirmed identity, clustering, range, and window behavior
   is unchanged. FIX 1c edits only the windows module, regression, and memo.

## Final per-file verification (FIX 1c)

Every command ran separately, one file at a time:

```text
python -m pytest tests/platformkit/execution/test_markout_identity_units.py -q -p no:cacheprovider
79 passed in 0.71s
python -m pytest tests/platformkit/execution/test_markout_causal.py -q -p no:cacheprovider
31 passed in 0.58s
python -m pytest tests/platformkit/execution/test_markout_mark_selection.py -q -p no:cacheprovider
10 passed, 18 subtests passed in 0.62s
python -m pytest tests/platformkit/execution/test_fractional_chain.py -q -p no:cacheprovider
26 passed in 0.60s
python -m pytest tests/platformkit/execution/test_markout.py -q -p no:cacheprovider
13 passed in 0.50s
```

Total: 159 passed tests, plus 18 passed subtests. The full suite was not run.
The fractional-chain run uses the committed eight-row public fixture, not an
archive. All other new cases are enumerated synthetic inputs.
Repository-wide conftests ran with these exact commands; no confcutdir override.

`python -m scripts.platformkit.execution.markout_causal --help` and
`python -m scripts.platformkit.execution.markout_causal` each printed
`markout_causal self-check OK`. This module has no argument parser, so --help
runs its self-check. `python -m scripts.platformkit.execution.markout_causal_windows --help`
exited successfully without output; the helper has no CLI or self-check.

## Contract preflight

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/markout_causal.py scripts/platformkit/execution/markout_causal_windows.py tests/platformkit/execution/test_markout_identity_units.py tests/platformkit/execution/test_fractional_chain.py docs/evidence/harness/S369_markout_identity_units_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S369_spec.md
PASS vocab clean over 5 files
PASS crlf no index-side CRLF over 5 file(s); 2 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 4 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

All nine preflight checks passed. No threshold lines are declared by this spec;
that check is explicitly a no-op, not evidence of a numerical comparison.
No commit was created; files are ready for lane_commit.

## NOT VERIFIED

- Runtime or archive mark coverage, and production caller integration.
- Venue ordering guarantees for response_end_ts and seq; ordering is a caller
  evidence contract tested with constructs here.
- Exact quantity presentation beyond the preserved legacy result field.
- Missing game identity cannot establish a same-game match independently.
- Deployment, pod state, and a committed SHA; files remain for lane_commit.
