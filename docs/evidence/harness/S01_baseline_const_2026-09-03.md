# S01 baseline constants

Log: `cx_s01_baseline_const`
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q8.

## Premise and acceptance result

The premise was measured before the change through the module's own
`_load_ticks(discover_store(Path("data/cache")))` path. The discovered local
store was `data/cache/ingame_grade_joined`; its canonical source is the
`mlb/` child directory.

| Denominator | Loader count before and after | Old constant | New constant | Result |
| --- | ---: | ---: | ---: | --- |
| ticks | 52,558 | 144,424 | 52,558 | matches |
| window ticks | 7,158 | 14,802 | 7,158 | matches |

Metric: constants equal loader counts; denominator: both constants.
Before: 0/2. Bar: 2/2. After: 2/2.
n: 2 (CONSTRUCT), exhaustively enumerating the two baseline constants.
Eye check: n/a (S-row); reproduction: run the focused test in master, which
recomputes `_load_ticks` counts and checks the module's `baseline_corpus.matches`
flag.

Non-tautology: the metric covers both constants and excludes no constant or
loader count. The loader output is independent of the two fixed constants.

## Commands and output

```text
python -c "from pathlib import Path; from scripts.platformkit.ingame.run_gap_arms_real_corpus import _BASELINE_TICKS, _BASELINE_WINDOW_TICKS, _load_ticks; from scripts.platformkit.ingame_replay_scoreboard import discover_store; store = discover_store(Path('data/cache')); assert store is not None, 'no parseable tick store'; ticks, _ = _load_ticks(store); window_count = sum(tick['in_window'] for tick in ticks); print('store=%s' % store); print('len(ticks)=%d' % len(ticks)); print('window_ids=%d' % window_count); print('constants=%d/%d' % (_BASELINE_TICKS, _BASELINE_WINDOW_TICKS)); print('premise_holds=%s' % (len(ticks) == 52558 and window_count == 7158 and (_BASELINE_TICKS, _BASELINE_WINDOW_TICKS) != (52558, 7158)))"
store=data\\cache\\ingame_grade_joined
len(ticks)=52558
window_ids=7158
constants=144424/14802
premise_holds=True

python -m pytest tests/platformkit/ingame/test_gap_arms_baseline_constants.py -q
.                                                                        [100%]
1 passed in 25.27s
```

## Contract self-check

- B1: Both denominators are included; none is filtered out.
- B2: No schema, field, status, or reader changes.
- B3: No gate behavior changes.
- B4: No claim or retry behavior changes.
- B5: No deployment action.
- B6: No module move, retirement, or import change.
- B7: No sampled render evidence; this is an exhaustive construct.
- B8: No fitted or scored comparison.
- B9: The two fixed baseline constants are distinct, named denominators.
- B10: No harness threshold or gate value changes.
- Q1: No scored comparison is made.
- Q2: No charged trial is run.
- Q3: The acceptance bar remains 2/2.
- Q4: No out-of-sample score is made.
- Q5: No AHEAD result is made.
- Q6: Calibration language only; no financial performance statement.
- Q7: `n = 2 (CONSTRUCT)` enumerates every constant; reproduction replaces an eye check.
- Q8: The premise was re-measured before editing.

## NOT VERIFIED

- The verifier has not yet rerun the focused test in master.
- No remote host or pod was contacted.
- No other files under `scripts/platformkit/ingame/` were changed.
- No `scripts/platformkit/eval_gate/` threshold, `data/registry/` file, or
  `data/cache/eval_gate/backtest_fwer.jsonl` file was touched.
