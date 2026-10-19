**S670 - HOLD**

- **Missing horizons can produce false TRUSTED results.** `scripts/platformkit/execution/series_gate.py:122` accepts an absent/null horizon; line 174 drops that game before calculating missing share. Removing adverse games' horizon blocks can leave sufficient positive games and zero reported missing quantity. This violates B1 despite the spec permitting omission. Fix: require explicit horizon accounting, mark absent evidence INSUFFICIENT, and retain excluded-game counts. `tests/platformkit/execution/test_series_gate_fix.py:36` tests missing fields and the entire `h` block, but misses this partial-block case.
- **The public API bypasses configuration validation.** `scripts/platformkit/execution/series_gate.py:220` trusts any supplied `cfg`. Lowering games/fills to 3 and corpora to 1 without changing the hash lets three constant-positive games satisfy the gate. Fix: apply the same hash, shape, and minimum checks to supplied dictionaries as to loaded files. `tests/platformkit/execution/test_series_gate.py:184` checks only `load_config`, leaving this bypass untested.

No unlanded code prerequisite or separate Windows defect found.

| S670 | HOLD | None | Missing horizons can produce false TRUSTED | M |
