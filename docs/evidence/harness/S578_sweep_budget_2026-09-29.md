# S578 per-file sweep budget (test-side memo + splits) -- 2026-09-29/30

Row S578, spec docs/evidence/tracking/specs/S578_spec.md (AMENDMENT 1 binding). Worktree
C:/Users/neelj/nba-harness-h247, branch harness-h247. Test-side only: no file under scripts/ is
edited; quote_reservation.py and position_caps.py are untouched (sha pins in
test_paper_account.py unaffected). Every run below was one pytest process at a time, only at
psutil available >= 1500 MB, on this laptop while games were live.

## Result

Five of five bars met; the dense cross-sport file is split out and reported OVER-CAP (not a pass).

| file | before (register / spec) | after wall_s | after summary | peak_rss_mb | collect before / after |
|---|---|---|---|---|---|
| ingame/test_four_arm_output_audit.py | 261-299 s | 51.7 | 94 passed in 49.59s | 145 | 94 / 94 (identical ids) |
| ingame/test_nba_four_arm_output_audit_exposure.py | timeout | 43.6 | 84 passed in 41.64s | 168 | 84 / 84 (identical ids) |
| ingame/test_nba_four_arm_output_audit_fix1h.py | timeout | 42.6 | 38 passed in 39.93s | 169 | 38 / 38 (identical ids) |
| ingame/test_nba_four_arm_primary_contrast.py | timeout (whole, 278) | 53.7 | 140 passed in 50.56s | 169 | 278 / 140 + 138 (union identical) |
| ingame/test_nba_four_arm_primary_contrast_endpoints.py (new) | -- | 34.5 | 138 passed in 32.62s | 177 | (see above) |
| ops/test_forward_qualification_cross_sport.py (fast 21) | timeout (whole, 25) | 8.1 | 21 passed in 5.47s | 111 | 25 / 21 + 4 (union identical) |
| ops/test_forward_qualification_cross_sport_dense.py (new) | -- | OVER-CAP | see disclosure | 123 | 4 (exact original names) |
| ingame/test_audit_memo.py (new) | -- | -- | 19 passed in 27.45s | -- | 19 |

Metric = run_file(path, timeout_s=300, max_rss_mb=500) from
scripts/platformkit/ops/per_file_test_sweep.py, exit 0. Bar = wall_s < 120 and peak_rss_mb < 250.
Collect comparisons: `--collect-only -q` on master (clean) vs the worktree, ids sorted and
compared byte for byte after mapping the new module path back to the original (only the module
path of moved tests changes).

Per-test after durations (file 1, -k row_order or optional_ledger or exact_large_integer, first
run): setup 3.23 s (first build, cold cache) then 0.87 s; call 1.14 s (row_order), 0.15 s, 0.01 s
(before: 1.56-1.85 s setup, 1.05-3.13 s call).

## What changed

1. tests/platformkit/ingame/audit_memo.py (new, 74 lines): `key` = sha256 digest of
   pickle.dumps((qualname, args, sorted(kw.items())), protocol=5); pickling error -> None and the
   wrapper calls the real function uncached; exceptions propagate and are never stored; results
   deep-copied on store and on return; per-function process-wide caches with `reset_caches()`;
   wrappers carry `__wrapped__`. Module-scoped fixtures with their own MonkeyPatch context:
   `memo_bootstrap` (four_arm_output_audit_checks.bootstrap) and `memo_audit` (that plus
   nba_four_arm_output_audit_checks.reconstruct and game_first, and
   nba_four_arm_output_audit_declared.reconstruct, the same wrapper object). No conftest.
2. test_four_arm_output_audit.py: `@memo` on `cell`, one import line,
   `pytestmark = pytest.mark.usefixtures('memo_bootstrap')`; stays at 300 lines by folding the
   two stdlib import lines and making `read` / `result_check` one-liners. reference_bootstrap and
   every test body are byte-identical; the import-time `bootstrap` stays the real function (M10).
3. exposure and fix1h: one import line + pytestmark each, nothing else.
4. primary_contrast: one module fixture `lag_control` = (rows, control, {False: forward
   recomputation, True: reversed recomputation}), computed outside any monkeypatch, consumed via
   copy.deepcopy by test_lag_membership_before_warmup only. DEVIATION from AMENDMENT 1 change 5
   (which names a 3-tuple): the forward recomputation is kept as its own entry so the
   reverse=False determinism check (control == recomputation) still compares two independent
   computations instead of an object with itself. No landed memo, no other shared fixture.
   Split by LOC and measured duration: test_carried_lag_before_exclusion,
   test_carried_endpoint_loss_before_exclusion, test_subset_warmup_saved_loss_before_exclusion and
   test_s405_endpoint_acceptance moved verbatim (line-for-line equal to master) into
   test_nba_four_arm_primary_contrast_endpoints.py, importing landed, preserve,
   supported_lag_rows from the original. s417_golden, source_rows, supported_lag_rows, landed stay
   in the original (test_nba_four_arm_trial_contrast.py:119/:269 import s417_golden).
5. cross_sport: the 4 dense tests moved verbatim (checked: the moved text is a substring of
   master's file and master minus that block equals the new original) into
   test_forward_qualification_cross_sport_dense.py, importing exactly DAY, NEXT, game, invoke,
   jsonl, keyed, populate, qualification, state, write (no `test_` name). No skip / xfail / slow
   marker; no sweep, conftest, pytest.ini or pyproject exclusion names the dense file (F9 grep:
   only the docstring and the original parametrize line match).

Non-mutation (AMENDMENT 1 change 3), read and asserted by M13: four_arm_output_audit_checks
bootstrap (:179-198), nba_four_arm_output_audit_checks reconstruct (:116-145) and game_first
(:146-164), and file-1 cell (:28-47 before the edit) do not mutate their arguments.

## Construct cases (n = 19 tests in test_audit_memo.py, CONSTRUCT)

M1 equal args one real call; M2 one-ulp row change misses; M3 arm / metric / weighting each miss
(3 params); M4 1 / 1.0 / True / 0.0 / -0.0, int vs str dict key, tuple vs list all distinct; M5
NaN vs None distinct; permuted dict order misses and equals the real call; M6 raise twice, nothing
stored; M7 lambda and generator arguments uncached and equal to the real call; M8 mutating a
returned dict does not change the next return; M9 memo_audit patches declared.reconstruct too and
nba.audit memoised twice == unmemoised (json sort_keys), verdict_release True; M10 file-1
import-time bootstrap has no __wrapped__ and is the real function; M11 reset_caches empties every
cache; M12' memoised cell == cell.__wrapped__ on the four subsets for params False, 'float', True,
and a cleared return does not leak; M13 no argument mutation. F1-F7 are the table rows above; F8
the dense collect list; F9 the marker/exclusion grep.

## Mutations (plugin or scratch copy in the OS temp dir; repo never edited; clean run 19 passed)

- (a) drop `arm` from the key: M3[arm] red (also M7 x2 by construction of the plugin, and M9) -- 4 failed.
- (b) key on game ids only: M2 red (plus M3 x3, M4, M5, dict order, M7 x2, M9, M12'[True]) -- 11 failed.
- (c) return the stored object without deepcopy (all wrappers): M8 red, M9 red, M12' x3 red -- 5 failed.
- (d) store None when the real call raises: M6 red -- 1 failed.
- (e') cell memo (memo factory only) returns without deepcopy: M8 and M12' x3 red -- 4 failed.
- (g) lag_control returns the forward control for the reversed call: SURVIVES (24 passed). By
  construction: the asserted property is serialized(forward) == serialized(reversed), so swapping
  in the forward value cannot be told apart. Reported, not hidden. Substitute (g'): the reversed
  recomputation drops one row -> 12 failed of 24 (every reverse=True case red).

## FOR-EXECUTION-LEAD disclosure (dense window; no scripts/ edit in this row)

The four dense tests pin qualified_decisions == 720 and covered_ms == WINDOW_S * 1000
(forward_replay_qualification.py:16, WINDOW_S = 3600), so the window cannot shrink without
changing what they assert. Builder measurement: the dense test
test_missing_d_with_sufficient_next_day_uses_frozen_bars, run alone through run_file with
timeout_s=120, max_rss_mb=250: exit timeout at 120.8 s, peak_rss_mb 123 (it runs; it does not
finish inside 120 s). The spec's before-condition tables (not re-measured by the builder): one
single-game replay at rows 30 / 60 / 120 / 240 took 1.4 / 3.5 / 11.1 / 46.4 s (time ~ rows^2.06,
extrapolating to ~445 s per 720-row invoke; extrapolated, not measured); a synthetic check_caps
call costs 18 us / 323 us / 1510 us / 8668 us at 0 / 50 / 200 / 1440 orders in the snapshot, linear
in ORDERS including closed ones. Mechanism by citation: quote_reservation.py:176-184 bisects
with check_caps at :180 (~14 probes per decision); position_caps.py:36-37 runs decimal_values on
the snapshot and on exposure_book, which runs decimal_values again (position_exposure.py:12)
and walks every order, skipping closed ones only after the walk (:17-18). A naive test-side memo
of decimal_values keyed on json.dumps was tried by the spec author and is NOT output-identical
(rows=60: qualified 60 -> 0, RESERVATION_INVALID 60); it is disclosed, not built.
Question for the execution lead (new register row requested): should reserve() walk the snapshot
once per call rather than once per bisection probe, and should closed orders be skipped before
the decimal walk? The orchestrator runs the dense file once under `timeout 900` when RAM allows.

## NOT VERIFIED

- The dense file's whole-file wall is not measured on this box (expected > 300 s).
- The 120 s bar is load-sensitive: walls above were taken with live games on the box; a
  loaded or cold machine may move them.
- s405 is not memoised (each param mutates rows; the landed memo was not built because both
  primary_contrast files are under 120 s without it).
- The spec's check_caps / replay probe tables are quoted from the spec, not re-run by the builder;
  the probe code is reproduced verbatim in the appendix below (spec-writer probes, 2026-09-30).
- Candidate HEAD: none (the builder does not commit). Verification base
  f3377a8029631fd1ef533bd2255eab44f41c829e. Candidate vs base: NOT EQUAL by construction (working
  tree changes uncommitted).

## A9 identities (sha256 of LF-normalised bytes, recomputed from disk as the last edit)

- tests/platformkit/ingame/audit_memo.py: 9542b6fc6f9f88381f99807f7c788bb35d6f262c2cfbf34d2f57b7ff1327bcb9 (74 lines)
- tests/platformkit/ingame/test_audit_memo.py: befa8166e802d3addbb3e9333b3bdab4954a025054b6c1715cddfaf682df9b7c (142 lines)
- tests/platformkit/ingame/test_four_arm_output_audit.py: 6294b7a9da80b3f6b96103b88db206bc91a57f8332c064de88cb3342e5e12b4e (300 lines)
- tests/platformkit/ingame/test_nba_four_arm_output_audit_exposure.py: 7fb3aef51681e6a08c848d402c8356a102a548aaaf8d31c9451cdc52aeafddd6 (296 lines)
- tests/platformkit/ingame/test_nba_four_arm_output_audit_fix1h.py: b2c4fcb7d2c0a895f7b617c16c71592fc6c41996fb7ee2461316b73af45cbc87 (286 lines)
- tests/platformkit/ingame/test_nba_four_arm_primary_contrast.py: bd4da6f92608d437f40ef9d94ca12a19502fdbb8b069f68cd16d16885fb716ee (255 lines)
- tests/platformkit/ingame/test_nba_four_arm_primary_contrast_endpoints.py: 7f7eea8ede989ce6ad6f3070a07748ae41996e46b3843db9b5e922dbee1aaa59 (56 lines)
- tests/platformkit/ops/test_forward_qualification_cross_sport.py: ec1325ede1b3a9b696ba2e40e371f24733c294a690a5ec52b0746e3db17f1509 (211 lines)
- tests/platformkit/ops/test_forward_qualification_cross_sport_dense.py: c7839b574f995ca38ae7e81c916132c9535ee50bdf6d5c1306a9de429de3962e (94 lines)

## APPENDIX: reproduction probes (for the execution lead; run from the repo root, one at a time, < 250 MB)

### probe_caps.py

```python
import sys, time, psutil
sys.path.insert(0, '.')
from scripts.platformkit.execution.position_caps import check_caps
def snap(n):
    orders = {f"o{i}": dict(open=(i >= n - 4), side="yes", ticker="T0", game_id="G0", qty="1", filled_qty="0",
                            unfilled_qty="1" if i >= n - 4 else "0") for i in range(n)}
    by = {f"T{i}": dict(net_qty="0", game_id="G0") for i in range(1)}
    return dict(by_ticker=by, orders=orders)
caps = {"global": "100"}
for n in (0, 50, 200, 1440):
    s = snap(n); reps = 200
    t = time.perf_counter()
    for _ in range(reps):
        check_caps(s, caps, order_id="new", ticker="T0", game_id="G0", side="yes", qty="3")
    per = (time.perf_counter() - t) / reps
    print(f"orders={n} check_caps_us={per*1e6:.0f} decisions_per_s_at_14_probes={1/(14*per):.1f}")
print("rss_mb", psutil.Process().memory_info().rss // 2**20)
```

### probe_dense2.py

```python
import sys, time, tempfile, json, hashlib
from pathlib import Path
sys.path.insert(0, '.')
from tests.platformkit.ops import test_forward_qualification_cross_sport as t
from scripts.platformkit.execution import position_caps as pc, position_exposure as pe


class MP:
    def setattr(self, obj, name, val):
        setattr(obj, name, val)


def memo(fn):
    cache = {}

    def wrapped(value):
        if not isinstance(value, (dict, list)):
            return fn(value)
        key = json.dumps(value, sort_keys=True)
        if key not in cache:
            cache[key] = fn(value)
        return cache[key]
    wrapped.cache = cache
    return wrapped


def run(n, patched):
    orig = (pc.decimal_values, pe.decimal_values)
    if patched:
        m = memo(orig[0])
        pc.decimal_values = m
        pe.decimal_values = m
    try:
        g = t.game("mlb")
        root = Path(tempfile.mkdtemp(prefix="s578_"))
        for kind in ("kalshi", "state"):
            for day in (t.DAY, t.NEXT):
                t.write(root / kind / "mlb" / (day + ".jsonl"), b"")
        t.write(root / "kalshi" / "mlb" / (t.NEXT + ".jsonl"), t.jsonl([t.book(g, i * 5) for i in range(n)] + t.tape(g)))
        t.write(root / "state" / "mlb" / (t.NEXT + ".jsonl"), t.jsonl([t.state(g, i) for i in range(0, n * 5, 15)]))
        a = time.perf_counter()
        body = t.invoke(root, [g], MP())
        w = time.perf_counter() - a
        return w, hashlib.sha256(json.dumps(body["games"], sort_keys=True).encode()).hexdigest()[:12] + " q=" + str(body["games"][0]["qualified_decisions"]) + " rc=" + json.dumps(body["games"][0]["reason_counts"], sort_keys=True)
    finally:
        pc.decimal_values, pe.decimal_values = orig


for n in (60,):
    for patched in (False, False, True):
        w, h = run(n, patched)
        print(f"RESULT rows={n} patched={patched} wall_s={w:.1f} games_sha={h}", flush=True)
```
