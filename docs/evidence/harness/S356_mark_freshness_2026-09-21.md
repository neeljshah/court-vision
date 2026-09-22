# S356: capture-time mark selection

Implemented; local CONSTRUCT verification only. No archive measurement.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h14; CPU-only checks.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.
Vocabulary follows contract Q6; automated scan required.

## Binding premise

Before editing, ran this in-memory construction with Python on stdin:

```python
from scripts.platformkit.execution.markout_causal import resolve_marks, markout_strict
fill = dict(ticker='g1', fill_ts=0, side='yes', price=0.5,
            fee_units=0.01, fee_schedule_version='construct', qty=1)
ticks = [dict(ticker='g1', src_ts=t, yes_home_prob=0.5) for t in (0, 35, 125)]
for h, entry in resolve_marks(fill, ticks, horizons_s=(30, 120)).items():
    result = markout_strict(fill, entry['mark'])
    print(f"horizon={h:g} scored={result.value is not None} reason={entry['reason'] or result.reason}")
    assert entry['mark'] is None and entry['reason'] == 'stale_mark'
```

Exact before output (exit 0):

```text
horizon=30 scored=False reason=stale_mark
horizon=120 scored=False reason=stale_mark
```

After: `test_binding_before_condition_now_scores_both_flat_marks` passes for
the identical construction. Both marks are selected at 35 and 125 seconds;
both values equal minus the entry fee, and both reasons are None. The summary
reports two scored fill-horizon observations and zero unscored observations.
This is n = 2 (CONSTRUCT), exhaustive over the two specified horizons.
No file-backed input, video resolution or corpus byte size applies.

## Implementation and compatibility

- Edited scripts/platformkit/execution/markout_causal.py and
  scripts/platformkit/execution/markout_causal_windows.py.
- Select the earliest valid same-market tick by parsed src_ts in the existing
  bounded window. No comparison with a previous price occurs during selection.
- max_wait_s was already 30 seconds; retain that default and its override.
  Preserve inclusive uncapped endpoints and exclusive next-horizon caps.
- Add optional keyword max_book_age_s, default None, to selection and summary.
  stale_mark now means ONLY an observed finite book_age_sec greater than that
  limit. Equality passes. Missing, null or unusable age is not evidence of
  staleness and passes this rule. Invalid caller limits raise ValueError.
- Preserve existing parameter names, positional calling conventions, defaults,
  return structures, tuple fields, reason strings and summary keys. Only
  optional keywords and summary fields are added. reason_for_tick retains its
  is_fresh argument for compatibility but ignores it. freshness_by_index retains
  its signature and legacy behavior and has no caller in mark selection.
- Add per-horizon mark_delay_median_s, mark_delay_p90_s, mark_delay_max_s and
  no_qualifying_mark_share. Delay is mark time minus fill time minus horizon.
  Delays include every qualifying mark, including marks for fills with invalid
  fees; median averages the middle pair, p90 uses nearest rank, max is exact.
  Missing-mark share divides fills without a qualifying mark by ALL fills,
  including malformed fills. With no fills the share is None; with no marks
  delay fields are None. Existing scored counts retain their original meaning.
- Only test_stale_repeated_tick_reason_is_specific was rewritten and renamed
  test_stale_book_age_tick_reason_is_specific: it had encoded price-change
  freshness. All other existing tests are unchanged. New constructs live in
  tests/platformkit/execution/test_markout_mark_selection.py to respect the cap.
- Reader census across scripts and tests found only summary_strict, _demo and
  tests/platformkit/execution/test_markout_causal.py consuming resolve_marks;
  summary_strict's external consumers were only that test file. The two windows
  helpers were used only by resolve_marks before this change.
- git diff against master confirms scripts/platformkit/ingame/quote_freshness.py
  and tests/platformkit/execution/test_markout.py are untouched.

## Other freshness_mask callers under scripts/platformkit

PowerShell recursive Select-String census (rg unavailable), followed by reading
each caller. Verdicts concern the declared control or diagnostic, not proof of
capture freshness. No caller below was changed.

| Caller | Verdict |
| --- | --- |
| scripts/platformkit/ingame/ingame_outcome_verdict_freshness.py, _brier_by_game_segment_both | Appropriate for the explicitly price-change-only calibration control; cannot establish capture age. |
| scripts/platformkit/ingame/ingame_soccer_trust_rerun.py, _accumulate | Appropriate for the optional price-change-only control arm; cannot establish capture age. |
| scripts/platformkit/ingame/quote_freshness.py, filter_fresh | Appropriate for its documented syntactic price-change subset. |
| scripts/platformkit/ingame/quote_freshness.py, freshness_share | Appropriate as a price-change share diagnostic. |
| scripts/platformkit/ingame/quote_freshness.py, longest_stale_run | Appropriate as a consecutive unchanged-price diagnostic. |
| scripts/platformkit/ingame/test_quote_freshness.py, eight direct test calls | Appropriate tests of the existing syntactic contract; not executed by this row. |

The retained scripts/platformkit/execution/markout_causal_windows.py helper
freshness_by_index still calls the mask for public compatibility. Its use for
endpoint eligibility was inappropriate and has been removed from selection.
Indirectly, scripts/platformkit/ingame/ingame_freshness_cross_corpus.py calls
_brier_by_game_segment_both in _fresh_only_verdict_for_half: appropriate as the
same declared control. tick_informative.py mentions the definition without
calling it; paper_maker.py, quote_engine.py and inplay_daytrader_maker.py import
other utilities, not this mask.

## Verification

Executed sequentially, one file per invocation:

```text
python -m pytest tests/platformkit/execution/test_markout_causal.py -q -p no:cacheprovider
31 passed
python -m pytest tests/platformkit/execution/test_markout_mark_selection.py -q -p no:cacheprovider
10 passed, 18 subtests passed
python -m pytest tests/platformkit/execution/test_markout.py -q -p no:cacheprovider
13 passed
python -m pytest tests/platformkit/execution/test_venue_time.py -q -p no:cacheprovider
65 passed
python -m scripts.platformkit.execution.markout_causal
markout_causal self-check OK
```

The new constructs cover flat marks, unchanged-before-moved selection, bounded
search and override, optional book age and its boundary, rejected candidates,
existing reason precedence, delay quantiles, parsed timestamps, empty inputs,
and denominators that include missing marks and invalid fees.

Required automated scan command:

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/markout_causal.py scripts/platformkit/execution/markout_causal_windows.py tests/platformkit/execution/test_markout_causal.py tests/platformkit/execution/test_markout_mark_selection.py docs/evidence/harness/S356_mark_freshness_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S356_spec.md
```

Automated preflight: exit 0, all nine checks PASS (vocab, crlf, loc, schema,
head_slice, spec_threshold, proposed, removed_artifact, row_duplication).

B/Q self-check: all-fill denominators, additive fields and checked readers;
missing age evidence does not reject a tick; no orphaned imports or artifacts;
no gate threshold changes. Queue, render, deployment, model fitting and scored
comparison clauses do not apply to this enumerated construction. No trial or
register writes, feature activation, data access, network or pod activity.
All changed files are ASCII and below the 300-line cap; new dependencies are
stdlib only. Source files remain on disk for lane_commit.

## NOT VERIFIED

- Real archive behavior, real capture age availability and real delay distributions.
- Any measured calibration result or out-of-sample comparison.
- Production use, deployment, pod state or service integration; pod use is OFF.
- Independent verifier rerun on master, commit creation and landing.
